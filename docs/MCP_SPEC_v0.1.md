# MCP v0.1 — SPEC da fronteira controlada entre o Agent e a Semantic Layer

**Status: SPEC, aguardando aprovação. Nada implementado.**

Define as seis capacidades governadas que o futuro PeopleLens Agent poderá
exercer, e — mais importante — o que ele não poderá exercer de jeito nenhum,
porque a capacidade não existe na superfície.

> **Princípio central.** O agente não recebe uma conexão; recebe um conjunto
> fechado de capacidades. Não há acesso a RAW, a tabelas intermediárias, a SQL
> arbitrário, a arquivos, a conexão genérica de banco nem a qualquer função de
> escrita. A fronteira não é uma permissão negada: é uma ferramenta que não
> existe.

---

## Parte I — O que a F7 já garante, e o que falta

O MCP não reconstrói nenhuma proteção. Ele expõe as que já existem e acrescenta
as que só fazem sentido na fronteira com um agente.

| Garantia | Onde já vive | O que o MCP acrescenta |
|---|---|---|
| a IA emite consulta semântica, nunca SQL | ADR-0028, `SemanticQuery.parse` | o transporte: o schema da tool é o mesmo objeto |
| filtro fixo do KPI aplicado na view | `plans.py`, FCx-14 | nada; herda |
| camada de verdade não registrada na conexão | `executor.connect` | nada; herda |
| `trust_resposta = min(trust_dado, teto)` | ADR-0029 | um terceiro termo: o teto do ator |
| recusa explicada, 16 classes | `query.Refusal` | recusa como **resultado**, não erro de protocolo |
| toda resposta e recusa no `semantic_query_log` | `trace.registrar` | ator e tool na mesma linha, pelo mesmo `trace_id` |
| supressão por privacidade no agregado | `ask.py` | **por linha** no breakdown (gap G-01) |

### 1. O estado real do catálogo

Os seis KPIs que o MCP vai expor com valor, e os limites de cada um, vêm do
contrato — não do código do MCP:

| KPI | Status | `period_grain` | Cobertura | n mín | Unidade |
|---|---|---|---|---|---|
| `headcount` | CERTIFIED | mês | 2016-01 → 2026-06 | 5 | pessoas |
| `turnover_rate` | CERTIFIED | ano | 2016 → 2026 | 20 | taxa |
| `women_in_leadership` | CERTIFIED | mês | 2016-01 → 2026-06 | 20 | share |
| `hiring_volume` | CERTIFIED | mês | **2021-03** → 2026-06 | 5 | pessoas |
| `time_to_fill` | CERTIFIED | trimestre | 2021-Q1 → 2026-Q2 | 5 | dias |
| 8 KPIs `DECLARED` | — | vários | vários | 5 ou 20 | vários |
| 5 KPIs `BLOCKED` | — | — | — | — | nenhuma |

Nenhum KPI tem `interpretation_rules` hoje. **O teto de nível efetivo é CONTEXT
em todos os treze que respondem**, e o MCP não pode destravar isso.

---

## Parte II — A fronteira, e por que ela é a superfície

Há três formas de dar acesso a dados a um agente, e elas não são equivalentes:

| Forma | O que acontece |
|---|---|
| uma tool genérica (`execute_sql`, `query_database`, `read_table`) | toda proteção vira validação de string; o agente alcança o que souber nomear |
| tools específicas + permissões que negam o resto | a permissão é a defesa, e uma permissão mal configurada abre tudo |
| **só tools específicas, e nenhuma outra existe** | o que não está no catálogo não é expressável |

A v0.1 adota a terceira. Escrita não é negada por permissão: **não há tool de
escrita**, então não há chamada a negar. Permissão é a segunda cerca, mais
estreita, dentro de uma superfície que já é fechada — defesa em profundidade, e
não a defesa.

### 2. O que o MCP não faz, por construção

- não calcula KPI: o cálculo continua no executor determinístico da F7;
- não interpreta tabela: chama contrato semântico existente;
- não aceita SQL, nome de tabela, coluna ou junção em nenhum campo de entrada;
- não alcança a Truth Layer, RAW, standardized ou conformed;
- não altera dado, mapeamento, identidade, definição de KPI, trust ou governança;
- não contorna KPI `BLOCKED`, nem "aproxima" uma consulta para fazê-la passar;
- não transforma `INDETERMINADA` em outro estado, em lugar nenhum da resposta.

---

## Parte III — Arquitetura

### 3. O caminho quantitativo

```
        USER
          │  pergunta em linguagem natural
          ▼
   ┌──────────────────────────────────────────┐
   │ PeopleLens Agent            (fase futura)│
   │  traduz pergunta -> consulta semântica   │  ← único passo com latitude
   │  interpreta a resposta, não a calcula    │
   └───────────────────┬──────────────────────┘
                       │ chamada de tool tipada
                       ▼
   ┌──────────────────────────────────────────┐
   │ MCP  v0.1        6 capacidades, read-only│
   │  autoriza (escopo do ator)               │
   │  valida forma, aplica limites            │
   │  registra ator + tool + trace_id         │
   └───────────────────┬──────────────────────┘
                       │ SemanticQuery
                       ▼
   ┌──────────────────────────────────────────┐
   │ SEMANTIC LAYER (F7)                      │
   │  7 validações -> executor -> trust ->    │
   │  Response Contract -> trace              │
   └───────────────────┬──────────────────────┘
                       │ DuckDB, schema `semantic`
                       ▼
   ┌──────────────────────────────────────────┐
   │ ANALYTICAL MODEL (F6, L3)                │
   └──────────────────────────────────────────┘

   ✗ RAW, standardized, conformed, truth: sem nome que resolva neste caminho
```

