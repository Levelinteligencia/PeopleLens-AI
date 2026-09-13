# F6: relatório de execução do modelo analítico

Modelo analítico L3 implementado conforme a SPEC v1.0. Perfil `dev` (escala
10%), seed `42`. RAW intacto, nenhuma inferência adicional, escopo não expandido.

---

## 1. Arquivos criados e alterados

### Criados

| Arquivo | O que é |
|---|---|
| `src/analytics/layer.py` | marca física de camada: `stamp`, `assert_layer`, `LayerError` |
| `src/analytics/model/keys.py` | chaves substitutas e catálogo de membros reservados |
| `src/analytics/model/origin.py` | regra de proveniência governada em três níveis (P1/P2/P3) |
| `src/analytics/model/dimensions.py` | as seis dimensões, incluindo SCD2 de `dim_employee` |
| `src/analytics/model/facts.py` | os sete fatos e a resolução de chaves estrangeiras |
| `src/analytics/model/build.py` | orquestrador da L3, manifesto, exclusões e lineage |
| `tests/analytical/test_model.py` | 38 testes: A-01 a A-17, F-01 a F-17 e proveniência |
| `docs/f6_analytical_model_report.md` | este relatório |

### Alterados

| Arquivo | Mudança | Decisão |
|---|---|---|
| `config/sources.yaml` | `determines_origin` nos 12 sistemas, `origin_vocabulary` e `system_of_record` por período | ADR-0026, ADR-0027 |
| `src/pipeline.py` | `analytical_ready` → `conformed_approved`; `check_provenance` passa a guardar três pares | D-02, ADR-0024 |
| `tests/pipeline/test_pipeline.py` | acompanha a renomeação | D-02 |
| `Makefile` | alvo `model`; `all` passa a incluir a L3 | — |
| `docs/adr/0024`, `0025` | emendas registradas na revisão da SPEC | diretrizes 1 e 3 |
| `docs/adr/0027` | novo: proveniência ≠ identidade | diretriz 1 |

## 2. O que foi construído

15 tabelas em `data/processed/analytical/`, todas com a coluna `layer`.

| Tabela | Linhas | Grain |
|---|---|---|
| `dim_calendar` | 4.201 | um dia |
| `dim_employee` | 17.121 | pessoa analítica × versão de atributos |
| `dim_organization` | 334 | unidade organizacional × versão |
| `dim_job_level` | 15 | código de nível (13 + 2 reservados) |
| `dim_origin` | 5 | classe de origem |
| `dim_source_system` | 13 | sistema-fonte × vigência |
| `fact_headcount_snapshot` | 130.817 | pessoa × mês × sistema observador |
| `fact_workforce_entry` | 5.919 | pessoa × data de entrada × sistema |
| `fact_termination` | 2.667 | pessoa × data de desligamento × sistema |
| `fact_movement` | 3.611 | uma movimentação observada |
| `fact_requisition` | 2.752 | uma requisição |
| `fact_application` | 31.110 | requisição × candidato |
| `fact_performance` | 14.909 | pessoa × ciclo |
| `fact_compensation` | 10.505 | pessoa × data de vigência |
| `analytical_exclusions` | 8 | um registro recusado |

**5.030 pessoas analíticas**, com média de 3,4 versões cada.

## 3. Proveniência: o resultado da diretriz 1

A regra em três níveis rende, sem resolver uma única identidade e sem inferir
nada por atributo:

| Origem | Pessoas | Regra | Evidência |
|---|---|---|---|
| `INDETERMINADA` | 2.736 (54,4%) | nenhuma se aplica | — |
| `CONTRATACAO` | 1.499 | P3 | candidatura no ATS que resultou em admissão |
| `POPULACAO_INICIAL` | 475 | P2 | admissão anterior a 2016-01-01 |
| `AQUISICAO_VIVAMARKET` | **320** | P1 | `sources.yaml:determines_origin` |

