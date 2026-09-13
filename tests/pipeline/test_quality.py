"""Testes da camada de qualidade e do trust score (F5).

Duas perguntas governam este arquivo.

A primeira e a que a Sam pediu explicitamente: **a camada de DQ altera o dado?**
A resposta tem que ser nao, e nao por convencao: `test_runner_nao_altera_nenhuma_frame`
compara as frames valor a valor antes e depois da execucao do catalogo.

A segunda e a distincao que a F5 existe para preservar:

    dado invalido != dado nao mapeado != decisao pendente
                  != identidade nao resolvida != dado quarentenado

Cada uma dessas desigualdades tem um teste. Elas parecem obvias escritas assim,
e sao exatamente as que um pipeline apaga sem querer: basta tratar tudo que
reprova como erro, e uma fila de decisao vira um defeito de dado.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import polars as pl
import pytest
import yaml

import pipeline
from analytics import contracts, trust
from generator import config, materialize, projection
from generator.events.lifecycle import World
from quality import runner


@pytest.fixture(scope="module")
def executado(tmp_path_factory):
    root = tmp_path_factory.mktemp("dq")
    src = Path(config.load().root)
    shutil.copytree(src / "config", root / "config")
    shutil.copytree(src / "data" / "reference", root / "data" / "reference")

    cfg = config.load(root)
    cfg.generation["reproducibility"]["active_profile"] = "smoke"
    tables = materialize.build_all(cfg, World(cfg).run())
    materialize.write(cfg, tables)
    projection.run(cfg, tables)
    out = pipeline.run(cfg, write=False)
    return cfg, out


@pytest.fixture(scope="module")
def catalogo(executado):
    cfg, _ = executado
    return runner.load_checks(cfg)


def _hash(df: pl.DataFrame) -> str:
    return hashlib.sha256(df.write_ipc(None).getbuffer()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# 1. DQ nao altera o dado
# --------------------------------------------------------------------------- #
def test_runner_nao_altera_nenhuma_frame(executado):
    """O teste central da F5.

    Um runner que corrige dado ao medir destroi a evidencia do problema, e o
    relatorio passa a descrever um dataset que nao existe em lugar nenhum.
    """
    cfg, out = executado
    frames = out["frames"]["conformed"]
    antes = {k: _hash(v) for k, v in frames.items()}

    class Mudo:
        def object(self, *a, **k):
            pass

    runner.run_all(cfg, frames, Mudo(), xref=out["frames"]["xref"])
    depois = {k: _hash(v) for k, v in frames.items()}
    assert antes == depois and antes


def test_trust_score_nao_altera_nenhuma_frame(executado):
    cfg, out = executado
    frames = out["frames"]["conformed"]
    antes = {k: _hash(v) for k, v in frames.items()}
    trust.compute(cfg, frames, out["frames"]["xref"])
    assert {k: _hash(v) for k, v in frames.items()} == antes


def test_quarentena_e_desvio_lateral_e_nao_filtro_destrutivo(executado):
    """ADR-0003. A linha reprovada sai do analitico e continua intacta na
    camada conformada, com a regra que a reprovou anexada."""
    _, out = executado
    qua = out["frames"]["quarantine"]
    if qua.is_empty():
        pytest.skip("quarentena vazia nesta amostra")
    for r in qua.head(20).to_dicts():
        conf = out["frames"]["conformed"][(r["source_system"], r["dataset"])]
        assert conf.filter(pl.col("_row_id") == r["record_id"]).height == 1
        ana = out["frames"]["analytical"][(r["source_system"], r["dataset"])]
        assert ana.filter(pl.col("_row_id") == r["record_id"]).height == 0
        assert r["failed_rule"] and r["finding_class"]


# --------------------------------------------------------------------------- #
# 2. As cinco distincoes
# --------------------------------------------------------------------------- #
def test_toda_classe_de_achado_e_declarada_e_conhecida(catalogo):
    declaradas = set(catalogo["finding_classes"])
    assert declaradas >= set(runner.FINDING_CLASSES)
    for c in catalogo["checks"]:
        assert c.get("finding_class") in declaradas, c["check_id"]


def test_pendencia_nunca_manda_registro_para_a_quarentena(catalogo, executado):
    """A desigualdade mais importante: **decisao pendente != dado quarentenado**.

    Tirar do analitico uma linha cujo unico problema e um mapeamento ainda nao
    aprovado apagaria dado que esta certo na origem, por causa de uma fila de
    trabalho. Quem decide o destino da linha e a severidade; classe de pendencia
    nunca pode ser BLOCKER.
    """
    pendentes = [c["check_id"] for c in catalogo["checks"]
                 if c["finding_class"] in runner.PENDENCY_CLASSES
                 and c["severity"] == "BLOCKER"]
    assert not pendentes, f"checks de pendencia com severidade BLOCKER: {pendentes}"

    _, out = executado
    qua = out["frames"]["quarantine"]
    if not qua.is_empty():
        assert set(qua["finding_class"].unique().to_list()).isdisjoint(runner.PENDENCY_CLASSES)
        assert set(qua["severity"].unique().to_list()) == {"BLOCKER"}


def test_nao_mapeado_e_decisao_pendente_sao_classes_distintas(catalogo):
    """`Mktg` sem mapeamento e uma fila de trabalho. `N4` da VivaMarket e uma
    pergunta sem resposta tecnica. As duas viram UNMAPPED e nao sao a mesma
    coisa: a primeira alguem resolve, a segunda alguem decide."""
    por_id = {c["check_id"]: c for c in catalogo["checks"]}
    assert por_id["DQ_VALID_006"]["finding_class"] == "DECISAO_PENDENTE"
    assert por_id["DQ_CONS_001"]["finding_class"] == "NAO_MAPEADO"


def test_identidade_nao_resolvida_nao_e_dado_invalido(catalogo):
    ident = [c for c in catalogo["checks"]
             if c["expectation"] == "expect_identity_resolved"]
    assert ident, "nenhum check de cobertura de identidade no catalogo"
    for c in ident:
        assert c["finding_class"] == "IDENTIDADE_NAO_RESOLVIDA", c["check_id"]


def test_ausencia_legitima_nunca_penaliza_a_confianca(executado, catalogo):
    """Nao declarar raca, cor ou deficiencia e opcao da pessoa. Penalizar a
    confianca por isso transformaria o trust score em pressao por preenchimento."""
    assert any(c["finding_class"] == "AUSENCIA_LEGITIMA" for c in catalogo["checks"])
    _, out = executado
    for linha in out["frames"]["trust"].to_dicts():
        assert "AUSENCIA_LEGITIMA" not in (linha["perda_por_classe"] or {})


# --------------------------------------------------------------------------- #
# 3. Catalogo bem formado
# --------------------------------------------------------------------------- #
def test_toda_expectativa_declarada_existe_no_runner(catalogo, executado):
    """Expectativa com nome errado no YAML tem que estourar, nao passar em
    silencio."""
    cfg, out = executado
    frames = out["frames"]["conformed"]
    for c in catalogo["checks"]:
        spec = dict(c)
        df = frames.get(runner._key(c["dataset"]))
        if df is None:
            continue
        runner._failing_rows(spec, df, frames)   # ValueError se desconhecida


def test_nenhum_check_do_catalogo_fica_sem_rodar(executado):
    """NOT_RUN e legitimo como estado, e nao pode virar rotina: um catalogo com
    checks que nunca rodam parece cobertura e nao e."""
    _, out = executado
    dq = out["frames"]["dq"]
    nao_rodaram = dq.filter(pl.col("status") == "NOT_RUN")["check_id"].to_list()
    assert not nao_rodaram, f"checks sem execucao: {nao_rodaram}"


def test_check_sobre_coluna_inexistente_vira_not_run_e_nunca_pass(executado):
    """Erro de digitacao no nome da coluna nao pode virar check aprovado."""
    cfg, out = executado
    frames = out["frames"]["conformed"]
    spec = {"check_id": "X", "expectation": "expect_column_values_to_not_be_null",
            "column": "coluna_que_nao_existe", "threshold": {"max_failure_rate": 0.0}}
    df = frames[("HRIS_CORE", "employee_master")]
    falhas, avaliados = runner._failing_rows(spec, df, frames)
    assert avaliados == 0   # o runner traduz isso em NOT_RUN, nao em PASS


def test_todo_check_declara_severidade_dimensao_e_base_de_limiar(catalogo):
    for c in catalogo["checks"]:
        assert c["severity"] in ("BLOCKER", "CRITICAL", "WARNING", "INFO"), c["check_id"]
        assert c["dimension"] in ("Completeness", "Validity", "Consistency", "Uniqueness",
                                  "Referential Integrity", "Timeliness", "Reconciliation")
        assert c.get("threshold_basis") in ("invariante", "derivado", "provisional"), c["check_id"]


def test_todas_as_sete_dimensoes_tem_cobertura(executado):
    _, out = executado
    dims = set(out["frames"]["dq"]["dimension"].unique().to_list())
    assert dims == {"Completeness", "Validity", "Consistency", "Uniqueness",
                    "Referential Integrity", "Timeliness", "Reconciliation"}


def test_catalogo_cobre_todos_os_sistemas_da_onda_1(catalogo, executado):
    cfg, _ = executado
    onda1 = set(cfg.sources["waves"][1]["systems"])
    cobertos = {c["dataset"].split(".")[0] for c in catalogo["checks"]}
    assert onda1 <= cobertos, f"sistemas da onda 1 sem check: {onda1 - cobertos}"


# --------------------------------------------------------------------------- #
# 4. Contratos de KPI (ADR-0011)
# --------------------------------------------------------------------------- #
def test_nenhum_check_orfao(executado):
    """ADR-0011: check que nao alimenta KPI nenhum apodrece em silencio."""
    cfg, _ = executado
    orfaos = [p for p in contracts.verify(cfg) if "orfao" in p]
    assert not orfaos, orfaos


def test_contrato_de_kpi_bate_com_o_catalogo(executado):
    cfg, _ = executado
    assert contracts.verify(cfg) == []


def test_contrato_declara_mapeamentos_e_n_minimo(executado):
    cfg, _ = executado
    for kpi, doc in contracts.load(cfg).items():
        assert doc["depends_on_mappings"], kpi
        assert doc["minimum_n"] >= 5, kpi
        assert doc["response_levels"]["CAUSALIDADE"].startswith("negado"), kpi


# --------------------------------------------------------------------------- #
# 5. Trust score
# --------------------------------------------------------------------------- #
def test_warning_e_info_nao_entram_no_trust_score(catalogo, executado):
    """ADR-0010: so BLOCKER e CRITICAL pesam."""
    _, out = executado
    por_id = {c["check_id"]: c for c in catalogo["checks"]}
    frames = out["frames"]["conformed"]
    cfg, _ = executado

    leves = {cid for cid, c in por_id.items() if c["severity"] in ("WARNING", "INFO")}
    cut = {k: {} for k in frames}
    resultados = runner.run_for_cut(cfg, frames, cut, xref=out["frames"]["xref"])
    so_leves = {cid: r for cid, r in resultados.items() if cid in leves}
    atrib = runner and trust._atribuicao(por_id, so_leves)
    assert atrib["perda_total"] is None, "check WARNING ou INFO influenciou o score"


def test_sem_check_aplicavel_nao_vira_certified(executado):
    """Ausencia de evidencia nao e evidencia de qualidade."""
    _, out = executado
    t = out["frames"]["trust"]
    sem = t.filter(pl.col("checks_avaliados") == 0)
    if sem.is_empty():
        pytest.skip("todos os pares tiveram check aplicavel")
    assert set(sem["trust_status"].unique().to_list()) == {"INDETERMINADO"}
    assert sem["trust_score"].null_count() == sem.height


def test_perda_por_classe_soma_a_perda_total(executado):
    """A atribuicao e exata: as contribuicoes por classe somam a perda medida.
    Sem isso o 'porque' do score seria decorativo."""
    _, out = executado
    for r in out["frames"]["trust"].to_dicts():
        if r["trust_score"] is None:
            continue
        # polars completa o struct com None nas classes que aquela linha nao
        # avaliou; None ali e "nao medido", nao zero
        soma = sum(v for v in (r["perda_por_classe"] or {}).values() if v is not None)
        # tolerancia acomoda o arredondamento para 6 casas de cada parcela
        tol = 1e-6 * (len(r["perda_por_classe"] or {}) + 2)
        assert abs(soma - (1 - r["trust_score"])) < tol, r["kpi"]
        assert abs((r["perda_por_erro"] + r["perda_por_pendencia"]) - soma) < tol


def test_perda_por_erro_e_perda_por_pendencia_nao_se_misturam(executado):
    """A populacao da aquisicao nao tem dado errado: tem decisao e vinculo
    pendentes. O score tem que dizer isso, nao so que a confianca caiu."""
    _, out = executado
    t = out["frames"]["trust"]
    viva = t.filter((pl.col("recorte") == "origem=VIVAMARKET_LEGACY")
                    & (pl.col("kpi") == "headcount"))
    if viva.is_empty():
        pytest.skip("recorte da aquisicao ausente nesta amostra")
    r = viva.to_dicts()[0]
    assert r["perda_por_erro"] == 0.0
    assert r["perda_por_pendencia"] > 0.0
    assert r["motivo"] == "PENDENCIA"


def test_pendencia_pura_nao_derruba_para_blocked_acima_do_piso(executado):
    """Regra do ADR-0022. Nao estar resolvido nao e o mesmo que estar errado."""
    _, out = executado
    for r in out["frames"]["trust"].to_dicts():
        if r["trust_score"] is None:
            continue
        pendencia_pura = r["perda_por_erro"] == 0.0
        if pendencia_pura and r["trust_score"] >= trust.PISO_PENDENCIA:
            assert r["trust_status"] != "BLOCKED", (r["kpi"], r["recorte"], r["trust_score"])


def test_supressao_por_n_minimo_e_privacidade_e_nao_qualidade(executado):
    """Duas recusas diferentes precisam continuar diferentes: 'o grupo e pequeno
    demais para preservar anonimato' (ADR-0007) nao e 'nao confio no dado'."""
    _, out = executado
    t = out["frames"]["trust"]
    assert "suprimido_por_n_minimo" in t.columns
    assert "trust_status" in t.columns
    suprimidos = t.filter(pl.col("suprimido_por_n_minimo"))
    if not suprimidos.is_empty():
        # supressao nao muda o score; ela muda se a resposta sai
        assert suprimidos["trust_score"].null_count() < suprimidos.height


