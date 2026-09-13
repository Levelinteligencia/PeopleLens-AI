# F5: o que a camada de qualidade encontrou

Quinta edição do registro de achados. Mesmo princípio das quatro anteriores: os
erros ficam documentados porque uma camada de validação que nunca falhou não
provou nada.

A F5 teve cinco achados. Quatro estão no instrumento de medição, não no dado,
e três deles têm a mesma assinatura: **um número plausível, produzido por uma
comparação inválida, que ninguém questionaria porque o número parece razoável.**

---

## Achado 1: a reconciliação passava por coincidência de dois erros

| | |
|---|---|
| **Encontrado por** | `DQ_RECON_002`, a versão mês a mês da reconciliação |
| **Sintoma** | o total passava com razão 1,068; 79% dos meses ficavam fora da faixa |
| **Severidade** | **crítica**, e a mais perigosa da fase |

### O que acontecia

`DQ_RECON_001` comparava `HRIS_CORE.headcount_snapshot` contra
`PAYROLL_BR.payroll_headcount_snapshot` e passava com folga: razão 1,068 dentro
da faixa de 0,90 a 1,10. Parecia dizer que HRIS e folha concordam.

Não dizia nada disso. O HRIS corporativo cobre **cinco países** e começa em
**maio de 2019**; a folha cobre **o Brasil** e começa em **2016**. O check
comparava dois recortes diferentes do mundo e chamava a diferença de
concordância.

Dois erros de escopo, em direções opostas, se cancelando:

| Comparação | Razão | Veredito |
|---|---|---|
| tudo × tudo (o que estava no catálogo) | 1,068 | **passa** |
| só BR × folha, total | 0,799 | reprovaria |
| só BR × folha, **mês a mês** | 0,966 em todos os 86 meses | passa, e mede o que deve |

Os períodos em que só a folha existe inflavam o denominador e puxavam a razão
global para dentro da faixa. Ao mesmo tempo, os cinco países contra um país
puxavam para cima. As duas distorções se anularam numa faixa que aprovava.

A versão mês a mês, que eu tinha acrescentado para pegar compensação entre
períodos, reprovou em 79% dos meses e foi o que revelou tudo. Os dados mensais
mostravam a razão subindo de 1,09 em 2019 para 1,42 em 2026: não era ruído, era
a expansão internacional aumentando a distância entre uma empresa de cinco
países e uma folha de um país.

### A correção

Não foi mexer no limiar. Foi **igualar o escopo dos dois lados antes de
comparar**, com recorte declarado no YAML:

```yaml
filter:           {column: std_country, equals: BR}
reference_filter: {column: dt_competencia__iso, min: "2019-05-01"}
```

Com escopo igualado, a razão é **0,966 em todos os 86 meses**, sem um único mês
fora da faixa. Esse número é a divergência que o `population_rule` da folha
prevê em `sources.yaml`: ela inclui terceiro, estagiário e aviso prévio, e
exclui afastado de longa duração. O check voltou a medir o que se propõe a
medir, e o que ele mede bate com o que a configuração declara.

### A lição, que vale para toda reconciliação

**Reconciliar duas fontes sem igualar vigência e população mede a diferença de
escopo, não a diferença de dado.** E todo sistema deste projeto tem vigência e
população diferentes: é a premissa do universo NOVAORA.

Guarda criada: `test_reconciliacao_entre_sistemas_iguala_o_escopo` exige que os
checks que cruzam sistemas declarem recorte, e a comparação mês a mês usa `join`
interno, que por construção só compara período existente dos dois lados.

---

## Achado 2: o check de identidade comparava chaves diferentes

| | |
|---|---|
| **Encontrado por** | `DQ_REF_010`, cobertura de identidade do ATS |
| **Sintoma** | 100,00% de identidade não resolvida |

### O que acontecia

O check comparava `ATS_CLOUD.application.employee_id` contra o conjunto de
chaves resolvidas no `xref`. Mas o `xref` indexa o ATS por `candidate_id`
(`CAND00014524`), não por `employee_id` (`1451`), porque a maioria das
candidaturas nunca teve employee_id.

