"""Proposta de resolucao das excecoes de mapeamento.

Este modulo NAO aprova nada. Ele classifica cada excecao aberta e produz um
documento pronto para decisao humana, com recomendacao e justificativa.

A classificacao existe porque tratar as 57 excecoes como uma lista homogenea
esconde a unica distincao que importa: algumas sao **variacao de escrita** e
outras sao **decisao de negocio**. Misturar as duas leva ou a aprovar tudo em
bloco, que e o erro que o principio 5 evita, ou a travar tudo esperando uma
decisao que a maioria dos casos nao precisa.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

import polars as pl

from generator.config import Config
from . import similarity
from .depara import load_approved

CLASSES = {
    "VARIANTE_DE_ESCRITA": "mesma palavra, escrita de outro jeito (acento, caixa, espaco, abreviacao)",
    "APELIDO_CONHECIDO": "sigla ou nome alternativo do mesmo conceito, com candidato unico e claro",
    "CANDIDATO_PROVAVEL": "candidato plausivel mas nao obvio; exige conferencia antes de aprovar",
    "DECISAO_DE_NEGOCIO": "o sistema de origem nao distingue o que a NOVAORA distingue; nao existe resposta tecnica",
    "TRADUCAO_PENDENTE": "origem e dominio corporativo estao em linguas diferentes; a similaridade nao e evidencia aqui",
    "CANDIDATO_FRACO": "nenhum candidato plausivel; sugestao do pipeline provavelmente errada",
}


def _strip(v: str) -> str:
    return unicodedata.normalize("NFKD", v or "").encode("ascii", "ignore").decode()


def _foreign_scales(cfg: Config) -> dict[str, set[str]]:
    """Escalas proprias declaradas pelos sistemas em sources.yaml.

    Um valor que pertence a uma escala estrangeira nao e erro de digitacao: e a
    organizacao adquirida usando o vocabulario dela. Isso muda a classificacao.
    """
    out: dict[str, set[str]] = {}
    for name, meta in cfg.sources["systems"].items():
        scale = meta.get("job_level_scale")
        if scale:
            out[name] = {str(v) for v in scale}
    return out


def _language(cfg: Config, system: str) -> tuple[str, str]:
    """Lingua declarada do sistema e lingua do dominio corporativo.

    Nenhuma das duas e inferida do dado: as duas estao em `sources.yaml`.
    """
    canonico = cfg.sources.get("meta", {}).get("canonical_field_language", "")
    origem = (cfg.sources["systems"].get(system, {}) or {}).get("field_language", "")
    return str(origem or ""), str(canonico or "")


def classify(cfg: Config, exceptions: pl.DataFrame) -> list[dict]:
    approved = load_approved(cfg)
    scales = _foreign_scales(cfg)
    out: list[dict] = []

    for e in exceptions.filter(pl.col("status") == "OPEN").to_dicts():
        field, valor, system = e["source_field"], e["source_value"], e["source_system"]
        table = approved.get(field, {})
        lang_origem, lang_canonico = _language(cfg, system)
        outra_lingua = bool(lang_origem and lang_canonico and lang_origem != lang_canonico)

        alvos = {rows[0]["source_value"]: rows[0]["standard_value"] for rows in table.values()}
        ranked = similarity.rank(valor, alvos, top=2)
        top1 = (ranked[0].score, ranked[0].value, ranked[0].method) if ranked else (0.0, None, "nenhum")
        top2 = (ranked[1].score, ranked[1].value) if len(ranked) > 1 else (0.0, None)
        via = ranked[0].via if ranked else ""
        gap = round(top1[0] - top2[0], 3)

        # escala propria de sistema adquirido
        if valor in scales.get(system, set()):
            classe = "DECISAO_DE_NEGOCIO"
            motivo = (f"`{valor}` pertence a escala propria de {system}. A escala de origem tem "
                      f"menos niveis que a da NOVAORA, entao um mesmo valor cobre mais de um nivel "
                      f"corporativo. Nao ha traducao correta, ha decisao de People Analytics.")
            recomendacao = "decidir com People Analytics; manter em excecao ate la"
        # mesma palavra sem acento e sem caixa
        elif any(_strip(valor).lower().replace(" ", "") == _strip(k).lower().replace(" ", "")
                 for k in alvos):
            classe = "VARIANTE_DE_ESCRITA"
            motivo = "identico a um valor ja aprovado depois de remover acento, caixa e espaco."
            recomendacao = f"aprovar como `{top1[1]}`"
        elif top1[0] >= 0.80 and gap >= 0.12:
            classe = "APELIDO_CONHECIDO"
            ponte = f" via o apelido ja aprovado `{via}`" if via and via != top1[1] else ""
            motivo = (f"candidato unico e destacado: `{top1[1]}`{ponte}, por {top1[2]}, com "
                      f"{top1[0]:.2f}, {gap:.2f} acima do segundo colocado.")
            recomendacao = f"aprovar como `{top1[1]}`"
        elif top1[0] >= 0.55 and gap < 0.12 and not outra_lingua:
            classe = "DECISAO_DE_NEGOCIO"
            motivo = (f"dois candidatos empatados: `{top1[1]}` ({top1[0]:.2f}) e `{top2[1]}` "
                      f"({top2[0]:.2f}). Similaridade nao desempata significado.")
            recomendacao = "decidir com a area dona do dado"
        # Abaixo do limiar de apelido conhecido, um valor em outra lingua nao tem
        # candidato: o que sobra da pontuacao e coincidencia de letras entre dois
        # vocabularios diferentes. `Controladoria` casando 0,61 com `Engineering`
        # nao e um candidato provavel, e um ruido com cara de evidencia.
        elif outra_lingua:
            classe = "TRADUCAO_PENDENTE"
            motivo = (f"{system} declara `{lang_origem}` e o dominio corporativo e "
                      f"`{lang_canonico}`. Nenhum apelido aprovado cobre `{valor}`, entao o melhor "
                      f"score ({top1[0]:.2f}, com `{top1[1]}`) mede semelhanca de letras entre "
                      f"linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**")
            recomendacao = "traduzir com quem conhece os dois vocabularios; nao decidir por score"
        elif top1[0] >= 0.55:
            classe = "CANDIDATO_PROVAVEL"
            motivo = (f"candidato provavel `{top1[1]}` por {top1[2]}, com {top1[0]:.2f}. "
                      f"Plausivel, e nao obvio o bastante para aprovar sem conferir.")
            recomendacao = f"conferir e, se confirmado, aprovar como `{top1[1]}`"
        else:
            classe = "CANDIDATO_FRACO"
            motivo = (f"melhor candidato e `{top1[1]}` com similaridade {top1[0]:.2f}, baixa demais. "
                      f"A sugestao do pipeline provavelmente esta errada.")
            recomendacao = "investigar a origem do valor antes de decidir"

        oferece_candidato = classe not in ("TRADUCAO_PENDENTE", "DECISAO_DE_NEGOCIO")
        out.append(dict(
            exception_id=e["exception_id"], source_system=system, source_field=field,
            source_value=valor, occurrences=e["occurrence_count"],
            source_language=lang_origem, canonical_language=lang_canonico,
            pipeline_suggestion=e["suggested_value"], pipeline_confidence=e["confidence_score"],
            best_candidate=top1[1] if oferece_candidato else None,
            best_score=round(top1[0], 3), best_method=top1[2] if oferece_candidato else "nao aplicavel",
            matched_alias=via if oferece_candidato else None,
            runner_up=top2[1], gap=gap,
            classe=classe, motivo=motivo, recomendacao=recomendacao,
        ))
    return sorted(out, key=lambda r: (r["classe"], -r["occurrences"]))


def to_markdown(cfg: Config, rows: list[dict]) -> str:
    por_classe: dict[str, list[dict]] = {}
    for r in rows:
        por_classe.setdefault(r["classe"], []).append(r)

    L: list[str] = []
    L.append("# F4: proposta de resolucao das excecoes de mapeamento\n")
    L.append("> **Nada aqui foi aplicado.** Este documento e insumo de decisao. A aprovacao\n"
             "> acontece por chamada explicita de `Governance.approve`, com valor padrao,\n"
             "> responsavel e justificativa, e escreve no arquivo de referencia versionado.\n")
    L.append(f"\n{len(rows)} excecoes abertas, classificadas em {len(por_classe)} grupos.\n")

    L.append("| Classe | Quantas | O que significa |")
    L.append("|---|---|---|")
    for classe, desc in CLASSES.items():
        L.append(f"| {classe} | {len(por_classe.get(classe, []))} | {desc} |")

    ordem = ["DECISAO_DE_NEGOCIO", "TRADUCAO_PENDENTE", "CANDIDATO_FRACO", "CANDIDATO_PROVAVEL",
             "APELIDO_CONHECIDO", "VARIANTE_DE_ESCRITA"]
    for classe in ordem:
        grupo = por_classe.get(classe)
        if not grupo:
            continue
        L.append(f"\n## {classe}\n")
        L.append(f"_{CLASSES[classe]}_\n")
        L.append("| Valor de origem | Sistema | Lingua | Campo | Ocorrencias | Melhor candidato | Casou com | Score | Criterio | Recomendacao |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in grupo:
            cand = f"`{r['best_candidate']}`" if r["best_candidate"] else "nenhum"
            alias = f"`{r['matched_alias']}`" if r.get("matched_alias") else "-"
            L.append(f"| `{r['source_value']}` | {r['source_system']} | {r['source_language'] or '-'} | "
                     f"{r['source_field']} | {r['occurrences']} | {cand} | {alias} | "
                     f"{r['best_score']:.2f} | {r['best_method']} | {r['recomendacao']} |")
        if classe in ("DECISAO_DE_NEGOCIO", "TRADUCAO_PENDENTE", "CANDIDATO_FRACO", "CANDIDATO_PROVAVEL"):
            L.append("\nJustificativa caso a caso:\n")
            for r in grupo:
                L.append(f"- **`{r['source_value']}`** ({r['occurrences']} ocorrencias): {r['motivo']}")

    L.append("\n## Como aprovar\n")
    L.append("```python")
    L.append("from mapping.resolution import Governance")
    L.append("g = Governance(cfg)")
    L.append('g.approve("HRIS_LEGACY|department|Mktg",')
    L.append('          standard_value="Marketing",')
    L.append('          by="sam",')
    L.append('          rationale="abreviacao usada no sistema legado para a mesma area")')
    L.append("```\n")
    L.append("Nao existe funcao de aprovacao em lote por limiar de confianca, e isso e deliberado "
             "(principio 5 da Especificacao, Technical Design R4). O custo assimetrico nao mudou: "
             "um valor nao mapeado e visivel e sai do numerador; um valor mapeado errado e invisivel "
             "e contamina o numerador.\n")
    return "\n".join(L) + "\n"


def write(cfg: Config, exceptions: pl.DataFrame) -> tuple[Path, list[dict]]:
    rows = classify(cfg, exceptions)
    docs = Path(cfg.root) / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    target = docs / "f4_mapping_proposal.md"
    target.write_text(to_markdown(cfg, rows), encoding="utf-8")
    return target, rows
