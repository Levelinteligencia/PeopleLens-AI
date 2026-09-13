# LLM Interpreter v0.1 — P-03, relatório da avaliação empírica

**Status: P-03 APROVADO COM LACUNA CONHECIDA.** O LLM real foi usado, sem
fallback, em 17 casos de avaliação: 16 passaram e 1 falhou por uma lacuna do
**contrato semântico**, não do modelo. Nenhuma camada funcional foi alterada
para produzir este resultado.

A SPEC está em `docs/LLM_INTERPRETER_SPEC_v0.1.md`. Os casos de avaliação estão
em `src/agent/llm_eval.py` e **não foram alterados** para acomodar o resultado.

---

## 1. Objetivo

P-03 era a última pendência aberta da SPEC do LLM Interpreter: **qual modelo, e
por qual provedor.** A decisão foi mantida em aberto deliberadamente desde
2026-09-13, porque depende de ambiente e API disponíveis, e porque este projeto
recusa escolher fornecedor por preferência.

A pergunta que esta avaliação precisava responder não é "o modelo funciona", e
sim: **ele produz o `Intent` semanticamente correto?** JSON válido não é
aprovação. O critério declarado era comparar contra os casos esperados, usando o
`RuleInterpreter` como **linha de base, não como autoridade** sobre o resultado
certo.

## 2. Configuração real

| Item | Valor |
|---|---|
| provedor | `openai` |
| modelo | `gpt-5.6-luna` |
| LLM real utilizado | **sim** |
| `interpreter_used` | `LLM` |
| `interpreter_version` | `llm/0.1.0` |
| `schema_version` | `intent/1.0` |
| structured output | `json_schema`, `strict: true` |
| `temperature` | **não enviado** (o modelo só aceita o default) |
| orçamento consumido | **24 de 50** chamadas no período |

Duas correções precederam a execução, e as duas estão registradas em commits
próprios:

| Commit | O que destravou |
|---|---|
| `995b105` | nome do structured output: `intent/1.0` gerava `intent_1.0`, e o ponto viola `^[a-zA-Z0-9_-]+$` |
| `355b371` | modo estrito: sete propriedades com `enum`/`const` sem `type`, dois objetos com `required` incompleto, e `temperature=0` recusada pelo modelo |

## 3. Resultado quantitativo

**16 de 17 casos passaram.**

| | Resultado |
|---|---|
| casos executados | 17 (A–M em PT-BR, mais os quatro equivalentes em EN-US) |
| passaram | **16** |
| falharam | **1** (caso C) |

Para comparação, a linha de base do `RuleInterpreter` nos mesmos 17 casos,
medida antes desta execução, foi **13 passaram, 4 falharam** (`G`, `D-EN`,
`E-EN`, `F-EN`).

## 4. Equivalência PT-BR × EN-US

**4 de 4 pares equivalentes.**

É o ganho mais claro sobre a regra. O `RuleInterpreter` divergia em 3 dos 4
pares, porque os padrões de tipo de pergunta são expressões regulares em
português: "Which department had the highest turnover" virava `VALOR` em vez de
`RANKING`, e "Why did turnover decrease" virava `VALOR` em vez de `CAUSAL`.

O idioma não alterou KPI, período, dimensão, governança nem valor canônico. O
requisito de interface bilíngue (RF-01) permanece o que sempre foi: preocupação
futura de apresentação, e não autorização para o LLM criar ou traduzir membro de
dimensão.

## 5. Evidência de que o LLM real foi usado, sem fallback

O registro do interpretador, gravado em `agent_run_log.interpretacao`:

```
interpreter_used     LLM
interpreter_version  llm/0.1.0
provider             openai
model                gpt-5.6-luna
fallback             false
fallback_reason      null
retries              0
validation           OK
schema_erros         []
tokens_entrada       5833
tokens_saida         286
latencia_ms          3493
```

Cada linha fecha uma porta de dúvida, e vale dizer qual:

- `interpreter_used = LLM` e `fallback = false`: o `RuleInterpreter` **não**
  respondeu. Se tivesse respondido, apareceria `RULE_FALLBACK`, porque o
  fallback neste projeto é declarado e nunca silencioso (D-05);
- `retries = 0`: a primeira chamada já veio bem formada. Não houve tentativa
  repetida, e portanto não houve resposta "escolhida" entre várias;
- `validation = OK` com `schema_erros = []`: a saída passou pela validação
  **local**, que roda sempre, mesmo com structured output do provedor
  (ADR-0035, decisão 2);
- `tokens_entrada`, `tokens_saida` e `latencia_ms` são não nulos: houve resposta
  do provedor. Quando a chamada falha antes de retornar, os três ficam em
  `null`/`0`, que foi exatamente o sintoma das falhas anteriores.

Os valores de token e latência são os da interpretação registrada, por chamada,
e não um total do benchmark.

## 6. O caso C

```
pergunta:   "Compare o turnover de 2024 e 2025."

esperado:   question_type = COMPARACAO
            kpi           = turnover_rate
            compare_to    preenchido

obtido:     question_type = COMPARACAO      ✅
            kpi           = turnover_rate   ✅
            compare_to    = null            ❌ pelo avaliador
```

O modelo **reconheceu a comparação**. O que ele não fez foi preencher
`compare_to`.

## 7. Análise: a lacuna é do contrato, não do modelo

O contrato de `compare_to` tem exatamente três valores, e eles vêm do
vocabulário governado (`config/semantic/vocabulary.yaml`, bloco `comparisons`):