### 4. RAG e conhecimento são outro caminho

O MCP da v0.1 é **quantitativo**: responde números, definições, confiança e
linhagem, todos derivados de contrato e de tabela analítica.

Política de RH, texto de norma, histórico de decisão e qualquer conhecimento não
estruturado **não entram aqui**. Serão um caminho separado, com ferramentas
próprias, e a razão é a mesma que o ADR-0016 já registrou: um número e um
trecho de documento têm regimes de evidência diferentes. Misturá-los na mesma
tool faria uma citação de política virar evidência de um número.

```
USER -> Agent ─┬─> MCP quantitativo (esta SPEC)   -> Semantic Layer -> L3
               └─> [futuro] MCP de conhecimento   -> RAG            -> documentos
```

Nenhuma tool desta SPEC lê documento, e nenhuma tool futura de conhecimento
devolverá número calculado.

---

## Parte IV — Envelope comum

Toda tool devolve o mesmo envelope. O agente aprende uma forma, não seis.

```yaml
ok:              true | false          # respondeu com conteúdo útil?
outcome:         ANSWER | REFUSAL | SUPPRESSED | ERROR
request_id:      str                   # do chamador, ecoado; gerado se ausente
trace_id:        str                   # 16 hex, sempre presente, inclusive em recusa
tool:            str
kpi:                                   # ausente em erro de parâmetro
  id: str
  version: str
  status: CERTIFIED | DECLARED | BLOCKED | DEPRECATED | DRAFT
  owner: str
data:            objeto | null         # a carga da tool; null quando não houve resposta
trust:           objeto | null
response_level:                        # sempre presente quando há KPI resolvido
  requested: FACT | CONTEXT | INTERPRETATION | CAUSALITY
  granted:   FACT | CONTEXT | null
  ceiling_from: EVIDENCIA | GOVERNANCA | ATOR | TRUST
refusal:         objeto | null
suppressed:      objeto | null
limits:          objeto                # o que foi aplicado nesta chamada
caveats:         [str]
lineage_ref:                           # como pedir a linhagem desta resposta
  tool: get_lineage
  trace_id: str
```

**Regra do envelope:** `data` e `refusal` nunca são ambos preenchidos, e pelo
menos um dos quatro — `data`, `refusal`, `suppressed`, `error` — sempre é.

### 5. Vocabulário: sem tradução na fronteira

Nomes de tool e chaves do envelope em inglês. **Valores de domínio — classes de
recusa, status de trust, status de KPI, nomes de dimensão — atravessam a
fronteira exatamente como a Semantic Layer os emite**, em português onde é o
caso (`KPI_BLOQUEADO`, `DIMENSAO_NAO_PERMITIDA`, `PENDENCIA`, `pais`,
`departamento`).

Traduzir criaria uma tabela de correspondência entre dois vocabulários para o
mesmo conceito — que é precisamente o defeito que este projeto já encontrou duas
vezes, no `movement_type` e no `race_ethnicity`. Uma tradução não declarada
diverge em silêncio. Decisão M-03, para sua aprovação.

---

## Parte V — Catálogo das seis ferramentas

### 6. `get_kpi`

**Propósito.** Um valor, de um KPI, num período, sem quebra por dimensão. É a
tool que responde "quantas pessoas temos no Brasil hoje".

**Input**

```yaml
kpi:            str                  # obrigatório; id do catálogo
period:                              # obrigatório
  grain:  mes | trimestre | ano | ciclo
  from:   str                        # YYYY-MM | YYYY-Qn | YYYY | YYYY-Hn
  to:     str                        # opcional; default = from
filters:                             # opcional
  - dimension: str                   # nome de negócio
    in: [str]                        # termos do vocabulário governado
requested_level: FACT | CONTEXT      # opcional; default FACT
kpi_version:    str                  # opcional; default = versão corrente
request_id:     str                  # opcional
```

Campo desconhecido **reprova**. Não existe `sql`, `table`, `column`, `where`,
`expression`, `limit_rows` nem `raw`. O input é o `SemanticQuery` do ADR-0028,
transportado — não uma segunda linguagem de consulta.

**Output (`data`)**

```yaml
value:      number | null
unit:       str                      # pessoas, taxa, share, dias, meses, FTE
period:     {grain, from, to}
population: int                      # pessoas (ou requisições) no recorte
filters_applied:
  declared_by_contract: [str]        # filtros fixos do KPI, em linguagem de negócio
  requested_by_caller:  [{dimension, in}]
exclusions: [str]                    # o que ficou de fora, e por quê
coverage:
  population_covered: number | null  # quando o contrato declara cobertura
  verification:       number | null  # checks avaliados / declarados
  nao_declaracao:     {campo: taxa}  # quando aplicável
```

**Validações.** As sete da F7, na ordem delas, mais três da fronteira:
forma do input (campo desconhecido reprova); escopo do ator; limite de períodos
por chamada.

**Permissão.** `kpi:read:value`.

**Erros e recusas esperados.** `KPI_INEXISTENTE`, `KPI_BLOQUEADO`,
`KPI_EM_RASCUNHO`, `DIMENSAO_NAO_PERMITIDA`, `TERMO_DESCONHECIDO`,
`PERIODO_FORA_DE_COBERTURA`, `GRAIN_INCOMPATIVEL`, `MAPEAMENTO_PENDENTE`,
`NIVEL_SEM_EVIDENCIA`, `SEM_DADO_NO_PERIODO`, `VERSAO_INEXISTENTE`,
`PREDICADO_INDISPONIVEL`; supressão por privacidade.

