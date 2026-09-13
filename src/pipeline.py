"""Orquestrador do pipeline da F3.

    python -m pipeline

Sequencia (ADR-0003):

    L0 raw (imutavel)
      -> L1 standardized   forma: encoding, espaco, data, numero
      -> L2 conformed      DE/PARA aprovado + identidade
      -> qualidade         checks com severidade
      -> quarentena        desvio lateral dos reprovados por BLOCKER
      -> analitico-ready   o que sobrou, pronto para a F6

  transversal: profiling, data_quality_results, data_lineage, transformation_log
  lateral:     mapping_exceptions, data_quarantine

O RAW nunca e escrito por este processo. Se algum modulo tentar, o teste
`test_raw_permanece_imutavel` quebra.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import polars as pl

import compare_truth
from cleaning import standardize
from instrumentation import Timer
from generator import config
from ingestion import profiling, readers
from lineage import Lineage
from mapping import identity, proposal
from mapping.depara import ExceptionQueue, apply_all
from mapping.resolution import Governance
from analytics import contracts, trust
from quality import quarantine as quar
from quality import runner


def _manifesto(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _catalogo_semantico(cfg) -> dict:
    """Estado do KPI Catalog da F7: status, bloqueadores e governanca.

    Importado aqui dentro porque a camada semantica depende de DuckDB, e o
    pipeline precisa rodar mesmo onde ela nao estiver instalada. Quando falta,
    o resumo diz que nao foi verificado — nunca que esta OK.
    """
    try:
        from analytics.semantic import catalog as semcat
    except ImportError as e:                      # pragma: no cover
        return {"verificado": False, "motivo": str(e)}
    cat = semcat.load(cfg)
    por_status: dict[str, list[str]] = {}
    for kpi in cat.kpis.values():
        por_status.setdefault(kpi.status, []).append(kpi.kpi_id)
    return {
        "verificado": True,
        "total": len(cat.ids),
        "por_status": {k: sorted(v) for k, v in sorted(por_status.items())},
        "bloqueadores": {k.kpi_id: [b["motivo"] for b in k.bloqueadores]
                         for k in cat.por_status("BLOCKED")},
        "inconsistencias": semcat.verify(cfg),
    }


def check_provenance(cfg) -> dict:
    """Verifica que as camadas comparaveis vieram da MESMA execucao.

    Achado 1 da F3: com o RAW de uma execucao e a verdade de outra, a comparacao
    contra o gabarito produz numeros sem sentido e ninguem percebe, porque os
    dois lados existem e tem a forma certa. O manifesto ja carregava seed,
    perfil e config_hash; faltava alguem conferir.

    A F6 acrescenta a camada analitica, cujas nove tabelas tem o mesmo nome das
    nove da camada de verdade. Por isso o controle guarda **tres pares** e nao
    um (ADR-0024, decisao 5): raw x verdade, raw x analitico, verdade x
    analitico.
    """
    root = Path(cfg.root)
    camadas = {
        "raw": _manifesto(root / "data" / "raw" / "manifest.json"),
        "verdade": _manifesto(root / "data" / "synthetic" / "truth" / "manifest.json"),
        "analitico": _manifesto(root / "data" / "processed" / "analytical" / "manifest.json"),
    }
    pares, divergentes, indisponiveis = {}, [], []
    for a, b in (("raw", "verdade"), ("raw", "analitico"), ("verdade", "analitico")):
        ma, mb = camadas[a], camadas[b]
        if ma is None or mb is None:
            pares[f"{a} x {b}"] = "INDISPONIVEL"
            indisponiveis.append(f"{a} x {b}")
            continue
        dif = [k for k in ("seed", "profile", "scale") if ma.get(k) != mb.get(k)]
        pares[f"{a} x {b}"] = "OK" if not dif else f"DIVERGENTE em {dif}"
        if dif:
            divergentes.append(f"{a} x {b}")

    raw, tru = camadas["raw"], camadas["verdade"]
    if raw is None or tru is None:
        return {"status": "INDISPONIVEL", "pares": pares,
                "detalhe": "manifesto ausente em uma das camadas"}
    principal = [k for k in ("seed", "profile", "scale") if raw.get(k) != tru.get(k)]
    return {
        "status": "OK" if not principal else "DIVERGENTE",
        "seed": raw.get("seed"), "profile": raw.get("profile"), "scale": raw.get("scale"),
        "divergencias": principal, "pares": pares,
        "detalhe": ("RAW e verdade da mesma execucao" if not principal
                    else f"RAW e verdade divergem em {principal}; a comparacao com o gabarito nao vale")
                   + (f"; pares divergentes: {divergentes}" if divergentes else ""),
    }


def run(cfg=None, write: bool = True) -> dict:
    cfg = cfg or config.load()
    lin = Lineage()
    proveniencia = check_provenance(cfg)
    t0 = time.time()

    timer = Timer(run_id=lin.run_id, profile=cfg.profile, scale=cfg.scale)

    with timer.stage("ingestao"):
        staged = readers.ingest_all(cfg, lin)
    t_ing = time.time()

    with timer.stage("profiling", rows=sum(d.height for d in staged.values())):
        prof = profiling.profile_all(staged, lin)
        achados = profiling.findings(prof)
    t_prof = time.time()

    n_valores_antes = len(lin.values)
    with timer.stage("padronizacao", rows=sum(d.height for d in staged.values())) as st:
        std, parse_flags = standardize.standardize_all(cfg, staged, lin)
        st["values"] = len(lin.values) - n_valores_antes
    t_std = time.time()

    queue = ExceptionQueue(Path(cfg.root))
    queue.reset()
    n_valores_antes = len(lin.values)
    with timer.stage("depara", rows=sum(d.height for d in std.values())) as st:
        conformed, depara_resumo = apply_all(cfg, std, lin, queue)
        st["values"] = len(lin.values) - n_valores_antes
    with timer.stage("identidade", rows=sum(d.height for d in conformed.values())):
        xref = identity.build(cfg, conformed, lin)
    t_map = time.time()

    gov = Governance(cfg)
    novos_na_fila = gov.load_identity_queue(xref, run_id=lin.run_id)

    with timer.stage("qualidade", rows=sum(d.height for d in conformed.values())):
        dq, qua = runner.run_all(cfg, conformed, lin, xref=xref)
    with timer.stage("trust_score", rows=sum(d.height for d in conformed.values())):
        confianca = trust.compute(cfg, conformed, xref)
    analytical, quar_resumo = quar.split(conformed, qua)
    lin.object("layer", "conformed_approved", "layer", "conformed",
               "fatia aprovada da camada conformada, pos-quarentena (ADR-0024)", rows=sum(d.height for d in analytical.values()))
    t_dq = time.time()

    comparacao = (compare_truth.compare(cfg, conformed, analytical, xref)
                  if proveniencia["status"] == "OK"
                  else {"erro": proveniencia["detalhe"]})

    resumo = {
        "run_id": lin.run_id,
        "perfil": cfg.profile, "escala": cfg.scale, "seed": cfg.seed,
        "proveniencia": proveniencia,
        "linhas_por_camada": {
            "staged": sum(d.height for d in staged.values()),
            "standardized": sum(d.height for d in std.values()),
            "conformed": sum(d.height for d in conformed.values()),
            "conformed_approved": sum(d.height for d in analytical.values()),
        },
        "profiling": {"colunas": prof.height, "achados": len(achados)},
        "padronizacao": {"valores_transformados": len(lin.values),
                         "falhas_de_parse": parse_flags.height},
        "depara": depara_resumo,
        "excecoes_abertas": queue.open_frame().height,
        "excecoes_por_status": {k: v for k, v in queue.conn.execute(
            "SELECT status, COUNT(*) FROM mapping_exceptions GROUP BY status").fetchall()},
        "identidade": identity.summary(xref),
        "qualidade": quar.summary(dq, qua),
        "quarentena": quar_resumo,
        "contratos_de_kpi": {"total": len(contracts.load(cfg)),
                             "inconsistencias": contracts.verify(cfg)},
        # F7: governanca do catalogo semantico. Fica ao lado da verificacao de
        # contratos porque e a mesma pergunta uma camada acima — "o contrato
        # bate com a realidade?" — e porque uma inconsistencia aqui invalida
        # respostas, e nao apenas um numero.
        "catalogo_semantico": _catalogo_semantico(cfg),
        "trust_score": trust.summary(confianca),
        "lineage": lin.summary(),
        "governanca": {**gov.summary(lin.run_id), "identidade_novos_na_fila": novos_na_fila},
        "instrumentacao": {"por_etapa": timer.by_stage(),
                           "projecao_volume_completo": timer.projection(1.0)},
        "comparacao_verdade": comparacao,
        "tempos": {"ingestao": round(t_ing - t0, 1), "profiling": round(t_prof - t_ing, 1),
                   "padronizacao": round(t_std - t_prof, 1), "mapeamento": round(t_map - t_std, 1),
                   "qualidade": round(t_dq - t_map, 1), "total": round(time.time() - t0, 1)},
    }

    if write:
        root = Path(cfg.root)
        readers.write_staged(cfg, staged)
        profiling.write(root, prof)
        standardize.write(cfg, std)
        identity.write(cfg, xref)
        runner.write(cfg, dq, qua)
        lin.write(root)
        timer.write(root)
        base = root / "data" / "processed" / "conformed"
        base.mkdir(parents=True, exist_ok=True)
        for (system, dataset), df in conformed.items():
            d = base / system
            d.mkdir(parents=True, exist_ok=True)
            df.write_parquet(d / f"{dataset}.parquet", compression="zstd")
        ready = root / "data" / "processed" / "conformed_approved"
        for (system, dataset), df in analytical.items():
            d = ready / system
            d.mkdir(parents=True, exist_ok=True)
            df.write_parquet(d / f"{dataset}.parquet", compression="zstd")
        exc = queue.frame()
        if not exc.is_empty():
            exc.write_parquet(root / "data" / "processed" / "metadata" / "mapping_exceptions.parquet",
                              compression="zstd")
        meta = root / "data" / "processed" / "metadata"
        meta.mkdir(parents=True, exist_ok=True)
        trust.write(cfg, confianca)
        for nome, df in (("identity_decisions", gov.identity_queue()),
                         ("resolution_log", gov.log())):
            if not df.is_empty():
                df.write_parquet(meta / f"{nome}.parquet", compression="zstd")
        (root / "docs").mkdir(parents=True, exist_ok=True)
        proposal.write(cfg, queue.frame())
        with open(root / "docs" / "f3_pipeline.json", "w", encoding="utf-8") as fh:
            json.dump({"resumo": resumo, "profiling_findings": achados}, fh, indent=2,
                      ensure_ascii=False, default=str)

    return {"resumo": resumo, "achados": achados, "frames": {
        "staged": staged, "standardized": std, "conformed": conformed, "analytical": analytical,
        "profiling": prof, "dq": dq, "quarantine": qua, "xref": xref,
        "exceptions": queue.frame(), "parse_flags": parse_flags,
        "identity_queue": gov.identity_queue(), "resolution_log": gov.log(),
        "trust": confianca,
        "identity_stale": gov.identity_stale(lin.run_id)},
        "lineage": lin, "timer": timer, "governance": gov}


# --------------------------------------------------------------------------- #
def to_markdown(out: dict) -> str:
    r = out["resumo"]
    L: list[str] = []
    L.append("# PeopleLens, F3: pipeline de ingestao, padronizacao, DE/PARA e qualidade\n")
    L.append(f"Perfil `{r['perfil']}` (escala {r['escala']:.0%}), seed `{r['seed']}`, run `{r['run_id']}`.\n")
    L.append("> O RAW nao foi alterado. Nenhum valor foi corrigido em silencio: toda transformacao\n"
             "> esta em `transformation_log` com valor original, sistema de origem e regra aplicada.\n")
    pr = r.get("proveniencia", {})
    L.append(f"\nProveniencia: **{pr.get('status')}**, {pr.get('detalhe')}.\n")

    c = r["linhas_por_camada"]
    L.append("\n## Camadas\n")
    L.append("| Camada | Linhas | O que faz |")
    L.append("|---|---|---|")
    L.append(f"| L0 raw | (imutavel) | nada; so leitura |")
    L.append(f"| staged | {c['staged']:,} | copia fiel, tudo como texto, com `_row_id` |".replace(",", "."))
    L.append(f"| L1 standardized | {c['standardized']:,} | forma: encoding, espaco, data, numero |".replace(",", "."))
    L.append(f"| L2 conformed | {c['conformed']:,} | DE/PARA aprovado e identidade |".replace(",", "."))
    L.append(f"| conformed-approved | {c['conformed_approved']:,} | fatia aprovada da L2, pos-quarentena |".replace(",", "."))

    L.append("\n## Profiling\n")
    L.append(f"{r['profiling']['colunas']} colunas perfiladas, {r['profiling']['achados']} achados levantados "
             "sem ninguem dizer onde procurar.\n")
    ach = {}
    for a in out["achados"]:
        ach[a["tipo"]] = ach.get(a["tipo"], 0) + 1
    L.append("| Achado | Ocorrencias |")
    L.append("|---|---|")
    for k, v in sorted(ach.items(), key=lambda x: -x[1]):
        L.append(f"| {k.replace('_', ' ')} | {v} |")

    p = r["padronizacao"]
    L.append("\n## Padronizacao\n")
    L.append(f"{p['valores_transformados']:,} valores transformados, {p['falhas_de_parse']} falhas de conversao.\n".replace(",", "."))
    L.append("| Regra | Valores |")
    L.append("|---|---|")
    for rule, n in sorted(r["lineage"]["by_rule"].items(), key=lambda x: -x[1]):
        if rule.startswith("STD_"):
            L.append(f"| {rule} | {n:,} |".replace(",", "."))

    L.append("\n## DE/PARA\n")
    L.append("| Campo | Mapeados | Nao mapeados | Valores distintos sem mapa | Taxa |")
    L.append("|---|---|---|---|---|")
    for field, v in r["depara"].items():
        L.append(f"| {field} | {v['mapped']:,} | {v['unmapped']:,} | {v['distinct_unmapped']} | {v['unmapped_rate']:.2%} |".replace(",", "."))
    L.append(f"\n**{r['excecoes_abertas']} excecoes abertas** na fila, com sugestao e confianca. "
             "Nenhuma aplicada automaticamente (principio 5, ADR-0009).\n")

    i = r["identidade"]
    L.append("\n## Identidade\n")
    L.append("| Status | Registros |")
    L.append("|---|---|")
    for k, v in i.get("por_status", {}).items():
        L.append(f"| {k} | {v:,} |".replace(",", "."))
    L.append("\n| Sistema | Resolvidos | Total | Taxa |")
    L.append("|---|---|---|---|")
    for sysname, v in i.get("por_sistema", {}).items():
        L.append(f"| {sysname} | {v['resolvidos']:,} | {v['total']:,} | {v['taxa_resolucao']:.1%} |".replace(",", "."))

    q = r["qualidade"]
    L.append("\n## Qualidade\n")
    L.append(f"{q['checks_executados']} checks executados, {q['pass']} passaram, {q['fail']} falharam. "
             f"{q['quarentena']} registros em quarentena.\n")
    L.append("| Dimensao | Checks | Falhas |")
    L.append("|---|---|---|")
    for dim, v in q["por_dimensao"].items():
        L.append(f"| {dim} | {v['total']} | {v['fail']} |")
    if q["falhas"]:
        L.append("\n### Checks reprovados\n")
        L.append("| Check | Dataset | Severidade | Classe de achado | Taxa | Limite | Registros |")
        L.append("|---|---|---|---|---|---|---|")
        for f in q["falhas"]:
            L.append(f"| {f['check_id']} {f['name']} | {f['dataset']} | {f['severity']} | "
                     f"{f.get('finding_class', '-')} | {f['failure_rate']:.2%} | "
                     f"{f['threshold']:.2%} | {f['records_failed']} |")

    lin = r["lineage"]
    L.append("\n## Lineage\n")
    L.append(f"- {lin['objects']} relacoes entre objetos (camada por camada)")
    L.append(f"- {lin['value_transformations']:,} transformacoes de valor rastreadas individualmente".replace(",", "."))

    comp = r.get("comparacao_verdade", {})
    if comp and "erro" not in comp:
        L.append("\n## Comparacao com a camada de verdade\n")
        L.append("> Leitura correta: a F3 **nao corrige** nada. O que se mede e quanto da verdade ficou\n"
                 "> recuperavel apos padronizacao e DE/PARA, e quanto segue bloqueado esperando decisao.\n")
        L.append("| Campo | Comparados | Recuperados | Taxa | UNMAPPED | Divergentes |")
        L.append("|---|---|---|---|---|---|")
        for k, v in comp.get("campos", {}).items():
            if not v or not v.get("comparados"):
                continue
            L.append(f"| {k} | {v['comparados']:,} | {v['recuperados']:,} | {v['taxa_recuperacao']:.2%} | "
                     f"{v['unmapped']:,} | {v['divergentes']:,} |".replace(",", "."))
        va = comp.get("aquisicao_vivamarket")
        if va:
            L.append(f"\n**Aquisicao VivaMarket** ({va['comparados']} pessoas): job level recuperado "
                     f"{va['job_level_recuperado']:.1%}, sem mapa {va['job_level_unmapped']:.1%}; "
                     f"genero {va['gender_recuperado']:.1%}; departamento {va['department_recuperado']:.1%}.")
        hc = comp.get("headcount")
        if hc:
            L.append(f"\n**Headcount**: {hc['meses_comparados']} meses comparados, desvio medio absoluto "
                     f"{hc['desvio_medio_abs']:.3%}, maximo {hc['desvio_max_abs']:.3%}.")
        g = comp.get("gestores")
        if g:
            L.append(f"\n**Gestores orfaos remanescentes**: {g['orfaos_remanescentes']} de {g['registros']:,} "
                     f"({g['taxa']:.2%}). {g['nota']}.".replace(",", "."))
        ia = comp.get("identidade_aquisicao")
        if ia:
            L.append(f"\n**Identidade da aquisicao**: {ia['resolvidos_automaticamente']} resolvidos "
                     f"automaticamente, {ia['para_revisao_humana']} para revisao humana, "
                     f"{ia['ambiguos']} ambiguos. {ia['nota']}.")

    ts = r.get("trust_score", {})
    if ts:
        L.append("\n## Trust score\n")
        L.append("> O score e uma media ponderada unica sobre os checks que pesam, e a perda e\n"
                 "> **atribuida por natureza**: dado errado e uma coisa, decisao pendente e outra.\n"
                 "> Faixas provisorias; a calibragem contra a distribuicao alvo e da F7.\n")
        L.append(f"\n{ts['pares_kpi_recorte']} pares KPI x recorte avaliados, dos quais "
                 f"{ts['respondiveis']} respondiveis, {ts['suprimidos_por_n_minimo']} suprimidos por "
                 f"n minimo e {ts['indeterminados_sem_check_aplicavel']} sem nenhum check aplicavel "
                 "ao recorte (INDETERMINADO, que nao e o mesmo que aprovado).\n")
        L.append("| Status | Pares respondiveis | Share |")
        L.append("|---|---|---|")
        for st, n in sorted(ts.get("distribuicao", {}).items()):
            L.append(f"| {st} | {n} | {ts['distribuicao_pct'].get(st, 0):.1%} |")
        L.append("\n| Motivo principal da perda | Pares |")
        L.append("|---|---|")
        for m, n in sorted(ts.get("por_motivo", {}).items(), key=lambda x: -x[1]):
            L.append(f"| {m} | {n} |")
        L.append(f"\nTrust medio {ts['trust_medio']:.4f}. Perda media por **erro** "
                 f"{ts['perda_media_por_erro']:.5f}, por **pendencia** "
                 f"{ts['perda_media_por_pendencia']:.5f}: a confianca que falta neste dataset vem "
                 "majoritariamente de decisao em aberto, nao de dado errado.")

    kc = r.get("contratos_de_kpi", {})
    if kc:
        inc = kc.get("inconsistencias") or []
        L.append(f"\n{kc['total']} contratos de KPI com `depends_on_checks` e "
                 f"`depends_on_mappings` declarados (ADR-0011). "
                 + ("Nenhuma inconsistencia entre catalogo e contratos."
                    if not inc else f"**{len(inc)} inconsistencias**: {inc[:5]}"))

    g = r.get("governanca", {})
    if g:
        L.append("\n## Governanca das filas\n")
        L.append("> Duas filas, um ciclo de vida: `OPEN -> UNDER_REVIEW -> APPROVED | REJECTED`.\n"
                 "> Nao existe funcao de aprovacao em lote por limiar de confianca, e a ausencia\n"
                 "> dela e verificada por teste.\n")
        L.append("\n| Fila | Estado | Itens |")
        L.append("|---|---|---|")
        for estado, n in sorted(g.get("mapping_exceptions", {}).items()):
            L.append(f"| mapeamento | {estado} | {n:,} |".replace(",", "."))
        for estado, n in sorted(g.get("identity_decisions", {}).items()):
            L.append(f"| identidade | {estado} | {n:,} |".replace(",", "."))
        n_log = g.get("resolution_log", 0)
        L.append(f"\n{n_log} transicoes registradas em `resolution_log`"
                 + (", todas com responsavel, justificativa e data." if n_log else
                    ". A F4 entrega o mecanismo; promover qualquer mapeamento agora "
                    "contrariaria \"nenhuma promocao automatica\"."))
        stale = g.get("identidade_nao_observada_nesta_execucao", 0)
        if stale:
            L.append(f"\n{stale:,} casos de identidade continuam OPEN sem terem sido observados nesta "
                     .replace(",", ".")
                     + "execucao, e sao residuo de execucoes anteriores em outro perfil. Nao foram "
                       "apagados: sumir da base e um fato que merece visibilidade, nao delecao "
                       "silenciosa (ADR-0021).")

    ins = r.get("instrumentacao", {})
    if ins:
        L.append("\n## Custo de execucao\n")
        L.append("> Medicao pedida na aprovacao da F3, item 4: instrumentar para permitir decisao\n"
                 "> futura baseada em evidencia. Nada foi otimizado aqui.\n")
        L.append("\n| Etapa | Segundos | us por linha | Valores rastreados |")
        L.append("|---|---|---|---|")
        for etapa, v in ins.get("por_etapa", {}).items():
            us = f"{v['us_per_row']:.2f}" if v.get("us_per_row") else "-"
            L.append(f"| {etapa} | {v['seconds']:.2f} | {us} | {v['values']:,} |".replace(",", "."))
        pj = ins.get("projecao_volume_completo", {})
        if pj:
            L.append(f"\nProjecao para volume completo (fator {pj['fator']:.0f}x): "
                     f"{pj['minutos_projetados']:.1f} minutos. Ressalva: {pj['ressalva']}.")

    t = r["tempos"]
    L.append(f"\n## Tempos\n\ningestao {t['ingestao']}s, profiling {t['profiling']}s, "
             f"padronizacao {t['padronizacao']}s, mapeamento {t['mapeamento']}s, "
             f"qualidade {t['qualidade']}s. Total {t['total']}s.\n")
    return "\n".join(L) + "\n"


def main() -> int:
    out = run()
    report = Path(config.load().root) / "docs" / "f3_pipeline.md"
    report.write_text(to_markdown(out), encoding="utf-8")
    r = out["resumo"]
    q = r["qualidade"]
    print(f"run {r['run_id']} | perfil {r['perfil']} escala {r['escala']:.0%}")
    pr = r["proveniencia"]
    print(f"proveniencia: {pr['status']} ({pr['detalhe']})")
    print(f"camadas: staged {r['linhas_por_camada']['staged']:,} -> "
          f"conformed-approved {r['linhas_por_camada']['conformed_approved']:,}")
    print(f"profiling: {r['profiling']['colunas']} colunas, {r['profiling']['achados']} achados")
    print(f"padronizacao: {r['padronizacao']['valores_transformados']:,} valores transformados")
    print(f"DE/PARA: {r['excecoes_abertas']} excecoes abertas")
    print(f"identidade: {r['identidade']['por_status']}")
    print(f"qualidade: {q['pass']}/{q['checks_executados']} passaram, {q['quarentena']} em quarentena")
    for f in q["falhas"]:
        print(f"  FALHOU {f['check_id']} [{f['severity']}] {f['name']} "
              f"({f['failure_rate']:.2%} > {f['threshold']:.2%})")
    print(f"lineage: {r['lineage']['objects']} objetos, "
          f"{r['lineage']['value_transformations']:,} valores")
    print(f"relatorio: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
