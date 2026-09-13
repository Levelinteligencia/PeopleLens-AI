# Requisitos de produto futuros

Requisitos **registrados e ainda não implementados**. Nada aqui está em vigor,
nada aqui autoriza mudança de arquitetura, e nenhum item entra em execução sem
aprovação e fase própria.

O documento existe porque requisito lembrado em conversa não é requisito: ou ele
está escrito e rastreável, ou ele reaparece como retrabalho no meio de uma fase.

| # | Requisito | Origem | Situação |
|---|---|---|---|
| RF-01 | Interface bilíngue **PT-BR / EN-US** | Sam, 2026-09-13 | registrado, **não implementado** |

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
