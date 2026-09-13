# ADR-0032: Recusa é resultado da ferramenta, não erro de protocolo

- **Status:** **Proposta** (MCP v0.1, aguardando aprovação)
- **Data:** 2026-09-12
- **Origem:** MCP v0.1, decisão M-02
- **Fase:** vigora do MCP v0.1 em diante

## Contexto

A F7 gastou boa parte do seu desenho em recusa. São dezesseis classes, cada uma
com três campos obrigatórios — `classe`, `mensagem`, `o_que_resolveria` — e a
regra de que recusa é parte do produto, não exceção. "Recusa que não diz o
caminho é só uma porta fechada."

O protocolo MCP oferece uma saída fácil que apaga tudo isso: marcar a chamada
como erro. Um resultado com `isError: true` chega ao modelo como "a ferramenta
falhou", e o comportamento induzido é sempre o mesmo — **tentar de novo**.

Isso importa aqui mais do que importaria em outro sistema, porque as recusas
deste projeto são informativas por construção, e três delas ficam ativamente
perigosas se lidas como falha:

| Recusa | Lida como erro, o agente… | O que deveria acontecer |
|---|---|---|
| supressão por n mínimo | tenta outro recorte, e outro, até um passar | parar, e dizer que o grupo é pequeno demais |
| `KPI_BLOQUEADO` | tenta um KPI parecido | relatar o bloqueador e quem o resolve |
| `PERIODO_FORA_DE_COBERTURA` | tenta outro período, ou reporta zero | dizer a janela coberta |

A primeira é a pior. Repetir consultas estreitando o recorte até uma passar é
reidentificação por tentativa, e a supressão por privacidade existe justamente
para impedir isso. Transformá-la em erro transforma a proteção no gatilho.

Há ainda um efeito de segunda ordem: uma recusa que vira erro **sai do
raciocínio do agente e entra no tratamento de exceção do harness**. O agente
deixa de ter o que relatar à pessoa. A resposta vira "não consegui obter esse
dado", quando a resposta correta era "esse KPI está bloqueado porque
`movement_type` tem dois vocabulários, e quem resolve é People Analytics".

## Decisão

### 1. Recusa é resultado bem-sucedido do transporte

Uma recusa atravessa como chamada bem-sucedida, com o envelope preenchido:

```yaml
ok: false
outcome: REFUSAL
refusal:
  classe: KPI_BLOQUEADO
  mensagem: "..."
  o_que_resolveria: "..."
  detalhe: {...}
trace_id: ...
```

`ok: false` diz que não houve valor. `outcome` diz **por quê**, de forma que o
agente possa raciocinar. O protocolo não marca erro.

### 2. Quatro resultados, e eles não se confundem

| `outcome` | Significado | Quem resolve | Erro de protocolo? |
|---|---|---|---|
| `ANSWER` | há valor | — | não |
| `REFUSAL` | pergunta válida, resposta não sustentável | depende da classe | não |
| `SUPPRESSED` | há resposta; não sai por **privacidade** | ninguém: é assim mesmo | não |
| `ERROR` | chamada malformada, ou ator sem escopo | **quem chamou** | **sim** |

Só `ERROR` é erro de protocolo, e só ele descreve um defeito do chamador:
`PARAMETRO_INVALIDO`, `ESCOPO_INSUFICIENTE`, `CAPACIDADE_INEXISTENTE`. Esses o
agente deve corrigir ou desistir, e tentar de novo igual não adianta.

### 3. `o_que_resolveria` é obrigatório em toda recusa

Já é regra da F7; aqui ela vira contrato de transporte. Uma recusa sem caminho
deixa o agente diante de porta fechada, e agente diante de porta fechada
inventa.

### 4. Supressão nunca é recusa, e nunca é erro

`SUPPRESSED` é categoria própria, usa a palavra **privacidade**, e a resposta
diz explicitamente que não é desconfiança no dado. O trust do recorte continua
sendo devolvido, e não é o motivo.

