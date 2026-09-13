# F7 — Relatório de implementação da Semantic Layer

**Status: implementado, 188 testes passando, sem commit.** Nada de MCP, agente
ou interface. O modelo analítico da F6 não foi alterado.

A SPEC v1.0 está em `docs/F7_semantic_layer.md`. Este documento registra o que
foi construído, o que mudou em relação à SPEC e o que a implementação descobriu.

---

## 1. O que existe agora

```
pergunta
   │  a IA propõe            ← único passo com latitude
SemanticQuery                  {kpi, period, dimensions, filters, compare, level}
   │  validate()             ← sete verificações, determinísticas
consulta governada
   │  executor               ← DuckDB, views com filtros fixos aplicados
linhas
   │  certify()              ← trust_resposta = min(trust_dado, teto do status)
   │  response               ← nível, caveats, cobertura, trace_id
Answer                         resposta, recusa ou supressão por privacidade
   │  trace.registrar()      ← semantic_query_log, inclusive das recusas
```

A superfície que a F8 vai consumir é uma função: `ask(engine, consulta)`.

### 1.1 A fronteira, em código

A IA não emite SQL porque `SemanticQuery` não tem onde escrever SQL, e campo
desconhecido **reprova** em vez de ser ignorado:

```python
SemanticQuery.parse({"kpi": "headcount", "sql": "SELECT 1", ...})
# QueryShapeError: campos desconhecidos na consulta semantica: ['sql'].
# A consulta nao aceita SQL, nome de tabela, coluna ou junção (ADR-0028).
```

Ignorar o campo extra teria sido a porta por onde `{"table": ...}` entraria sem
ninguém notar. Cinco variações do ataque estão no teste FCx-15, incluindo
injeção pelo valor de um filtro, que vira recusa de vocabulário e não SQL.

### 1.2 O filtro fixo mora na view

`semantic.kpi_headcount` já nasce com `is_system_of_record = true` e
`is_month_end`. A consequência prática está no teste FCx-14: **nem consultando o
DuckDB direto** dá para somar headcount sem o sistema de registro, porque a view
já está desduplicada. O consumidor nunca precisa saber que houve migração de
HRIS em 2019.

---

## 2. Arquivos

### Criados

| Arquivo | O que faz |
|---|---|
| `config/semantic/vocabulary.yaml` | termo de negócio → membro de dimensão; termo desconhecido é recusa |
| `src/analytics/semantic/__init__.py` | a divisão de trabalho, em uma página |
| `src/analytics/semantic/catalog.py` | ciclo de vida, teto de governança, `verify()` do catálogo |
| `src/analytics/semantic/query.py` | `SemanticQuery`, `Refusal`, vocabulário, as sete validações |
| `src/analytics/semantic/plans.py` | planos de execução: o único lugar onde o KPI encontra a tabela |
| `src/analytics/semantic/executor.py` | conexão DuckDB, três schemas, montagem determinística do SQL |
| `src/analytics/semantic/certify.py` | `trust_resposta = min(trust_dado, teto)` |
| `src/analytics/semantic/response.py` | os quatro níveis, caveats, regras de redação |
| `src/analytics/semantic/versioning.py` | maior/menor/correção, comparabilidade entre versões |
| `src/analytics/semantic/trace.py` | os seis degraus de lineage e `semantic_query_log` |
| `src/analytics/semantic/ask.py` | orquestração: `engine()` e `ask()` |
| `tests/semantic/test_semantic.py` | 44 testes: AC-01..18, FC-01..12, FCx-13..17 e conferências |

### Alterados

| Arquivo | Mudança |
|---|---|
| `config/kpis/*.yaml` (18) | 11 campos novos da F7; `depends_on_checks` **intocado** |
| `src/pipeline.py` | `_catalogo_semantico()` no resumo, ao lado da verificação de contratos |
| `requirements.txt` | `duckdb>=1.0`, com a nota do ADR-0009 atualizada |
| `docs/adr/README.md` | ADR-0028, 0029, 0030 e a linha da F7 |

