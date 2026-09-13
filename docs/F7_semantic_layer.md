# F7 — SPEC da Semantic Layer, KPI Catalog e Trust Layer (v1.0)

**Status: SPEC, aguardando aprovação. Nada implementado.**

Define o contrato semântico entre People Analytics, os dados e a IA. É a camada
L4 do ADR-0003, entre o modelo analítico (L3, F6) e o MCP.

> Princípio central, na ordem em que as responsabilidades se encadeiam:
> **People Analytics define e governa os KPIs. A camada analítica calcula. A
> Semantic Layer certifica e descreve. O MCP expõe capacidades controladas. A IA
> interpreta.** A IA não calcula KPI sobre RAW nem sobre tabela intermediária.

---

## Parte I — Base factual

### 1. O que a F7 herda

| De onde | O quê |
|---|---|
| F3–F5 | 87 checks, 7 classes de achado, trust score com perda atribuída por classe |
| F4 | governança de exceções e identidade; 57 mapeamentos e 1.845 identidades em aberto |
| F5 | 18 contratos de KPI com `depends_on_checks` e `depends_on_mappings` derivados do catálogo |
| F6 | 15 tabelas L3, 5.030 pessoas analíticas, proveniência governada, membros reservados |
| ADR-0015 | quatro níveis de resposta, causalidade negada por padrão |
| ADR-0023 | calibragem por recorte fino, **bandas preservadas** |

### 2. O que os dados da L3 sustentam, verificado

Levantamento sobre as tabelas construídas, não sobre a declaração:

| Família | Situação | Evidência |
|---|---|---|
| Headcount, FTE, tenure, span of control | **completa** | `fact_headcount_snapshot`, 130.817 linhas, com gestor e FTE |
| Turnover (contagem) | **completa** | `fact_termination`, 2.667 |
| Turnover voluntário, attrition regrettable | **impossível** | nenhuma fonte da onda 1 tem motivo de desligamento (G-01) |
| Hiring volume | **parcial** | exige `origin = CONTRATACAO`: 1.499 de 5.030 pessoas |
| Time to fill, time to hire, offer acceptance | **completa** | `fact_requisition` e `fact_application` |
| DEI (gênero, raça e cor, PcD) | **completa**, com não declaração visível | `dim_employee`, membro `-4` |
| Performance | **completa, com ressalva** | `scale_type` separa a escala de 2021 |
| Mobilidade interna, promoção | **bloqueada** | `movement_type` sem DE/PARA aprovado (gap da F6) |
| Compa-ratio, pay gap | **bloqueada** | **não existe banda salarial fora da camada de verdade** |

### 3. Dois bloqueios que precisam ser nomeados

**`movement_type` sem mapeamento aprovado.** `fact_movement` carrega dois
vocabulários simultâneos: `Promotion`, `Transfer`, `Lateral Move`, `Demotion`,
`Reorganization` do HRIS corporativo, e `PROMOCAO`, `TRANSFERENCIA`,
`MOV LATERAL`, `REBAIXAMENTO` do legado. Contar promoções hoje daria 491 ou 601
dependendo de quem escreveu a consulta. Rota correta: a fila de exceções da F4.

**Banda salarial não existe fora da camada de verdade.** `ref_salary_band` está
em `data/synthetic/truth/`, e `data/reference/` tem apenas os cinco mapeamentos
de DE/PARA. `COMP_PLAN` é onda 2. Sem ponto médio de banda, compa-ratio não é
calculável, e lê-lo da camada de verdade é exatamente o que o teste F-13 da F6
proíbe.

Nenhum dos dois é contornável pela F7. Os dois viram **status de KPI**, não
cálculo aproximado.

---

## Parte II — KPI Catalog

### 4. Escopo da v1.0: seis KPIs certificáveis

Os 18 contratos da F5 permanecem. A F7 acrescenta `status` a cada um, e
**certifica seis**, escolhidos porque cada um demonstra um mecanismo diferente
da camada — não para aumentar cobertura.

| KPI | O que demonstra |
|---|---|
| `headcount` | o caminho feliz: grain pessoa × mês × sistema, recorte fino, trust alto |
| `turnover_rate` | KPI de razão, com numerador e denominador de fatos diferentes |
| `women_in_leadership` | DEI, n mínimo de privacidade e não declaração visível no denominador |
| `hiring_volume` | proveniência limitando confiança: só conta `origin = CONTRATACAO` |
| `time_to_fill` | grain que **não é pessoa**: a requisição |
| `internal_mobility_rate` | KPI **bloqueado por pendência de mapeamento**, e por que isso é a resposta certa |

Os outros doze ficam `DECLARED` ou `BLOCKED`, com o motivo registrado. Um KPI
declarado e não certificado continua consultável, e a resposta diz o que ele é.

### 5. Contrato de KPI, campos

