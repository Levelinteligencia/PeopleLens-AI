"""Planos de execucao: o unico lugar do projeto onde o KPI encontra a tabela.

Um plano tem duas partes:

    view      SQL que materializa o KPI sobre a L3, com os FILTROS FIXOS ja
              aplicados e as dimensoes ja resolvidas em nome de negocio;
    measure   como a medida se calcula a partir das linhas dessa view.

Os filtros fixos moram aqui, e nao na consulta, e essa e a decisao inteira. O
`headcount` so fecha com `is_system_of_record = true`, por causa da sobreposicao
HRIS_LEGACY x HRIS_CORE entre 2016 e 2019 (ADR-0026). Um SQL escrito por modelo
acerta esse filtro nove vezes em dez e, na decima, devolve um numero inflado com
cara de fato. Como a view ja o aplica, **nem quem consultar o DuckDB direto
consegue somar headcount sem o sistema de registro** (FCx-14).

Nenhum plano referencia RAW, standardized, conformed ou a camada de verdade. O
prefixo `analytical.` e o unico permitido, e ha teste que le o SQL e reprova
qualquer outro (AC-05).

KPI `BLOCKED` NAO tem plano. Nao e esquecimento: um KPI bloqueado nao produz
valor de nenhuma natureza (FCx-17), e nao ter por onde calcular e a garantia
estrutural disso.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import members

SCHEMA_PERMITIDO = "analytical."

# Colunas de periodo que toda view expoe, no formato do vocabulario.
PERIODO_COLS = {"mes": "periodo_mes", "trimestre": "periodo_trimestre",
                "ano": "periodo_ano", "ciclo": "periodo_ciclo"}

# Colunas de dimensao, no nome de negocio. O consumidor nunca ve `country`.
DIM_COLS = ("pais", "business_unit", "departamento", "nivel", "genero",
            "origem", "sistema_fonte")


@dataclass(frozen=True)
class Measure:
    """Como a medida se calcula sobre as linhas da view.

    `tipo` e fechado. Nao existe medida "expressao livre": toda expressao livre
    e um lugar onde uma regra de negocio entra pela consulta em vez de pelo
    contrato, que e exatamente o que o caso `movement_type` mostrou.
    """
    tipo: str                     # contagem_distinta | soma | razao | mediana | turnover
    coluna: str | None = None
    numerador: str | None = None   # expressao de agregacao, montada aqui
    denominador: str | None = None
    unidade: str = ""
    populacao: str | None = None   # expressao que conta a populacao do recorte


@dataclass(frozen=True)
class Plan:
    kpi_id: str
    sql: str
    measure: Measure
    dimensoes: tuple[str, ...]
    grains: tuple[str, ...]
    tabelas: tuple[str, ...]
    nota: str = ""
    extras: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Blocos reutilizados
# --------------------------------------------------------------------------- #
# Um unico bloco de join para tudo que pendura na foto mensal. Repetir o join a
# cada KPI seria repetir a chance de esquecer o filtro fixo.
# Projeções de dimensão. Nunca `o.department` direto: no membro reservado o
# atributo é nulo e o nome do membro se perde (G-02, ADR-0025).
_ORG_PAIS = members.por_sk("h.org_sk", "o.country", "o.code", "pais")
_ORG_BU = members.por_sk("h.org_sk", "o.business_unit", "o.code", "business_unit")
_ORG_DEPTO = members.por_sk("h.org_sk", "o.department", "o.code", "departamento")
_NIVEL = members.por_sk("h.job_level_sk", "j.code", "j.code", "nivel")

_HEADCOUNT_BASE = f"""
SELECT
    c.mes                                   AS periodo_mes,
    CAST(c.ano AS VARCHAR) || '-Q' || CAST(c.trimestre_num AS VARCHAR)
                                            AS periodo_trimestre,
    CAST(c.ano AS VARCHAR)                  AS periodo_ano,
    c.ciclo                                 AS periodo_ciclo,
    {_ORG_PAIS},
    {_ORG_BU},
    {_ORG_DEPTO},
    {_NIVEL},
    j.is_leadership                         AS is_lideranca,
    COALESCE(e.gender, '{members.VALOR_AUSENTE}')      AS genero,
    CASE WHEN e.origin_code IS NULL THEN '{members.VALOR_AUSENTE}'
         ELSE COALESCE(g.code, e.origin_code) END      AS origem,
    g.is_hire                               AS is_contratacao,
    COALESCE(s.code, '{members.VALOR_AUSENTE}')        AS sistema_fonte,
    h.party_key                             AS party_key,
    h.fte                                   AS fte,
    h.manager_id                            AS manager_id,
    e.hire_date                             AS hire_date,
    e.disability_flag                       AS disability_flag,
    c.date_iso                              AS data_referencia
