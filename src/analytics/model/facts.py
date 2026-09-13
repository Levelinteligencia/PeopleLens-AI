"""Fatos da camada analitica L3.

Sete fatos, divididos por **grain** e nao por assunto. Duas regras atravessam o
modulo:

1. **Todo fato se liga a versao da dimensao vigente na data do fato**, nunca a
   versao atual. Contar mulheres em lideranca em 2018 usando o nivel de 2026
   seria reescrever a historia, e e a forma mais comum de errar isso. O
   mecanismo e `join_asof` para tras por `party_key`.
2. **O sistema observador faz parte do grain** dos fatos de estado e de evento
   derivado (ADR-0026), porque entre maio e novembro de 2019 os dois HRIS
   descrevem a mesma pessoa no mesmo mes.
"""
from __future__ import annotations

import polars as pl

from . import keys

MEMBRO_SEM_CHAVE = -1
MEMBRO_UNMAPPED = -1
MEMBRO_DECISAO = -2
MEMBRO_NAO_OCORREU = -5
MEMBRO_FORA_VIGENCIA = -6
MEMBRO_ANTERIOR_A_SERIE = -7

SERIE_INICIO = 20160101      # espelha generation.yaml: analysis_period.start


def _date_sk(col: str) -> pl.Expr:
    """Data ISO para chave inteira.

    Vazio vira `ainda nao ocorreu`; data real anterior ao periodo de analise
    vira `anterior a serie`. A segunda existe porque ha admissoes de 1994 e o
    eixo cobre o periodo declarado: esticar o calendario ate a data mais antiga
    do dado o tornaria derivado do dado, que e o que o D18 proibe. A data em si
    continua na coluna de origem do fato.
    """
    num = pl.col(col).str.replace_all("-", "").cast(pl.Int64, strict=False)
    return (pl.when(pl.col(col).is_null() | (pl.col(col) == ""))
            .then(pl.lit(MEMBRO_NAO_OCORREU))
            .when(num.is_null()).then(pl.lit(MEMBRO_NAO_OCORREU))
            .when(num < SERIE_INICIO).then(pl.lit(MEMBRO_ANTERIOR_A_SERIE))
            .otherwise(num))


def resolve_employee(df: pl.DataFrame, dim_emp: pl.DataFrame, date_col: str) -> pl.DataFrame:
    """Liga o fato a versao de `dim_employee` vigente na data do fato."""
    d = (dim_emp.filter(pl.col("employee_sk") > 0)
         .select(["party_key", "effective_from", "employee_sk"])
         .drop_nulls("effective_from")
         .sort(["effective_from", "party_key"]))
    e = (df.with_columns(pl.col(date_col).fill_null("").alias("_d"))
           .sort(["_d", "party_key"]))
    out = e.join_asof(d, left_on="_d", right_on="effective_from",
                      by="party_key", strategy="backward")
    return out.with_columns(
        pl.col("employee_sk").fill_null(MEMBRO_SEM_CHAVE).cast(pl.Int64)).drop("_d")


def resolve_org(df: pl.DataFrame, dim_org: pl.DataFrame, cols: dict[str, str],
                alias: str = "org_sk") -> pl.DataFrame:
    """Liga o fato a unidade organizacional.

    Coluna de origem `UNMAPPED` cai no membro reservado da dimensao, nunca em
    nulo: pendencia de mapeamento continua contavel (ADR-0025).
    """
    chave = ["country", "business_unit", "department", "sub_department"]
    tmp = df.with_columns([pl.col(v).alias(f"_o_{k}") if v in df.columns
                           else pl.lit(None, dtype=pl.Utf8).alias(f"_o_{k}")
                           for k, v in cols.items()])
    for k in chave:
        if f"_o_{k}" not in tmp.columns:
            tmp = tmp.with_columns(pl.lit(None, dtype=pl.Utf8).alias(f"_o_{k}"))
    d = (dim_org.filter(pl.col("org_sk") > 0)
         .select(chave + ["org_sk"]).unique(subset=chave))
    d = d.rename({c: f"_o_{c}" for c in chave})
    out = tmp.join(d, on=[f"_o_{c}" for c in chave], how="left")
    tem_unmapped = pl.any_horizontal([pl.col(f"_o_{c}") == keys.UNMAPPED for c in chave])
    out = out.with_columns(
        pl.when(pl.col("org_sk").is_not_null()).then(pl.col("org_sk"))
          .when(tem_unmapped).then(pl.lit(MEMBRO_UNMAPPED))
          .otherwise(pl.lit(MEMBRO_UNMAPPED)).cast(pl.Int64).alias(alias))
    return out.drop([f"_o_{c}" for c in chave] + (["org_sk"] if alias != "org_sk" else []))


