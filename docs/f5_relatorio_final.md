# F5: relatório final

**Fase encerrada.** Perfil `dev` (escala 10%), seed `42`, commit versionado.
RAW intacto, nenhuma exceção promovida, nenhum limiar ajustado para fazer check
passar. Sem MCP, sem interface, sem F6 até nova autorização.

---

## 1. As quatro decisões aprovadas, e onde cada uma vive

| Decisão | O que fixa | Onde está aplicada |
|---|---|---|
| **DQ-01** | `centro_custo` fica exatamente como veio do RAW: sem alterar o gerador, sem imputar, sem remover a coluna. Finding de completude permanente, com impacto sobre KPIs documentado | `config/quality_checks.yaml` (`DQ_COMP_012`, campo `decision`), `docs/f5_completeness_gaps.md` |
| **DQ-02** | os 20 limiares provisionais **não** são congelados na F5; calibragem definitiva na F7, usando comportamento dos KPIs e distribuição de trust score como critério de negócio | `config/quality_checks.yaml`, `meta.thresholds_status: PROVISIONAL` e `meta.thresholds_decision` |
| **DQ-03** | `DESATUALIZADO` e `DIVERGENCIA` entram na taxonomia oficial de findings. Sete classes, e a taxonomia fecha aí | ADR-0022 Emenda 1, `config/quality_checks.yaml` (`approved_in` em cada classe) |
| **DQ-04** | calibragem da F7 por **recorte fino**; as bandas de trust score **não se movem** | **ADR-0023** (novo), `src/analytics/trust.py` (comentário na constante `BANDS`), `config/defects.yaml` (`trust_calibration_strategy`) |

Nenhuma das quatro mudou um número do pipeline. Isso é o esperado: as decisões
fixam **como o sistema deve se comportar**, e o comportamento já estava correto.
A saída da execução final é idêntica à da entrega anterior, com as justificativas
agora registradas no lugar onde alguém as lerá.

## 2. Os dez entregáveis

### 1. Relatório de DQ
`docs/f5_data_quality.md`. 87 checks, todos executados, 83 passando.

### 2. Catálogo completo de checks
`config/quality_checks.yaml`. Sete dimensões, cinco sistemas da onda 1, 21
expectativas distintas. Cada check declara `threshold_basis`: 49 invariantes, 18
derivados, 20 provisionais (estes últimos não congelados, por DQ-02).

### 3. Severidade e comportamento de cada check

| Severidade | Checks | Efeito |
|---|---|---|
| BLOCKER | 22 | linha vai para quarentena, não entra no analítico |
| CRITICAL | 40 | linha entra, e o check derruba o trust score do KPI dependente |
| WARNING | 22 | registra e monitora, não afeta trust score |
| INFO | 3 | apenas observabilidade |

A quarentena é acionada **por regra**, não por resultado agregado: a linha
reprovada por um BLOCKER sai mesmo que o check tenha passado dentro do limiar.

### 4. Trust Score e sua lógica

```
perda_total   = média ponderada das taxas de falha dos checks BLOCKER e CRITICAL
                das dependências do KPI, com peso = records_checked no recorte
trust_score   = 1 − perda_total
perda[classe] = contribuição daquela classe; as contribuições SOMAM perda_total
```

Fora do score por decisão, não por omissão: `AUSENCIA_LEGITIMA` (penalizar não
declaração viraria pressão por preenchimento), `WARNING` e `INFO` (ADR-0010), e
a supressão por n mínimo (privacidade, ADR-0007, em campo próprio).

Par sem check aplicável recebe `INDETERMINADO`, nunca `CERTIFIED`.

### 5. Impacto das pendências sobre o Trust Score

Média sobre os 190 pares respondíveis: **perda por erro 0,00038, perda por
pendência 0,01097.** A confiança que falta neste dataset vem de decisão em
aberto, não de dado errado — e há número atrás da frase.

A leitura fina, na população da aquisição (perda por erro **zero** em todas as
linhas):

| KPI | Trust | Status | Por que a resposta muda |
|---|---|---|---|
| `turnover_rate` | 0,353 | **BLOCKED** | exige seguir a mesma pessoa ao longo do tempo, entre sistemas |
| `compa_ratio` | 0,623 | LIMITED | precisa cruzar folha com cadastro |
| `headcount` | 0,741 | LIMITED | contar 320 pessoas não exige identidade resolvida |
| `promotion_rate` | 0,869 | LIMITED | |
| `women_in_leadership` | 0,869 | LIMITED | |

Mesma população, mesma qualidade de dado, respostas diferentes, porque a
pergunta é diferente.

### 6. Quarentena
8 linhas (0,005% do volume), todas de `HRIS_LEGACY.employee_master`, todas
acionadas por `DQ_VALID_001` e todas de classe `INVALIDO`. Dentro do critério de
saída de `defects.yaml`: não vazia e abaixo de 3%. Cada linha continua intacta na
camada conformada, com a regra que a reprovou anexada.

### 7. Reconciliações
8 checks, nenhum reprovando. A principal, HRIS × folha, sai em **0,966 em todos
os 86 meses** depois de igualar escopo dos dois lados — exatamente a divergência
que o `population_rule` da folha prevê.

### 8. Testes
**106 testes, todos passando**, 28 novos na F5. Os que respondem ao pedido de
garantir que DQ não altera o dado:

- `test_runner_nao_altera_nenhuma_frame`: compara as frames valor a valor antes
  e depois dos 87 checks;