**As 320 pessoas da aquisição estão classificadas e nenhuma delas tem vínculo
aprovado com o HRIS corporativo.** É a prova operacional de que proveniência não
depende de identidade, e está fixada no teste F-16.

Teto de contaminação declarável: no máximo **6,4%** das pessoas
`INDETERMINADA` podem ser da aquisição. Cai conforme as 320 decisões de
identidade forem tomadas.

### Base da identidade, por pessoa

| Base | Pessoas | O que significa |
|---|---|---|
| `intrinseca` | 4.111 | o próprio sistema carrega o `employee_id` corporativo; não há vínculo a resolver |
| `xref` | 601 | o vínculo foi aprovado pela governança |
| `nao_resolvida` | 327 | pessoa provisória, `party_key` no escopo da fonte |

A distinção entre as três está em coluna porque "não precisou de vínculo" e
"o vínculo foi aprovado" não são a mesma afirmação. As 327 provisórias são as
320 da VivaMarket mais 7 pessoas que aparecem em snapshot sem estar no cadastro
(as órfãs que o `DQ_REF_007` já media).

## 4. Comparabilidade: a sobreposição de 2019 preservada

| | Linhas |
|---|---|
| `fact_headcount_snapshot`, total | 130.817 |
| filtrado por `is_system_of_record` | 126.424 |
| janela maio–novembro de 2019, total | 8.939 |
| a mesma janela, filtrada | 4.546 |

A diferença de 4.393 linhas **é** a migração dos dois HRIS rodando em paralelo.
Somar sem o filtro duplica, e a duplicação é o comportamento correto: é ruidosa
e detectável, enquanto a escolha silenciosa seria silenciosa. O teste F-01
reprova se ela deixar de acontecer.

## 5. Governança preservada até a L3

| Estado | Onde vive no modelo | Contagem |
|---|---|---|
| `N4` e `N5` da VivaMarket | membro `-2` de `dim_job_level` | 42 versões, valores `N4` e `N5` na coluna de origem |
| departamento sem mapa | membro `-1` de `dim_organization` | usado em 23.206 linhas do snapshot legado |
| identidade não resolvida | pessoa provisória, não membro reservado | 327 |
| marco não atingido | membro `-5` de `dim_calendar` | requisições e candidaturas em curso |
| data anterior ao período de análise | membro `-7` de `dim_calendar` | admissões de 1994 a 2015 |
| quarentena | `analytical_exclusions` | 8 |

Nenhuma chave estrangeira nula em nenhum fato.

## 6. Testes executados

**144 testes, todos passando.** 38 são novos.

| Suíte | Testes | Resultado |
|---|---|---|
| `tests/truth` | 22 | passou |
| `tests/raw` | 15 | passou |
| `tests/pipeline` | 69 | passou |
| `tests/analytical` | **38** | passou |

### Critérios de aceite que devem passar

| # | Critério | Resultado |
|---|---|---|
| A-01 | toda tabela declara o grain | ✅ 15/15 |
| A-02 | nenhuma tabela mistura grains | ✅ zero violações |
| A-03 | toda chave estrangeira resolve | ✅ zero órfãos |
| A-04 | nenhuma chave estrangeira é nula | ✅ |
| A-05 | histórico não é sobrescrito | ✅ reprocessar não reduz versões |
| A-06 | fato usa a versão vigente na data do fato | ✅ zero fatos fora de vigência |
| A-07 | vigências não se sobrepõem | ✅ zero sobreposições, zero pessoas com duas versões vigentes |
| A-08 | identidade não resolvida vira pessoa provisória contável | ✅ 327 |
| A-09 | nenhuma linha em quarentena entra | ✅ interseção vazia |
| A-10 | toda exclusão registrada | ✅ 8 = 8 |
| A-11 | `N4` e `N5` contáveis | ✅ 42 no membro `-2` |
| A-12 | calendário cobre meses sem dado | ✅ 4.201 dias contra 127 meses com dado |
| A-13 | lineage fecha até o `_row_id` | ✅ |
| A-13b | proveniência registra a regra que a determinou | ✅ P1, P2, P3 com `evidence_source` |
| A-14 | manifesto declara camada e proveniência | ✅ |
| A-15 | nenhum KPI calculado na L3 | ✅ verificado no código |
| A-16 | o modelo é determinístico | ✅ duas execuções idênticas |
| A-17 | toda tabela carrega a camada | ✅ 15/15 |

