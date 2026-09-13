"""Dimensoes da camada analitica L3 (ADR-0003).

Seis dimensoes. Tres sao geradas de configuracao (`dim_calendar`,
`dim_job_level`, `dim_source_system`, `dim_origin`) e duas sao construidas a
partir do dado conformado (`dim_employee`, `dim_organization`).

Duas decisoes atravessam o modulo:

1. **Nenhuma chave estrangeira e nula** (ADR-0025). Toda dimensao traz seus
   membros reservados, com chave negativa e nome.
2. **`dim_employee` usa o sistema de registro do periodo** para montar a linha
   do tempo (ADR-0026). O fato preserva todos os observadores; a dimensao usa o
   que vale, senao a mesma pessoa teria duas versoes vigentes na sobreposicao de
   2019.
"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from generator.config import Config

from . import keys, origin as prov

SOR_OPEN = "9999-12-31"


# --------------------------------------------------------------------------- #
# Dimensoes de configuracao
# --------------------------------------------------------------------------- #
def dim_calendar(cfg: Config) -> pl.DataFrame:
    """Um dia por linha, **gerada da configuracao e nunca dos dados**.

    A justificativa e o defeito D18: um calendario derivado dos dados nao contem
    os meses em que a carga falhou, e um mes que nao existe no eixo e um buraco
    que some do grafico. O `DQ_TIME_003` existe para detectar exatamente isso.
    """
    per = cfg.generation["company"]["analysis_period"]
    ini, fim = date.fromisoformat(str(per["start"])), date.fromisoformat(str(per["end"]))
    fim = date(fim.year + 1, fim.month, fim.day)

    dias = [ini + timedelta(days=i) for i in range((fim - ini).days + 1)]
    df = pl.DataFrame({"date_iso": [d.isoformat() for d in dias]}).with_columns([
        pl.col("date_iso").str.replace_all("-", "").cast(pl.Int64).alias("date_sk"),
        pl.col("date_iso").str.slice(0, 4).cast(pl.Int32).alias("ano"),
        pl.col("date_iso").str.slice(0, 7).alias("mes"),
        pl.col("date_iso").str.slice(5, 2).cast(pl.Int32).alias("mes_num"),
        pl.col("date_iso").str.slice(8, 2).cast(pl.Int32).alias("dia"),
    ]).with_columns([
        ((pl.col("mes_num") - 1) // 3 + 1).alias("trimestre_num"),
    ]).with_columns([
        (pl.col("ano").cast(pl.Utf8) + pl.lit("-T") + pl.col("trimestre_num").cast(pl.Utf8)).alias("trimestre"),
        (pl.col("ano").cast(pl.Utf8) + pl.lit("-H") + ((pl.col("mes_num") - 1) // 6 + 1).cast(pl.Utf8)).alias("ciclo"),
    ])
    # fim de mes: o dia seguinte tem mes diferente
    prox = df["mes"].shift(-1)
    df = df.with_columns((pl.Series("prox", prox) != pl.col("mes")).fill_null(True).alias("is_month_end"))

    esquema = {c: df.schema[c] for c in df.columns}
    res = keys.reserved_frame("dim_calendar", esquema, "date_sk",
                              defaults={"is_month_end": False})
    return pl.concat([res, df], how="vertical_relaxed")


def dim_job_level(cfg: Config) -> pl.DataFrame:
    """Treze niveis, da configuracao.

    Existe porque promocao, rebaixamento e lideranca dependem de **ordem**, e
    ordem e da escala e nao da pessoa. Guardar o rank em `dim_employee` o
    duplicaria em cada versao SCD2 e permitiria que duas versoes da mesma pessoa
    discordassem sobre quanto vale IC4.
    """
    niveis = cfg.org["job_levels"]
    linhas = [{"job_level_sk": i, "code": code, "label": code,
               "rank": i, "job_level_group": meta["group"], "track": meta["track"],
               "is_leadership": meta["track"] in ("M", "D"), "finding_class": None}
              for i, (code, meta) in enumerate(niveis.items(), start=1)]
    df = pl.DataFrame(linhas)
    esquema = {c: df.schema[c] for c in df.columns}
    res = keys.reserved_frame("dim_job_level", esquema, "job_level_sk",
                              defaults={"is_leadership": False})
    return pl.concat([res, df], how="vertical_relaxed")


def dim_origin(cfg: Config) -> pl.DataFrame:
    """Vocabulario governado de origem (ADR-0027).

    Dois papeis, um vocabulario: origem **da pessoa** em `dim_employee` e origem
    **da entrada** em `fact_workforce_entry`. Duas dimensoes criariam dois
    vocabularios que podem divergir.
    """
    voc = prov.vocabulary(cfg)
    regras = {"P1": "sources.yaml:determines_origin",
              "P2": "generation.yaml:analysis_period.start",
              "P3": "ATS_CLOUD.application"}
    linhas = [{"origin_sk": int(m["sk"]), "code": code, "label": code.replace("_", " ").title(),
               "is_hire": bool(m["is_hire"]), "is_acquisition": bool(m["is_acquisition"]),
               "determination_rule": m.get("rule"),
               "evidence_source": regras.get(m.get("rule") or "")}
              for code, m in voc.items()]
    return pl.DataFrame(linhas).sort("origin_sk")


def dim_source_system(cfg: Config) -> pl.DataFrame:
    """Sistema-fonte com vigencia, populacao e papel.

    E a dimensao que o achado 1 da F5 exige: se vigencia e populacao de cada
    fonte ficam so em comentario de YAML, o erro se repete na camada seguinte.
    """
    sor = {}
    for r in cfg.sources.get("system_of_record", {}).get("headcount", []):
        sor[r["system"]] = (str(r["from"]), str(r["to"]) if r["to"] else SOR_OPEN)

    linhas = []
    for i, (nome, m) in enumerate(cfg.sources["systems"].items(), start=1):
        de, ate = sor.get(nome, (None, None))
        linhas.append({
            "source_sk": i, "code": nome, "label": m.get("name", nome),
            "wave": int(m.get("wave") or 0),
            "active_from": str(m["active_from"]) if m.get("active_from") else None,
            "active_to": str(m["active_to"]) if m.get("active_to") else None,
            "countries": ",".join(m.get("countries") or []),
            "field_language": m.get("field_language"),
            "population_rule": (m.get("population_rule") or "").strip() or None,
            "has_enterprise_employee_id": str(m.get("has_enterprise_employee_id")),
            "determines_origin": m.get("determines_origin"),
            "sor_headcount_from": de, "sor_headcount_to": ate,
            "finding_class": None,
        })
    df = pl.DataFrame(linhas)
    esquema = {c: df.schema[c] for c in df.columns}
    res = keys.reserved_frame("dim_source_system", esquema, "source_sk", defaults={"wave": 0})
    return pl.concat([res, df], how="vertical_relaxed")


def system_of_record(cfg: Config) -> list[tuple[str, str, str]]:
    return [(r["system"], str(r["from"]), str(r["to"]) if r["to"] else SOR_OPEN)
            for r in cfg.sources.get("system_of_record", {}).get("headcount", [])]


# --------------------------------------------------------------------------- #
# Dimensoes construidas do dado conformado
# --------------------------------------------------------------------------- #
ORG_KEY = ["country", "business_unit", "department", "sub_department"]


def dim_organization(obs: pl.DataFrame, inicio: str = "2016-01-01") -> pl.DataFrame:
    """Unidade organizacional, **derivada**.

    `org_structure` esta declarado em `sources.yaml` para os dois HRIS e nunca
    foi projetado, entao esta dimensao nasce das combinacoes observadas. As
    consequencias ficam declaradas em `is_derived`:

    - unidade que existe sem ninguem alocado nao aparece;
    - a data de criacao e aproximada pela primeira alocacao observada;
    - renomear e indistinguivel de criar outra e mover todo mundo.
    """
    # observacao anterior ao periodo de analise nao data uma unidade: uma
    # admissao de 1994 nao prova que aquele departamento existia em 1994, e
    # deixar entrar seria a falsa precisao que o caso de falha F-07 proibe
    base = (obs.filter(pl.col("obs_date").is_not_null() & (pl.col("obs_date") != "")
                       & (pl.col("obs_date") >= inicio))
               .group_by(ORG_KEY)
               .agg([pl.col("obs_date").min().alias("effective_from"),
                     pl.col("obs_date").max().alias("ultima_observacao")]))
    fim_serie = obs["obs_date"].max()
    base = base.with_columns([
        pl.when(pl.col("ultima_observacao") >= fim_serie)
          .then(pl.lit(SOR_OPEN)).otherwise(pl.col("ultima_observacao")).alias("effective_to"),
        (pl.col("ultima_observacao") >= fim_serie).alias("is_current"),
        pl.lit(True).alias("is_derived"),
        pl.lit(None, dtype=pl.Utf8).alias("finding_class"),
        pl.lit(None, dtype=pl.Utf8).alias("code"),
        pl.lit(None, dtype=pl.Utf8).alias("label"),
    ]).sort(ORG_KEY)
    base = keys.surrogate(base, "org_sk", start=1)

    esquema = {c: base.schema[c] for c in base.columns}
    res = keys.reserved_frame("dim_organization", esquema, "org_sk",
                              defaults={"is_derived": False, "is_current": True,
                                        "effective_to": SOR_OPEN})
    return pl.concat([res, base], how="vertical_relaxed")


TRACKED = ["country", "business_unit", "department", "sub_department",
           "job_level", "manager_id", "location", "employment_type", "fte"]


def _versions(obs: pl.DataFrame) -> pl.DataFrame:
    """Colapsa observacoes consecutivas iguais numa versao SCD2.

    Abre versao quando muda qualquer atributo que um KPI recorta. Nome e titulo
    nao abrem versao: abrir versao para tudo transforma SCD2 em log de auditoria
    e multiplica o volume sem ganho analitico.
    """
    obs = obs.sort(["party_key", "obs_date"])
    assinatura = pl.concat_str([pl.col(c).cast(pl.Utf8).fill_null("~") for c in TRACKED], separator="|")
    obs = obs.with_columns(assinatura.alias("_sig"))
    obs = obs.with_columns(
        ((pl.col("_sig") != pl.col("_sig").shift(1).over("party_key"))
         | pl.col("_sig").shift(1).over("party_key").is_null()).alias("_muda"))
    obs = obs.with_columns(pl.col("_muda").cum_sum().over("party_key").alias("_versao"))

    # identidade vem da propria observacao: ha pessoas que aparecem no snapshot
    # e nao no cadastro (orfas do DQ_REF_007), e sem isso elas ficariam com a
    # base da identidade nula, que e justamente o nulo que o ADR-0025 proibe
    agg = [pl.col("obs_date").min().alias("effective_from"),
           pl.col("obs_date").max().alias("ultima_observacao"),
           pl.col("source_system").last().alias("source_system"),
           pl.col("identity_status").last().alias("_id_status"),
           pl.col("identity_basis").last().alias("_id_basis"),
           pl.col("is_provisional_person").last().alias("_id_prov")]
    agg += [pl.col(c).last().alias(c) for c in TRACKED]
    agg += [pl.col("source_row_id").first().alias("source_row_id")]
    return obs.group_by(["party_key", "_versao"]).agg(agg).sort(["party_key", "_versao"])


def dim_employee(cfg: Config, obs: pl.DataFrame, mestre: pl.DataFrame,
                 movimentos: pl.DataFrame) -> pl.DataFrame:
    """Pessoa analitica x versao de atributos, SCD tipo 2.

    A chave natural e `party_key` (ADR-0027, decisao 6): `EMP:<employee_id>`
    quando a identidade foi RESOLVED pela governanca, `SRC:<sistema>:<id>` em
    qualquer outro caso. A pessoa provisoria e uma pessoa de verdade, contavel,
    com origem classificada, cujo vinculo com outras aparicoes dela mesma esta
    em aberto.
    """
    v = _versions(obs) if not obs.is_empty() else obs

    if not v.is_empty():
        # fecha a vigencia no dia anterior ao inicio da versao seguinte
        prox = pl.col("effective_from").shift(-1).over("party_key")
        v = v.with_columns(
            pl.when(prox.is_null()).then(pl.lit(SOR_OPEN))
              .otherwise(prox.str.to_date().dt.offset_by("-1d").dt.to_string("%Y-%m-%d"))
              .alias("effective_to"))
        v = v.with_columns((pl.col("effective_to") == SOR_OPEN).alias("is_current"))

    # motivo da mudanca: do movimento observado quando existe; senao, honesto
    if not v.is_empty() and not movimentos.is_empty():
        mv = (movimentos.select(["party_key", "movement_date", "movement_type"])
              .with_columns(pl.col("movement_date").str.slice(0, 7).alias("_m")))
        v = (v.with_columns(pl.col("effective_from").str.slice(0, 7).alias("_m"))
               .join(mv.select(["party_key", "_m", "movement_type"]).unique(subset=["party_key", "_m"]),
                     on=["party_key", "_m"], how="left"))
    else:
        v = v.with_columns(pl.lit(None, dtype=pl.Utf8).alias("movement_type")) if not v.is_empty() else v

    if not v.is_empty():
        primeira = pl.col("_versao") == 1
        v = v.with_columns(
            pl.when(primeira).then(pl.lit("Entrada"))
             .when(pl.col("movement_type").is_not_null()).then(pl.col("movement_type"))
             .otherwise(pl.lit("Observado sem evento")).alias("change_reason")).drop(["_m", "movement_type"])

    # pessoas que so existem no cadastro (carga unica, sem snapshot)
    # uma pessoa analitica pode ter cadastro em mais de um sistema; vence o de
    # maior precedencia (`_sor_rank`), senao a mesma pessoa teria duas versoes
    # vigentes na mesma data, que e o caso de falha F-02
    so_mestre = mestre.filter(~pl.col("party_key").is_in(
        v["party_key"].unique().to_list() if not v.is_empty() else []))
    if "_sor_rank" in so_mestre.columns:
        so_mestre = so_mestre.sort(["party_key", "_sor_rank"]).unique(
            subset=["party_key"], keep="first", maintain_order=True)
    else:
        so_mestre = so_mestre.unique(subset=["party_key"], keep="first", maintain_order=True)
    if not so_mestre.is_empty():
        extra = so_mestre.select(
            ["party_key", "source_system", "source_row_id"]
            + [c for c in TRACKED if c in so_mestre.columns]).with_columns([
                pl.lit(1).cast(pl.UInt32).alias("_versao"),
                so_mestre["hire_date__iso"].alias("effective_from"),
                pl.lit(SOR_OPEN).alias("effective_to"),
                pl.lit(SOR_OPEN).alias("ultima_observacao"),
                pl.lit(True).alias("is_current"),
                pl.lit("Entrada").alias("change_reason"),
                so_mestre["identity_status"].alias("_id_status"),
                so_mestre["identity_basis"].alias("_id_basis"),
                so_mestre["is_provisional_person"].alias("_id_prov")])
        for c in TRACKED:
            if c not in extra.columns:
                extra = extra.with_columns(pl.lit(None, dtype=pl.Utf8).alias(c))
        v = pl.concat([v, extra.select(v.columns)], how="vertical_relaxed") if not v.is_empty() else extra

    atributos = [c for c in ("employee_id", "source_employee_id", "full_name", "job_title",
                             "cost_center", "gender", "race_ethnicity", "disability_flag",
                             "hire_date__iso", "termination_date__iso", "employment_status",
                             "identity_status", "identity_basis", "is_provisional_person",
                             "job_level_source",
                             "origin_code", "determination_rule", "evidence_source")
                 if c in mestre.columns]
    v = v.join(mestre.select(["party_key"] + atributos).unique(
        subset=["party_key"], keep="first", maintain_order=True), on="party_key", how="left")
    for col, tmp in (("identity_status", "_id_status"), ("identity_basis", "_id_basis"),
                     ("is_provisional_person", "_id_prov")):
        if tmp in v.columns:
            v = (v.with_columns(pl.coalesce([pl.col(col), pl.col(tmp)]).alias(col))
                 if col in v.columns else v.with_columns(pl.col(tmp).alias(col)))
            v = v.drop(tmp)

    v = v.rename({"hire_date__iso": "hire_date", "termination_date__iso": "termination_date"}) \
        if "hire_date__iso" in v.columns else v
    v = v.sort(["party_key", "effective_from"])
    v = keys.surrogate(v, "employee_sk", start=1).drop("_versao")

    esquema = {c: v.schema[c] for c in v.columns}
    res = keys.reserved_frame("dim_employee", esquema, "employee_sk",
                              defaults={"is_current": True, "effective_to": SOR_OPEN,
                                        "is_provisional_person": False})
    if "party_key" in esquema:
        res = res.with_columns(pl.Series("party_key",
                                         [m["code"] for m in keys.RESERVED["dim_employee"]]))
    return pl.concat([res, v], how="vertical_relaxed")
