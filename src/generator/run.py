"""CLI da geracao.

    python -m generator.run --profile dev --seed 42

F1 gera SOMENTE a camada de verdade. Projecao em sistemas-fonte e injecao de
defeitos sao F2 e nao existem neste codigo.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import config, coverage, materialize, metrics, projection, validate, validate_raw
from .events.lifecycle import World


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gerador do ground truth da NOVAORA (F1)")
    ap.add_argument("--root", default=None, help="raiz do projeto")
    ap.add_argument("--profile", default=None, choices=["smoke", "dev", "full"], help="perfil de escala")
    ap.add_argument("--seed", type=int, default=None, help="sobrescreve o master_seed")
    ap.add_argument("--no-write", action="store_true", help="nao escreve parquet")
    ap.add_argument("--samples", type=int, default=1000, help="linhas por amostra versionada")
    ap.add_argument("--report", default="docs/f1_metrics.md", help="caminho do relatorio")
    ap.add_argument("--stage", default="truth", choices=["truth", "raw", "all"],
                    help="truth = so a camada de verdade (F1); raw = projecao nos sistemas-fonte (F2)")
    args = ap.parse_args(argv)

    cfg = config.load(args.root)
    if args.profile:
        cfg.generation["reproducibility"]["active_profile"] = args.profile
    if args.seed is not None:
        cfg.generation["reproducibility"]["master_seed"] = args.seed

    print(f"perfil={cfg.profile} escala={cfg.scale:.0%} seed={cfg.seed}")
    t0 = time.time()
    truth = World(cfg).run()
    t1 = time.time()
    tables = materialize.build_all(cfg, truth)
    t2 = time.time()
    checks = validate.run_all(cfg, tables)
    t3 = time.time()

    failed = [c for c in checks if not c.passed]
    for c in failed:
        marca = "FALHOU" if c.severity in ("BLOCKER", "CRITICAL") else "AVISO "
        print(f"  {marca} {c.check_id}: {c.name} | {c.detail}")
    passed, total = validate.summary(checks)
    bloqueantes = validate.blocking(checks)
    print(f"validacoes: {passed}/{total}" + (f" ({len(bloqueantes)} bloqueantes)" if bloqueantes else ""))

    m = metrics.compute(cfg, tables)

    if not args.no_write:
        manifest = materialize.write(cfg, tables)
        materialize.write_samples(cfg, tables, n=args.samples)
        report = Path(cfg.root) / args.report
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(metrics.to_markdown(cfg, m, checks), encoding="utf-8")
        with open(Path(cfg.root) / "docs" / "f1_metrics.json", "w", encoding="utf-8") as fh:
            json.dump(m, fh, indent=2, ensure_ascii=False, default=str)
        print(f"manifesto: {len(manifest['datasets'])} datasets, config_hash={manifest['config_hash']}")
        print(f"relatorio: {report}")

    print(f"tempos: simulacao {t1-t0:.1f}s | materializacao {t2-t1:.1f}s | validacao {t3-t2:.1f}s")

    if args.stage in ("raw", "all"):
        t4 = time.time()
        ledger, raw_manifest = projection.run(cfg, tables)
        t5 = time.time()
        raw_checks = validate_raw.run_all(cfg, tables, ledger)
        for c in raw_checks:
            if not c.passed:
                marca = "FALHOU" if c.severity in ("BLOCKER", "CRITICAL") else "AVISO "
                print(f"  {marca} {c.check_id}: {c.name} | {c.detail}")
        rp, rt = validate.summary(raw_checks)
        rb = validate.blocking(raw_checks)
        print(f"validacoes RAW: {rp}/{rt}" + (f" ({len(rb)} bloqueantes)" if rb else ""))
        print(f"ledger de defeitos: {raw_manifest['ledger_rows']} ocorrencias, "
              f"taxas {raw_manifest['rates_status']}")
        if not args.no_write:
            report = Path(cfg.root) / "docs" / "f2_projection.md"
            report.write_text(metrics.raw_to_markdown(cfg, raw_manifest, ledger, raw_checks), encoding="utf-8")
            cov = coverage.write(cfg, ledger)
            print(f"relatorio RAW: {report}")
            print(f"cobertura de defeitos: {cov}")
        print(f"tempos RAW: projecao {t5-t4:.1f}s | validacao {time.time()-t5:.1f}s")
        bloqueantes = bloqueantes + rb

    return 1 if bloqueantes else 0


if __name__ == "__main__":
    sys.exit(main())