FROM analytical.fact_headcount_snapshot h
JOIN analytical.dim_calendar     c ON c.date_sk      = h.date_sk
JOIN analytical.dim_employee     e ON e.employee_sk  = h.employee_sk
JOIN analytical.dim_organization o ON o.org_sk       = h.org_sk
JOIN analytical.dim_job_level    j ON j.job_level_sk = h.job_level_sk
JOIN analytical.dim_source_system s ON s.source_sk   = h.source_sk
LEFT JOIN analytical.dim_origin  g ON g.code         = e.origin_code
WHERE h.is_system_of_record        -- FILTRO FIXO DO KPI (ADR-0026)
  AND c.is_month_end               -- a foto e de fim de mes, por definicao
"""

_ORG_DE_REQUISICAO = f"""
    {members.por_sk("r.org_sk", "o.country", "o.code", "pais")},
    {members.por_sk("r.org_sk", "o.business_unit", "o.code", "business_unit")},
    {members.por_sk("r.org_sk", "o.department", "o.code", "departamento")},
    {members.por_sk("r.job_level_sk", "j.code", "j.code", "nivel")}
"""

def _emp_dims(fato: str) -> str:
    """Dimensões desnormalizadas em `dim_employee`, pelo `employee_sk` do fato.

    Duas fontes de nome, e as duas importam:

    - o valor NÃO MAPEADO já chega como a própria string `'UNMAPPED'` (825
      linhas em `department`), e atravessa nomeado sozinho;
    - o `employee_sk` NEGATIVO aponta para o membro reservado de
      `dim_employee`, cujos atributos são nulos e cujo nome vive em
      `party_key` (`SEM_CHAVE_DE_ORIGEM`, `FORA_DO_UNIVERSO`).

    O segundo caso não é raro: 5.376 das 5.919 linhas de
    `fact_workforce_entry` têm `employee_sk = -1`. Projetar `e.department`
    direto transformaria todas elas em nulo — é o mesmo defeito G-02, uma
    junção adiante.
    """
    sk = f"{fato}.employee_sk"
    return ",\n    ".join((
        members.por_sk(sk, "e.country", "e.party_key", "pais"),
        members.por_sk(sk, "e.business_unit", "e.party_key", "business_unit"),
        members.por_sk(sk, "e.department", "e.party_key", "departamento"),
        members.por_atributo("j.code", "nivel"),
    ))


PLANS: dict[str, Plan] = {}


def _reg(p: Plan) -> None:
    PLANS[p.kpi_id] = p


# --------------------------------------------------------------------------- #
# Certificados
# --------------------------------------------------------------------------- #
_reg(Plan(
    kpi_id="headcount",
    sql=_HEADCOUNT_BASE,
    measure=Measure("contagem_distinta", coluna="party_key", unidade="pessoas",
                    populacao="COUNT(DISTINCT party_key)"),
    dimensoes=("pais", "business_unit", "departamento", "nivel", "genero",
               "origem", "sistema_fonte"),
    grains=("mes", "trimestre", "ano"),
    tabelas=("fact_headcount_snapshot", "dim_calendar", "dim_employee",
             "dim_organization", "dim_job_level", "dim_source_system", "dim_origin"),
    nota="uma pessoa conta uma vez por mes, pelo sistema de registro do periodo",
))

_reg(Plan(
    kpi_id="turnover_rate",
    # Duas fontes: desligamentos no periodo e o estoque nas pontas. O
    # denominador NAO e a soma dos meses: somar doze fotos mensais daria doze
    # vezes a empresa. E a media das pontas, como o contrato declara.
    sql=f"""
