"""F2 Defect Coverage & Reconciliation Report.

Reconcilia tres fontes que descrevem os mesmos defeitos e que podem divergir:

1. `config/defects.yaml`, o que o catalogo **declara**;
2. `config/sources.yaml`, o que cada sistema **diz que carrega**;
3. o ledger da projecao, o que de fato **aconteceu** no RAW.

Divergencia entre as tres e exatamente o tipo de erro que a F2 encontrou (ver
ADR-0008, Emenda 1), entao o relatorio e gerado por codigo e faz parte da
esteira, em vez de ser escrito a mao e envelhecer.

Distincao que o relatorio torna explicita, e que virou achado critico da F2:
**tentativa registrada nao e corrupcao observada**. Um registro pode ser
oferecido ao defeito, sortear positivo, e ainda assim sair identico do outro
lado se a funcao de injecao nao garantir mudanca. Quando isso acontece, o ledger
mente a favor do gerador, e o gabarito fica corrompido em silencio.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .projection import WAVE_1
from .projection.base import Ledger

# Mapa defeito -> validacoes ESPECIFICAS da camada RAW.
# As genericas (R01 catalogo, R02 sistema declarado, R03 onda, R04 cobertura,
# R07 calibragem) valem para todos e nao entram aqui.
RAW_CHECKS: dict[str, list[str]] = {
    "D01": ["R06", "R12"],
    "D02": ["R05", "R11"],
    "D05": ["R14"],
    "D06": ["R08"],
    "D11": ["R16"],
    "D12": ["R14"],
    "D23": ["R10"],
}

# Defeitos que NAO sao injetados: eles ja sao fato do mundo gerado na F1 e a
# projecao apenas os registra. Confundi-los com injecao inflaria a contagem de
# corrupcao e mentiria sobre o que o gerador fez.
OBSERVED_NOT_INJECTED = {"D02", "D03", "D16"}

# Defeitos que sao propriedade do formato do sistema, aplicados a 100% dos
# registros, sem sorteio por linha.
FORMAT_WIDE = {"D01", "D05", "D07", "D12", "D23", "D_DEFINITION_DRIFT"}

SEVERITY_TEXT = {
    "structural": "BLOCKER, vai para quarentena",
    "semantic": "CRITICAL, exige DE/PARA ou derruba trust score",
    "cosmetic": "WARNING, resolvido na padronizacao",
}


def _num(n: int) -> str:
    """Separador de milhar no padrao pt-BR, sem tocar em nada mais da linha."""
    return f"{n:,}".replace(",", ".")


def _incidents(spec: dict) -> str:
    inc = spec.get("root_cause_incident")
    if isinstance(inc, list):
        return ", ".join(inc)
    if inc:
        return str(inc)
    return spec.get("root_cause", "") or "-"


def compute(cfg: Config, ledger: Ledger) -> dict:
    calib = ledger.calibration()
    led = ledger.to_frame()

    attempts_by: dict[str, int] = {}
    expected_by: dict[str, float] = {}
    for c in calib:
        attempts_by[c["defect_id"]] = attempts_by.get(c["defect_id"], 0) + c["eligible"]
        expected_by[c["defect_id"]] = expected_by.get(c["defect_id"], 0.0) + c["expected_rate"] * c["eligible"]

    corrupted_by: dict[str, int] = {}
    applied_by: dict[str, set[str]] = {}
    if led.height:
        for r in led.select(["defect_id", "source_system"]).to_dicts():
            corrupted_by[r["defect_id"]] = corrupted_by.get(r["defect_id"], 0) + 1
            applied_by.setdefault(r["defect_id"], set()).add(r["source_system"])

    rows: list[dict] = []
    for spec in cfg.defects["defects"]:
        did = spec["id"]
        declared = spec.get("source_systems", [])
        wave = 1 if any(s in WAVE_1 for s in declared) else 2
        att = attempts_by.get(did, 0)
        cor = corrupted_by.get(did, 0)
        exp = (expected_by.get(did, 0.0) / att) if att else None
        obs = (cor / att) if att else None

        # taxa declarada, para defeitos que nao passam por sorteio
        declarada = spec.get("rate")
        if declarada is None and "rate_range" in spec:
            lo, hi = spec["rate_range"]
            declarada = (lo + hi) / 2
        if declarada is None and "rate_by_country" in spec:
            v = list(spec["rate_by_country"].values())
            declarada = sum(v) / len(v)

        # defeitos de contagem absoluta (D06, D22) nao tem taxa: o alvo e um
        # numero de registros, escalado pelo perfil ativo
        alvo_abs = None
        if spec.get("rate_type") == "absolute":
            n = (spec.get("scope") or {}).get("absolute_count")
            if n:
                alvo_abs = max(1, int(round(n * cfg.scale)))

        if wave == 2:
            status = "ONDA_2"
        elif did in OBSERVED_NOT_INJECTED and att == 0:
            status = "OBSERVADO_NA_VERDADE"
        elif did in FORMAT_WIDE and att == 0:
            status = "DETERMINISTICO_100%"
        elif att == 0 and cor > 0:
            status = "DETERMINISTICO"
        elif att == 0 and cor == 0:
            status = "NAO_APLICADO"
        elif att < 200:
            status = "SEM_AMOSTRA"
        else:
            sd = (exp * (1 - exp) / att) ** 0.5 if exp and exp < 1 else 0.0
            tol = max(3 * sd, 0.20 * (exp or 0))
            status = "OK" if abs((obs or 0) - (exp or 0)) <= tol else "FORA"

        raw_checks = RAW_CHECKS.get(did, [])
        if wave == 2:
            e2e = "PENDENTE, sistema da onda 2"
        elif did in OBSERVED_NOT_INJECTED:
            e2e = "OBSERVADO, nao injetado; deteccao por DQ so na F5"
        elif cor == 0:
            e2e = "SEM INJECAO"
        elif not raw_checks:
            e2e = "PARCIAL, injetado e calibrado, sem verificacao especifica no RAW"
        else:
            e2e = "PARCIAL, injetado, calibrado e verificado no RAW; deteccao por DQ so na F5"

        rows.append(dict(
            defect_id=did, name=spec.get("name", ""), dimension=spec.get("dimension", ""),
            kind=spec.get("kind", ""), severity=SEVERITY_TEXT.get(spec.get("kind", ""), "-"),
            wave=wave,
            declared_systems=declared,
            applied_systems=sorted(applied_by.get(did, set())),
            attempts=att, corrupted=cor,
            expected_rate=round(exp, 5) if exp is not None else None,
            observed_rate=round(obs, 5) if obs is not None else None,
            declared_rate=round(declarada, 5) if declarada is not None else None,
            expected_absolute=alvo_abs,
            calibration_status=status,
            incidents=_incidents(spec),
            dq_checks_planned=spec.get("detected_by", []),
            raw_checks=raw_checks,
            e2e_status=e2e,
        ))

    resumo = {
        "total": len(rows),
        "onda_1": sum(1 for r in rows if r["wave"] == 1),
        "onda_2": sum(1 for r in rows if r["wave"] == 2),
        "injetados": sum(1 for r in rows if r["corrupted"] > 0),
        "calibracao_ok": sum(1 for r in rows if r["calibration_status"] == "OK"),
        "calibracao_fora": sum(1 for r in rows if r["calibration_status"] == "FORA"),
        "deterministicos": sum(1 for r in rows if r["calibration_status"].startswith("DETERMINISTICO")),
        "observados_na_verdade": sum(1 for r in rows if r["calibration_status"] == "OBSERVADO_NA_VERDADE"),
        "amostrados": sum(1 for r in rows if r["attempts"] > 0),
        "sem_verificacao_raw": sorted(r["defect_id"] for r in rows
                                      if r["wave"] == 1 and r["corrupted"] > 0 and not r["raw_checks"]),
        "sem_injecao_na_onda_1": sorted(r["defect_id"] for r in rows
                                        if r["wave"] == 1 and r["corrupted"] == 0),
        "ocorrencias_no_ledger": int(led.height),
        "tentativas_no_ledger": len(ledger.attempts),
        "rates_status": cfg.defects["meta"].get("rates_status"),
        "freeze_phase": cfg.defects["meta"].get("freeze_phase"),
    }
    return {"resumo": resumo, "defeitos": rows}


# --------------------------------------------------------------------------- #
def to_markdown(cfg: Config, data: dict) -> str:
    r, rows = data["resumo"], data["defeitos"]
    L: list[str] = []
    L.append("# F2 Defect Coverage & Reconciliation Report\n")
    L.append(f"Perfil `{cfg.profile}` (escala {cfg.scale:.0%}), seed `{cfg.seed}`. "
             f"Onda 1: {', '.join(WAVE_1)}.\n")
    L.append(f"> Taxas **{r['rates_status']}**, congelamento previsto para a "
             f"**{r['freeze_phase']}** (ADR-0008, Emenda 2).\n")

    L.append("\n## Resumo\n")
    L.append("| | |")
    L.append("|---|---|")
    L.append(f"| Defeitos no catalogo | {r['total']} |")
    L.append(f"| Previstos para a onda 1 | {r['onda_1']} |")
    L.append(f"| Adiados para a onda 2 | {r['onda_2']} |")
    L.append(f"| Efetivamente injetados | {r['injetados']} |")
    L.append(f"| Calibragem OK | {r['calibracao_ok']} |")
    L.append(f"| Calibragem fora | {r['calibracao_fora']} |")
    L.append(f"| Deterministicos (sem sorteio) | {r['deterministicos']} |")
    L.append(f"| Observados na verdade (nao injetados) | {r['observados_na_verdade']} |")
    L.append(f"| Amostrados por sorteio | {r['amostrados']} |")
    L.append(f"| Tentativas registradas | {_num(r['tentativas_no_ledger'])} |")
    L.append(f"| Corrupcoes observadas | {_num(r['ocorrencias_no_ledger'])} |")

    L.append("\n## Cobertura e reconciliacao, defeito a defeito\n")
    L.append("| ID | Nome | Dimensao | Severidade | Sistemas declarados | Sistemas aplicados | Tentativas | Corrompidos | Esperado | Observado | Calibragem |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for d in rows:
        if d["expected_absolute"] is not None:
            exp = f"{_num(d['expected_absolute'])} registros"
            obs = f"{_num(d['corrupted'])} registros"
        else:
            exp = (f"{d['expected_rate']:.2%}" if d["expected_rate"] is not None else
                   (f"{d['declared_rate']:.2%}" if d["declared_rate"] is not None else "-"))
            obs = f"{d['observed_rate']:.2%}" if d["observed_rate"] is not None else "-"
        decl = ", ".join(d["declared_systems"]) or "-"
        apl = ", ".join(d["applied_systems"]) or "-"
        L.append(f"| {d['defect_id']} | {d['name']} | {d['dimension']} | {d['kind']} | {decl} | {apl} | "
                 f"{_num(d['attempts'])} | {_num(d['corrupted'])} | {exp} | {obs} | {d['calibration_status']} |")

    L.append("\n## Incidentes de origem e deteccao planejada\n")
    L.append("| ID | Incidente ou pratica de origem | Checks de DQ previstos (F5) | Validacoes no RAW (F2) | Status end-to-end |")
    L.append("|---|---|---|---|---|")
    for d in rows:
        L.append(f"| {d['defect_id']} | {d['incidents']} | {', '.join(d['dq_checks_planned']) or '-'} | "
                 f"{', '.join(d['raw_checks']) or '-'} | {d['e2e_status']} |")

    L.append("\n## Lacunas conhecidas\n")
    onda2 = [d for d in rows if d["wave"] == 2]
    L.append(f"**Onda 2 ({len(onda2)} defeitos).** Dependem de sistemas que so entram depois da F5:\n")
    for d in onda2:
        L.append(f"- `{d['defect_id']}` {d['name']}, em {', '.join(d['declared_systems'])}")

    sem_raw = r["sem_verificacao_raw"]
    L.append(f"\n**Sem verificacao especifica no RAW ({len(sem_raw)} defeitos).** Estao injetados e "
             "calibrados, e sao cobertos apenas pelas validacoes genericas R01 a R04 e R07. "
             "A verificacao especifica deles acontece na F5, quando os checks de DQ existirem.\n")
    for did in sem_raw:
        nome = next(d["name"] for d in rows if d["defect_id"] == did)
        L.append(f"- `{did}` {nome}")

    sem_inj = r["sem_injecao_na_onda_1"]
    if sem_inj:
        L.append(f"\n**Previstos para a onda 1 e sem injecao ({len(sem_inj)}).** "
                 "Se algum aparecer aqui, e bug e nao escopo.\n")
        for did in sem_inj:
            L.append(f"- `{did}`")
    else:
        L.append("\n**Nenhum defeito previsto para a onda 1 ficou sem injecao.**")

    L.append("\n## Nota sobre tentativa versus corrupcao\n")
    L.append("O ledger conta duas coisas diferentes de proposito:\n")
    L.append("- **tentativa**: um registro foi oferecido ao defeito, com a taxa esperada daquele "
             "momento, ja considerando escopo temporal, picos por incidente e taxa por pais;")
    L.append("- **corrupcao observada**: o valor gravado no RAW ficou de fato diferente do "
             "valor verdadeiro.\n")
    L.append("As duas so coincidem se a funcao de injecao garantir mudanca. A F2 encontrou um caso "
             "em que nao garantia, e o efeito era o pior possivel: o ledger registrava corrupcao que "
             "nao existia no arquivo, ou seja, o **gabarito ficava errado a favor do gerador**. "
             "Ver `docs/f2_validation_findings.md`, achado 1.\n")
    return "\n".join(L) + "\n"


def write(cfg: Config, ledger: Ledger) -> Path:
    data = compute(cfg, ledger)
    docs = Path(cfg.root) / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "f2_defect_coverage.md").write_text(to_markdown(cfg, data), encoding="utf-8")
    with open(docs / "f2_defect_coverage.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
    return docs / "f2_defect_coverage.md"
