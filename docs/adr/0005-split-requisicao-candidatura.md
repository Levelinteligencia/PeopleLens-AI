# ADR-0005: Separação de `fact_requisition` e `fact_application`

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D5 (Technical Design v0.3)
- **Fase:** F0, vigora a partir da F1

## Contexto

A Especificação define `fact_hiring` com grão declarado de "uma linha por
candidatura/processo", mas a lista de campos mistura dois grãos:

| Grão requisição | Grão candidatura |
|---|---|
| `requisition_id`, `position_id` | `candidate_id`, `application_date` |
| `opening_date`, `approval_date`, `posting_date` | `screening_date`, `interview_date` |
| `requisition_status`, `recruiter_id` | `offer_date`, `offer_accepted_flag`, `hire_date` |

Com funil médio de 11 candidaturas por vaga, cada requisição apareceria 11
vezes na tabela. Qualquer média de Time to Fill contaria a mesma vaga 11 vezes
e enviesaria o resultado na direção das vagas que receberam mais candidaturas,
que são justamente as mais fáceis de preencher. O indicador ficaria
sistematicamente otimista, e o erro seria invisível.

Esse é exatamente o tipo de erro que o projeto existe para denunciar.

## Decisão

Separar em duas tabelas físicas e manter `fact_hiring` como **view na camada
semântica**:

```
fact_requisition        grão: requisition_id
fact_application        grão: requisition_id x candidate_id
vw_hiring (semântica)   grão: contratação efetivada
```

Grãos declarados no `kpi_catalog`:

| KPI | Grão | Tabela base |
|---|---|---|
| Time to Fill | requisição | `fact_requisition` |
| Time to Hire | candidatura contratada | `fact_application` |
| Offer Acceptance Rate | oferta | `fact_application` |

Time to Fill = `hire_date - opening_date`, sobre `fact_requisition`.
Time to Hire = `hire_date - application_date`, sobre `fact_application`
restrito a `offer_accepted_flag = 1`.

Nenhuma das duas métricas confia nos valores calculados que a fonte entrega.

## Alternativas consideradas

1. **Tabela única no grão de candidatura, com campos de requisição repetidos.**
   É o desenho mais comum em exportação de ATS e a origem de uma classe inteira
   de erros de Talent Acquisition. Descartada pelo viés descrito acima.
2. **Tabela única no grão de requisição, com o funil colapsado em contagens.**
   Corrige o Time to Fill e destrói o resto: sem candidato não há Offer
   Acceptance Rate por pessoa, não há análise de `candidate_source`, e o
   defeito D15 (candidato duplicado) deixa de poder existir.
3. **Tabela única com coluna indicando o grão da linha.** Aparece em sistemas
   legados e é o pior dos mundos: toda consulta precisa filtrar pelo indicador,
   e quem esquecer soma coisas de naturezas diferentes.
4. **Duas tabelas mais view semântica.** Escolhida.

## Consequências

**Positivas**

- Time to Fill passa a ser calculado sobre ~33.300 linhas em vez de ~366.700,
  o que é ao mesmo tempo o argumento de performance e o de correção.
- Três KPIs ganham grão explícito e distinto entre si, que é o que o campo
  `grain` do `kpi_catalog` exige.
- O defeito D16 (requisição sem contratação, com pico de 40% em 2020) deixa de
  ser anomalia difícil de representar e vira simplesmente requisição sem
  candidatura aceita.
- É o exemplo mais didático do princípio 9 no projeto: Time to Hire e Time to
  Fill, tratados como sinônimos na maior parte das organizações, têm grãos,
  tabelas e respostas diferentes.

**Negativas**

- Diverge do formato em que a maioria dos ATS exporta, então a camada de
  ingestão precisa fazer o split explicitamente.
- Duas tabelas para manter em vez de uma.

**Riscos e mitigação**

- *Risco:* alguém consultar `fact_application` achando que é grão de
  requisição. *Mitigação:* teste que compara o grão declarado no YAML do KPI
  com o `GROUP BY` real do SQL, e falha na divergência (ADR-0011).

## Referências

- Technical Design v0.3, seção 6.2
- Especificação do Universo v1.0, seção 8 e princípio 9
- `config/defects.yaml`: D15, D16, D17