Extensão do contrato da F5. Os quatro campos existentes (`depends_on_checks`,
`depends_on_mappings`, `minimum_n`, `response_levels`) **não mudam**.

| Campo | Obrigatório | Observação |
|---|---|---|
| `kpi_id` | sim | imutável; muda o id, é outro KPI |
| `name`, `description` | sim | linguagem de negócio, sem nome de tabela |
| `business_definition` | sim | **novo**: a frase que People Analytics assina |
| `formula` | sim | expressão sobre medidas e dimensões da L3, nunca SQL bruto |
| `grain` | sim | **estruturado**: lista de dimensões, não texto livre |
| `population` | sim | **novo**: quem entra no denominador, declarado |
| `period_grain` | sim | `mes`, `trimestre`, `ano` ou `ciclo` |
| `period_coverage` | sim | **novo**: janela em que o KPI tem dado, derivada da L3 |
| `allowed_dimensions` | sim | **novo**: recorte fora daqui é recusa, não erro |
| `filters` | sim | **novo**: filtros fixos, sempre aplicados |
| `exclusions` | sim | **novo**: o que sai, e por quê (membros reservados inclusive) |
| `source_tables` | sim | **novo**: tabelas da L3; nenhuma outra camada é acessível |
| `owner` | sim | **novo**: pessoa ou área que assina a definição |
| `version` | sim | **novo**: semântico, com as regras da seção 15 |
| `status` | sim | **novo**: `DRAFT`, `DECLARED`, `CERTIFIED`, `BLOCKED`, `DEPRECATED` |
| `certification` | sim | **novo**: requisitos de DQ e trust, e bloqueadores |
| `depends_on_checks` | derivado | inalterado, da F5 |
| `depends_on_mappings` | sim | inalterado, da F5 |
| `minimum_n` | sim | inalterado; ADR-0007 |
| `response_levels` | sim | inalterado; ADR-0015 |
| `interpretation_rules` | não | **novo**: banda, meta ou limiar, com dono e data; sem isso, INTERPRETATION é bloqueado |
| `causal_studies` | não | **novo**: estudos registrados; sem isso, CAUSALITY é negado |

### 6. Os seis contratos, em resumo

#### `headcount` — CERTIFIED

| | |
|---|---|
| definição de negócio | pessoas ativas no fim do período, contadas uma vez por pessoa |
| fórmula | `count_distinct(party_key)` em `fact_headcount_snapshot` onde `is_month_end` e `is_system_of_record` |
| grain | `mes × pais × business_unit × departamento` |
| população | pessoas observadas pelo sistema de registro do período |
| dimensões permitidas | país, business unit, departamento, nível, gênero, origem, sistema-fonte |
| filtros fixos | `is_system_of_record = true` |
| exclusões | linhas em quarentena (nunca entram na L3); membro `-1` de `dim_employee` |
| fonte | `fact_headcount_snapshot`, `dim_employee`, `dim_organization`, `dim_calendar` |
| n mínimo | 5 |

O filtro fixo não é detalhe: sem ele, a sobreposição de 2019 duplica. Ele é
**do KPI**, e não do consumidor, exatamente para que o consumidor não precise
saber que houve uma migração.

#### `turnover_rate` — CERTIFIED

| | |
|---|---|
| definição | desligamentos no período sobre a média do headcount de início e fim |
| fórmula | `count(fact_termination) / avg(headcount_inicio, headcount_fim)` |
| grain | `ano × pais × business_unit` |
| exclusões | **sem recorte por voluntariedade**: não há motivo de desligamento na onda 1 |
| n mínimo | 20 |

A exclusão é a parte importante: `turnover_rate` responde, e
`voluntary_turnover` **não existe no catálogo**. Um KPI que não pode ser
calculado não entra como KPI vazio.

#### `women_in_leadership` — CERTIFIED

| | |
|---|---|
| definição | share de mulheres entre as pessoas em níveis de liderança |
| fórmula | `count(gender = Female e is_leadership) / count(is_leadership)` |
| grain | `mes × pais` |
| população | denominador é quem está em nível de liderança **e declarou gênero** |
| exclusões | membro `-4` (não informado) sai do numerador **e do denominador**, e a taxa de não declaração é reportada junto |
| n mínimo | 20 |

Excluir a não declaração dos dois lados e reportar a taxa é o que impede o
número de parecer melhor do que é. Penalizar a não declaração no trust score
continua proibido (ADR-0022).

#### `hiring_volume` — CERTIFIED com cobertura declarada

| | |
|---|---|
| definição | pessoas que entraram na empresa por contratação no período |
| fórmula | `count(fact_workforce_entry)` onde `dim_origin.is_hire = true` |
| exclusões | `AQUISICAO_*` e `INDETERMINADA` **nunca contam como contratação** |
| cobertura | 1.499 de 5.030 pessoas têm origem determinada como contratação |

