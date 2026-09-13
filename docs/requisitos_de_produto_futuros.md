# Requisitos de produto futuros

Requisitos **registrados e ainda não implementados**. Nada aqui está em vigor,
nada aqui autoriza mudança de arquitetura, e nenhum item entra em execução sem
aprovação e fase própria.

O documento existe porque requisito lembrado em conversa não é requisito: ou ele
está escrito e rastreável, ou ele reaparece como retrabalho no meio de uma fase.

| # | Requisito | Origem | Situação |
|---|---|---|---|
| RF-01 | Interface bilíngue **PT-BR / EN-US** | Sam, 2026-09-13 | registrado, **não implementado** |
| RF-02 | Comparação entre **dois períodos arbitrários** | P-03, caso C | registrado, **não implementado** |

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

**O que este registro NÃO autoriza:**

- não acrescenta valor a `COMPARACOES` nem ao bloco `comparisons` do
  vocabulário governado;
- não altera o contrato do `Intent` nem a `schema_version`;
- não altera a MCP SPEC nem a capacidade `compare_kpi`;
- não muda o prompt, o interpretador ou o avaliador para fazer o caso C passar.

**Quatro decisões que a fase precisará tomar**, e nenhuma delas é acrescentar um
enum:

1. **vocabulário**: a forma nova entra declarada, com responsável e data, como
   qualquer outro termo governado;
2. **contrato**: o `Intent` precisaria carregar dois períodos, o que é mudança de
   contrato e exige `schema_version` nova;
3. **MCP**: `compare_kpi` precisaria aceitar a base nova, e isso é mudança da MCP
   SPEC, não do agente;
4. **Semantic Layer**: precisa decidir se a comparação entre dois períodos
   arbitrários é respondível em CONTEXT e sob qual trust. Dois períodos com
   coberturas diferentes não são automaticamente comparáveis.

**O que já funciona sem isto.** A pergunta do usuário não fica sem resposta: a
decisão A-05 permite dois `get_kpi` lado a lado como apresentação factual
independente, sem nenhuma aritmética entre eles. A lacuna é de expressividade do
`Intent`, não de capacidade de responder.

**Fase.** A definir. É backlog arquitetural, não correção pendente, e não
bloqueia P-03.
