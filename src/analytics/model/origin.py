"""Proveniencia governada (ADR-0027).

Proveniencia **nao e** identidade. Sao duas perguntas independentes:

    proveniencia   de qual sistema este registro veio, e o que isso prova sobre
                   como a pessoa entrou. Sempre conhecida: o registro veio de
                   algum lugar.
    identidade     estes dois registros sao a mesma pessoa. So conhecida quando
                   o vinculo e aprovado pela governanca.

A primeira versao da SPEC amarrava as duas, e por isso rendia zero pessoas
classificadas: a identidade da VivaMarket esta 0% resolvida. Um registro em
`VIVAMARKET_LEGACY.employee_master` e, inequivocamente, de alguem que entrou
pela aquisicao — isso e verdade pelo arquivo em que ele chegou, e nao depende de
resolver com quem ele corresponde no HRIS.

Tres niveis, avaliados em ordem, e o primeiro que se aplica vence:

    P1  o sistema-fonte determina         `sources.yaml`, campo determines_origin
    P2  admissao anterior ao inicio da serie   `generation.yaml`
    P3  candidatura no ATS que resultou em admissao, com identidade resolvida
    --  nenhuma se aplica                 INDETERMINADA

P3 usa identidade, e isso nao contradiz o ADR: ali a identidade e **evidencia
positiva de processo** (a pessoa passou pelo funil de recrutamento), e nao
pre-requisito para classificar. Onde P1 se aplica, P3 e irrelevante.

**Nada aqui infere origem por atributo da pessoa.** Data de admissao, exceto o
corte declarado de P2, departamento, localidade, nome, cargo, senioridade e
faixa salarial nao entram. Nenhum deles carrega a informacao.
"""
from __future__ import annotations

import polars as pl

from generator.config import Config

INDETERMINADA = "INDETERMINADA"


def vocabulary(cfg: Config) -> dict[str, dict]:
    return cfg.sources["meta"]["origin_vocabulary"]


def determines_origin(cfg: Config) -> dict[str, str]:
    """Sistemas que determinam origem (nivel P1).

    `HRIS_CORE` e `HRIS_LEGACY` ficam de fora **por declaracao**, e nao por
    esquecimento: marca-los como organico faria toda pessoa absorvida da
    aquisicao aparecer como contratacao, fechando o headcount com uma mentira.
    """
    return {n: m["determines_origin"] for n, m in cfg.sources["systems"].items()
            if m.get("determines_origin")}


def series_start(cfg: Config) -> str:
    return str(cfg.generation["company"]["analysis_period"]["start"])


def hire_evidence(applications: pl.DataFrame, xref: pl.DataFrame) -> set[str]:
    """Nivel P3: employee_id com evidencia positiva de contratacao.

    A evidencia e uma candidatura que resultou em admissao e cujo candidato tem
    identidade RESOLVED. Nao e similaridade: e o registro do funil.
    """
    if applications.is_empty() or "employee_id" not in applications.columns:
        return set()
    resolvidos = set(
        xref.filter((pl.col("source_system") == "ATS_CLOUD")
                    & (pl.col("match_status") == "RESOLVED"))["source_employee_id"]
        .cast(pl.Utf8).to_list())
    contratados = applications.filter(
        pl.col("employee_id").is_not_null()
        & pl.col("hire_date__iso").is_not_null()
        & (pl.col("hire_date__iso") != "")
        & pl.col("candidate_id").cast(pl.Utf8).is_in(list(resolvidos) or [""]))
    return set(contratados["employee_id"].cast(pl.Utf8).to_list())


def classify(cfg: Config, pessoas: pl.DataFrame, evidencia_p3: set[str]) -> pl.DataFrame:
    """Atribui `origin_code` e `determination_rule` a cada pessoa analitica.

    `pessoas` precisa de: `source_system`, `employee_id` (pode ser nulo) e
    `hire_date__iso`.
    """
    p1 = determines_origin(cfg)
    inicio = series_start(cfg)
    vazio = list(evidencia_p3) or [""]

    return pessoas.with_columns([
        pl.when(pl.col("source_system").is_in(list(p1)))
          .then(pl.col("source_system").replace_strict(p1, default=INDETERMINADA))
        .when(pl.col("hire_date__iso").is_not_null()
              & (pl.col("hire_date__iso") != "")
              & (pl.col("hire_date__iso") < inicio))
          .then(pl.lit("POPULACAO_INICIAL"))
        .when(pl.col("employee_id").cast(pl.Utf8).is_in(vazio))
          .then(pl.lit("CONTRATACAO"))
        .otherwise(pl.lit(INDETERMINADA))
        .alias("origin_code"),

        pl.when(pl.col("source_system").is_in(list(p1)))
          .then(pl.lit("P1"))
        .when(pl.col("hire_date__iso").is_not_null()
              & (pl.col("hire_date__iso") != "")
              & (pl.col("hire_date__iso") < inicio))
          .then(pl.lit("P2"))
        .when(pl.col("employee_id").cast(pl.Utf8).is_in(vazio))
          .then(pl.lit("P3"))
        .otherwise(pl.lit(None, dtype=pl.Utf8))
        .alias("determination_rule"),
    ]).with_columns(
        pl.when(pl.col("determination_rule") == "P1").then(pl.lit("sources.yaml:determines_origin"))
         .when(pl.col("determination_rule") == "P2").then(pl.lit("generation.yaml:analysis_period.start"))
         .when(pl.col("determination_rule") == "P3").then(pl.lit("ATS_CLOUD.application"))
         .otherwise(pl.lit(None, dtype=pl.Utf8)).alias("evidence_source"))


def contamination_ceiling(pessoas: pl.DataFrame, aquisicao: int) -> dict:
    """Teto da contaminacao em INDETERMINADA.

    Quantas das pessoas sem origem determinada podem, no maximo, ser da
    aquisicao. E um numero declaravel, e cai conforme a fila de identidade for
    trabalhada. Sem ele, `INDETERMINADA` seria uma incerteza sem tamanho.
    """
    indet = pessoas.filter(pl.col("origin_code") == INDETERMINADA).height
    total = pessoas.height
    return {
        "indeterminadas": indet,
        "total": total,
        "taxa_indeterminada": round(indet / total, 4) if total else 0.0,
        "teto_contaminacao_aquisicao": aquisicao,
        "teto_relativo": round(aquisicao / total, 4) if total else 0.0,
    }