SELECT
    c.mes                                   AS periodo_mes,
    CAST(c.ano AS VARCHAR) || '-Q' || CAST(c.trimestre_num AS VARCHAR)
                                            AS periodo_trimestre,
    CAST(c.ano AS VARCHAR)                  AS periodo_ano,
    c.ciclo                                 AS periodo_ciclo,
    {_emp_dims('t')},
    CASE WHEN e.origin_code IS NULL THEN '{members.VALOR_AUSENTE}'
         ELSE COALESCE(g.code, e.origin_code) END AS origem,
    t.party_key      AS party_key,
    t.terminations   AS desligamentos
FROM analytical.fact_termination t
JOIN analytical.dim_calendar     c ON c.date_sk     = t.date_sk
JOIN analytical.dim_employee     e ON e.employee_sk = t.employee_sk
LEFT JOIN analytical.dim_job_level j ON j.job_level_sk = e.job_level_sk
LEFT JOIN analytical.dim_origin    g ON g.code = e.origin_code
""",
    measure=Measure("turnover", numerador="SUM(desligamentos)", unidade="taxa",
                    populacao="COUNT(DISTINCT party_key)"),
    dimensoes=("pais", "business_unit", "departamento", "nivel", "origem"),
    grains=("ano",),
    tabelas=("fact_termination", "dim_calendar", "dim_employee",
             "dim_job_level", "dim_origin"),
    nota="denominador vem do plano de headcount, nas pontas do periodo",
    extras={"denominador_de": "headcount"},
))

_reg(Plan(
    kpi_id="women_in_leadership",
    # O filtro de lideranca e do CONTRATO. E a nao declaracao sai dos DOIS
    # lados, e a taxa e devolvida junto: excluir so do numerador faria o
    # indicador parecer melhor do que e.
    sql=_HEADCOUNT_BASE + """
  AND j.is_leadership
  AND e.gender IS NOT NULL
  AND e.gender NOT IN ('Not informed', 'UNMAPPED')
""",
    measure=Measure("razao",
                    numerador="COUNT(DISTINCT CASE WHEN genero = 'Female' THEN party_key END)",
                    denominador="COUNT(DISTINCT party_key)",
                    unidade="share", populacao="COUNT(DISTINCT party_key)"),
    dimensoes=("pais", "business_unit", "departamento", "nivel", "origem"),
    grains=("mes", "trimestre", "ano"),
    tabelas=("fact_headcount_snapshot", "dim_calendar", "dim_employee",
             "dim_organization", "dim_job_level", "dim_source_system", "dim_origin"),
    nota="nao declaracao de genero sai do numerador e do denominador",
    extras={"taxa_de_nao_declaracao_de": "genero"},
))

_reg(Plan(
    kpi_id="hiring_volume",
    # `is_hire` e o unico criterio. Origem AQUISICAO_* e INDETERMINADA nao
    # contam, e o filtro esta aqui porque contar INDETERMINADA como contratacao
    # e FC-09 (ADR-0027).
    sql=f"""
SELECT
    c.mes                                   AS periodo_mes,
    CAST(c.ano AS VARCHAR) || '-Q' || CAST(c.trimestre_num AS VARCHAR)
                                            AS periodo_trimestre,
    CAST(c.ano AS VARCHAR)                  AS periodo_ano,
    c.ciclo                                 AS periodo_ciclo,
    {_emp_dims('w')},
    g.code           AS origem,
    s.code           AS sistema_fonte,
    w.party_key      AS party_key,
    w.entries        AS entradas