É o KPI que demonstra proveniência virando confiança: a resposta vem com a
cobertura, e a cobertura sobe conforme a fila de identidade do ATS for
trabalhada. Contar `INDETERMINADA` aqui é o caso de falha FC-09.

#### `time_to_fill` — CERTIFIED

| | |
|---|---|
| definição | dias entre a abertura da requisição e a admissão |
| fórmula | `median(days_to_fill)` em `fact_requisition` onde o marco de admissão ocorreu |
| grain | `trimestre × business_unit` |
| exclusões | requisições com `date_sk_hire = -5` (ainda não ocorreu) e status `Cancelled` |

Demonstra que nem todo KPI tem grain de pessoa, e que marco não atingido é um
membro nomeado e não um nulo a ignorar.

#### `internal_mobility_rate` — BLOCKED

| | |
|---|---|
| definição | movimentações internas sobre headcount médio |
| bloqueador | `movement_type` sem DE/PARA aprovado: dois vocabulários coexistem |
| resposta | recusa explicando o bloqueio e o que o resolve |

Entra no catálogo **bloqueado** de propósito. Um KPI que hoje daria 491 ou 601
dependendo de quem escreveu a consulta não é um KPI com qualidade baixa: é um
KPI sem definição fechada.

### 7. Os outros doze

| Status | KPIs | Motivo |
|---|---|---|
| `DECLARED` | `fte`, `tenure`, `span_of_control`, `gender_representation`, `black_representation`, `pcd_representation`, `performance_distribution`, `time_to_hire`, `offer_acceptance_rate` | calculáveis; fora do escopo de certificação da v1.0 |
| `BLOCKED` | `promotion_rate` | depende de `movement_type` |
| `BLOCKED` | `compa_ratio`, `pay_gap` | **não existe banda salarial fora da camada de verdade**; `COMP_PLAN` é onda 2 |

---

## Parte III — Semantic Layer

### 8. O que o consumidor nunca precisa saber

Nome físico de tabela, caminho de join, regra de cálculo, código técnico,
detalhe do RAW, qual sistema é o de registro em cada período, qual membro
reservado significa o quê. Tudo isso vive no contrato.

### 9. A tradução, em três passos

```
pergunta em linguagem natural
        │
        ▼  a IA propõe  (único passo com latitude)
consulta semântica          {kpi_id, period, dimensions[], filters[], compare?}
        │
        ▼  a camada valida contra o contrato  (determinístico)
consulta governada          tabelas L3, filtros fixos, membros excluídos
        │
        ▼  a camada executa e certifica
resposta                    valor + trust + nível + trace
```

**A saída da IA é um objeto de consulta, nunca SQL e nunca um número.** É a
fronteira que impede a IA de calcular sobre RAW ou sobre tabela intermediária, e
está proposta como ADR-0028.

### 10. A consulta semântica

```yaml
kpi: headcount
period: {grain: mes, from: 2025-01, to: 2025-12}
dimensions: [pais, departamento]
filters:
  - {dimension: pais, in: [BR, AR]}
compare: {type: periodo_anterior}   # opcional
```

Não tem tabela, não tem join, não tem coluna. O que ela tem é o vocabulário do
contrato.

### 11. Vocabulário governado

`config/semantic/vocabulary.yaml` mapeia o termo de negócio para o membro da
dimensão. Declarado, versionado, e **termo desconhecido é recusa e não palpite**
— a mesma regra do DE/PARA, pelo mesmo motivo: um termo mapeado errado é
invisível e um termo não mapeado é visível.

| Termo | Resolve para |
|---|---|
| "liderança", "gestores" | `dim_job_level.is_leadership = true` |
| "mulheres" | `dim_employee.gender = Female` |
| "Brasil" | `dim_organization.country = BR` |
| "gente que veio da VivaMarket" | `dim_origin.code = AQUISICAO_VIVAMARKET` |
| "contratações" | `dim_origin.is_hire = true` |

Sinônimos entram por decisão, não por similaridade — o achado 3 da F4 já mostrou
o que acontece quando similaridade vira evidência.

### 12. Validação da consulta

Sete verificações, todas determinísticas, antes de qualquer execução:

1. o `kpi_id` existe e seu `status` permite resposta;
2. toda dimensão pedida está em `allowed_dimensions`;
3. todo termo de filtro existe no vocabulário;
4. o período pedido está dentro de `period_coverage`;
5. o grain do período é compatível com `period_grain`;
6. a população resultante atinge `minimum_n`;
7. as dependências de mapeamento do KPI não têm pendência bloqueante.

Falhou qualquer uma, a resposta é uma **recusa explicada**, com o que seria
necessário para responder. Recusa é parte do produto, e não uma exceção.

---

## Parte IV — Trust Layer

### 13. Composição do trust de uma resposta