**Limites.** Máximo 24 períodos por chamada. Sem `dimensions` — quebra é
`breakdown_kpi`.

**Exemplo de chamada**

```json
{"kpi": "headcount",
 "period": {"grain": "mes", "from": "2026-06"},
 "filters": [{"dimension": "pais", "in": ["Brasil"]}]}
```

**Exemplo de resposta**

```yaml
ok: true
outcome: ANSWER
trace_id: 5baa389be7ae47a2
tool: get_kpi
kpi: {id: headcount, version: 1.0.0, status: CERTIFIED, owner: people-analytics}
data:
  value: 1324
  unit: pessoas
  period: {grain: mes, from: 2026-06, to: 2026-06}
  population: 1324
  filters_applied:
    declared_by_contract: ["apenas o sistema de registro do período"]
    requested_by_caller: [{dimension: pais, in: [Brasil]}]
  exclusions: ["linhas em quarentena", "pessoa sem chave de origem"]
  coverage: {population_covered: null, verification: 0.7234}
trust:
  status: CERTIFIED
  score: 0.998555
  limitado_por: NENHUM
  motivo: PENDENCIA
  trust_dado: CERTIFIED
  trust_governanca: CERTIFIED
  perda_por_erro: 0.000186
  perda_por_pendencia: 0.001259
  perda_por_classe: {INVALIDO: 0.000186, NAO_MAPEADO: 0.001075,
                     IDENTIDADE_NAO_RESOLVIDA: 0.000184}
  recorte_usado: "pais=BR"
response_level: {requested: FACT, granted: FACT, ceiling_from: EVIDENCIA}
caveats:
  - "cobertura de verificação de 72%: 34 de 47 checks declarados rodaram neste recorte"
  - "perda de confiança por pendência de 0.0013: há decisão ou vínculo em aberto"
lineage_ref: {tool: get_lineage, trace_id: 5baa389be7ae47a2}
```

Note o que **não** está na resposta: `fact_headcount_snapshot`,
`is_system_of_record`, `org_sk`, qualquer join. O filtro fixo aparece em
linguagem de negócio, porque o agente precisa saber que ele existe sem precisar
saber como se chama.

---

### 7. `compare_kpi`

**Propósito.** O mesmo KPI, no mesmo recorte, em duas janelas — a base do nível
CONTEXT. É a tool que responde "e comparado com o ano passado?".

**Input**

```yaml
kpi:      str
period:   {grain, from, to}
compare_to:                          # obrigatório; base DECLARADA
  periodo_anterior | mesmo_periodo_ano_anterior | media_da_populacao
filters:  [...]                      # igual ao get_kpi
requested_level: CONTEXT             # fixo; pedir FACT aqui é get_kpi
```

**Output (`data`)**

```yaml
current: {value, period, population}
baseline: {value, period, population, trust_status}
delta:          number
delta_relative: number | null
direction:      SUBIU | CAIU | ESTAVEL
statement_kind: ASSOCIACAO           # sempre; nunca CAUSA
```

**Validações.** Tudo do `get_kpi`, para as **duas** janelas. A base precisa ser
ela própria respondível: se a janela de comparação cai fora da cobertura, ou é
recusada por qualquer das sete validações, a tool **não compara** — devolve
`COMPARACAO_NAO_RESPONDIVEL` com o motivo da base. Comparar com um número que
não existe é pior do que não comparar.

Duas versões diferentes do mesmo KPI **nunca** são comparadas sem declaração
explícita (ADR-0030): `COMPARACAO_ENTRE_VERSOES`.

**Permissão.** `kpi:read:value`.

**Limites.** Exatamente duas janelas. Nunca dois KPIs diferentes — comparar
`headcount` com `turnover_rate` é aritmética entre grandezas distintas, e a
tool não tem como expressá-la.

**Recusa característica**

```yaml
ok: false
outcome: REFUSAL
tool: compare_kpi
kpi: {id: hiring_volume, version: 1.0.0, status: CERTIFIED}
refusal:
  classe: COMPARACAO_NAO_RESPONDIVEL
  mensagem: >-
    a base de comparação (2020) está fora da cobertura de hiring_volume,
    que tem dado de 2021-03 a 2026-06. A resposta correta não é zero.
  o_que_resolveria: "comparar com um período dentro de 2021-03..2026-06"
  detalhe: {cobertura: ["2021-03", "2026-06"], base_pedida: "2020"}
trace_id: 9f2c1ab4de075566
```

---

### 8. `breakdown_kpi`

**Propósito.** O mesmo KPI, um período, quebrado por até duas dimensões
permitidas. É a tool que responde "e por país?".

**Input**

```yaml
kpi:        str
period:     {grain, from, to}
dimensions: [str]                    # 1 ou 2, todas em allowed_dimensions
filters:    [...]
order_by:   value | dimension        # opcional; default value desc
top_n:      int                      # opcional; ≤ 50
```

**Output (`data`)**

```yaml
dimensions: [str]
rows:
  - keys:       {dimension: member}  # membro NOMEADO, nunca null
    value:      number | null
    population: int
    suppressed: bool                 # true quando a linha ficou abaixo do n mínimo
    trust_status: str                # trust do recorte fino daquela linha
total:
  value:      number | null          # null quando a medida não é somável
  population: int
rows_suppressed: int
rows_returned:   int
rows_available:  int
```

**A regra que define esta tool:** `minimum_n` vale **por linha**, não só no
total. Uma quebra pode passar no agregado e vazar num recorte pequeno. Hoje ela
vaza — ver gap G-01 na Parte XIII, com o caso real. A linha suprimida continua
na saída, com `suppressed: true`, `value: null` e a população **omitida**, para
que o agente saiba que o recorte existe sem saber quanta gente há nele.