FROM analytical.fact_workforce_entry w
JOIN analytical.dim_calendar      c ON c.date_sk     = w.date_sk
JOIN analytical.dim_origin        g ON g.origin_sk   = w.origin_sk
JOIN analytical.dim_employee      e ON e.employee_sk = w.employee_sk
JOIN analytical.dim_source_system s ON s.source_sk   = w.source_sk
LEFT JOIN analytical.dim_job_level j ON j.job_level_sk = e.job_level_sk
WHERE g.is_hire                    -- FILTRO FIXO DO KPI (ADR-0027, FC-09)
""",
    measure=Measure("soma", coluna="entradas", unidade="pessoas",
                    populacao="COUNT(DISTINCT party_key)"),
    dimensoes=("pais", "business_unit", "departamento", "nivel", "origem", "sistema_fonte"),
    grains=("mes", "trimestre", "ano"),
    tabelas=("fact_workforce_entry", "dim_calendar", "dim_origin", "dim_employee",
             "dim_source_system", "dim_job_level"),
    nota="so contratacao; aquisicao e origem indeterminada nunca entram",
))

_reg(Plan(
    kpi_id="time_to_fill",
    sql=f"""
SELECT
    c.mes                                   AS periodo_mes,
    CAST(c.ano AS VARCHAR) || '-Q' || CAST(c.trimestre_num AS VARCHAR)
                                            AS periodo_trimestre,
    CAST(c.ano AS VARCHAR)                  AS periodo_ano,
    c.ciclo                                 AS periodo_ciclo,
{_ORG_DE_REQUISICAO},
    r.requisition_id AS requisition_id,
    r.days_to_fill   AS dias
FROM analytical.fact_requisition r
JOIN analytical.dim_calendar      c ON c.date_sk      = r.date_sk_hire
LEFT JOIN analytical.dim_organization o ON o.org_sk   = r.org_sk
LEFT JOIN analytical.dim_job_level    j ON j.job_level_sk = r.job_level_sk
WHERE r.date_sk_hire > 0           -- marco atingido; -5 e "ainda nao ocorreu"
  AND r.days_to_fill IS NOT NULL
  AND COALESCE(r.status, '') <> 'Cancelled'
""",
    measure=Measure("mediana", coluna="dias", unidade="dias",
                    populacao="COUNT(DISTINCT requisition_id)"),
    dimensoes=("pais", "business_unit", "departamento", "nivel"),
    grains=("trimestre", "ano"),
    tabelas=("fact_requisition", "dim_calendar", "dim_organization", "dim_job_level"),
    nota="grain de requisicao, nao de pessoa",
))

# --------------------------------------------------------------------------- #
# Declarados
# --------------------------------------------------------------------------- #
_reg(Plan(
    kpi_id="fte",
    sql=_HEADCOUNT_BASE,
    measure=Measure("soma", coluna="fte", unidade="FTE",
                    populacao="COUNT(DISTINCT party_key)"),
    dimensoes=("pais", "business_unit", "departamento", "nivel", "genero",
               "origem", "sistema_fonte"),
    grains=("mes", "trimestre", "ano"),
    tabelas=("fact_headcount_snapshot", "dim_calendar", "dim_employee",
             "dim_organization", "dim_job_level", "dim_source_system", "dim_origin"),
))

_reg(Plan(
    kpi_id="tenure",
    sql=_HEADCOUNT_BASE + "  AND e.hire_date IS NOT NULL\n",
    measure=Measure(
        "mediana",
        coluna="DATEDIFF('month', CAST(hire_date AS DATE), CAST(data_referencia AS DATE))",
        unidade="meses", populacao="COUNT(DISTINCT party_key)"),
    dimensoes=("pais", "business_unit", "departamento", "nivel", "genero", "origem"),
    grains=("mes", "trimestre", "ano"),
    tabelas=("fact_headcount_snapshot", "dim_calendar", "dim_employee",
             "dim_organization", "dim_job_level", "dim_origin"),
))

_reg(Plan(
    kpi_id="span_of_control",
    sql=_HEADCOUNT_BASE + "  AND h.manager_id IS NOT NULL\n",
    measure=Measure("razao", numerador="COUNT(DISTINCT party_key)",
                    denominador="COUNT(DISTINCT manager_id)",
                    unidade="pessoas por gestor", populacao="COUNT(DISTINCT party_key)"),
    dimensoes=("pais", "business_unit", "departamento"),
    grains=("mes", "trimestre", "ano"),
    tabelas=("fact_headcount_snapshot", "dim_calendar", "dim_employee",
             "dim_organization", "dim_job_level", "dim_source_system", "dim_origin"),
))

_reg(Plan(
    kpi_id="gender_representation",
    sql=_HEADCOUNT_BASE + """
  AND e.gender IS NOT NULL
  AND e.gender NOT IN ('Not informed', 'UNMAPPED')
