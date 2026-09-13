"""Ponto de entrada da camada semantica.

    consulta semantica -> validacao -> execucao -> certificacao -> resposta

Uma funcao, `ask`, e toda a superficie que o MCP vai consumir na F8. Ela recebe
o objeto que a IA emitiu (ou o dicionario equivalente) e devolve um `Answer`,
que pode ser uma resposta, uma recusa ou uma supressao por privacidade. As tres
carregam `trace_id`, e as tres ficam no `semantic_query_log`.

A IA nunca chega a este modulo com SQL nem com numero: `SemanticQuery.parse`
rejeita o que nao for consulta semantica antes de qualquer coisa acontecer
(ADR-0028).
"""
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from generator.config import Config

from . import certify, executor, members, plans, privacy, response, trace
from .catalog import Catalog, load as load_catalog
from .query import (QueryShapeError, Refusal, SemanticQuery, Vocabulary,
                    load_vocabulary, validate)


@dataclass
class Engine:
    """Estado caro reaproveitado entre consultas: catalogo, vocabulario,
    conexao DuckDB e o parquet de trust da F5."""
    cfg: Config
    catalog: Catalog
    vocab: Vocabulary
    con: object
    trust_df: pl.DataFrame | None
    mapeamentos_pendentes: dict[str, str]

    def close(self) -> None:
        try:
            self.con.close()
        except Exception:      # noqa: BLE001 - fechar conexao nao derruba resposta
            pass


def _membros_das_dimensoes(con) -> dict[str, set[str]]:
    """Membros que a L3 de fato tem, para as dimensoes que o vocabulario
    declara como `members_from_dimension`."""
    out: dict[str, set[str]] = {}
    consultas = {
        "departamento": "SELECT DISTINCT department FROM analytical.dim_organization",
        "nivel": "SELECT DISTINCT code FROM analytical.dim_job_level",
        "sistema_fonte": "SELECT DISTINCT code FROM analytical.dim_source_system",
    }
    for dim, sql in consultas.items():
        out[dim] = {r[0] for r in con.execute(sql).fetchall() if r[0]}
    return out


def engine(cfg: Config, mapeamentos_pendentes: dict[str, str] | None = None) -> Engine:
    con = executor.connect(cfg)                 # sem camada de verdade, sempre
    return Engine(cfg=cfg, catalog=load_catalog(cfg),
                  vocab=load_vocabulary(cfg, _membros_das_dimensoes(con)),
                  con=con, trust_df=certify.load_trust(cfg),
                  mapeamentos_pendentes=mapeamentos_pendentes or {})


