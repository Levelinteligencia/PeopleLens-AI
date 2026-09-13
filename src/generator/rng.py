"""Geracao de numeros aleatorios deterministica e derivada.

Regra do ADR-0001 / Technical Design R9: nada de estado aleatorio global.
Cada modulo, e quando faz sentido cada entidade, recebe um gerador proprio
derivado de hash(master_seed, nome_do_modulo, id_da_entidade). Isso da duas
propriedades:

  1. `make data SEED=42` reproduz o mesmo universo byte a byte;
  2. e possivel regerar uma parte sem alterar o resto.
"""
from __future__ import annotations

import hashlib

import numpy as np


def derive_seed(master_seed: int, module: str, entity: str | int = "") -> int:
    payload = f"{master_seed}|{module}|{entity}".encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big")


def generator(master_seed: int, module: str, entity: str | int = "") -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(derive_seed(master_seed, module, entity)))


class RngBook:
    """Carteira de geradores por modulo, para nao espalhar seeds pelo codigo."""

    def __init__(self, master_seed: int) -> None:
        self.master_seed = master_seed
        self._cache: dict[tuple[str, str | int], np.random.Generator] = {}

    def get(self, module: str, entity: str | int = "") -> np.random.Generator:
        key = (module, entity)
        if key not in self._cache:
            self._cache[key] = generator(self.master_seed, module, entity)
        return self._cache[key]
