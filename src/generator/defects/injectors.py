"""Funcoes de injecao de defeito.

Cada funcao corrompe um valor de um jeito especifico e devolve o valor
corrompido. Quem chama e responsavel por registrar no ledger, porque so quem
chama sabe a chave do registro.

Regra do projeto (Especificacao secao 25): nenhuma funcao aqui e chamada "por
acaso". Toda chamada vem de um defeito do catalogo, que por sua vez aponta para
um incidente ou uma pratica declarada.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

# --------------------------------------------------------------------------- #
# D23: encoding quebrado
# --------------------------------------------------------------------------- #
def mojibake(value: str | None) -> str | None:
    """Texto latin-1 lido como utf-8, o classico 'Distribuicao' virar lixo.

    Aplicado ao VALOR e nao ao arquivo, porque em xlsx nao existe encoding de
    arquivo: o dano acontece a montante, na exportacao do sistema legado, e
    chega na planilha ja corrompido.
    """
    if not value:
        return value
    try:
        return value.encode("utf-8").decode("latin-1")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return value


# --------------------------------------------------------------------------- #
# D07: formato de data divergente
# --------------------------------------------------------------------------- #
def format_date(d: date | None, fmt: str) -> str | None:
    if d is None:
        return None
    return d.strftime(fmt)


# --------------------------------------------------------------------------- #
# D08: data impossivel
# --------------------------------------------------------------------------- #
IMPOSSIBLE_PATTERNS = ["31/02/{y}", "30/02/{y}", "01/01/1900", "99/99/9999"]


def impossible_date(rng: np.random.Generator, reference: date | None, fmt: str) -> str:
    """Datas que nao existem, ou que existem e sao absurdas.

    Quatro familias: dia inexistente no mes, ano sentinela 1900, data futura
    distante e digitacao trocada no ano.
    """
    kind = int(rng.integers(0, 4))
    year = reference.year if reference else 2020
    if kind == 0:
        return IMPOSSIBLE_PATTERNS[int(rng.integers(0, 2))].format(y=year)
    if kind == 1:
        return date(1900, 1, 1).strftime(fmt)
    if kind == 2:
        return (date(year + 40, 6, 15)).strftime(fmt)
    # digitacao trocada: 2019 -> 0219
    base = reference or date(year, 6, 15)
    return base.strftime(fmt).replace(str(year), f"0{str(year)[1:]}", 1)


# --------------------------------------------------------------------------- #
# D04: nomenclatura livre em campo sem dominio controlado
# --------------------------------------------------------------------------- #
def _variant(value: str, kind: int) -> str:
    if kind == 0:
        return value.upper()
    if kind == 1:
        return value.lower()
    if kind == 2:
        return f" {value} "
    if kind == 3:
        return value.replace(" ", "  ")
    if kind == 4:
        return value.replace("&", "e")
    return "".join(w[:4] + "." if len(w) > 5 else w for w in value.split(" "))


def free_text_variant(rng: np.random.Generator, value: str) -> str:
    """Variacoes tipicas de digitacao manual do mesmo conceito.

    A funcao GARANTE que o valor mude. Sem essa garantia, um departamento de
    palavra unica e sem "&" podia sair identico, e o ledger registraria um
    defeito que nao aconteceu, o que corromperia o gabarito. Foi um dos achados
    das validacoes da F2.
    """
    order = list(rng.permutation(6))
    for kind in order:
        out = _variant(value, int(kind))
        if out != value:
            return out
    return value + " "   # espaco a direita e uma variante real e desagradavel


DEPARTMENT_ALIASES = {
    "People": ["RH", "R.H.", "Recursos Humanos", "rh", "REC HUMANOS", "People & Culture", "DHO"],
    "Finance": ["Financeiro", "FIN", "Controladoria", "Finanças"],
    "Legal": ["Jurídico", "JUR", "Depto Juridico"],
    "Store Operations": ["Operações Loja", "OPER LOJA", "Lojas", "Operação de Lojas"],
    "Customer Service": ["SAC", "Atendimento", "Central de Atendimento", "CS"],
    "Logistics": ["Logística", "LOG", "Transportes"],
    "Distribution Centers": ["CD", "Centro de Distribuição", "CDs"],
    "Engineering": ["TI", "Tecnologia", "Eng", "Desenvolvimento"],
    "Marketing": ["MKT", "Marketing e Comunicação", "Mktg"],
}


def department_alias(rng: np.random.Generator, canonical: str) -> str:
    """Nome alternativo do mesmo departamento, como digitado no sistema legado.

    Esta e a materia-prima da camada de DE/PARA: e exatamente este valor que
    precisa virar `People` sem que ninguem o corrija em silencio.
    """
    options = DEPARTMENT_ALIASES.get(canonical)
    if options:
        return str(rng.choice(options))
    return free_text_variant(rng, canonical)


# --------------------------------------------------------------------------- #
# D12: escala de nivel propria de sistema adquirido
# --------------------------------------------------------------------------- #
def foreign_level(canonical: str, scale: list[str], mapping: dict[str, str]) -> str:
    return mapping.get(canonical, scale[len(scale) // 2])


def vivamarket_level_map(levels: list[str]) -> dict[str, str]:
    """N1 a N7 sobre os 13 niveis da NOVAORA.

    O mapa e proposital e AMBIGUO em dois pontos: N4 cobre IC4 e M1, N5 cobre
    IC5 e M2. Esses casos precisam cair em `mapping_exceptions` na F4, e nao
    ser resolvidos por chute.
    """
    return {
        "IC1": "N1", "IC2": "N2", "IC3": "N3", "IC4": "N4", "IC5": "N5",
        "M1": "N4", "M2": "N5", "M3": "N6", "M4": "N6", "M5": "N7",
        "D1": "N7", "D2": "N7", "D3": "N7",
    }


def comprafacil_level_map() -> dict[str, str]:
    return {
        "IC1": "A", "IC2": "B", "IC3": "C", "IC4": "D", "IC5": "D",
        "M1": "D", "M2": "E", "M3": "E", "M4": "F", "M5": "F",
        "D1": "F", "D2": "F", "D3": "F",
    }


# --------------------------------------------------------------------------- #
# D09: gestor inexistente
# --------------------------------------------------------------------------- #
def orphan_manager_id(rng: np.random.Generator, known_ids: list[int]) -> int:
    """Gestor que nao existe no cadastro.

    Dois modos: um id fora da faixa conhecida (gestor de outro sistema) e um id
    de alguem ja desligado sem sucessao registrada.
    """
    if known_ids and rng.random() < 0.5:
        return int(rng.choice(known_ids))
    return int(rng.integers(900000, 999999))


# --------------------------------------------------------------------------- #
# D01: dominio divergente de genero
# --------------------------------------------------------------------------- #
LEGACY_GENDER = {"Female": "F", "Male": "M", "Non-binary": "", "Not informed": ""}
VIVA_GENDER = {"Female": "FEM", "Male": "MASC", "Non-binary": "OUTRO", "Not informed": ""}


# --------------------------------------------------------------------------- #
# D14: valor ausente
# --------------------------------------------------------------------------- #
def drop(value):
    return None


# --------------------------------------------------------------------------- #
# D19: pais inconsistente entre sistemas
# --------------------------------------------------------------------------- #
def swap_country(rng: np.random.Generator, country: str, options: list[str]) -> str:
    alt = [c for c in options if c != country]
    return str(rng.choice(alt)) if alt else country


# --------------------------------------------------------------------------- #
# D06: colisao de faixa de id
# --------------------------------------------------------------------------- #
def colliding_id(rng: np.random.Generator, existing_ids: list[int]) -> int:
    return int(rng.choice(existing_ids))


# --------------------------------------------------------------------------- #
# D22: duplicidade de vinculo por recontratacao
# --------------------------------------------------------------------------- #
def duplicate_row(row: dict, new_key: str, key_field: str) -> dict:
    dup = dict(row)
    dup[key_field] = new_key
    return dup


# --------------------------------------------------------------------------- #
# numeros em formato local
# --------------------------------------------------------------------------- #
def decimal_br(value: float | None, places: int = 2) -> str | None:
    if value is None:
        return None
    return f"{value:.{places}f}".replace(".", ",")
