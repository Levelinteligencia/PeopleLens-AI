# MCP v0.1 — Relatório de implementação

**Status: implementado, 237 testes passando, sem commit.** Sem agente, sem
harness, sem RAG, sem embeddings, sem LLM, sem interface. F0–F7 intocados.

A SPEC aprovada está em `docs/MCP_SPEC_v0.1.md` e **não foi alterada**.

---

## 1. Arquivos criados

| Arquivo | O que faz |
|---|---|
| `src/mcp/__init__.py` | o princípio da camada, em uma página |
| `src/mcp/envelope.py` | os quatro resultados e a regra do envelope (ADR-0032) |
| `src/mcp/actor.py` | escopos, contrato do ator e composição do teto (ADR-0033) |
| `src/mcp/limits.py` | limites da fronteira e contagem de períodos |
| `src/mcp/tools.py` | as seis capacidades |
| `src/mcp/observability.py` | `mcp_call_log`, ligado ao `semantic_query_log` pelo `trace_id` |
| `src/mcp/server.py` | registro de capacidades, autorização, validação de forma, dispatch |
| `tests/mcp/test_mcp.py` | 35 testes de contrato |

## 2. Arquivos alterados

**Nenhum.** Verificado por varredura de modificação: só os oito arquivos acima
foram tocados. F0–F6, contratos de KPI, `quality_checks.yaml`, mappings, Truth
Layer, geração de dados e as regras semânticas da F7 estão exatamente como
estavam.

## 3. Ferramentas implementadas

| Tool | Escopo | Read-only | Calcula? |
|---|---|---|---|
| `get_kpi` | `kpi:read:value` | sim | não — delega a `ask()` |
| `compare_kpi` | `kpi:read:value` | sim | não |
| `breakdown_kpi` | `kpi:read:value` | sim | não |
| `get_kpi_definition` | `kpi:read:definition` | sim | não toca dado |
| `get_trust` | `kpi:read:trust` | sim | não calcula valor |
| `get_lineage` | `kpi:read:lineage` | sim | não toca dado |

`server.list_tools()` devolve o manifesto em forma de `tools/list` — nome,
descrição, `inputSchema`, escopo e `readOnly`. `server.call(tool, args, actor)`
executa. A camada é protocolo-agnóstica: ligar isso a um transporte concreto é
um passo mecânico e posterior, e o que precisava estar certo aqui é a
superfície, não o encanamento.

## 4. Testes adicionados

35 testes, cobrindo os casos A–W pedidos:

| Bloco | Testes |
|---|---|
| A–F, as seis capacidades | `get_kpi`, `compare_kpi`, `breakdown_kpi`, `get_kpi_definition`, `get_trust`, `get_lineage` |
| G–J, estados governados | BLOCKED, LIMITED, CERTIFIED, teto inferior ao pedido |
| K–N, privacidade e membros | `minimum_n` já aplicado, linha `SUPPRESSED`, `UNMAPPED`, `VALOR_AUSENTE` |
| O–R, segurança de interface | SQL, RAW, camada intermediária, escrita |
| S–W, recusas e teto | KPI inexistente, filtro inválido, dimensão negada, recusa ≠ erro, teto não é elevado |
| D-1 | 6 testes de série (ver seção 8) |
| apoio | envelope, limites, log, registro de seis, não duplicação |

## 5. Resultado da suíte

```
237 passed in 91.49s
    144  F0–F6
     58  F7 (44 + 14 da correção M-06)
     35  MCP v0.1
```

## 6. Invariantes verificadas

Todas chegam **pela fronteira**, e nenhuma é recalculada no MCP:

| KPI | Período | Valor |
|---|---|---|
| `headcount` | 2026-06 | 1.942 |
| `headcount` | 2016-06 | 397 |
| `turnover_rate` | 2024 | 0,253766 |

A verificação de que o MCP não calcula é estrutural, não declaratória:
`test_o_mcp_nao_duplica_a_camada_semantica` lê a **árvore sintática** de
`tools.py` e reprova qualquer literal de código com `SELECT`, `FROM`, `JOIN`,
`GROUP BY`, `COUNT(`, `read_parquet` ou `is_system_of_record` — mesma técnica do
teste F-13 da F6. As docstrings podem citar o nome da coluna para explicar o
defeito que a fronteira evita; o código, não. E `test_invariantes` verifica que
nenhum módulo do MCP importa Polars ou DuckDB.

