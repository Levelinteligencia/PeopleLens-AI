"""Testes da resolucao governada da F4.

A pergunta central da F3 era "o pipeline transformou apenas o que declarou".
A da F4 e outra: **nada muda de significado sem alguem assinar embaixo.**

O que precisa ficar provado aqui:

1. nao existe caminho que aprove sozinho, nem por limiar de confianca, nem em
   lote, nem por sugestao do proprio pipeline;
2. aprovar exige valor explicito, responsavel e justificativa, e o resultado vai
   para o arquivo de referencia versionado, nao para o banco;
3. o efeito e real: a execucao seguinte enxerga o mapeamento e a excecao some;
4. rejeitar nao apaga, e reexecutar o pipeline nao ressuscita o que foi decidido;
5. identidade segue a mesma governanca, e `nao corresponde a ninguem` e uma
   decisao valida.

Tudo roda num diretorio temporario proprio, com perfil `smoke`. Os arquivos de
referencia de verdade, em `data/reference/`, nao sao tocados: a Sam autorizou a
F4 dizendo "nenhuma promocao automatica", e o teste nao e excecao a isso.
"""
from __future__ import annotations

import csv
import inspect
import shutil
from pathlib import Path

import polars as pl
import pytest

import pipeline
from generator import config, materialize, projection
from generator.events.lifecycle import World
from mapping import proposal
from mapping.depara import FIELDS, ExceptionQueue
from mapping.resolution import Governance, GovernanceError


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory):
    """Uma execucao completa num universo descartavel."""
    root = tmp_path_factory.mktemp("gov")
    src = Path(config.load().root)
    shutil.copytree(src / "config", root / "config")
    shutil.copytree(src / "data" / "reference", root / "data" / "reference")

    cfg = config.load(root)
    cfg.generation["reproducibility"]["active_profile"] = "smoke"
    truth = World(cfg).run()
    tables = materialize.build_all(cfg, truth)
    materialize.write(cfg, tables)
    projection.run(cfg, tables)

    out = pipeline.run(cfg, write=False)
    # instantaneo das excecoes ANTES de qualquer decisao deste modulo, para que
    # os testes de estado inicial nao dependam da ordem de execucao
    inicial = out["frames"]["exceptions"].clone()
    return cfg, out, inicial


@pytest.fixture(scope="module")
def gov(sandbox):
    cfg, _, _ = sandbox
    return Governance(cfg)


def _uma_excecao_aberta(inicial: pl.DataFrame, campo: str | None = None) -> dict:
    f = inicial.filter(pl.col("status") == "OPEN")
    if campo:
        f = f.filter(pl.col("source_field") == campo)
    if f.is_empty():
        pytest.skip(f"nenhuma excecao aberta para {campo or 'qualquer campo'}")
    return f.sort("exception_id").to_dicts()[0]


def _ref_rows(cfg, campo: str) -> list[dict]:
    path = Path(cfg.root) / "data" / "reference" / f"{FIELDS[campo]}.csv"
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------- #
# 1. nao existe atalho
# --------------------------------------------------------------------------- #
def test_nao_existe_aprovacao_automatica_nem_em_lote(gov):
    """Principio 5, verificado na superficie da API.

    Nao basta que ninguem chame um aprovador automatico: ele nao pode existir,
    porque a existencia e o convite. Este teste quebra no dia em que alguem
    adicionar `approve_all` ou `auto_approve(threshold=0.95)`.
    """
    publicos = [n for n in dir(gov) if not n.startswith("_")]
    proibidos = [n for n in publicos
                 if any(p in n.lower() for p in ("auto", "bulk", "batch", "all", "threshold"))]
    assert not proibidos, f"metodos com cara de aprovacao automatica: {proibidos}"

    sig = inspect.signature(Governance.approve)
    for obrigatorio in ("standard_value", "by", "rationale"):
        p = sig.parameters[obrigatorio]
        assert p.default is inspect.Parameter.empty, f"`{obrigatorio}` nao pode ter default"


def test_aprovacao_exige_valor_explicito(gov, sandbox):
    _, _, inicial = sandbox
    e = _uma_excecao_aberta(inicial)
    with pytest.raises(GovernanceError, match="standard_value"):
        gov.approve(e["exception_id"], standard_value="", by="teste",
                    rationale="justificativa suficientemente longa")


def test_aprovacao_exige_justificativa(gov, sandbox):
    _, _, inicial = sandbox
    e = _uma_excecao_aberta(inicial)
    with pytest.raises(GovernanceError, match="justificativa"):
        gov.approve(e["exception_id"], standard_value="Marketing", by="teste", rationale="ok")