def ask(eng: Engine, consulta: dict | SemanticQuery, registrar: bool = True):
    """Responde uma consulta semantica. Nunca levanta por dado: recusa."""
    q = consulta if isinstance(consulta, SemanticQuery) else SemanticQuery.parse(consulta)
    tid = trace.novo_trace_id()

    recusa, resolvido = validate(q, eng.catalog, eng.vocab, eng.mapeamentos_pendentes)
    kpi = eng.catalog.get(q.kpi)
    if recusa is not None:
        ans = response.recusa(tid, q, recusa, kpi)
        if registrar:
            trace.registrar(eng.cfg, q, ans)
        return ans

    res, recusa = executor.execute(eng.con, q, kpi, resolvido)
    if recusa is not None:
        ans = response.recusa(tid, q, recusa, kpi)
        if registrar:
            trace.registrar(eng.cfg, q, ans)
        return ans

    if not res.linhas:
        ans = response.recusa(tid, q, Refusal(
            "SEM_DADO_NO_PERIODO",
            f"nao ha linha de {q.kpi} no recorte pedido. A resposta correta nao "
            "e zero: zero e um valor, e ausencia de carga nao e.",
            "verificar a cobertura do periodo e o recorte, ou consultar um "
            "periodo com dado"), kpi)
        if registrar:
            trace.registrar(eng.cfg, q, ans)
        return ans

    declarada = (kpi.cobertura_declarada or {}).get("population_covered")
    t = certify.certify(eng.cfg, kpi, resolvido, res.populacao,
                        cobertura_populacao=declarada, trust_df=eng.trust_df)

    # Supressao por privacidade vem ANTES do nivel: um recorte pequeno demais
    # nao responde nem com trust perfeito (ADR-0007).
    #
    # Duas avaliacoes, e a segunda e a que faltava (G-01): o agregado protege a
    # consulta sem quebra, e a quebra por dimensao precisa ser protegida LINHA A
    # LINHA. Um total de 82 pessoas passa no minimo de 20 e ainda assim carrega
    # uma linha com 1 pessoa.
    if res.populacao < kpi.minimum_n:
        ans = response.supressao(tid, q, kpi, t, res.populacao)
        if registrar:
            trace.registrar(eng.cfg, q, ans, res.sql)
        return ans

    privacidade = privacy.aplicar(res.linhas, kpi.minimum_n,
                                  list(q.dimensions), plans.PLANS[kpi.kpi_id])
    if privacidade.tudo_suprimido:
        ans = response.supressao(tid, q, kpi, t, privacidade.populacao_publicada,
                                 detalhe=privacidade.to_dict())
        if registrar:
            trace.registrar(eng.cfg, q, ans, res.sql)
        return ans

    nivel, motivo_teto = response.nivel_efetivo(q.requested_level, kpi, t)
    if nivel is None:
        ans = response.recusa(tid, q, Refusal(
            "NIVEL_SEM_EVIDENCIA",
            f"{q.kpi} nao responde em nenhum nivel neste recorte: {motivo_teto}.",
            "resolver a pendencia que derrubou o trust, ou certificar o KPI"), kpi)
        if registrar:
            trace.registrar(eng.cfg, q, ans, res.sql)
        return ans

    valor, linhas = _valor(res, q, privacidade)
    caveats = _caveats(kpi, t, res, q, motivo_teto, privacidade)
    cobertura = _cobertura(kpi, t, res, declarada, privacidade)

    comparacao = None
    if nivel == "CONTEXT" and q.compare:
        comparacao = _comparar(eng, q, kpi, valor)
        if comparacao is None:
            nivel = "FACT"
            caveats.append("a base de comparacao pedida nao e respondivel neste "
                           "recorte; a resposta desce para FACT")

    ans = response.resposta(tid, q, kpi, t, nivel, valor,
                            plans.PLANS[kpi.kpi_id].measure.unidade,
                            linhas, cobertura, caveats, comparacao)
    if registrar:
        trace.registrar(eng.cfg, q, ans, res.sql)
    return ans


# --------------------------------------------------------------------------- #
def _valor(res: executor.ExecResult, q: SemanticQuery,
           priv: privacy.Resultado):
    """Valor escalar quando a consulta tem um unico recorte; senao, None e as
    linhas. Inventar um agregado de agregados seria regra de negocio nova.

    As linhas ja vem da camada de privacidade, com as suprimidas sem valor e
    sem populacao.
    """
    linhas = priv.linhas
    if len(linhas) == 1 and not linhas[0].get("suprimido"):
        v = linhas[0].get("valor")
        return (None if v is None else (round(float(v), 6) if isinstance(v, float)
                                        else v)), linhas
    return None, linhas


def _caveats(kpi, t: certify.TrustResposta, res: executor.ExecResult,
             q: SemanticQuery, motivo_teto: str | None,
             priv: privacy.Resultado) -> list[str]:
    c: list[str] = []
    if priv.houve_supressao:
        c.append(f"{priv.suprimidas} de {priv.suprimidas + priv.publicadas} linhas "
                 f"suprimidas por PRIVACIDADE (minimo de {priv.minimum_n} pessoas), "
                 "nao por qualidade do dado"
                 + (f"; {priv.complementares} por supressao complementar, para que "
                    "o residuo nao identifique um recorte unico"
                    if priv.complementares else ""))
    governados = _estados_governados(priv.linhas, q)
    for estado, n in sorted(governados.items()):
        c.append(f"{n} linha(s) em `{estado}`: {members.significado(estado)}")
    if t.limitado_por == "GOVERNANCA":
        c.append(f"KPI em {kpi.status}: a resposta nao pode ser certificada por "
                 "governanca, independente da qualidade do dado")
    if t.perda_por_pendencia:
        c.append(f"perda de confianca por pendencia de {t.perda_por_pendencia:.4f}: "
                 "ha decisao ou vinculo em aberto, nao dado errado")
    if t.perda_por_erro:
        c.append(f"perda de confianca por erro de {t.perda_por_erro:.4f}")
    if t.cobertura_de_verificacao is not None and t.cobertura_de_verificacao < 1.0:
        c.append(f"cobertura de verificacao de {t.cobertura_de_verificacao:.0%}: "
                 f"{t.checks_avaliados} de {t.checks_declarados} checks declarados "
                 "rodaram neste recorte; o restante nao e confianca nem perda")
    taxa = res.extras.get("taxa_de_nao_declaracao")
    if taxa:
        campo = res.extras.get("taxa_de_nao_declaracao_de")
        c.append(f"taxa de nao declaracao de {campo} de {taxa:.1%}, excluida do "
                 "numerador e do denominador e nunca penalizada no trust")
    if motivo_teto:
        c.append(motivo_teto)
    for e in kpi.doc.get("exclusions") or []:
        c.append(f"exclusao aplicada: {e.get('o_que')}")
    return c