## 7. Failure cases cobertos

| # | Caso | Como falha |
|---|---|---|
| FCm-01 | alcançar RAW | nenhum `inputSchema` admite `table`, `schema`, `column`, `path`, `sql`, `query`; os schemas `truth`/`raw`/`conformed` não resolvem na conexão |
| FCm-02 | SQL arbitrário | 6 variações, incluindo `sql`, `query`, `where`, `expression` dentro do filtro, e SQL no lugar do `kpi_id` |
| FCm-03 | valor de KPI `BLOCKED` | os 5 bloqueados × 2 tools de valor: `KPI_BLOQUEADO`, `data: null` |
| FCm-04 | dimensão não permitida | recusa com a lista do que responde; a negação vinda do **ator** é distinguível pela `origem: ATOR` |
| FCm-05 | alterar mapeamento | `CAPACIDADE_INEXISTENTE` |
| FCm-06 | alterar Trust | idem; `get_trust` não tem campo de entrada que altere banda |
| FCm-07 | consultar a Truth Layer | nome não resolve; parâmetro não existe |
| FCm-08 | `INDETERMINADA` virar contratação | herdado da F7 (FC-09), preservado |
| FCm-09 | ultrapassar o teto | `test_w`: ator CAUSALITY não recebe CAUSALITY; nenhum KPI tem teto acima de CONTEXT |
| FCm-10 | vazar recorte abaixo do mínimo | linha `suppressed: true`, `value: null`, população omitida |
| FCm-11 | membro `null` | `UNMAPPED` atravessa nomeado; `VALOR_AUSENTE` é distinto |
| FCm-12 | truncagem silenciosa | recusa com o que estreitar; `top_n` é escolha declarada e sai em `limits` |

Complemento sobre escrita (FCm-05/06 e o critério 5): escrita não é negada por
permissão. **Não existe ferramenta de escrita**, então não há chamada a negar —
`test_r` verifica que o registro tem exatamente as seis, que nenhuma está na
lista de nomes proibidos, e que `Actor(scopes=("kpi:write:value",))` levanta erro
porque o escopo não existe.

## 8. Desvio D-1 — `series` em `get_kpi`

**É desvio da SPEC, autorizado por você, e a SPEC permanece inalterada.**

**Por que foi necessário.** A SPEC permite `period.to` diferente de `from`, com
limite de 24 períodos — ou seja, uma série é uma entrada válida. O schema de
saída da Parte V, porém, nomeia só `value: number | null` escalar. Sem um campo
para a série, uma consulta de 6 meses responderia `value: null` e nada mais, e a
entrada permitida não teria saída.

**O que foi implementado.**

- **1 período → `value` escalar**, exatamente como o contrato atual. `series` e
  `series_meta` **não aparecem** nesse caso;
- **2+ períodos → `series`**, e `value` fica `null` porque não há escalar a
  informar;
- cada item da série traz `period`, `value`, `population` e os metadados
  governados do ponto: `suppressed` e `suppression_reason` — a supressão por
  privacidade vale por linha, e um mês pequeno demais não responde só porque a
  série inteira responde;
- `series_meta` declara `periods`, `grain`, `unit`, `suppressed_periods` e
  `trust_escopo`, que diz explicitamente que **trust e teto valem para a série
  inteira** e vivem no envelope. Nenhum ponto carrega trust próprio: isso seria
  regra semântica nova;
- nenhum valor é recalculado. Cada item é a linha que a Semantic Layer devolveu.

**Quais testes comprovam.**

| Teste | O que prova |
|---|---|
| `test_d1_um_periodo_responde_escalar` | compatibilidade: 1 período = 1.942 escalar, sem `series` |
| `test_d1_dois_ou_mais_periodos_respondem_series` | 6 meses, campos exatos por item, último ponto = o escalar |
| `test_d1_serie_ate_24_periodos` | 24 períodos respondem |
| `test_d1_mais_de_24_periodos_e_recusado` | 25 períodos → `LIMITE_DE_RESULTADO_EXCEDIDO`, `data: null` |
| `test_d1_serie_preserva_trust_teto_e_limitacoes` | trust LIMITED/GOVERNANCA, caveats e teto preservados; nenhum ponto com trust próprio |
| `test_d1_nao_altera_valor_nem_cria_regra_semantica` | cada ponto é idêntico à consulta escalar do mesmo mês; nenhuma soma, média ou interpolação em `tools.py` |

