# ADR-0026: O sistema observador faz parte do grain do fato

- **Status:** **Proposta** (F6, aguardando aprovação)
- **Data:** 2026-09-11
- **Origem:** SPEC da F6, Partes II.8 e VII
- **Fase:** vigora da F6 em diante

## Contexto

Entre maio e novembro de 2019, o HRIS legado e o HRIS corporativo rodaram em
paralelo (`INC_2019_HRIS_MIGRATION`). Nesses sete meses, **a mesma pessoa aparece
no mesmo mês nos dois sistemas**, com atributos que podem divergir.

Um fato de headcount com grain "pessoa × mês" não consegue representar isso. Ou
alguém escolhe um dos dois sistemas e a evidência da migração desaparece, ou os
dois entram e a contagem duplica sem que nada avise.

A escolha silenciosa é a saída fácil e é a que o projeto já pagou. O achado 1 da
F5 foi uma reconciliação que passava com razão 1,068 porque comparava cinco
países desde 2019 contra a folha de um país desde 2016 — duas distorções de
escopo se cancelando dentro de uma faixa que aprovava. Com o escopo igualado, a
razão é 0,966 em todos os 86 meses. **A lição foi que vigência e população
precisam ser parte da comparação, não uma nota no YAML.**

O mesmo vale para os outros sistemas: cada um tem `active_from`, `active_to`,
países cobertos e `population_rule` próprios. A folha, por exemplo, tem uma
definição de "ativo" que inclui terceiro, estagiário e aviso prévio, e exclui
afastado de longa duração.

## Decisão

1. **`source_sk` faz parte do grain** de `fact_headcount_snapshot`, `fact_hire`,
   `fact_termination` e `fact_compensation`. O grain de headcount é
   **pessoa × mês × sistema observador**.

2. **`dim_source_system` é uma dimensão de primeira classe**, com vigência
   própria (SCD2), alimentada por `config/sources.yaml`: onda, `active_from`,
   `active_to`, países, `field_language`, `population_rule`,
   `has_enterprise_employee_id`.

3. **`is_system_of_record` é declarado por período**, em configuração, e marca
   qual observação vale quando mais de uma existe. A contagem correta vira um
   filtro explícito, e não um julgamento no momento da carga.

4. **Nenhuma agregação cruza sistemas sem declarar que os está cruzando.** Isso
   aparece como critério de aceite e como teste: somar headcount sem filtrar
   `is_system_of_record` tem que produzir duplicação no período de sobreposição
   de 2019, e um teste **falha se não produzir**, porque isso significaria que o
   grain está errado.

5. **Populações com definição incompatível não entram no mesmo fato.** A folha
   fica fora de `fact_headcount_snapshot` por dois motivos somados: 59% da
   população sem identidade resolvida, e uma definição própria de ativo. A
   comparação entre HRIS e folha continua onde já funciona, nas reconciliações
   da F5.

## Alternativas consideradas

1. **Grain pessoa × mês, escolhendo um sistema por precedência na carga.** Mais
   simples de consultar e apaga a sobreposição de 2019. O custo é alto e
   invisível: `DQ_RECON_005`, que mede o quanto os dois sistemas discordam
   durante a migração, perderia a matéria-prima, e a pergunta "quanto custou a
   migração" ficaria sem resposta.
2. **Grain pessoa × mês, com uma coluna dizendo de qual sistema veio.** Parece a
   mesma coisa e não é: se o sistema não está na chave, duas observações da
   mesma pessoa no mesmo mês violam a unicidade, e a carga tem que descartar uma
   delas de qualquer jeito.
3. **Tabelas separadas por sistema.** Preserva tudo e empurra a união para todo
   consumidor, que passa a ter que saber as vigências de cor — exatamente o
   conhecimento tácito que o achado 1 da F5 mostrou não sobreviver.
4. **Incluir a folha no fato de headcount, com flag de população.** Traria 59% de
   linhas sem dono e misturaria duas definições de ativo na mesma coluna
   contável.

## Consequências

**Positivas**

- A sobreposição da migração de 2019 fica preservada e mensurável, em vez de
  resolvida por uma escolha que ninguém registrou.
- Comparabilidade vira estrutura: vigência e população de cada fonte são colunas,
  não convenção.
- Quando a onda 2 trouxer `PAYROLL_LATAM`, `ATS_LEGACY` e `COMPRAFACIL_ERP`, o
  modelo já sabe representar fontes com vigências diferentes.

**Negativas**

- Consulta ingênua duplica no período de sobreposição. Isso é deliberado e
  testado: a duplicação é ruidosa e detectável, enquanto a escolha silenciosa
  seria silenciosa.
- Um `join` a mais em toda consulta de headcount.
- `is_system_of_record` é mais uma declaração a manter em configuração, e
  declaração errada produz contagem errada.

**Riscos e mitigação**

- *Risco:* alguém materializar uma view "simplificada" já filtrada e ela virar a
  fonte de fato, reintroduzindo a escolha silenciosa por outro caminho.
  *Mitigação:* a view pode existir, desde que o filtro esteja no nome e a
  definição cite este ADR.

## Referências

- `docs/F6_analytical_model.md`, Partes II.8.1 e VII
- `docs/f5_validation_findings.md`, achado 1
- `config/sources.yaml`, `active_from`, `active_to`, `population_rule`
- `config/incidents.yaml`, `INC_2019_HRIS_MIGRATION`
- ADR-0003 (camadas), ADR-0022 (natureza da perda de confiança)
