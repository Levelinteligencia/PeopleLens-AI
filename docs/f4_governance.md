# F4: identidade, resolução governada de exceções e DE/PARA operacional

Perfil `dev` (escala 10%), seed `42`. Nenhum mapeamento foi promovido, nenhuma
identidade foi decidida e nada foi aplicado automaticamente. A F4 construiu o
**mecanismo** de decisão; as decisões são da Sam e da área dona de cada dado.

> Escopo autorizado: identidade, resolução governada de exceções e DE/PARA
> operacional. Sem MCP, sem interface e sem commit.

---

## O que a F4 resolve

A F3 terminou com duas filas paradas e nenhuma forma de trabalhá-las: 57
exceções de mapeamento e 1.579 casos de identidade que o sistema estava
proibido de decidir sozinho. Uma fila sem mecanismo de resolução não é
governança, é acúmulo.

O mecanismo tem que atravessar uma tensão específica. A regra do projeto é que
nada muda de significado sem decisão humana, e a consequência natural disso é
uma fila que ninguém trabalha, porque cada item chega sem contexto. Uma fila
que ninguém trabalha acaba sendo aprovada em bloco, que é exatamente o que a
regra queria impedir. **A saída não é afrouxar a regra, é reduzir o custo de
cumpri-la**: classificar as exceções por natureza, mostrar por que cada
sugestão foi feita, e separar o que um analista resolve em cinco segundos do
que exige uma decisão de negócio.

---

## 1. Ciclo de vida das decisões

Duas filas, uma governança, os estados da Especificação seção 17:

```
OPEN ──> UNDER_REVIEW ──> APPROVED ──> promoção para o CSV versionado
                      └─> REJECTED ──> fica na fila, com motivo
```

| Regra | Onde é feita valer |
|---|---|
| não existe aprovação automática, nem por limiar de confiança | `Governance` não tem método `auto_*`, `bulk_*` ou `approve_all`, e um teste verifica a **ausência** deles |
| aprovar exige valor explícito, responsável e justificativa | `approve()` levanta `GovernanceError` sem `standard_value` ou com justificativa de menos de 10 caracteres |
| aprovar escreve no arquivo versionado, não no banco | `_promote()` grava em `data/reference/*.csv`; o histórico do Git é a trilha de auditoria (ADR-0009) |
| toda transição fica registrada, inclusive as recusas | `resolution_log` guarda de, para, valor, responsável, justificativa e data |
| rejeitar não apaga | a exceção permanece na fila como `REJECTED` |
| depreciar não apaga | `deprecate()` muda o status da linha e preserva o valor padrão antigo, porque séries históricas foram calculadas com ele |

A ausência de aprovação em lote é testada de propósito. Não basta ninguém
chamar um aprovador automático: ele não pode existir, porque a existência é o
convite.

## 2. As 57 exceções, classificadas

`src/mapping/proposal.py` produz `docs/f4_mapping_proposal.md`. Classifica e
não aplica.

| Classe | Quantas | O que é | Quem decide |
|---|---|---|---|
| APELIDO_CONHECIDO | 43 | sigla ou abreviação com candidato único e destacado | analista, em segundos |
| TRADUCAO_PENDENTE | 12 | origem e domínio corporativo em línguas diferentes | quem conhece os dois vocabulários |
| DECISAO_DE_NEGOCIO | 2 | `N4` e `N5` da VivaMarket | People Analytics |

A distinção é o ponto. Tratar as 57 como lista homogênea leva ou a aprovar tudo
em bloco, ou a travar tudo esperando uma decisão que 43 delas não precisam.

### Por que a sugestão agora mostra o apelido intermediário

`JUR → Legal, 0,82 por prefixo` é uma sugestão inconferível: `JUR` não é
prefixo de `Legal`. É prefixo de `JURIDICO`, um apelido que já está no mapa
aprovado. O motor sempre pontuou contra os dois lados da tabela; o que faltava
era mostrar qual deles casou. Uma sugestão que esconde o intermediário pede fé
em vez de revisão, e fé é o que produz aprovação em bloco.

A proposta agora traz a coluna **casou com**.

### Por que 12 exceções não recebem candidato nenhum

Ver o achado 3 em `docs/f4_validation_findings.md`. Em resumo: `Controladoria`
pontuava 0,61 contra `Engineering` e aparecia como candidato provável. Não é
candidato, é coincidência de letras entre dois vocabulários. Quando a língua
declarada do sistema difere da língua do domínio corporativo e nenhum apelido
aprovado cobre o valor, a proposta não oferece candidato e diz por quê.

### As duas exceções de negócio continuam pendentes

`N4` (30 ocorrências) e `N5` (12) são os níveis em que a escala de sete da
VivaMarket cobre dois níveis da NOVAORA cada. Não existe tradução correta.
Continuam em `UNMAPPED`, o `DQ_VALID_006` continua reprovado em 13,12% contra
um limiar de 10%, e o limiar não foi tocado — conforme o item 1 da aprovação da
F3.

## 3. DE/PARA operacional: vigência temporal

Mapeamento tem data. `3` em `performance_rating` significava
"Meets Expectations" até 2020 e deixou de significar qualquer coisa em 2021,
quando a escala virou textual (defeito `D_DEFINITION_DRIFT`). Aplicar o mapa
sem olhar a data reescreveria a história.

`DATASET_SPEC` declara, por dataset, de qual coluna sai cada campo padronizado
**e qual coluna dá a data de referência do registro**. `lookup()` só considera
uma linha aprovada se a data do registro estiver dentro da vigência.

| Janela | Valores de origem | Resultado |
|---|---|---|
| 2016-01-01 a 2020-12-31 | `1` a `5` | escala numérica traduzida para os rótulos |
| 2021-01-01 em diante | rótulos textuais | mapeados para si mesmos |