### Casos que devem falhar

| # | Caso | Resultado |
|---|---|---|
| F-01 | headcount sem filtro não duplicar em 2019 | ✅ duplica, como exigido |
| F-02 | duas versões vigentes na mesma data | ✅ zero |
| F-03 | fato apontando para a versão atual | ✅ zero |
| F-04 | nível nulo onde a origem era `N4` | ✅ todos em `-2` |
| F-05 | quarentena em qualquer fato | ✅ zero |
| F-06 | `party_key` consolidado sem vínculo aprovado | ✅ zero |
| F-07 | organização com vigência anterior ao primeiro dado | ✅ zero |
| F-08 | pico de entradas em agosto de 2022 | ✅ sem pico |
| F-09 | `termination_reason` existindo | ✅ coluna ausente |
| F-10 | compensação além da identidade resolvida | ✅ zero |
| F-11 | mês com falha de carga ausente do calendário | ✅ presente |
| F-12 | duas execuções com contagens diferentes | ✅ idênticas |
| F-13 | código da L3 lendo a camada de verdade | ✅ verificado por AST |
| F-14 | tabela sem `layer` ou com `layer` errada | ✅ `LayerError` |
| F-15 | contratação contando `INDETERMINADA` ou aquisição | ✅ `is_hire` exclusivo |
| F-16 | pessoa da VivaMarket sem origem de aquisição | ✅ 320/320 com P1 |
| F-17 | duas observações do mesmo sistema no mesmo mês | ✅ zero |

## 7. Desvios da SPEC

Cinco, todos por evidência encontrada na implementação. Nenhum muda regra de
negócio.

### D-1. O grain é verificado pela chave natural, não pela substituta

A SPEC declarou a chave de `fact_headcount_snapshot` como
`(employee_sk, date_sk, source_sk)`. Na implementação, três pessoas distintas do
snapshot legado apontam para o mesmo `employee_sk = -1` (o membro reservado),
porque estão no snapshot e não no cadastro. Membro reservado é catch-all por
construção e pode repetir.

O grain declarado na SPEC — **pessoa × mês × sistema** — está correto; o que
estava errado era verificá-lo pela chave substituta. A verificação passou a usar
`(party_key, date_sk, source_sk)`, que é a chave natural. Zero violações.

### D-2. Membro `-7`, data anterior ao período de análise

A SPEC não previu admissões anteriores a 2016, e elas existem: a mais antiga é
de 1994. Havia duas saídas, e esticar o calendário até a data mais antiga do
dado o tornaria derivado do dado, que é exatamente o que o defeito D18 proíbe.

Entrou o membro reservado `-7 ANTERIOR_A_SERIE`. A data em si continua na coluna
de origem do fato; o que muda é que ela não vira nulo nem estica o eixo.

### D-3. `identity_basis`: intrínseca, xref ou não resolvida

A SPEC tratava a identidade como binária (resolvida ou não). A implementação
encontrou três estados, e a diferença importa: o `HRIS_CORE` **carrega** o
`employee_id` corporativo, então não há vínculo a resolver; o `HRIS_LEGACY`
depende do `xref`. Chamar os dois de "resolvido" apagaria a distinção entre
"não precisou de vínculo" e "o vínculo foi aprovado".

### D-4. `job_level_source` ao lado do padronizado