```python
COMPARACOES = (
    "periodo_anterior",
    "mesmo_periodo_ano_anterior",
    "media_da_populacao",
)
```

Os três são **bases relativas**: comparam o período pedido contra algo derivado
dele. Nenhum deles representa **dois períodos arbitrários citados lado a lado**.
"2024 versus 2025" não é "o período anterior" nem "o mesmo período do ano
anterior" nem "a média da população": é uma quarta coisa, e ela não existe no
vocabulário.

Diante disso, o LLM tinha duas saídas. Podia escolher `periodo_anterior`, que é
o mais parecido e estaria **errado**: 2024 não é o período anterior a 2024, e
com `from = 2024` a comparação apontaria para 2023. Ou podia deixar o campo
vazio, sinalizando que a pergunta não é representável pelas bases declaradas.

**Ele deixou vazio, e esse é o comportamento correto.** É literalmente a regra
que o projeto sustenta desde o ADR-0020: um termo mapeado errado por
similaridade é invisível; um termo não mapeado é visível. Preencher
`compare_to` por aproximação teria feito o caso C passar no avaliador e
produzido, em produção, uma comparação silenciosamente errada.

A falha, portanto, é do **caso de avaliação**, que esperava um preenchimento que
o contrato não sustenta, e da **lacuna do contrato**, que não modela comparação
entre períodos arbitrários. Não é falha do modelo.

Vale registrar que o caminho para responder a pergunta do usuário já existe, e
não depende de `compare_to`: quando `compare_kpi` recusa, a decisão A-05 permite
dois `get_kpi` lado a lado, como **apresentação factual independente**, sem
nenhuma aritmética entre eles. A lacuna é de expressividade do `Intent`, não de
capacidade de responder.

## 8. Decisão: o contrato não muda nesta fase

**Nada foi alterado para fazer C passar.** Nem o `compare_to`, nem o vocabulário
governado, nem o caso de avaliação, nem o limiar do benchmark.

As três coisas que foram explicitamente recusadas:

1. **acrescentar um quarto valor a `COMPARACOES`** para representar a comparação
   arbitrária. Seria mudança do vocabulário governado, que exige decisão
   registrada, responsável e data, e não cabe num ajuste para fazer um teste
   passar;
2. **relaxar o caso C** no avaliador, removendo a verificação de `compare_to`.
   Seria apagar a evidência da lacuna;
3. **instruir o modelo a escolher a base mais próxima**. Seria pedir
   exatamente a inferência por similaridade que o ADR-0020 proíbe.

Mudar o limiar para o resultado ficar bonito é a versão de teste do que a F5
chamou de mexer no threshold para o check passar. Não se faz.

## 9. Conclusão

**P-03 APROVADO COM LACUNA CONHECIDA.**

`gpt-5.6-luna`, da OpenAI, fica como o modelo do LLM Interpreter v0.1. A
aprovação se sustenta em quatro observações, e não em impressão:

- **16 de 17** contra os casos esperados, e a linha de base determinística fez
  13 de 17 nos mesmos casos;
- **4 de 4** em equivalência PT-BR × EN-US, onde a regra fazia 1 de 4;
- **sem fallback, sem retry, schema válido na primeira tentativa** — o contrato
  do `Intent` foi respeitado sem precisar de segunda chance;
- **o único caso que falhou, falhou pelo motivo certo**: o modelo recusou-se a
  inventar uma base de comparação que o vocabulário governado não declara.

O último ponto é o que mais importa nesta fase. Um modelo que acertasse 17 de 17
preenchendo `compare_to` por semelhança seria **pior**, não melhor: passaria no
benchmark e erraria em produção, de forma invisível. A aprovação vale porque o
modelo errou o teste do jeito certo.

## 10. Backlog arquitetural, e não correção imediata

**Comparação arbitrária entre períodos é backlog**, registrado em
`docs/requisitos_de_produto_futuros.md` como **RF-02**. Não faz parte de P-03,
não é correção pendente, e não bloqueia nada.

Quando for a hora, é decisão de arquitetura com pelo menos quatro pontas, e
nenhuma delas é "acrescentar um enum":

1. **o vocabulário governado** precisa declarar a forma nova, com responsável e
   data, como qualquer outro termo;
2. **o `Intent`** precisaria de um campo capaz de carregar dois períodos, e isso
   é mudança de contrato, com `schema_version` nova;
3. **o MCP** precisaria que `compare_kpi` aceitasse a base nova, e isso é
   mudança da MCP SPEC, não do agente;
4. **a Semantic Layer** precisaria decidir se a comparação entre dois períodos
   arbitrários é respondível em CONTEXT, e sob qual trust — uma comparação entre
   períodos de coberturas diferentes não é automaticamente legítima.

Outros itens que seguem abertos, e que **não** são consequência desta avaliação:

- a execução mediu 17 casos. Ampliar o conjunto é trabalho de avaliação, não de
  correção;
- `orcamento_llm_por_periodo` continua sem valor de produção (P-05). A execução
  consumiu 24 chamadas, o que é a primeira medição real disponível para
  calibrá-lo;
- os ADRs 0024 a 0035 seguem com status **Proposta**.

---

## Referências

- `docs/LLM_INTERPRETER_SPEC_v0.1.md` — SPEC, Partes XV e XVII
- `docs/requisitos_de_produto_futuros.md` — RF-02
- `src/agent/llm_eval.py` — os 17 casos, inalterados
- ADR-0020 (sugestão não atravessa fronteira de língua), ADR-0035 (a saída do
  LLM é entrada não confiável)
- Decisão A-05 (dois valores independentes quando a comparação é recusada)