**Membro nulo não sai.** Quando a dimensão resolve para membro reservado, a
linha traz o nome do membro (`UNMAPPED`, `DECISAO_PENDENTE`,
`TRADUCAO_PENDENTE`, `NAO_INFORMADO`, `INDETERMINADA`) e nunca `null` — ADR-0025.
Hoje sai `null` — gap G-02, com o caso real.

**Permissão.** `kpi:read:value`.

**Limites.** Máximo 2 dimensões, 50 linhas retornadas, 200 linhas avaliadas.
Excedeu, é recusa `LIMITE_DE_RESULTADO_EXCEDIDO` dizendo o que estreitar — nunca
truncagem silenciosa, porque um top-50 apresentado como total é um número errado
com cara de certo.

---

### 9. `get_kpi_definition`

**Propósito.** O contrato em linguagem de negócio: o que o KPI mede, quem
assina, o que ele exclui, até onde vai, e o que o bloqueia. É a tool que
responde "o que vocês chamam de turnover?" — e é a que impede o agente de
inventar a definição.

**Input**

```yaml
kpi:     str | null                  # null lista o catálogo inteiro, resumido
version: str                         # opcional
include: [definition, limits, dependencies, blockers, versions]
```

**Output (`data`)**

```yaml
kpi_id, name, description
business_definition: str             # a frase que People Analytics assina
formula_plain:       str             # em linguagem de negócio, NUNCA SQL
grain:               str
population:          str
period_grain, period_coverage, period_rollup
allowed_dimensions:  [str]
fixed_filters:       [{regra_plain, porque}]
exclusions:          [{o_que, porque}]
minimum_n:           int
response_levels:
  ceiling: CONTEXT
  why:     "sem interpretation_rules registradas"
governance:
  owner, version, status, certified_at
  blockers: [{motivo, resolvido_por}]
dependencies:
  checks_count: int                  # contagem, não a lista de 47 ids
  mappings:     [str]
versions_queryable: [str]
```

**`formula_plain` nunca contém SQL, nome de tabela ou coluna.** A definição que
o agente lê é a mesma que uma pessoa de RH leria. `source_tables` **não é
exposto** nesta tool: o agente não precisa dele para explicar um número, e
expô-lo daria a ele nomes físicos para tentar usar.

**Permissão.** `kpi:read:definition` — a mais ampla, porque saber o que a
empresa mede não revela quanto ela mede.

**Erros.** `KPI_INEXISTENTE`, `VERSAO_INEXISTENTE`.

**Um KPI `BLOCKED` responde normalmente aqui.** Essa é a razão de a tool
existir: `internal_mobility_rate` não dá número, e dá explicação.

```yaml
data:
  kpi_id: internal_mobility_rate
  business_definition: "Movimentações internas de transferência ou lateral sobre
                        o headcount médio."
  governance:
    status: BLOCKED
    blockers:
      - motivo: >-
          movement_type sem DE/PARA aprovado: dois vocabulários coexistem
          (Promotion 491 e PROMOCAO 110, Transfer 480 e TRANSFERENCIA 92).
          O KPI daria 491 ou 601 conforme quem escreveu a consulta.
        resolvido_por: >-
          DE/PARA governado de movement_type, aprovado na fila da F4 com
          responsável e justificativa
  response_levels: {ceiling: null, why: "KPI em BLOCKED"}
```

---

### 10. `get_trust`

**Propósito.** A confiança de um KPI num recorte, **sem calcular o valor**. É a
tool que responde "posso confiar nesse número?" e, principalmente, "o que
precisa acontecer para eu poder".

**Input**

```yaml
kpi:     str
scope:                               # opcional; default GLOBAL
  filters: [{dimension, in}]
period:  {grain, from, to}           # opcional
explain: bool                        # default true
```

**Output (`data`)**

```yaml
status:            CERTIFIED | LIMITED | BLOCKED | INDETERMINADO
score:             number | null     # o ÚNICO número medido
trust_dado:        str
trust_governanca:  str | null
limitado_por:      DADO | GOVERNANCA | COBERTURA | ATOR | NENHUM
motivo:            str
composition:
  formula: "min(trust_dado, teto_do_status, teto_do_ator)"
  bands:   {CERTIFIED: 0.95, LIMITED: 0.70, piso_pendencia: 0.40}
attribution:
  perda_por_erro:      number | null
  perda_por_pendencia: number | null
  perda_por_classe:    {classe: number}
verification:
  checks_avaliados: int
  checks_declarados: int
  coverage: number
  nota: "check não avaliado não é confiança nem perda"
what_would_improve_it: [str]         # quando explain=true
```

**As bandas são devolvidas, e são as da F5.** O agente não as recalcula, não as
ajusta e não as compara com banda de mercado. ADR-0023 continua valendo.

**`what_would_improve_it`** é o campo que transforma trust em ação. Para
`hiring_volume`: "trabalhar a fila de identidade do ATS eleva a cobertura de
origem acima de 29,8%". Para um KPI `DECLARED`: "certificar o KPI, o que é
decisão de People Analytics e não consequência do dado".

**Permissão.** `kpi:read:trust`.

**Limites.** Não devolve resultado de check individual nem linha reprovada —
isso é lineage, e tem escopo próprio.

---

### 11. `get_lineage`

**Propósito.** Os seis degraus, da resposta até o `_row_id` da fonte. É a tool
que responde "como você chegou nesse número?".

**Input**