""",
    measure=Measure("razao",
                    numerador="COUNT(DISTINCT CASE WHEN genero = 'Female' THEN party_key END)",
                    denominador="COUNT(DISTINCT party_key)",
                    unidade="share", populacao="COUNT(DISTINCT party_key)"),
    dimensoes=("pais", "business_unit", "departamento", "nivel", "origem"),
    grains=("mes", "trimestre", "ano"),
    tabelas=("fact_headcount_snapshot", "dim_calendar", "dim_employee",
             "dim_organization", "dim_job_level", "dim_source_system", "dim_origin"),
    extras={"taxa_de_nao_declaracao_de": "genero"},
))

_reg(Plan(
    kpi_id="pcd_representation",
    # `disability_flag` nulo e ausencia legitima: sai dos dois lados e NUNCA
    # penaliza o trust (ADR-0022).
    sql=_HEADCOUNT_BASE + "  AND e.disability_flag IS NOT NULL\n",
    measure=Measure("razao",
                    numerador="COUNT(DISTINCT CASE WHEN disability_flag = 'True' "
                              "THEN party_key END)",
                    denominador="COUNT(DISTINCT party_key)",
                    unidade="share", populacao="COUNT(DISTINCT party_key)"),
    dimensoes=("pais", "business_unit", "departamento", "nivel"),
    grains=("mes", "trimestre", "ano"),
    tabelas=("fact_headcount_snapshot", "dim_calendar", "dim_employee",
             "dim_organization", "dim_job_level", "dim_source_system", "dim_origin"),
    extras={"taxa_de_nao_declaracao_de": "disability_flag"},
))

_reg(Plan(
    kpi_id="performance_distribution",
    sql=f"""
SELECT
    c.mes                                   AS periodo_mes,
    CAST(c.ano AS VARCHAR) || '-Q' || CAST(c.trimestre_num AS VARCHAR)
                                            AS periodo_trimestre,
    CAST(c.ano AS VARCHAR)                  AS periodo_ano,
    p.review_cycle                          AS periodo_ciclo,
    {_emp_dims('p')},
    COALESCE(e.gender, '{members.VALOR_AUSENTE}') AS genero,
    p.party_key      AS party_key,
    p.std_performance_rating AS nota,
    p.reviews        AS avaliacoes
FROM analytical.fact_performance p
JOIN analytical.dim_calendar  c ON c.date_sk     = p.date_sk
JOIN analytical.dim_employee  e ON e.employee_sk = p.employee_sk
LEFT JOIN analytical.dim_job_level j ON j.job_level_sk = e.job_level_sk
WHERE p.std_performance_rating IS NOT NULL
""",
    measure=Measure("soma", coluna="avaliacoes", unidade="avaliacoes",
                    populacao="COUNT(DISTINCT party_key)"),
    dimensoes=("pais", "business_unit", "departamento", "nivel", "genero"),
    grains=("ciclo", "ano"),
    tabelas=("fact_performance", "dim_calendar", "dim_employee", "dim_job_level"),
))

_reg(Plan(
    kpi_id="time_to_hire",
    sql=f"""
SELECT
    c.mes                                   AS periodo_mes,
    CAST(c.ano AS VARCHAR) || '-Q' || CAST(c.trimestre_num AS VARCHAR)
                                            AS periodo_trimestre,
    CAST(c.ano AS VARCHAR)                  AS periodo_ano,
    c.ciclo                                 AS periodo_ciclo,
{_ORG_DE_REQUISICAO},
    a.candidate_id   AS candidate_id,
    a.days_to_hire   AS dias