def test_sugestao_de_alta_confianca_nao_aprova_nada(sandbox):
    """A sugestao do pipeline nunca vira estado.

    Existem excecoes com confianca alta na fila. Todas continuam OPEN, sem
    responsavel e sem valor resolvido, ate alguem chamar `approve`.
    """
    _, _, inicial = sandbox
    altas = inicial.filter((pl.col("confidence_score") >= 0.9) & (pl.col("status") == "OPEN"))
    if altas.is_empty():
        pytest.skip("nenhuma sugestao de confianca alta nesta amostra")
    assert altas["resolution"].null_count() == altas.height
    assert altas["resolved_by"].null_count() == altas.height


def test_proposta_classifica_e_nao_aplica(sandbox):
    """`proposal` produz documento, nao efeito colateral."""
    cfg, out, inicial = sandbox
    antes = _ref_rows(cfg, "department")
    _, rows = proposal.write(cfg, out["frames"]["exceptions"])
    assert rows, "a proposta nao classificou nada"
    assert set(r["classe"] for r in rows) <= set(proposal.CLASSES)
    assert _ref_rows(cfg, "department") == antes, "a proposta escreveu no arquivo de referencia"


def test_ambiguidade_de_negocio_nao_recebe_recomendacao_tecnica(sandbox):
    """N4 e N5 da VivaMarket: a excecao que o desenho quis criar.

    Sao os niveis em que a escala da empresa adquirida cobre dois niveis da
    NOVAORA. Nao existe mapeamento correto, e a proposta precisa dizer isso em
    vez de sugerir o candidato mais parecido.
    """
    cfg, out, _ = sandbox
    rows = proposal.classify(cfg, out["frames"]["exceptions"])
    viva = [r for r in rows if r["source_value"] in ("N4", "N5")]
    if not viva:
        pytest.skip("N4/N5 ausentes nesta amostra")
    for r in viva:
        assert r["classe"] == "DECISAO_DE_NEGOCIO", r
        assert "aprovar como" not in r["recomendacao"]


def test_valor_em_outra_lingua_nao_recebe_candidato(sandbox):
    """Achado da F4: score entre linguas diferentes nao e evidencia.

    `Controladoria` casava 0,61 com `Engineering` e aparecia como candidato
    provavel. Nao e candidato, e coincidencia de letras entre dois vocabularios.
    Quando a lingua declarada do sistema difere da do dominio corporativo e
    nenhum apelido aprovado cobre o valor, a proposta nao oferece candidato.
    """
    cfg, out, _ = sandbox
    rows = proposal.classify(cfg, out["frames"]["exceptions"])
    traducoes = [r for r in rows if r["classe"] == "TRADUCAO_PENDENTE"]
    if not traducoes:
        pytest.skip("nenhum valor em outra lingua nesta amostra")
    for r in traducoes:
        assert r["best_candidate"] is None, r
        assert r["matched_alias"] is None
        assert r["source_language"] and r["source_language"] != r["canonical_language"]
        assert "aprovar como" not in r["recomendacao"]


def test_sugestao_aceita_e_conferivel_pelo_apelido_que_casou(sandbox):
    """`JUR -> Legal, 0,82 por prefixo` e inconferivel: `JUR` nao e prefixo de
    `Legal`. E prefixo de `JURIDICO`, um apelido ja aprovado. A proposta tem que
    mostrar o intermediario, senao pede fe em vez de revisao."""
    cfg, out, _ = sandbox
    rows = proposal.classify(cfg, out["frames"]["exceptions"])
    aceitos = [r for r in rows if r["classe"] in ("APELIDO_CONHECIDO", "VARIANTE_DE_ESCRITA")]
    if not aceitos:
        pytest.skip("nenhuma sugestao aceita nesta amostra")
    conhecidos = {r["source_value"] for r in _ref_rows(cfg, "department")}
    conhecidos |= {r["standard_value"] for r in _ref_rows(cfg, "department")}
    for r in aceitos:
        assert r["matched_alias"], r
        if r["source_field"] == "department":
            assert r["matched_alias"] in conhecidos, \
                f"{r['source_value']} casou com `{r['matched_alias']}`, que nao esta no mapa aprovado"


