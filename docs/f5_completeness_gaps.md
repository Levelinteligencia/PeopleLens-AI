# Lacunas de completude conhecidas, e o que elas impedem

Documento exigido pela decisão **DQ-01** no fechamento da F5: registrar a
ausência de `centro_custo` na folha como finding de completude permanente, e
documentar quais KPIs podem ser impactados.

> A regra que governa este documento: **uma lacuna conhecida e documentada é
> melhor que uma lacuna preenchida por conveniência.** Imputar centro de custo
> produziria um número que ninguém pode auditar, e o custo de descobrir isso
> tarde é maior que o custo de não responder agora.

---

## DQ-01: `centro_custo` ausente em `PAYROLL_BR.payroll_headcount_snapshot`

| | |
|---|---|
| **Check** | `DQ_COMP_012`, severidade WARNING, classe `INVALIDO` |
| **Situação** | 100% nulo, em 100.788 linhas |
| **Decisão** | manter como veio do RAW: não alterar o gerador, não imputar, não remover a coluna |
| **Status do check** | reprovado, permanentemente, até haver dado na fonte |

### O que a decisão preserva

Três coisas, e vale nomear as três porque cada uma corresponde a uma tentação
diferente:

1. **Não alterar o gerador** preserva a imutabilidade do RAW. Corrigir a origem
   apagaria a evidência de que o problema existiu, e o projeto inteiro é sobre
   a diferença entre um número e um número em que se pode confiar.
2. **Não imputar** preserva a diferença entre ausência e valor. Um centro de
   custo imputado por regra entraria em relatório financeiro com cara de fato.
3. **Não remover a coluna** preserva a declaração. A coluna existe no contrato
   da fonte; escondê-la faria o pipeline parecer completo e tornaria o problema
   invisível na próxima carga.

### O que continua possível

**O centro de custo existe e está completo nos dois HRIS.**

| Dataset | Coluna | Preenchimento |
|---|---|---|
| `HRIS_CORE.employee_master` | `cost_center` | 100% (4.111 de 4.111) |
| `HRIS_LEGACY.employee_master` | `CENTRO_CUSTO` | 100% (1.496 de 1.496) |
| `PAYROLL_BR.payroll_headcount_snapshot` | `centro_custo` | **0%** |

Então qualquer análise de **pessoas** por centro de custo continua viável pela
via do HRIS: headcount, FTE, turnover e distribuição por nível recortados por
centro de custo são todos respondíveis.

### O que fica impedido

O que a lacuna quebra não é a análise por centro de custo: é a **atribuição de
valor da folha a centro de custo**. A chave de atribuição só existe de um lado.

| KPI | Impacto | Severidade do impacto |
|---|---|---|
| `compa_ratio` | não pode ser recortado por centro de custo pela via da folha; o recorte por nível e país segue íntegro | **parcial** |
| `pay_gap` | idem: o recorte por centro de custo fica indisponível, o recorte por nível e gênero segue íntegro | **parcial** |
| `headcount`, `fte` | recorte por centro de custo funciona pelo HRIS, mas **não reconcilia** contra a folha nesse recorte | **parcial** |
| custo por FTE, custo por centro de custo | não calculáveis a partir da folha | **bloqueante**, e são KPIs ainda não contratados |
| `DQ_RECON_001` e `DQ_RECON_002` | não podem ser refinados por centro de custo; a reconciliação HRIS × folha continua só no nível país e período | **parcial** |

Nenhum dos 18 KPIs contratados fica bloqueado. O que fica bloqueado é uma
**família de recortes** e uma **família de KPIs financeiros** que ainda não
existe no catálogo. Registrar agora evita que alguém os contrate na F6 supondo
que o dado está lá.

### Como isso aparece na resposta ao usuário

Quando a F6 receber "qual o compa-ratio do centro de custo CC-BR-RET-03", a
resposta correta não é um número nem um erro genérico. É:

> Não consigo responder esse recorte. O centro de custo está completo no HRIS,
> mas ausente em 100% da folha, que é onde está o valor salarial. Posso
> responder compa-ratio por nível, por país ou por departamento.

Essa é a recusa útil do ADR-0015: dizer **o que seria necessário** para
responder, em vez de só recusar.

---

## Lacunas de cobertura do catálogo, sem decisão pendente

Registradas aqui para não se perderem, e sem ação nesta fase.

**206 dos 396 pares KPI × recorte são `INDETERMINADO`**, isto é, não têm nenhum
check aplicável ao recorte. Concentram-se em dois lugares:

- recortes por ano anteriores a 2019, quando só o HRIS legado existia e o
  catálogo tem menos checks sobre ele;
- sistemas com poucos checks próprios, como `ATS_CLOUD` fora dos datasets de
  requisição e candidatura.

`INDETERMINADO` é o comportamento correto (ausência de evidência não é evidência
de qualidade), e a lacuna é insumo do dimensionamento da F6.

---

## O que reabre este documento

| Gatilho | O que muda |
|---|---|
| a fonte passar a enviar `centro_custo` | o check volta a passar sozinho, sem tocar em nada |
| a onda 2 trazer `PAYROLL_LATAM` | a mesma verificação precisa ser feita lá antes de contratar KPI financeiro |
| alguém contratar KPI de custo | este documento é a razão pela qual ele nasce BLOCKED |