Resultado: **0 `UNMAPPED` em `performance_rating`**, com as duas escalas
convivendo no mesmo dataset e cada avaliação lida pela regra vigente na data em
que foi feita.

Uma correção de percurso vale registrar. A primeira versão dava vigência
`2016-01-01` a **todo** mapeamento semeado, e não só aos que mudam de
significado. Pessoas admitidas antes de 2016 — a população é semeada desde 2004
— passaram a cair em `UNMAPPED`, e as falhas de qualidade saltaram de 1 para 4.
A vigência padrão passou a ser aberta; janela fechada é para mudança real de
significado, não para todo mundo.

## 4. Identidade

44.926 vínculos avaliados entre sistemas.

| Status | Vínculos | O que significa |
|---|---|---|
| RESOLVED | 10.183 | identificador exato ou padrão de identificador; decidido pelo sistema |
| MANUAL_REVIEW | 1.491 | nome, ou nome mais data de admissão; **o sistema não decide** |
| AMBIGUOUS | 88 | mais de um candidato plausível; nunca recebe `employee_id` |
| UNRESOLVED | 33.164 | sem candidato; em boa parte candidatos de ATS que nunca viraram colaboradores |

O que entra na fila humana são os 1.579 que o sistema estava proibido de
decidir. A composição diz de onde vem o custo de integração:

| Origem | Casos | Por quê |
|---|---|---|
| ATS_CLOUD, `fuzzy_name` | 1.033 | o ATS só preenche `employee_id` em 63% dos casos |
| suspeita de identidade duplicada | 428 | mesma pessoa em mais de um sistema sem chave comum |
| VIVAMARKET_LEGACY, `name_hire_date` | 382 | a aquisição veio sem `employee_id` corporativo (defeito D05) |
| VIVAMARKET_LEGACY, `fuzzy_name` | 2 | |

`decide_identity(employee_id=None)` é uma decisão legítima e esperada: um
terceiro de agência na folha não tem contraparte no HRIS, e forçar um vínculo
seria pior do que registrar que não existe vínculo.

## 5. Custo de execução, medido

Instrumentação pedida no item 4 da aprovação da F3: medir para permitir decisão
futura baseada em evidência. **Nada foi otimizado.**

| Etapa | Segundos (10%) | µs por linha | Participação |
|---|---|---|---|
| padronização | 20,2 | 67,2 | 89% |
| profiling | 1,0 | 3,2 | 4% |
| DE/PARA | 0,7 | 2,2 | 3% |
| ingestão | 0,6 | — | 3% |
| identidade | 0,3 | 0,9 | 1% |
| qualidade | 0,05 | 0,2 | 0,2% |

Total 22,7s para 300 mil linhas. Projeção linear para volume completo: **3,8
minutos**, com a ressalva de que a projeção vale para as etapas linha a linha e
subestima custo fixo por dataset.

A leitura relevante: o lineage em granularidade de valor está concentrado na
padronização, que sozinha responde por 89% do tempo e registra 273.867
transformações individuais. Quatro minutos para o dataset inteiro não justifica
abrir mão de rastreabilidade por valor. A instrumentação fica gravada em
`data/processed/metadata/execution_timing.parquet`, acumulando histórico, para
que a decisão seja revisada com série e não com impressão.

## 6. Estado das filas ao fim da F4

| Fila | Estado | Itens |
|---|---|---|
| mapeamento | OPEN | 57 |
| identidade | OPEN | 1.845 |
| `resolution_log` | — | 0 transições |

Zero transições é o resultado correto: a F4 entrega o mecanismo, e promover
qualquer mapeamento agora contrariaria "nenhuma promoção automática".

Dos 1.845 casos de identidade, **266 não foram observados nesta execução**. São
resíduo de execuções anteriores em outro perfil. Não foram apagados — ver o
achado 2 em `docs/f4_validation_findings.md`.

## 7. Artefatos

| Arquivo | Conteúdo |
|---|---|
| `src/mapping/resolution.py` | `Governance`: ciclo de vida, promoção, depreciação, fila de identidade |
| `src/mapping/proposal.py` | classificação das exceções e geração do documento de decisão |
| `src/mapping/similarity.py` | quatro estratégias de pontuação, com o apelido que casou |
| `src/instrumentation.py` | `Timer`, histórico acumulado em parquet |
| `docs/f4_mapping_proposal.md` | as 57 exceções, classificadas, com justificativa caso a caso |
| `data/processed/metadata/identity_decisions.parquet` | fila de identidade |
| `data/processed/metadata/resolution_log.parquet` | trilha de decisões (vazia por ora) |
| `tests/pipeline/test_governance.py` | 24 testes do ciclo governado |

76 testes no total, todos passando.

## 8. O que precisa de decisão sua

| # | Decisão | Efeito de não decidir |
|---|---|---|
| 1 | `N4` e `N5` da VivaMarket | `DQ_VALID_006` segue reprovado e o trust score do KPI dependente segue derrubado, que é o comportamento desejado |
| 2 | as 12 exceções de tradução | 286 ocorrências seguem `UNMAPPED` (284 de departamento, 2 de gênero) |
| 3 | as 43 sugestões com apelido conferível | 822 ocorrências seguem `UNMAPPED`; nenhuma será promovida sem aprovação explícita |
| 4 | os 266 casos de identidade não observados | continuam visíveis na fila, marcados |
| 5 | a classe `TRADUCAO_PENDENTE` foi introduzida na taxonomia da proposta | é classificação, não regra de negócio, e não aplica nada; mas é adição de vocabulário e cabe seu aval |
