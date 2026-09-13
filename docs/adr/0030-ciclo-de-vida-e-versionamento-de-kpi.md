# ADR-0030: Ciclo de vida e versionamento de KPI, com a versão anterior consultável

- **Status:** **Proposta** (F7, aguardando aprovação)
- **Data:** 2026-09-12
- **Origem:** F7, decisão D7-04
- **Fase:** vigora da F7 em diante

## Contexto

O ADR-0011 definiu o que um contrato de KPI **declara**: dependências de checks,
dependências de mapeamentos, n mínimo, níveis de resposta permitidos. Não
definiu o que acontece ao contrato **ao longo do tempo** — quem o aprova, como
ele muda, e o que a mudança faz com os números já respondidos.

Essa lacuna tem consequência concreta. Um KPI de People Analytics muda de
definição por motivos legítimos e frequentes: um nível deixa de contar como
liderança, o denominador passa a incluir estagiários, uma exclusão nova entra
depois de uma auditoria. Sem regra, a mudança é retroativa por padrão: a
consulta de hoje sobre 2022 devolve um número diferente do que devolveu em 2022,
sem nada na resposta indicando isso. A série histórica é reescrita em silêncio.

É a mesma patologia que o projeto já combateu duas vezes, agora na camada
semântica: a F3 proibiu correção silenciosa no RAW e a F4 proibiu promoção
automática de mapeamento. Aqui o valor alterado não é uma célula, é a definição
que gera milhares de células.

O ciclo de vida também já existe no projeto, em outro objeto: mapeamento de
DE/PARA tem `APPROVED`, `PROPOSED`, `DEPRECATED`, `REJECTED`, com aprovação que
exige responsável e justificativa. Reusar essa forma é preferível a inventar
outra.

## Decisão

### 1. Cinco estados

```
DRAFT → DECLARED → CERTIFIED → DEPRECATED
                 ↘ BLOCKED (bloqueador técnico ou de definição)
```

| Transição | Exige |
|---|---|
| `DRAFT → DECLARED` | dono, definição de negócio, fórmula, grain, população |
| `DECLARED → CERTIFIED` | nenhum check BLOCKER das dependências reprovando; mapeamentos sem pendência bloqueante; cobertura declarada; aprovação registrada com dono e data |
| `qualquer → BLOCKED` | bloqueador declarado **e o que o resolve** |
| `BLOCKED → anterior` | o bloqueador resolvido, com a evidência |
| `CERTIFIED → DEPRECATED` | KPI substituto declarado |

`BLOCKED` é estado de primeira classe e não ausência. `internal_mobility_rate`,
`promotion_rate`, `compa_ratio` e `pay_gap` entram no catálogo bloqueados, com o
bloqueador nomeado, em vez de ficarem de fora e reaparecerem como consulta ad hoc
sem governança.

### 2. Versionamento semântico, e a primeira linha é a que importa

| Mudança | Versão | Efeito |
|---|---|---|
| definição de negócio ou fórmula | **maior** | quebra comparabilidade |
| filtro, exclusão, dimensão permitida, cobertura | menor | não quebra série |
| texto, descrição, dono | correção | nenhum |

`kpi_id` é **imutável**. Mudou o id, é outro KPI, não uma versão nova.

### 3. Mudar a fórmula não reescreve o passado

Uma mudança maior **não substitui** a versão anterior: as duas coexistem. A série
histórica calculada com a versão anterior continua reproduzível, e toda resposta
declara qual versão usou.

```yaml
kpi: {id: women_in_leadership, version: 2.0.0, status: CERTIFIED}
```

Comparar dois períodos calculados com versões diferentes é **recusado por
padrão**. A recusa diz o que mudou entre as versões e o que seria necessário
para comparar mesmo assim — quem quiser comparar declara isso explicitamente, e
a resposta sai com a ressalva de quebra de comparabilidade. Fazer a comparação
sem aviso é apresentar uma tendência que é artefato da mudança de definição.

Isso é o análogo semântico do ADR-0018: antes de comparar, controlar a
proveniência do número.

### 4. Depreciar não apaga

Um KPI `DEPRECATED` continua consultável para período histórico, com teto
`LIMITED` e CONTEXT (ADR-0029), e a resposta aponta o substituto. Remover um KPI
do catálogo torna irreproduzíveis todas as respostas que já o citaram.

