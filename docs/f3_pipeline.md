# PeopleLens, F3: pipeline de ingestao, padronizacao, DE/PARA e qualidade

Perfil `dev` (escala 10%), seed `42`, run `12aec8a360bc`.

> O RAW nao foi alterado. Nenhum valor foi corrigido em silencio: toda transformacao
> esta em `transformation_log` com valor original, sistema de origem e regra aplicada.


Proveniencia: **OK**, RAW e verdade da mesma execucao.


## Camadas

| Camada | Linhas | O que faz |
|---|---|---|
| L0 raw | (imutavel) | nada; so leitura |
| staged | 300.419 | copia fiel. tudo como texto. com `_row_id` |
| L1 standardized | 300.419 | forma: encoding. espaco. data. numero |
| L2 conformed | 300.419 | DE/PARA aprovado e identidade |
| conformed-approved | 300.411 | fatia aprovada da L2. pos-quarentena |

## Profiling

136 colunas perfiladas, 49 achados levantados sem ninguem dizer onde procurar.

| Achado | Ocorrencias |
|---|---|
| dominio candidato a depara | 19 |
| alta taxa de nulos | 9 |
| data fora do iso | 7 |
| encoding suspeito | 5 |
| espaco nas pontas | 3 |
| caixa inconsistente | 3 |
| decimal com virgula | 3 |

## Padronizacao

280.727 valores transformados. 8 falhas de conversao.

| Regra | Valores |
|---|---|
| STD_DATE_PARSE | 137.069 |
| STD_DECIMAL_BR | 134.500 |
| STD_ENCODING_REPAIR | 1.497 |
| STD_TRIM | 575 |
| STD_COLLAPSE_WS | 226 |

## DE/PARA

| Campo | Mapeados | Nao mapeados | Valores distintos sem mapa | Taxa |
|---|---|---|---|---|
| gender | 5.891 | 2 | 1 | 0.03% |
| country | 240.284 | 0 | 0 | 0.00% |
| job_level | 139.454 | 42 | 2 | 0.03% |
| department | 138.390 | 1.106 | 33 | 0.79% |
| performance_rating | 14.909 | 0 | 0 | 0.00% |

**57 excecoes abertas** na fila, com sugestao e confianca. Nenhuma aplicada automaticamente (principio 5, ADR-0009).


## Identidade

| Status | Registros |
|---|---|
| AMBIGUOUS | 88 |
| MANUAL_REVIEW | 1.491 |
| RESOLVED | 10.183 |
| UNRESOLVED | 33.164 |

| Sistema | Resolvidos | Total | Taxa |
|---|---|---|---|
| HRIS_CORE | 4.111 | 4.111 | 100.0% |
| VIVAMARKET_LEGACY | 0 | 320 | 0.0% |
| PAYROLL_BR | 3.077 | 7.509 | 41.0% |
| HRIS_LEGACY | 1.496 | 1.496 | 100.0% |
| ATS_CLOUD | 1.499 | 31.110 | 4.8% |
| * | 0 | 380 | 0.0% |

## Qualidade

87 checks executados, 83 passaram, 4 falharam. 8 registros em quarentena.

| Dimensao | Checks | Falhas |
|---|---|---|
| Completeness | 15 | 1 |
| Consistency | 16 | 1 |
| Reconciliation | 8 | 0 |
| Referential Integrity | 12 | 1 |
| Timeliness | 6 | 0 |
| Uniqueness | 9 | 0 |
| Validity | 21 | 1 |

### Checks reprovados

| Check | Dataset | Severidade | Classe de achado | Taxa | Limite | Registros |
|---|---|---|---|---|---|---|
| DQ_COMP_012 centro de custo presente no snapshot da folha | PAYROLL_BR.payroll_headcount_snapshot | WARNING | INVALIDO | 100.00% | 5.00% | 100788 |
| DQ_VALID_006 job level em dominio corporativo apos o DE/PARA, aquisicao | VIVAMARKET_LEGACY.employee_master | CRITICAL | DECISAO_PENDENTE | 13.12% | 10.00% | 42 |
| DQ_CONS_006 departamento da aquisicao mapeado para o dominio padrao | VIVAMARKET_LEGACY.employee_master | CRITICAL | NAO_MAPEADO | 29.38% | 10.00% | 94 |
| DQ_REF_008 identidade resolvida para a populacao da aquisicao | VIVAMARKET_LEGACY.employee_master | CRITICAL | IDENTIDADE_NAO_RESOLVIDA | 100.00% | 0.00% | 320 |

## Lineage