### Não alterados, de propósito

`src/analytics/model/` (F6), `src/analytics/trust.py` (F5), `src/quality/`,
`src/mapping/`, `config/quality_checks.yaml`, nenhum threshold de DQ, nenhuma
banda de trust.

---

## 3. Testes

```
188 passed in 91.80s
    144  F0–F6, inalterados
     44  F7
```

Os 44 da F7 se dividem em:

| Bloco | Testes | O que cobrem |
|---|---|---|
| AC-01..AC-18 | 18 | os acceptance criteria da Parte XI |
| FC-01..FC-12 | 12 | os doze casos de falha da Parte IX |
| FCx-13..FCx-17 | 5 | o que deve falhar |
| conferências | 9 | vocabulário, teto de nível, redação, números contra Polars |

### 3.1 A conferência que importa

`test_numeros_batem_com_calculo_independente` recalcula três KPIs em Polars,
fora do DuckDB, e compara:

| KPI | Camada semântica | Polars, independente |
|---|---|---|
| `headcount` 2026-06 | 1.942 | 1.942 |
| `headcount` 2025 (rollup de ano) | 2.038 | 2.038 (dezembro, não a soma dos meses) |
| `turnover_rate` 2024 | 0,253766 | 438 / ((1.566 + 1.886) / 2) = 0,253766 |

Um executor que erra em silêncio produz respostas com trace, trust e
certificação, e todas erradas. Sem a conferência não há como saber.

---

## 4. Acceptance criteria

| # | Critério | Situação |
|---|---|---|
| AC-01 | campos obrigatórios em todo KPI | **passa** — 18 contratos, 20 campos verificados |
| AC-02 | `depends_on_checks` continua derivado | **passa** — a extensão não digitou nenhuma dependência |
| AC-03 | `CERTIFIED` com dono, versão, data e zero bloqueadores | **passa** — os 5 certificados |
| AC-04 | `source_tables` só aponta para a L3 | **passa** — e o plano não lê tabela que o contrato não declarou |
| AC-05 | nenhuma consulta toca RAW, verdade ou intermediária | **passa** — schema não registrado, não acordo de cavalheiros |
| AC-06 | consulta resolvível sem nomear tabela, join ou coluna | **passa** — a resposta também não os expõe |
| AC-07 | dimensão fora do permitido é recusa | **passa** — com o que responde no lugar |
| AC-08 | termo fora do vocabulário nunca vira aproximação | **passa** — "Brasilia" não casa com "Brasil" |
| AC-09 | `trust_resposta = min(trust_dado, teto)` | **passa** — nas 5 combinações e na resposta real |
| AC-10 | bandas da F5 inalteradas | **passa** — `{CERTIFIED: 0,95, LIMITED: 0,70}`, piso 0,40 |
| AC-11 | abaixo do n mínimo é supressão por privacidade | **passa** — campo próprio, a palavra é "privacidade" |
| AC-12 | resposta declara nível, trust, cobertura e caveats | **passa** — 10 campos obrigatórios |
| AC-13 | INTERPRETATION só com regra registrada | **passa** — nenhum KPI tem regra; teto efetivo é CONTEXT |
| AC-14 | CAUSALITY negada diz o que faltaria | **passa** — desenho, controle, intervalo, limitações |
| AC-15 | trace navega até o `_row_id` da fonte | **passa** — seis degraus, na ordem |
| AC-16 | resposta e recusa no `semantic_query_log` | **passa** — com `l3_run_id` e versão do KPI |
| AC-17 | mudança de fórmula gera versão maior | **passa** — e `kpi_id` é imutável |
| AC-18 | nenhuma regra de negócio nova sem sinalização | **passa** — todo filtro fixo do plano está escrito no contrato |

