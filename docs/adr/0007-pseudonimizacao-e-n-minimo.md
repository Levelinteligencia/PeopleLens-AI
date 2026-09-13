# ADR-0007: Pseudonimização e supressão por n mínimo

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D7 (Technical Design v0.3)
- **Fase:** F0, vigora a partir da F6

## Contexto

`fact_engagement` traz `employee_id`. Tecnicamente funciona, e é um problema
real de governança: pesquisa de engajamento com identificação rastreável
destrói a confiança na própria pesquisa e, no Brasil, entra em terreno sensível
sob a LGPD.

O mesmo vale para `race_ethnicity` e `disability_flag`, que são autodeclarados
e cuja taxa de não declaração é alta por natureza (defeito D03).

## Decisão

1. **RAW permanece como a fonte entrega**, identificado. Anonimizar no RAW seria
   alterar o RAW e violaria o princípio 1.
2. **Camada analítica substitui `employee_id` por `respondent_pseudo_id`** em
   `fact_engagement`, mantendo os atributos de recorte necessários para
   análise.
3. **Camada semântica aplica supressão por n mínimo**, com `min_group_size = 5`
   parametrizado em `config/generation.yaml` e declarado por KPI no campo
   `minimum_group_size` do contrato.
4. Quando o recorte pedido fica abaixo do n mínimo, **a resposta não é um
   número, é uma recusa** que explica o motivo.
5. `Não informado` é **valor de primeira classe**, nunca imputado. KPIs de DEI
   reportam sobre a base de declarantes e **informam a taxa de não declaração
   junto do resultado**.

## Alternativas consideradas

1. **Manter `employee_id` até a camada semântica.** Mais simples e descartada
   pelo risco de governança.
2. **Anonimizar já no RAW.** Descartada por violar o princípio 1.
3. **n mínimo apenas em engajamento.** Descartada: os mesmos riscos valem para
   recortes de raça, cor e deficiência.
4. **Imputar `Não informado` pela distribuição conhecida.** Descartada com
   ênfase: imputar autodeclaração é inventar identidade de pessoas.

## Consequências

**Positivas**

- Produz o melhor caso de uso para a pergunta obrigatória da seção 27 da
  Especificação, "por que você não consegue responder essa pergunta?". A
  recusa por confidencialidade é mais convincente que a recusa por qualidade,
  porque é recusa **por princípio**.
- Interage com o defeito D03 de forma produtiva: com 24% a 35% de não
  declaração, o denominador de DEI vira um problema declarado, não escondido,
  e isso reforça a distinção entre fato e interpretação.

**Negativas**

- Recortes finos de engajamento ficam indisponíveis, o que é o comportamento
  correto e mesmo assim vai frustrar quem pedir.
- A pseudonimização impede alguns cruzamentos individuais entre engajamento e
  outros fatos; cruzamentos agregados continuam possíveis.

**Riscos e mitigação**

- *Risco:* reidentificação por combinação de recortes (cruzar país, área, nível
  e gênero até sobrar uma pessoa). *Mitigação:* o n mínimo é avaliado sobre o
  recorte final entregue, não sobre cada dimensão isolada.

## Referências

- Technical Design v0.3, seção 6.4
- Especificação do Universo v1.0, seções 14 e 27
- `config/generation.yaml`: `engagement.min_group_size`, bloco `demographics`
