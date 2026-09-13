# ADR-0028: A saída da IA é consulta semântica, nunca SQL nem número

- **Status:** **Proposta** (F7, aguardando aprovação)
- **Data:** 2026-09-12
- **Origem:** F7, princípio central declarado pela Sam; decisão D7-02
- **Fase:** vigora da F7 em diante, e condiciona a F8 (MCP) e o agente

## Contexto

O princípio que abre a F7 é uma divisão de trabalho:

> People Analytics define e governa os KPIs. A camada analítica calcula. A
> Semantic Layer certifica e descreve. O MCP expõe capacidades controladas. A IA
> interpreta. A IA **não** deve calcular KPIs diretamente sobre RAW ou tabelas
> intermediárias.

O princípio é claro e, sozinho, não é executável. "Não calcular sobre RAW" é uma
proibição de destino, e o que decide o comportamento é a **forma da saída** do
modelo. Três formas são possíveis, e elas não são equivalentes:

| Forma da saída | O que acontece na prática |
|---|---|
| a IA devolve um número | não há como saber de onde veio; a proibição é inverificável |
| a IA devolve SQL | tecnicamente auditável, e na prática a proibição vaza: qualquer `FROM` alcança qualquer tabela, o filtro fixo pode ser omitido, o `is_system_of_record` esquecido duplica 2019, e o `JOIN` errado atravessa a camada de verdade |
| a IA devolve uma consulta semântica | o alcance é o vocabulário; o que não está declarado não é expressável |

O caso concreto que decide: `headcount` só fecha com
`is_system_of_record = true`, por causa da sobreposição HRIS_LEGACY × HRIS_CORE
entre 2016 e 2019 (ADR-0026). Um SQL escrito por modelo, ainda que correto em
nove de dez tentativas, erra esse filtro na décima e devolve um número inflado
com cara de fato. O filtro é **do KPI**, e não do consumidor.

Há também o precedente do projeto: a F6 gastou um teste (F-13, com verificação
por AST) para garantir que nenhum literal de código aponta para a camada de
verdade. Dar ao modelo a capacidade de escrever `FROM` livre desfaz esse teste
em tempo de execução.

O ADR-0016 trata do papel do RAG, que é outra coisa: lá se decide o que a IA
**lê**; aqui se decide o que a IA **emite**.

## Decisão

### 1. A fronteira

A IA emite um **objeto de consulta semântica**. Não emite SQL, não emite nome de
tabela, não emite número calculado por ela.

```yaml
kpi: headcount
period: {type: month, value: 2026-06}
dimensions: {pais: BR}
compare_to: null
requested_level: FACT
```

O objeto referencia apenas `kpi_id`, dimensões de negócio e valores do
vocabulário. Nenhum campo dele admite nome físico, expressão, coluna, junção ou
fragmento de SQL — não por convenção, mas porque o schema do objeto não tem onde
colocá-los.

### 2. O executor é determinístico

A tradução de consulta semântica para SQL é código, não modelo. Dada a mesma
consulta e o mesmo estado do dado, o SQL gerado é sempre o mesmo, e os filtros
fixos do contrato do KPI são aplicados pelo executor, jamais pelo chamador.

### 3. Sete validações antes de executar

A consulta é recusada, e não corrigida silenciosamente, quando: o `kpi_id` não
existe; o status do KPI não permite a consulta; uma dimensão não está em
`allowed_dimensions`; um valor não está no vocabulário; o período está fora de
`period_coverage`; o nível pedido excede o que a evidência sustenta; a população
resultante fica abaixo de `minimum_n`.

Recusa é resposta. "Aproximar" a consulta para que ela passe é proibido, pela
mesma razão que a F4 proíbe mapear por similaridade: o custo do erro é
assimétrico e invisível.

### 4. Nenhum caminho alternativo de leitura

O consumidor — MCP, agente ou pessoa — alcança apenas o schema `semantic`, que
expõe views com os filtros fixos já aplicados. RAW, camada de verdade, L1, L2 e
as tabelas cruas da L3 não são endereçáveis por essa via. Quem consultar o
DuckDB diretamente por esse schema também não consegue errar o filtro.

### 5. O número nunca vem do modelo

Todo valor numérico em uma resposta vem de execução no DuckDB, com `trace_id`.
Um número que a IA produziria "de memória", estimaria ou interpolaria é
exatamente o que a F5 chama de score artificial, e está proibido pelo mesmo
motivo.

## Alternativas consideradas

1. **SQL gerado pela IA com validação por allowlist de tabelas e colunas.**
   Auditável e insuficiente: a allowlist aceita `FROM fact_headcount_snapshot`
   sem o `is_system_of_record`, que é justamente o erro que importa. Validar
   semântica de SQL arbitrário é mais difícil que gerar o SQL.
2. **SQL gerado pela IA sobre views já filtradas.** Melhor, e ainda permite
   junções e agregações que a view não previu, além de vazar nomes físicos para
   o consumidor — o oposto do objetivo da Semantic Layer.
3. **A IA devolve o número e cita a fonte.** A citação não é verificável, e o
   número passa a depender da aritmética do modelo.
4. **Linguagem de consulta intermediária própria, mais expressiva que o objeto.**
   Toda expressividade a mais é uma regra de negócio que alguém escreve na
   consulta em vez de no contrato do KPI. Foi o que o caso `movement_type`
   mostrou: escolher o vocabulário na hora da consulta é inventar definição.

## Consequências

**Positivas**

- A proibição de calcular sobre RAW passa a ser estrutural, e não uma instrução
  em prompt que o modelo pode desobedecer.
- A consulta semântica é logável, difável e reproduzível: a mesma consulta, seis
  meses depois, é auditável sem reconstruir o raciocínio do modelo.
- O consumidor não precisa saber que houve migração de HRIS, que existem membros
  reservados negativos ou que a camada de verdade existe.
- Erro de modelo vira recusa de validação, e não número errado.

**Negativas**

- Toda pergunta nova que o vocabulário não cobre é uma recusa, até alguém
  estender o contrato. A camada é deliberadamente menos capaz do que um gerador
  de SQL livre.
- Manter `allowed_dimensions`, `filters` e vocabulário atualizados é trabalho
  contínuo de governança, e o custo de esquecer aparece como recusa ao usuário.
- Há um executor a mais para escrever e testar, e ele é código crítico: um bug
  nele erra em todas as respostas de uma vez.

**Riscos e mitigação**

- *Risco:* a pressão prática ("só desta vez, deixa consultar direto") abrir uma
  rota paralela ao schema `semantic`. *Mitigação:* casos de falha FC-01 e FC-12,
  e o mesmo padrão de teste da F6 — a ausência de rota alternativa é verificada,
  e não confiada.
- *Risco:* o objeto de consulta crescer campo a campo até virar SQL com outro
  nome. *Mitigação:* qualquer campo novo no objeto exige justificativa no
  contrato do KPI correspondente, nunca no schema do objeto isolado.

## Referências

- `docs/F7_semantic_layer.md`, Partes III e VIII
- ADR-0015 (níveis de resposta), ADR-0016 (papel do RAG), ADR-0024 (separação
  entre camada de verdade e analítica), ADR-0026 (sistema observador no grain)
- Teste F-13 da F6, `tests/analytical/test_model.py`