A F5 já calcula trust de dado. A F7 acrescenta a dimensão que faltava:
**confiança de governança**. As duas se compõem, e a menor manda.

```
trust_dado        = 1 − perda ponderada dos checks das dependências, no recorte  (F5)
trust_governanca  = teto do status do KPI                                        (F7)
trust_resposta    = min(trust_dado, trust_governanca)
```

| Status do KPI | Teto de confiança | Teto de nível de resposta |
|---|---|---|
| `CERTIFIED` | sem teto | INTERPRETATION com regra; CAUSALITY com estudo |
| `DECLARED` | LIMITED | CONTEXT |
| `BLOCKED` | — | recusa |
| `DEPRECATED` | LIMITED | CONTEXT, só período histórico |
| `DRAFT` | — | recusa |

**Um KPI não certificado nunca responde como CERTIFIED**, por mais limpo que
esteja o dado. Isso é decisão de governança e não de qualidade, e está proposto
como ADR-0029.

### 14. Critérios objetivos de trust por KPI × recorte

As bandas da F5 **não se movem** (ADR-0023, DQ-04): `CERTIFIED ≥ 0,95`,
`LIMITED ≥ 0,70`, piso de pendência 0,40. A calibragem é por recorte fino, como
decidido.

| Critério | Efeito |
|---|---|
| algum check `BLOCKER` das dependências reprovando no recorte | `BLOCKED` |
| `trust_dado` abaixo do piso de pendência | `BLOCKED` |
| perda vinda **só** de pendência, acima do piso | no máximo `LIMITED`, motivo declarado |
| população abaixo de `minimum_n` | não é trust: é supressão por privacidade, em campo próprio |
| nenhum check aplicável ao recorte | `INDETERMINADO`, nunca `CERTIFIED` |
| cobertura de população abaixo do declarado no contrato | rebaixa para `LIMITED`, com a cobertura na resposta |

O último é novo da F7 e é o que faz `hiring_volume` sair como `LIMITED`: a
cobertura de origem é 30%, e a resposta diz isso.

**Nenhum score artificial.** Todo componente vem de check executado, de cobertura
medida ou de status declarado. Onde não há evidência, o resultado é
`INDETERMINADO` e não um número.

---

## Parte V — Response Contract

### 15. Os quatro níveis e a evidência de cada um

| Nível | O que afirma | Evidência necessária |
|---|---|---|
| **FACT** | o número | KPI com status que permita; trust ≥ LIMITED; n ≥ mínimo; dimensões permitidas; período coberto |
| **CONTEXT** | o número comparado | tudo do FACT, mais uma base de comparação declarada (outro período, outro recorte ou a média da população) que seja **ela própria respondível** |
| **INTERPRETATION** | se é bom ou ruim | tudo do CONTEXT, mais uma regra em `interpretation_rules` com dono e data de aprovação |
| **CAUSALITY** | por quê | **negado por padrão**; exige estudo em `causal_studies` com desenho, tratamento, controle, efeito, intervalo e limitações |

### 16. As cinco regras de redação

Reafirmam o ADR-0015 e valem como contrato de saída:

1. toda resposta declara em que nível opera; níveis não se misturam na mesma
   frase;
2. associação vive em CONTEXT e é sempre nomeada como associação. "Porque",
   "causou", "levou a", "impactou" e "explica" não aparecem em CONTEXT;
3. INTERPRETATION cita a regra e o dono. A IA não inventa banda, meta ou limiar,
   e não usa benchmark de mercado emprestado;
4. CAUSALITY é negada de forma **útil**: a recusa diz o que seria necessário
   para responder;
5. a escada é limitada pelo trust: em `LIMITED`, CONTEXT sai com ressalva e
   INTERPRETATION é bloqueado; em `BLOCKED`, nenhum nível responde.

### 17. Forma da resposta

```yaml
level: FACT
value: 1942
unit: pessoas
kpi: {id: headcount, version: 1.0.0, status: CERTIFIED, owner: people-analytics}
scope: {period: 2026-06, dimensions: {pais: BR}}
trust: {status: CERTIFIED, score: 0.9986, motivo: PENDENCIA,
        perda_por_erro: 0.0002, perda_por_pendencia: 0.0013}
coverage: {population_covered: 1.0, identity_resolved: 1.0}
caveats:
  - "8 registros ficaram fora do analítico por falha de conversão de data"
trace_id: ...
```

`caveats` não é decorativo: é onde a pendência que não derrubou o trust ainda
aparece para quem lê.

---

## Parte VI — Lineage e explicabilidade

### 18. "Como o PeopleLens chegou a essa resposta?"

A resposta é um `trace`, navegável em seis degraus, cada um já existente numa
camada anterior:

