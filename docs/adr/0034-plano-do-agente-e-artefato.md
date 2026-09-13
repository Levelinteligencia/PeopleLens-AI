# ADR-0034: O plano do agente é um artefato, não um raciocínio

- **Status:** **Proposta** (Agent Harness v0.1, aguardando aprovação)
- **Data:** 2026-09-12
- **Origem:** SPEC do Agent Harness, Parte XXI; substância aprovada na
  autorização de implementação, Parte 6
- **Fase:** vigora do Agent Harness v0.1 em diante

## Contexto

Três ADRs já delimitam o agente, e nenhum deles cobre o que este cobre.

| ADR | Governa |
|---|---|
| **0028** | o que a IA **emite** para a Semantic Layer: consulta semântica, nunca SQL nem número |
| **0031** | o que **existe para ser chamado**: seis capacidades, nenhuma genérica, nenhuma de escrita |
| **0033** | até **onde** a resposta pode ir: o teto composto de evidência, governança e ator |

Falta a pergunta do meio: **por que esta capacidade foi escolhida, e não outra?**

Essa pergunta não é acadêmica. A SPEC do Harness mapeia, para cada proibição do
agente, a camada que a torna impossível — e a tabela tem exatamente **uma** linha
em que a camada é "Agent Policy", sem estrutura por baixo:

> escolher outro KPI parecido em silêncio → **nada impede hoje**

É a proibição mais provável de ser violada por um modelo prestativo, e é a única
que depende de comportamento. Tudo o mais falha contra estrutura: SQL não tem
campo, RAW não tem nome que resolva, escrita não tem ferramenta.

O problema com deixá-la só na política é que **política sem artefato não é
testável**. Se a escolha da capacidade vive no raciocínio do modelo, três
critérios de aceite da SPEC não têm como ser verificados:

| Critério | Por que fica inverificável |
|---|---|
| **AA-09** — a seleção de ferramenta é governada | não há objeto para comparar com a matriz da SPEC |
| **AA-11** — a execução é reproduzível | reproduzir prosa de modelo não é reproduzir decisão |
| **P-03** — KPI escolhido pelo id do catálogo, nunca por similaridade | não há registro do que foi considerado |

E há o problema de auditoria, que aparece depois: seis meses adiante, "por que o
agente respondeu com `headcount` quando perguntaram sobre saída de pessoas?" não
tem resposta se a decisão nunca virou objeto. O `mcp_call_log` guarda **que** a
chamada aconteceu; o `semantic_query_log` guarda **o que** foi perguntado.
Nenhum dos dois guarda **por quê**.

Vale notar o paralelo, porque este projeto já resolveu o mesmo problema duas
vezes na mesma forma. O ADR-0028 não pediu ao modelo que não escrevesse SQL:
mudou a **forma da saída**, e o SQL deixou de ser expressável. O ADR-0031 não
negou escrita por permissão: removeu a ferramenta. Aqui a mesma jogada, um andar
acima — não se pede ao agente que escolha bem a capacidade; exige-se que a
escolha exista como objeto antes de valer, e aí ela pode ser conferida.

## Decisão

### 1. O plano existe antes da primeira chamada

Nenhuma capacidade do MCP é invocada antes de o plano estar montado e no estado
da execução. Um plano produzido depois da chamada é justificativa, não decisão, e
justificativa posterior é exatamente o que se quer evitar.

### 2. O plano é um objeto estruturado, com quatro campos por passo

```yaml
plan:
  justificativa: "a comparação vem da capacidade que a calcula"
  steps:
    - passo: 1
      capacidade: compare_kpi
      motivo: "comparação é capacidade própria; subtrair dois get_kpi
               seria o agente calculando"
      objetivo: "obter a variação governada de turnover_rate"
      origem: MATRIZ
```

`passo`, `capacidade`, `motivo` e `objetivo` são obrigatórios. `origem` declara
de onde a escolha veio: `MATRIZ` (a tabela da SPEC), `FALLBACK_A05` (dois valores
independentes quando a comparação foi recusada) ou `SEGUIMENTO` (pergunta de
acompanhamento sobre uma resposta anterior).

### 3. O que o plano **não** contém

Cadeia de pensamento não entra. O que fica registrado é **justificativa
operacional estruturada**: qual capacidade, por que ela e não outra, o que se
espera obter. Guardar o raciocínio interno seria registrar texto livre de modelo,
que não é auditável, cresce sem limite e pode conter conteúdo que o log não
deveria carregar.

Valores de filtro também não entram, pela mesma regra do `mcp_call_log`: registra-se
que houve filtro por `pais`, nunca quais países.

### 4. A seleção de capacidade vem da matriz