def _estados_governados(linhas: list[dict], q: SemanticQuery) -> dict[str, int]:
    """Quantas linhas caem em cada estado governado, por dimensao pedida.

    Existe porque `UNMAPPED` numa linha de breakdown e so uma palavra em
    maiusculas ate alguem dizer o que ela significa. Sem isto, quem le reporta
    "397 pessoas em departamento nao identificado" como se fosse um
    departamento (G-02).
    """
    contagem: dict[str, int] = {}
    for l in linhas:
        for dim in q.dimensions:
            v = l.get(dim)
            if members.e_governado(v):
                contagem[v] = contagem.get(v, 0) + 1
    return contagem


def _cobertura(kpi, t: certify.TrustResposta, res: executor.ExecResult,
               declarada: float | None, priv: privacy.Resultado) -> dict:
    # A populacao publicada e a das linhas que sairam. A das suprimidas nao
    # entra: somar as duas devolveria, por subtracao, o que a supressao tirou.
    d = dict(population=priv.populacao_publicada,
             verificacao=t.cobertura_de_verificacao,
             periodos=len(res.periodos),
             linhas_publicadas=priv.publicadas,
             linhas_suprimidas=priv.suprimidas)
    if priv.houve_supressao:
        d["supressao"] = priv.to_dict()
    if declarada is not None:
        d["population_covered"] = declarada
        d["nota"] = (kpi.cobertura_declarada or {}).get("nota")
    taxa = res.extras.get("taxa_de_nao_declaracao")
    if taxa is not None:
        d["nao_declaracao"] = {res.extras.get("taxa_de_nao_declaracao_de"): taxa}
    return d


def _comparar(eng: Engine, q: SemanticQuery, kpi, valor):
    """Base de comparacao, que precisa ser ela propria respondivel (secao 15).

    Se a base cai fora da cobertura, ou e recusada por qualquer das sete
    validacoes, a resposta desce para FACT em vez de comparar com um numero que
    nao existe.
    """
    if valor is None:
        return None
    anterior = _periodo_anterior(q)
    if anterior is None:
        return None
    base = SemanticQuery(kpi=q.kpi, period=anterior, dimensions=q.dimensions,
                         filters=q.filters, requested_level="FACT")
    ans = ask(eng, base, registrar=False)
    if not ans.respondeu or ans.value is None:
        return None
    delta = valor - ans.value
    return dict(tipo=q.compare,
                base=dict(period={"grain": anterior.grain, "from": anterior.inicio,
                                  "to": anterior.fim},
                          value=ans.value, trust=ans.trust.get("status")),
                delta=round(delta, 6),
                delta_relativo=(None if not ans.value
                                else round(delta / ans.value, 6)),
                nota="variacao observada; e associacao no tempo, nao causa")


def _periodo_anterior(q: SemanticQuery):
    from .query import Period
    g, ini = q.period.grain, q.period.inicio
    if q.compare == "mesmo_periodo_ano_anterior":
        if g == "mes":
            v = f"{int(ini[:4]) - 1}-{ini[5:7]}"
        elif g == "trimestre":
            v = f"{int(ini[:4]) - 1}-{ini[5:]}"
        elif g == "ano":
            v = str(int(ini) - 1)
        else:
            return None
        return Period(g, v, v)
    if q.compare == "periodo_anterior":
        if g == "mes":
            ano, mes = int(ini[:4]), int(ini[5:7])
            ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
            v = f"{ano}-{mes:02d}"
        elif g == "trimestre":
            ano, tri = int(ini[:4]), int(ini[-1])
            ano, tri = (ano - 1, 4) if tri == 1 else (ano, tri - 1)
            v = f"{ano}-Q{tri}"
        elif g == "ano":
            v = str(int(ini) - 1)
        else:
            return None
        return Period(g, v, v)
    return None
