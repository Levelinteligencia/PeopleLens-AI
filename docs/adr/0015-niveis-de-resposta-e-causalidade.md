# ADR-0015: Níveis de resposta e proibição de causalidade sem evidência

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** Technical Design v0.3, seções 11.4 e 17 (R11)
- **Fase:** F0, vigora a partir da F7

## Contexto

O princípio 9 da Especificação pede que o projeto diferencie fato, cálculo e
interpretação. Ao desenhar o contrato de KPI ficou claro que falta um quarto
nível, e que ele é o mais perigoso: **causalidade**.

O modo de falha mais caro de um sistema de analytics com IA não é errar a
conta, é acertar a conta e errar a frase. "O turnover subiu porque o
engajamento caiu" passa por qualquer revisão, vai para o comitê, vira
iniciativa e orçamento. Se a relação não se sustenta, o custo não é um número
errado no dashboard, é uma decisão organizacional errada.

Em dados de RH isso é especialmente delicado, porque quase toda associação
forte tem confundidor óbvio: área com turnover alto costuma ter tenure média
baixa, nível mais júnior, mais lojas e gestores mais novos, tudo junto.

## Decisão

Quatro níveis de resposta, declarados por KPI no contrato, e cada resposta do
PeopleLens carrega a etiqueta do nível em que opera.

| Nível | O que é | Base | Padrão |
|---|---|---|---|
| FATO | o valor observado ou calculado | dado governado mais fórmula do contrato | sempre permitido |
| CONTEXTO | comparação ou associação que situa o fato | mesmo dado governado, base de comparação declarada | permitido, com base declarada |
| INTERPRETAÇÃO | leitura qualificada do fato | regra de negócio governada, com dono | só se houver regra registrada |
| CAUSALIDADE | atribuição de causa | estudo com desenho, controles e limitações | **negado por padrão** |

Campos no contrato de KPI:

```yaml
response_levels:
  fact:    {enabled: true}
  context:
    enabled: true
    comparison_basis: [previous_period, same_period_previous_year, peer_business_unit]
    correlations_allowed: true
  interpretation:
    enabled: true
    owner: People Analytics
    rules:
      - rule_id: TURNOVER_BAND_RETAIL_2026
        statement: acima de 12% no semestre está fora da banda de tolerância
        source: Política de People Analytics 2026
        valid_from: 2026-01-01
  causality:
    enabled: false
    reason: nenhum estudo causal registrado para este KPI
    evidence: []
```

Quando houver estudo, o nível é liberado com a evidência declarada: `study_id`,
`question`, `design`, populações de tratamento e controle, `controls`, `effect`,
`interval`, `limitations`, `owner` e `approved_at`.

### As cinco regras

1. Toda resposta declara em que nível opera. Níveis não se misturam na mesma
   frase.
2. Associação vive em CONTEXTO e é sempre nomeada como associação. "Porque",
   "causou", "levou a", "impactou" e "explica" não aparecem em resposta de
   nível CONTEXTO.
3. INTERPRETAÇÃO só existe com regra registrada no contrato, e a resposta cita
   a regra e o dono. A IA não inventa banda, meta nem limiar, e não usa
   benchmark de mercado emprestado.
4. CAUSALIDADE é negada por padrão, e a negação é **útil**: em vez de só
   recusar, o sistema diz o que seria necessário para responder.
5. A escada de asserção é limitada pelo trust score. Em LIMITED, CONTEXTO sai
   com ressalva e INTERPRETAÇÃO é bloqueada. Em BLOCKED, nenhum nível responde.

A regra 5 amarra as duas réguas do projeto: quanto pior o dado, menos longe o
sistema se permite ir na escada de afirmação.

## Alternativas consideradas

1. **Manter os três níveis da Especificação.** Deixa causalidade num vácuo, e
   vácuo em sistema de IA é preenchido por fluência.
2. **Proibir correlação junto com causalidade.** Descartada: associação é fato
   sobre os dados e é informação legítima. O problema é o verbo, não a
   estatística.
3. **Liberar causalidade com aviso textual ("isto não é causa").** Descartada:
   o aviso não sobrevive ao copiar e colar para o slide.
4. **Liberar causalidade por confiança do modelo.** Descartada: confiança do
   modelo não é evidência sobre o mundo.

## Consequências

**Positivas**

- Fecha o princípio 9 com o nível que faltava.
- A recusa vira demonstração, não limitação, e responde diretamente à pergunta
  obrigatória "por que você não consegue responder essa pergunta?".
- Junto com o ADR-0007, dá dois tipos distintos de recusa: por
  confidencialidade e por ausência de evidência.

**Negativas**

- O PeopleLens vai parecer menos inteligente que um assistente genérico em
  algumas perguntas, porque o genérico responde "porque" com fluência.
  Consideramos isso o comportamento correto e um ponto de apresentação.
- Escrever as regras de interpretação por KPI é trabalho de People Analytics,
  não de engenharia, e depende de alguém decidir bandas e metas.

**Riscos e mitigação**

- *Risco:* vazamento de linguagem causal na camada de geração de texto.
  *Mitigação:* teste que verifica ausência dos verbos proibidos em respostas de
  nível CONTEXTO.
- *Risco:* o gerador embutir correlações (por exemplo engajamento e turnover em
  `config/generation.yaml`) e alguém tratá-las como causa descoberta.
  *Mitigação:* o próprio arquivo declara que são associações embutidas, e o
  notebook de avaliação nunca as apresenta como achado.

## Referências

- Technical Design v0.3, seções 11.4 e 17 (R11)
- Especificação do Universo v1.0, princípio 9, seções 27 e 29
- ADR-0007 (recusa por confidencialidade), ADR-0011 (trust score por recorte)
