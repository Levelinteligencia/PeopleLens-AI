"""Construcao da camada analitica L3 (F6).

    python -m analytics.model.build

Le `data/processed/conformed_approved/`, que e a fatia aprovada da camada
conformada (pos-quarentena), e escreve `data/processed/analytical/`.

Tres regras que o codigo faz valer, e nao apenas documenta:

1. **Nunca le `data/synthetic/truth/`.** A verdade e insumo de avaliacao, nunca
   de construcao. O atalho e tentador exatamente onde o dado conformado e ruim,
   e produziria um modelo que passa na avaliacao contra si mesmo (ADR-0024,
   caso de falha F-13).
2. **Toda tabela carrega a coluna `layer`.** Nove tabelas desta camada tem o
   mesmo nome de nove tabelas da camada de verdade; caminho diferente nao basta,
   porque quem le um Parquet direto do disco nao passa pelo schema de consulta.
3. **Quarentena nao entra em silencio.** O que ficou de fora fica registrado em
   `analytical_exclusions`, porque "quarentena nao entra" e "ninguem sabe o que
   ficou de fora" sao compativeis, e a segunda e inaceitavel.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import polars as pl

from generator import config
from generator.config import Config
from lineage import Lineage

from ..layer import ANALYTICAL, stamp
from . import dimensions as dim
from . import facts as fct
from . import keys, origin as prov

CONFORMED = Path("data") / "processed" / "conformed_approved"
ANALITICO = Path("data") / "processed" / "analytical"
# nao existe constante apontando para a camada de verdade aqui, e isso e
# deliberado: o teste F-13 reprova qualquer literal de codigo que a referencie,
# inclusive um que so servisse para documentar a proibicao.


# --------------------------------------------------------------------------- #
def _read(root: Path) -> dict[tuple[str, str], pl.DataFrame]:
    base = root / CONFORMED
    if not base.exists():
        raise FileNotFoundError(
            f"{base} nao existe. Rode o pipeline (make pipeline) antes da L3.")
    out = {}
    for p in sorted(base.rglob("*.parquet")):
        if p.stem.startswith("xref"):
            continue
        out[(p.parent.name, p.stem)] = pl.read_parquet(p)
    return out


def _xref(root: Path) -> pl.DataFrame:
    p = root / "data" / "processed" / "conformed" / "xref_employee_identity.parquet"
    return pl.read_parquet(p) if p.exists() else pl.DataFrame()


def _identidade(xref: pl.DataFrame) -> pl.DataFrame:
    """(sistema, id de origem) -> employee_id corporativo e status.

    Le o que a governanca decidiu e nada mais. Nenhum matching novo, nenhuma
    similaridade adicional (ADR-0004).
    """
    if xref.is_empty():
        return pl.DataFrame(schema={"source_system": pl.Utf8, "source_employee_id": pl.Utf8,
                                    "employee_id_corp": pl.Utf8, "identity_status": pl.Utf8})
    return (xref.select([
        pl.col("source_system"),
        pl.col("source_employee_id").cast(pl.Utf8),
        pl.when(pl.col("match_status") == "RESOLVED")
          .then(pl.col("employee_id").cast(pl.Utf8))
          .otherwise(None).alias("employee_id_corp"),
        pl.col("match_status").alias("identity_status")])
        .unique(subset=["source_system", "source_employee_id"]))


# --------------------------------------------------------------------------- #
# Normalizacao das fontes para o vocabulario do modelo
# --------------------------------------------------------------------------- #
MESTRE = {
    ("HRIS_CORE", "employee_master"): {
        "id": "source_employee_id", "corp_id": "employee_id",
        "hire": "hire_date__iso", "term": "termination_date__iso",
        "cols": {"country": "std_country", "business_unit": "business_unit",
                 "department": "std_department", "sub_department": "sub_department",
                 "job_level": "std_job_level", "job_level_source": "job_level",
                 "manager_id": "manager_id",
                 "location": "location", "employment_type": "employment_type", "fte": "fte__num",
                 "full_name": "full_name", "job_title": "job_title", "cost_center": "cost_center",
                 "gender": "std_gender", "race_ethnicity": "race_ethnicity",
                 "disability_flag": "disability_flag", "employment_status": "employment_status"},
    },
    ("HRIS_LEGACY", "employee_master"): {
        "id": "MATRICULA", "hire": "DT_ADMISSAO__iso", "term": "DT_DEMISSAO__iso",
        "cols": {"country": "std_country", "business_unit": None,
                 "department": "std_department", "sub_department": None,
                 "job_level": "std_job_level", "job_level_source": "NIVEL",
                 "manager_id": "GESTOR",
                 "location": "LOCAL", "employment_type": "TIPO_CONTRATO", "fte": "JORNADA__num",
                 "full_name": "NOME", "job_title": "CARGO", "cost_center": "CENTRO_CUSTO",
                 "gender": "std_gender", "race_ethnicity": None,
                 "disability_flag": None, "employment_status": "SITUACAO"},
    },
    ("VIVAMARKET_LEGACY", "employee_master"): {
        "id": "COD_FUNC", "hire": "DT_ADM__iso", "term": None,
        "cols": {"country": "std_country", "business_unit": None,
                 "department": "std_department", "sub_department": None,
                 "job_level": "std_job_level", "job_level_source": "NIVEL",
                 "manager_id": "GESTOR",
                 "location": "LOCAL", "employment_type": None, "fte": None,
                 "full_name": "NOME", "job_title": None, "cost_center": None,
                 "gender": "std_gender", "race_ethnicity": None,
                 "disability_flag": None, "employment_status": "SITUACAO"},
    },
}

SNAPSHOT = {
    ("HRIS_CORE", "headcount_snapshot"): {
        "id": "employee_id", "corp_id": "employee_id", "date": "snapshot_date__iso",
        "cols": {"country": "std_country", "business_unit": "business_unit",
                 "department": "std_department", "sub_department": "sub_department",
                 "job_level": "std_job_level", "job_level_source": "job_level",
                 "manager_id": "manager_id",
                 "location": "location", "employment_type": "employment_type", "fte": "fte__num"},
    },
    ("HRIS_LEGACY", "headcount_snapshot"): {
        "id": "MATRICULA", "date": "DT_REFERENCIA__iso",
        "cols": {"country": "std_country", "business_unit": None,
                 "department": "std_department", "sub_department": None,
                 "job_level": "std_job_level", "job_level_source": "NIVEL",
                 "manager_id": "GESTOR",
                 "location": None, "employment_type": None, "fte": "JORNADA__num"},
    },
}


def _normaliza(df: pl.DataFrame, spec: dict, sistema: str, dataset: str,
               ident: pl.DataFrame, extra: dict[str, str] | None = None) -> pl.DataFrame:
    sel = [pl.col(spec["id"]).cast(pl.Utf8).alias("source_employee_id"),
           pl.lit(sistema).alias("source_system"),
           pl.lit(dataset).alias("source_dataset"),
           pl.col("_row_id").alias("source_row_id")]
    for destino, origem in {**spec["cols"], **(extra or {})}.items():
        sel.append(pl.col(origem).cast(pl.Utf8).alias(destino) if origem and origem in df.columns
                   else pl.lit(None, dtype=pl.Utf8).alias(destino))
    if spec.get("corp_id") and spec["corp_id"] in df.columns:
        sel.append(pl.col(spec["corp_id"]).cast(pl.Utf8).alias("_corp_id"))
    out = df.select(sel)
    out = out.join(ident, on=["source_system", "source_employee_id"], how="left")
    return _party(out, tem_corp="_corp_id" in out.columns)


def _party(out: pl.DataFrame, tem_corp: bool) -> pl.DataFrame:
    """Chave da pessoa analitica, com a base da identidade declarada.

    `intrinseca`: o proprio sistema carrega o employee_id corporativo, entao nao
    ha vinculo a resolver. `xref`: o vinculo foi decidido pela governanca.
    Qualquer outro caso e pessoa provisoria, e a distincao entre as tres fica em
    coluna porque "nao precisou de vinculo" e "o vinculo foi aprovado" nao sao a
    mesma afirmacao.
    """
    corp = pl.col("_corp_id") if tem_corp else pl.lit(None, dtype=pl.Utf8)
    intrinseca = corp.is_not_null() & (corp != "") if tem_corp else pl.lit(False)
    return out.with_columns([
        pl.col("identity_status").fill_null("UNRESOLVED"),
    ]).with_columns([
        pl.when(intrinseca).then(pl.lit("intrinseca"))
          .when(pl.col("identity_status") == "RESOLVED").then(pl.lit("xref"))
          .otherwise(pl.lit("nao_resolvida")).alias("identity_basis"),
        pl.when(intrinseca).then(corp)
          .otherwise(pl.col("employee_id_corp")).alias("employee_id"),
    ]).with_columns([
        pl.when(pl.col("identity_basis") != "nao_resolvida")
          .then(pl.lit("EMP:") + pl.col("employee_id"))
          .otherwise(pl.lit("SRC:") + pl.col("source_system") + pl.lit(":")
                     + pl.col("source_employee_id")).alias("party_key"),
        (pl.col("identity_basis") == "nao_resolvida").alias("is_provisional_person"),
        pl.when(intrinseca).then(pl.lit("RESOLVED"))
          .otherwise(pl.col("identity_status")).alias("identity_status"),
    ]).drop([c for c in ("employee_id_corp", "_corp_id") if c in out.columns])


def attach_party(df: pl.DataFrame, ident: pl.DataFrame, sistema: str, dataset: str,
                 id_col: str, corp_col: str | None = None) -> pl.DataFrame:
    """Anexa a chave da pessoa analitica a um dataset de evento.

    Le o `xref` e nada mais: identidade nao resolvida vira pessoa provisoria
    (`SRC:<sistema>:<id>`), nunca um vinculo inventado (ADR-0004, ADR-0027).
    """
    cols = [pl.col(id_col).cast(pl.Utf8).alias("source_employee_id"),
            pl.lit(sistema).alias("source_system"),
            pl.lit(dataset).alias("source_dataset"),
            pl.col("_row_id").alias("source_row_id")]
    if corp_col and corp_col in df.columns:
        cols.append(pl.col(corp_col).cast(pl.Utf8).alias("_corp_id"))
    out = (df.with_columns(cols)
             .join(ident, on=["source_system", "source_employee_id"], how="left"))
    return _party(out, tem_corp=corp_col is not None and "_corp_id" in out.columns)


def build_inputs(cfg: Config, frames: dict, xref: pl.DataFrame) -> dict:
    ident = _identidade(xref)

    mestres = []
    for (s, d), spec in MESTRE.items():
        df = frames.get((s, d))
        if df is None:
            continue
        extra = {"hire_date__iso": spec["hire"], "termination_date__iso": spec["term"]}
        mestres.append(_normaliza(df, spec, s, d, ident, extra))
    mestre = pl.concat(mestres, how="diagonal_relaxed")

    obs = []
    for (s, d), spec in SNAPSHOT.items():
        df = frames.get((s, d))
        if df is None:
            continue
        obs.append(_normaliza(df, spec, s, d, ident, {"obs_date": spec["date"]}))
    observacoes = pl.concat(obs, how="diagonal_relaxed")

    ordem_sor = {sistema: i for i, (sistema, _, _) in
                 enumerate(reversed(dim.system_of_record(cfg)))}
    mestre = mestre.with_columns(
        pl.col("source_system").replace_strict(ordem_sor, default=99)
        .alias("_sor_rank")).sort(["party_key", "_sor_rank", "source_system"])

    # proveniencia: classificada por registro, independente de identidade
    apps = frames.get(("ATS_CLOUD", "application"), pl.DataFrame())
    p3 = prov.hire_evidence(apps, xref)
    mestre = prov.classify(cfg, mestre, p3)

    # uma pessoa analitica pode aparecer em mais de um cadastro; a origem
    # determinada vence a indeterminada, e P1 vence as demais
    ordem = {"P1": 0, "P2": 1, "P3": 2}
    mestre = (mestre.with_columns(
        pl.col("determination_rule").replace_strict(ordem, default=9).alias("_ord"))
        .sort(["party_key", "_ord"]))
    origem_pessoa = (mestre.group_by("party_key")
                     .agg([pl.col("origin_code").first(), pl.col("determination_rule").first(),
                           pl.col("evidence_source").first()]))
    mestre = (mestre.drop(["origin_code", "determination_rule", "evidence_source", "_ord"])
              .join(origem_pessoa, on="party_key", how="left"))

    movs = []
    for s, spec in (("HRIS_CORE", {"id": "employee_id", "corp": "employee_id",
                                   "date": "movement_date__iso"}),
                    ("HRIS_LEGACY", {"id": "MATRICULA", "corp": None,
                                     "date": "DT_MOVIMENTO__iso"})):
        df = frames.get((s, "movement"))
        if df is None:
            continue
        tipo = "movement_type" if "movement_type" in df.columns else "TIPO"
        de = "old_department" if "old_department" in df.columns else "DEPTO_ANTERIOR"
        para = "new_department" if "new_department" in df.columns else "DEPTO_NOVO"
        nde = "old_job_level" if "old_job_level" in df.columns else "NIVEL_ANTERIOR"
        npara = "new_job_level" if "new_job_level" in df.columns else "NIVEL_NOVO"
        m = df.select([
            pl.col(spec["id"]).cast(pl.Utf8).alias("source_employee_id"),
            pl.lit(s).alias("source_system"), pl.lit("movement").alias("source_dataset"),
            pl.col("_row_id").alias("source_row_id"),
            pl.col(spec["date"]).alias("movement_date"),
            pl.col(tipo).cast(pl.Utf8).alias("movement_type"),
            pl.col(de).cast(pl.Utf8).alias("old_department"),
            pl.col(para).cast(pl.Utf8).alias("new_department"),
            pl.col(nde).cast(pl.Utf8).alias("old_job_level"),
            pl.col(npara).cast(pl.Utf8).alias("new_job_level"),
            pl.lit(None, dtype=pl.Utf8).alias("country"),
            pl.lit(None, dtype=pl.Utf8).alias("business_unit"),
        ] + ([pl.col(spec["corp"]).cast(pl.Utf8).alias("_corp_id")]
             if spec["corp"] and spec["corp"] in df.columns else []))
        m = m.join(ident, on=["source_system", "source_employee_id"], how="left")
        movs.append(_party(m, tem_corp="_corp_id" in m.columns))
    movimentos = pl.concat(movs, how="diagonal_relaxed") if movs else pl.DataFrame()

    eventos = {}
    for chave, _ in {
            "performance": ("HRIS_CORE", "performance", "employee_id", "employee_id"),
            "compensation": ("PAYROLL_BR", "compensation", "matricula_folha", None)}.items():
        sistema, dataset, id_col, corp_col = _
        df = frames.get((sistema, dataset))
        if df is not None:
            eventos[chave] = attach_party(df, ident, sistema, dataset, id_col, corp_col)

    return {"mestre": mestre, "obs": observacoes, "movimentos": movimentos,
            "eventos": eventos}


# --------------------------------------------------------------------------- #
def build(cfg: Config | None = None, write: bool = True) -> dict:
    cfg = cfg or config.load()
    root = Path(cfg.root)
    lin = Lineage()
    frames = _read(root)
    xref = _xref(root)
    ent = build_inputs(cfg, frames, xref)

    sor = dim.system_of_record(cfg)
    # a dimensao usa o sistema de registro do periodo; o fato preserva todos os
    # observadores (ADR-0026). Sem isso a mesma pessoa teria duas versoes
    # vigentes na sobreposicao de 2019.
    regra = pl.lit(False)
    for sistema, de, ate in sor:
        regra = regra | ((pl.col("source_system") == sistema)
                         & (pl.col("obs_date") >= de) & (pl.col("obs_date") <= ate))
    obs_sor = ent["obs"].filter(regra & pl.col("obs_date").is_not_null() & (pl.col("obs_date") != ""))

    decisao_nivel = _valores_em_decisao(cfg, root)
    dims = {
        "dim_calendar": dim.dim_calendar(cfg),
        "dim_job_level": dim.dim_job_level(cfg),
        "dim_origin": dim.dim_origin(cfg),
        "dim_source_system": dim.dim_source_system(cfg),
        # a dimensao organizacional e derivada das combinacoes observadas: os
        # snapshots do sistema de registro e a data de entrada de cada cadastro,
        # que cobre a aquisicao, cuja populacao nao aparece em snapshot algum
        "dim_organization": dim.dim_organization(pl.concat([
            obs_sor.select(dim.ORG_KEY + ["obs_date"]),
            ent["mestre"].select(dim.ORG_KEY + [pl.col("hire_date__iso").alias("obs_date")]),
        ], how="diagonal_relaxed"), inicio=prov.series_start(cfg)),
    }
    dims["_decisao_nivel"] = decisao_nivel
    dims["dim_employee"] = fct.resolve_level(
        dim.dim_employee(cfg, obs_sor, ent["mestre"], ent["movimentos"]),
        dims["dim_job_level"], "job_level", decisao=decisao_nivel)

    fatos = {
        "fact_headcount_snapshot": fct.fact_headcount_snapshot(ent["obs"], dims, sor),
        "fact_workforce_entry": fct.fact_workforce_entry(ent["mestre"], dims),
        "fact_termination": fct.fact_termination(ent["mestre"], dims),
        "fact_movement": fct.fact_movement(ent["movimentos"], dims),
        "fact_performance": fct.fact_performance(ent["eventos"]["performance"], dims)
        if "performance" in ent["eventos"] else pl.DataFrame(),
        "fact_compensation": fct.fact_compensation(ent["eventos"]["compensation"], dims)
        if "compensation" in ent["eventos"] else pl.DataFrame(),
    }
    if ("ATS_CLOUD", "requisition") in frames:
        fatos["fact_requisition"] = fct.fact_requisition(frames[("ATS_CLOUD", "requisition")], dims)
        if ("ATS_CLOUD", "application") in frames:
            fatos["fact_application"] = fct.fact_application(
                frames[("ATS_CLOUD", "application")], dims, fatos["fact_requisition"])

    dims.pop("_decisao_nivel")
    tabelas = {**{k: stamp(v, ANALYTICAL) for k, v in dims.items()},
               **{k: stamp(v, ANALYTICAL) for k, v in fatos.items() if not v.is_empty()}}

    exclusoes = _exclusoes(root, lin)
    resumo = _resumo(cfg, tabelas, ent, exclusoes)

    for nome, df in tabelas.items():
        tipo = "dimension" if nome.startswith("dim_") else "fact"
        lin.object(tipo, f"analytical.{nome}", "layer", "conformed_approved",
                   f"camada L3, grain declarado em model_grain.yaml", rows=df.height)

    if write:
        _write(root, tabelas, exclusoes, cfg, lin, resumo)
    return {"tabelas": tabelas, "exclusoes": exclusoes, "resumo": resumo, "lineage": lin}


def _valores_em_decisao(cfg: Config, root: Path) -> set[str]:
    """Valores de nivel que a governanca marcou como decisao de negocio.

    Le a fila de excecoes da F4: sao os valores classificados como escala
    propria de sistema adquirido, `N4` e `N5`. Nao infere nada.
    """
    escalas = set()
    for m in cfg.sources["systems"].values():
        for v in (m.get("job_level_scale") or []):
            escalas.add(str(v))
    return escalas


def _exclusoes(root: Path, lin: Lineage) -> pl.DataFrame:
    """O que a quarentena tirou, registrado.

    "Quarentena nao entra" e "ninguem sabe o que ficou de fora" sao compativeis,
    e a segunda e inaceitavel: sem esta tabela, a resposta a "quantas pessoas tem
    a empresa" perde a frase que a torna honesta.
    """
    p = root / "data" / "processed" / "metadata" / "data_quarantine.parquet"
    if not p.exists():
        return pl.DataFrame(schema={"source_system": pl.Utf8, "dataset": pl.Utf8,
                                    "record_id": pl.Utf8, "failed_rule": pl.Utf8,
                                    "finding_class": pl.Utf8, "excluded_from": pl.Utf8})
    q = pl.read_parquet(p)
    return q.select([
        pl.col("source_system"), pl.col("dataset"), pl.col("record_id"),
        pl.col("failed_rule"), pl.col("finding_class"),
        pl.lit("analytical").alias("excluded_from")])


def _resumo(cfg: Config, tabelas: dict, ent: dict, exclusoes: pl.DataFrame) -> dict:
    mestre = ent["mestre"]
    pessoas = mestre.unique(subset=["party_key"])
    aquisicao = pessoas.filter(pl.col("origin_code").str.starts_with("AQUISICAO")).height
    return {
        "perfil": cfg.profile, "escala": cfg.scale, "seed": cfg.seed,
        "linhas_por_tabela": {k: v.height for k, v in sorted(tabelas.items())},
        "pessoas_analiticas": pessoas.height,
        "pessoas_provisorias": int(pessoas["is_provisional_person"].sum()),
        "origem": {r["origin_code"]: r["len"] for r in
                   pessoas.group_by("origin_code").len().sort("len", descending=True).to_dicts()},
        "origem_por_regra": {str(r["determination_rule"]): r["len"] for r in
                             pessoas.group_by("determination_rule").len().to_dicts()},
        "contaminacao": prov.contamination_ceiling(pessoas, aquisicao),
        "exclusoes": exclusoes.height,
    }


def _write(root: Path, tabelas: dict, exclusoes: pl.DataFrame, cfg: Config,
           lin: Lineage, resumo: dict) -> Path:
    base = root / ANALITICO
    base.mkdir(parents=True, exist_ok=True)
    for nome, df in tabelas.items():
        df.write_parquet(base / f"{nome}.parquet", compression="zstd")
    stamp(exclusoes, ANALYTICAL).write_parquet(base / "analytical_exclusions.parquet",
                                               compression="zstd")
    manifesto = {
        "layer": ANALYTICAL, "run_id": lin.run_id,
        "seed": cfg.seed, "profile": cfg.profile, "scale": cfg.scale,
        "config_hash": _config_hash(root),
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "tables": {k: v.height for k, v in sorted(tabelas.items())},
    }
    (base / "manifest.json").write_text(json.dumps(manifesto, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    meta = root / "data" / "processed" / "metadata"
    meta.mkdir(parents=True, exist_ok=True)
    lin.frames()["data_lineage"].write_parquet(meta / "analytical_lineage.parquet",
                                               compression="zstd")
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "f6_model.json").write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return base


def _config_hash(root: Path) -> str | None:
    p = root / "data" / "raw" / "manifest.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8")).get("config_hash")


def main() -> int:
    out = build()
    r = out["resumo"]
    print(f"L3 analytical | perfil {r['perfil']} escala {r['escala']:.0%}")
    for k, v in r["linhas_por_tabela"].items():
        print(f"  {k:28} {v:>9,}".replace(",", "."))
    print(f"pessoas analiticas: {r['pessoas_analiticas']:,}".replace(",", ".")
          + f" | provisorias: {r['pessoas_provisorias']:,}".replace(",", "."))
    print("origem:", r["origem"])
    c = r["contaminacao"]
    print(f"indeterminada: {c['taxa_indeterminada']:.1%} | "
          f"teto de contaminacao por aquisicao: {c['teto_relativo']:.1%}")
    print(f"exclusoes registradas: {r['exclusoes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