```yaml
trace_id: str                        # de uma resposta anterior
kpi:      str                        # alternativa: linhagem só de definição
depth:    definition | rule | table | source
```

Um dos dois é obrigatório. Com `trace_id`, a linhagem é **daquela resposta**,
com a execução da L3 que a produziu. Com `kpi`, é a linhagem da definição, sem
degrau de fonte — porque não houve resposta a rastrear.

**Output (`data`)**

```yaml
resposta:          {trace_id, level, value, scope, trust}
kpi:               {id, version, owner, status, certified_at}
definicao:         {business_definition, formula_plain, population,
                    filters, exclusions}
regra:             {checks_count, mappings, trust_recorte,
                    perda_por_classe, membros_excluidos}
tabela_analitica:  {layer: analytical, tabelas, filtros_fixos,
                    linhas_consideradas, l3_run_id}
fonte:
  por_onde: "source_row_id nas tabelas da L3"
  depois:   "transformation_log: valor original, sistema de origem, regra"
  e_entao:  "arquivo bruto em data/raw, imutável"
  acesso:   NAO_EXPOSTO_POR_ESTE_MCP
```

**O degrau `fonte` descreve o caminho; não o percorre.** Ele diz por onde uma
pessoa com acesso chega ao valor original — e não devolve o valor original, o
`source_row_id` de ninguém, nem uma amostra de linhas. Percorrer o último
degrau é leitura de RAW, e nenhuma tool deste MCP faz isso.

É aqui que `depth: table` é o máximo útil para o agente, e `depth: source`
devolve a descrição do caminho e o aviso de acesso.

**Permissão.** `kpi:read:lineage`.

**Erros.** `TRACE_INEXISTENTE` (o `trace_id` não está no `semantic_query_log`),
`LINEAGE_INDISPONIVEL` (a resposta é anterior ao registro, ou a execução da L3
que a produziu não existe mais).

---

## Parte VI — Permissões

### 12. Quatro escopos, por natureza de informação

| Escopo | Tools | O que revela | Sensibilidade |
|---|---|---|---|
| `kpi:read:definition` | `get_kpi_definition` | o que a empresa mede e quem assina | baixa |
| `kpi:read:trust` | `get_trust` | quanto se pode afirmar, e o que falta | baixa |
| `kpi:read:lineage` | `get_lineage` | como o número foi produzido | média |
| `kpi:read:value` | `get_kpi`, `compare_kpi`, `breakdown_kpi` | os números | **alta** |

A separação não é burocrática. `kpi:read:definition` sem `kpi:read:value` é um
ator que pode explicar a metodologia e não pode ver resultado — que é
exatamente o perfil de quem está construindo ou auditando o catálogo.

### 13. Contrato do ator

Autenticação corporativa fica para depois. O que a v0.1 define é o **contrato
que a autenticação vai preencher**:

```yaml
actor:
  id:            str                 # referência opaca, nunca e-mail ou nome
  type:          human | agent | service
  scopes:        [str]
  max_response_level: FACT | CONTEXT | INTERPRETATION | CAUSALITY
  dimension_deny: [str]              # dimensões que este ator não recorta
  kpi_allow:      [str] | ALL
```

Três observações que importam mais que o schema:

1. **`actor.id` é referência opaca.** Não é e-mail, não é nome, não é
   `employee_id`. O log liga a chamada a uma pessoa sem guardar quem ela é.
2. **Nenhum escopo concede escrita**, porque não há tool de escrita. Um escopo
   `kpi:write:*` não existe e não deve ser criado "para o futuro": escopo que
   existe acaba sendo concedido.
3. **`max_response_level` do ator compõe com o teto de evidência**, ele não o
   substitui. Um ator com `INTERPRETATION` não desbloqueia INTERPRETATION num
   KPI sem `interpretation_rules` — ADR-0033.

### 14. A composição final

```
response_level = min( nível pedido,
                      teto de evidência   (F7: status + regra + estudo),
                      teto do ator        (v0.1) )

trust_resposta = min( trust_dado          (F5, medido),
                      teto do status      (F7, ADR-0029),
                      teto do ator        (v0.1) )
```

O campo `ceiling_from` diz qual dos três prendeu. Sem ele, um agente que recebe
CONTEXT não sabe se deve pedir certificação a People Analytics, corrigir dado
com engenharia, ou pedir permissão ao administrador — três ações, três pessoas.

---

## Parte VII — Erros e recusas estruturadas

### 15. Três resultados negativos, e eles não se confundem

| `outcome` | Significado | Quem resolve |
|---|---|---|
| `REFUSAL` | a pergunta é válida; a resposta não é sustentável | depende da classe |
| `SUPPRESSED` | há resposta; ela não sai por **privacidade** | ninguém: é assim mesmo |
| `ERROR` | a chamada está malformada ou o ator não tem escopo | quem chamou |

Misturar os três é o erro mais caro possível nesta fronteira: um agente que lê
"supressão por n mínimo" como "erro" tenta de novo com outro recorte até
conseguir — que é reidentificação por tentativa.

### 16. Catálogo de resultados negativos

Herdados da Semantic Layer, verbatim:

