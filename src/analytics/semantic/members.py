"""Estados governados na saída da camada semântica (G-02, ADR-0025).

O ADR-0025 decidiu que **pendência de governança vira membro nomeado, nunca
nulo**, e a L3 cumpre: `dim_organization` tem `org_sk = -1` com `code =
'UNMAPPED'` e `label = 'sem mapeamento aprovado'`. As views da F7 projetavam o
**atributo** (`o.department`), que é nulo no membro reservado, e o nome se
perdia na última camada.

O tamanho do problema: 40 dos 126 meses da série — 2016-01 a 2019-04, a era
inteira do `HRIS_LEGACY` — têm 100% das linhas no membro reservado. A resposta
saía como `{departamento: null, valor: 397}`, e quem lesse isso reportaria "397
pessoas em departamento não identificado" como se fosse um departamento.

Três estados que NÃO podem se confundir, e é essa distinção que este módulo
existe para manter:

    UNMAPPED / DECISAO_PENDENTE / ...   pendência de GOVERNANÇA: existe decisão
                                        ou mapeamento em aberto, e há quem a
                                        resolva
    VALOR_AUSENTE                       o registro de origem não trouxe o campo:
                                        não há decisão pendente, há dado que não
                                        veio
    membro de negócio                   "BR", "Retail", "Finance"

`VALOR_AUSENTE` é estado de **apresentação** da camada semântica, e não um
membro novo de dimensão: nenhuma dimensão da L3 ganha linha por causa dele, e o
catálogo de membros reservados da F6 permanece exatamente como está.
"""
from __future__ import annotations

# Ausência real de valor no registro de origem. Distinto de toda pendência de
# governança, e distinto de "Not informed", que é uma declaração de quem não
# quis declarar e é valor legítimo da fonte.
VALOR_AUSENTE = "VALOR_AUSENTE"

# Pendências de governança, como a F6 as nomeia em `model/keys.py`. A lista é
# de leitura: este módulo não cria nem renomeia membro reservado.
PENDENCIAS_DE_GOVERNANCA = (
    "UNMAPPED",              # sem mapeamento aprovado (dim_organization, dim_job_level)
    "DECISAO_PENDENTE",      # decisão de negócio pendente (N4, N5 da VivaMarket)
    "TRADUCAO_PENDENTE",     # tradução pendente entre vocabulários
    "SEM_CHAVE_DE_ORIGEM",   # registro sem chave utilizável (dim_employee)
    "FORA_DO_UNIVERSO",      # fora do universo conhecido
    "AINDA_NAO_OCORREU",     # marco não atingido (dim_calendar, -5)
    "ANTERIOR_A_SERIE",      # anterior ao período de análise (dim_calendar, -7)
    "INDETERMINADA",         # origem não determinada (ADR-0027): estado LEGÍTIMO
)

ESTADOS_GOVERNADOS = (*PENDENCIAS_DE_GOVERNANCA, VALOR_AUSENTE)

# O que cada estado significa para quem lê a resposta. Sem isto, "UNMAPPED"
# numa linha de breakdown é só uma palavra em maiúsculas.
SIGNIFICADO = {
    "UNMAPPED": "sem mapeamento aprovado: o valor de origem existe e ainda não "
                "foi mapeado para o vocabulário corporativo",
    "DECISAO_PENDENTE": "decisão de negócio pendente: alguém precisa decidir, e "
                        "inferir o valor é proibido",
    "TRADUCAO_PENDENTE": "tradução pendente entre vocabulários de idiomas "
                         "diferentes (ADR-0020)",
    "SEM_CHAVE_DE_ORIGEM": "registro sem chave de origem utilizável",
    "FORA_DO_UNIVERSO": "fora do universo conhecido",
    "AINDA_NAO_OCORREU": "marco ainda não atingido; não é ausência de dado",
    "ANTERIOR_A_SERIE": "anterior ao início da série de análise",
    "INDETERMINADA": "origem não determinada: estado legítimo e frequente "
                     "(ADR-0027), nunca contado como contratação",
    VALOR_AUSENTE: "o registro de origem não trouxe este campo; não há decisão "
                   "pendente, há dado que não veio",
}


def e_governado(valor) -> bool:
    return isinstance(valor, str) and valor in ESTADOS_GOVERNADOS


def e_pendencia(valor) -> bool:
    """Pendência de governança tem dono e caminho; `VALOR_AUSENTE` não tem."""
    return isinstance(valor, str) and valor in PENDENCIAS_DE_GOVERNANCA


def significado(valor) -> str | None:
    return SIGNIFICADO.get(valor)


# --------------------------------------------------------------------------- #
# Geradores de SQL
# --------------------------------------------------------------------------- #
def por_sk(sk: str, atributo: str, code: str, alias: str) -> str:
    """Projeção de dimensão que vem de uma dimensão com surrogate key.

    A ordem dos ramos é a decisão inteira:

    1. `sk` negativo  -> o membro é reservado, e o nome dele é `code`;
    2. `sk` nulo      -> não houve junção: o fato não aponta para a dimensão;
    3. atributo nulo  -> a linha da dimensão existe e o campo não veio;
    4. caso contrário -> o valor de negócio.

    Trocar 1 por 3 é exatamente o defeito G-02: o membro reservado tem o
    atributo nulo, então projetar o atributo apaga o nome do membro.
    """
    return (f"CASE WHEN {sk} < 0 THEN {code} "
            f"WHEN {sk} IS NULL THEN '{VALOR_AUSENTE}' "
            f"WHEN {atributo} IS NULL THEN '{VALOR_AUSENTE}' "
            f"ELSE {atributo} END AS {alias}")


def por_atributo(atributo: str, alias: str) -> str:
    """Projeção de dimensão que vem de um atributo desnormalizado.

    Em `dim_employee` o valor não mapeado chega como a própria string
    `'UNMAPPED'` (825 linhas em `department`), então ele já atravessa nomeado.
    O que falta é distinguir o nulo, que aqui significa ausência de valor e não
    pendência.
    """
    return f"COALESCE({atributo}, '{VALOR_AUSENTE}') AS {alias}"