```
resposta          valor, recorte, nível, trust
   ↓
KPI               id, versão, dono, status, data de certificação
   ↓
definição         business_definition, fórmula, população, filtros, exclusões
   ↓
regra             checks que compuseram o trust; mapeamentos usados; membros excluídos
   ↓
tabela analítica  tabelas da L3, linhas consideradas, filtros fixos aplicados
   ↓
fonte             _row_id → transformation_log → valor original, sistema, regra → arquivo bruto
```

Nada disso é construído pela F7: os cinco degraus inferiores já existem em
`data_lineage`, `analytical_lineage`, `transformation_log`,
`data_quality_results` e nos contratos. A F7 **encadeia**, e a única coisa nova
é o registro da consulta que produziu a resposta.

### 19. `semantic_query_log`

Uma linha por resposta: `trace_id`, pergunta original, consulta semântica
resolvida, KPI e versão, recorte, trust, nível, caveats, `run_id` da L3
consultada.

Existe por dois motivos. Reproduzir uma resposta meses depois exige saber a
versão do KPI e a execução da L3 que a produziram. E uma recusa também é
registrada — sem isso, ninguém descobre que a mesma pergunta é recusada toda
semana pelo mesmo mapeamento pendente.

---

## Parte VII — Governança

### 20. Ciclo de vida do KPI

Mesma forma da governança de mapeamento da F4, e de propósito: reusar o padrão
já aprovado em vez de inventar outro.

```
DRAFT → DECLARED → CERTIFIED → DEPRECATED
                 ↘ BLOCKED (bloqueador técnico ou de definição)
```

| Transição | Exige |
|---|---|
| `DRAFT → DECLARED` | dono, definição de negócio, fórmula, grain, população |
| `DECLARED → CERTIFIED` | dependências de DQ sem check BLOCKER reprovando; mapeamentos sem pendência bloqueante; cobertura declarada; aprovação registrada com dono e data |
| `qualquer → BLOCKED` | bloqueador declarado, com o que o resolve |
| `CERTIFIED → DEPRECATED` | KPI substituto declarado; a versão antiga **continua consultável** para período histórico |

### 21. Versionamento

Semântico, e a regra que importa é a primeira:

| Mudança | Versão | Efeito |
|---|---|---|
| definição de negócio ou fórmula | **maior** | quebra comparabilidade; a versão anterior fica consultável e a resposta diz qual foi usada |
| filtro, exclusão ou dimensão permitida | menor | não quebra série |
| texto, descrição, dono | correção | nenhum |

**Mudar a fórmula de um KPI certificado não reescreve o passado.** A série
histórica calculada com a versão anterior continua reproduzível, e uma comparação
entre duas versões é recusada a menos que alguém declare que quer compará-las.

### 22. O que a IA não decide

Nenhuma decisão de negócio é inventada pela IA. Concretamente, a IA não:

- cria, altera ou versiona KPI;
- escolhe fórmula, população, filtro ou exclusão;
- aprova mapeamento, resolve identidade ou promove exceção;
- define banda, meta ou limiar;
- afirma causalidade;
- estima um número quando o dado não permite calculá-lo.

A IA traduz pergunta em consulta, e explica a resposta. As duas coisas são
verificáveis contra o contrato.

---

## Parte VIII — Arquitetura

### 23. Visão conceitual

```
pergunta
   │
   ▼
┌─────────────────────────────────────────────┐
│ SEMANTIC LAYER                              │
│  vocabulário → consulta semântica           │
│  validação contra o contrato                │
└───────────────┬─────────────────────────────┘
                │
      ┌─────────┴──────────┐
      ▼                    ▼
┌───────────────┐   ┌──────────────────┐
│ KPI CATALOG   │   │ TRUST LAYER      │
│ definição     │   │ DQ (F5) + status │
│ versão, dono  │   │ cobertura, n mín │
└───────┬───────┘   └────────┬─────────┘
        └──────────┬─────────┘
                   ▼
        ┌─────────────────────┐
        │ EXECUÇÃO GOVERNADA  │  sobre a L3, e só sobre a L3
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │ RESPONSE CONTRACT   │  nível, trust, caveats, trace
        └─────────────────────┘
```

### 24. Visão física

A física não precisa espelhar o conceitual, e aqui não espelha: catálogo e trust
são configuração mais função, não serviços.

| Componente conceitual | Forma física | Tecnologia |
|---|---|---|
| KPI Catalog | `config/kpis/*.yaml`, estendidos | YAML versionado no Git |
| Vocabulário | `config/semantic/vocabulary.yaml` | YAML versionado |
| Semantic Layer | `src/analytics/semantic/resolver.py` | Python, sem estado |
| Execução governada | `src/analytics/semantic/executor.py` | **DuckDB** sobre os Parquet da L3 (ADR-0009) |
| Trust Layer | `src/analytics/trust.py`, estendido para a L3 | Python, reusa a F5 |
| Response Contract | `src/analytics/semantic/response.py` | Python |
| Log de consultas | `data/governance/peoplelens_gov.db` | SQLite, onde as outras filas já vivem |

