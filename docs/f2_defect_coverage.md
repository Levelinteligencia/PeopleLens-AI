# F2 Defect Coverage & Reconciliation Report

Perfil `dev` (escala 10%), seed `42`. Onda 1: HRIS_LEGACY, HRIS_CORE, PAYROLL_BR, ATS_CLOUD, VIVAMARKET_LEGACY.

> Taxas **PROVISIONAL**, congelamento previsto para a **F7** (ADR-0008, Emenda 2).


## Resumo

| | |
|---|---|
| Defeitos no catalogo | 24 |
| Previstos para a onda 1 | 18 |
| Adiados para a onda 2 | 6 |
| Efetivamente injetados | 18 |
| Calibragem OK | 6 |
| Calibragem fora | 0 |
| Deterministicos (sem sorteio) | 9 |
| Observados na verdade (nao injetados) | 3 |
| Amostrados por sorteio | 6 |
| Tentativas registradas | 274.943 |
| Corrupcoes observadas | 20.758 |

## Cobertura e reconciliacao, defeito a defeito

| ID | Nome | Dimensao | Severidade | Sistemas declarados | Sistemas aplicados | Tentativas | Corrompidos | Esperado | Observado | Calibragem |
|---|---|---|---|---|---|---|---|---|---|---|
| D01 | Dominio de gender divergente | Consistency | semantic | HRIS_LEGACY, HRIS_CORE, VIVAMARKET_LEGACY | HRIS_CORE, HRIS_LEGACY, VIVAMARKET_LEGACY | 0 | 2.575 | 100.00% | - | DETERMINISTICO_100% |
| D02 | race_ethnicity inexistente | Completeness | semantic | HRIS_LEGACY | HRIS_LEGACY | 0 | 1 | 100.00% | - | OBSERVADO_NA_VERDADE |
| D03 | race_ethnicity nao informada | Completeness | semantic | HRIS_CORE | HRIS_CORE | 0 | 1.031 | 29.00% | - | OBSERVADO_NA_VERDADE |
| D04 | Departamento com nomenclatura livre | Consistency | semantic | HRIS_LEGACY, VIVAMARKET_LEGACY | HRIS_LEGACY, VIVAMARKET_LEGACY | 24.512 | 3.397 | 12.00% | 13.86% | OK |
| D05 | employee_id corporativo ausente | Completeness | structural | VIVAMARKET_LEGACY, COMPRAFACIL_ERP, ATS_CLOUD | ATS_CLOUD, VIVAMARKET_LEGACY | 0 | 1.199 | 100.00% | - | DETERMINISTICO_100% |
| D06 | employee_id duplicado entre sistemas | Uniqueness | structural | VIVAMARKET_LEGACY, HRIS_CORE | VIVAMARKET_LEGACY | 0 | 18 | 18 registros | 18 registros | DETERMINISTICO |
| D07 | Formato de data divergente | Validity | cosmetic | HRIS_LEGACY, VIVAMARKET_LEGACY, ATS_LEGACY, COMPRAFACIL_ERP | HRIS_LEGACY, VIVAMARKET_LEGACY | 0 | 4 | 100.00% | - | DETERMINISTICO_100% |
| D08 | Data impossivel | Validity | structural | HRIS_LEGACY, VIVAMARKET_LEGACY, COMPRAFACIL_ERP | HRIS_LEGACY, VIVAMARKET_LEGACY | 1.626 | 9 | 0.40% | 0.55% | OK |
| D09 | manager_id orfao | Referential Integrity | structural | HRIS_LEGACY, HRIS_CORE, ORGCHART, VIVAMARKET_LEGACY, COMPRAFACIL_ERP | HRIS_CORE, HRIS_LEGACY, VIVAMARKET_LEGACY | 136.554 | 3.095 | 2.20% | 2.27% | OK |
| D10 | Departamento extinto ainda em uso | Consistency | semantic | ORGCHART | - | 0 | 0 | 15.00% | - | ONDA_2 |
| D11 | Divergencia de headcount HRIS versus Payroll | Reconciliation | semantic | HRIS_CORE, PAYROLL_BR, PAYROLL_LATAM | PAYROLL_BR | 0 | 5.464 | 3.50% | - | DETERMINISTICO |
| D12 | job_level fora do padrao corporativo | Validity | semantic | VIVAMARKET_LEGACY, COMPRAFACIL_ERP | VIVAMARKET_LEGACY | 0 | 320 | 100.00% | - | DETERMINISTICO_100% |
| D13 | Salario anual versus mensal | Consistency | semantic | PAYROLL_LATAM, COMP_PLAN | - | 0 | 0 | 100.00% | - | ONDA_2 |
| D14 | Moeda ausente | Completeness | semantic | HRIS_LEGACY, PAYROLL_BR, PAYROLL_LATAM | PAYROLL_BR | 106.861 | 1.838 | 1.76% | 1.72% | OK |
| D15 | Candidato duplicado | Uniqueness | semantic | ATS_LEGACY | - | 0 | 0 | 6.00% | - | ONDA_2 |
| D16 | Requisicao sem contratacao | Referential Integrity | semantic | ATS_LEGACY, ATS_CLOUD | ATS_CLOUD | 0 | 374 | 15.00% | - | OBSERVADO_NA_VERDADE |
| D17 | Contratacao sem requisicao valida | Referential Integrity | structural | ATS_LEGACY, ATS_CLOUD, HRIS_CORE | ATS_CLOUD | 1.279 | 127 | 9.00% | 9.93% | OK |
| D18 | Registro parado | Timeliness | semantic | ORGCHART, LMS, COMPRAFACIL_ERP | - | 0 | 0 | 3.00% | - | ONDA_2 |
| D19 | country inconsistente entre sistemas | Consistency | semantic | HRIS_CORE, PAYROLL_BR, PAYROLL_LATAM, COMPRAFACIL_ERP | HRIS_CORE | 4.111 | 52 | 1.20% | 1.26% | OK |
| D20 | compa_ratio da fonte divergente do recalculado | Reconciliation | semantic | COMP_PLAN | - | 0 | 0 | 34 registros | 0 registros | ONDA_2 |
| D21 | engagement_score zerado indevidamente | Validity | structural | ENGAGE | - | 0 | 0 | 100.00% | - | ONDA_2 |
| D22 | Duplicidade de vinculo por recontratacao | Uniqueness | semantic | HRIS_LEGACY, HRIS_CORE, LMS | HRIS_LEGACY | 0 | 190 | 190 registros | 190 registros | DETERMINISTICO |
| D23 | Encoding quebrado | Validity | cosmetic | HRIS_LEGACY, VIVAMARKET_LEGACY, COMPRAFACIL_ERP | HRIS_LEGACY, VIVAMARKET_LEGACY | 0 | 1.063 | 100.00% | - | DETERMINISTICO_100% |
| D_DEFINITION_DRIFT | Deriva de definicao ao longo do tempo | Consistency | semantic | HRIS_CORE, HRIS_LEGACY, COMP_PLAN | HRIS_CORE | 0 | 1 | - | - | DETERMINISTICO_100% |

