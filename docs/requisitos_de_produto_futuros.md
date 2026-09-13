# Requisitos de produto futuros

Requisitos **registrados e ainda não implementados**. Nada aqui está em vigor,
nada aqui autoriza mudança de arquitetura, e nenhum item entra em execução sem
aprovação e fase própria.

O documento existe porque requisito lembrado em conversa não é requisito: ou ele
está escrito e rastreável, ou ele reaparece como retrabalho no meio de uma fase.

| # | Requisito | Origem | Situação |
|---|---|---|---|
| RF-01 | Interface bilíngue **PT-BR / EN-US** | Sam, 2026-09-13 | registrado, **não implementado** |
| RF-02 | Comparação entre **dois períodos arbitrários** | P-03, caso C | **IMPLEMENTADO** em 2026-09-13, decisão B |

---

## RF-01 · Interface bilíngue PT-BR / EN-US

**O que é.** O PeopleLens deve, no futuro, poder ser operado e responder em
**português do Brasil** e em **inglês dos Estados Unidos**.

**O que este registro NÃO autoriza**, e a lista é a parte importante:

- não cria camada de tradução;
- não altera o modelo semântico, o vocabulário governado, o catálogo de KPIs,
  nem qualquer contrato das fases F0–F7;
- não altera o MCP, o Agent Harness, o Agent Loop nem a SPEC do LLM Interpreter;
- não introduz nova arquitetura, novo componente, nova dependência ou nova
  capacidade;
- não muda o idioma de nada que já existe.

**O que já é sabido, e precisa ser decidido quando a fase existir.** Registrado
agora porque é o tipo de coisa que fica cara depois:

1. **Idioma da pergunta e idioma do vocabulário são coisas distintas.** O
   `vocabulary.yaml` declara `language: pt-BR`, e o ADR-0020 proíbe que uma
   sugestão de mapeamento atravesse a fronteira de língua. Traduzir termo de
   negócio por semelhança é exatamente o que aquele ADR impede — portanto um
   termo em inglês só resolve se **estiver declarado** como sinônimo governado,
   com responsável e data, como qualquer outro sinônimo.
2. **Idioma da resposta não pode alterar o nível da resposta.** FACT, CONTEXT e
   CAUSALITY, os tetos de confiança e as recusas governadas são invariantes de
   idioma. Uma recusa em inglês recusa a mesma coisa, pelo mesmo motivo.
3. **Texto de recusa e de ambiguidade é parte do produto**, não de log. O
   registro (`agent_run_log`, `mcp_call_log`, `semantic_query_log`) permanece em
   uma forma só, para que a auditoria não dependa do idioma de quem perguntou.
4. **Nome de membro de dimensão não é texto traduzível.** "Customer Service" é
   o membro; "Atendimento ao Cliente" só existe se for sinônimo declarado.

**Fase.** A definir. Não é F8, F9 nem F10 por decisão — é um requisito sem fase
atribuída até que Sam atribua uma.

---

## RF-02 · Comparação entre dois períodos arbitrários

**O que é.** Hoje `compare_to` aceita três bases, e as três são **relativas**:
`periodo_anterior`, `mesmo_periodo_ano_anterior` e `media_da_populacao`. Elas
comparam o período pedido contra algo derivado dele. Uma pergunta que cite dois
períodos lado a lado — "compare o turnover de 2024 e 2025" — não é
representável por nenhuma das três.

**Como apareceu.** Na avaliação empírica de P-03, caso C. O LLM identificou a
comparação corretamente e deixou `compare_to` vazio, que é o comportamento
certo: escolher `periodo_anterior` por semelhança apontaria para 2023 e
produziria uma comparação silenciosamente errada. Ver
`docs/llm_interpreter_p03_report.md`, seções 6 a 8.

**O defeito que a validação E2E expôs.** Pior do que a lacuna: o par errado
chegava a ser respondido. `plan.py` tinha
`compare_to=intent.compare_to or "periodo_anterior"`, e o default convertia a
lacuna em base relativa. Para "entre 2024 e 2025", o `period` ficava em 2024 e a
Semantic Layer derivava **2023**. A resposta saía plausível e comparava o par
que ninguém pediu.

## Decisão B, e por que não a A

Duas formas chegavam ao mesmo resultado funcional:

| | O que faria | Custo |
|---|---|---|
| **A** | o `PLAN` leria o intervalo `from: 2024, to: 2025` como um par | barato, e **reintroduz inferência no PLAN** |
| **B** | o `Intent` declara os dois períodos em campos separados | contrato novo, `schema_version` nova |

**Escolhida a B, por Sam, em 2026-09-13.** O motivo é um princípio, não
preferência: a A faria o `PLAN` reinterpretar a pergunta. Um intervalo
`2024..2025` significa agregação numa pergunta de valor, e significaria par numa
de comparação. É a mesma classe de "o mais parecido serve" que custou o caso C e
o `Customer Service` inferindo `business_unit`. O par declarado não se infere: ou
a pergunta nomeou os dois períodos, ou não nomeou.

## Como ficou

`compare_to` continua sendo **qual é a base**; `compare_period` carrega **o
valor** quando a base é declarada.

```jsonc
{ "schema_version": "intent/1.1",
  "question_type":  "COMPARACAO",
  "period":         {"grain": "ano", "from": "2025", "to": "2025"},
  "compare_to":     "periodo_declarado",
  "compare_period": {"grain": "ano", "from": "2024", "to": "2024"} }
```

As quatro camadas, e em nenhuma delas houve lógica de comparação nova:

1. **vocabulário**: `periodo_declarado` declarado em `comparisons`, com
   `requires: compare_period`;
2. **contrato**: `Intent.compare_period`, e `schema_version` de `intent/1.0` para
   `intent/1.1`. A versão anterior é **rejeitada**, nunca adaptada;
3. **MCP**: `compare_kpi` aceita `compare_period`, e recusa
   `COMPARACAO_NAO_RESPONDIVEL` quando a base é declarada e o período não veio;
4. **Semantic Layer**: `SemanticQuery.compare_period`, e `_periodo_anterior`
   ganhou um ramo que **usa** o período em vez de derivá-lo. O delta continua
   sendo calculado lá dentro, e o agente segue sem fazer aritmética.

**O default silencioso morreu.** Numa `COMPARACAO` sem base, o `RESOLVE`
devolve ambiguidade com as quatro bases governadas como opções. A única base
escolhida pelo plano é a da pergunta **causal**, e ela é declarada no `motivo`
do passo, porque ali quem pediu a comparação foi o agente, não a pessoa.

**Compatibilidade preservada.** `periodo_anterior`,
`mesmo_periodo_ano_anterior` e `media_da_populacao` derivam o período como
sempre, e com `compare_period` nulo. Trust, privacidade, linhagem, permissões,
ranking e Smart Refusal intocados.