| Classe | `outcome` | Quando |
|---|---|---|
| `KPI_INEXISTENTE` | REFUSAL | id fora do catálogo; a recusa lista os válidos |
| `KPI_BLOQUEADO` | REFUSAL | KPI `BLOCKED`; devolve bloqueador e o que o resolve |
| `KPI_EM_RASCUNHO` | REFUSAL | KPI `DRAFT` |
| `DIMENSAO_NAO_PERMITIDA` | REFUSAL | recorte fora de `allowed_dimensions` |
| `TERMO_DESCONHECIDO` | REFUSAL | termo fora do vocabulário; **nunca aproxima** |
| `PERIODO_FORA_DE_COBERTURA` | REFUSAL | fora de `period_coverage`; **não é zero** |
| `GRAIN_INCOMPATIVEL` | REFUSAL | grain mais fino que o contrato, ou sem `period_rollup` |
| `MAPEAMENTO_PENDENTE` | REFUSAL | dependência com pendência bloqueante |
| `NIVEL_SEM_EVIDENCIA` | REFUSAL | nível acima do teto; diz o que faltaria |
| `SEM_DADO_NO_PERIODO` | REFUSAL | sem linha no recorte; **não é zero** |
| `VERSAO_INEXISTENTE` | REFUSAL | versão pedida não registrada |
| `COMPARACAO_ENTRE_VERSOES` | REFUSAL | fórmula mudou entre as janelas |
| `COMPARACAO_NAO_RESPONDIVEL` | REFUSAL | a base não é ela própria respondível |
| `PREDICADO_INDISPONIVEL` | REFUSAL | o termo resolve para algo que o KPI não expõe |
| `SEM_PLANO_DE_EXECUCAO` | REFUSAL | KPI sem plano — garantia estrutural do FCx-17 |

Acrescentados pela fronteira:

| Classe | `outcome` | Quando |
|---|---|---|
| `TRUST_INSUFICIENTE` | REFUSAL | `trust_resposta` = BLOCKED ou INDETERMINADO |
| `LIMITE_DE_RESULTADO_EXCEDIDO` | REFUSAL | breakdown acima do limite; diz o que estreitar |
| `TRACE_INEXISTENTE` | REFUSAL | `trace_id` não está no log |
| `LINEAGE_INDISPONIVEL` | REFUSAL | resposta anterior ao registro |
| `PARAMETRO_INVALIDO` | **ERROR** | campo desconhecido, tipo errado, formato errado |
| `ESCOPO_INSUFICIENTE` | **ERROR** | ator sem o escopo da tool |
| `CAPACIDADE_INEXISTENTE` | **ERROR** | tool que não existe na superfície |

Toda recusa carrega os três campos da F7 — `classe`, `mensagem`,
`o_que_resolveria` — e `o_que_resolveria` **não é opcional**. Recusa que não diz
o caminho é só uma porta fechada, e um agente diante de porta fechada inventa.

### 17. `KPI LIMITED` não é recusa

`LIMITED` **responde**, com o teto de nível em CONTEXT, a ressalva no `caveats`
e `limitado_por` dizendo o lado. Tratar `LIMITED` como erro faria oito dos
treze KPIs que respondem hoje desaparecerem do agente — e eles são informação
honesta, não informação ruim.

---

## Parte VIII — Limites

| Limite | Valor | Por quê |
|---|---|---|
| períodos por chamada | 24 | uma série de dois anos cabe; uma década vira breakdown |
| dimensões no breakdown | 2 | três dimensões pulverizam o recorte abaixo do n mínimo |
| linhas retornadas | 50 | acima disso é relatório, não resposta de agente |
| linhas avaliadas | 200 | excedeu, recusa dizendo o que estreitar |
| tools por resposta do agente | — | fora do escopo do MCP; é política do harness |
| timeout por chamada | 30 s | consulta que não termina vira erro, não resposta parcial |
| tamanho do payload | 256 KB | acima disso o agente não consegue raciocinar sobre a saída |

**Nenhuma truncagem silenciosa.** Todo limite atingido vira recusa explicada.
Devolver as 50 primeiras linhas de 300 e chamar isso de resposta é o mesmo erro
que responder zero para período sem carga.

---

## Parte IX — Observabilidade

### 18. O que cada chamada registra

```yaml
request_id:       str
trace_id:         str                # o MESMO da Semantic Layer
timestamp:        iso8601
tool:             str
actor_ref:        str                # referência opaca
actor_type:       human | agent | service
scopes_used:      [str]
kpi_id:           str | null
kpi_version:      str | null
period:           {grain, from, to} | null
dimensions:       [str]              # NOMES, nunca valores
filter_dimensions: [str]             # NOMES, nunca os termos filtrados
outcome:          ANSWER | REFUSAL | SUPPRESSED | ERROR
refusal_class:    str | null
trust_status:     str | null
trust_score:      number | null
response_level:   str | null
rows_returned:    int
rows_suppressed:  int
duration_ms:      int
l3_run_id:        str | null
```

### 19. O que **não** se registra

- nenhum `party_key`, `employee_id`, `source_employee_id`, nome ou identificador
  de pessoa;
- nenhuma linha do resultado;
- **nenhum valor de filtro** — registra-se que houve filtro por `pais`, não
  quais países. Uma sequência de consultas filtradas estreitando o recorte é
  um traço de reidentificação, e guardá-la cria o risco que a supressão por n
  mínimo existe para evitar;
- nenhum valor de KPI abaixo do n mínimo (não há valor a registrar, mas a regra
  fica escrita);
- nenhuma pergunta em linguagem natural — ela pode conter nome de pessoa. O
  `semantic_query_log` da F7 guarda `pergunta`; na fronteira com o agente esse
  campo **não é propagado** sem decisão explícita. Decisão M-04.

### 20. Relação com o `semantic_query_log`

O log do MCP **não duplica** o da F7. Ele registra ator, tool, escopo e duração,
e referencia o mesmo `trace_id`. Duas tabelas que descrevem a mesma chamada
divergem — é a mesma razão pela qual `depends_on_checks` é derivado e não
digitado.

