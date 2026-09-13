# PeopleLens, F1: metricas da camada de verdade

Perfil `dev` (escala 10%), seed `42`.

> Estes numeros descrevem o mundo simulado. Nao sao KPIs certificados: 
> a camada semantica governada so existe na F7.


## Headcount e turnover

| Ano | HC medio | HC fim | Deslig. | Turnover | Voluntario | Involuntario |
|---|---|---|---|---|---|---|
| 2016 | 404 | 450 | 93 | 23.0% | 14.1% | 8.9% |
| 2017 | 455 | 513 | 125 | 27.5% | 18.7% | 8.8% |
| 2018 | 526 | 598 | 157 | 29.8% | 18.8% | 11.0% |
| 2019 | 636 | 743 | 149 | 23.4% | 16.7% | 6.8% |
| 2020 | 735 | 806 | 115 | 15.6% | 11.7% | 3.9% |
| 2021 | 833 | 958 | 252 | 30.2% | 19.9% | 10.3% |
| 2022 | 1090 | 1397 | 300 | 27.5% | 20.4% | 7.2% |
| 2023 | 1419 | 1602 | 337 | 23.8% | 16.6% | 7.2% |
| 2024 | 1620 | 1886 | 438 | 27.0% | 16.8% | 10.2% |
| 2025 | 1856 | 2038 | 398 | 21.4% | 14.9% | 6.5% |
| 2026 | 1947 | 1942 | 221 | 22.7% | 15.1% | 7.6% |

## Turnover por segmento

| Segmento | Realizado | Configurado (base) |
|---|---|---|
| corporate | 10.6% | 11.0% |
| customer | 28.0% | 30.0% |
| digital | 12.0% | 13.0% |
| retail_ops | 33.7% | 34.0% |
| supply | 21.2% | 22.0% |

## Carreira

| Ano | Taxa de promocao | Mobilidade interna | Movimentos por reorg |
|---|---|---|---|
| 2016 | 5.7% | 8.2% | 0 |
| 2017 | 5.9% | 6.2% | 0 |
| 2018 | 5.9% | 8.9% | 0 |
| 2019 | 4.6% | 7.7% | 0 |
| 2020 | 6.1% | 8.0% | 0 |
| 2021 | 4.3% | 8.4% | 0 |
| 2022 | 5.4% | 7.3% | 0 |
| 2023 | 5.2% | 8.6% | 200 |
| 2024 | 7.2% | 9.3% | 0 |
| 2025 | 5.1% | 8.0% | 1886 |
| 2026 | 4.9% | 8.3% | 0 |

## DEI

> Parametros sinteticos. Nao representam nenhuma populacao real.

| Ano | Mulheres no total | Mulheres em lideranca | Taxa de declaracao de raca e cor |
|---|---|---|---|
| 2016 | 54.5% | 50.9% | 0.0% |
| 2017 | 57.3% | 56.7% | 0.0% |
| 2018 | 55.1% | 49.9% | 0.0% |
| 2019 | 55.7% | 49.3% | 46.0% |
| 2020 | 53.9% | 45.1% | 74.3% |
| 2021 | 54.1% | 44.4% | 74.0% |
| 2022 | 54.3% | 44.1% | 72.7% |
| 2023 | 53.8% | 43.9% | 71.1% |
| 2024 | 53.2% | 42.4% | 71.0% |
| 2025 | 53.3% | 43.2% | 71.2% |
| 2026 | 53.5% | 43.7% | 71.9% |

## Recrutamento

- requisicoes: 4247, preenchidas 3617 (85%)
- candidaturas: 47629 (11.21 por requisicao)
- Time to Fill: media 87.8 dias, mediana 74
- Time to Hire: media 48.0 dias, mediana 41
- Offer Acceptance Rate: 73.8%

## Engajamento, aprendizagem e remuneracao

- pesquisas: 16724, taxa de resposta 66.5%, score medio 3.641
- nao respondentes com score preenchido: 0 (deve ser 0 na verdade)
- matriculas: 47801, conclusao obrigatoria 88.0%, opcional 61.0%
- compa-ratio recalculado: media 1.1442, p10 0.8523, p90 1.241

## Populacao

- individuos historicos: 4527
- versoes SCD2: 12357 (2.73 por pessoa)
- por origem: {'acquisition_comprafacil': 210, 'acquisition_vivamarket': 320, 'initial': 380, 'organic': 3617}