| # | Deve falhar | Situação |
|---|---|---|
| FCx-13 | `CERTIFIED` com trust de dado `BLOCKED` responder em FACT | **falha** como esperado |
| FCx-14 | somar headcount sem o sistema de registro | **falha** — a view já vem desduplicada |
| FCx-15 | a IA emitir SQL ou número | **falha** — 5 variações, incluindo injeção por valor |
| FCx-16 | resposta sem `trace_id` | **falha** — as três formas de resposta carregam rastro |
| FCx-17 | KPI `BLOCKED` produzir valor | **falha** — não há plano, não há view, não há número |

---

## 5. O catálogo, como ficou

| Status | KPIs |
|---|---|
| `CERTIFIED` (5) | `headcount`, `turnover_rate`, `women_in_leadership`, `hiring_volume`, `time_to_fill` |
| `DECLARED` (8) | `fte`, `tenure`, `span_of_control`, `gender_representation`, `pcd_representation`, `performance_distribution`, `time_to_hire`, `offer_acceptance_rate` |
| `BLOCKED` (5) | `internal_mobility_rate`, `promotion_rate`, `compa_ratio`, `pay_gap`, **`black_representation`** |

O que a camada responde hoje:

| KPI | Período | Valor | Trust | Limitado por |
|---|---|---|---|---|
| `headcount` | 2026-06 | 1.942 pessoas | CERTIFIED | — |
| `headcount` | 2025 | 2.038 pessoas | CERTIFIED | — |
| `turnover_rate` | 2024 | 0,2538 | CERTIFIED | — |
| `women_in_leadership` | 2026-06 | 0,4413 | CERTIFIED | — |
| `hiring_volume` | 2025 | 334 pessoas | **LIMITED** | cobertura (29,8%) |
| `time_to_fill` | 2025-Q2 | 72,5 dias | CERTIFIED | — |
| `fte` | 2026-06 | 1.852,75 | **LIMITED** | governança |
| `tenure` | 2026-06 | 34 meses | **LIMITED** | governança |
| `span_of_control` | 2026-06 | 1,89 | **LIMITED** | governança |
| `gender_representation` | 2026-06 | 0,5335 | **LIMITED** | governança |
| `pcd_representation` | 2026-06 | 0,0341 | **LIMITED** | governança |
| `time_to_hire` | 2025-Q2 | 42 dias | **LIMITED** | governança |
| `offer_acceptance_rate` | 2025-Q2 | 0,75 | **LIMITED** | governança |

Oito KPIs com dado limpo respondendo `LIMITED` é o efeito pretendido do
ADR-0029: certificação é ato de governança, não consequência de um limiar.

---

## 6. Desvios da SPEC

Seis, todos declarados. Nenhum reabre decisão da F0–F6.

### D7i-1 — `black_representation` passou de `DECLARED` para `BLOCKED`

**O que a SPEC dizia:** `DECLARED`, "calculável; fora do escopo de certificação
da v1.0".

**O que a implementação encontrou:** `race_ethnicity` chega em quatro
vocabulários e idiomas ao mesmo tempo, e **não existe `ref_race_mapping`**:

```
Branca 3.739 | Parda 2.612 | Preta 1.417 | No informado 1.133
Blanca   766 | Indigena 725 | Afrodescendiente 496 | Afrocolombiana 105
```

Agrupar "Parda" com "Afrodescendiente" hoje seria mapeamento por similaridade
atravessando fronteira de língua, que é exatamente o que o ADR-0020 proíbe. Pior:
definiria por conta própria quem é considerado negro em cinco países, o que é
decisão de negócio e de política de DEI, não de engenharia.

É o mesmo padrão do `movement_type`, encontrado numa dimensão diferente. O
bloqueador declara o que o resolve: `ref_race_mapping` governado, aprovado por
People Analytics com responsável e justificativa, **por país**.

### D7i-2 — `period_coverage` de `hiring_volume` é 2021-03, não 2016-01

Derivado da L3, como a SPEC manda. A primeira entrada com origem determinada
como `CONTRATACAO` é março de 2021, porque o ATS só existe a partir dali.

A consequência é o risco R-08 virando comportamento: perguntar
`hiring_volume` para 2018 **recusa por período fora de cobertura**, e não
responde zero. Zero é um valor; ausência de carga não é.