```
mcp_call_log.trace_id  ──>  semantic_query_log.trace_id  ──>  l3_run_id
      quem chamou              o que foi perguntado           qual carga
```

---

## Parte X — Matriz Tool × Permission × Guardrail

| Tool | Escopo | Read-only | Calcula? | Alcança L3? | Guardrails aplicados |
|---|---|---|---|---|---|
| `get_kpi` | `kpi:read:value` | sim | não (delega) | via `semantic` | 7 validações + escopo + n mínimo + teto de nível + 24 períodos |
| `compare_kpi` | `kpi:read:value` | sim | não | via `semantic` | tudo acima, **nas duas janelas** + versão + base respondível |
| `breakdown_kpi` | `kpi:read:value` | sim | não | via `semantic` | tudo do `get_kpi` + **n mínimo por linha** + membro nomeado + 2 dims + 50 linhas |
| `get_kpi_definition` | `kpi:read:definition` | sim | não | **não** | sem `source_tables`, sem SQL, sem nome físico |
| `get_trust` | `kpi:read:trust` | sim | não | **não** | bandas da F5 devolvidas, nunca recalculadas; sem check individual |
| `get_lineage` | `kpi:read:lineage` | sim | não | **não** | degrau `fonte` descreve o caminho, não o percorre |

| Guardrail estrutural | Como é garantido | Onde já é testado |
|---|---|---|
| sem SQL arbitrário | campo desconhecido reprova no parse | FCx-15 (F7) |
| sem RAW / truth | schema não registrado na conexão | AC-05 (F7) |
| sem escrita | **não existe tool de escrita** | ACm-02 (novo) |
| KPI `BLOCKED` sem valor | não há plano de execução | FCx-17 (F7) |
| filtro fixo sempre aplicado | está na view, não na consulta | FCx-14 (F7) |
| `INDETERMINADA` preservada | `is_hire` é o único critério | FC-09 (F7) |

Seis dos guardrails já têm teste em verde na F7. O MCP herda; não reimplementa.

---

## Parte XI — Failure cases

Doze, todos verificáveis, cada um como teste na implementação.

| # | O que deve falhar | Evidência esperada |
|---|---|---|
| **FCm-01** | alcançar RAW por qualquer tool | nenhum input aceita tabela; a conexão não registra o schema |
| **FCm-02** | executar SQL arbitrário | `PARAMETRO_INVALIDO` em `sql`, `table`, `where`, `expression`, `query` |
| **FCm-03** | obter valor de KPI `BLOCKED` | `KPI_BLOQUEADO` nas três tools de valor; `data` = null |
| **FCm-04** | usar dimensão fora de `allowed_dimensions` | `DIMENSAO_NAO_PERMITIDA` com a lista do que responde |
| **FCm-05** | alterar mapeamento | nenhuma tool escreve; `CAPACIDADE_INEXISTENTE` para nome inventado |
| **FCm-06** | alterar Trust | idem; e `get_trust` não tem campo de entrada que altere banda |
| **FCm-07** | consultar a Truth Layer | nome não resolve; `PARAMETRO_INVALIDO` se vier como parâmetro |
| **FCm-08** | transformar `INDETERMINADA` em contratação | `hiring_volume` soma 1.499, nunca 4.910; breakdown por origem só devolve `CONTRATACAO` |
| **FCm-09** | ultrapassar o Response Level permitido | `NIVEL_SEM_EVIDENCIA`; INTERPRETATION não sai sem regra registrada |
| **FCm-10** | vazar recorte abaixo do n mínimo num breakdown | linha com `suppressed: true`, `value: null`, população omitida |
| **FCm-11** | devolver `null` como membro de dimensão | membro reservado nomeado, ou recusa |
| **FCm-12** | truncar resultado em silêncio | `LIMITE_DE_RESULTADO_EXCEDIDO`, nunca top-50 apresentado como total |

**FCm-10 e FCm-11 falham hoje.** São os gaps da Parte XIII, e é por isso que
`breakdown_kpi` não pode ser implementado antes deles.

---

## Parte XII — Acceptance criteria

| # | Critério |
|---|---|
| ACm-01 | as seis tools existem, e **nenhuma outra** é registrada no servidor |
| ACm-02 | nenhuma tool declara operação de escrita; o servidor anuncia `read_only` |
| ACm-03 | todo input rejeita campo desconhecido, com `PARAMETRO_INVALIDO` |
| ACm-04 | nenhum input aceita nome de tabela, coluna, junção ou fragmento de SQL |
| ACm-05 | toda resposta, recusa e supressão carrega `trace_id` |
| ACm-06 | `data` e `refusal` nunca coexistem; sempre há um dos quatro resultados |
| ACm-07 | recusa é `outcome: REFUSAL` com `ok: false`, **não** erro de protocolo |
| ACm-08 | toda recusa preenche `o_que_resolveria` |
| ACm-09 | `SUPPRESSED` é distinto de `REFUSAL` e de `ERROR`, e usa a palavra privacidade |
| ACm-10 | `response_level.granted = min(pedido, evidência, ator)`, com `ceiling_from` |
| ACm-11 | `trust` devolvido é o da F7, sem recálculo; bandas inalteradas |
| ACm-12 | KPI `BLOCKED` responde em `get_kpi_definition` e recusa nas tools de valor |
| ACm-13 | `get_kpi_definition` não expõe `source_tables` nem SQL |
| ACm-14 | `breakdown_kpi` suprime **por linha** e nunca devolve membro `null` |
| ACm-15 | `get_lineage` descreve o degrau de fonte sem devolver `source_row_id` |
| ACm-16 | o log registra nomes de dimensão, nunca valores de filtro nem identificador de pessoa |
| ACm-17 | `mcp_call_log.trace_id` casa com `semantic_query_log.trace_id` |
| ACm-18 | escopo ausente produz `ESCOPO_INSUFICIENTE` antes de qualquer execução |