Para atribuir o membro `-2` a `N4` e `N5` é preciso saber qual era o valor de
origem, e depois do DE/PARA ele é `UNMAPPED`. A coluna de origem passou a ser
carregada explicitamente, o que também cumpre o ADR-0025: "`N4` vira o membro
`-2` e continua sendo `N4` na coluna de origem".

### D-5. Contagens de origem por pessoa, não por registro

A SPEC projetou 58,1% de `INDETERMINADA` contando **registros do HRIS_CORE**; o
modelo reporta 54,4% contando **pessoas analíticas** depois da consolidação por
`party_key`. Mudou a base de contagem, não a regra: `CONTRATACAO` saiu em 1.499,
exatamente o previsto, e `AQUISICAO_VIVAMARKET` em 320.

## 8. Gaps confirmados na implementação

Todos já documentados na SPEC, agora com evidência de execução.

| Gap | Evidência |
|---|---|
| **G-01** sem motivo de desligamento | `fact_termination` não tem `termination_reason`, `voluntary_flag`, `regrettable_flag` nem `termination_type`. Nenhuma coluna vazia foi criada |
| **G-02** `dim_organization` derivada | `is_derived = true` em todas as 334 linhas; vigência limitada ao período de análise |
| **G-03** aquisição dentro do HRIS | teto de 6,4% documentado e reportado |
| **G-04** readmissão | `event_evidence = derivado_de_atributo` em `fact_workforce_entry` e `fact_termination` |
| **G-05** remuneração parcial | `fact_compensation` só liga a identidade resolvida |

### Gap novo encontrado na implementação

**`movement_type` não tem DE/PARA aprovado.** `fact_movement` e
`dim_employee.change_reason` carregam dois vocabulários ao mesmo tempo:
`Promotion`, `Transfer`, `Lateral Move` do HRIS corporativo, e `PROMOCAO`,
`TRANSFERENCIA`, `MOV LATERAL` do legado.

Não criei o mapeamento: seria regra de negócio nova sem ADR, e a rota correta é
a fila de exceções da F4. O efeito prático é que qualquer contagem por tipo de
movimentação na F7 precisa tratar os dois vocabulários, ou o campo precisa
entrar no DE/PARA antes. Fica como **decisão pendente**.

## 9. Resumo executivo das decisões implementadas

1. **Proveniência é independente de identidade.** Regra governada em três
   níveis, declarada em `sources.yaml`. Rende 320 pessoas de aquisição
   classificadas hoje, com 0% de identidade resolvida.
2. **`HRIS_CORE` e `HRIS_LEGACY` não determinam origem**, por declaração
   explícita. Marcá-los como orgânico faria toda pessoa absorvida virar
   contratação.
3. **`INDETERMINADA` é estado válido**, em 54,4% das pessoas, com teto de
   contaminação declarado. Nenhuma inferência por data, departamento,
   localidade, nome ou cargo.
4. **Pessoa provisória** para identidade não resolvida, sem nenhum matching
   novo: 327 pessoas contáveis que, sem isso, teriam colapsado num membro único.
5. **`layer` é coluna física** em todas as 15 tabelas, e `assert_layer` reprova
   na entrada. Caminho e schema não bastam: quem lê um Parquet direto do disco
   não passa por eles.
6. **`fact_workforce_entry`** no lugar de `fact_hire`, com `origin_sk`
   obrigatório e sem default silencioso.
7. **Sistema observador no grain** do headcount: a sobreposição de 2019
   preservada, 8.939 linhas contra 4.546 filtradas.
8. **`check_provenance` guarda três pares**: raw × verdade, raw × analítico,
   verdade × analítico. Os três em `OK`.
9. **`analytical_ready` → `conformed_approved`**, liberando `analytical/` para a
   L3 como o ADR-0014 previa.
10. **Nenhum KPI calculado na L3**, verificado por teste no código.

---

**Não iniciado:** F7, MCP, interface. **Não alterado:** RAW, DQ, trust score,
thresholds. **Sem commit.**