def resolve_level(df: pl.DataFrame, dim_lvl: pl.DataFrame, col: str,
                  alias: str = "job_level_sk", decisao: set[str] | None = None) -> pl.DataFrame:
    """Liga o fato ao nivel.

    `UNMAPPED` vindo de um valor que a governanca marcou como decisao de negocio
    (`N4`, `N5` da VivaMarket) vai para o membro `-2`, e nao para o `-1`: a
    distincao entre "falta mapear" e "nao existe resposta tecnica" e a que a F5
    fixou e que o ADR-0025 preserva.
    """
    decisao = decisao or set()
    d = dim_lvl.filter(pl.col("job_level_sk") > 0).select(["code", "job_level_sk"])
    src = col if col in df.columns else None
    if src is None:
        return df.with_columns(pl.lit(MEMBRO_UNMAPPED).cast(pl.Int64).alias(alias))
    out = df.join(d.rename({"code": "_lvl"}), left_on=src, right_on="_lvl", how="left")
    origem_bruta = "job_level_source" if "job_level_source" in df.columns else None
    marca_decisao = (pl.col(origem_bruta).is_in(list(decisao) or [""])
                     if origem_bruta else pl.lit(False))
    return out.with_columns(
        pl.when(pl.col("job_level_sk").is_not_null()).then(pl.col("job_level_sk"))
          .when(marca_decisao).then(pl.lit(MEMBRO_DECISAO))
          .otherwise(pl.lit(MEMBRO_UNMAPPED)).cast(pl.Int64).alias(alias)
    ).drop("job_level_sk" if alias != "job_level_sk" else [])


def _source_sk(df: pl.DataFrame, dim_src: pl.DataFrame) -> pl.DataFrame:
    d = dim_src.filter(pl.col("source_sk") > 0).select(["code", "source_sk"])
    return (df.join(d.rename({"code": "_src"}), left_on="source_system", right_on="_src", how="left")
              .with_columns(pl.col("source_sk").fill_null(MEMBRO_FORA_VIGENCIA).cast(pl.Int64)))


# --------------------------------------------------------------------------- #
def fact_headcount_snapshot(obs: pl.DataFrame, dims: dict, sor: list) -> pl.DataFrame:
    """Grain: **pessoa x mes de referencia x sistema observador**.

    O sistema faz parte do grain porque na sobreposicao de 2019 os dois HRIS
    descrevem a mesma pessoa no mesmo mes. `is_system_of_record` marca qual
    observacao vale; somar sem esse filtro duplica a sobreposicao, e a
    duplicacao e o comportamento correto (caso de falha F-01).
    """
    f = resolve_employee(obs, dims["dim_employee"], "obs_date")
    f = _source_sk(f, dims["dim_source_system"])
    f = resolve_org(f, dims["dim_organization"],
                    {"country": "country", "business_unit": "business_unit",
                     "department": "department", "sub_department": "sub_department"})
    f = resolve_level(f, dims["dim_job_level"], "job_level", decisao=dims["_decisao_nivel"])

    regra = pl.lit(False)
    for sistema, de, ate in sor:
        regra = regra | ((pl.col("source_system") == sistema)
                         & (pl.col("obs_date") >= de) & (pl.col("obs_date") <= ate))

    return f.with_columns([
        _date_sk("obs_date").alias("date_sk"),
        regra.alias("is_system_of_record"),
        pl.lit(1).cast(pl.Int32).alias("headcount"),
        pl.col("fte").cast(pl.Float64, strict=False).alias("fte"),
    ]).select(["employee_sk", "date_sk", "source_sk", "org_sk", "job_level_sk",
               "party_key", "obs_date", "is_system_of_record", "headcount", "fte",
               "manager_id", "source_system", "source_dataset", "source_row_id"])