Sem tecnologia nova. DuckDB entra como camada de leitura, exatamente onde o
ADR-0009 previu desde a F0 e onde a F6 já o declarou.

Três schemas no DuckDB: `truth`, `analytical` e `semantic`. O último expõe
apenas views por KPI, com os filtros fixos já aplicados — de forma que mesmo
alguém consultando o DuckDB diretamente não consiga somar headcount sem o
sistema de registro.

---

## Parte IX — Failure cases

Oito casos, todos verificáveis, cada um com a recusa que o sistema deve produzir.

| # | Situação | Comportamento exigido |
|---|---|---|
| **FC-01** | KPI não certificado | responde no máximo em CONTEXT, e a resposta declara que o KPI não é certificado |
| **FC-02** | KPI `BLOCKED` (`internal_mobility_rate`) | recusa, nomeando o bloqueador e o que o resolve |
| **FC-03** | população incompleta (`hiring_volume` com 30% de cobertura) | responde com `LIMITED` e a cobertura explícita |
| **FC-04** | mapeamento pendente nas dependências | recusa ou `LIMITED`, conforme a pendência seja bloqueante; a exceção é nomeada |
| **FC-05** | identidade não resolvida onde o KPI exige | `LIMITED`, com a cobertura de identidade na resposta; nunca conta pessoa provisória como consolidada |
| **FC-06** | definição ambígua (`movement_type` com dois vocabulários) | recusa; dois vocabulários não produzem um número, produzem dois |
| **FC-07** | dimensão não permitida (compa-ratio por centro de custo) | recusa, dizendo por quê e o que responde no lugar |
| **FC-08** | período fora da cobertura (headcount em 2014) | recusa, informando a janela coberta |
| **FC-09** | contar `INDETERMINADA` ou `AQUISICAO_*` como contratação | proibido: `is_hire` é o único critério |
| **FC-10** | evidência insuficiente para causalidade | negação útil: diz que desenho de estudo responderia |
| **FC-11** | recorte abaixo do n mínimo | supressão por **privacidade**, com essa palavra, e não por qualidade |
| **FC-12** | comparar duas versões de um KPI sem declarar | recusa; mudança de fórmula quebra comparabilidade |

---

## Parte X — Riscos e gaps

| ID | Risco ou gap | Severidade | Tratamento |
|---|---|---|---|
| **R-01** | `movement_type` sem DE/PARA aprovado | **alta** | bloqueia 2 KPIs; rota é a fila da F4, não a F7 |
| **R-02** | banda salarial só na camada de verdade | **alta** | bloqueia compa-ratio e pay gap até a onda 2 |
| **R-03** | a IA propor consulta plausível e errada (KPI parecido, recorte parecido) | **alta** | validação determinística e recusa por vocabulário; a IA não escolhe o que não está declarado |
| **R-04** | vocabulário virar ponto de injeção de regra de negócio por sinônimo | média | sinônimo entra por decisão registrada, nunca por similaridade |
| **R-05** | 206 de 396 pares KPI × recorte sem check aplicável (F5) | média | vira `INDETERMINADO`, e a lacuna dimensiona a expansão do catálogo de checks |
| **R-06** | `minimum_n` passa a ser real pela primeira vez | média | até a F6 a população era contagem de linhas; agora é de pessoas, e mais respostas serão suprimidas |
| **R-07** | recorte fino multiplica o custo de cálculo do trust | baixa | a instrumentação da F4 mede antes de otimizar |
| **R-08** | `period_coverage` derivado da L3 pode mascarar buraco de carga | média | derivar da L3 **e** cruzar com `DQ_TIME_003`; mês sem dado é recusa, não zero |

---

## Parte XI — Acceptance criteria

### 25. Devem passar

| # | Critério |
|---|---|
| AC-01 | todo KPI do catálogo tem os campos obrigatórios da seção 5 preenchidos |
| AC-02 | `depends_on_checks` continua derivado do catálogo de checks, nunca digitado |
| AC-03 | todo KPI `CERTIFIED` tem dono, versão, data de aprovação e zero bloqueadores |
| AC-04 | `source_tables` de todo KPI referencia apenas tabelas da L3 |
| AC-05 | nenhuma consulta executada toca RAW, standardized ou conformed |
| AC-06 | toda consulta semântica válida é resolvível sem o consumidor nomear tabela, join ou coluna |
| AC-07 | dimensão fora de `allowed_dimensions` produz recusa, não erro técnico |
| AC-08 | termo fora do vocabulário produz recusa, nunca correspondência aproximada |
| AC-09 | `trust_resposta = min(trust_dado, teto do status)`, verificável |
| AC-10 | as bandas de trust da F5 permanecem inalteradas |
| AC-11 | recorte abaixo de `minimum_n` é suprimido por privacidade, em campo próprio |
| AC-12 | toda resposta declara nível, trust, cobertura e caveats |
| AC-13 | INTERPRETATION só sai com regra registrada, e cita a regra e o dono |
| AC-14 | CAUSALITY é negada sem estudo registrado, e a negação diz o que faltaria |
| AC-15 | todo `trace` navega da resposta até o `_row_id` da fonte |
| AC-16 | toda resposta e toda recusa ficam em `semantic_query_log` |
| AC-17 | mudança de fórmula gera versão maior e a anterior continua consultável |
| AC-18 | nenhuma regra de negócio nova foi introduzida sem sinalização explícita |

