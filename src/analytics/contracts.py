"""Contratos de KPI: leitura, derivacao e verificacao (ADR-0011).

Um contrato de KPI declara de que checks de qualidade e de que mapeamentos
aquele KPI depende. Sem isso o trust score seria escolhido em vez de calculado,
e "de onde veio esse numero" nao teria resposta verificavel.

A parte autoral do contrato (nome, grao, formula, mapeamentos, n minimo, niveis
de resposta) e escrita a mao. `depends_on_checks` NAO e: ele e derivado de
`consumed_by_kpis` no catalogo de checks, porque duas listas que descrevem a
mesma relacao em lugares diferentes divergem, e a divergencia e silenciosa.

    catalogo de checks                contrato de KPI
    check.consumed_by_kpis   ---->    kpi.depends_on_checks
                             (derivado, nunca digitado)

`verify` reprova nos dois sentidos: check consumido por KPI inexistente, e
contrato apontando para check que nao existe. `sync` regrava a derivacao.
"""
from __future__ import annotations

import collections
from pathlib import Path

import yaml

from generator.config import Config


def catalog(cfg: Config) -> dict:
    with open(Path(cfg.root) / "config" / "quality_checks.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _dir(cfg: Config) -> Path:
    return Path(cfg.root) / "config" / "kpis"


def load(cfg: Config) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(_dir(cfg).glob("*.yaml")):
        with open(p, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        out[doc["kpi_id"]] = doc
    return out


def derive_checks(cfg: Config) -> dict[str, list[str]]:
    """Inverte `consumed_by_kpis`: para cada KPI, os checks que o alimentam."""
    inv: dict[str, list[str]] = collections.defaultdict(list)
    for c in catalog(cfg)["checks"]:
        for k in c.get("consumed_by_kpis") or []:
            inv[k].append(c["check_id"])
    return {k: sorted(v) for k, v in inv.items()}


def verify(cfg: Config) -> list[str]:
    """Devolve as inconsistencias entre catalogo e contratos. Vazio e o esperado."""
    cat = catalog(cfg)
    contratos = load(cfg)
    derivado = derive_checks(cfg)
    ids = {c["check_id"] for c in cat["checks"]}
    problemas: list[str] = []

    # 1. check orfao: nao alimenta KPI nenhum (ADR-0011)
    for c in cat["checks"]:
        if not (c.get("consumed_by_kpis") or []) and not c.get("observability_only"):
            problemas.append(f"check orfao, nao consumido por nenhum KPI: {c['check_id']}")

    # 2. check declarado para KPI que nao tem contrato
    for kpi in derivado:
        if kpi not in contratos:
            problemas.append(f"checks apontam para KPI sem contrato: {kpi}")

    # 3. contrato apontando para check inexistente, ou desalinhado da derivacao
    for kpi, doc in contratos.items():
        declarado = list(doc.get("depends_on_checks") or [])
        for cid in declarado:
            if cid not in ids:
                problemas.append(f"{kpi} depende de check inexistente: {cid}")
        esperado = derivado.get(kpi, [])
        if sorted(declarado) != esperado:
            faltando = sorted(set(esperado) - set(declarado))
            sobrando = sorted(set(declarado) - set(esperado))
            problemas.append(
                f"{kpi}: depends_on_checks fora de sincronia com o catalogo"
                + (f"; faltando {faltando}" if faltando else "")
                + (f"; sobrando {sobrando}" if sobrando else ""))
        if not doc.get("depends_on_mappings"):
            problemas.append(f"{kpi}: sem depends_on_mappings declarado")
        if not doc.get("minimum_n"):
            problemas.append(f"{kpi}: sem minimum_n declarado (ADR-0007)")
    return problemas


def sync(cfg: Config) -> list[str]:
    """Regrava `depends_on_checks` em cada contrato a partir do catalogo."""
    derivado = derive_checks(cfg)
    alterados = []
    for p in sorted(_dir(cfg).glob("*.yaml")):
        texto = p.read_text(encoding="utf-8")
        cabecalho = "".join(l for l in texto.splitlines(keepends=True) if l.startswith("#"))
        doc = yaml.safe_load(texto)
        novo = derivado.get(doc["kpi_id"], [])
        if list(doc.get("depends_on_checks") or []) == novo:
            continue
        doc["depends_on_checks"] = novo
        p.write_text(cabecalho + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                     encoding="utf-8")
        alterados.append(doc["kpi_id"])
    return alterados