def fact_workforce_entry(mestre: pl.DataFrame, dims: dict) -> pl.DataFrame:
    """Grain: **pessoa x data de entrada x sistema observador**.

    Era `fact_hire`. Renomeada porque **entrada na forca de trabalho nao e
    sinonimo de contratacao**, e um fato chamado `hire` convida a somar tudo
    como contratacao para fechar headcount.

    `origin_sk` e obrigatorio e **nao tem default silencioso**: entrada sem
    regra de proveniencia aplicavel fica `INDETERMINADA`, e um KPI de
    contratacao filtra `is_hire` explicitamente (caso de falha F-15).
    """
    base = mestre.filter(pl.col("hire_date__iso").is_not_null()
                         & (pl.col("hire_date__iso") != ""))
    f = resolve_employee(base, dims["dim_employee"], "hire_date__iso")
    f = _source_sk(f, dims["dim_source_system"])
    o = dims["dim_origin"].select(["code", "origin_sk"]).rename({"code": "_o"})
    f = f.join(o, left_on="origin_code", right_on="_o", how="left")
    return f.with_columns([
        _date_sk("hire_date__iso").alias("date_sk"),
        pl.col("origin_sk").cast(pl.Int64),          # sem fill_null: F-16 exige que exista
        pl.lit(1).cast(pl.Int32).alias("entries"),
        pl.lit("derivado_de_atributo").alias("event_evidence"),
    ]).select(["employee_sk", "date_sk", "source_sk", "origin_sk", "party_key",
               "hire_date__iso", "entries", "event_evidence", "determination_rule",
               "evidence_source", "source_system", "source_dataset", "source_row_id"])


def fact_termination(mestre: pl.DataFrame, dims: dict) -> pl.DataFrame:
    """Grain: **pessoa x data de desligamento x sistema observador**.

    **Sem motivo, sem tipo, sem flag de voluntariedade.** Nenhuma fonte da onda
    1 carrega esses campos, e as colunas nao sao criadas vazias, porque coluna
    nula convida a preencher (caso de falha F-09). Turnover e contavel;
    attrition voluntaria e regrettable attrition nao existem aqui.
    """
    base = mestre.filter(pl.col("termination_date__iso").is_not_null()
                         & (pl.col("termination_date__iso") != ""))
    f = resolve_employee(base, dims["dim_employee"], "termination_date__iso")
    f = _source_sk(f, dims["dim_source_system"])
    tenure = (pl.col("termination_date__iso").str.to_date(strict=False)
              - pl.col("hire_date__iso").str.to_date(strict=False)).dt.total_days() / 30.44
    return f.with_columns([
        _date_sk("termination_date__iso").alias("date_sk"),
        pl.lit(1).cast(pl.Int32).alias("terminations"),
        tenure.round(2).alias("tenure_months"),
        pl.lit("derivado_de_atributo").alias("event_evidence"),
    ]).select(["employee_sk", "date_sk", "source_sk", "party_key",
               "termination_date__iso", "terminations", "tenure_months", "event_evidence",
               "source_system", "source_dataset", "source_row_id"])


