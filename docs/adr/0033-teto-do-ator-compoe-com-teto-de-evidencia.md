# ADR-0033: O teto do ator compõe com o teto de evidência, e nunca o substitui

- **Status:** **Proposta** (MCP v0.1, aguardando aprovação)
- **Data:** 2026-09-12
- **Origem:** MCP v0.1, decisão M-05
- **Fase:** vigora do MCP v0.1 em diante

## Contexto

O ADR-0029 estabeleceu que confiança tem duas dimensões independentes, e que a
menor manda:

```
trust_resposta = min(trust_dado, teto do status de certificação)
```

A F7 implementou isso e o caso que o justifica continua no catálogo:
`internal_mobility_rate` tem trust de dado 0,9939 e está `BLOCKED`, porque
`movement_type` carrega dois vocabulários ao mesmo tempo. Dado limpo, definição
frágil.

O MCP introduz uma **terceira** dimensão, que não existia enquanto o consumidor
era o próprio projeto: **quem está perguntando**. Um ator pode estar autorizado a
ver headcount e não a ver recorte por gênero; a ver números e não a ver linhagem;
a receber fato e não interpretação.

A pergunta que este ADR responde é a de direção: uma permissão **abaixa** o
teto ou pode **levantá-lo**?

A resposta errada é intuitiva, e é por isso que precisa estar escrita. Em quase
todo sistema, permissão é o que libera: quem tem o papel certo alcança o que
outros não alcançam. Transplantar essa intuição para cá produziria um ator com
`max_response_level: INTERPRETATION` recebendo interpretação de um KPI que não
tem nenhuma `interpretation_rule` registrada — ou seja, a IA inventando uma
banda porque quem perguntou tinha cargo alto.

Isso não é uma hipótese: hoje **nenhum dos treze KPIs que respondem tem regra de
interpretação registrada**, e o teto efetivo é CONTEXT em todos. Um sistema em
que permissão levanta teto estaria, no primeiro dia, gerando interpretação sem
regra para quem tem o escopo mais alto.

## Decisão

### 1. Três termos, e o menor manda

```
response_level = min( nível pedido,
                      teto de evidência   (F7: status + regra + estudo),
                      teto do ator        (autorização) )

trust_resposta = min( trust_dado          (F5, medido),
                      teto do status      (F7, ADR-0029),
                      teto do ator        (autorização) )
```

O `min` é sobre ordens declaradas — `FACT < CONTEXT < INTERPRETATION <
CAUSALITY` e `BLOCKED < LIMITED < CERTIFIED` — e não sobre números. Nenhum
número novo é criado, pela mesma razão do ADR-0029: o único valor medido
continua sendo `trust_dado`.

### 2. Autorização só restringe

`actor.max_response_level` e `actor.dimension_deny` **abaixam** o que já era
possível. Nenhuma configuração de ator destrava nível, dimensão, KPI bloqueado,
período fora de cobertura ou recorte abaixo do n mínimo.

Em particular: nenhum ator, com nenhum escopo, recebe INTERPRETATION de um KPI
sem `interpretation_rules`, nem CAUSALITY sem estudo registrado. Evidência
ausente não é permissão faltando.

### 3. `ceiling_from` é obrigatório na resposta

A resposta declara **qual dos três** prendeu:

```yaml
response_level: {requested: CONTEXT, granted: FACT, ceiling_from: ATOR}
```

Sem esse campo, um agente que recebe FACT quando pediu CONTEXT não sabe se deve
pedir certificação a People Analytics (`GOVERNANCA`), pedir correção de dado a
engenharia (`TRUST`), esperar uma regra ser assinada (`EVIDENCIA`) ou pedir
permissão ao administrador (`ATOR`). São quatro ações, quatro pessoas, e sem o
campo ele adivinha — provavelmente reclamando do dado, que é a suspeita padrão e
a errada na maior parte dos casos.

### 4. Supressão por privacidade não tem teto de ator

`minimum_n` não é permissão e não é configurável por ator. Um ator com todos os
escopos continua recebendo `SUPPRESSED` num recorte abaixo do mínimo. O ADR-0007
protege a pessoa contada, não o dado, e quem pergunta não muda quem está no
recorte.

### 5. Escopo é verificado antes de qualquer execução

`ESCOPO_INSUFICIENTE` é `ERROR` e acontece antes da validação semântica e antes
de qualquer leitura. Uma chamada não autorizada não deve nem revelar se o KPI
existe.

### 6. A autorização não é o que impede a escrita

Vale repetir aqui porque a confusão é natural: não há tool de escrita
(ADR-0031). A autorização estreita leitura. Descrever o modelo de permissão como
"o que impede o agente de alterar dados" seria descrever errado, e a descrição
errada é o começo de alguém adicionar a capacidade confiando na permissão.

## Alternativas consideradas

1. **Permissão que libera nível.** Rejeitada: produziria interpretação sem regra
   registrada para quem tem escopo alto, que é exatamente o que o ADR-0015
   proíbe e o que a F7 implementou como teto de evidência.
2. **Autorização como quarta dimensão de confiança, com número próprio.**
   Exigiria inventar um número para "ator restrito", e número inventado é o
   score artificial que a F5 proíbe.
3. **Só escopo de ferramenta, sem teto de nível por ator.** Mais simples, e
   perde um caso real: um ator pode legitimamente ver números e não dever
   receber juízo de valor sobre eles. Sem `max_response_level`, a única forma de
   expressar isso seria negar a ferramenta inteira.
4. **Deixar a autorização inteiramente para o harness, fora do MCP.** O harness
   não conhece o teto de evidência, então a composição aconteceria em dois
   lugares que não se falam — e composição espalhada diverge, que é o defeito
   que este projeto já pagou em `depends_on_checks`.
5. **`minimum_n` configurável por ator.** Rejeitada sem hesitação: transformaria
   proteção da pessoa contada em privilégio de quem pergunta.

## Consequências

**Positivas**

- A autorização corporativa pode ser plugada depois sem redesenhar a composição:
  o terceiro termo já tem lugar, ordem e campo de diagnóstico.
- `ceiling_from` transforma uma limitação em encaminhamento: o agente diz a quem
  pedir.
- Fecha, antes de existir autenticação, a porta por onde "o diretor tem acesso
  total" viraria interpretação sem regra.

**Negativas**

- Três termos compondo é mais difícil de explicar do que "você tem ou não tem
  acesso", e alguém vai receber FACT com todas as permissões e achar que há um
  bug de permissão.
- Um ator restrito e um KPI não certificado produzem a mesma banda por motivos
  diferentes, e distinguir depende de o consumidor ler `ceiling_from`.
- Exige que o contrato do ator exista desde já, mesmo sem autenticação, para que
  a composição seja testável.

**Riscos e mitigação**

- *Risco:* alguém implementar `max_response_level` como override em vez de teto,
  porque "o admin precisa ver tudo". *Mitigação:* ACm-10, que verifica o `min`
  nas combinações, incluindo ator alto com evidência ausente.
- *Risco:* `dimension_deny` ser usado para esconder um problema de dado em vez de
  restringir acesso. *Mitigação:* `ceiling_from: ATOR` é visível na resposta e no
  log, então a restrição aparece em vez de silenciar.

## Referências

- `docs/MCP_SPEC_v0.1.md`, Partes VI, IX e XII
- ADR-0007 (n mínimo e supressão), ADR-0015 (níveis de resposta e causalidade),
  ADR-0022 (natureza da perda), ADR-0029 (certificação limita o nível),
  ADR-0031 (o MCP expõe capacidades)
