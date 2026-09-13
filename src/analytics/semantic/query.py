"""Consulta semantica e as sete validacoes deterministicas (ADR-0028, F7 secao 12).

A saida da IA e um `SemanticQuery`. Ele **nao tem onde escrever** nome de
tabela, coluna, junção ou fragmento de SQL: o schema nao tem esse campo, e
chave desconhecida e erro, nao campo extra ignorado. A proibicao de calcular
sobre RAW deixa de ser uma instrucao em prompt e passa a ser a forma do objeto.

    kpi: headcount
    period: {grain: mes, from: 2025-01, to: 2025-12}
    dimensions: [pais, departamento]
    filters: [{dimension: pais, in: [Brasil, Argentina]}]

Recusa e resposta, nao excecao. As sete validacoes produzem uma `Refusal` que
diz o que seria necessario para responder, e a camada NUNCA aproxima uma
consulta para faze-la passar: um termo mapeado errado e invisivel, um termo nao
mapeado e visivel (ADR-0020, achado 3 da F4).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from generator.config import Config

from .catalog import Catalog, Kpi, ORDEM_NIVEL, NIVEIS

CAMPOS = {"kpi", "kpi_version", "period", "dimensions", "filters", "compare",
          "requested_level", "pergunta"}
CAMPOS_PERIODO = {"grain", "from", "to"}
CAMPOS_FILTRO = {"dimension", "in"}

GRAINS = ("mes", "trimestre", "ano", "ciclo")

# Ordem de finura dos grains de periodo. Um pedido mais grosso que o grain do
# contrato so passa se o contrato declarar `period_rollup`: sem isso, somar
# headcount de doze meses produziria doze vezes a empresa.
FINURA = {"mes": 0, "trimestre": 1, "ciclo": 1, "ano": 2}

PADRAO = {
    "mes": re.compile(r"^\d{4}-(0[1-9]|1[0-2])$"),
    "trimestre": re.compile(r"^\d{4}-Q[1-4]$"),
    "ano": re.compile(r"^\d{4}$"),
    "ciclo": re.compile(r"^\d{4}(-H[12])?$"),
}


class QueryShapeError(ValueError):
    """A consulta nao tem a forma de uma consulta semantica.

    Separado de `Refusal` de proposito: uma recusa e uma resposta ao usuario;
    isto e um contrato quebrado por quem chamou, e o unico jeito de chegar aqui
    e tentando passar SQL, nome de tabela ou campo inventado.
    """


CLASSES_DE_RECUSA = (
    "KPI_INEXISTENTE", "KPI_BLOQUEADO", "KPI_EM_RASCUNHO",
    "DIMENSAO_NAO_PERMITIDA", "TERMO_DESCONHECIDO",
    "PERIODO_FORA_DE_COBERTURA", "GRAIN_INCOMPATIVEL",
    "POPULACAO_ABAIXO_DO_MINIMO", "MAPEAMENTO_PENDENTE",
    "NIVEL_SEM_EVIDENCIA", "COMPARACAO_ENTRE_VERSOES", "SEM_DADO_NO_PERIODO",
    "VERSAO_INEXISTENTE", "COMPARACAO_NAO_RESPONDIVEL", "PREDICADO_INDISPONIVEL",
    "SEM_PLANO_DE_EXECUCAO",
)


@dataclass(frozen=True)
class Refusal:
    """Uma recusa explicada. `o_que_resolveria` nao e opcional: recusa que nao
    diz o caminho e so uma porta fechada."""
    classe: str
    mensagem: str
    o_que_resolveria: str
    detalhe: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.classe not in CLASSES_DE_RECUSA:
            raise ValueError(f"classe de recusa desconhecida: {self.classe}")

    def to_dict(self) -> dict:
        return dict(classe=self.classe, mensagem=self.mensagem,
                    o_que_resolveria=self.o_que_resolveria, detalhe=self.detalhe)


@dataclass(frozen=True)
class Period:
    grain: str
    inicio: str
    fim: str


@dataclass(frozen=True)
class Filter:
    dimension: str
    valores: tuple[str, ...]


@dataclass(frozen=True)
class SemanticQuery:
    kpi: str
    period: Period
    dimensions: tuple[str, ...] = ()
    filters: tuple[Filter, ...] = ()
    compare: str | None = None
    requested_level: str = "FACT"
    kpi_version: str | None = None
    pergunta: str | None = None

    # ----------------------------------------------------------------- forma
    @classmethod
    def parse(cls, bruto: dict) -> "SemanticQuery":
        """Constroi a consulta a partir do dicionario que a IA emitiu.

        Chave desconhecida NAO e ignorada. Ignorar seria a porta por onde
        `{"sql": "..."}` ou `{"table": "fact_headcount_snapshot"}` entraria sem
        ninguem notar, e o objeto deixaria de ser a fronteira que o ADR-0028
        descreve.
        """
        if not isinstance(bruto, dict):
            raise QueryShapeError("consulta semantica precisa ser um objeto")
        extras = set(bruto) - CAMPOS
        if extras:
            raise QueryShapeError(
                f"campos desconhecidos na consulta semantica: {sorted(extras)}. "
                "A consulta nao aceita SQL, nome de tabela, coluna ou junção "
                "(ADR-0028).")
        if "kpi" not in bruto or not isinstance(bruto["kpi"], str):
            raise QueryShapeError("consulta semantica exige `kpi`")

        p = bruto.get("period")
        if not isinstance(p, dict):
            raise QueryShapeError("consulta semantica exige `period`")
        extras_p = set(p) - CAMPOS_PERIODO
        if extras_p:
            raise QueryShapeError(f"campos desconhecidos em `period`: {sorted(extras_p)}")
        grain = p.get("grain")
        if grain not in GRAINS:
            raise QueryShapeError(f"grain de periodo desconhecido: {grain!r}")
        inicio, fim = str(p.get("from") or ""), str(p.get("to") or p.get("from") or "")
        if not inicio:
            raise QueryShapeError("`period.from` e obrigatorio")

        dims = tuple(bruto.get("dimensions") or ())
        if any(not isinstance(d, str) for d in dims):
            raise QueryShapeError("`dimensions` e uma lista de nomes de dimensao de negocio")

        filtros = []
        for f in bruto.get("filters") or ():
            if not isinstance(f, dict):
                raise QueryShapeError("cada filtro e um objeto {dimension, in}")
            extras_f = set(f) - CAMPOS_FILTRO
            if extras_f:
                raise QueryShapeError(
                    f"campos desconhecidos no filtro: {sorted(extras_f)}. "
                    "Filtro nao aceita expressao, operador nem coluna fisica.")
            vals = f.get("in")
            if isinstance(vals, str):
                vals = [vals]
            if not vals:
                raise QueryShapeError("filtro sem valores em `in`")
            filtros.append(Filter(str(f.get("dimension")), tuple(str(v) for v in vals)))

        nivel = bruto.get("requested_level") or "FACT"
        if nivel not in NIVEIS:
            raise QueryShapeError(f"nivel de resposta desconhecido: {nivel!r}")

        return cls(kpi=bruto["kpi"], period=Period(grain, inicio, fim),
                   dimensions=dims, filters=tuple(filtros),
                   compare=bruto.get("compare"), requested_level=nivel,
                   kpi_version=bruto.get("kpi_version"),
                   pergunta=bruto.get("pergunta"))

    def to_dict(self) -> dict:
        return dict(
            kpi=self.kpi, kpi_version=self.kpi_version,
            period={"grain": self.period.grain, "from": self.period.inicio,
                    "to": self.period.fim},
            dimensions=list(self.dimensions),
            filters=[{"dimension": f.dimension, "in": list(f.valores)} for f in self.filters],
            compare=self.compare, requested_level=self.requested_level,
            pergunta=self.pergunta)


# --------------------------------------------------------------------------- #
# Vocabulario
# --------------------------------------------------------------------------- #
def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


@dataclass
class Vocabulary:
    doc: dict
    membros_da_dimensao: dict[str, set[str]] = field(default_factory=dict)

    @property
    def dimensoes(self) -> list[str]:
        return sorted(self.doc.get("dimensions") or {})

    @property
    def comparacoes(self) -> list[str]:
        return sorted(self.doc.get("comparisons") or {})

    def fisico(self, dim: str) -> dict:
        return (self.doc["dimensions"][dim]).get("physical") or {}

    def resolve(self, dim: str, termo: str) -> tuple[str | None, dict | None, str | None]:
        """Termo de negocio -> (membro, predicado, erro).

        Nunca aproxima. Termo fora do vocabulario devolve erro com a lista dos
        termos validos daquela dimensao, que e informacao verificavel, e nao um
        palpite ordenado por similaridade.
        """
        spec = (self.doc.get("dimensions") or {}).get(dim)
        if spec is None:
            return None, None, f"dimensao desconhecida no vocabulario: {dim}"

        alvo = _slug(termo)

        for grupo, g in (spec.get("groups") or {}).items():
            if alvo == _slug(grupo) or any(alvo == _slug(t) for t in g.get("terms") or []):
                return None, dict(g["resolves_to"], grupo=grupo), None

        for membro, m in (spec.get("members") or {}).items():
            if alvo == _slug(membro) or any(alvo == _slug(t) for t in m.get("terms") or []):
                return membro, None, None

        if spec.get("members_from_dimension"):
            bloqueados = {_slug(t) for t in spec.get("reserved_terms_blocked") or []}
            if alvo in bloqueados:
                return None, None, (
                    f"{termo!r} e membro reservado de {dim} e nao e consultavel: "
                    "representa pendencia de governanca, nao um valor de negocio "
                    "(ADR-0025)")
            for membro in self.membros_da_dimensao.get(dim, ()):
                if alvo == _slug(membro):
                    return membro, None, None

        return None, None, f"termo fora do vocabulario de {dim}: {termo!r}"

    def termos(self, dim: str, limite: int = 12) -> list[str]:
        spec = (self.doc.get("dimensions") or {}).get(dim) or {}
        nomes = list(spec.get("members") or {}) or sorted(
            self.membros_da_dimensao.get(dim, ()))
        nomes += list(spec.get("groups") or {})
        return sorted(nomes)[:limite]


def load_vocabulary(cfg: Config, membros: dict[str, set[str]] | None = None) -> Vocabulary:
    p = Path(cfg.root) / "config" / "semantic" / "vocabulary.yaml"
    with open(p, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return Vocabulary(doc, membros or {})


# --------------------------------------------------------------------------- #
# Periodo
# --------------------------------------------------------------------------- #
def _chave(grain: str, valor: str) -> str:
    """Valor de periodo normalizado para comparacao lexicografica."""
    if grain == "trimestre":
        return valor
    if grain == "ciclo":
        return valor
    return valor


def _dentro(valor: str, ini: str, fim: str) -> bool:
    """Comparacao lexicografica funciona porque os formatos sao ordenaveis:
    YYYY, YYYY-MM, YYYY-Qn e YYYY-Hn crescem com o tempo como texto."""
    return ini <= valor <= fim or (valor[:4] >= ini[:4] and valor[:4] <= fim[:4]
                                   and len(valor) == 4)


# --------------------------------------------------------------------------- #
# As sete validacoes
# --------------------------------------------------------------------------- #
def validate(q: SemanticQuery, cat: Catalog, vocab: Vocabulary,
             mapeamentos_pendentes: dict[str, str] | None = None
             ) -> tuple[Refusal | None, dict]:
    """Devolve (recusa, resolvido). Recusa None significa consulta executavel.

    Sete verificacoes, todas deterministicas, todas antes de qualquer execucao.
    A ordem importa: o KPI primeiro, porque sem contrato nao ha o que validar.
    """
    resolvido: dict = {"filtros": [], "predicados": []}

    # 1. o KPI existe e o status permite responder ---------------------------
    kpi = cat.get(q.kpi)
    if kpi is None:
        return Refusal(
            "KPI_INEXISTENTE",
            f"nao existe KPI com id {q.kpi!r} no catalogo.",
            f"consultar um dos KPIs do catalogo: {', '.join(cat.ids)}",
        ), resolvido

    if kpi.status == "BLOCKED":
        b = kpi.bloqueadores[0] if kpi.bloqueadores else {}
        return Refusal(
            "KPI_BLOQUEADO",
            f"{q.kpi} esta BLOCKED e nao produz valor de nenhuma natureza. "
            f"Bloqueador: {b.get('motivo', 'nao declarado')}",
            b.get("resolvido_por", "resolver o bloqueador declarado no contrato"),
            {"kpi": q.kpi, "bloqueadores": kpi.bloqueadores},
        ), resolvido

    if kpi.status == "DRAFT":
        return Refusal(
            "KPI_EM_RASCUNHO",
            f"{q.kpi} esta em DRAFT: a definicao ainda nao foi declarada.",
            "declarar o KPI (dono, definicao de negocio, formula, grain, populacao)",
        ), resolvido

    # versao pedida explicitamente
    if q.kpi_version and q.kpi_version != kpi.version:
        return Refusal(
            "VERSAO_INEXISTENTE",
            f"a versao {q.kpi_version} de {q.kpi} nao esta disponivel; "
            f"a versao corrente e {kpi.version}.",
            "consultar uma versao registrada do KPI",
            {"corrente": kpi.version},
        ), resolvido

    # 2. toda dimensao pedida esta em allowed_dimensions ---------------------
    permitidas = set(kpi.allowed_dimensions)
    for d in q.dimensions:
        if d not in permitidas:
            return Refusal(
                "DIMENSAO_NAO_PERMITIDA",
                f"{q.kpi} nao responde por {d!r}.",
                f"recortar por uma das dimensoes permitidas: "
                f"{', '.join(kpi.allowed_dimensions)}",
                {"pedida": d, "permitidas": kpi.allowed_dimensions},
            ), resolvido

    # 3. todo termo de filtro existe no vocabulario --------------------------
    for f in q.filters:
        if f.dimension not in permitidas:
            return Refusal(
                "DIMENSAO_NAO_PERMITIDA",
                f"{q.kpi} nao aceita filtro por {f.dimension!r}.",
                f"filtrar por uma das dimensoes permitidas: "
                f"{', '.join(kpi.allowed_dimensions)}",
                {"pedida": f.dimension, "permitidas": kpi.allowed_dimensions},
            ), resolvido
        membros, predicados = [], []
        for termo in f.valores:
            membro, pred, erro = vocab.resolve(f.dimension, termo)
            if erro:
                return Refusal(
                    "TERMO_DESCONHECIDO",
                    erro,
                    f"usar um termo declarado do vocabulario de {f.dimension}: "
                    f"{', '.join(vocab.termos(f.dimension))}. Termo fora do "
                    "vocabulario nao vira correspondencia aproximada (ADR-0020).",
                    {"dimensao": f.dimension, "termo": termo},
                ), resolvido
            (predicados if pred else membros).append(pred or membro)
        if membros:
            resolvido["filtros"].append({"dimension": f.dimension, "members": membros})
        for p in predicados:
            resolvido["predicados"].append(dict(p, dimension=f.dimension))

    # 4. o periodo pedido esta dentro de period_coverage ---------------------
    cobertura = kpi.period_coverage
    if cobertura is None:
        return Refusal(
            "PERIODO_FORA_DE_COBERTURA",
            f"{q.kpi} nao tem cobertura de periodo declarada.",
            "declarar period_coverage no contrato, derivado da L3",
        ), resolvido
    ini, fim = cobertura
    for valor in {q.period.inicio, q.period.fim}:
        if not PADRAO[q.period.grain].match(valor):
            return Refusal(
                "GRAIN_INCOMPATIVEL",
                f"{valor!r} nao tem o formato de {q.period.grain}.",
                f"usar o formato {PADRAO[q.period.grain].pattern}",
            ), resolvido
    fora = [v for v in (q.period.inicio, q.period.fim)
            if not _dentro(v, ini, fim)]
    if fora:
        return Refusal(
            "PERIODO_FORA_DE_COBERTURA",
            f"{q.kpi} tem dado de {ini} a {fim}. O periodo pedido ({fora[0]}) "
            "esta fora dessa janela, e a resposta correta nao e zero.",
            f"consultar dentro de {ini}..{fim}",
            {"cobertura": [ini, fim], "pedido": [q.period.inicio, q.period.fim]},
        ), resolvido

    # 5. o grain do periodo e compativel com period_grain --------------------
    pedido, contrato = FINURA[q.period.grain], FINURA[kpi.period_grain]
    if q.period.grain != kpi.period_grain:
        if pedido < contrato:
            return Refusal(
                "GRAIN_INCOMPATIVEL",
                f"{q.kpi} e apurado por {kpi.period_grain}; nao ha como "
                f"desagrega-lo para {q.period.grain}.",
                f"consultar por {kpi.period_grain}",
            ), resolvido
        if not kpi.period_rollup:
            return Refusal(
                "GRAIN_INCOMPATIVEL",
                f"{q.kpi} e apurado por {kpi.period_grain} e o contrato nao "
                f"declara como agregar para {q.period.grain}.",
                f"consultar por {kpi.period_grain}, ou declarar period_rollup "
                "no contrato",
            ), resolvido
    resolvido["rollup"] = (None if q.period.grain == kpi.period_grain
                           else kpi.period_rollup)

    # 6. dependencias de mapeamento sem pendencia bloqueante -----------------
    pendentes = mapeamentos_pendentes or {}
    bloqueantes = {m: pendentes[m] for m in kpi.doc.get("depends_on_mappings") or []
                   if m in pendentes}
    if bloqueantes:
        nome, motivo = sorted(bloqueantes.items())[0]
        return Refusal(
            "MAPEAMENTO_PENDENTE",
            f"{q.kpi} depende de {nome}, que tem pendencia bloqueante: {motivo}",
            "resolver a excecao na fila de governanca da F4, com responsavel e "
            "justificativa",
            {"mapeamentos": bloqueantes},
        ), resolvido

    # 7. o nivel pedido cabe no que a evidencia sustenta ---------------------
    teto = kpi.teto_nivel
    if teto is None:
        return Refusal(
            "KPI_BLOQUEADO",
            f"{q.kpi} nao responde em nenhum nivel.",
            "resolver o bloqueador declarado",
        ), resolvido
    if ORDEM_NIVEL[q.requested_level] > ORDEM_NIVEL[teto]:
        falta = ("um estudo registrado em causal_studies, com desenho, tratamento, "
                 "controle, efeito, intervalo e limitacoes"
                 if q.requested_level == "CAUSALITY" else
                 "uma regra registrada em interpretation_rules, com dono e data"
                 if q.requested_level == "INTERPRETATION" else
                 "certificacao do KPI")
        return Refusal(
            "NIVEL_SEM_EVIDENCIA",
            f"{q.requested_level} nao esta sustentado para {q.kpi}: o teto e {teto}.",
            f"para responder em {q.requested_level} seria necessario {falta}.",
            {"pedido": q.requested_level, "teto": teto, "status": kpi.status},
        ), resolvido

    # comparacao declarada precisa existir no vocabulario
    if q.compare and q.compare not in vocab.comparacoes:
        return Refusal(
            "COMPARACAO_NAO_RESPONDIVEL",
            f"base de comparacao desconhecida: {q.compare!r}",
            f"usar uma base declarada: {', '.join(vocab.comparacoes)}",
        ), resolvido

    resolvido["kpi"] = kpi
    return None, resolvido


def kpi_de(resolvido: dict) -> Kpi:
    return resolvido["kpi"]
