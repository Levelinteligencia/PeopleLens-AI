"""Testes do pipeline da F3.

A pergunta central: o pipeline transformou apenas o que declarou ter
transformado, e preservou rastreabilidade de tudo.

Os testes rodam num diretorio temporario com o perfil `smoke`, para nao
sobrescrever os artefatos do perfil `dev` na raiz do projeto.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import polars as pl
import pytest

import pipeline
from generator import config, materialize, projection
from generator.events.lifecycle import World


@pytest.fixture(scope="session")
def executed(tmp_path_factory):
    root = tmp_path_factory.mktemp("peoplelens")
    src = Path(config.load().root)
    shutil.copytree(src / "config", root / "config")
    shutil.copytree(src / "data" / "reference", root / "data" / "reference")

    cfg = config.load(root)
    cfg.generation["reproducibility"]["active_profile"] = "smoke"
    truth = World(cfg).run()
    tables = materialize.build_all(cfg, truth)
    materialize.write(cfg, tables)
    projection.run(cfg, tables)

    antes = _raw_fingerprint(root)
    out = pipeline.run(cfg, write=True)
    depois = _raw_fingerprint(root)
    return cfg, out, antes, depois


def _raw_fingerprint(root: Path) -> dict[str, tuple[int, float]]:
    base = root / "data" / "raw"
    return {str(p.relative_to(base)): (p.stat().st_size, p.stat().st_mtime)
            for p in sorted(base.rglob("*")) if p.is_file()}


# --------------------------------------------------------------- imutabilidade
def test_raw_permanece_imutavel(executed):
    """Principio 1. Se o pipeline escrever no RAW, este teste quebra."""
    _, _, antes, depois = executed
    assert antes == depois and antes


# ------------------------------------------------------ nenhuma correcao silenciosa
def test_toda_diferenca_entre_staged_e_standardized_esta_no_lineage(executed):
    """A invariante mais importante da F3.

    Percorre valor a valor as colunas originais e exige que toda diferenca
    entre staged e standardized tenha entrada correspondente no
    transformation_log. Uma correcao sem registro reprova aqui.
    """
    _, out, _, _ = executed
    log = out["lineage"].frames()["transformation_log"]
    registrados = {(r["row_id"], r["field"]) for r in
                   log.filter(pl.col("layer") == "L1").select(["row_id", "field"]).to_dicts()}

    faltando = []
    for key, staged in out["frames"]["staged"].items():
        std = out["frames"]["standardized"][key]
        cols = [c for c in staged.columns if not c.startswith("_")]
        a = staged.select(["_row_id"] + cols).to_dicts()
        b = std.select(["_row_id"] + cols).to_dicts()
        for ra, rb in zip(a, b):
            for c in cols:
                if ra[c] != rb[c] and (ra["_row_id"], c) not in registrados:
                    faltando.append((ra["_row_id"], c, ra[c], rb[c]))
    assert not faltando, f"{len(faltando)} transformacoes sem registro: {faltando[:5]}"


def test_toda_coluna_padronizada_tem_regra_de_depara_registrada(executed):
    _, out, _, _ = executed
    log = out["lineage"].frames()["transformation_log"]
    l2 = log.filter(pl.col("layer") == "L2")
    assert l2.height > 0
    # toda entrada L2 aponta para um mapping_id aprovado ou para UNMAPPED
    regras = set(l2["rule_id"].unique().to_list())
    assert all(r.startswith("DEPARA:") for r in regras)


def test_lineage_de_valor_preserva_origem_e_regra(executed):
    _, out, _, _ = executed
    log = out["lineage"].frames()["transformation_log"]
    for col in ("layer", "source_system", "dataset", "row_id", "field", "original_value", "rule_id"):
        assert col in log.columns
    assert log["source_system"].null_count() == 0
    assert log["rule_id"].null_count() == 0


# ----------------------------------------------------------------- DE/PARA
def test_valor_desconhecido_nunca_e_corrigido_automaticamente(executed):
    """Principio 5: confianca alta melhora a sugestao, nao autoriza aplicar."""
    _, out, _, _ = executed
    exc = out["frames"]["exceptions"]
    if exc.is_empty():
        pytest.skip("nenhuma excecao nesta amostra")
    assert set(exc["status"].unique().to_list()) == {"OPEN"}
    assert exc["resolved_by"].null_count() == exc.height
    # existe sugestao de alta confianca e mesmo assim nada foi aplicado
    altas = exc.filter(pl.col("confidence_score") >= 0.8)
    if altas.height:
        assert set(altas["status"].unique().to_list()) == {"OPEN"}


def test_desconhecido_vira_unmapped_e_nao_nulo(executed):
    _, out, _, _ = executed
    achou = False
    for key, df in out["frames"]["conformed"].items():
        for c in df.columns:
            if c.startswith("std_") and not c.endswith("__mapping_id"):
                if df.filter(pl.col(c) == "UNMAPPED").height:
                    achou = True
    assert achou, "nenhum UNMAPPED encontrado; o DE/PARA nao esta sendo exercitado"


def test_excecao_registra_contagem_e_sugestao(executed):
    _, out, _, _ = executed
    exc = out["frames"]["exceptions"]
    if exc.is_empty():
        pytest.skip("nenhuma excecao nesta amostra")
    assert (exc["occurrence_count"] > 0).all()
    assert exc["source_value"].null_count() == 0


# --------------------------------------------------------------- identidade
def test_identidade_nunca_promove_match_ambiguo(executed):
    """ADR-0004: match por nome, mesmo unico, sai como MANUAL_REVIEW."""
    _, out, _, _ = executed
    x = out["frames"]["xref"]
    resolvidos = x.filter(pl.col("match_status") == "RESOLVED")
    assert set(resolvidos["match_method"].unique().to_list()) <= {"exact_id", "pattern_id"}
    fuzzy = x.filter(pl.col("match_method").is_in(["fuzzy_name", "name_hire_date"]))
    if fuzzy.height:
        assert set(fuzzy["match_status"].unique().to_list()) <= {"MANUAL_REVIEW", "AMBIGUOUS"}


def test_ambiguo_nao_recebe_employee_id(executed):
    _, out, _, _ = executed
    x = out["frames"]["xref"]
    amb = x.filter(pl.col("match_status") == "AMBIGUOUS")
    if amb.height:
        assert amb["employee_id"].null_count() == amb.height


# ---------------------------------------------------------------- qualidade
def test_todo_check_tem_severidade_e_dimensao_validas(executed):
    _, out, _, _ = executed
    dq = out["frames"]["dq"]
    assert set(dq["severity"].unique().to_list()) <= {"BLOCKER", "CRITICAL", "WARNING", "INFO"}
    assert set(dq["dimension"].unique().to_list()) <= {
        "Completeness", "Validity", "Consistency", "Uniqueness",
        "Referential Integrity", "Timeliness", "Reconciliation"}


def test_todas_as_sete_dimensoes_tem_pelo_menos_um_check(executed):
    _, out, _, _ = executed
    dims = set(out["frames"]["dq"]["dimension"].unique().to_list())
    assert dims == {"Completeness", "Validity", "Consistency", "Uniqueness",
                    "Referential Integrity", "Timeliness", "Reconciliation"}


def test_quarentena_recebe_apenas_reprovados_por_blocker(executed):
    _, out, _, _ = executed
    qua = out["frames"]["quarantine"]
    if qua.is_empty():
        pytest.skip("nenhuma quarentena nesta amostra")
    assert set(qua["severity"].unique().to_list()) == {"BLOCKER"}
    assert set(qua["resolution_status"].unique().to_list()) == {"OPEN"}


def test_quarentena_nao_apaga_o_registro_da_camada_conformada(executed):
    """Desvio lateral, nao filtro destrutivo (ADR-0003)."""
    _, out, _, _ = executed
    qua = out["frames"]["quarantine"]
    if qua.is_empty():
        pytest.skip("nenhuma quarentena nesta amostra")
    for r in qua.head(20).to_dicts():
        conf = out["frames"]["conformed"][(r["source_system"], r["dataset"])]
        assert conf.filter(pl.col("_row_id") == r["record_id"]).height == 1
        ana = out["frames"]["analytical"][(r["source_system"], r["dataset"])]
        assert ana.filter(pl.col("_row_id") == r["record_id"]).height == 0


# ------------------------------------------------------------------ lineage
def test_lineage_cobre_todas_as_camadas(executed):
    _, out, _, _ = executed
    obj = out["lineage"].frames()["data_lineage"]
    nomes = " ".join(obj["object_name"].to_list())
    for camada in ("staged.", "profiling.", "standardized.", "conformed.", "data_quality_results",
                   "data_quarantine", "conformed_approved"):
        assert camada in nomes, camada


# ---------------------------------------------------------------- proveniencia
def test_check_provenance_detecta_divergencia(tmp_path):
    """ADR-0018, regra 1: a comparacao so vale se os dois lados vierem da mesma
    execucao."""
    import json
    from types import SimpleNamespace

    for rel, mf in (("data/raw", {"seed": 42, "profile": "smoke", "scale": 0.02}),
                    ("data/synthetic/truth", {"seed": 42, "profile": "dev", "scale": 0.1})):
        d = tmp_path / rel
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps(mf), encoding="utf-8")

    r = pipeline.check_provenance(SimpleNamespace(root=tmp_path))
    assert r["status"] == "DIVERGENTE"
    assert set(r["divergencias"]) == {"profile", "scale"}


def test_pipeline_bloqueia_comparacao_com_proveniencia_divergente(executed):
    """ADR-0018, regra 2: divergiu, a comparacao nao roda e o relatorio diz por
    que, em vez de exibir numeros invalidos."""
    import json

    cfg, _, _, _ = executed
    mf = Path(cfg.root) / "data" / "raw" / "manifest.json"
    original = mf.read_text(encoding="utf-8")
    try:
        d = json.loads(original)
        d["profile"] = "um-perfil-que-nao-e-o-da-verdade"
        mf.write_text(json.dumps(d), encoding="utf-8")
        out = pipeline.run(cfg, write=False)
        assert out["resumo"]["proveniencia"]["status"] == "DIVERGENTE"
        assert "erro" in out["resumo"]["comparacao_verdade"]
        assert "taxa_recuperacao" not in str(out["resumo"]["comparacao_verdade"])
    finally:
        mf.write_text(original, encoding="utf-8")


# ------------------------------------------------------------- reprodutibilidade
def test_pipeline_e_deterministico(executed):
    cfg, out, _, _ = executed
    de_novo = pipeline.run(cfg, write=False)
    a, b = out["resumo"], de_novo["resumo"]
    assert a["linhas_por_camada"] == b["linhas_por_camada"]
    assert a["depara"] == b["depara"]
    assert a["qualidade"]["fail"] == b["qualidade"]["fail"]
