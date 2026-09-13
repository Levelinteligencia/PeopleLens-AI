# F5: Data Quality, severidade, quarentena, reconciliação e Trust Score

Perfil `dev` (escala 10%), seed `42`. RAW intacto, nenhuma exceção promovida,
nenhum threshold ajustado para fazer check passar.

> Princípio que governa a fase, fixado por você na abertura:
> **dado inválido ≠ dado não mapeado ≠ decisão pendente ≠ identidade não
> resolvida ≠ dado quarentenado.** O fato de um valor não estar resolvido não
> significa que ele esteja errado; significa que existe uma decisão ou
> evidência pendente.

---

## 1. O catálogo

87 checks, todos executados, 83 passaram.

| Dimensão | Checks | Falhas |
|---|---|---|
| Validity | 21 | 1 |
| Consistency | 16 | 1 |
| Completeness | 15 | 1 |
| Referential Integrity | 12 | 1 |
| Uniqueness | 9 | 0 |
| Reconciliation | 8 | 0 |
| Timeliness | 6 | 0 |

21 expectativas distintas, cobrindo os cinco sistemas da onda 1. Nenhum check
ficou `NOT_RUN`: um catálogo com checks que nunca rodam parece cobertura e não é.

### Três atributos, três perguntas diferentes

| Atributo | Responde |
|---|---|
| `threshold` | **quando** o check reprova |
| `severity` | **o que acontece** com a linha reprovada (ADR-0010) |
| `finding_class` | **que natureza** tem o problema (ADR-0022, novo na F5) |

`threshold_basis` diz de onde veio cada limiar, porque limiar sem base declarada
é palpite, e palpite que ninguém marcou como palpite vira fato em três meses:

| Base | Checks | O que significa |
|---|---|---|
| `invariante` | 49 | 0.0 estrutural: chave duplicada, saída antes da entrada |
| `derivado` | 18 | calculado de `defects.yaml`, `sources.yaml` ou `generation.yaml` |
| `provisional` | 20 | palpite fundamentado, a calibrar na F7 |

## 2. Severidade e comportamento

| Severidade | Checks | Efeito |
|---|---|---|
| BLOCKER | 22 | linha vai para quarentena, não entra no analítico |
| CRITICAL | 40 | linha entra, e o check derruba o trust score do KPI dependente |
| WARNING | 22 | registra e monitora, não afeta trust score |
| INFO | 3 | apenas observabilidade |

A quarentena é acionada **por regra, não por resultado agregado**: a linha
reprovada por um check BLOCKER sai mesmo que o check como um todo tenha passado
dentro do limiar. O limiar governa o status do check; a severidade governa o
destino da linha.

## 3. As classes de achado

| Classe | Pendência? | Checks | Falhas |
|---|---|---|---|
| `INVALIDO` | não | 54 | 1 |
| `NAO_MAPEADO` | sim | 11 | 1 |
| `DIVERGENCIA` | não | 10 | 0 |
| `DESATUALIZADO` | sim | 5 | 0 |
| `IDENTIDADE_NAO_RESOLVIDA` | sim | 4 | 1 |
| `AUSENCIA_LEGITIMA` | sim | 2 | 0 |
| `DECISAO_PENDENTE` | sim | 1 | 1 |

Três desigualdades da sua lista viraram teste executável:

- **decisão pendente ≠ dado quarentenado**: classe de pendência nunca pode ter
  severidade BLOCKER, e o teste reprova o catálogo se alguém declarar uma. Tirar
  do analítico uma linha cujo único problema é um mapeamento não aprovado
  apagaria dado correto por causa de uma fila de trabalho.
- **não mapeado ≠ decisão pendente**: `Mktg` sem mapa é fila de trabalho;
  `N4` da VivaMarket é pergunta sem resposta técnica. As duas viram `UNMAPPED` e
  não são a mesma coisa — a primeira alguém resolve, a segunda alguém decide.
- **identidade não resolvida ≠ dado inválido**: todo check de cobertura de
  identidade é obrigado a declarar `IDENTIDADE_NAO_RESOLVIDA`.

## 4. Os quatro checks reprovados

| Check | Severidade | Classe | Taxa | Limite | Linhas |
|---|---|---|---|---|---|
| `DQ_REF_008` identidade resolvida na aquisição | CRITICAL | IDENTIDADE_NAO_RESOLVIDA | 100,00% | 0% | 320 |
| `DQ_CONS_006` departamento da aquisição mapeado | CRITICAL | NAO_MAPEADO | 29,38% | 10% | 94 |
| `DQ_VALID_006` job level da aquisição mapeado | CRITICAL | DECISAO_PENDENTE | 13,12% | 10% | 42 |
| `DQ_COMP_012` centro de custo na folha | WARNING | INVALIDO | 100,00% | 5% | 100.788 |