## Incidentes de origem e deteccao planejada

| ID | Incidente ou pratica de origem | Checks de DQ previstos (F5) | Validacoes no RAW (F2) | Status end-to-end |
|---|---|---|---|---|
| D01 | INC_2019_HRIS_MIGRATION | DQ_VALID_004, DQ_CONS_002 | R06, R12 | PARCIAL, injetado, calibrado e verificado no RAW; deteccao por DQ so na F5 |
| D02 | INC_2019_HRIS_MIGRATION | DQ_COMP_007 | R05, R11 | OBSERVADO, nao injetado; deteccao por DQ so na F5 |
| D03 | autodeclaracao opcional | DQ_COMP_008 | - | OBSERVADO, nao injetado; deteccao por DQ so na F5 |
| D04 | entrada manual sem dominio controlado | DQ_CONS_001 | - | PARCIAL, injetado e calibrado, sem verificacao especifica no RAW |
| D05 | INC_2022_VIVAMARKET, INC_2024_COMPRAFACIL | DQ_COMP_001 | R14 | PARCIAL, injetado, calibrado e verificado no RAW; deteccao por DQ so na F5 |
| D06 | INC_2022_VIVAMARKET | DQ_UNIQ_002 | R08 | PARCIAL, injetado, calibrado e verificado no RAW; deteccao por DQ so na F5 |
| D07 | padrao do sistema de origem | DQ_VALID_001 | - | PARCIAL, injetado e calibrado, sem verificacao especifica no RAW |
| D08 | digitacao manual | DQ_VALID_002, DQ_VALID_003 | - | PARCIAL, injetado e calibrado, sem verificacao especifica no RAW |
| D09 | gestor desligado sem sucessao registrada, e reorganizacoes | DQ_REF_001 | - | PARCIAL, injetado e calibrado, sem verificacao especifica no RAW |
| D10 | INC_2023_DIGITAL_REORG, INC_2025_NEW_ORG_MODEL | DQ_CONS_005, DQ_RECON_004 | - | PENDENTE, sistema da onda 2 |
| D11 | definicoes diferentes de ativo: a folha inclui terceiros, estagiarios e aviso previo | DQ_RECON_001 | R16 | PARCIAL, injetado, calibrado e verificado no RAW; deteccao por DQ so na F5 |
| D12 | INC_2022_VIVAMARKET, INC_2024_COMPRAFACIL | DQ_VALID_006 | R14 | PARCIAL, injetado, calibrado e verificado no RAW; deteccao por DQ so na F5 |
| D13 | pratica diferente por pais | DQ_CONS_008 | - | PENDENTE, sistema da onda 2 |
| D14 | campo opcional no sistema legado | DQ_COMP_011 | - | PARCIAL, injetado e calibrado, sem verificacao especifica no RAW |
| D15 | mesma pessoa com e-mails diferentes, sem chave estavel no ATS legado | DQ_UNIQ_005 | - | PENDENTE, sistema da onda 2 |
| D16 | vaga cancelada, congelada ou preenchida internamente sem registro | DQ_REF_004 | - | OBSERVADO, nao injetado; deteccao por DQ so na F5 |
| D17 | contratacao emergencial de loja, registrada depois | DQ_REF_005, DQ_RECON_003 | - | PARCIAL, injetado e calibrado, sem verificacao especifica no RAW |
| D18 | integracao que parou de rodar e ninguem percebeu | DQ_TIME_002 | - | PENDENTE, sistema da onda 2 |
| D19 | pais do contrato diferente do pais de trabalho, em expatriados e remotos | DQ_CONS_003 | - | PARCIAL, injetado e calibrado, sem verificacao especifica no RAW |
| D20 | INC_2025_NEW_ORG_MODEL | DQ_RECON_002 | - | PENDENTE, sistema da onda 2 |
| D21 | response_flag = 0 exportado como score 0 em vez de nulo | DQ_VALID_011 | - | PENDENTE, sistema da onda 2 |
| D22 | recontratacao criou registro novo em vez de reabrir o vinculo | DQ_UNIQ_001, DQ_CONS_006 | - | PARCIAL, injetado e calibrado, sem verificacao especifica no RAW |
| D23 | arquivo latin-1 lido como utf-8 | DQ_VALID_009 | R10 | PARCIAL, injetado, calibrado e verificado no RAW; deteccao por DQ so na F5 |
| D_DEFINITION_DRIFT | INC_2021_PERF_SCALE, INC_2025_NEW_ORG_MODEL | DQ_CONS_010 | - | PARCIAL, injetado e calibrado, sem verificacao especifica no RAW |