def test_trust_score_entre_zero_e_um(executado):
    _, out = executado
    t = out["frames"]["trust"].filter(pl.col("trust_score").is_not_null())
    assert (t["trust_score"] >= 0.0).all() and (t["trust_score"] <= 1.0).all()


# --------------------------------------------------------------------------- #
# 6. Reconciliacao
# --------------------------------------------------------------------------- #
def test_reconciliacao_entre_sistemas_iguala_o_escopo(catalogo):
    """Achado 1 da F5: reconciliar duas fontes com vigencia e populacao
    diferentes mede a diferenca de escopo, nao a diferenca de dado."""
    por_id = {c["check_id"]: c for c in catalogo["checks"]}
    for cid in ("DQ_RECON_001", "DQ_RECON_002"):
        c = por_id[cid]
        assert c.get("filter"), f"{cid} compara HRIS de cinco paises com folha do Brasil"
    assert por_id["DQ_RECON_001"].get("reference_filter"), \
        "a comparacao agregada precisa recortar a janela de sobreposicao"


def test_reconciliacao_mes_a_mes_so_compara_periodo_que_existe_dos_dois_lados(executado):
    cfg, out = executado
    frames = out["frames"]["conformed"]
    spec = {"expectation": "expect_group_count_ratio_between",
            "group_column": "snapshot_date__iso",
            "reference_dataset": "PAYROLL_BR.payroll_headcount_snapshot",
            "reference_group_column": "dt_competencia__iso",
            "min_ratio": 0.0, "max_ratio": 99.0}
    _, meses = runner._failing_rows(spec, frames[("HRIS_CORE", "headcount_snapshot")], frames)
    hc = frames[("HRIS_CORE", "headcount_snapshot")]["snapshot_date__iso"].drop_nulls()
    pb = frames[("PAYROLL_BR", "payroll_headcount_snapshot")]["dt_competencia__iso"].drop_nulls()
    comuns = {d[:7] for d in hc.to_list()} & {d[:7] for d in pb.to_list()}
    assert meses == len(comuns)