Os três primeiros são a aquisição VivaMarket, e nenhum deles é dado errado:
são vínculo pendente, tradução pendente e decisão de negócio pendente.

Os quatro continuam reprovando **por decisão**, e cada um por um motivo
diferente:

| Check | Decisão que o mantém reprovado |
|---|---|
| `DQ_VALID_006` | `N4` e `N5` seguem sem mapeamento aprovado; o limiar não se move |
| `DQ_CONS_006` | as 12 traduções pendentes da F4 seguem sem candidato automático |
| `DQ_REF_008` | identidade da aquisição não se resolve por similaridade |
| `DQ_COMP_012` | DQ-01: `centro_custo` fica como veio do RAW, sem imputação |

O impacto do quarto sobre os KPIs está em `docs/f5_completeness_gaps.md`,
conforme exigido por DQ-01.

## 5. Quarentena

8 linhas, todas de `HRIS_LEGACY.employee_master`, 0,005% do volume — dentro do
critério de saída de `defects.yaml` (não vazia e abaixo de 3%).

| Regra acionadora | Classe | Linhas |
|---|---|---|
| `DQ_VALID_001` data de admissão não convertida | INVALIDO | 8 |

Todas de classe `INVALIDO`, como tem que ser. Cada linha continua **intacta na
camada conformada** com a regra que a reprovou anexada, e sai apenas do
analítico: desvio lateral, não filtro destrutivo.

## 6. Reconciliações

8 checks, nenhum reprovando. Duas famílias:

| Forma | O que faz |
|---|---|
| `expect_row_count_ratio_between` | razão agregada entre duas fontes |
| `expect_group_count_ratio_between` | razão **período a período**, com `join` interno |

A segunda existe porque a primeira esconde duas coisas. Compensação, primeiro:
um mês 20% acima e outro 20% abaixo fecham em zero. Diferença de vigência,
depois: período em que só uma das fontes existe entra no total e dilui a razão.

| Check | Comparação | Resultado |
|---|---|---|
| `DQ_RECON_001` | headcount BR do HRIS × folha, janela de sobreposição | razão 0,966 |
| `DQ_RECON_002` | o mesmo, mês a mês | 0,966 em **todos** os 86 meses |
| `DQ_RECON_005` | HRIS legado × corporativo na migração de 2019 | dentro da faixa |
| `DQ_RECON_006` | eventos de remuneração × população da folha | dentro da faixa |

O 0,966 constante é exatamente a divergência que o `population_rule` da folha
prevê: ela inclui terceiro, estagiário e aviso prévio, e exclui afastado longo.
Chegar a esse número exigiu corrigir o escopo dos dois lados — ver o achado 1.

## 7. Trust Score

### A lógica

```
perda_total   = média ponderada das taxas de falha dos checks BLOCKER e CRITICAL
                das dependências do KPI, com peso = records_checked no recorte
trust_score   = 1 − perda_total
perda[classe] = contribuição daquela classe; as contribuições SOMAM perda_total
```

O que o score deixa de fora, e por quê:

- **`AUSENCIA_LEGITIMA` não entra em nenhum componente.** Penalizar a confiança
  porque alguém optou por não declarar raça, cor ou deficiência transformaria o
  trust score em pressão por preenchimento. A taxa é reportada ao lado do
  número, como contexto de leitura, nunca como desconto.
- **WARNING e INFO não entram**, por ADR-0010.
- **Supressão por n mínimo fica em campo próprio.** É recusa por privacidade
  (ADR-0007), não por qualidade: "o grupo é pequeno demais para preservar
  anonimato" é uma frase diferente de "não confio no dado".
- **Par sem nenhum check aplicável recebe `INDETERMINADO`, nunca `CERTIFIED`.**
  Ausência de evidência não é evidência de qualidade.

`quality_score` na forma do ADR-0011 (validade × cobertura) continua calculado e
reportado, para continuidade com aquele ADR.

### Recortes

18 contratos de KPI × 22 recortes = 396 pares. Três famílias de recorte, e a
terceira é a que importa: `origem`, o sistema de origem, porque isola
exatamente as populações de confiança diferente.

| | |
|---|---|
| pares avaliados | 396 |
| respondíveis | 190 |
| `INDETERMINADO`, sem check aplicável | 206 |
| suprimidos por n mínimo | 0 |

### Distribuição

| Status | Pares respondíveis | Share |
|---|---|---|
| CERTIFIED | 184 | 96,8% |
| LIMITED | 5 | 2,6% |
| BLOCKED | 1 | 0,5% |

Trust médio 0,9887. **Perda média por erro 0,00038; por pendência 0,01097.** A
confiança que falta neste dataset vem majoritariamente de decisão em aberto, não
de dado errado — e essa é a frase que o projeto inteiro existe para conseguir
dizer com número atrás.

