"""Chaves substitutas e membros reservados (ADR-0025).

Duas regras governam este modulo.

**Nenhuma chave estrangeira e nula.** Um `join` que nao encontra a chave produz
nulo, e nulo nao tem classe, nao tem motivo e nao e contavel. Tres coisas muito
diferentes — `N4` da VivaMarket, um departamento sem mapa e alguem que optou por
nao declarar raca — chegariam a camada semantica como a mesma coisa: vazio.
Por isso cada dimensao carrega membros reservados, com chave negativa, nomeados,
e com a classe de achado da F5 ao lado.

**Identidade nao resolvida e a excecao** (ADR-0025, Emenda 1). Ela nao vira
membro reservado: vira pessoa provisoria, com `party_key` no escopo da fonte.
Pendencia de mapeamento e de decisao viram membro; pendencia de *vinculo* vira
uma pessoa a mais, porque a pessoa existe e precisa ser contavel. Sem isso, os
320 registros da VivaMarket colapsariam num membro unico e deixariam de ser
pessoas.
"""
from __future__ import annotations

import polars as pl

# Membros reservados, por dimensao. A chave negativa e visivel numa leitura
# rapida e nao colide com chave substituta gerada por sequencia.
RESERVED: dict[str, list[dict]] = {
    "dim_employee": [
        {"sk": -1, "code": "SEM_CHAVE_DE_ORIGEM", "label": "registro sem chave de origem utilizavel",
         "finding_class": None},
        {"sk": -4, "code": "FORA_DO_UNIVERSO", "label": "fora do universo conhecido",
         "finding_class": None},
    ],
    "dim_organization": [
        {"sk": -1, "code": "UNMAPPED", "label": "sem mapeamento aprovado",
         "finding_class": "NAO_MAPEADO"},
        {"sk": -2, "code": "DECISAO_PENDENTE", "label": "decisao de negocio pendente",
         "finding_class": "DECISAO_PENDENTE"},
        {"sk": -3, "code": "TRADUCAO_PENDENTE", "label": "traducao pendente",
         "finding_class": "NAO_MAPEADO"},
    ],
    "dim_job_level": [
        {"sk": -1, "code": "UNMAPPED", "label": "sem mapeamento aprovado",
         "finding_class": "NAO_MAPEADO"},
        {"sk": -2, "code": "DECISAO_PENDENTE", "label": "decisao de negocio pendente (N4, N5)",
         "finding_class": "DECISAO_PENDENTE"},
    ],
    "dim_calendar": [
        {"sk": -5, "code": "AINDA_NAO_OCORREU", "label": "marco ainda nao atingido",
         "finding_class": None},
        # o eixo cobre o periodo de analise declarado; uma data real fora dele
        # (admissao anterior a 2016) nao vira nulo nem estica o eixo, vira um
        # membro nomeado. A data em si continua na coluna de origem do fato.
        {"sk": -7, "code": "ANTERIOR_A_SERIE", "label": "anterior ao periodo de analise",
         "finding_class": None},
    ],
    "dim_source_system": [
        {"sk": -6, "code": "FORA_DE_VIGENCIA", "label": "fora da vigencia do sistema",
         "finding_class": "DESATUALIZADO"},
    ],
    "dim_origin": [
        {"sk": -1, "code": "INDETERMINADA", "label": "origem indeterminada",
         "finding_class": None},
    ],
}

UNMAPPED = "UNMAPPED"


def surrogate(df: pl.DataFrame, name: str, start: int = 1) -> pl.DataFrame:
    """Chave substituta por posicao, deterministica dentro de uma ordem dada.

    Nao usa hash: hash muda entre versoes de biblioteca, e chave que muda quebra
    a comparacao entre execucoes, que e um dos criterios de aceite.
    """
    return df.with_row_index(name=name, offset=start).with_columns(
        pl.col(name).cast(pl.Int64))


def reserved_frame(dim: str, schema: dict, sk_col: str,
                   defaults: dict | None = None) -> pl.DataFrame:
    """Linhas reservadas de uma dimensao, no esquema dela.

    `sk` do catalogo vai para a coluna de chave da dimensao; `code`, `label` e
    `finding_class` entram quando a dimensao tiver essas colunas. O resto fica
    nulo de proposito: um membro reservado nao tem atributo de negocio, ele
    **e** a ausencia de um.
    """
    # colunas de texto que so tem nulo na dimensao seriam inferidas como Null e
    # recusariam o rotulo do membro reservado; declaramos o tipo.
    schema = {c: (pl.Utf8 if (c in ("code", "label", "finding_class")
                              or t == pl.Null) else t)
              for c, t in schema.items()}
    linhas = []
    for m in RESERVED.get(dim, []):
        linha = {c: None for c in schema}
        linha.update(defaults or {})
        linha[sk_col] = m["sk"]
        for c in ("code", "label", "finding_class"):
            if c in schema:
                linha[c] = m[c]
        linhas.append(linha)
    if not linhas:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(linhas, schema=schema)


def party_key(source_system: str, source_id: str, employee_id, match_status: str) -> str:
    """A chave da pessoa analitica.

    `EMP:<employee_id>` quando a identidade foi RESOLVED pela governanca;
    `SRC:<sistema>:<id de origem>` em qualquer outro caso, que e a pessoa
    provisoria do ADR-0027, decisao 6.

    Nao faz matching: le o que o `xref` decidiu e nada mais.
    """
    if match_status == "RESOLVED" and employee_id is not None:
        return f"EMP:{employee_id}"
    return f"SRC:{source_system}:{source_id}"


def map_to_sk(df: pl.DataFrame, on: list[str], dim: pl.DataFrame,
              sk: str, fallback: int) -> pl.Series:
    """Resolve a chave estrangeira, com membro reservado no lugar de nulo."""
    j = df.join(dim.select(on + [sk]), on=on, how="left")
    return j[sk].fill_null(fallback)