### 5. `LIMITED` responde

Um KPI `LIMITED` não é recusa: responde, com teto de nível em CONTEXT, ressalva
nos `caveats` e `limitado_por` dizendo o lado. Tratar `LIMITED` como falha faria
oito dos treze KPIs que respondem hoje desaparecerem do agente — e eles são
informação honesta, não informação ruim.

### 6. Toda recusa é registrada

Recusa entra no log com a mesma dignidade de uma resposta, com `trace_id`. É a
razão pela qual a F7 registra recusas: sem isso, ninguém descobre que a mesma
pergunta é recusada toda semana pelo mesmo mapeamento pendente.

## Alternativas consideradas

1. **`isError: true` para tudo que não é valor.** É o caminho padrão e o que
   produz o comportamento de repetição. Descartado principalmente pela
   supressão: transforma a proteção de privacidade no gatilho da tentativa
   seguinte.
2. **`isError: true` só para bloqueios "graves", resultado normal para o
   resto.** Exigiria classificar dezesseis classes em duas famílias por
   gravidade, e gravidade não é o eixo certo — o eixo é **quem resolve**. Duas
   recusas igualmente graves podem exigir ações de pessoas diferentes.
3. **Resultado normal com texto livre explicando.** O agente lê, e nada garante
   estrutura: sem `classe`, o harness não consegue métrica de recusa, e sem
   `o_que_resolveria` obrigatório o campo some na primeira pressa.
4. **Exceção tipada no protocolo, com payload estruturado no erro.** Depende de
   o cliente preservar o payload do erro, o que nem todo harness faz. A
   informação mais importante ficaria no lugar mais frágil.
5. **Devolver zero em vez de recusar, em período sem cobertura.** Já descartado
   na F7 e repetido aqui: zero é um valor, ausência de carga não é.

## Consequências

**Positivas**

- O agente pode **relatar** a recusa à pessoa, com o motivo e o caminho, em vez
  de dizer que falhou.
- A supressão por privacidade deixa de induzir repetição, que era o risco real.
- Recusas viram métrica: contagem por classe mostra qual pendência de governança
  custa mais respostas por semana.
- O harness distingue defeito do chamador (`ERROR`) de limite do sistema
  (`REFUSAL`), e só o primeiro merece retentativa.

**Negativas**

- `ok: false` com chamada bem-sucedida é contraintuitivo para quem espera que
  sucesso de protocolo signifique sucesso de negócio. Vai precisar de explicação
  em toda integração nova.
- Um harness que só olha `isError` vai tratar recusa como sucesso e pode deixar
  passar `data: null` sem tratamento. O envelope mitiga com `ok`, mas depende de
  o consumidor lê-lo.
- Quatro categorias de resultado é mais superfície de contrato do que duas.

**Riscos e mitigação**

- *Risco:* o agente, vendo `ok: false` sem erro, inventar um número plausível
  para não devolver resposta vazia. *Mitigação:* fora do escopo do MCP — é regra
  do agente — mas a `mensagem` e o `o_que_resolveria` existem para dar a ele
  algo verdadeiro para dizer no lugar.
- *Risco:* classificar como `REFUSAL` algo que é defeito do chamador,
  escondendo bug de integração. *Mitigação:* `PARAMETRO_INVALIDO`,
  `ESCOPO_INSUFICIENTE` e `CAPACIDADE_INEXISTENTE` são `ERROR` por definição, e
  ACm-07 verifica a separação.

## Referências

- `docs/MCP_SPEC_v0.1.md`, Partes IV, VII e XII
- ADR-0007 (n mínimo e supressão), ADR-0015 (níveis de resposta), ADR-0029
  (certificação limita o nível), ADR-0031 (o MCP expõe capacidades)
- F7, `src/analytics/semantic/query.py`, as dezesseis classes de recusa