### 26. Devem falhar

| # | O que deve falhar |
|---|---|
| FC-01 a FC-12 | os doze casos da Parte IX, cada um como teste |
| FCx-13 | um KPI `CERTIFIED` cujo trust de dado seja `BLOCKED` responder em FACT |
| FCx-14 | somar headcount sem o filtro fixo de sistema de registro, via camada semântica |
| FCx-15 | a IA emitir SQL ou um número em vez de uma consulta semântica |
| FCx-16 | uma resposta sem `trace_id` |
| FCx-17 | um KPI `BLOCKED` produzir valor numérico de qualquer natureza |

---

## Parte XII — Decisões necessárias

| # | Decisão | Recomendação |
|---|---|---|
| **D7-01** | escopo de seis KPIs certificados na v1.0 | **aprovar**: cada um demonstra um mecanismo distinto, e cobertura não é o objetivo |
| **D7-02** | a saída da IA é consulta semântica, nunca SQL nem número (ADR-0028) | **aprovar**: é a fronteira que sustenta o princípio central |
| **D7-03** | certificação de KPI limita o nível de resposta, independente da qualidade do dado (ADR-0029) | **aprovar**: confiança de governança e de dado são coisas diferentes |
| **D7-04** | ciclo de vida e versionamento de KPI, com a versão anterior consultável (ADR-0030) | **aprovar**: mudar fórmula não pode reescrever a série histórica |
| **D7-05** | `internal_mobility_rate` e `promotion_rate` entram `BLOCKED` até `movement_type` ter DE/PARA | **aprovar**; a alternativa é escolher um vocabulário na consulta, que é regra de negócio inventada |
| **D7-06** | `compa_ratio` e `pay_gap` entram `BLOCKED` até haver banda salarial fora da camada de verdade | **aprovar**; ler a banda da verdade é o que o teste F-13 da F6 proíbe |
| **D7-07** | quem é o `owner` dos KPIs certificados | **precisa de você**: sugiro `people-analytics` como área, com nome de pessoa quando houver |
| **D7-08** | `women_in_leadership` exclui a não declaração do numerador **e** do denominador | **aprovar**, com a taxa de não declaração sempre reportada junto |
| **D7-09** | `hiring_volume` certificado com cobertura de 30%, ou declarado até a cobertura subir | **certificar com cobertura declarada**: é o KPI que demonstra proveniência virando confiança |
| **D7-10** | o schema `semantic` no DuckDB expõe apenas views com filtros fixos aplicados | **aprovar**: impede o erro mesmo para quem consulta o DuckDB direto |

---

## Parte XIII — ADRs propostos

Três, e só o que é decisão arquitetural nova.

| ADR | Assunto | Por que é novo |
|---|---|---|
| **0028** | a IA produz consulta semântica, nunca SQL nem número | nenhum ADR anterior define a fronteira entre IA e cálculo; o ADR-0016 trata do RAG, que é outra coisa |
| **0029** | certificação de KPI limita o nível de resposta | o ADR-0022 governa confiança de **dado**; confiança de **governança** é uma segunda dimensão, e a composição das duas é nova |
| **0030** | ciclo de vida e versionamento de KPI | o ADR-0011 define dependências do contrato, não o ciclo de vida nem o efeito de mudar uma fórmula sobre a série histórica |

O que **não** vira ADR, por já estar decidido: níveis de resposta e causalidade
(ADR-0015), bandas de trust (ADR-0023), DuckDB como camada de consulta
(ADR-0009), n mínimo (ADR-0007), dependências declaradas (ADR-0011), classe de
achado (ADR-0022).

---

**Nada implementado.** Sem código, sem MCP, sem agente, sem interface, sem
expansão do modelo analítico, sem alteração de threshold de DQ, sem commit.

## Parte XIV — Matriz KPI → DQ → Trust → Response Level

### 23. A matriz dos seis, com o trust de dado medido

Os números de `trust_dado` abaixo são a execução atual da F5 no recorte
`GLOBAL`, não estimativas. `trust_governanca` é o teto do status proposto nesta
SPEC. `trust_resposta` é o mínimo dos dois, pela regra da seção 13.