def test_identidade_com_chave_incompativel_nao_vira_cem_por_cento(executado):
    """Achado 2 da F5: apontar o check de identidade para a coluna errada
    produzia 100% de nao resolvido, numero plausivel para um sistema de
    identidade fraca e por isso dificil de questionar."""
    cfg, out = executado
    frames = runner._expose_identity(out["frames"]["conformed"], out["frames"]["xref"])
    spec = {"expectation": "expect_identity_resolved", "column": "candidate_name",
            "identity_system": "ATS_CLOUD"}
    _, avaliados = runner._failing_rows(spec, frames[("ATS_CLOUD", "application")], frames)
    assert avaliados == 0, "chave incompativel deveria virar NOT_RUN, nao 100% de falha"


# --------------------------------------------------------------------------- #
# 7. Criterio de saida da calibragem
# --------------------------------------------------------------------------- #
def test_quarentena_nao_vazia_e_abaixo_de_tres_por_cento(executado):
    """`calibration.exit_criteria` em defects.yaml."""
    _, out = executado
    total = out["resumo"]["linhas_por_camada"]["conformed"]
    q = out["resumo"]["qualidade"]["quarentena"]
    assert q > 0, "quarentena vazia e quarentena decorativa"
    assert q / total < 0.03, f"{q / total:.2%} do volume em quarentena"