FROM analytical.fact_application a
JOIN analytical.dim_calendar   c ON c.date_sk = a.date_sk_hire
LEFT JOIN analytical.fact_requisition r ON r.requisition_sk = a.requisition_sk
LEFT JOIN analytical.dim_organization o ON o.org_sk = r.org_sk
LEFT JOIN analytical.dim_job_level    j ON j.job_level_sk = r.job_level_sk
WHERE a.date_sk_hire > 0
  AND a.days_to_hire IS NOT NULL
""",
    measure=Measure("mediana", coluna="dias", unidade="dias",
                    populacao="COUNT(DISTINCT candidate_id)"),
    dimensoes=("business_unit", "departamento", "nivel"),
    grains=("trimestre", "ano"),
    tabelas=("fact_application", "fact_requisition", "dim_calendar",
             "dim_organization", "dim_job_level"),
))

_reg(Plan(
    kpi_id="offer_acceptance_rate",
    sql=f"""
SELECT
    c.mes                                   AS periodo_mes,
    CAST(c.ano AS VARCHAR) || '-Q' || CAST(c.trimestre_num AS VARCHAR)
                                            AS periodo_trimestre,
    CAST(c.ano AS VARCHAR)                  AS periodo_ano,
    c.ciclo                                 AS periodo_ciclo,
{_ORG_DE_REQUISICAO},
    a.candidate_id   AS candidate_id,
    a.offers         AS ofertas,
    a.accepts        AS aceites
FROM analytical.fact_application a
JOIN analytical.dim_calendar   c ON c.date_sk = a.date_sk_offer
LEFT JOIN analytical.fact_requisition r ON r.requisition_sk = a.requisition_sk
LEFT JOIN analytical.dim_organization o ON o.org_sk = r.org_sk
LEFT JOIN analytical.dim_job_level    j ON j.job_level_sk = r.job_level_sk
WHERE a.date_sk_offer > 0
  AND a.offers > 0
""",
    measure=Measure("razao", numerador="SUM(aceites)", denominador="SUM(ofertas)",
                    unidade="share", populacao="COUNT(DISTINCT candidate_id)"),
    dimensoes=("business_unit", "departamento", "nivel"),
    grains=("trimestre", "ano"),
    tabelas=("fact_application", "fact_requisition", "dim_calendar",
             "dim_organization", "dim_job_level"),
))

# --------------------------------------------------------------------------- #
# Sem plano, de proposito
# --------------------------------------------------------------------------- #
# internal_mobility_rate, promotion_rate  -> movement_type sem DE/PARA
# compa_ratio, pay_gap                    -> sem banda salarial fora da verdade
# black_representation                    -> race_ethnicity sem DE/PARA
#
# Nao ter plano nao e lacuna de implementacao: e a garantia estrutural de que um
# KPI BLOCKED nao produz valor de natureza nenhuma (FCx-17). Escrever o plano e
# depender do status para nao executa-lo deixaria um numero a uma linha de
# distancia.
SEM_PLANO = ("internal_mobility_rate", "promotion_rate", "compa_ratio",
             "pay_gap", "black_representation")


def plano(kpi_id: str) -> Plan | None:
    return PLANS.get(kpi_id)


def tabelas_fora_da_l3() -> dict[str, list[str]]:
    """Referencias de schema fora de `analytical.` em qualquer plano.

    Vazio e o esperado (AC-05). O teste le isto em vez de confiar em revisao.
    """
    import re
    fora: dict[str, list[str]] = {}
    padrao = re.compile(r"\b(\w+)\.(fact_|dim_|ref_|stg_|raw_)\w+", re.IGNORECASE)
    for kpi, p in PLANS.items():
        achados = {m.group(1) for m in padrao.finditer(p.sql)
                   if m.group(1).lower() != "analytical"}
        if achados:
            fora[kpi] = sorted(achados)
    return fora