| KPI | Checks decl. / aval. | Mappings | `trust_dado` | motivo | Status proposto | `trust_governanca` | `trust_resposta` | Teto de nível |
|---|---|---|---|---|---|---|---|---|
| `headcount` | 47 / 34 | country, department | **0,9984** | PENDENCIA | `CERTIFIED` | sem teto | **CERTIFIED** | INTERPRETATION com regra |
| `turnover_rate` | 19 / 17 | country, department | **0,9911** | PENDENCIA | `CERTIFIED` | sem teto | **CERTIFIED** | INTERPRETATION com regra |
| `women_in_leadership` | 5 / 5 | gender, job_level | **0,9970** | PENDENCIA | `CERTIFIED` | sem teto | **CERTIFIED** | INTERPRETATION com regra |
| `hiring_volume` | 6 / 3 | country, department | **1,0000** | OK | `CERTIFIED` com cobertura | LIMITED por cobertura 30% | **LIMITED** | CONTEXT com ressalva |
| `time_to_fill` | 5 / 4 | department | **1,0000** | OK | `CERTIFIED` | sem teto | **CERTIFIED** | INTERPRETATION com regra |
| `internal_mobility_rate` | 3 / 3 | department | **0,9939** | PENDENCIA | `BLOCKED` | — | **recusa** | nenhum |

Nenhum dos seis tem `interpretation_rules` registrada hoje. Portanto, na prática,
**o teto efetivo da v1.0 é CONTEXT em todos**, e INTERPRETATION destrava
individualmente quando alguém assinar uma banda ou meta. CAUSALITY permanece
negada em todos, por ausência de estudo (ADR-0015).

### 24. As duas linhas que justificam o ADR-0029

| | `internal_mobility_rate` | `hiring_volume` |
|---|---|---|
| `trust_dado` | 0,9939 — **CERTIFIED** pela banda da F5 | 1,0000 — **CERTIFIED** pela banda da F5 |
| o que está errado | a **definição**: `Promotion` 491 e `PROMOCAO` 110, `Transfer` 480 e `TRANSFERENCIA` 92 convivem sem DE/PARA | a **cobertura**: 1.499 de 5.030 pessoas com origem determinada |
| quem resolve | People Analytics, decidindo o vocabulário | a fila de identidade do ATS |
| `trust_resposta` | recusa | LIMITED, com a cobertura na resposta |

Sem a dimensão de governança, os dois sairiam como `CERTIFIED` com trust acima
de 0,99. O primeiro devolveria 491 ou 601 conforme quem escreveu a consulta, com
cara de fato. É o modo de falha mais caro de uma camada semântica, e é o que a
composição `min()` impede.

O mesmo vale para `compa_ratio` (0,9959) e `pay_gap` (0,9937): trust de dado alto
sobre KPIs que **não são calculáveis fora da camada de verdade**. Ambos entram
`BLOCKED`.

### 25. A cobertura de checks é parte da matriz

`checks_declarados` e `checks_avaliados` divergem em quatro dos seis: `headcount`
declara 47 e avalia 34; `hiring_volume` declara 6 e avalia 3. A diferença são
checks que não se aplicam ao recorte ou que não rodaram. Isso **não** é perda de
trust — não há evidência de erro — e também não é confiança. Entra na resposta
como cobertura de verificação, e um recorte sem nenhum check aplicável sai como
`INDETERMINADO`, nunca `CERTIFIED` (seção 14).

### 26. Os outros doze, resumidos

| KPI | `trust_dado` | Status proposto | `trust_resposta` | Teto de nível |
|---|---|---|---|---|
| `fte` | 1,0000 | `DECLARED` | LIMITED | CONTEXT |
| `tenure` | 0,9995 | `DECLARED` | LIMITED | CONTEXT |
| `span_of_control` | 0,9958 | `DECLARED` | LIMITED | CONTEXT |
| `gender_representation` | 1,0000 | `DECLARED` | LIMITED | CONTEXT |
| `black_representation` | 1,0000 | `DECLARED` | LIMITED | CONTEXT |
| `pcd_representation` | 1,0000 | `DECLARED` | LIMITED | CONTEXT |
| `performance_distribution` | 1,0000 | `DECLARED` | LIMITED | CONTEXT |
| `time_to_hire` | 1,0000 | `DECLARED` | LIMITED | CONTEXT |
| `offer_acceptance_rate` | 1,0000 | `DECLARED` | LIMITED | CONTEXT |
| `promotion_rate` | 0,9993 | `BLOCKED` — `movement_type` | recusa | nenhum |
| `compa_ratio` | 0,9959 | `BLOCKED` — sem banda salarial fora da verdade | recusa | nenhum |
| `pay_gap` | 0,9937 | `BLOCKED` — sem banda salarial fora da verdade | recusa | nenhum |

Nove KPIs com dado bom respondendo em CONTEXT é desconfortável e é o efeito
pretendido: certificação é ato de governança, não consequência de um limiar.

---