def test_n4_e_n5_permanecem_como_excecao_pendente(sandbox):
    """Item 1 da aprovacao da F3: registrar N4/N5 como excecoes pendentes.

    O pipeline nao pode ter resolvido nem escondido nenhum dos dois.
    """
    cfg, _, inicial = sandbox
    aprovados = {r["source_value"] for r in _ref_rows(cfg, "job_level")
                 if r["mapping_status"] == "APPROVED"}
    assert "N4" not in aprovados and "N5" not in aprovados
    pendentes = inicial.filter(pl.col("source_value").is_in(["N4", "N5"]))
    if pendentes.is_empty():
        pytest.skip("N4/N5 ausentes nesta amostra")
    assert set(pendentes["status"].unique().to_list()) == {"OPEN"}


# --------------------------------------------------------------------------- #
# 2 e 3. o ciclo completo, com efeito verificado
# --------------------------------------------------------------------------- #
def test_ciclo_completo_promove_para_o_csv_versionado_e_muda_a_execucao_seguinte(sandbox, gov):
    """OPEN -> UNDER_REVIEW -> APPROVED -> mapeamento vigente.

    O teste so vale se o efeito for medido do lado de fora: nao basta a fila
    dizer APPROVED, a execucao seguinte tem que enxergar o mapeamento.
    """
    cfg, _, inicial = sandbox
    e = _uma_excecao_aberta(inicial, campo="department")
    eid, valor = e["exception_id"], e["source_value"]
    alvo = "Marketing"

    antes = _ref_rows(cfg, "department")
    assert not any(r["source_value"] == valor and r["mapping_status"] == "APPROVED" for r in antes)

    gov.under_review(eid, by="teste", rationale="triagem da fila de excecoes da F4")
    path = gov.approve(eid, standard_value=alvo, by="teste",
                       rationale="valor do sistema legado equivalente ao departamento corporativo")

    # o arquivo versionado ganhou exatamente uma linha, com autoria e data
    depois = _ref_rows(cfg, "department")
    assert len(depois) == len(antes) + 1
    nova = [r for r in depois if r["source_value"] == valor][0]
    assert nova["standard_value"] == alvo
    assert nova["mapping_status"] == "APPROVED"
    assert nova["approved_by"] == "teste" and nova["approved_at"]
    assert path.suffix == ".csv", "a promocao tem que ir para o CSV versionado, nao para o banco"

    # o log guarda as duas transicoes, com responsavel e justificativa
    log = gov.log().filter(pl.col("item_id") == eid)
    assert log["to_status"].to_list() == ["UNDER_REVIEW", "APPROVED"]
    assert log.filter(pl.col("to_status") == "APPROVED")["decided_value"].item() == alvo
    assert log["decided_by"].null_count() == 0
    assert (log["rationale"].str.len_chars() >= 10).all()

    # efeito real: reexecutar o pipeline e o valor deixa de ser excecao
    de_novo = pipeline.run(cfg, write=False)
    exc = de_novo["frames"]["exceptions"]
    ainda_aberta = exc.filter((pl.col("source_value") == valor) & (pl.col("status") == "OPEN"))
    assert ainda_aberta.is_empty(), f"`{valor}` continua aberta apos a promocao"

    conformado = False
    for df in de_novo["frames"]["conformed"].values():
        if "std_department" in df.columns and df.filter(pl.col("std_department") == alvo).height:
            conformado = True
    assert conformado, "o mapeamento aprovado nao chegou na camada conformada"


def test_promocao_e_idempotente(sandbox, gov):
    """Aprovar duas vezes o mesmo par nao duplica a linha de referencia.

    Importa porque a fila e reconstruida a cada execucao: sem isso, o arquivo de
    referencia cresceria uma linha por rodada.
    """
    cfg, _, _ = sandbox
    antes = len(_ref_rows(cfg, "country"))
    for _ in range(3):
        gov._promote("country", "REPUBLICA ARGENTINA", "AR", by="teste")
    assert len(_ref_rows(cfg, "country")) == antes + 1


def test_excecao_ja_decidida_nao_pode_ser_decidida_de_novo(sandbox, gov):
    cfg, _, inicial = sandbox
    e = _uma_excecao_aberta(inicial, campo="department")
    with pytest.raises(GovernanceError, match="ja esta APPROVED"):
        gov.approve(e["exception_id"], standard_value="Outro", by="teste",
                    rationale="tentativa de reescrever decisao ja tomada")


