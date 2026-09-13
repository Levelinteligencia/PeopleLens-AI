# ADR-0006: Tratamento de moeda e câmbio

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D6 (Technical Design v0.3)
- **Fase:** F0, vigora a partir da F6

## Contexto

A NOVAORA opera em cinco países com cinco moedas, e a prática de remuneração
difere: Chile e México trabalham com salário anual, os demais com mensal
(defeito D13). A janela de análise tem dez anos e inclui a Argentina, cujo
câmbio no período domina qualquer série convertida.

Além disso, `fact_compensation` traz `compa_ratio` calculado pela fonte, que já
é tratado como valor de origem versus recalculado (Technical Design seção 6.3,
aprovado).

## Decisão

1. **O salário em moeda local é o fato.** É o que a fonte entrega e é o que fica
   no analítico, com `currency` e `salary_period` explícitos.
2. **Normalização de período** (anual para mensal) acontece na camada
   standardized, é determinística e é registrada no lineage.
3. **`ref_exchange_rate` tem duas naturezas de taxa**, nunca misturadas:
   - `rate_type = 'analysis'`: taxa fixa por ano, usada em comparações entre
     países;
   - `rate_type = 'spot'`: taxa do mês, usada apenas para reconciliação com a
     folha.
4. **A regra mais importante:** compa-ratio e pay gap são **sempre** calculados
   com recorte de país. Compa-ratio é salário sobre o ponto médio da banda
   local, mesma moeda no numerador e no denominador, portanto adimensional.
   Pay gap dentro de país também. Isso torna os dois KPIs de remuneração mais
   relevantes **imunes a câmbio**, e reduz o raio de impacto desta decisão a
   visões absolutas consolidadas, como custo total de folha em LATAM.

## Alternativas consideradas

1. **Taxa spot mensal para tudo.** Tecnicamente correta e analiticamente
   destrutiva: a série de salários da Argentina em USD viraria um gráfico de
   câmbio, e o número estaria "certo".
2. **Moeda constante de um único ano-base.** Remove a distorção e afasta demais
   da realidade financeira em dez anos.
3. **Só moeda local, sem conversão.** Honesto e insuficiente: impede a visão
   consolidada LATAM que a empresa obviamente teria.
4. **Local mais duas normalizações.** Escolhida.

## Consequências

**Positivas**

- Os KPIs de remuneração mais visíveis não dependem de premissa cambial.
- A existência de duas taxas com propósitos declarados é, por si, um bom
  exemplo de governança semântica.

**Negativas**

- `ref_exchange_rate` precisa ser mantida e versionada.
- Visões consolidadas em USD carregam uma premissa que precisa ser exibida
  junto do número.

**Riscos e mitigação**

- *Risco:* alguém usar `spot` numa comparação histórica. *Mitigação:* o
  contrato do KPI declara qual `rate_type` ele usa, e o teste falha se um KPI
  de comparação entre países referenciar `spot`.

## Referências

- Technical Design v0.3, seções 6.3 e 18 (D6)
- `config/generation.yaml`: bloco `compensation`
- `config/defects.yaml`: D13, D14, D20