def fact_movement(mov: pl.DataFrame, dims: dict) -> pl.DataFrame:
    """Grain: **uma movimentacao observada**.

    O unico fato de evento realmente observado da onda 1, e por isso o unico que
    sustenta mobilidade e promocao com confianca de evento e nao de
    reconstrucao. `level_delta` e aritmetica sobre o rank declarado; chamar
    `level_delta > 0` de promocao e regra de negocio, e e F7.
    """
    if mov.is_empty():
        return mov
    f = resolve_employee(mov, dims["dim_employee"], "movement_date")
    f = _source_sk(f, dims["dim_source_system"])
    f = resolve_org(f, dims["dim_organization"],
                    {"country": "country", "business_unit": "business_unit",
                     "department": "old_department", "sub_department": "_none"},
                    alias="org_sk_from")
    f = resolve_org(f, dims["dim_organization"],
                    {"country": "country", "business_unit": "business_unit",
                     "department": "new_department", "sub_department": "_none"},
                    alias="org_sk_to")
    rank = dims["dim_job_level"].filter(pl.col("job_level_sk") > 0).select(["code", "rank"])
    f = (f.join(rank.rename({"code": "_a", "rank": "rank_from"}), left_on="old_job_level",
                right_on="_a", how="left")
          .join(rank.rename({"code": "_b", "rank": "rank_to"}), left_on="new_job_level",
                right_on="_b", how="left"))
    return f.with_columns([
        _date_sk("movement_date").alias("date_sk"),
        pl.lit(1).cast(pl.Int32).alias("movements"),
        (pl.col("rank_to") - pl.col("rank_from")).alias("level_delta"),
        pl.lit("observado").alias("event_evidence"),
    ]).with_row_index("movement_sk", offset=1).with_columns(
        pl.col("movement_sk").cast(pl.Int64)
    ).select(["movement_sk", "employee_sk", "date_sk", "source_sk", "org_sk_from", "org_sk_to",
              "party_key", "movement_date", "movement_type", "movements", "level_delta",
              "event_evidence", "source_system", "source_dataset", "source_row_id"])


def fact_requisition(req: pl.DataFrame, dims: dict) -> pl.DataFrame:
    """Grain: **uma requisicao**, em snapshot acumulativo.

    Quatro papeis do calendario: abertura, aprovacao, publicacao e admissao.
    Marco nao atingido aponta para o membro `-5` (`ainda nao ocorreu`), nunca
    para nulo.
    """
    f = _source_sk(req.with_columns([
        pl.lit("ATS_CLOUD").alias("source_system"),
        pl.lit("requisition").alias("source_dataset"),
        pl.col("_row_id").alias("source_row_id")]), dims["dim_source_system"])
    f = resolve_org(f, dims["dim_organization"],
                    {"country": "std_country", "business_unit": "org_business_unit",
                     "department": "std_department", "sub_department": "org_sub_department"})
    f = resolve_level(f, dims["dim_job_level"], "std_job_level")
    dias = lambda a, b: ((pl.col(b).str.to_date(strict=False) - pl.col(a).str.to_date(strict=False))
                         .dt.total_days())
    return f.with_columns([
        _date_sk("opening_date__iso").alias("date_sk_opening"),
        _date_sk("approval_date__iso").alias("date_sk_approval"),
        _date_sk("posting_date__iso").alias("date_sk_posting"),
        _date_sk("hire_date__iso").alias("date_sk_hire"),
        pl.lit(1).cast(pl.Int32).alias("requisitions"),
        dias("opening_date__iso", "hire_date__iso").alias("days_to_fill"),
        dias("opening_date__iso", "approval_date__iso").alias("days_to_approve"),
    ]).with_row_index("requisition_sk", offset=1).with_columns(
        pl.col("requisition_sk").cast(pl.Int64)
    ).select(["requisition_sk", "requisition_id", "source_sk", "org_sk", "job_level_sk",
              "date_sk_opening", "date_sk_approval", "date_sk_posting", "date_sk_hire",
              "requisitions", "days_to_fill", "days_to_approve", "status",
              "source_system", "source_dataset", "source_row_id"])


