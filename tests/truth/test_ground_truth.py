"""Testes da camada de verdade (F1).

Nao sao testes de Data Quality: a camada de qualidade opera sobre dados sujos e
so existe na F5. Aqui verificamos que a verdade e internamente coerente, que o
mundo gerado e plausivel e que a geracao e reproduzivel a partir do seed.
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from generator import config, materialize, metrics, validate
from generator.events.lifecycle import World


@pytest.fixture(scope="session")
def built():
    cfg = config.load()
    cfg.generation["reproducibility"]["active_profile"] = "smoke"
    truth = World(cfg).run()
    tables = materialize.build_all(cfg, truth)
    return cfg, truth, tables


# --------------------------------------------------------------- configuracao
def test_config_valida():
    cfg = config.load()
    assert cfg.seed
    assert 0 < cfg.scale <= 1.0
    assert len(cfg.org["job_levels"]) == 13


def test_config_invalida_falha_cedo():
    cfg = config.load()
    cfg.generation["segments"][0]["hc_share"] += 0.5
    with pytest.raises(ValueError, match="hc_share"):
        config.validate(cfg)


# -------------------------------------------------------------- coerencia
def test_nenhuma_validacao_bloqueante_falha(built):
    cfg, _, tables = built
    falhas = validate.blocking(validate.run_all(cfg, tables))
    assert not falhas, "\n".join(f"{c.check_id}: {c.name} | {c.detail}" for c in falhas)


def test_nenhum_gestor_orfao(built):
    _, _, t = built
    emp = t["dim_employee"]
    ids = set(emp["employee_id"].to_list())
    mgrs = emp.filter(pl.col("manager_id").is_not_null())["manager_id"].to_list()
    assert set(mgrs) <= ids


def test_um_unico_topo_de_hierarquia(built):
    _, _, t = built
    cur = t["dim_employee"].filter(pl.col("is_current") & (pl.col("employment_status") == "Active"))
    assert cur.filter(pl.col("manager_id").is_null()).height == 1


# ------------------------------------------------------------- reprodutibilidade
def test_mesmo_seed_produz_o_mesmo_mundo():
    cfg = config.load()
    cfg.generation["reproducibility"]["active_profile"] = "smoke"
    a = materialize.build_all(cfg, World(cfg).run())
    b = materialize.build_all(cfg, World(cfg).run())
    for name in a:
        assert materialize.frame_hash(a[name]) == materialize.frame_hash(b[name]), name


def test_seeds_diferentes_produzem_mundos_diferentes():
    cfg = config.load()
    cfg.generation["reproducibility"]["active_profile"] = "smoke"
    a = materialize.build_all(cfg, World(cfg).run())
    cfg2 = config.load()
    cfg2.generation["reproducibility"]["active_profile"] = "smoke"
    cfg2.generation["reproducibility"]["master_seed"] = 4242
    b = materialize.build_all(cfg2, World(cfg2).run())
    assert materialize.frame_hash(a["dim_employee"]) != materialize.frame_hash(b["dim_employee"])


# ------------------------------------------------------- a verdade nao tem defeito
@pytest.mark.parametrize("tabela,colunas", [
    ("dim_employee", ["employee_id", "hire_date", "country", "department", "job_level"]),
    ("fact_headcount_snapshot", ["employee_id", "snapshot_date", "country", "job_level"]),
    ("fact_termination", ["employee_id", "termination_date", "termination_type"]),
    ("fact_compensation", ["employee_id", "effective_date", "base_salary", "currency"]),
])
def test_camada_de_verdade_sem_campos_obrigatorios_nulos(built, tabela, colunas):
    """Na F1 nao ha injecao de defeitos: a verdade e completa por construcao.
    Nulos so aparecem a partir da F2, e sempre com causa declarada."""
    _, _, t = built
    for col in colunas:
        assert t[tabela][col].null_count() == 0, f"{tabela}.{col}"


def test_datas_sempre_dentro_da_janela_de_analise(built):
    cfg, _, t = built
    start, end = cfg.period
    snap = t["fact_headcount_snapshot"]["snapshot_date"]
    assert snap.min() >= start and snap.max() <= end
    term = t["fact_termination"]["termination_date"]
    assert term.min() >= start and term.max() <= end


# ----------------------------------------------------------------- incidentes
def test_marketplace_so_existe_apos_a_aquisicao_de_2022(built):
    _, _, t = built
    mkt = t["fact_headcount_snapshot"].filter(pl.col("business_unit") == "Marketplace")
    if mkt.height:
        assert mkt["snapshot_date"].min() >= date(2022, 8, 1)


def test_aquisicoes_entram_como_populacao_e_nao_como_contratacao(built):
    _, _, t = built
    emp = t["dim_employee"].filter(pl.col("is_current"))
    origens = set(emp["origin"].unique().to_list())
    assert {"acquisition_vivamarket", "acquisition_comprafacil"} <= origens
    acq = set(emp.filter(pl.col("origin").str.starts_with("acquisition"))["employee_id"].to_list())
    contratados = set(t["fact_application"].filter(pl.col("employee_id").is_not_null())["employee_id"].to_list())
    assert not (acq & contratados)


def test_aprendizagem_so_apos_a_entrada_do_lms(built):
    cfg, _, t = built
    assert t["fact_learning"]["enrollment_date"].min() >= cfg.generation["learning"]["available_from"]


def test_escala_de_performance_muda_em_2021(built):
    _, _, t = built
    perf = t["fact_performance"]
    antes = perf.filter(pl.col("review_date") < date(2021, 1, 1))["scale_type"].unique().to_list()
    depois = perf.filter(pl.col("review_date") >= date(2021, 1, 1))["scale_type"].unique().to_list()
    assert antes == ["numeric"]
    assert depois == ["textual"]


def test_nao_respondente_nunca_tem_score_zero(built):
    _, _, t = built
    eng = t["fact_engagement"]
    nao = eng.filter(pl.col("response_flag") == 0)
    assert nao["engagement_score"].null_count() == nao.height


# -------------------------------------------------------------- plausibilidade
def test_turnover_realizado_proximo_do_configurado(built):
    cfg, _, t = built
    m = metrics.compute(cfg, t)
    for seg, v in m["turnover_by_segment"].items():
        alvo = v["configured_base_rate"]
        assert abs(v["realized_annual_rate"] - alvo) <= 0.12, (seg, v)


def test_piramide_de_niveis_nao_inverte(built):
    cfg, _, t = built
    m = metrics.compute(cfg, t)
    dist = m["level_distribution_final"]
    assert dist.get("IC1", 0) > dist.get("IC3", 0) > dist.get("M3", 0)


def test_headcount_cresce_ao_longo_da_serie(built):
    cfg, _, t = built
    m = metrics.compute(cfg, t)
    anos = sorted(m["headcount_by_year"])
    assert m["headcount_by_year"][anos[-1]]["eoy"] > m["headcount_by_year"][anos[0]]["eoy"] * 3


def test_promocao_sempre_sobe_de_nivel(built):
    cfg, _, t = built
    ranks = {lv: cfg.level_rank(lv) for lv in cfg.org["job_levels"]}
    prom = t["fact_movement"].filter(pl.col("movement_type") == "Promotion")
    for r in prom.select(["old_job_level", "new_job_level"]).to_dicts():
        assert ranks[r["new_job_level"]] > ranks[r["old_job_level"]]


def test_time_to_fill_maior_que_time_to_hire(built):
    """Time to Fill parte da abertura da requisicao e Time to Hire da
    candidatura, entao o primeiro e necessariamente maior. E o teste que
    protege o split do ADR-0005."""
    cfg, _, t = built
    m = metrics.compute(cfg, t)
    assert m["recruitment"]["time_to_fill_days_mean"] > m["recruitment"]["time_to_hire_days_mean"]
