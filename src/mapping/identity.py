"""Resolucao de identidade entre sistemas (ADR-0004).

Tres conceitos distintos, e confundi-los e a origem da maior parte dos erros de
headcount em empresa com mais de um sistema de RH:

| campo | significado | quem gera |
|---|---|---|
| `source_employee_id` | matricula no sistema de origem | o sistema-fonte |
| `employee_id` | identidade corporativa NOVAORA | este modulo |
| `employee_key` | chave substituta da versao SCD2 | a camada analitica |

Regra que vem do ADR-0004 e do principio 5: **resolucao automatica nunca promove
um match ambiguo**. Confianca alta melhora a sugestao, nao autoriza a decisao.
Um match por nome e data de admissao, mesmo unico, sai como `MANUAL_REVIEW` e
nao como `RESOLVED`.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

import polars as pl

from generator.config import Config

STATUS = ("RESOLVED", "AMBIGUOUS", "UNRESOLVED", "MANUAL_REVIEW")


def _norm_name(v: str | None) -> str:
    s = unicodedata.normalize("NFKD", v or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def build(cfg: Config, conformed: dict[tuple[str, str], pl.DataFrame], lineage) -> pl.DataFrame:
    now = datetime.utcnow().isoformat(timespec="seconds")
    rows: list[dict] = []
    n = 0

    # ------------------------------------------------------------------ ancora
    # O HRIS corporativo e o sistema de referencia: quem tem employee_id la,
    # tem identidade corporativa por definicao.
    core = conformed.get(("HRIS_CORE", "employee_master"))
    anchor: dict[int, dict] = {}
    if core is not None:
        for r in core.select(["employee_id", "full_name", "hire_date__iso", "source_employee_id"]).to_dicts():
            eid = _int(r["employee_id"])
            if eid is None:
                continue
            anchor[eid] = {"name": _norm_name(r["full_name"]), "hire": r["hire_date__iso"]}
            n += 1
            rows.append(dict(xref_id=f"X{n:07d}", source_system="HRIS_CORE",
                             source_employee_id=r["source_employee_id"], employee_id=eid,
                             match_method="exact_id", match_confidence=1.0,
                             match_status="RESOLVED", resolved_at=now, resolved_by="pipeline"))

    # O HRIS legado tambem era sistema de registro no seu periodo, e sua
    # MATRICULA e o mesmo identificador corporativo (sources.yaml declara
    # `has_enterprise_employee_id: true`). Ignorar isso derrubaria a taxa de
    # resolucao da folha nos anos anteriores a 2019 sem motivo real.
    leg0 = conformed.get(("HRIS_LEGACY", "employee_master"))
    if leg0 is not None:
        for r in leg0.select(["MATRICULA", "NOME", "DT_ADMISSAO__iso"]).to_dicts():
            mid = _int(r["MATRICULA"])
            if mid is None or mid in anchor:
                continue
            anchor[mid] = {"name": _norm_name(r["NOME"]), "hire": r["DT_ADMISSAO__iso"]}

    by_name: dict[str, list[int]] = {}
    by_name_hire: dict[tuple[str, str], list[int]] = {}
    for eid, meta in anchor.items():
        by_name.setdefault(meta["name"], []).append(eid)
        if meta["hire"]:
            by_name_hire.setdefault((meta["name"], meta["hire"]), []).append(eid)

    def add(system: str, src_id, employee_id, method: str, confidence: float, status: str) -> None:
        nonlocal n
        n += 1
        rows.append(dict(xref_id=f"X{n:07d}", source_system=system, source_employee_id=str(src_id),
                         employee_id=employee_id, match_method=method, match_confidence=confidence,
                         match_status=status, resolved_at=now if status == "RESOLVED" else None,
                         resolved_by="pipeline" if status == "RESOLVED" else None))

    # --------------------------------------------------------- HRIS legado
    leg = conformed.get(("HRIS_LEGACY", "employee_master"))
    if leg is not None:
        for r in leg.select(["MATRICULA", "NOME", "DT_ADMISSAO__iso"]).to_dicts():
            mid = _int(r["MATRICULA"])
            if mid is not None and mid in anchor:
                add("HRIS_LEGACY", r["MATRICULA"], mid, "exact_id", 1.0, "RESOLVED")
                continue
            # D22: recontratacao virou cadastro novo. Nome e data de admissao
            # dao um candidato, e um candidato nao basta para decidir.
            key = (_norm_name(r["NOME"]), r["DT_ADMISSAO__iso"])
            cands = by_name_hire.get(key, [])
            if len(cands) == 1:
                add("HRIS_LEGACY", r["MATRICULA"], cands[0], "name_hire_date", 0.85, "MANUAL_REVIEW")
            elif len(cands) > 1:
                add("HRIS_LEGACY", r["MATRICULA"], None, "name_hire_date", 0.85, "AMBIGUOUS")
            else:
                add("HRIS_LEGACY", r["MATRICULA"], None, "none", 0.0, "UNRESOLVED")

    # ---------------------------------------------------------------- folha
    pay = conformed.get(("PAYROLL_BR", "payroll_headcount_snapshot"))
    if pay is not None:
        vistos = set()
        for r in pay.select(["matricula_folha", "vinculo"]).to_dicts():
            mf = r["matricula_folha"]
            if mf in vistos:
                continue
            vistos.add(mf)
            m = re.fullmatch(r"F(\d+)", str(mf))
            if m and _int(m.group(1)) in anchor:
                add("PAYROLL_BR", mf, _int(m.group(1)), "pattern_id", 1.0, "RESOLVED")
            else:
                # terceiros e estagiarios de agencia (defeito D11) nao tem
                # contraparte no HRIS, e isso e correto, nao e falha de match
                add("PAYROLL_BR", mf, None, "none", 0.0, "UNRESOLVED")

    # ------------------------------------------------------------ aquisicao
    viva = conformed.get(("VIVAMARKET_LEGACY", "employee_master"))
    if viva is not None:
        for r in viva.select(["COD_FUNC", "NOME", "DT_ADM__iso"]).to_dicts():
            nome = _norm_name(r["NOME"])
            cands = by_name_hire.get((nome, r["DT_ADM__iso"]), [])
            if len(cands) == 1:
                add("VIVAMARKET_LEGACY", r["COD_FUNC"], cands[0], "name_hire_date", 0.85, "MANUAL_REVIEW")
            elif len(cands) > 1:
                add("VIVAMARKET_LEGACY", r["COD_FUNC"], None, "name_hire_date", 0.85, "AMBIGUOUS")
            else:
                homonimos = by_name.get(nome, [])
                if len(homonimos) == 1:
                    add("VIVAMARKET_LEGACY", r["COD_FUNC"], homonimos[0], "fuzzy_name", 0.60, "MANUAL_REVIEW")
                elif len(homonimos) > 1:
                    add("VIVAMARKET_LEGACY", r["COD_FUNC"], None, "fuzzy_name", 0.60, "AMBIGUOUS")
                else:
                    add("VIVAMARKET_LEGACY", r["COD_FUNC"], None, "none", 0.0, "UNRESOLVED")

    # ------------------------------------------------------------------ ATS
    ats = conformed.get(("ATS_CLOUD", "application"))
    if ats is not None:
        for r in ats.select(["candidate_id", "employee_id", "candidate_name"]).to_dicts():
            eid = _int(r["employee_id"])
            if eid is not None and eid in anchor:
                add("ATS_CLOUD", r["candidate_id"], eid, "exact_id", 1.0, "RESOLVED")
            else:
                nome = _norm_name(r["candidate_name"])
                cands = by_name.get(nome, [])
                if len(cands) == 1:
                    add("ATS_CLOUD", r["candidate_id"], cands[0], "fuzzy_name", 0.60, "MANUAL_REVIEW")
                elif len(cands) > 1:
                    add("ATS_CLOUD", r["candidate_id"], None, "fuzzy_name", 0.60, "AMBIGUOUS")
                else:
                    add("ATS_CLOUD", r["candidate_id"], None, "none", 0.0, "UNRESOLVED")

    # Suspeita de identidade duplicada (assinatura do defeito D22): duas
    # identidades corporativas distintas com o mesmo nome e a mesma data de
    # admissao. NAO sao fundidas aqui: viram suspeita para revisao humana.
    suspeitos = {k: v for k, v in by_name_hire.items() if len(v) > 1}
    for (nome, hire), ids in suspeitos.items():
        for eid in ids:
            add("*", eid, eid, "duplicate_identity_suspect", 0.80, "MANUAL_REVIEW")

    df = pl.DataFrame(rows, infer_schema_length=None)
    lineage.object("table", "conformed.xref_employee_identity", "dataset",
                   "conformed.*.employee_master",
                   "resolucao de identidade; ambiguo nunca e promovido automaticamente",
                   rows=df.height)
    return df


def summary(xref: pl.DataFrame) -> dict:
    if xref.is_empty():
        return {}
    out: dict = {"total": xref.height}
    out["por_status"] = dict(xref.group_by("match_status").len().sort("match_status").iter_rows())
    out["por_metodo"] = dict(xref.group_by("match_method").len().sort("match_method").iter_rows())
    por_sistema = {}
    for sysname in xref["source_system"].unique().to_list():
        sub = xref.filter(pl.col("source_system") == sysname)
        por_sistema[sysname] = {
            "total": sub.height,
            "resolvidos": sub.filter(pl.col("match_status") == "RESOLVED").height,
            "taxa_resolucao": round(sub.filter(pl.col("match_status") == "RESOLVED").height / sub.height, 4),
        }
    out["por_sistema"] = por_sistema
    return out


def write(cfg: Config, xref: pl.DataFrame) -> Path:
    base = Path(cfg.root) / "data" / "processed" / "conformed"
    base.mkdir(parents=True, exist_ok=True)
    xref.write_parquet(base / "xref_employee_identity.parquet", compression="zstd")
    return base / "xref_employee_identity.parquet"