A remoção definitiva é ato deliberado e registrado, nunca limpeza.

### 5. Quem muda

A criação, alteração, versionamento, certificação e depreciação de KPI são atos
de People Analytics, registrados com dono e data. A IA não executa nenhum deles
(ADR-0028, seção 5 da Parte VII da SPEC). Um contrato alterado sem dono e sem
data não é uma versão nova: é uma alteração não governada, e a verificação de
contratos a recusa.

### 6. Dependências fazem parte do contrato versionado

`depends_on_checks` continua **derivado** de `consumed_by_kpis`, como a F5
estabeleceu, e nunca digitado. Uma mudança nas dependências que altere o conjunto
de checks que sustenta o KPI é mudança menor; uma que altere o que o KPI mede é
maior. A verificação bidirecional da F5 (`contracts.verify()`) continua valendo
e passa a cobrir também `status`, `owner` e `version`.

## Alternativas consideradas

1. **Sem versionamento: o contrato é o que está no arquivo hoje.** É o
   comportamento padrão e o pior: reescreve a série histórica em silêncio, que é
   exatamente a correção silenciosa que o projeto proíbe desde a F3.
2. **Versionar e manter só a versão corrente consultável.** Metade do problema
   resolvido: dá para saber que mudou, não dá para reproduzir o número antigo.
   Uma resposta de seis meses atrás vira inauditável.
3. **Congelar a fórmula: KPI certificado não muda, cria-se outro id.**
   Reprodutível e ruim de usar: `headcount_v2`, `headcount_v3` poluem o
   vocabulário e o consumidor tem que saber qual pedir, que é precisamente o que
   a Semantic Layer existe para evitar.
4. **Deixar a comparação entre versões passar com uma nota de rodapé.** Foi
   descartado pela mesma razão que `caveats` não substitui recusa: a nota é o que
   não se lê. Recusar e explicar é mais útil que responder e ressalvar.
5. **Versionamento por data de vigência, como o DE/PARA da F4
   (`valid_from`/`valid_to`).** Elegante e inadequado aqui: a vigência de um
   mapeamento é uma propriedade do mundo (o código mudou naquela data); a versão
   de um KPI é uma propriedade da decisão, e a mesma versão pode ser aplicada
   retroativamente ou não conforme a decisão. Manter os dois como versões
   coexistentes é mais honesto que fingir uma linha do tempo.

## Consequências

**Positivas**

- Um número respondido em 2026 continua reproduzível em 2028, com a versão que o
  gerou.
- Mudança de definição vira evento visível, datado e com dono, em vez de um diff
  de YAML que ninguém liga a um salto na série.
- `BLOCKED` como estado nomeado permite falar sobre o KPI que não pode ser
  calculado, o que é mais útil do que o silêncio.
- Reusa o padrão de governança já aprovado na F4, sem vocabulário novo para
  aprender.

**Negativas**

- Duas ou mais versões de um mesmo KPI convivendo é complexidade real: a
  resposta precisa dizer a versão sempre, e a comparação entre períodos vira uma
  verificação a mais.
- Depreciar sem apagar faz o catálogo crescer monotonicamente. Com o tempo há
  KPIs que ninguém usa ocupando espaço no vocabulário — e o custo de removê-los é
  justamente o que este ADR protege.
- A recusa de comparação entre versões vai parecer excesso de zelo na primeira
  vez que acontecer, e será difícil de explicar a quem só quer o gráfico.

**Riscos e mitigação**

- *Risco:* alguém editar a fórmula sem subir a versão, por pressa. *Mitigação:*
  a verificação de contratos compara a fórmula com a registrada na versão
  corrente e falha quando divergem sem incremento — mesma lógica da verificação
  bidirecional da F5.
- *Risco:* versão maior usada para mudanças cosméticas, inflando quebras de
  comparabilidade. *Mitigação:* a tabela da seção 2 é a regra, e a justificativa
  fica no contrato.

## Referências

- `docs/F7_semantic_layer.md`, Parte VII
- ADR-0011 (dependências no contrato de KPI), ADR-0018 (controle de proveniência
  antes de comparar), ADR-0028 (saída da IA é consulta semântica), ADR-0029
  (certificação limita o nível de resposta)
- F4, ciclo de vida do DE/PARA; F5, `src/analytics/contracts.py`
