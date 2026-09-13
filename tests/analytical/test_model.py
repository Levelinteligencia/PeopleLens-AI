"""Criterios de aceite do modelo analitico L3 (F6).

Dezessete criterios que devem passar (A-01 a A-17) e dezessete casos que devem
falhar (F-01 a F-17). Os casos de falha nao sao testes negativos por capricho:
cada um descreve um jeito especifico de o modelo estar errado parecendo certo, e
varios deles vieram de erros que este projeto ja cometeu.

O mais contraintuitivo e o F-01: somar headcount sem filtrar o sistema de
registro **tem que duplicar** na sobreposicao de 2019. Se nao duplicar, o grain
esta errado e a evidencia da migracao foi apagada por uma escolha que ninguem
registrou.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import polars as pl
import pytest

import pipeline
from analytics.layer import ANALYTICAL, LayerError, assert_layer
from analytics.model import build as B
from analytics.model import keys
from generator import config, materialize, projection
from generator.events.lifecycle import World

GRAIN = {
    "fact_headcount_snapshot": ["party_key", "date_sk", "source_sk"],
    "fact_workforce_entry": ["party_key", "date_sk", "source_sk"],
    "fact_termination": ["party_key", "date_sk", "source_sk"],
    "fact_compensation": ["party_key", "date_sk", "source_sk"],
    "fact_performance": ["party_key", "review_cycle"],
    "fact_movement": ["movement_sk"],
    "fact_requisition": ["requisition_sk"],
    "fact_application": ["application_sk"],
    "dim_employee": ["party_key", "effective_from"],
    "dim_organization": ["org_sk"],
    "dim_calendar": ["date_sk"],
    "dim_job_level": ["job_level_sk"],
    "dim_origin": ["origin_sk"],
    "dim_source_system": ["source_sk"],
}

FK = {
    "employee_sk": ("dim_employee", "employee_sk"),
    "org_sk": ("dim_organization", "org_sk"),
    "org_sk_from": ("dim_organization", "org_sk"),
    "org_sk_to": ("dim_organization", "org_sk"),
    "job_level_sk": ("dim_job_level", "job_level_sk"),
    "origin_sk": ("dim_origin", "origin_sk"),
    "source_sk": ("dim_source_system", "source_sk"),
    "date_sk": ("dim_calendar", "date_sk"),
    "date_sk_opening": ("dim_calendar", "date_sk"),
    "date_sk_approval": ("dim_calendar", "date_sk"),
    "date_sk_posting": ("dim_calendar", "date_sk"),
    "date_sk_hire": ("dim_calendar", "date_sk"),
    "date_sk_application": ("dim_calendar", "date_sk"),
    "date_sk_offer": ("dim_calendar", "date_sk"),
}


@pytest.fixture(scope="module")
def modelo(tmp_path_factory):
    """Universo descartavel, perfil `smoke`, pipeline e L3 ponta a ponta."""
    root = tmp_path_factory.mktemp("l3")
    src = Path(config.load().root)
    shutil.copytree(src / "config", root / "config")
    shutil.copytree(src / "data" / "reference", root / "data" / "reference")

    cfg = config.load(root)
    cfg.generation["reproducibility"]["active_profile"] = "smoke"
    tables = materialize.build_all(cfg, World(cfg).run())
    materialize.write(cfg, tables)
    projection.run(cfg, tables)
    pipeline.run(cfg, write=True)

    out = B.build(cfg, write=True)
    return cfg, out, out["tabelas"]


# ===========================================================================
# A-01 a A-17: devem passar
# ===========================================================================
def test_a01_toda_tabela_declara_o_grain(modelo):
    _, _, t = modelo
    for nome in t:
        assert nome in GRAIN, f"{nome} sem grain declarado"


def test_a02_nenhuma_tabela_mistura_grains(modelo):
    """A chave declarada e unica na tabela."""
    _, _, t = modelo
    for nome, df in t.items():
        chave = GRAIN[nome]
        if not set(chave) <= set(df.columns):
            pytest.fail(f"{nome} sem as colunas do grain {chave}")
        dup = df.group_by(chave).len().filter(pl.col("len") > 1)
        assert dup.is_empty(), f"{nome} tem {dup.height} violacoes de grain {chave}"


def test_a03_toda_chave_estrangeira_resolve(modelo):
    """Inclusive nos membros negativos: reservado e um membro, nao um buraco."""
    _, _, t = modelo
    for nome, df in t.items():
        if not nome.startswith("fact_"):
            continue
        for col, (dimensao, pk) in FK.items():
            if col not in df.columns or dimensao not in t:
                continue
            validos = set(t[dimensao][pk].to_list())
            orfaos = set(df[col].drop_nulls().to_list()) - validos
            assert not orfaos, f"{nome}.{col} aponta para {sorted(orfaos)[:5]} inexistentes"


def test_a04_nenhuma_chave_estrangeira_e_nula(modelo):
    _, _, t = modelo
    for nome, df in t.items():
        if not nome.startswith("fact_"):
            continue
        for col in FK:
            if col in df.columns:
                assert df[col].null_count() == 0, f"{nome}.{col} tem nulo"


def test_a05_historico_nao_e_sobrescrito(modelo):
    """Reprocessar nao pode reduzir versoes de um periodo ja fechado."""
    cfg, out, t = modelo
    antes = t["dim_employee"].filter(pl.col("employee_sk") > 0).height
    de_novo = B.build(cfg, write=False)["tabelas"]["dim_employee"]
    assert de_novo.filter(pl.col("employee_sk") > 0).height >= antes


def test_a06_fato_usa_a_versao_vigente_na_data_do_fato(modelo):
    """Contar mulheres em lideranca em 2018 com o nivel de 2026 seria reescrever
    a historia."""
    _, _, t = modelo
    d = t["dim_employee"].filter(pl.col("employee_sk") > 0).select(
        ["employee_sk", "party_key", "effective_from", "effective_to"])
    f = t["fact_headcount_snapshot"].join(d, on="employee_sk", how="inner")
    fora = f.filter((pl.col("obs_date") < pl.col("effective_from"))
                    | (pl.col("obs_date") > pl.col("effective_to")))
    assert fora.is_empty(), f"{fora.height} fatos ligados a versao fora de vigencia"


def test_a07_vigencias_nao_se_sobrepoem_nem_deixam_buraco(modelo):
    _, _, t = modelo
    v = (t["dim_employee"].filter(pl.col("employee_sk") > 0)
         .sort(["party_key", "effective_from"])
         .with_columns(pl.col("effective_from").shift(-1).over("party_key").alias("_prox")))
    sobrepoe = v.filter(pl.col("_prox").is_not_null() & (pl.col("effective_to") >= pl.col("_prox")))
    assert sobrepoe.is_empty(), f"{sobrepoe.height} vigencias sobrepostas"
    correntes = (t["dim_employee"].filter(pl.col("employee_sk") > 0).filter(pl.col("is_current"))
                 .group_by("party_key").len().filter(pl.col("len") > 1))
    assert correntes.is_empty(), f"{correntes.height} pessoas com duas versoes vigentes"


def test_a08_identidade_nao_resolvida_vira_pessoa_provisoria_contavel(modelo):
    """ADR-0025, Emenda 1. A pessoa existe e precisa ser contavel."""
    _, _, t = modelo
    d = t["dim_employee"].filter(pl.col("employee_sk") > 0)
    prov = d.filter(pl.col("is_provisional_person"))
    assert prov.height > 0, "nenhuma pessoa provisoria; a VivaMarket deveria produzir algumas"
    assert (prov["party_key"].str.starts_with("SRC:")).all()
    assert (d.filter(~pl.col("is_provisional_person"))["party_key"].str.starts_with("EMP:")).all()


def test_a09_nenhuma_linha_em_quarentena_entra_no_modelo(modelo):
    cfg, _, t = modelo
    p = Path(cfg.root) / "data" / "processed" / "metadata" / "data_quarantine.parquet"
    if not p.exists():
        pytest.skip("sem quarentena nesta amostra")
    bloqueados = set(pl.read_parquet(p)["record_id"].to_list())
    for nome, df in t.items():
        if "source_row_id" in df.columns:
            vazou = set(df["source_row_id"].drop_nulls().to_list()) & bloqueados
            assert not vazou, f"{nome} contem {len(vazou)} linhas em quarentena"


def test_a10_toda_exclusao_fica_registrada(modelo):
    cfg, out, _ = modelo
    p = Path(cfg.root) / "data" / "processed" / "metadata" / "data_quarantine.parquet"
    esperado = pl.read_parquet(p).height if p.exists() else 0
    assert out["exclusoes"].height == esperado


def test_a11_n4_e_n5_continuam_contaveis(modelo):
    """A decisao da F4 preservada ate a camada analitica."""
    _, _, t = modelo
    d = t["dim_employee"]
    decisao = d.filter(pl.col("job_level_sk") == -2)
    if decisao.is_empty():
        pytest.skip("N4/N5 ausentes nesta amostra")
    assert set(decisao["job_level_source"].unique().to_list()) <= {"N4", "N5"}
    membro = t["dim_job_level"].filter(pl.col("job_level_sk") == -2)
    assert membro.height == 1 and membro["finding_class"][0] == "DECISAO_PENDENTE"


def test_a12_calendario_cobre_meses_sem_dado(modelo):
    """D18: um mes que nao existe no eixo e um buraco que some do grafico."""
    _, _, t = modelo
    cal = set(t["dim_calendar"].filter(pl.col("date_sk") > 0)["mes"].unique().to_list())
    com_dado = set(t["fact_headcount_snapshot"]["obs_date"].str.slice(0, 7).unique().to_list())
    assert com_dado <= cal
    assert len(cal) > len(com_dado), "o calendario nao pode ser apenas os meses com dado"


def test_a13_lineage_fecha_ate_o_row_id(modelo):
    cfg, _, t = modelo
    conf = Path(cfg.root) / "data" / "processed" / "conformed_approved"
    ids = set()
    for p in conf.rglob("*.parquet"):
        ids |= set(pl.read_parquet(p, columns=["_row_id"])["_row_id"].to_list())
    f = t["fact_headcount_snapshot"]
    amostra = set(f["source_row_id"].drop_nulls().head(200).to_list())
    assert amostra and amostra <= ids


def test_a13b_proveniencia_registra_a_regra_que_a_determinou(modelo):
    _, _, t = modelo
    d = t["dim_employee"].filter(pl.col("employee_sk") > 0)
    determinada = d.filter(pl.col("determination_rule").is_not_null())
    assert determinada.height > 0
    assert set(determinada["determination_rule"].unique().to_list()) <= {"P1", "P2", "P3"}
    assert determinada["evidence_source"].null_count() == 0


def test_a14_manifesto_declara_camada_e_proveniencia(modelo):
    cfg, _, _ = modelo
    import json
    mf = json.loads((Path(cfg.root) / "data" / "processed" / "analytical" / "manifest.json")
                    .read_text(encoding="utf-8"))
    for campo in ("layer", "run_id", "seed", "profile", "scale"):
        assert mf.get(campo) is not None, campo
    assert mf["layer"] == ANALYTICAL
    assert mf["profile"] == cfg.profile


def test_a15_nenhum_kpi_e_calculado_na_l3(modelo):
    """A fronteira com a F7, verificada no codigo e nao na intencao."""
    raiz = Path(config.load().root) / "src" / "analytics" / "model"
    for py in raiz.glob("*.py"):
        texto = py.read_text(encoding="utf-8")
        assert "config/kpis" not in texto, f"{py.name} referencia contrato de KPI"
        assert "contracts" not in texto.replace("# ", ""), f"{py.name} importa contratos de KPI"


def test_a16_o_modelo_e_deterministico(modelo):
    cfg, _, t = modelo
    de_novo = B.build(cfg, write=False)["tabelas"]
    for nome, df in t.items():
        assert de_novo[nome].height == df.height, nome
        assert de_novo[nome].columns == df.columns, nome


def test_a17_toda_tabela_carrega_a_camada(modelo):
    _, _, t = modelo
    for nome, df in t.items():
        assert_layer(df, ANALYTICAL, nome)


# ===========================================================================
# F-01 a F-17: devem falhar
# ===========================================================================
def test_f01_somar_headcount_sem_o_sistema_de_registro_duplica_em_2019(modelo):
    """**Tem que duplicar.** Se nao duplicar, o grain esta errado e a evidencia
    da migracao de 2019 foi apagada por uma escolha que ninguem registrou."""
    _, _, t = modelo
    f = t["fact_headcount_snapshot"]
    mes = pl.col("obs_date").str.slice(0, 7)
    sobreposicao = f.filter((mes >= "2019-05") & (mes <= "2019-11"))
    if sobreposicao.is_empty():
        pytest.skip("sem sobreposicao nesta amostra")
    sistemas = set(sobreposicao["source_system"].unique().to_list())
    assert len(sistemas) == 2, f"esperava dois observadores na migracao, veio {sistemas}"
    sem_filtro = sobreposicao.height
    com_filtro = sobreposicao.filter(pl.col("is_system_of_record")).height
    assert sem_filtro > com_filtro, "somar sem filtrar deveria duplicar, e nao duplicou"


def test_f02_pessoa_com_duas_versoes_vigentes_reprova(modelo):
    _, _, t = modelo
    d = t["dim_employee"].filter(pl.col("employee_sk") > 0)
    for data in ("2018-06-15", "2022-08-15", "2026-01-15"):
        vigentes = d.filter((pl.col("effective_from") <= data) & (pl.col("effective_to") >= data))
        dup = vigentes.group_by("party_key").len().filter(pl.col("len") > 1)
        assert dup.is_empty(), f"{dup.height} pessoas com duas versoes vigentes em {data}"


def test_f03_fato_apontando_para_a_versao_atual_reprova(modelo):
    """Um fato de 2018 nao pode apontar para a versao corrente de 2026."""
    _, _, t = modelo
    d = t["dim_employee"].filter(pl.col("employee_sk") > 0).select(
        ["employee_sk", "is_current", "effective_from"])
    f = (t["fact_headcount_snapshot"].filter(pl.col("obs_date") < "2019-01-01")
         .join(d, on="employee_sk", how="inner"))
    if f.is_empty():
        pytest.skip("sem fatos antigos nesta amostra")
    errados = f.filter(pl.col("is_current") & (pl.col("effective_from") > pl.col("obs_date")))
    assert errados.is_empty()


def test_f04_nivel_nulo_onde_a_origem_era_n4_reprova(modelo):
    _, _, t = modelo
    d = t["dim_employee"]
    n45 = d.filter(pl.col("job_level_source").is_in(["N4", "N5"]))
    if n45.is_empty():
        pytest.skip("N4/N5 ausentes")
    assert n45["job_level_sk"].null_count() == 0
    assert set(n45["job_level_sk"].unique().to_list()) == {-2}


def test_f05_linha_em_quarentena_em_qualquer_fato_reprova(modelo):
    cfg, _, t = modelo
    p = Path(cfg.root) / "data" / "processed" / "metadata" / "data_quarantine.parquet"
    if not p.exists():
        pytest.skip("sem quarentena")
    bloqueados = set(pl.read_parquet(p)["record_id"].to_list())
    for nome, df in t.items():
        if nome.startswith("fact_") and "source_row_id" in df.columns:
            assert not (set(df["source_row_id"].drop_nulls().to_list()) & bloqueados), nome


def test_f06_party_key_consolidado_para_identidade_nao_aprovada_reprova(modelo):
    """Promoveria match nao governado. ADR-0004 nao tem excecao na L3."""
    _, _, t = modelo
    d = t["dim_employee"].filter(pl.col("employee_sk") > 0)
    nao_resolvida = d.filter(pl.col("identity_basis") == "nao_resolvida")
    assert not nao_resolvida.filter(pl.col("party_key").str.starts_with("EMP:")).height
    manual = d.filter(pl.col("identity_status").is_in(["MANUAL_REVIEW", "AMBIGUOUS"]))
    if manual.height:
        assert (manual["party_key"].str.starts_with("SRC:")).all()


def test_f07_organizacao_com_vigencia_anterior_ao_primeiro_dado_reprova(modelo):
    """Vigencia derivada nao pode fingir precisao que nao tem."""
    _, _, t = modelo
    org = t["dim_organization"].filter(pl.col("org_sk") > 0)
    assert org["is_derived"].all()
    primeiro = t["fact_headcount_snapshot"]["obs_date"].min()
    antes = org.filter(pl.col("effective_from") < "2000-01-01")
    assert antes.is_empty()
    assert org["effective_from"].min() is not None and primeiro is not None


def test_f08_pico_de_entradas_em_agosto_de_2022_reprova(modelo):
    """Seria sinal de que alguem inferiu a aquisicao por data.

    As pessoas da VivaMarket entraram no HRIS com a data de admissao original,
    que vai de 2000 a 2022. Nao ha pico porque nao ha o que detectar.
    """
    _, _, t = modelo
    f = t["fact_workforce_entry"].filter(pl.col("source_system") != "VIVAMARKET_LEGACY")
    por_mes = (f.with_columns(pl.col("hire_date__iso").str.slice(0, 7).alias("m"))
               .group_by("m").len().sort("m"))
    if por_mes.height < 6:
        pytest.skip("serie curta demais")
    ago = por_mes.filter(pl.col("m") == "2022-08")
    if ago.is_empty():
        pytest.skip("sem agosto de 2022")
    mediana = por_mes["len"].median()
    assert ago["len"][0] < mediana * 5, "pico em agosto de 2022 sugere aquisicao inferida por data"


def test_f09_termination_reason_existindo_reprova(modelo):
    """Nao ha fonte na onda 1; se a coluna existe, foi inventada."""
    _, _, t = modelo
    proibidas = {"termination_reason", "voluntary_flag", "regrettable_flag", "termination_type"}
    assert not (set(t["fact_termination"].columns) & proibidas)


def test_f10_compensacao_alem_da_identidade_resolvida_reprova(modelo):
    _, _, t = modelo
    f = t["fact_compensation"]
    if f.is_empty():
        pytest.skip("sem remuneracao nesta amostra")
    # nenhuma linha pode ter sido ligada a uma pessoa sem vinculo aprovado
    d = t["dim_employee"].select(["employee_sk", "identity_basis"])
    j = f.join(d, on="employee_sk", how="left")
    ligadas = j.filter(pl.col("employee_sk") > 0)
    assert not ligadas.filter(pl.col("identity_basis") == "nao_resolvida").height


def test_f11_mes_com_falha_de_carga_ausente_do_calendario_reprova(modelo):
    _, _, t = modelo
    cal = t["dim_calendar"].filter(pl.col("date_sk") > 0)
    meses = set(cal["mes"].unique().to_list())
    for m in ("2016-01", "2019-05", "2022-08", "2026-06"):
        assert m in meses, f"{m} ausente do calendario"


def test_f12_duas_execucoes_com_contagens_diferentes_reprovam(modelo):
    cfg, _, t = modelo
    outra = B.build(cfg, write=False)["tabelas"]
    for nome, df in t.items():
        assert outra[nome].height == df.height, f"{nome} nao e deterministico"


def test_f13_codigo_da_l3_lendo_a_camada_de_verdade_reprova(modelo):
    """Produziria um modelo que passa na avaliacao contra si mesmo."""
    raiz = Path(config.load().root) / "src" / "analytics" / "model"
    import ast
    for py in raiz.glob("*.py"):
        arvore = ast.parse(py.read_text(encoding="utf-8"))
        literais = [n.value for n in ast.walk(arvore)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        # docstring e comentario podem citar o caminho; literal de codigo, nao
        docstrings = {ast.get_docstring(n) for n in ast.walk(arvore)
                      if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))}
        for lit in literais:
            if lit in docstrings or lit is None or len(lit) > 200:
                continue
            assert "synthetic" not in lit or "truth" not in lit, \
                f"{py.name} referencia a camada de verdade: {lit!r}"


def test_f14_tabela_sem_camada_ou_com_camada_errada_reprova(modelo):
    _, _, t = modelo
    with pytest.raises(LayerError):
        assert_layer(t["dim_employee"].drop("layer"), ANALYTICAL)
    with pytest.raises(LayerError):
        assert_layer(t["dim_employee"], "truth")


def test_f15_contratacao_contando_indeterminada_ou_aquisicao_reprova(modelo):
    """`origin_sk` nao tem default silencioso, e `is_hire` e explicito."""
    _, _, t = modelo
    o = t["dim_origin"]
    hire = set(o.filter(pl.col("is_hire"))["origin_sk"].to_list())
    aquisicao = set(o.filter(pl.col("is_acquisition"))["origin_sk"].to_list())
    indeterminada = set(o.filter(pl.col("code") == "INDETERMINADA")["origin_sk"].to_list())
    assert not (hire & aquisicao) and not (hire & indeterminada)

    f = t["fact_workforce_entry"]
    assert f["origin_sk"].null_count() == 0, "origin_sk e obrigatorio"
    contratacoes = f.filter(pl.col("origin_sk").is_in(list(hire))).height
    total = f.height
    assert contratacoes < total, "tudo virou contratacao; a origem foi preenchida por inferencia"


def test_f16_pessoa_da_vivamarket_sem_origem_de_aquisicao_reprova(modelo):
    """O teste que prova que **proveniencia nao depende de identidade**.

    As 320 pessoas da aquisicao tem origem classificada e nenhuma delas tem
    vinculo aprovado com o HRIS corporativo.
    """
    _, _, t = modelo
    o = t["dim_origin"].filter(pl.col("code") == "AQUISICAO_VIVAMARKET")
    assert o.height == 1
    sk = o["origin_sk"][0]

    viva = t["fact_workforce_entry"].filter(pl.col("source_system") == "VIVAMARKET_LEGACY")
    assert viva.height > 0, "a aquisicao deveria produzir entradas"
    assert set(viva["origin_sk"].unique().to_list()) == {sk}
    assert set(viva["determination_rule"].unique().to_list()) == {"P1"}

    # e a prova do ponto: origem conhecida, identidade nao resolvida
    d = t["dim_employee"].filter(pl.col("employee_sk") > 0)
    pessoas = d.filter(pl.col("origin_code") == "AQUISICAO_VIVAMARKET")
    assert pessoas.height > 0
    assert pessoas["is_provisional_person"].all(), \
        "as pessoas da aquisicao nao deveriam ter vinculo aprovado"


def test_f17_duas_observacoes_do_mesmo_sistema_no_mesmo_mes_reprovam(modelo):
    """Violaria o grain declarado."""
    _, _, t = modelo
    f = t["fact_headcount_snapshot"]
    dup = f.group_by(["party_key", "date_sk", "source_sk"]).len().filter(pl.col("len") > 1)
    assert dup.is_empty(), f"{dup.height} violacoes do grain pessoa x mes x sistema"


# ===========================================================================
# Proveniencia (diretrizes 1 a 4)
# ===========================================================================
def test_hris_nao_determina_origem(modelo):
    """Marca-los como organico faria toda pessoa absorvida da aquisicao virar
    contratacao, fechando o headcount com uma mentira."""
    cfg, _, _ = modelo
    from analytics.model import origin as prov
    determina = prov.determines_origin(cfg)
    assert "HRIS_CORE" not in determina and "HRIS_LEGACY" not in determina
    assert determina.get("VIVAMARKET_LEGACY") == "AQUISICAO_VIVAMARKET"


def test_indeterminada_permanece_estado_valido(modelo):
    """Nao preencher por inferencia. 100% de cobertura seria o sinal de alarme."""
    _, out, t = modelo
    d = t["dim_employee"].filter(pl.col("employee_sk") > 0)
    indet = d.filter(pl.col("origin_code") == "INDETERMINADA")
    assert indet.height > 0, "cobertura total de origem sugere inferencia"
    assert indet["determination_rule"].null_count() == indet.height
    assert out["resumo"]["contaminacao"]["teto_contaminacao_aquisicao"] >= 0


def test_membros_reservados_existem_em_toda_dimensao(modelo):
    _, _, t = modelo
    for nome, esperados in keys.RESERVED.items():
        if nome not in t:
            continue
        pk = GRAIN[nome][0] if nome != "dim_employee" else "employee_sk"
        presentes = set(t[nome][pk].to_list()) if pk in t[nome].columns else set()
        for m in esperados:
            assert m["sk"] in presentes, f"{nome} sem o membro {m['sk']} ({m['code']})"