- 48 relacoes entre objetos (camada por camada)
- 280.727 transformacoes de valor rastreadas individualmente

## Comparacao com a camada de verdade

> Leitura correta: a F3 **nao corrige** nada. O que se mede e quanto da verdade ficou
> recuperavel apos padronizacao e DE/PARA, e quanto segue bloqueado esperando decisao.

| Campo | Comparados | Recuperados | Taxa | UNMAPPED | Divergentes |
|---|---|---|---|---|---|
| HRIS_LEGACY.gender | 1.287 | 1.287 | 100.00% | 0 | 0 |
| HRIS_LEGACY.department | 1.306 | 1.256 | 96.17% | 50 | 0 |
| HRIS_LEGACY.job_level | 1.306 | 1.306 | 100.00% | 0 | 0 |
| HRIS_CORE.department | 4.111 | 4.111 | 100.00% | 0 | 0 |
| HRIS_CORE.country | 4.111 | 4.059 | 98.74% | 0 | 52 |

**Aquisicao VivaMarket** (320 pessoas): job level recuperado 85.9%, sem mapa 13.1%; genero 99.4%; departamento 70.6%.

**Headcount**: 86 meses comparados, desvio medio absoluto 0.000%, maximo 0.000%.

**Gestores orfaos remanescentes**: 41 de 4.111 (1.00%). a F3 nao corrige; orfao permanece e alimenta o check DQ_REF_001.

**Identidade da aquisicao**: 0 resolvidos automaticamente, 320 para revisao humana, 0 ambiguos. zero resolucao automatica e o comportamento projetado no ADR-0004, nao uma falha.

## Trust score

> O score e uma media ponderada unica sobre os checks que pesam, e a perda e
> **atribuida por natureza**: dado errado e uma coisa, decisao pendente e outra.
> Faixas provisorias; a calibragem contra a distribuicao alvo e da F7.


396 pares KPI x recorte avaliados, dos quais 190 respondiveis, 0 suprimidos por n minimo e 206 sem nenhum check aplicavel ao recorte (INDETERMINADO, que nao e o mesmo que aprovado).

| Status | Pares respondiveis | Share |
|---|---|---|
| BLOCKED | 1 | 0.5% |
| CERTIFIED | 184 | 96.8% |
| LIMITED | 5 | 2.6% |

| Motivo principal da perda | Pares |
|---|---|
| OK | 118 |
| PENDENCIA | 38 |
| ERRO | 34 |

Trust medio 0.9887. Perda media por **erro** 0.00038, por **pendencia** 0.01097: a confianca que falta neste dataset vem majoritariamente de decisao em aberto, nao de dado errado.

18 contratos de KPI com `depends_on_checks` e `depends_on_mappings` declarados (ADR-0011). Nenhuma inconsistencia entre catalogo e contratos.

## Governanca das filas

> Duas filas, um ciclo de vida: `OPEN -> UNDER_REVIEW -> APPROVED | REJECTED`.
> Nao existe funcao de aprovacao em lote por limiar de confianca, e a ausencia
> dela e verificada por teste.


| Fila | Estado | Itens |
|---|---|---|
| mapeamento | OPEN | 57 |
| identidade | OPEN | 1.845 |

0 transicoes registradas em `resolution_log`. A F4 entrega o mecanismo; promover qualquer mapeamento agora contrariaria "nenhuma promocao automatica".

266 casos de identidade continuam OPEN sem terem sido observados nesta execucao, e sao residuo de execucoes anteriores em outro perfil. Nao foram apagados: sumir da base e um fato que merece visibilidade, nao delecao silenciosa (ADR-0021).

## Custo de execucao

> Medicao pedida na aprovacao da F3, item 4: instrumentar para permitir decisao
> futura baseada em evidencia. Nada foi otimizado aqui.


| Etapa | Segundos | us por linha | Valores rastreados |
|---|---|---|---|
| ingestao | 0.58 | - | 0 |
| profiling | 0.88 | 2.92 | 0 |
| padronizacao | 21.46 | 71.45 | 273.867 |
| depara | 0.56 | 1.87 | 6.860 |
| identidade | 0.24 | 0.79 | 0 |
| qualidade | 0.28 | 0.93 | 0 |
| trust_score | 1.88 | 6.25 | 0 |

Projecao para volume completo (fator 10x): 4.3 minutos. Ressalva: projecao linear; vale para etapas linha a linha e subestima custo fixo por dataset.

## Tempos

ingestao 0.6s, profiling 0.9s, padronizacao 21.5s, mapeamento 0.8s, qualidade 2.2s. Total 26.2s.

