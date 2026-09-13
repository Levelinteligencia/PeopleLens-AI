"""Marca fisica de camada (ADR-0024, Emenda 1).

A camada de verdade em `data/synthetic/truth/` e a camada analitica em
`data/processed/analytical/` tem nove tabelas com o mesmo nome e a mesma forma,
descrevendo universos diferentes: uma e o gabarito, a outra e o que o pipeline
conseguiu reconstruir. A distancia entre as duas **e** a medida do projeto, e
confundi-las inverte o sentido da medida.

Caminho diferente nao basta: quem le um Parquet direto do disco nao passa pelo
schema de consulta. Por isso toda tabela das duas camadas carrega a coluna
`layer`, e a distincao vive **dentro** do arquivo.

`assert_layer` reprova na entrada de qualquer funcao que espere uma camada e
receba a outra. Ela existe porque o achado 1 da F3 foi exatamente isto: os dois
lados existiam, tinham a forma certa, e descreviam empresas diferentes.
"""
from __future__ import annotations

import polars as pl

LAYER_COLUMN = "layer"
TRUTH = "truth"
ANALYTICAL = "analytical"
LAYERS = (TRUTH, ANALYTICAL)


class LayerError(RuntimeError):
    pass


def stamp(df: pl.DataFrame, layer: str) -> pl.DataFrame:
    """Carimba a camada na tabela. Idempotente."""
    if layer not in LAYERS:
        raise LayerError(f"camada desconhecida: {layer}")
    if LAYER_COLUMN in df.columns:
        df = df.drop(LAYER_COLUMN)
    return df.with_columns(pl.lit(layer).alias(LAYER_COLUMN))


def assert_layer(df: pl.DataFrame, expected: str, nome: str = "") -> pl.DataFrame:
    """Falha se a tabela nao for da camada esperada.

    Tabela sem a coluna tambem falha: ausencia de marca nao vale como marca
    certa, pela mesma razao que um check que nao rodou nao vale como check que
    passou.
    """
    rotulo = f" ({nome})" if nome else ""
    if LAYER_COLUMN not in df.columns:
        raise LayerError(f"tabela sem coluna `{LAYER_COLUMN}`{rotulo}")
    vistos = set(df[LAYER_COLUMN].unique().to_list())
    if vistos != {expected}:
        raise LayerError(f"esperava camada `{expected}`{rotulo}, veio {sorted(vistos)}")
    return df