### D7i-3 — campo novo `period_rollup` no contrato

A validação 5 ("o grain do período é compatível com `period_grain`") não é
executável sem dizer **como** agregar. Sem regra, perguntar headcount por ano
somaria doze fotos mensais e devolveria doze vezes a empresa.

`period_rollup` declara isso no contrato, com dois valores possíveis:
`ultimo_periodo` para estoque (headcount, FTE, shares) e `soma` para fluxo
(contratações). É declaração, não inferência: um KPI sem `period_rollup` só
responde no grain do contrato.

### D7i-4 — `trust_resposta` é mínimo de **status**, não de número

A SPEC escreve `trust_resposta = min(trust_dado, teto do status)`. Implementar
isso como mínimo numérico exigiria inventar um número para o teto
(`DECLARED = 0,94`?), e número inventado é exatamente o score artificial que a
F5 proíbe.

A implementação compõe sobre a ordem `BLOCKED < LIMITED < CERTIFIED`, e mantém
`trust_dado` como o **único número medido** na resposta. `limitado_por` diz qual
dos dois elos prendeu: `DADO`, `GOVERNANCA` ou `COBERTURA`. AC-09 verifica as
cinco combinações.

### D7i-5 — a conexão da camada semântica não registra o schema `truth`

A Parte VIII declara três schemas: `truth`, `analytical`, `semantic`. A
implementação registra `truth` **apenas sob pedido explícito**
(`connect(cfg, with_truth=True)`), e o caminho da resposta nunca o pede.

O motivo: registrar a camada de verdade na mesma conexão criaria um nome que
resolve, e a proibição voltaria a depender de disciplina. Com o schema ausente,
`SELECT ... FROM truth.dim_employee` levanta erro, e AC-05 verifica isso
executando a consulta proibida. É a continuidade do teste F-13 da F6, que
proibiu o literal no código: aqui a proibição vira a ausência do objeto.

### D7i-6 — `source_tables` foi completado a partir dos planos

Sete contratos declaravam menos tabelas do que o cálculo de fato lê (faltavam
`dim_origin`, `dim_source_system`, `dim_job_level` em diferentes combinações).
O contrato é a autoridade, então ele foi completado e AC-04 passou a exigir
`tabelas do plano ⊆ source_tables do contrato` — um plano não pode ler o que o
contrato não declarou.

---

## 7. O que a implementação confirmou da SPEC

- **`internal_mobility_rate` com trust de dado 0,9939 e `BLOCKED`** continua
  sendo o caso que justifica o ADR-0029. O teste FC-06 fixa os dois números,
  491 e 601, no bloqueador.
- **`hiring_volume` soma exatamente 1.499** entre 2021 e 2026, e o recorte por
  origem devolve só `CONTRATACAO`. Contar `INDETERMINADA` daria 4.910 — a
  diferença é o tamanho da mentira que o filtro fixo evita (FC-09).
- **A cobertura de verificação vai na resposta**: `headcount` no recorte
  `pais=BR` avalia 34 dos 47 checks declarados. Os 13 restantes não são
  confiança nem perda; entram como caveat de cobertura de verificação, e um
  recorte sem check aplicável sai `INDETERMINADO`.
- **A taxa de não declaração viaja junto** em `women_in_leadership`,
  `gender_representation` e `pcd_representation`, e continua sem penalizar o
  trust (ADR-0022).

---

## 8. Pendências que a F7 não resolve, e nem deveria

| Pendência | Bloqueia | Quem resolve |
|---|---|---|
| `movement_type` sem DE/PARA governado | `internal_mobility_rate`, `promotion_rate` | People Analytics, na fila da F4 |
| `ref_race_mapping` inexistente | `black_representation` | People Analytics, por país |
| banda salarial só na camada de verdade | `compa_ratio`, `pay_gap` | onda 2 (`COMP_PLAN`) |
| nenhuma `interpretation_rule` registrada | INTERPRETATION em todos os 13 | People Analytics, com dono e data |
| 320 identidades da VivaMarket em revisão | cobertura de `hiring_volume` | fila de identidade da F4 |

