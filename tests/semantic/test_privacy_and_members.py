"""G-01 e G-02: supressao por linha e membro reservado preservado.

Os dois gaps que a SPEC do MCP encontrou ao projetar `breakdown_kpi`, cada um
com o caso real que o revelou:

    G-01  women_in_leadership por pais, 2019-06, minimum_n = 20
              AR n=6   BR n=75   CO n=1
          O total (82) passava no minimo e a linha do CO expunha uma pessoa.

    G-02  headcount por departamento, 2016-06
              {departamento: null, valor: 397}
          40 dos 126 meses da serie estao 100% no membro reservado UNMAPPED,
          e o nome se perdia na ultima camada.

Nenhum limiar novo, nenhuma definicao de KPI alterada: o mesmo `minimum_n` do
ADR-0007, avaliado no grao certo, e o mesmo membro reservado do ADR-0025,
projetado pelo nome em vez do atributo.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from analytics.semantic import ask as A, members, plans, privacy
from generator import config

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def cfg():
    return config.load(ROOT)


@pytest.fixture(scope="module")
def eng(cfg):
    e = A.engine(cfg)
    yield e
    e.close()


def _linhas(pops: list[int], dim: str = "pais") -> list[dict]:
    """Linhas sinteticas: uma por membro, com a populacao pedida."""
    return [{dim: f"M{i}", "valor": 10.0 + i, "populacao": p}
            for i, p in enumerate(pops)]


# ========================================================================== #
# G-01 — minimum_n por linha
# ========================================================================== #
def test_g01_agregado_acima_do_minimo_com_linha_abaixo(eng):
    """O caso que revelou o gap. O total passa; as linhas pequenas nao saem."""
    ans = A.ask(eng, {"kpi": "women_in_leadership",
                      "period": {"grain": "mes", "from": "2019-06", "to": "2019-06"},
                      "dimensions": ["pais"]}, registrar=False)
    assert ans.respondeu
    por_pais = {l["pais"]: l for l in ans.rows}

    # BR tem 75 pessoas e responde
    assert por_pais["BR"]["suprimido"] is False
    assert por_pais["BR"]["valor"] == pytest.approx(0.533333, abs=1e-5)
    assert por_pais["BR"]["populacao"] == 75

    # AR (n=6) e CO (n=1) ficam sem valor E sem populacao
    for pais in ("AR", "CO"):
        linha = por_pais[pais]
        assert linha["suprimido"] is True
        assert linha["motivo_supressao"] == privacy.MOTIVO_PRIMARIA
        assert linha["valor"] is None
        assert linha["populacao"] is None
        # nem numerador nem denominador sobrevivem: com os dois, a razao volta
        assert linha.get("numerador") is None
        assert linha.get("denominador") is None

    assert ans.coverage["linhas_suprimidas"] == 2
    assert ans.coverage["linhas_publicadas"] == 1
    assert ans.coverage["supressao"]["motivo"] == "PRIVACIDADE"
    assert any("PRIVACIDADE" in c and "qualidade" in c for c in ans.caveats)


def test_g01_todas_as_linhas_acima_do_minimo(eng):
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"},
                      "dimensions": ["pais"]}, registrar=False)
    assert ans.respondeu
    assert ans.coverage["linhas_suprimidas"] == 0
    assert len(ans.rows) == 5
    assert all(l["suprimido"] is False for l in ans.rows)
    assert all(l["populacao"] >= 5 for l in ans.rows)
    # nada suprimido: a populacao publicada e a populacao inteira
    assert ans.coverage["population"] == sum(l["populacao"] for l in ans.rows) == 1942
    assert "supressao" not in ans.coverage


def test_g01_todas_as_linhas_abaixo_do_minimo(eng):
    """Sem nenhuma linha publicavel, a resposta inteira e supressao.

    Nao e uma resposta vazia nem uma recusa: e `SUPPRESSED`, com a palavra
    privacidade, porque um agente que le "erro" tenta outro recorte.
    """
    ans = A.ask(eng, {"kpi": "turnover_rate",
                      "period": {"grain": "ano", "from": "2018", "to": "2018"},
                      "dimensions": ["departamento"],
                      "filters": [{"dimension": "pais", "in": ["Argentina"]}]},
                registrar=False)
    assert ans.suppressed is not None
    assert ans.refusal is None
    assert ans.suppressed["motivo"] == "PRIVACIDADE"
    assert ans.suppressed["linhas_publicadas"] == 0
    assert ans.suppressed["linhas_suprimidas"] == 10
    assert ans.value is None and ans.level is None
    assert "qualidade" in ans.suppressed["nota"]
    assert "privacidade" in ans.explanation.lower()


def test_g01_fronteira_exatamente_no_minimum_n():
    """Populacao IGUAL ao minimo publica. O minimo e o que basta.

    Testado na funcao e nao numa consulta para que a fronteira seja exata e nao
    dependa de o dado ter, por acaso, um recorte com exatamente n pessoas.
    """
    # duas abaixo, para isolar a fronteira da supressao complementar
    r = privacy.aplicar(_linhas([15, 19, 20, 21]), minimum_n=20, dimensoes=["pais"])
    estado = {l["pais"]: l["suprimido"] for l in r.linhas}
    assert estado == {"M0": True, "M1": True, "M2": False, "M3": False}
    assert r.suprimidas == 2 and r.publicadas == 2
    assert r.complementares == 0      # duas ja suprimidas: nada a complementar

    # e o limite inferior do publicado continua sendo o proprio minimo
    r2 = privacy.aplicar(_linhas([20, 20, 20]), minimum_n=20, dimensoes=["pais"])
    assert r2.suprimidas == 0


def test_g01_tentativa_de_inferir_o_valor_suprimido(eng):
    """Uma unica linha suprimida seria reconstruivel por subtracao.

    O total da mesma consulta sem quebra continua disponivel. Com uma linha
    suprimida, `total - publicadas` devolve exatamente a linha protegida. Por
    isso a menor linha restante e suprimida junto, e o residuo passa a ser
    compartilhado por duas.
    """
    # a funcao: exatamente uma abaixo do minimo dispara a complementar
    r = privacy.aplicar(_linhas([3, 40, 50, 60]), minimum_n=20, dimensoes=["pais"])
    suprimidas = [l["pais"] for l in r.linhas if l["suprimido"]]
    assert suprimidas == ["M0", "M1"]          # M1 e a menor das restantes
    assert r.complementares == 1
    motivos = {l["pais"]: l.get("motivo_supressao") for l in r.linhas if l["suprimido"]}
    assert motivos == {"M0": privacy.MOTIVO_PRIMARIA,
                       "M1": privacy.MOTIVO_COMPLEMENTAR}

    # duas linhas, uma abaixo: a complementar colapsa a resposta inteira
    r2 = privacy.aplicar(_linhas([3, 90]), minimum_n=20, dimensoes=["pais"])
    assert r2.tudo_suprimido is True

    # e o ataque de fato, contra a consulta real
    total = A.ask(eng, {"kpi": "headcount",
                        "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
                  registrar=False).value
    quebra = A.ask(eng, {"kpi": "women_in_leadership",
                         "period": {"grain": "mes", "from": "2019-06", "to": "2019-06"},
                         "dimensions": ["pais"]}, registrar=False)
    assert total == 1942
    publicada = sum(l["populacao"] for l in quebra.rows if not l["suprimido"])
    suprimidas_n = sum(1 for l in quebra.rows if l["suprimido"])
    # o residuo, se alguem o calcular, cobre 2 linhas e nao identifica nenhuma
    assert suprimidas_n >= 2
    assert quebra.coverage["population"] == publicada
    assert all(l["populacao"] is None for l in quebra.rows if l["suprimido"])


def test_g01_nao_cria_threshold_novo(eng, cfg):
    """O limiar continua sendo o `minimum_n` do contrato, e nada mais."""
    from analytics.semantic import catalog as C
    cat = C.load(cfg)
    assert cat["women_in_leadership"].minimum_n == 20
    assert cat["headcount"].minimum_n == 5
    fonte = (ROOT / "src" / "analytics" / "semantic" / "privacy.py").read_text(encoding="utf-8")
    # nenhum numero magico servindo de limiar
    assert "minimum_n" in fonte
    for proibido in ("= 5", "= 10", "= 20", "= 25"):
        assert f"minimo{proibido}" not in fonte


def test_g01_consulta_sem_quebra_nao_muda(eng):
    """A correcao e no grao da quebra; o agregado continua como estava."""
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
                registrar=False)
    assert ans.value == 1942 and ans.trust["status"] == "CERTIFIED"
    t = A.ask(eng, {"kpi": "turnover_rate",
                    "period": {"grain": "ano", "from": "2024", "to": "2024"}},
              registrar=False)
    assert t.value == pytest.approx(0.253766, abs=1e-6)


# ========================================================================== #
# G-02 — membro reservado preservado
# ========================================================================== #
def test_g02_membro_reservado_presente(eng):
    """2016-06: 397 pessoas no membro reservado, e o nome dele aparece."""
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2016-06", "to": "2016-06"},
                      "dimensions": ["departamento"]}, registrar=False)
    assert ans.respondeu
    assert len(ans.rows) == 1
    linha = ans.rows[0]
    assert linha["departamento"] == "UNMAPPED"
    assert linha["departamento"] is not None
    assert linha["valor"] == 397
    assert members.e_pendencia(linha["departamento"])
    assert any("UNMAPPED" in c and "mapeamento" in c for c in ans.caveats)


def test_g02_nenhuma_linha_traz_membro_nulo(eng):
    """Varredura: em nenhuma dimensao, em nenhum periodo, sai `null` como chave.

    A era inteira do HRIS_LEGACY (40 dos 126 meses) esta 100% no membro
    reservado, entao esta varredura cobre exatamente o trecho que falhava.
    """
    for mes in ("2016-06", "2017-01", "2018-12", "2019-04", "2019-05", "2026-06"):
        for dim in ("pais", "business_unit", "departamento", "nivel", "origem"):
            ans = A.ask(eng, {"kpi": "headcount",
                              "period": {"grain": "mes", "from": mes, "to": mes},
                              "dimensions": [dim]}, registrar=False)
            if not ans.respondeu:
                continue
            for l in ans.rows:
                assert l[dim] is not None, (mes, dim)
                assert str(l[dim]).strip() != "", (mes, dim)


def test_g02_valor_realmente_ausente_e_distinto(eng):
    """`VALOR_AUSENTE` nao e pendencia de governanca, e nao se confunde com ela.

    Em `genero`, a L3 tem tres coisas diferentes na mesma coluna: o genero
    declarado, a nao declaracao que a fonte registrou (`Not informed`), e o
    campo que simplesmente nao veio. As tres saem com nomes diferentes.
    """
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"},
                      "dimensions": ["genero"]}, registrar=False)
    membros_ = {l["genero"] for l in ans.rows}
    assert "Female" in membros_ and "Male" in membros_
    assert "Not informed" in membros_        # declaracao de quem nao quis declarar
    assert members.VALOR_AUSENTE in membros_  # campo que nao veio
    assert None not in membros_

    assert members.e_governado(members.VALOR_AUSENTE)
    assert not members.e_pendencia(members.VALOR_AUSENTE)
    assert members.e_pendencia("UNMAPPED")
    assert "decisão pendente" in members.significado(members.VALOR_AUSENTE)


def test_g02_mistura_de_reservado_e_membros_validos(eng):
    """Uma quebra com membro reservado e membros de negocio na mesma saida."""
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2016-06", "to": "2016-06"},
                      "dimensions": ["nivel"]}, registrar=False)
    assert ans.respondeu
    membros_ = {l["nivel"] for l in ans.rows}
    validos = {m for m in membros_ if not members.e_governado(m)}
    assert "IC1" in validos and "M1" in validos
    assert None not in membros_
    # e o caso da entrada de pessoal, onde o reservado vem de dim_employee
    entradas = A.ask(eng, {"kpi": "hiring_volume",
                           "period": {"grain": "ano", "from": "2025", "to": "2025"},
                           "dimensions": ["departamento"]}, registrar=False)
    assert entradas.respondeu
    assert "SEM_CHAVE_DE_ORIGEM" in {l["departamento"] for l in entradas.rows}
    assert None not in {l["departamento"] for l in entradas.rows}


def test_g02_reservado_nao_e_confundido_com_ausencia(eng):
    """`UNMAPPED` e `VALOR_AUSENTE` sao estados distintos, com donos distintos.

    Um tem caminho de resolucao (alguem aprova o mapeamento); o outro nao tem
    decisao pendente, tem dado que nao veio. Colapsar os dois num `null` apaga
    exatamente essa diferenca, que e a razao de ser do ADR-0025.
    """
    assert "UNMAPPED" != members.VALOR_AUSENTE
    assert members.e_pendencia("UNMAPPED")
    assert not members.e_pendencia(members.VALOR_AUSENTE)
    assert members.significado("UNMAPPED") != members.significado(members.VALOR_AUSENTE)
    assert "mapeamento" in members.significado("UNMAPPED")

    # INDETERMINADA continua sendo estado legitimo de origem (ADR-0027), e nao
    # vira ausencia nem contratacao
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"},
                      "dimensions": ["origem"]}, registrar=False)
    origens = {l["origem"] for l in ans.rows}
    assert "INDETERMINADA" in origens
    assert members.e_governado("INDETERMINADA")
    assert None not in origens


def test_g02_projecao_nunca_le_o_atributo_direto():
    """O defeito era projetar `o.department`; a correcao e verificada no SQL.

    Toda dimensao de negocio sai de um CASE que olha o surrogate key antes do
    atributo, ou de um COALESCE nomeado. Um `AS departamento` direto de coluna
    seria a volta do G-02.
    """
    import re
    for kpi_id, plano in plans.PLANS.items():
        for dim in ("pais", "business_unit", "departamento", "nivel"):
            direto = re.search(rf"^\s*\w+\.\w+\s+AS {dim}\s*,?\s*$",
                               plano.sql, re.MULTILINE)
            assert direto is None, f"{kpi_id}: projecao direta em {dim}"


def test_g02_totais_nao_mudaram(eng):
    """A correcao renomeia membro; nao move ninguem de recorte."""
    import polars as pl
    h = pl.read_parquet(ROOT / "data" / "processed" / "analytical"
                        / "fact_headcount_snapshot.parquet").filter(
        pl.col("is_system_of_record"))
    for mes, esperado in (("2016-06", 397), ("2026-06", 1942)):
        ans = A.ask(eng, {"kpi": "headcount",
                          "period": {"grain": "mes", "from": mes, "to": mes},
                          "dimensions": ["departamento"]}, registrar=False)
        real = h.filter(pl.col("obs_date").str.starts_with(mes))["party_key"].n_unique()
        assert sum(l["valor"] for l in ans.rows) == real == esperado
