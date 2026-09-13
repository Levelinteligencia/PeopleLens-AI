"""Versionamento de KPI (ADR-0030).

A regra que importa e a primeira: **mudar a formula de um KPI certificado nao
reescreve o passado.** Sem ela, a mudanca de definicao e retroativa por padrao,
e a consulta de hoje sobre 2022 devolve um numero diferente do que devolveu em
2022, sem nada na resposta indicando isso. E a mesma patologia que a F3 proibiu
no RAW e a F4 na promocao de mapeamento, agora na camada semantica: aqui o valor
alterado nao e uma celula, e a definicao que gera milhares de celulas.

    definicao de negocio ou formula        -> versao MAIOR, quebra comparabilidade
    filtro, exclusao, dimensao, cobertura  -> versao menor, nao quebra serie
    texto, descricao, dono                 -> correcao

`kpi_id` e imutavel. Mudou o id, e outro KPI, e nao uma versao nova.
"""
from __future__ import annotations

from .catalog import Kpi

# Campos cuja mudanca altera O QUE o KPI mede.
MAIOR = ("business_definition", "formula", "grain", "population", "period_grain")

# Campos cuja mudanca altera QUEM entra na conta ou ate onde ela vai, sem mudar
# a medida. Nao quebram a serie, e por isso sao menores.
MENOR = ("filters", "exclusions", "allowed_dimensions", "period_coverage",
         "period_rollup", "source_tables", "depends_on_mappings", "minimum_n",
         "response_levels", "interpretation_rules", "causal_studies",
         "coverage", "status", "certification")


class VersionError(ValueError):
    pass


def tipo_de_mudanca(antes: dict, depois: dict) -> str | None:
    """`maior`, `menor`, `correcao` ou None quando nada mudou."""
    if antes.get("kpi_id") != depois.get("kpi_id"):
        raise VersionError(
            "kpi_id e imutavel: mudar o id nao e uma versao nova, e outro KPI")
    if any(antes.get(c) != depois.get(c) for c in MAIOR):
        return "maior"
    if any(antes.get(c) != depois.get(c) for c in MENOR):
        return "menor"
    campos = set(antes) | set(depois)
    if any(antes.get(c) != depois.get(c) for c in campos
           if c not in ("version",)):
        return "correcao"
    return None


def proxima_versao(atual: str, tipo: str) -> str:
    maior, menor, correcao = (int(x) for x in atual.split("."))
    if tipo == "maior":
        return f"{maior + 1}.0.0"
    if tipo == "menor":
        return f"{maior}.{menor + 1}.0"
    if tipo == "correcao":
        return f"{maior}.{menor}.{correcao + 1}"
    raise VersionError(f"tipo de mudanca desconhecido: {tipo!r}")


def versoes_consultaveis(kpi: Kpi) -> list[str]:
    """Versoes que respondem hoje.

    A versao corrente sempre; as anteriores registradas em `previous_versions`
    continuam consultaveis para periodo historico. Remover uma versao torna
    irreproduzivel toda resposta que a citou, e por isso nao ha funcao que
    remova.
    """
    anteriores = [str(v["version"]) for v in kpi.doc.get("previous_versions") or []]
    return sorted({kpi.version, *anteriores})


def comparavel(kpi: Kpi, a: str, b: str) -> bool:
    """Duas versoes sao comparaveis quando a medida nao mudou entre elas.

    Mudanca maior quebra comparabilidade, e comparar assim mesmo apresenta como
    tendencia o que e artefato de definicao. A comparacao e recusada por padrao;
    quem quiser compara-las declara isso explicitamente, e a resposta sai com a
    ressalva de quebra.
    """
    if a == b:
        return True
    return a.split(".")[0] == b.split(".")[0]


def diff_para_resposta(antes: dict, depois: dict) -> list[str]:
    """O que mudou entre duas versoes, em linguagem de contrato.

    E o que a recusa de comparacao entre versoes devolve: dizer apenas "as
    versoes sao diferentes" nao ajuda ninguem a decidir se quer comparar.
    """
    return [f"{c}: mudou" for c in (*MAIOR, *MENOR)
            if antes.get(c) != depois.get(c)]
