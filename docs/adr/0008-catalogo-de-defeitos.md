# ADR-0008: Catálogo de defeitos, estrutura aprovada e taxas provisórias

- **Status:** Parcial (Parte A aceita e emendada em 11/09/2026; Parte B em aberto até a **F7**)
- **Data:** 2026-09-11
- **Decisão relacionada:** D8 (Technical Design v0.3)
- **Fase:** F0 para a Parte A, fim da F2 para a Parte B

## Contexto

O dataset precisa de defeitos com causa declarada, e não de corrupção
aleatória. Isso tem duas partes de naturezas diferentes.

A **estrutura** do catálogo (quais tipos de defeito existem, de qual incidente
cada um decorre, qual sistema o carrega e qual população afeta) é modelagem.

As **taxas numéricas** são calibragem. E calibragem tem uma propriedade
incômoda: depois de fixada, ela vira o **gabarito** contra o qual toda a
performance do pipeline é medida.

O efeito de uma taxa no trust score final não é previsível no papel, porque os
defeitos interagem. D09 (manager órfão) e D10 (departamento extinto) se
sobrepõem depois de uma reorganização, e o efeito combinado sobre um KPI que
depende dos dois não é a soma dos efeitos isolados.

Errar para baixo produz um pipeline bonito e um projeto vazio: fila de exceções
quase vazia, quarentena sem uso, todos os KPIs verdes, e a demonstração mais
importante, a da IA recusando responder, sem como acontecer. Errar para cima
produz um sistema que nunca responde e que parece quebrado em vez de
criterioso.

## Decisão

**Parte A, aceita.** A estrutura do catálogo está fechada: 23 tipos de defeito
mais o `D_DEFINITION_DRIFT`, cada um com causa raiz apontando para um incidente
ou prática declarada, sistemas de origem, escopo e checks que o detectam. Está
em `config/defects.yaml`.

**Parte B, em aberto.** As taxas numéricas entram no mesmo arquivo como
parâmetros **provisórios** (`meta.rates_status: PROVISIONAL`) e são calibradas
ao final da F2, rodando o universo no perfil `dev` (10% do volume), contra uma
**distribuição alvo de trust score**:

| Faixa | Alvo | Concentração esperada |
|---|---|---|
| CERTIFIED | 60% a 70% | Brasil e Corporate, 2021 em diante |
| LIMITED | 20% a 25% | janela da migração de 2019, países menores |
| BLOCKED | 10% a 15% | populações VivaMarket e CompraFácil, 2016 a 2018 |

A percepção que sustenta essa inversão: **as taxas não devem ser escolhidas por
realismo isolado; realismo é restrição, a distribuição é o objetivo.**

Ao final da F2 as taxas são congeladas (`rates_status: FROZEN`), com data e
referência a um ADR de fechamento, e passam a ser o gabarito oficial.

Duas taxas exigem atenção especial na calibragem:

- **D03** (raça e cor não informada, 24% a 35%): governa todos os KPIs de DEI e
  interage com o n mínimo do ADR-0007. É a mais sensível do catálogo.
- **D11** (divergência HRIS versus Payroll, 2% a 5%): governa a reconciliação,
  o check mais visível da demonstração. Abaixo de 2% ninguém percebe; acima de
  8% parece erro de implementação em vez de realidade organizacional.

## Alternativas consideradas

1. **Fixar as taxas agora, por julgamento.** Era a proposta da v0.1 do Technical
   Design. Revista pelo argumento de interação entre defeitos.
2. **Calibrar por benchmark de mercado.** Não existe benchmark público confiável
   de taxa de defeito em dados de RH por tipo de defeito. Qualquer número
   citado seria invenção com aparência de fonte.
3. **Calibrar iterativamente contra a distribuição alvo.** Escolhida.

## Consequências

**Positivas**

- A estrutura destrava a F0, a F1 e a F2 sem depender da calibragem.
- A calibragem acontece com evidência, no perfil reduzido, que é barato de
  regerar.
- Os critérios de saída ficam objetivos e verificáveis (ver
  `calibration.exit_criteria` em `config/defects.yaml`).

**Negativas**

- O gabarito só existe ao final da F2, então nenhuma afirmação de acurácia pode
  ser feita antes disso.

**Riscos e mitigação**

- *Risco:* a calibragem não convergir e virar ajuste infinito. *Mitigação:*
  critérios de saída explícitos e um teto de três rodadas; se não convergir,
  a decisão volta para a Sam com os resultados das três.
- *Risco:* alterar taxa depois da F7 exigiria regerar tudo. *Mitigação:* o
  congelamento ao final da F2 é anterior a qualquer volume completo.

## Emenda 1, 11/09/2026: reconciliação entre `sources.yaml` e `defects.yaml`

**Aprovada pela Sam na aprovação da F2.**

A F2 revelou que os dois arquivos de configuração descreviam o mesmo fenômeno
sem se referenciarem. `sources.yaml` já declarava, na metadata de cada sistema:

- `VIVAMARKET_LEGACY.gender_values: ["MASC", "FEM"]`, que é domínio divergente
  de gênero, ou seja, D01;
- `VIVAMARKET_LEGACY`, com departamento de digitação livre, ou seja, D04;
- `ATS_CLOUD.enterprise_id_fill_rate: 0.63`, que é ausência do ID corporativo,
  ou seja, D05.

Nenhum dos três constava em `source_systems` do defeito correspondente. Não era
divergência de opinião entre os arquivos, era omissão em um deles.

**Alterações incorporadas à Parte A:**

| Defeito | `source_systems` antes | depois |
|---|---|---|
| D01 | HRIS_LEGACY, HRIS_CORE | + VIVAMARKET_LEGACY |
| D04 | HRIS_LEGACY | + VIVAMARKET_LEGACY |
| D05 | VIVAMARKET_LEGACY, COMPRAFACIL_ERP | + ATS_CLOUD |
| D_DEFINITION_DRIFT | (sem `source_systems`) | HRIS_CORE, HRIS_LEGACY, COMP_PLAN |

A validação **R02** ("todo defeito ocorre só em sistema que declara carregá-lo")
passa a ser a guarda permanente contra esse tipo de omissão: qualquer defeito
injetado em sistema não declarado quebra a fase.

## Emenda 2, 11/09/2026: a Parte B fecha na F7, não na F2

**Aprovada pela Sam na aprovação da F2.**

Os critérios de saída desta decisão referenciam a distribuição de trust score, e
trust score só existe a partir da F7. O plano original de congelar as taxas ao
final da F2 era, portanto, irrealizável como escrito.

O que a F2 **pôde** verificar, e verificou, é outra coisa e continua valendo: a
taxa realizada de cada defeito bate com a esperada, medida por defeito, sistema
e dataset, com o ledger contando tentativas e não só acertos.

**Decisão:** `meta.rates_status` permanece `PROVISIONAL` até a F7. O
congelamento acontece lá, quando trust score e suas dependências existirem, e o
critério de fechamento é o já declarado em `calibration.exit_criteria`.

Consequência assumida: nenhuma afirmação de acurácia do pipeline contra o
gabarito pode ser feita antes da F7, e uma recalibragem naquele ponto pode
exigir regerar o dataset.

## Referências

- Technical Design v0.3, seções 8 e 18 (D8)
- Especificação do Universo v1.0, seção 25
- `config/defects.yaml`, `config/incidents.yaml`
- `docs/f2_defect_coverage.md`, `docs/f2_validation_findings.md`
