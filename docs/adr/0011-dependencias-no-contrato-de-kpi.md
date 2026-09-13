# ADR-0011: Dependências declaradas no contrato de KPI

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D11 (Technical Design v0.3)
- **Fase:** F0, vigora a partir da F7

## Contexto

A seção 23 da Especificação exige que cada KPI tenha `trust_status` e
`quality_score`. Para que esses valores sejam calculáveis, e não escolhidos, é
preciso saber **de quais checks de qualidade e de quais mapeamentos** cada KPI
depende.

O mesmo vale para lineage: responder "de onde veio esse número" exige uma
cadeia declarada, não inferida.

## Decisão

Acrescentar dois campos ao contrato de KPI (`src/analytics/kpis/<kpi>.yaml`):

```yaml
depends_on_checks:   [DQ_TERM_001, DQ_TERM_004, DQ_HC_002, DQ_RECON_001]
depends_on_mappings: [ref_department_mapping, ref_termination_reason_mapping]
```

Com eles, o trust score passa a ser calculável:

```
quality_score(kpi, recorte) =
    média ponderada do pass rate dos checks em depends_on_checks, no recorte
  x (1 - taxa de UNMAPPED nos campos de depends_on_mappings, no recorte)
```

O `kpi_catalog` continua sendo **gerado** a partir dos YAML, nunca digitado.

Proteção obrigatória: um teste falha se existir um check que **não é consumido
por nenhum KPI** e que também não está marcado como `observability_only`. Sem
esse teste, o grafo de dependências apodrece em silêncio conforme novos checks
forem criados.

## Alternativas consideradas

1. **Trust score global por dataset.** Todos os KPIs que leem
   `fact_termination` teriam o mesmo score. Grosseiro demais: um KPI que usa
   apenas `termination_date` não deveria ser penalizado por problema em
   `termination_reason`.
2. **Atribuir trust score manualmente por KPI.** Vira opinião com aparência de
   métrica, e desatualiza no primeiro mês.
3. **Inferir a dependência analisando o SQL do KPI.** Elegante e frágil:
   descoberta automática de linhagem por parsing erra com CTE, view e função, e
   o erro é silencioso.
4. **Declaração explícita.** Escolhida. Mais verbosa, e verificável.

## Consequências

**Positivas**

- Transforma lineage e trust score de conceito em código executável.
- Torna a pergunta "como esse KPI foi calculado?" respondível sem trabalho
  adicional, porque a resposta já está declarada.
- Permite trust score **por recorte** e não só global (ver ADR-0015 e Technical
  Design R7).

**Negativas**

- Cada novo check precisa ser conectado a KPIs, o que é manutenção contínua.
- Declaração pode divergir do SQL real se ninguém verificar, daí o teste.

**Riscos e mitigação**

- *Risco:* declaração incompleta inflar o trust score. *Mitigação:* além do
  teste de check órfão, um teste que confere se todas as tabelas referenciadas
  no SQL do KPI têm pelo menos um check declarado.

## Referências

- Technical Design v0.3, seções 11.2, 11.3 e 18 (D11)
- Especificação do Universo v1.0, seções 20, 22 e 23