## 9. Outros desvios e decisões de implementação

Três, todos menores e nenhum arquitetural. Nenhum ADR novo foi criado.

**D-2 — `response_level` ausente nas tools de metadados.** A SPEC diz que o
campo está "sempre presente quando há KPI resolvido". `get_kpi_definition`,
`get_trust` e `get_lineage` resolvem um KPI e **não produzem resposta
quantitativa**, então não há nível a conceder. O campo fica ausente em vez de
preenchido com um valor que não significa nada. O teto de nível do KPI continua
disponível, em `get_kpi_definition`, no campo `response_levels.ceiling`.

**D-3 — o filtro fixo atravessa pelo `porque`, não pelo `regra`.** O contrato
guarda o filtro em duas formas: `regra` (`is_system_of_record = true`) e
`porque` (a explicação de negócio). A SPEC exige que o filtro apareça "em
linguagem de negócio, porque o agente precisa saber que ele existe sem precisar
saber como se chama". O MCP expõe o `porque`. Isto foi encontrado por um teste
que eu havia escrito para outra coisa: `test_p` reprovou porque
`is_system_of_record` estava vazando na resposta.

**D-4 — `maxItems` fora do schema de `dimensions`.** A SPEC diz que todo limite
atingido vira **recusa explicada**. Declarar `maxItems: 2` no `inputSchema`
transformaria três dimensões em erro de forma (`PARAMETRO_INVALIDO`) em vez de
recusa governada. O limite ficou só na verificação, que produz
`LIMITE_DE_RESULTADO_EXCEDIDO` dizendo o que estreitar.

**Escopo declarado, não um desvio:** a v0.1 implementa o *boundary* — registro,
autorização, validação, dispatch e manifesto. O binding a um transporte concreto
(stdio/JSON-RPC) não foi implementado, porque a SPEC não o especifica e porque o
que precisa estar certo nesta etapa é a superfície. `list_tools()` já devolve o
manifesto na forma que um transporte consome.

## 10. Decisões que precisam de aprovação humana

**Nenhuma bloqueante.** D-1 já foi autorizada. D-2, D-3 e D-4 são consequências
diretas de regras que a SPEC já declara, e estão registradas acima para você
confirmar ou reverter.

Duas observações, sem ação necessária agora:

1. **Os limites da Parte VIII são um ponto de partida.** 24 períodos, 2
   dimensões, 50 linhas e 200 avaliadas. Na prática, `headcount` por
   departamento × nível já produz 218 linhas e é recusado — que é o
   comportamento correto pela SPEC, e vale saber que acontece no primeiro
   recorte de duas dimensões que alguém tentar.
2. **`get_lineage` por `trace_id` reconstrói a linhagem do registro de
   consultas**, que não guarda a contagem de linhas consideradas. O campo volta
   `null` com uma nota dizendo por quê, em vez de um número adivinhado.

## 11. Critério de sucesso

| # | Critério | Situação |
|---|---|---|
| 1 | seis ferramentas implementadas | **sim**, e exatamente seis |
| 2 | respeitam a SPEC | **sim**, com os desvios 8 e 9 declarados |
| 3 | nenhuma acessa RAW/intermediário | **sim** — o schema não resolve e o parâmetro não existe |
| 4 | nenhuma aceita SQL arbitrário | **sim** — campo desconhecido reprova, em duas camadas |
| 5 | nenhuma tem write capability | **sim** — a ferramenta não existe, e o escopo também não |
| 6 | BLOCKED continua BLOCKED | **sim** — nos 5 bloqueados, nas tools de valor |
| 7 | Trust preservado | **sim** — devolvido da F7, sem recálculo; bandas intactas |
| 8 | privacidade preservada | **sim** — o MCP não implementa `minimum_n`, preserva |
| 9 | `UNMAPPED` preservado | **sim** — e distinto de `VALOR_AUSENTE` |
| 10 | teto corretamente composto | **sim** — `min` dos três, com `ceiling_from` |
| 11 | recusa é resultado estruturado | **sim** — só três classes são `ERROR` |
| 12 | testes de contrato verdes | **sim** — 35 |
| 13 | suíte F0–F7 verde | **sim** — 237 no total |
| 14 | valores analíticos inalterados | **sim** — 1.942 / 397 / 0,253766 |

---

**Sem commit.** Aguardando revisão.