A distribuição está longe da faixa-alvo de `defects.yaml` (CERTIFIED 60–70%). A
calibragem é declaradamente da F7, e por **DQ-04** ela acontece por recorte
fino, com as bandas preservadas: mexer no limiar até a distribuição fechar
produziria o resultado desejado numa tarde e destruiria o significado do número
(ADR-0023).

## 8. O impacto das pendências, visto de perto

A mesma população, seis KPIs, seis respostas diferentes:

| KPI | Recorte | Trust | Status | Perda por erro | Perda por pendência |
|---|---|---|---|---|---|
| `turnover_rate` | origem=VIVAMARKET | 0,353 | **BLOCKED** | 0,000 | 0,647 |
| `compa_ratio` | origem=VIVAMARKET | 0,623 | LIMITED | 0,000 | 0,377 |
| `headcount` | origem=VIVAMARKET | 0,741 | LIMITED | 0,000 | 0,259 |
| `promotion_rate` | origem=VIVAMARKET | 0,869 | LIMITED | 0,000 | 0,131 |
| `women_in_leadership` | origem=VIVAMARKET | 0,869 | LIMITED | 0,000 | 0,131 |
| `headcount` | origem=HRIS_CORE | 1,000 | CERTIFIED | 0,000 | 0,000 |

**Perda por erro zero em todas as linhas.** Os dados da VivaMarket não estão
errados. O que falta é decisão e vínculo.

E a leitura por KPI é a demonstração que o projeto persegue: contar 320 pessoas
da aquisição não exige identidade resolvida entre sistemas, então `headcount`
responde com ressalva. Calcular turnover exige seguir a mesma pessoa ao longo do
tempo, através de sistemas, então `turnover_rate` não responde. Mesma população,
mesma qualidade de dado, respostas diferentes — porque a pergunta é diferente.

`compa_ratio` para `pais=AR` sai em 0,833 (LIMITED, pendência pura), que é o
custo de mapeamento de departamento ainda aberto naquele recorte.

## 9. Testes

106 testes no total, 28 novos na F5. Os que respondem diretamente ao seu item 9:

| Teste | O que prova |
|---|---|
| `test_runner_nao_altera_nenhuma_frame` | compara as frames valor a valor antes e depois de rodar os 87 checks |
| `test_trust_score_nao_altera_nenhuma_frame` | o mesmo para o cálculo de confiança |
| `test_quarentena_e_desvio_lateral_e_nao_filtro_destrutivo` | a linha sai do analítico e continua na camada conformada |
| `test_pendencia_nunca_manda_registro_para_a_quarentena` | classe de pendência não pode ser BLOCKER |
| `test_check_sobre_coluna_inexistente_vira_not_run_e_nunca_pass` | erro de digitação não vira check aprovado |
| `test_perda_por_classe_soma_a_perda_total` | a atribuição é exata, não decorativa |
| `test_ausencia_legitima_nunca_penaliza_a_confianca` | não declarar não desconta confiança |
| `test_identidade_com_chave_incompativel_nao_vira_cem_por_cento` | a guarda do achado 2 |
| `test_reconciliacao_entre_sistemas_iguala_o_escopo` | a guarda do achado 1 |

Mais o guarda de sessão da F4, que reprova a suíte inteira se ela tocar em
`data/raw`, `data/synthetic/truth` ou `data/reference`.

## 10. Artefatos

| Arquivo | Conteúdo |
|---|---|
| `config/quality_checks.yaml` | 87 checks, 7 classes de achado, base de cada limiar |
| `config/kpis/*.yaml` | 18 contratos com `depends_on_checks` e `depends_on_mappings` |
| `src/analytics/contracts.py` | derivação e verificação nos dois sentidos |
| `src/analytics/trust.py` | trust score, recortes, atribuição da perda |
| `src/quality/runner.py` | 21 expectativas, recorte declarado, execução por recorte |
| `data/processed/metadata/kpi_trust_score.parquet` | 396 pares KPI × recorte |
| `data/processed/metadata/data_quality_results.parquet` | resultado dos 87 checks |
| `data/processed/metadata/data_quarantine.parquet` | 8 linhas desviadas |
| `docs/adr/0022-*.md` | classe de achado e natureza da perda |
| `docs/adr/0023-*.md` | calibragem por recorte fino, bandas preservadas |
| `docs/f5_completeness_gaps.md` | lacunas de completude e KPIs impactados (DQ-01) |
| `docs/technical_design_v0.4_delta.md` | o que F4 e F5 mudaram na linha de base v0.3 |

`depends_on_checks` **não é digitado**: é derivado de `consumed_by_kpis` no
catálogo, e `contracts.verify` reprova nos dois sentidos — check órfão e
contrato apontando para check inexistente. Zero inconsistências, zero órfãos.
