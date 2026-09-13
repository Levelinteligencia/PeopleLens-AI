# ADR-0001: Geração em dois passos, ground truth e projeção

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D1 (Technical Design v0.3)
- **Fase:** F0, vigora a partir da F1

## Contexto

O projeto precisa de um dataset de RH sintético, grande, e propositalmente
sujo. A forma direta de produzir isso é gerar os dados já com defeitos. Essa
forma tem dois problemas.

O primeiro é de avaliação. Um dataset sujo gerado diretamente é inauditável:
dá para inspecionar o pipeline, não dá para medi-lo, porque não existe valor
de referência. "O headcount depois do tratamento é 14.203" é uma afirmação sem
contraparte.

O segundo é menos óbvio e mais grave para este projeto: defeito sem causa não
tem padrão. Nulos distribuídos uniformemente aparecem igualmente em todo ano,
país e sistema. A camada de profiling não tem o que descobrir e vira
decoração. Quando o nulo vem de uma causa, por exemplo o campo não existir
antes de jun/2019, o profiling encontra uma quebra de série numa data
específica, e essa descoberta é o que justifica a camada existir.

## Decisão

A geração acontece em dois passos separados.

**Passo A**, simulação da NOVAORA verdadeira. Cada pessoa tem um ciclo de vida
coerente, com eventos encadeados e integridade referencial garantida por
construção. Saída em `data/synthetic/truth/`.

**Passo B**, projeção dessa verdade nos sistemas-fonte, aplicando por sistema
os perfis de corrupção declarados em `config/defects.yaml`, sempre
referenciando o incidente que os origina em `config/incidents.yaml`. Saída em
`data/raw/<source_system>/`.

A camada `truth/` fica **fora do alcance do pipeline**. Ela é lida apenas por
`tests/truth/` e por um notebook de avaliação. Nenhum módulo de ingestão,
limpeza, mapeamento, qualidade ou analytics tem permissão de leitura sobre ela.

## Alternativas consideradas

1. **Gerar os dados sujos diretamente.** Metade do código. Descartada: elimina
   o gabarito e produz defeitos sem padrão.
2. **Gerar a verdade e descartá-la após a projeção.** Economiza disco.
   Descartada: disco não é restrição aqui, e sem a verdade não há avaliação.
3. **Expor a verdade como um "sistema-fonte perfeito".** Descartada: contamina
   o exercício, porque o pipeline aprenderia a preferir a fonte limpa.

## Consequências

**Positivas**

- Habilita a afirmação quantitativa que diferencia o projeto: "o HRIS
  reportava headcount 4,1% acima da realidade; após reconciliação e DE/PARA o
  PeopleLens chegou a 0,3% do valor verdadeiro".
- Permite validar o trust score contra a verdade, em vez de confiar nele.
- Transforma os testes de integração em medição de acurácia, não verificação
  de forma.
- Todo defeito passa a ter causa declarada, o que atende diretamente à seção 25
  da Especificação.

**Negativas**

- Praticamente dobra o código do gerador. É o componente mais caro do projeto.
- Exige manter coerência entre duas representações do mesmo mundo.

**Riscos e mitigação**

- *Risco:* vazamento acidental da verdade para o pipeline. *Mitigação:* a
  verdade fica em diretório próprio, e um teste falha se qualquer módulo fora
  de `tests/` importar dela.
- *Risco:* a verdade e a projeção divergirem por bug e ninguém perceber.
  *Mitigação:* o manifesto registra contagens dos dois lados e o teste de
  reconciliação da F2 compara.

## Referências

- Technical Design v0.3, seções 2 e 17 (R1)
- Especificação do Universo v1.0, seção 25
- `config/generation.yaml`, `config/defects.yaml`