Interseção zero. Resultado: 100% de não resolvido.

### Por que é a mesma família do achado 1

O número é **plausível**. O ATS é o sistema de identidade mais fraca do
universo, com `enterprise_id_fill_rate: 0.63` declarado em `sources.yaml`. Um
relatório dizendo "100% da população do ATS sem identidade resolvida" seria lido
e aceito, e a taxa real, 95,18%, está perto o bastante para ninguém desconfiar.

É o mesmo mecanismo do achado 2 da F3, onde a referência errada produzia 23% de
órfãos falsos: **a comparação errada produz um número no lugar certo.**

### A correção

Duas, em camadas diferentes. A especificação apontou para `candidate_id`, que é
a chave certa. E, mais importante, `expect_identity_resolved` ganhou uma guarda:
se a coluna declarada não tem **nenhuma** interseção com o universo de chaves
daquele sistema, o check não está medindo cobertura baixa, está comparando
coisas diferentes. Nesse caso ele não roda, e aparece como `NOT_RUN` em vez de
100% de falha.

`NOT_RUN` é um estado desconfortável e é o correto: um check que não rodou não é
evidência de qualidade, e o relatório separa os dois.

---

## Achado 3: uma coluna que nunca teve dado, em três fases

| | |
|---|---|
| **Encontrado por** | `DQ_COMP_012`, centro de custo presente no snapshot da folha |
| **Sintoma** | 100% nulo em 100.788 linhas |

`centro_custo` está declarado em `sources.yaml` como coluna de
`PAYROLL_BR.payroll_headcount_snapshot`, está declarado em
`standardization.yaml` como coluna de texto, foi perfilado na F3, atravessou a
padronização e o DE/PARA, e **nunca carregou um único valor**. O gerador da F2
não preenche o campo.

Três fases de pipeline, 49 achados de profiling, e ninguém viu — porque uma
coluna vazia não quebra nada. Ela só existe.

### O que não foi feito

**Não corrigi o gerador.** Preencher a coluna mudaria o RAW, e o RAW é imutável
por decisão sua. O check fica reprovando, com severidade WARNING, e a decisão de
preencher ou de remover a coluna da declaração é sua — está na lista da seção
final.

O achado vale por si: um catálogo de qualidade com 87 checks encontrou, no
primeiro processamento, um buraco que três fases de validação não tinham
encontrado. É a defesa concreta de por que o catálogo precisava crescer.

---

## Achado 4: o trust score como produto de componentes explodia

| | |
|---|---|
| **Sintoma** | `pais=BR`, com 208 mil linhas e validade 0,9997, aparecia como BLOCKED |
| **Severidade** | alta, e inteiramente minha |

### O que acontecia

A primeira implementação seguia a forma do ADR-0011 literalmente e a estendia:
um componente por classe de achado, cada um sendo a média das taxas de falha dos
checks daquela classe, e o score sendo o produto dos componentes.

Dois erros empilhados.

O primeiro: a média era **simples**, e o ADR-0011 diz **ponderada**. Um check
avaliando 320 linhas da aquisição pesava igual a um avaliando 100 mil do HRIS.

O segundo, mais profundo: **os componentes não são comensuráveis**. Cada um é
uma média dentro da própria classe, e classes diferentes cobrem frações
diferentes do recorte. Multiplicá-los soma peras com laranjas e chama o
resultado de confiança.

Juntos: `DQ_REF_008` reprova em 100% sobre 320 linhas da VivaMarket; o
componente de identidade ia a zero; o produto ia a zero; e o recorte `pais=BR`
inteiro — 208 mil linhas, validade 0,9997 — virava BLOCKED.

### A correção

Uma média ponderada **única** sobre todos os checks que pesam, com peso igual a
`records_checked` no recorte, e as classes usadas para **atribuir** a perda em
vez de fatorá-la:

```
perda_total   = Σ (taxa_falha × linhas) / Σ linhas
trust_score   = 1 − perda_total
perda[classe] = contribuição da classe, e as contribuições SOMAM perda_total
```

A atribuição passa a ser exata, e um teste exige que as contribuições somem a
perda medida — sem isso o "porquê" do score seria decorativo.

Resultado: `pais=BR` volta a 0,9986 CERTIFIED, e a penalidade da aquisição
aparece com força total em `origem=VIVAMARKET_LEGACY`, que é o recorte onde ela
é verdadeira.

---

## Achado 5: a distribuição de confiança está fora da faixa-alvo

| | |
|---|---|
| **Sintoma** | 96,8% dos pares respondíveis em CERTIFIED; a meta é 60% a 70% |
| **Status** | esperado, e mesmo assim precisa de decisão |

`defects.yaml` declara `target_trust_distribution`: CERTIFIED 60–70%, LIMITED
20–25%, BLOCKED 10–15%. O realizado é 96,8% / 2,6% / 0,5%.

A calibragem contra essa distribuição é **declaradamente da F7**
(`trust_calibration_phase: F7`), então o desvio não é surpresa. O que vale
registrar é a **causa mecânica**, porque ela muda o que a F7 vai precisar fazer.

O trust score é uma média ponderada sobre a população do recorte. Os defeitos
deste universo são **concentrados**: a VivaMarket são 320 de 300.419 linhas.
Num recorte grosso, 320 linhas 100% problemáticas movem o score em 0,001.

Isso não é um erro do cálculo. `pais=BR` **é** confiável, e dizer o contrário
por causa de 320 linhas seria o erro do achado 4 de volta. Mas significa duas
coisas para a F7:

1. **A distribuição-alvo só é alcançável com recortes finos.** Se a F7 avaliar
   trust por país × ano × business unit, a aquisição e o período 2016–2018
   isolam populações pequenas o bastante para produzir LIMITED e BLOCKED na
   proporção prevista. Os recortes desta fase são grossos de propósito, porque
   o objetivo aqui era a lógica, não a calibragem.
2. **Ou os limiares de faixa mudam, ou os recortes mudam, e não os dois.** Mexer
   nos dois ao mesmo tempo para atingir a distribuição seria ajustar o
   instrumento até o resultado ficar bonito, que é o que o ADR-0017 proíbe.

Um segundo número acompanha: **206 dos 396 pares são `INDETERMINADO`**, sem
nenhum check aplicável ao recorte. Não é falha do score; é lacuna de cobertura
do catálogo, concentrada nos recortes por ano anteriores a 2019 e nos sistemas
que têm poucos checks próprios. Vale como insumo do dimensionamento da F6.

---

## O que muda daqui para frente

| Achado | Guarda permanente criada |
|---|---|
| 1, escopo desigual | recorte declarado no YAML, `join` interno na comparação por período, e teste exigindo recorte nos checks que cruzam sistemas |
| 2, chave incompatível | interseção vazia vira `NOT_RUN`, nunca 100% de falha |
| 3, coluna sempre vazia | o check fica reprovando até haver decisão |
| 4, componentes não comensuráveis | média ponderada única e teste exigindo que a atribuição some a perda |
| 5, distribuição fora da faixa | nenhuma: é entrada da calibragem da F7 |

Sobre o conjunto das cinco fases. Os achados da F1 eram sobre **o mundo
simulado**; os da F2 sobre **o mecanismo que fabrica os defeitos**; os da F3
sobre **o instrumento que mede**; os da F4 sobre **o mecanismo que registra
decisão**; os da F5 sobre **a régua que julga**.

E há um padrão dentro do padrão que vale nomear. Os achados 1 e 2 desta fase, o
achado 2 da F3 e o achado 1 da F3 são todos a mesma coisa: **uma comparação
entre coisas que não são comparáveis, produzindo um número plausível.** Quatro
vezes em três fases. Não é coincidência — é a falha característica de um sistema
cujo trabalho inteiro é comparar fontes heterogêneas. O que muda é que agora
existe guarda para cada uma das quatro.