- `test_trust_score_nao_altera_nenhuma_frame`: o mesmo para o cálculo de confiança;
- `test_quarentena_e_desvio_lateral_e_nao_filtro_destrutivo`;
- `test_pendencia_nunca_manda_registro_para_a_quarentena`;
- `test_check_sobre_coluna_inexistente_vira_not_run_e_nunca_pass`;
- `test_perda_por_classe_soma_a_perda_total`;
- mais o guarda de sessão da F4, que reprova a suíte inteira se ela tocar em
  `data/raw`, `data/synthetic/truth` ou `data/reference`.

### 9. Achados inesperados
Cinco, em `docs/f5_validation_findings.md`. Quatro estão no instrumento de
medição, não no dado:

1. **a reconciliação passava por coincidência de dois erros** — comparava cinco
   países contra a folha de um país, em janelas de vigência diferentes, e as
   duas distorções se cancelavam dentro de uma faixa que aprovava;
2. **o check de identidade do ATS comparava chaves diferentes**, produzindo 100%
   plausível;
3. **`centro_custo` 100% nulo em 100.788 linhas**, atravessando três fases sem
   ser visto — agora regido por DQ-01;
4. **o trust score como produto de componentes explodia**, derrubando `pais=BR`
   inteiro por causa de um check sobre 320 linhas;
5. **distribuição de confiança fora da faixa-alvo**, com causa mecânica
   identificada — agora regida por DQ-04 e ADR-0023.

Os achados 1 e 2 desta fase e os achados 1 e 2 da F3 são o mesmo mecanismo:
**uma comparação entre coisas não comparáveis produzindo um número plausível.**
Quatro vezes em três fases, que é a falha característica de um sistema cujo
trabalho é comparar fontes heterogêneas. Agora existe guarda para as quatro.

### 10. Decisões que precisam de você antes da F6
Ver seção 5.

## 3. Documentação e ADRs atualizados

| Artefato | Estado |
|---|---|
| `docs/f5_data_quality.md` | atualizado com as quatro decisões |
| `docs/f5_validation_findings.md` | cinco achados |
| `docs/f5_completeness_gaps.md` | **novo**, exigido por DQ-01 |
| `docs/technical_design_v0.4_delta.md` | **novo**: o que F4 e F5 mudaram na linha de base v0.3 |
| ADR-0022 | **Emenda 1**: taxonomia oficial de sete classes (DQ-03) |
| ADR-0023 | **novo**: calibragem por recorte fino, bandas preservadas (DQ-04) |
| `docs/adr/README.md` | índice com 23 ADRs e as seis fases cobertas |

A SPEC foi atualizada como **delta sobre a v0.3**, e não como reescrita. A v0.3
continua sendo a linha de base aprovada: reescrever um documento aprovado de
95 KB para acomodar mudanças pontuais é a forma mais eficiente de perder o rastro
de qual decisão mudou o quê.

## 4. O commit

Primeiro commit versionado do projeto desde a estrutura inicial. Vai tudo que as
seis fases produziram: F0 a F5 num único commit de fase, porque as fases
anteriores nunca foram versionadas.

**O que entra:** `src/`, `config/` (incluindo os 18 contratos de KPI), `tests/`,
`docs/` (23 ADRs e os relatórios de todas as fases), `Makefile`,
`requirements.txt`, e `data/reference/*.csv`.

Os CSVs de referência entram porque o ADR-0009 os define como a trilha de
auditoria dos mapeamentos aprovados: o histórico do Git **é** o registro de quem
aprovou o quê e quando.

**O que não entra:** `data/raw/`, `data/synthetic/`, `data/processed/` e
`data/governance/`.

Essa é uma decisão que você deixou em aberto no `.gitignore` inicial ("quando o
volume da base sintética for definido, decidiremos juntos"). O volume agora é
conhecido — 42 MB no perfil `dev`, e dez vezes isso no perfil completo — e o
critério que aplico é o do próprio projeto: **tudo isso é reproduzível a partir
do seed e da configuração**, e o manifesto carrega `seed`, `profile`, `scale` e
`config_hash` justamente para provar isso. Versionar saída regenerável faria o
repositório crescer 42 MB a cada execução, sem acrescentar informação.

É reversível com uma linha no `.gitignore`, e fica registrada aqui como decisão
minha para você confirmar ou derrubar.

## 5. O que precisa de decisão sua antes da F6

| # | Assunto | Por que precisa de você |
|---|---|---|
| 1 | Versionamento dos dados gerados | apliquei o critério de reprodutibilidade; é a decisão que você tinha deixado em aberto |
| 2 | Cobertura do catálogo: 206 dos 396 pares em `INDETERMINADO` | não é falha do score, é lacuna de checks nos recortes anteriores a 2019 e nos sistemas com poucos checks próprios. Dimensiona parte da F6 |
| 3 | KPIs financeiros por centro de custo | nascem BLOCKED enquanto DQ-01 valer; se a F6 for contratá-los, você precisa saber disso antes |
| 4 | Escopo da F6 | a camada semântica e de KPIs pode assumir o trust score como está, mas as bandas só se confirmam na F7 |
| 5 | `minimum_n` ainda não exercitado | a população dos recortes hoje é contagem de linhas avaliadas, não de pessoas distintas. A supressão por privacidade só vira real quando os KPIs calcularem sobre pessoas, na F6 |

---

## Estado do projeto ao fim da F5

| | |
|---|---|
| fases concluídas | F0, F1, F2, F3, F4, F5 |
| ADRs | 23 |
| checks de qualidade | 87, 83 passando |
| contratos de KPI | 18, zero inconsistências, zero checks órfãos |
| testes | 106, todos passando |
| linhas processadas | 300.419 no perfil `dev` |
| transformações rastreadas individualmente | 280.727 |
| exceções de mapeamento abertas | 57 |
| decisões de identidade pendentes | 1.845 |
| promoções automáticas | **zero**, desde o primeiro dia |