## Lacunas conhecidas

**Onda 2 (6 defeitos).** Dependem de sistemas que so entram depois da F5:

- `D10` Departamento extinto ainda em uso, em ORGCHART
- `D13` Salario anual versus mensal, em PAYROLL_LATAM, COMP_PLAN
- `D15` Candidato duplicado, em ATS_LEGACY
- `D18` Registro parado, em ORGCHART, LMS, COMPRAFACIL_ERP
- `D20` compa_ratio da fonte divergente do recalculado, em COMP_PLAN
- `D21` engagement_score zerado indevidamente, em ENGAGE

**Sem verificacao especifica no RAW (11 defeitos).** Estao injetados e calibrados, e sao cobertos apenas pelas validacoes genericas R01 a R04 e R07. A verificacao especifica deles acontece na F5, quando os checks de DQ existirem.

- `D03` race_ethnicity nao informada
- `D04` Departamento com nomenclatura livre
- `D07` Formato de data divergente
- `D08` Data impossivel
- `D09` manager_id orfao
- `D14` Moeda ausente
- `D16` Requisicao sem contratacao
- `D17` Contratacao sem requisicao valida
- `D19` country inconsistente entre sistemas
- `D22` Duplicidade de vinculo por recontratacao
- `D_DEFINITION_DRIFT` Deriva de definicao ao longo do tempo

**Nenhum defeito previsto para a onda 1 ficou sem injecao.**

## Nota sobre tentativa versus corrupcao

O ledger conta duas coisas diferentes de proposito:

- **tentativa**: um registro foi oferecido ao defeito, com a taxa esperada daquele momento, ja considerando escopo temporal, picos por incidente e taxa por pais;
- **corrupcao observada**: o valor gravado no RAW ficou de fato diferente do valor verdadeiro.

As duas so coincidem se a funcao de injecao garantir mudanca. A F2 encontrou um caso em que nao garantia, e o efeito era o pior possivel: o ledger registrava corrupcao que nao existia no arquivo, ou seja, o **gabarito ficava errado a favor do gerador**. Ver `docs/f2_validation_findings.md`, achado 1.

