"""Trust score por KPI e por recorte (ADR-0011, ADR-0022).

A pergunta que este modulo responde nao e "o dado esta bom". E:

    **quanto desta resposta eu posso afirmar, e o que exatamente falta para
    poder afirmar o resto.**

Por isso o score nao e um numero opaco. Ele e o produto de quatro componentes
declarados, e cada componente responde por uma natureza distinta de perda:

    validade    checks de classe INVALIDO e DIVERGENCIA      -> o dado esta errado
    cobertura   checks de classe NAO_MAPEADO e DECISAO_PENDENTE -> falta decisao
    identidade  checks de classe IDENTIDADE_NAO_RESOLVIDA    -> falta vinculo
    atualidade  checks de classe DESATUALIZADO               -> falta chegar

    quality_score = validade x cobertura          (formula do ADR-0011)
    trust_score   = quality_score x identidade x atualidade

`AUSENCIA_LEGITIMA` **nao entra em nenhum componente**, e essa e uma decisao de
principio e nao de calculo: penalizar a confianca porque alguem optou por nao
declarar raca, cor ou deficiencia transformaria o trust score em pressao por
preenchimento. A taxa e reportada ao lado do numero, como contexto de leitura.
`WARNING` e `INFO` tambem nao entram, por ADR-0010.

A regra que a Sam fixou na abertura da F5 vive aqui:

    dado invalido != dado nao mapeado != decisao pendente
                  != identidade nao resolvida != dado quarentenado

Consequencia pratica: um recorte cuja perda vem inteiramente de pendencia nao e
rebaixado a BLOCKED junto com um recorte que tem dado errado. Nao estar
resolvido nao e o mesmo que estar errado, e a diferenca muda o que a pessoa faz
a seguir: com erro, corrige a fonte; com pendencia, decide.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import yaml

from generator.config import Config
from mapping.depara import DATASET_SPEC
from quality import runner

from . import contracts

# Faixas de trust status. A calibragem contra a distribuicao alvo de
# defects.yaml (`target_trust_distribution`) acontece na F7.
#
# ADR-0023 (decisao DQ-04): a F7 calibra por RECORTE FINO, e **estas bandas nao
# se movem**. Mexer no limiar ate a distribuicao bater no alvo produziria a
# distribuicao desejada numa tarde e destruiria o significado do numero: a banda
# passaria a ser escolhida pelo resultado que produz. Se alguem estiver prestes
# a editar a linha abaixo para fechar uma distribuicao, e este ADR que a
# proibe.
BANDS = {"CERTIFIED": 0.95, "LIMITED": 0.70}
PISO_PENDENCIA = 0.40   # abaixo disso nem pendencia pura sustenta resposta

COMPONENTES = {
    "validade":   ("INVALIDO", "DIVERGENCIA"),
    "cobertura":  ("NAO_MAPEADO", "DECISAO_PENDENTE"),
    "identidade": ("IDENTIDADE_NAO_RESOLVIDA",),
    "atualidade": ("DESATUALIZADO",),
}
IGNORADAS = ("AUSENCIA_LEGITIMA",)          # reportada, nunca penalizada
SEVERIDADES_QUE_PESAM = ("BLOCKER", "CRITICAL")


# --------------------------------------------------------------------------- #
# Recortes
# --------------------------------------------------------------------------- #
# Datasets em que a data de referencia e de fato um PERIODO, e nao um atributo
# da pessoa. `hire_date` num cadastro diz quando aquela pessoa entrou, nao a que
# periodo a linha pertence: recortar o cadastro por ano de admissao produziria
# "ano=1994" com uma linha, que nao e um recorte temporal da empresa.
DATASETS_COM_PERIODO = {
    "HRIS_CORE.headcount_snapshot", "HRIS_LEGACY.headcount_snapshot",
    "PAYROLL_BR.payroll_headcount_snapshot", "PAYROLL_BR.compensation",
    "HRIS_CORE.performance", "HRIS_CORE.movement", "HRIS_LEGACY.movement",
    "ATS_CLOUD.application", "ATS_CLOUD.requisition",
}


def _date_col(key: tuple[str, str]) -> str | None:
    nome = f"{key[0]}.{key[1]}"
    if nome not in DATASETS_COM_PERIODO:
        return None
    spec = DATASET_SPEC.get(nome)
    return spec.get("date") if spec else None


def cuts(cfg: Config, frames: dict) -> dict[str, dict]:
    """Recortes avaliados. Cada um mapeia dataset -> filtro.

    Tres familias, escolhidas porque sao as que separam populacoes de confianca
    diferente neste universo:

    - `pais`, porque a cobertura de sistema varia por pais;
    - `ano`, porque a migracao de 2019 e a aquisicao de 2022 partem a serie;
    - `origem`, o sistema de origem, porque e o recorte que isola exatamente as
      populacoes problematicas (a aquisicao sem identificador corporativo).
    """
    out: dict[str, dict] = {"GLOBAL": {k: {} for k in frames}}

    paises = set()
    for key, df in frames.items():
        if "std_country" in df.columns:
            paises |= set(df["std_country"].drop_nulls().unique().to_list())
    for p in sorted(paises - {"UNMAPPED"}):
        out[f"pais={p}"] = {k: {"column": "std_country", "equals": p}
                            for k, df in frames.items() if "std_country" in df.columns}

    anos = set()
    for key, df in frames.items():
        c = _date_col(key)
        if c and c in df.columns:
            anos |= {d[:4] for d in df[c].drop_nulls().to_list() if d}
    for a in sorted(anos):
        alvo = {}
        for key, df in frames.items():
            c = _date_col(key)
            if c and c in df.columns:
                alvo[key] = {"column": c, "min": f"{a}-01-01", "max": f"{a}-12-31"}
        out[f"ano={a}"] = alvo

    for sistema in sorted({k[0] for k in frames}):
        out[f"origem={sistema}"] = {k: {} for k in frames if k[0] == sistema}
    return out


# --------------------------------------------------------------------------- #
# Calculo
# --------------------------------------------------------------------------- #
def _componente(specs: dict, resultados: dict, classes: tuple[str, ...]) -> tuple[float | None, list[str]]:
    """1 menos a media PONDERADA das taxas de falha dos checks daquelas classes.

    Ponderada por `records_checked`, como o ADR-0011 especifica, e a diferenca
    nao e cosmetica. Na primeira versao a media era simples, e um check que
    avaliava 320 linhas da aquisicao pesava igual a um que avaliava 100 mil do
    HRIS. Bastava esse check reprovar em 100% para o componente ir a zero, o
    produto ir a zero e o recorte `pais=BR` inteiro, com 208 mil linhas e
    validade de 0,9995, aparecer como BLOCKED. Ponderar coloca o peso onde esta
    a populacao, e a penalidade da aquisicao passa a aparecer com forca total no
    recorte que isola a aquisicao, que e onde ela e verdadeira.

    Devolve (None, []) quando nenhum check da classe rodou no recorte. None nao
    e 1.0: ausencia de evidencia nao e evidencia de qualidade, e quem chama
    precisa saber a diferenca.
    """
    soma_falhas = 0.0
    soma_peso = 0.0
    usados = []
    for cid, r in resultados.items():
        spec = specs[cid]
        if spec["severity"] not in SEVERIDADES_QUE_PESAM:
            continue
        if spec["finding_class"] not in classes:
            continue
        peso = float(r["records_checked"])
        if peso <= 0:
            continue
        soma_falhas += min(1.0, r["failure_rate"]) * peso
        soma_peso += peso
        usados.append(cid)
    if not soma_peso:
        return None, []
    return max(0.0, 1.0 - soma_falhas / soma_peso), sorted(usados)


def _atribuicao(specs: dict, resultados: dict) -> dict:
    """Decompoe a perda total de confianca por classe de achado.

    O score e UMA media ponderada sobre todos os checks que pesam, e as
    contribuicoes por classe somam exatamente a perda total. Isso substitui a
    primeira versao, que multiplicava um componente por classe.

    Por que o produto nao servia: cada componente era uma media dentro da
    propria classe, e classes diferentes cobrem fracoes diferentes do recorte.
    Um unico check de identidade sobre 320 linhas da aquisicao, reprovando em
    100%, zerava o componente de identidade; o produto ia a zero; e o recorte
    `pais=BR` inteiro, com 208 mil linhas e validade de 0,9997, aparecia como
    BLOCKED. Os componentes nao eram comensuraveis, entao multiplica-los somava
    peras com laranjas e chamava o resultado de confianca.

    Com media ponderada unica, cada check pesa pela populacao que ele de fato
    avaliou, e a atribuicao por classe diz de onde veio a perda sem inventar
    aritmetica entre grandezas diferentes.
    """
    peso_total = 0.0
    perda_por_classe: dict[str, float] = {}
    cobertura_por_classe: dict[str, float] = {}
    usados: list[str] = []

    for cid, r in resultados.items():
        spec = specs[cid]
        if spec["severity"] not in SEVERIDADES_QUE_PESAM:
            continue
        classe = spec["finding_class"]
        if classe in IGNORADAS:
            continue
        peso = float(r["records_checked"])
        if peso <= 0:
            continue
        peso_total += peso
        perda_por_classe[classe] = perda_por_classe.get(classe, 0.0) + min(1.0, r["failure_rate"]) * peso
        cobertura_por_classe[classe] = cobertura_por_classe.get(classe, 0.0) + peso
        usados.append(cid)

    if not peso_total:
        return {"perda_total": None, "por_classe": {}, "cobertura": {}, "checks": []}

    return {
        "perda_total": sum(perda_por_classe.values()) / peso_total,
        "por_classe": {c: v / peso_total for c, v in perda_por_classe.items()},
        "cobertura": {c: v / peso_total for c, v in cobertura_por_classe.items()},
        "checks": sorted(usados),
    }


def _componente_por_classe(atrib: dict, classes: tuple[str, ...]) -> float | None:
    """Score do componente: 1 menos a perda das classes dele, dentro da fatia
    que essas classes avaliaram. Diagnostico, nao fator do produto."""
    peso = sum(atrib["cobertura"].get(c, 0.0) for c in classes)
    if peso <= 0:
        return None
    perda = sum(atrib["por_classe"].get(c, 0.0) for c in classes)
    return max(0.0, 1.0 - perda / peso)


def _status(trust: float | None, perda_erro: float, perda_pendencia: float) -> tuple[str, str]:
    """Status e motivo principal.

    A regra do ADR-0022 esta no bloco final: perda que vem so de pendencia nao
    derruba para BLOCKED enquanto houver base para responder com ressalva. Nao
    estar resolvido nao e o mesmo que estar errado, e a diferenca muda o que a
    pessoa faz a seguir: com erro, corrige a fonte; com pendencia, decide.
    """
    if trust is None:
        return "INDETERMINADO", "SEM_EVIDENCIA"
    if trust >= BANDS["CERTIFIED"]:
        return "CERTIFIED", "OK" if (perda_erro + perda_pendencia) < 1e-9 else (
            "ERRO" if perda_erro >= perda_pendencia else "PENDENCIA")
    motivo = "ERRO" if perda_erro > perda_pendencia else "PENDENCIA"
    if trust >= BANDS["LIMITED"]:
        return "LIMITED", motivo
    if perda_erro < 1e-6 and trust >= PISO_PENDENCIA:
        return "LIMITED", "PENDENCIA"     # pendencia pura: responde com ressalva
    return "BLOCKED", motivo


def _populacao(frames: dict, cut: dict) -> int:
    total = 0
    for key, filtro in cut.items():
        df = frames.get(key)
        if df is None:
            continue
        total += runner._apply_filter(df, filtro).height
    return total


def compute(cfg: Config, frames: dict, xref: pl.DataFrame | None = None) -> pl.DataFrame:
    """Trust score para cada par (KPI, recorte)."""
    cat = runner.load_checks(cfg)
    specs = {c["check_id"]: c for c in cat["checks"]}
    kpis = contracts.load(cfg)
    recortes = cuts(cfg, frames)

    linhas: list[dict] = []
    for nome_recorte, cut in recortes.items():
        resultados = runner.run_for_cut(cfg, frames, cut, xref=xref, catalog_cache=cat)
        pop = _populacao(frames, cut)

        for kpi, contrato in kpis.items():
            deps = set(contrato["depends_on_checks"])
            no_recorte = {cid: r for cid, r in resultados.items() if cid in deps}
            atrib = _atribuicao(specs, no_recorte)

            perda = atrib["perda_total"]
            trust = None if perda is None else max(0.0, 1.0 - perda)

            classes_erro = COMPONENTES["validade"]
            perda_erro = sum(atrib["por_classe"].get(c, 0.0) for c in classes_erro)
            perda_pend = (perda or 0.0) - perda_erro

            comp = {nome: _componente_por_classe(atrib, classes)
                    for nome, classes in COMPONENTES.items()}

            # quality_score na forma do ADR-0011: validade x cobertura. Mantido
            # para continuidade com o ADR; o trust_score e a medida que a F5
            # usa, pela razao no docstring de `_atribuicao`.
            quality = None
            if comp["validade"] is not None or comp["cobertura"] is not None:
                quality = (comp["validade"] or 1.0) * (comp["cobertura"] or 1.0)

            status, motivo = _status(trust, perda_erro, perda_pend)

            # Supressao por n minimo e PRIVACIDADE (ADR-0007), nao qualidade.
            # Fica em campo proprio para que a recusa seja explicavel pelo
            # motivo certo: "o grupo e pequeno demais para preservar anonimato"
            # e diferente de "nao confio no dado".
            suprimido = pop < int(contrato.get("minimum_n") or 0)

            linhas.append(dict(
                kpi=kpi, recorte=nome_recorte, populacao=pop,
                validade=None if comp["validade"] is None else round(comp["validade"], 6),
                cobertura=None if comp["cobertura"] is None else round(comp["cobertura"], 6),
                identidade=None if comp["identidade"] is None else round(comp["identidade"], 6),
                atualidade=None if comp["atualidade"] is None else round(comp["atualidade"], 6),
                quality_score=None if quality is None else round(quality, 6),
                trust_score=None if trust is None else round(trust, 6),
                trust_status=status, motivo=motivo,
                perda_por_erro=None if perda is None else round(perda_erro, 6),
                perda_por_pendencia=None if perda is None else round(max(0.0, perda_pend), 6),
                perda_por_classe={c: round(v, 6) for c, v in atrib["por_classe"].items()},
                checks_avaliados=len(atrib["checks"]), checks_declarados=len(deps),
                suprimido_por_n_minimo=suprimido, minimum_n=int(contrato.get("minimum_n") or 0),
            ))
    return pl.DataFrame(linhas, infer_schema_length=None)


def summary(df: pl.DataFrame) -> dict:
    """Resumo. Separa o que e respondivel do que nao e, e por que nao e.

    Misturar as tres coisas numa distribuicao so daria um numero bonito e
    errado: um recorte suprimido por n minimo nao e um recorte confiavel, e um
    recorte sem nenhum check aplicavel muito menos.
    """
    if df.is_empty():
        return {}
    respondivel = df.filter(~pl.col("suprimido_por_n_minimo")
                            & (pl.col("trust_status") != "INDETERMINADO"))
    dist = {r["trust_status"]: r["len"] for r in respondivel.group_by("trust_status").len().to_dicts()}
    n = respondivel.height or 1
    return {
        "pares_kpi_recorte": df.height,
        "respondiveis": respondivel.height,
        "suprimidos_por_n_minimo": int(df["suprimido_por_n_minimo"].sum()),
        "indeterminados_sem_check_aplicavel": df.filter(
            pl.col("trust_status") == "INDETERMINADO").height,
        "distribuicao": dist,
        "distribuicao_pct": {k: round(v / n, 4) for k, v in dist.items()},
        "por_motivo": {r["motivo"]: r["len"] for r in respondivel.group_by("motivo").len().to_dicts()},
        "trust_medio": round(respondivel["trust_score"].mean() or 0.0, 4),
        "perda_media_por_erro": round(respondivel["perda_por_erro"].mean() or 0.0, 6),
        "perda_media_por_pendencia": round(respondivel["perda_por_pendencia"].mean() or 0.0, 6),
    }


def write(cfg: Config, df: pl.DataFrame) -> Path:
    base = Path(cfg.root) / "data" / "processed" / "metadata"
    base.mkdir(parents=True, exist_ok=True)
    # `perda_por_classe` vira JSON: a chave varia por linha, e um struct com
    # esquema fixo forcaria todas as classes em todas as linhas, inventando
    # zeros onde a classe simplesmente nao foi avaliada. Zero e "sem perda";
    # ausente e "nao medido"; os dois nao podem virar a mesma coisa.
    df.with_columns(
        pl.col("perda_por_classe").map_elements(
            lambda d: __import__("json").dumps(
                {k: v for k, v in (d or {}).items() if v is not None},
                ensure_ascii=False),
            return_dtype=pl.Utf8).alias("perda_por_classe")
    ).write_parquet(base / "kpi_trust_score.parquet", compression="zstd")
    return base