def fact_application(app: pl.DataFrame, dims: dict, fact_req: pl.DataFrame) -> pl.DataFrame:
    """Grain: **requisicao x candidato**.

    Separado de `fact_requisition` pelo ADR-0005, e o grain confirma a razao:
    juntar multiplicaria a contagem de vagas pelo numero de candidatos.

    Apenas uma fracao das candidaturas tem identidade resolvida; as demais
    apontam para o membro `-1` de `dim_employee`, o que e correto porque a
    maioria dos candidatos legitimamente nunca virou colaborador.
    """
    f = _source_sk(app.with_columns([
        pl.lit("ATS_CLOUD").alias("source_system"),
        pl.lit("application").alias("source_dataset"),
        pl.col("_row_id").alias("source_row_id"),
        pl.lit(None, dtype=pl.Utf8).alias("party_key")]), dims["dim_source_system"])
    f = resolve_employee(f, dims["dim_employee"], "hire_date__iso")
    r = fact_req.select(["requisition_id", "requisition_sk"]).unique(subset=["requisition_id"])
    f = f.join(r, on="requisition_id", how="left")
    dias = lambda a, b: ((pl.col(b).str.to_date(strict=False) - pl.col(a).str.to_date(strict=False))
                         .dt.total_days())
    return f.with_columns([
        _date_sk("application_date__iso").alias("date_sk_application"),
        _date_sk("offer_date__iso").alias("date_sk_offer"),
        _date_sk("hire_date__iso").alias("date_sk_hire"),
        pl.lit(1).cast(pl.Int32).alias("applications"),
        pl.col("offer_date__iso").is_not_null().cast(pl.Int32).alias("offers"),
        (pl.col("offer_accepted") == "true").cast(pl.Int32).alias("accepts"),
        dias("application_date__iso", "hire_date__iso").alias("days_to_hire"),
        pl.col("requisition_sk").fill_null(MEMBRO_SEM_CHAVE).cast(pl.Int64),
    ]).with_row_index("application_sk", offset=1).with_columns(
        pl.col("application_sk").cast(pl.Int64)
    ).select(["application_sk", "requisition_sk", "employee_sk", "source_sk",
              "candidate_id", "date_sk_application", "date_sk_offer", "date_sk_hire",
              "applications", "offers", "accepts", "days_to_hire", "source",
              "source_system", "source_dataset", "source_row_id"])


def fact_performance(perf: pl.DataFrame, dims: dict) -> pl.DataFrame:
    """Grain: **pessoa x ciclo de avaliacao**.

    Guarda a nota padronizada **e** `scale_type`, porque comparar distribuicao
    de performance atraves da mudanca de escala de 2021 e armadilha que a camada
    seguinte precisa enxergar para evitar.
    """
    f = resolve_employee(perf, dims["dim_employee"], "review_date__iso")
    f = _source_sk(f, dims["dim_source_system"])
    return f.with_columns([
        _date_sk("review_date__iso").alias("date_sk"),
        pl.lit(1).cast(pl.Int32).alias("reviews"),
        pl.when(pl.col("review_date__iso") < "2021-01-01").then(pl.lit("numerica"))
          .otherwise(pl.lit("textual")).alias("scale_type"),
    ]).select(["employee_sk", "date_sk", "source_sk", "party_key", "review_cycle",
               "std_performance_rating", "scale_type", "reviews",
               "source_system", "source_dataset", "source_row_id"])


def fact_compensation(comp: pl.DataFrame, dims: dict) -> pl.DataFrame:
    """Grain: **pessoa x data de vigencia da mudanca salarial**.

    Populacao restrita e declarada: so Brasil, e so identidade resolvida. Sem
    conversao de moeda, porque converter e interpretacao e e F7 (ADR-0006).
    """
    f = resolve_employee(comp, dims["dim_employee"], "dt_vigencia__iso")
    f = _source_sk(f, dims["dim_source_system"])
    return f.with_columns([
        _date_sk("dt_vigencia__iso").alias("date_sk"),
        pl.col("salario_base__num").cast(pl.Float64, strict=False).alias("base_salary"),
        pl.lit(1).cast(pl.Int32).alias("salary_change_count"),
    ]).select(["employee_sk", "date_sk", "source_sk", "party_key", "dt_vigencia__iso",
               "base_salary", "moeda", "motivo", "salary_change_count",
               "source_system", "source_dataset", "source_row_id"])
