# ADR-0013: Ferramenta de Data Quality, Great Expectations, Soda Core, Pandera ou runner próprio

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D13 (Technical Design v0.3)
- **Fase:** F0, vigora a partir da F5

> Este ADR foi pedido explicitamente pela Sam com comparação detalhada entre as
> quatro opções, por ser a única decisão do projeto em que a melhor escolha
> técnica e a melhor escolha de posicionamento profissional podem divergir.

## Contexto

O PeopleLens precisa executar cerca de 70 checks de qualidade distribuídos em
sete dimensões (Completeness, Validity, Consistency, Uniqueness, Referential
Integrity, Timeliness, Reconciliation), persistir os resultados em
`data_quality_results`, e usar esses resultados para calcular o trust score de
cada KPI **por recorte**.

O requisito que diferencia este projeto de um uso comum de ferramenta de DQ
está no ADR-0011: cada KPI declara `depends_on_checks`, e o trust score é uma
função do pass rate desses checks específicos, no recorte consultado. O check
não é um alarme, é **insumo de um contrato**.

Somado a isso, o ADR-0010 exige severidade por check com efeito diferenciado:
`BLOCKER` manda para quarentena, `CRITICAL` derruba trust score, `WARNING` e
`INFO` apenas observam.

## Requisitos de avaliação

| # | Requisito | Origem |
|---|---|---|
| R1 | Checks declarados em arquivo, não em código | R8, gerador declarativo |
| R2 | Identidade estável de check (`check_id` citável de fora) | ADR-0011 |
| R3 | Severidade por check com quatro efeitos distintos | ADR-0010 |
| R4 | Ligação check para KPI, consumível pelo contrato | ADR-0011 |
| R5 | Resultado por recorte, não só global | Technical Design R7 |
| R6 | Checks de reconciliação entre datasets diferentes | Especificação seção 26 |
| R7 | Execução sobre DuckDB e Parquet | ADR-0009 |
| R8 | Rodar sem infraestrutura, com um clone do repositório | ADR-0009 |
| R9 | Persistir no schema `data_quality_results` da Especificação | Especificação seção 18 |
| R10 | Reconhecimento de mercado (critério de posicionamento, não técnico) | contexto de portfólio |

## Comparação

| Requisito | Great Expectations | Soda Core | Pandera | Runner próprio |
|---|---|---|---|---|
| R1 declarativo | Sim, suites | Sim, SodaCL em YAML, o mais próximo do que queremos | Parcial, schema em código ou YAML | Sim, por construção |
| R2 identidade estável | Parcial, a expectation é identificada por tipo mais argumentos | Sim | Sim | Sim |
| R3 severidade em 4 níveis | Não nativo, daria para usar `meta` livre | Parcial, tem warn e fail, dois níveis | Não nativo | Sim |
| R4 ligação check para KPI | **Não** | **Não** | **Não** | Sim |
| R5 resultado por recorte | Parcial, exige modelar partição como batch | Parcial | Não | Sim |
| R6 reconciliação entre datasets | Limitado e desconfortável | Sim | **Fraco**, é validação de dataframe único | Sim |
| R7 DuckDB e Parquet | Sim | Sim | Sim, inclusive Polars | Sim |
| R8 sem infraestrutura | Pesado, muitas dependências transitivas | Médio | Leve | Leve |
| R9 schema da Especificação | Formato próprio, exige adaptador | Formato próprio, exige adaptador | Não persiste | Nativo |
| R10 reconhecimento | **Alto** | Médio | Baixo a médio | Nenhum, é código nosso |

### Leitura da comparação

**Great Expectations** tem o vocabulário mais amplo de expectations e o maior
reconhecimento de mercado, que é uma vantagem real num portfólio. O problema
não é qualidade da ferramenta, é o **modelo conceitual**: o GE pensa em
*expectation sobre dataset*. Ele não modela "este check alimenta o trust score
deste KPI". Essa ligação, que é o requisito central do projeto (R4), teria que
ser construída por cima do GE de qualquer forma. Ou seja, pagaríamos a
dependência pesada e ainda escreveríamos a parte difícil. Há ainda dois
agravantes: o histórico de redesenhos com quebra de compatibilidade da
ferramenta, que envelhece mal um repositório de portfólio, e o fato de os data
docs do GE competirem visualmente com a camada de trust score, que é onde está
a narrativa do projeto.

