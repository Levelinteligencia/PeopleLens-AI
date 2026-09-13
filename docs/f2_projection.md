# PeopleLens, F2: projecao nos sistemas-fonte

Perfil `dev` (escala 10%), seed `42`, onda 1.

> A camada de verdade nao foi alterada. O RAW e projecao dela, com os defeitos
> declarados em `config/defects.yaml`. As taxas estao **PROVISIONAL** (ADR-0008, Parte B).


## Volumes por sistema

| Sistema | Dataset | Linhas | Formato |
|---|---|---|---|
| HRIS_LEGACY | employee_master | 1.496 | csv |
| HRIS_LEGACY | headcount_snapshot | 23.206 | csv |
| HRIS_LEGACY | movement | 262 | csv |
| HRIS_CORE | employee_master | 4.111 | parquet |
| HRIS_CORE | headcount_snapshot | 107.611 | parquet |
| HRIS_CORE | performance | 14.909 | parquet |
| HRIS_CORE | movement | 3.349 | parquet |
| PAYROLL_BR | payroll_headcount_snapshot | 100.788 | csv |
| PAYROLL_BR | compensation | 10.505 | csv |
| ATS_CLOUD | requisition | 2.752 | json |
| ATS_CLOUD | application | 31.110 | json |
| VIVAMARKET_LEGACY | employee_master | 320 | xlsx |

## Defeitos injetados

| Defeito | Nome | Dimensao | Ocorrencias |
|---|---|---|---|
| D11 | Divergencia de headcount HRIS versus Payroll | Reconciliation | 5.464 |
| D04 | Departamento com nomenclatura livre | Consistency | 3.397 |
| D09 | manager_id orfao | Referential Integrity | 3.095 |
| D01 | Dominio de gender divergente | Consistency | 2.575 |
| D14 | Moeda ausente | Completeness | 1.838 |
| D05 | employee_id corporativo ausente | Completeness | 1.199 |
| D23 | Encoding quebrado | Validity | 1.063 |
| D03 | race_ethnicity nao informada | Completeness | 1.031 |
| D16 | Requisicao sem contratacao | Referential Integrity | 374 |
| D12 | job_level fora do padrao corporativo | Validity | 320 |
| D22 | Duplicidade de vinculo por recontratacao | Uniqueness | 190 |
| D17 | Contratacao sem requisicao valida | Referential Integrity | 127 |
| D19 | country inconsistente entre sistemas | Consistency | 52 |
| D06 | employee_id duplicado entre sistemas | Uniqueness | 18 |
| D08 | Data impossivel | Validity | 9 |
| D07 | Formato de data divergente | Validity | 4 |
| D02 | race_ethnicity inexistente | Completeness | 1 |
| D_DEFINITION_DRIFT | Deriva de definicao ao longo do tempo | Consistency | 1 |

Total: **20.758 ocorrencias** registradas no ledger.

Cobertura: 18 de 24 defeitos do catalogo estao ativos na onda 1. Os demais dependem de sistemas da onda 2: ['D10', 'D13', 'D15', 'D18', 'D20', 'D21'].

## Calibragem: esperado versus realizado

> Base da decisao D8 Parte B. O ledger conta quantos registros foram
> **oferecidos** a cada defeito e qual era a taxa esperada em cada oferta,
> ja considerando escopo temporal, picos por incidente e taxa por pais.

| Defeito | Sistema.dataset | Elegiveis | Esperado | Realizado | Desvio |
|---|---|---|---|---|---|
| D04 | HRIS_LEGACY.employee_master | 1.306 | 12.00% | 12.56% | +0.56% |
| D04 | HRIS_LEGACY.headcount_snapshot | 23.206 | 12.00% | 12.55% | +0.55% |
| D08 | HRIS_LEGACY.employee_master | 1.306 | 0.40% | 0.61% | +0.21% |
| D08 | VIVAMARKET_LEGACY.employee_master | 320 | 0.40% | 0.31% | -0.09% |
| D09 | HRIS_CORE.employee_master | 4.111 | 2.23% | 1.80% | -0.43% |
| D09 | HRIS_CORE.headcount_snapshot | 107.611 | 2.28% | 2.37% | +0.09% |
| D09 | HRIS_LEGACY.employee_master | 1.306 | 1.80% | 1.76% | -0.04% |
| D09 | HRIS_LEGACY.headcount_snapshot | 23.206 | 1.80% | 1.87% | +0.07% |
| D09 | VIVAMARKET_LEGACY.employee_master | 320 | 5.00% | 4.69% | -0.31% |
| D14 | PAYROLL_BR.compensation | 10.505 | 1.73% | 1.66% | -0.08% |
| D14 | PAYROLL_BR.payroll_headcount_snapshot | 96.356 | 1.77% | 1.73% | -0.04% |
| D17 | ATS_CLOUD.requisition | 1.279 | 9.00% | 9.93% | +0.93% |
| D19 | HRIS_CORE.employee_master | 4.111 | 1.20% | 1.26% | +0.06% |

## Validacoes da camada RAW

17 de 17 passaram.

| ID | Verificacao | Resultado |
|---|---|---|
| R01 | nenhum defeito fora do catalogo | OK |
| R02 | todo defeito ocorre so em sistema que declara carrega-lo | OK |
| R03 | a F2 escreve apenas os sistemas da onda 1 | OK |
| R04 | todo defeito previsto para a onda 1 aparece ao menos uma vez | OK |
| R05 | D02 e registrado como ausencia de coluna, nao como valor | OK |
| R06 | D01 no HRIS_CORE so ocorre na janela de sobreposicao da migracao | OK |
| R07 | taxa realizada de cada defeito dentro de 3 desvios da esperada | OK |
| R08 | D06 respeita a contagem absoluta configurada | OK |
| R09 | registro sem defeito declarado reproduz a verdade exatamente | OK |
| R10 | HRIS_LEGACY legivel em latin-1 com delimitador ponto e virgula | OK |
| R11 | HRIS_LEGACY nao expoe coluna de raca e cor (D02) | OK |
| R12 | HRIS_LEGACY usa dominio antigo de genero | OK |
| R13 | ATS_CLOUD produz JSON aninhado valido | OK |
| R14 | VivaMarket entrega xlsx sem o employee_id corporativo (D05) | OK |
| R15 | todo arquivo da landing zone carrega as colunas tecnicas de lineage | OK |
| R16 | divergencia de populacao entre HRIS e folha dentro da faixa configurada | OK |
| R17 | manifesto da camada de verdade continua presente e intacto | OK |