---

## Parte XIII — Gaps que bloqueiam a implementação

Dois, ambos encontrados ao projetar `breakdown_kpi`, ambos na F7, ambos com caso
real. Nenhum é escopo novo: são precondições.

### G-01 — `minimum_n` é aplicado no agregado, não por linha

A F7 compara `minimum_n` com a **soma** das populações do resultado. Num
breakdown, o total passa e um recorte pequeno sai.

Caso real, `women_in_leadership` (n mínimo 20) por país em 2019-06:

| país | valor | população |
|---|---|---|
| AR | 0,6667 | **6** |
| BR | 0,5333 | 75 |
| CO | — | **1** |

Nada foi suprimido, porque o total (82) passa. A linha do CO com população 1
revela o gênero de uma única pessoa em liderança. É supressão por privacidade
falhando exatamente onde ela existe para funcionar.

**Correção necessária:** `minimum_n` avaliado por linha do resultado, com a
linha permanecendo visível e sem valor. Afeta `ask.py` e é precondição de
`breakdown_kpi`.

### G-02 — membro reservado vira `null` na camada semântica

O ADR-0025 decidiu que pendência de governança vira **membro nomeado, nunca
nulo**, e a L3 cumpre: `dim_organization` tem `org_sk = -1` com
`code = 'UNMAPPED'`, `label = 'sem mapeamento aprovado'`,
`finding_class = 'NAO_MAPEADO'`.

As views da F7 projetam `o.department`, que é **nulo** no membro reservado. O
nome se perde na última camada.

O tamanho disso surpreende: **40 dos 126 meses da série — 2016-01 a 2019-04, a
era inteira do `HRIS_LEGACY` — têm 100% das linhas no membro reservado**, 18.813
de 126.424 linhas.

```
headcount por departamento, 2016-06:
  {departamento: null, valor: 397}     ← única linha; deveria ser UNMAPPED
```

Ou seja: `headcount` quebrado por país, business unit ou departamento **não é
respondível nos primeiros 40 meses**, e hoje é respondido com `null` no lugar do
membro. Um agente lendo isso reporta "397 pessoas em departamento
não-identificado" como se fosse um departamento.

**Correção necessária:** a view projeta o nome do membro reservado quando o
`sk` é negativo, e `breakdown_kpi` nunca devolve `null` como chave. Precondição
de `breakdown_kpi`.

---

## Parte XIV — Decisões necessárias

| # | Decisão | Recomendação |
|---|---|---|
| **M-01** | escopo de seis tools, read-only, sem tool genérica | **aprovar**: é o princípio inteiro |
| **M-02** | recusa é resultado da tool, não erro de protocolo (ADR-0032) | **aprovar**: é o que permite o agente relatar o motivo em vez de tentar de novo |
| **M-03** | valores de domínio atravessam sem tradução; só o envelope é em inglês | **aprovar**: tradução não declarada diverge em silêncio, como `movement_type` |
| **M-04** | a pergunta em linguagem natural **não** é propagada ao log do MCP | **aprovar**: ela pode conter nome de pessoa |
| **M-05** | teto do ator compõe com o teto de evidência (ADR-0033) | **aprovar**: permissão não desbloqueia evidência ausente |
| **M-06** | corrigir G-01 e G-02 na F7 antes de implementar `breakdown_kpi` | **precisa de você**: é mexer na F7, que você pediu para não alterar — mas `breakdown_kpi` sem isso vaza recorte de 1 pessoa |
| **M-07** | limites: 24 períodos, 2 dimensões, 50 linhas, 30 s | **aprovar** como ponto de partida, revisável com uso |
| **M-08** | `get_lineage` não percorre o degrau de fonte | **aprovar**: percorrer é leitura de RAW |
| **M-09** | RAG fica num caminho separado, com MCP próprio | **aprovar**: número e citação têm regimes de evidência diferentes |
| **M-10** | `actor.id` é referência opaca, nunca e-mail ou `employee_id` | **aprovar** |

---

## Parte XV — ADRs propostos

Três, e só o que é decisão arquitetural nova.

| ADR | Assunto | Por que é novo |
|---|---|---|
| **0031** | o MCP expõe capacidades, não uma conexão | o ADR-0028 governa o que a IA **emite**; este governa o que **existe para ser chamado**. São fronteiras diferentes: uma sobre a forma da saída, outra sobre o tamanho da superfície |
| **0032** | recusa é resultado da tool, não erro de protocolo | nenhum ADR anterior trata do transporte da recusa; a F7 definiu a recusa, não como ela atravessa uma fronteira de protocolo com `isError` |
| **0033** | o teto do ator compõe com o teto de evidência | o ADR-0029 compõe **duas** dimensões, dado e governança; a autorização é uma terceira, e a regra de composição precisa ser declarada antes de existir autenticação |

O que **não** vira ADR, por já estar decidido: consulta semântica como saída da
IA (ADR-0028), certificação limitando nível (ADR-0029), ciclo de vida e
versionamento (ADR-0030), bandas de trust (ADR-0023), n mínimo (ADR-0007),
membros reservados (ADR-0025), papel do RAG (ADR-0016), DuckDB (ADR-0009).

---

**Nada implementado.** Sem código, sem servidor MCP, sem agente, sem harness,
sem RAG, sem embeddings, sem interface, sem commit. F0–F7 intocados.