## Validacoes de coerencia

53 de 54 passaram.

| ID | Verificacao | Resultado |
|---|---|---|
| V01 | dim_employee tem exatamente um is_current por employee_id | OK |
| V02 | SCD2 sem sobreposicao de vigencia | OK |
| V03 | SCD2 sem buraco entre versoes | OK |
| V04 | primeira versao do SCD2 comeca na data de admissao | OK |
| V05 | termination_date nunca anterior a hire_date | OK |
| V06 | nenhuma admissao depois do fim da serie | OK |
| V07 | nenhum manager_id orfao na camada de verdade | OK |
| V08 | nenhum ciclo na linha de reporte | OK |
| V09 | exatamente uma pessoa ativa sem gestor (topo da hierarquia) | OK |
| V09b | so fica sem gestor quem nao tem ninguem de nivel superior ativo | OK |
| V10 | snapshot nunca antes da admissao | OK |
| V11 | snapshot nunca depois do desligamento | OK |
| V12 | snapshot sem duplicidade por employee_id e mes | OK |
| V13.fact_termination | fact_termination sem employee_id inexistente | OK |
| V13.fact_movement | fact_movement sem employee_id inexistente | OK |
| V13.fact_compensation | fact_compensation sem employee_id inexistente | OK |
| V13.fact_performance | fact_performance sem employee_id inexistente | OK |
| V13.fact_learning | fact_learning sem employee_id inexistente | OK |
| V13.fact_engagement | fact_engagement sem employee_id inexistente | OK |
| V14 | snapshot sem org_key inexistente | OK |
| V15.fact_movement | fact_movement sem evento fora do vinculo | OK |
| V15.fact_compensation | fact_compensation sem evento fora do vinculo | OK |
| V15.fact_performance | fact_performance sem evento fora do vinculo | OK |
| V15.fact_learning | fact_learning sem evento fora do vinculo | OK |
| V15.fact_engagement | fact_engagement sem evento fora do vinculo | OK |
| V16.fact_termination | fact_termination com chave unica ['termination_id'] | OK |
| V16.fact_movement | fact_movement com chave unica ['movement_id'] | OK |
| V16.fact_requisition | fact_requisition com chave unica ['requisition_id'] | OK |
| V16.fact_application | fact_application com chave unica ['requisition_id', 'candidate_id'] | OK |
| V16.dim_employee | dim_employee com chave unica ['employee_key'] | OK |
| V16.dim_organization | dim_organization com chave unica ['org_key'] | OK |
| V17 | promocao sempre eleva o nivel | OK |
| V18 | rebaixamento sempre reduz o nivel | OK |
| V19 | nao respondente tem score nulo, nunca zero | OK |
| V20 | respondente sempre tem score | OK |
| V21 | escala de performance correta para o periodo | OK |
| V22 | aprendizagem so existe apos a entrada do LMS | OK |
| V23 | Marketplace nao existe antes da aquisicao de 2022 | OK |
| V24 | nenhum salario nulo ou negativo | OK |
| V25 | candidatura com admissao implica oferta aceita | OK |
| V26 | requisicao preenchida sempre tem data de admissao | OK |
| V27 | admissao nunca anterior a abertura da requisicao | OK |
| V28 | headcount mensal dentro da tolerancia ajustada ao ruido amostral | OK |
| V28b | headcount acumulado dentro de 3% do plano | OK |
| V29 | pessoa vinda de aquisicao nunca aparece como contratacao | OK |
| V30 | share feminino cai da base para o topo da hierarquia | OK |
| V30b | sem inversao relevante no gradiente de genero entre niveis com n suficiente | OK |
| V31 | share de pessoas pretas e pardas cai da base para o topo no BR | OK |
| V32 | taxa de nao declaracao de raca e cor proxima do configurado por pais | OK |
| V33 | quem nao declarou nunca recebe valor de raca e cor imputado | OK |
| V34 | nenhuma declaracao de raca e cor antes de o campo existir | OK |
| V35 | share feminino na lideranca nao anda contra a tendencia configurada | FALHOU: variacao de -1.0% entre as pontas da serie pos-2021 |
| V36 | idade na admissao dentro da faixa configurada para o nivel | OK |
| V37 | nenhum genero presente na forca de trabalho some da lideranca | OK |