# --------------------------------------------------------------------------- #
# 4. rejeitar nao e esquecer
# --------------------------------------------------------------------------- #
def test_rejeicao_exige_justificativa_e_nao_apaga(sandbox, gov):
    cfg, _, inicial = sandbox
    abertas = inicial.filter((pl.col("status") == "OPEN")
                             & (pl.col("source_field") != "department")).sort("exception_id")
    if abertas.is_empty():
        pytest.skip("sem excecao disponivel para rejeitar")
    eid = abertas.to_dicts()[0]["exception_id"]

    with pytest.raises(GovernanceError, match="justificativa"):
        gov.reject(eid, by="teste", rationale="nao")

    gov.reject(eid, by="teste", rationale="valor invalido na origem; corrigir no sistema-fonte")
    fila = gov.conn.execute(
        "SELECT status, resolved_by FROM mapping_exceptions WHERE exception_id=?", (eid,)).fetchone()
    assert fila == ("REJECTED", "teste")
    assert gov.log().filter(pl.col("item_id") == eid)["to_status"].to_list() == ["REJECTED"]


def test_reexecutar_o_pipeline_nao_ressuscita_decisao(sandbox, gov):
    """Achado da F4: `reset()` apagava a fila inteira a cada execucao.

    O efeito era silencioso e grave: um valor REJECTED voltava OPEN na rodada
    seguinte, e a rejeicao virava esquecimento. A fila agora preserva o que tem
    decisao humana e recomeca a contagem.
    """
    cfg, _, _ = sandbox
    decididas = {r[0]: r[1] for r in gov.conn.execute(
        "SELECT exception_id, status FROM mapping_exceptions WHERE status<>'OPEN'").fetchall()}
    assert decididas, "o teste depende de ter havido decisao antes"

    pipeline.run(cfg, write=False)

    q = ExceptionQueue(Path(cfg.root))
    for eid, status in decididas.items():
        atual = q.conn.execute(
            "SELECT status FROM mapping_exceptions WHERE exception_id=?", (eid,)).fetchone()
        assert atual and atual[0] == status, f"{eid} voltou de {status} para {atual}"


def test_valor_rejeitado_nao_entra_no_mapa_aprovado(sandbox, gov):
    cfg, _, _ = sandbox
    rejeitadas = gov.conn.execute(
        "SELECT source_field, source_value FROM mapping_exceptions WHERE status='REJECTED'").fetchall()
    for campo, valor in rejeitadas:
        aprovados = {r["source_value"] for r in _ref_rows(cfg, campo)
                     if r["mapping_status"] == "APPROVED"}
        assert valor not in aprovados


def test_deprecar_nao_apaga_a_linha(sandbox, gov):
    """Mudanca de significado nao pode apagar historico.

    Series antigas foram calculadas com o mapa antigo. Apagar a linha tornaria
    isso irreconstruivel; DEPRECATED mantem legivel o que valia antes.
    """
    cfg, _, _ = sandbox
    antes = _ref_rows(cfg, "country")
    alvo = [r for r in antes if r["mapping_status"] == "APPROVED"][0]["source_value"]

    gov.deprecate("country", alvo, by="teste", rationale="valor descontinuado pela area dona do dado")

    depois = _ref_rows(cfg, "country")
    assert len(depois) == len(antes)
    linha = [r for r in depois if r["source_value"] == alvo][0]
    assert linha["mapping_status"] == "DEPRECATED"
    assert linha["standard_value"], "o valor padrao antigo tem que continuar legivel"


def test_deprecar_o_que_nao_existe_falha(gov):
    with pytest.raises(GovernanceError):
        gov.deprecate("country", "PAIS QUE NUNCA EXISTIU", by="teste",
                      rationale="tentativa sobre valor inexistente")


# --------------------------------------------------------------------------- #
# 5. identidade sob a mesma governanca
# --------------------------------------------------------------------------- #
def test_fila_de_identidade_recebe_apenas_o_que_o_sistema_nao_decidiu(sandbox, gov):
    """ADR-0004: RESOLVED saiu por identificador exato e nao vai para fila
    humana. MANUAL_REVIEW e AMBIGUOUS vao, porque sao exatamente os casos em que
    o sistema esta proibido de decidir sozinho."""
    _, out, _ = sandbox
    fila = gov.identity_queue()
    if fila.is_empty():
        pytest.skip("fila de identidade vazia nesta amostra")

    x = out["frames"]["xref"]
    pendentes = {f"{r['source_system']}|{r['source_employee_id']}"
                 for r in x.filter(pl.col("match_status").is_in(["MANUAL_REVIEW", "AMBIGUOUS"])).to_dicts()}
    resolvidos = {f"{r['source_system']}|{r['source_employee_id']}"
                  for r in x.filter(pl.col("match_status") == "RESOLVED").to_dicts()}
    na_fila = set(fila["decision_id"].to_list())
    assert na_fila <= pendentes
    assert not (na_fila & resolvidos)


