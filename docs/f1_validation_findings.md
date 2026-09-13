# F1: o que as validações pegaram

Registro dos erros encontrados pelas validações de coerência durante a
construção do gerador. Este documento existe por decisão da Sam na aprovação da
F1 (item 5): os erros ficam documentados como **evidência de que a camada de
validação funciona**.

O argumento é simples. Uma suíte de validação que nunca falhou não provou nada:
pode estar certa ou pode estar vazia. O valor destas quatro falhas é justamente
que elas aconteceram, foram diagnosticadas e apontaram erro real de modelagem,
não falso positivo.

---

## Achado 1: o degrau da aquisição de 2022

**Achado mais importante dos quatro.**

| | |
|---|---|
| **Validação** | V28, headcount mensal dentro da tolerância |
| **Sintoma** | desvio de 22,4% entre plano e realizado em ago/2022 |
| **Severidade** | alta: distorcia todos os KPIs de headcount e de crescimento em 2022 |

**O que acontecia.** A curva de headcount da Especificação vai de 9.000 em 2021
para 13.000 em 2022. O plano mensal interpolava esse crescimento linearmente ao
longo dos doze meses. A simulação, corretamente, fazia a VivaMarket entrar de
uma vez em agosto, com 3.200 pessoas.

Resultado: em agosto o realizado saltava muito acima do plano interpolado, e o
gerador então parava de contratar durante meses para deixar o número convergir
de volta. Nas séries, isso apareceria como um congelamento de contratação
inexistente no segundo semestre de 2022.

**A causa raiz é conceitual, não de código.** Crescimento por aquisição e
crescimento orgânico são fenômenos diferentes e estavam sendo tratados como o
mesmo. A interpolação linear é adequada para contratação, e é errada para um
evento que acontece num dia.

**A correção.** `headcount_plan` passou a ler as aquisições de
`config/incidents.yaml` e a construir a curva em duas partes: o crescimento
orgânico interpola de `HC(ano anterior)` até `HC(ano) menos a aquisição`, e no
mês do evento o plano dá o degrau. No fim do ano os dois caminhos chegam ao
mesmo total.

**Por que este achado vale mais que os outros.** Ele é a prova antecipada da
tese central do projeto. Um analista lendo o dataset original reportaria
"crescimento de 44% em 2022", quando o crescimento orgânico foi de 800 pessoas.
A mesma confusão que o defeito ia criar no dado, o bug criou no gerador. E foi
uma validação estrutural que pegou, não inspeção visual.

Esse caso vira um bom caso de teste para o PeopleLens na F10: a pergunta
"quanto a empresa cresceu em 2022?" tem duas respostas certas e uma errada, e o
sistema precisa saber separar entrada por aquisição de contratação.

---

## Achado 2: movimentação registrada depois do desligamento

| | |
|---|---|
| **Validação** | V04 e V15, eventos fora do vínculo |
| **Sintoma** | 19 movimentações antes da admissão e 19 depois do desligamento |
| **Severidade** | média: quebrava a integridade temporal do SCD2 |

**O que acontecia.** Os eventos do mês não tinham ordem definida dentro do mês.
Admissão sorteava um dia entre 1 e 27, movimentação era registrada no dia 15,
desligamento sorteava um dia entre 1 e 27. Uma pessoa desligada no dia 3 podia
receber uma movimentação em massa datada no dia 15 do mesmo mês, porque as
reorganizações rodavam no início do processamento mensal.

**A correção.** Convenção explícita de dia dentro do mês:

| Evento | Dia |
|---|---|
| Admissão | 1 a 14 |
| Movimentação, avaliação, pesquisa, mérito | 15 |
| Desligamento | 16 a 28 |

A ordem passa a ser garantida por construção, e não por verificação. Custo: as
admissões se concentram na primeira quinzena, o que é um artefato do modelo e
está documentado. Benefício: elimina uma classe inteira de incoerência em vez
de corrigir caso a caso.

---

## Achado 3: matrícula em treinamento antes da admissão

| | |
|---|---|
| **Validação** | V15, `fact_learning` sem evento fora do vínculo |
| **Sintoma** | 727 matrículas anteriores à data de admissão |
| **Severidade** | baixa em impacto, alta em frequência |

**O que acontecia.** A data de matrícula sorteava um dia qualquer do mês. Para
quem foi admitido no dia 10, qualquer sorteio entre 1 e 9 caía antes do
vínculo existir.

**A correção.** A data de matrícula é limitada pela data de admissão. Simples,
e o ponto é outro: 727 linhas em 48 mil passariam despercebidas em inspeção
visual, e a validação estrutural pegou todas.

---

## Achado 4: pessoas sem gestor que não eram o topo da hierarquia

| | |
|---|---|
| **Validação** | V09b, criada em resposta ao próprio achado |
| **Sintoma** | duas pessoas com `manager_id` nulo, uma delas IC1 |
| **Severidade** | média: `manager_id` órfão é defeito planejado para a F2, e não podia existir na verdade |

**O que acontecia.** Durante a criação da população inicial de jan/2016, as
primeiras pessoas eram criadas quando ainda não existia ninguém de nível
superior, então ficavam sem gestor. Como a atribuição de gestor só era refeita
quando o gestor saía, elas nunca ganhavam um.

**A correção.** Duas partes. Primeiro, uma segunda passada depois de semear a
população: com todo mundo criado, a hierarquia é refeita do topo para a base.
Segundo, a atribuição é conceitualmente do instante da admissão, então ela
corrige a versão de origem no log de estado em vez de criar uma versão SCD2
nova (senão toda a população inicial ganharia uma mudança de gestor falsa em
jan/2016).

**O detalhe que merece registro.** A validação que eu escrevi primeiro estava
errada: exigia que quem não tem gestor esteja no nível D3. Isso passava no
perfil `dev` e falhava no perfil `smoke`, onde a população é pequena demais
para existir alguém em D3. A invariante certa não é sobre o nível, é sobre o
instante: **alguém só fica sem gestor se, naquele momento, não existir nenhuma
pessoa ativa de nível superior**. A validação foi reescrita nesses termos.

Vale como lição para as fases seguintes: uma validação que depende do tamanho
da amostra está testando a amostra, não a regra.

---

## O que isso diz sobre a camada de validação

| Achado | Encontrado por | Tipo de erro |
|---|---|---|
| 1, degrau da aquisição | validação de plano versus realizado | conceitual, no modelo |
| 2, evento fora do vínculo | validação de integridade temporal | de ordenação |
| 3, matrícula antes da admissão | validação de integridade temporal | de limite |
| 4, pessoa sem gestor | validação de integridade referencial | de inicialização |

Nenhum dos quatro seria pego por inspeção visual de amostra, e nenhum quebrava
a execução: o gerador rodava sem erro e produzia um mundo plausível à primeira
vista nos quatro casos.

É esse o argumento que o projeto faz sobre Data Quality, aplicado a si mesmo:
dado errado não avisa que está errado, e a única defesa é verificação
declarada, executável e rodada sempre.