**Soda Core** é o caminho intermediário e o mais próximo do que o projeto quer:
checks declarados em YAML, suporte a reconciliação entre datasets, e dois
níveis de severidade nativos (warn e fail), que cobrem metade do R3. Perde nos
mesmos pontos: nada de R4, e R5 exigiria construção. E tem o pior dos dois
mundos no critério de posicionamento: ainda é uma dependência externa, e é
menos reconhecida no mercado brasileiro que o GE, então nem resolve o R10.

**Pandera** é leve, estável e boa naquilo que faz: validação de schema, ou
seja, Completeness, Validity e Uniqueness. Fraca justamente em Consistency e
Reconciliation, que exigem comparação entre datasets. E essas duas são as
dimensões mais interessantes deste projeto, porque são as que contam a história
de sistemas divergentes. Adotar Pandera cobriria as dimensões fáceis e deixaria
as difíceis para código próprio, que é o pior recorte possível.

**Runner próprio** atende todos os requisitos técnicos e perde o R10.

### Dimensionamento do runner próprio

Não é um projeto, é um módulo: ler YAML, executar SQL no DuckDB, comparar com
threshold, gravar em `data_quality_results` com severidade e recorte. Da ordem
de 200 a 300 linhas. Formato do check:

```yaml
check_id: DQ_REF_001
name: manager_id existe em dim_employee
dimension: Referential Integrity
severity: BLOCKER
dataset: fact_headcount_snapshot
grain: [snapshot_date, country]
threshold: {max_failure_rate: 0.02}
sql: |
  SELECT ... FROM ... LEFT JOIN ... WHERE m.employee_id IS NULL
consumed_by_kpis: [headcount, turnover_rate, span_of_control]
```

## Decisão

**Runner próprio**, com o ADR comparativo (este documento) como entregável
obrigatório da F0.

## Mitigação do risco de posicionamento

O risco do runner próprio não é técnico, é de triagem: currículo e repositório
passam por filtro de palavra-chave, e "Great Expectations" é uma delas. Três
mitigações, que resolvem o risco sem comprometer a arquitetura:

1. **Este ADR.** Numa entrevista técnica, a rejeição bem argumentada de uma
   ferramenta popular demonstra mais critério que a adoção dela. A pergunta
   "por que você não usou Great Expectations?" passa a ser a melhor pergunta
   possível, não a pior.
2. **Seção de ferramentas avaliadas no README**, citando as quatro opções. O
   termo existe no repositório, honestamente, no contexto certo.
3. **Vocabulário próximo ao do GE na especificação dos checks**
   (`expect_column_values_to_not_be_null`, `expect_table_row_count_to_be_between`),
   para que a familiaridade conceitual fique evidente na leitura do código.

## Consequências

**Positivas**

- Atende R1 a R9 sem adaptador.
- O motor de DQ vira assunto de conversa técnica em vez de configuração.
- Zero dependência adicional pesada.

**Negativas**

- Código nosso para manter e testar.
- Vocabulário de checks menor que o do GE: só teremos os checks que
  escrevermos.
- Nenhuma interface pronta de visualização de resultados.

**Riscos e mitigação**

- *Risco:* o runner crescer até virar uma ferramenta mal feita. *Mitigação:*
  escopo congelado em ler, executar, comparar e persistir. Qualquer coisa além
  disso (agendamento, alerta, UI) fica fora.
- *Risco:* triagem automatizada. *Mitigação:* as três acima.

## Quando reavaliar

Esta decisão deve ser revisitada se qualquer uma das condições ocorrer:

1. o número de checks passar de ~150, quando a manutenção do vocabulário
   próprio começa a pesar mais que a dependência;
2. o projeto precisar de execução distribuída ou agendada em produção;
3. alguma das ferramentas passar a modelar nativamente a ligação check para
   métrica governada, que é o requisito R4.

## Referências

- Technical Design v0.3, seções 10, 14 e 18 (D13)
- ADR-0010 (severidade), ADR-0011 (dependências no contrato de KPI)
- Especificação do Universo v1.0, seções 18 e 26