def test_decisao_de_identidade_exige_justificativa(sandbox, gov):
    fila = gov.identity_queue()
    if fila.is_empty():
        pytest.skip("fila de identidade vazia")
    did = fila.filter(pl.col("status") == "OPEN").sort("decision_id")["decision_id"].to_list()[0]
    with pytest.raises(GovernanceError, match="justificativa"):
        gov.decide_identity(did, employee_id=1, by="teste", rationale="ok")


def test_nao_corresponde_a_ninguem_e_decisao_valida(sandbox, gov):
    """Terceiro de agencia na folha nao tem contraparte no HRIS. Forcar um
    vinculo seria pior do que registrar que nao existe vinculo."""
    fila = gov.identity_queue()
    if fila.is_empty():
        pytest.skip("fila de identidade vazia")
    abertos = fila.filter(pl.col("status") == "OPEN").sort("decision_id")["decision_id"].to_list()
    did = abertos[-1]
    gov.decide_identity(did, employee_id=None, by="teste",
                        rationale="pessoa da folha sem contraparte no cadastro corporativo")
    row = gov.conn.execute(
        "SELECT status, decided_employee_id FROM identity_decisions WHERE decision_id=?", (did,)).fetchone()
    assert row == ("REJECTED", None)
    assert gov.log().filter(pl.col("item_id") == did)["to_status"].to_list() == ["REJECTED"]


def test_identidade_decidida_nao_e_redecidida_nem_reaberta(sandbox, gov):
    """A fila e recarregada a cada execucao, e nao pode reabrir o que foi
    decidido."""
    _, out, _ = sandbox
    fila = gov.identity_queue()
    if fila.is_empty():
        pytest.skip("fila de identidade vazia")
    decididos = fila.filter(pl.col("status") != "OPEN")["decision_id"].to_list()
    if not decididos:
        pytest.skip("nenhuma decisao de identidade tomada ainda")
    did = decididos[0]

    with pytest.raises(GovernanceError, match="ja esta"):
        gov.decide_identity(did, employee_id=1, by="teste",
                            rationale="tentativa de redecidir caso ja fechado")

    novos = gov.load_identity_queue(out["frames"]["xref"])
    assert novos == 0, "recarregar a fila inseriu casos que ja estavam la"
    status = gov.conn.execute(
        "SELECT status FROM identity_decisions WHERE decision_id=?", (did,)).fetchone()[0]
    assert status != "OPEN"


def test_fila_de_identidade_marca_o_que_a_execucao_atual_nao_viu(sandbox, gov):
    """Achado da F4: a fila de identidade e cumulativa e nao tinha marca de
    observacao, entao residuo de uma execucao anterior (inclusive de outro
    universo) ficava indistinguivel de caso pendente legitimo.

    Nao se apaga, se marca. Aqui a marca e exercitada com um run_id inventado:
    nada foi observado por ele, logo tudo que esta OPEN e considerado nao
    observado.
    """
    cfg, _, _ = sandbox
    atual = pipeline.run(cfg, write=False)["resumo"]["run_id"]
    assert gov.identity_stale(atual).height == 0, "a execucao atual deixou casos sem marca"

    fantasma = gov.identity_stale("run-que-nunca-existiu")
    abertos = gov.identity_queue().filter(pl.col("status") == "OPEN").height
    assert fantasma.height == abertos
    assert set(fantasma["status"].unique().to_list()) == {"OPEN"}, \
        "caso ja decidido nao pode ser reportado como residuo"


# --------------------------------------------------------------------------- #
# transversal
# --------------------------------------------------------------------------- #
def test_toda_transicao_tem_responsavel_justificativa_e_data(gov):
    log = gov.log()
    assert log.height > 0
    assert log["decided_by"].null_count() == 0
    assert log["rationale"].null_count() == 0
    assert log["decided_at"].null_count() == 0
    assert (log["rationale"].str.len_chars() >= 10).all()
    assert set(log["queue"].unique().to_list()) <= {"mapping", "identity"}


def test_toda_promocao_aponta_para_o_arquivo_que_alterou(sandbox, gov):
    cfg, _, _ = sandbox
    promocoes = gov.log().filter(pl.col("promoted_to").is_not_null())
    assert promocoes.height > 0
    for destino in promocoes["promoted_to"].to_list():
        assert (Path(cfg.root) / destino).exists()
        assert destino.startswith("data/reference/")