Nenhuma delas se resolve escrevendo código, e é por isso que todas aparecem na
resposta em vez de sumirem nela.

---

## 9. Resumo executivo

A F7 fecha o contrato semântico entre People Analytics, os dados e a IA. O que
mudou de verdade:

1. **A proibição de calcular sobre RAW virou estrutura.** A IA emite um objeto
   que não tem campo para SQL, o executor é determinístico, e a camada de
   verdade não está registrada na conexão. Três garantias independentes, todas
   verificadas por teste em vez de confiadas a revisão.

2. **Confiança passou a ter duas dimensões.** Um número limpo sob uma definição
   que ninguém assinou deixou de parecer confiável — que é o modo de falha mais
   caro de uma camada semântica. A resposta agora diz **quem** resolve:
   pendência de dado vai para engenharia e qualidade, pendência de definição vai
   para People Analytics.

3. **Recusa virou produto.** Doze classes de recusa, cada uma dizendo o que
   seria necessário para responder, todas registradas no
   `semantic_query_log` — porque sem registrar a recusa ninguém descobre que a
   mesma pergunta é recusada toda semana pelo mesmo mapeamento pendente.

4. **Cinco KPIs certificados e cinco bloqueados**, e os bloqueados estão no
   catálogo com o bloqueador nomeado em vez de fora dele. Um KPI que hoje daria
   491 ou 601 conforme quem escreveu a consulta não é um KPI de qualidade baixa:
   é um KPI sem definição fechada, e essa é a resposta certa.

Sem MCP, sem agente, sem interface, sem commit.

---

## Apêndice — Correção M-06 (G-01 e G-02)

Aplicada depois da SPEC do MCP v0.1, que encontrou os dois gaps ao projetar
`breakdown_kpi`. Nenhum limiar novo, nenhuma definição de KPI alterada, nenhum
arquivo fora da camada semântica tocado.

| Arquivo | Mudança |
|---|---|
| `src/analytics/semantic/members.py` | **novo**: vocabulário dos estados governados e os geradores de projeção |
| `src/analytics/semantic/privacy.py` | **novo**: `minimum_n` por linha, com supressão complementar |
| `src/analytics/semantic/plans.py` | toda dimensão sai por membro nomeado, nunca pelo atributo |
| `src/analytics/semantic/ask.py` | supressão por linha, cobertura publicada, caveats de estado governado |
| `src/analytics/semantic/response.py` | `supressao()` aceita o detalhe por linha |
| `tests/semantic/test_privacy_and_members.py` | **novo**: 14 testes |

**G-01.** `minimum_n` passou a ser avaliado por linha do resultado, não só no
agregado. A linha suprimida mantém a chave do recorte e perde valor, numerador,
denominador e população. Como uma única linha suprimida seria reconstruível por
subtração contra o total — que `get_kpi` devolve —, a menor linha restante é
suprimida junto: supressão complementar. Sem nenhuma linha publicável, a
resposta inteira vira `SUPPRESSED`.

**G-02.** As views projetavam o atributo (`o.department`), nulo no membro
reservado. Agora projetam o nome do membro quando o surrogate key é negativo, e
`VALOR_AUSENTE` quando o campo de fato não veio — três estados distinguíveis:
pendência de governança, ausência de valor, membro de negócio.

A correção revelou uma segunda ocorrência do mesmo defeito, uma junção adiante:
**5.376 das 5.919 linhas de `fact_workforce_entry` têm `employee_sk = -1`**, e as
dimensões vindas de `dim_employee` viravam nulo. Hoje saem como
`SEM_CHAVE_DE_ORIGEM`.

Totais inalterados: `headcount` 2026-06 = 1.942, 2016-06 = 397,
`turnover_rate` 2024 = 0,253766. Suíte completa: **202 testes passando**.