A matriz da SPEC (tipo de pergunta → capacidade) é a fonte da escolha, e não uma
sugestão ao modelo. Consequência direta e deliberada: **o modelo não escolhe
ferramenta**. A latitude dele fica em `UNDERSTAND` — transformar linguagem em
intenção — e o plano é derivado da intenção resolvida.

Isso é mais estrito do que a SPEC exigia. É o lugar certo da restrição: a matriz
é declarada, auditável em diff, e discutível como decisão; a preferência de um
modelo não é nenhuma das três coisas.

### 5. O plano é comparável, e é isso que o torna testável

Como é objeto, o plano pode ser comparado com a matriz (AA-09) e com o plano de
outra execução da mesma pergunta (AA-11). A reprodutibilidade que se exige de um
agente com LLM **não é determinismo de texto**: é o plano e a sequência de
chamadas que precisam reproduzir. A prosa pode variar; a decisão, não.

### 6. O plano é registrado

`agent_run_log.plan` guarda o plano serializado, ao lado da intenção, das
decisões e do `stop_reason`. Junto com os `trace_id`, fecha a cadeia:

```
agent_run_log.plan       por que a capacidade foi escolhida
agent_run_log.trace_ids  ──> mcp_call_log     quem chamou
                         ──> semantic_query_log  o que foi perguntado
                         ──> l3_run_id           qual carga
```

## Alternativas consideradas

1. **Deixar a escolha no raciocínio do modelo, com a matriz no prompt.** É o
   desenho mais comum e o que este projeto recusa desde a F6: a garantia passa a
   depender de obediência, e não há como testar. A matriz no prompt continua
   sendo boa ideia — ela só não pode ser a única coisa.
2. **Registrar a cadeia de pensamento completa como trilha de auditoria.** Dá a
   sensação de transparência e entrega pouco: texto livre não é comparável com a
   matriz, cresce sem limite, e é o lugar mais provável de vazar conteúdo
   sensível para o log. Justificativa estruturada responde a mesma pergunta e é
   verificável.
3. **Derivar o plano depois das chamadas, para o registro.** Seria justificativa
   retroativa. O valor do plano está em existir **antes**, porque é isso que o
   torna uma decisão em vez de uma explicação.
4. **Deixar o modelo escolher a capacidade e validar a escolha contra a matriz.**
   Melhor que nada, e ainda assim entrega ao modelo uma decisão que já está
   decidida. Se a matriz é a resposta certa, aplicá-la é o comportamento, e não
   um resultado a validar depois.
5. **Não ter matriz, e deixar a seleção emergir da descrição das ferramentas.**
   É como um agente genérico funciona. Aqui produziria o erro central: pedir
   `turnover` e receber `headcount` porque as descrições se parecem.

## Consequências

**Positivas**

- A única proibição que dependia de comportamento passa a ter verificação: o
  plano é comparado com a matriz, e a comparação é automática.
- "Por que o agente chamou isso?" tem resposta seis meses depois, sem
  reconstruir o raciocínio de um modelo que talvez nem exista mais na mesma
  versão.
- A reprodutibilidade vira afirmação testável: mesma pergunta, mesmo plano,
  mesma sequência de chamadas.
- Uma capacidade nova exige entrar na matriz, que é uma decisão visível em diff —
  e não uma preferência que aparece em produção.

**Negativas**

- O agente fica menos flexível do que um agente genérico. Uma pergunta cujo
  padrão a matriz não previu vira ambiguidade ou recusa, mesmo que uma combinação
  de capacidades a respondesse. É o preço, e é consciente.
- A matriz precisa ser mantida. Um tipo de pergunta novo é trabalho de governança,
  não de prompt.
- Há um objeto a mais no registro, e ele precisa ser podado de valores de filtro
  toda vez — uma inclusão distraída de `filters` no plano levaria termo filtrado
  para o log.

**Riscos e mitigação**

- *Risco:* o plano virar formalidade, preenchido com motivos genéricos ("porque
  sim"). *Mitigação:* `motivo` e `objetivo` são obrigatórios e conferidos por
  teste; o valor real vem da revisão humana amostral, que é o quinto eixo de
  avaliação da SPEC.
- *Risco:* alguém acrescentar um passo fora da matriz "só neste caso".
  *Mitigação:* `origem` declara a procedência de cada passo, e as três origens
  válidas são fechadas.
- *Risco:* o plano crescer até virar registro de raciocínio. *Mitigação:* a
  decisão 3, e o fato de que campos novos no plano exigem passar por aqui.

## Referências

- `docs/AGENT_HARNESS_SPEC_v0.1.md`, Partes VI, VII, XIII e XVII
- ADR-0028 (a saída da IA é consulta semântica), ADR-0031 (o MCP expõe
  capacidades), ADR-0032 (recusa é resultado), ADR-0033 (teto do ator)
- Critérios AA-09, AA-11 e Política P-03 da SPEC do Harness
