# Demografia da NOVAORA: natureza dos parâmetros e coerência interna

> **Estes números não representam estatísticas reais de nenhuma empresa, setor,
> país ou população.** Eles descrevem uma empresa fictícia construída para
> exercitar um pipeline de dados, e não devem ser citados, apresentados ou
> reutilizados como se descrevessem o mundo real.

Documento exigido pela Sam na aprovação da F1, item 3. Cobre três coisas: o que
os parâmetros são e o que não são, como a coerência interna é garantida, e o
que foi deliberadamente evitado.

---

## 1. O que estes parâmetros são

Todos os valores demográficos em `config/generation.yaml` estão marcados como
`[SINTETICO]` e vivem sob o bloco `demographics`. Eles são **entradas de uma
simulação**, escolhidas para que o dataset resultante exercite os componentes
do projeto:

- uma camada de DE/PARA que precisa lidar com valores autodeclarados em cinco
  países, com vocabulários diferentes;
- uma regra de supressão por n mínimo que precisa de recortes pequenos para
  disparar (ADR-0007);
- KPIs de representatividade que precisam de um denominador problemático para
  serem interessantes;
- um defeito D02 e um defeito D03 que só fazem sentido se o campo tiver uma
  data de nascimento e uma taxa de não declaração alta.

## 2. O que estes parâmetros não são

Não são pesquisa. Não são benchmark. Não são projeção. Não foram derivados de
nenhuma fonte estatística, censo, pesquisa setorial ou base pública, e não
foram calibrados contra nenhuma.

O cabeçalho de `config/generation.yaml` e o docstring de
`src/generator/world/population.py` repetem esse aviso no ponto em que alguém
leria os números, que é onde o aviso serve para alguma coisa.

**Consequência prática para a apresentação do projeto:** nenhum gráfico de DEI
gerado a partir deste dataset pode ser mostrado sem a legenda de dados
sintéticos, e nenhuma conclusão sobre desigualdade real pode ser extraída dele.
O que o projeto demonstra é a **capacidade de medir**, não uma medição.

---

## 3. Coerência interna, e como ela é verificada

Coerência interna é diferente de realismo. O compromisso aqui é que o mundo
gerado seja consistente com o que a própria configuração declara, e que a
consistência seja verificada por código e não por leitura.

Oito validações cobrem isso (`src/generator/validate.py`, bloco
`_demographic_coherence`):

| ID | Verifica |
|---|---|
| V30 | o share feminino não aumenta conforme a senioridade sobe |
| V31 | o share de pessoas pretas e pardas cai da base ao topo no Brasil, sem inversão relevante |
| V32 | a taxa de não declaração por país fica perto da configurada |
| V33 | quem não declarou nunca recebe um valor concreto imputado |
| V34 | nenhuma declaração existe antes da data em que o campo passou a existir |
| V35 | o share feminino na liderança não anda contra a tendência configurada (WARNING, ver seção 4) |
| V36 | a idade na admissão respeita a faixa do nível **de admissão**, não a do nível atual |
| V37 | nenhum gênero presente na força de trabalho desaparece da liderança |

Três delas nasceram de erro encontrado, o que vale registrar:

- **V31** começou exigindo monotonia estrita em todos os sete grupos de nível.
  Falhava em Director por ruído amostral, com n abaixo de 50. A regra correta
  exige n mínimo de 100 por grupo e olha a diferença entre base e topo, porque
  monotonia estrita não é a invariante, a tendência é.
- **V32** estava contando participantes da campanha de autodeclaração em vez de
  declarantes, e reportava 2,5% de não declaração onde o configurado era 24%.
  Erro na validação, não no gerador.
- **V36** comparava a idade de admissão com a faixa do nível **atual**. Quem
  entrou como Entry aos 19 anos e hoje é Manager aparecia como fora da faixa.
  A correção exigiu guardar `hire_job_level` no modelo, que é informação útil
  por si só.

### Coerência temporal

A demografia não é estática, e a evolução tem causa declarada:

| Momento | O que acontece | Onde está |
|---|---|---|
| até mai/2019 | os campos de raça, cor e deficiência **não existem** | defeito D02 |
| jun/2019 | o campo passa a existir e roda uma campanha de autodeclaração com quem já está na casa | `INC_2019_HRIS_MIGRATION`, efeito `field_appears` |
| jun/2019 em diante | quem é admitido declara ou não declara, pela taxa do país | defeito D03 |
| 2021 em diante | a empresa adota metas de diversidade e o gradiente de gênero na liderança melhora lentamente | `leadership_trend_per_year_from_2021` |

A campanha de 2019 existe porque, sem ela, só quem fosse admitido depois de
jun/2019 teria o campo preenchido, e a taxa de declaração levaria a década
inteira para convergir. Isso seria um artefato do modelo, não um fenômeno.

A separação entre "não existe o campo" e "existe e não foi declarado" é feita
por `race_declared_at`. Antes dessa data não é dado faltante, é ausência de
campo, e o PeopleLens precisa saber responder "indisponível" em vez de zero.

---

## 4. O que foi deliberadamente evitado

**Não otimizamos o dataset para produzir resultados positivos de DEI.** O
gradiente de gênero e o de raça e cor por nível são parâmetros de entrada, e o
resultado agregado é consequência. Em nenhum momento um número de saída foi
perseguido ajustando a entrada, o que é a aplicação direta do ADR-0017.

Concretamente, o que **não** foi feito:

- ajustar o gradiente até "Women in Leadership" chegar a um percentual bonito;
- suavizar a queda de representatividade nos níveis seniores;
- reduzir a taxa de não declaração para que os KPIs de DEI ficassem mais
  fáceis de calcular;
- imputar raça ou cor por distribuição conhecida, que seria inventar
  identidade de pessoas, ainda que sintéticas;
- remover o gênero "Não informado" e a categoria não binária para simplificar
  o modelo.

O share feminino na liderança termina a série em cerca de 42%, e isso não é uma
meta atingida: é o que sai de um gradiente que começa em 58% na base e cai até
18% no topo, combinado com uma população de liderança dominada por Manager e
Senior Manager, e com uma tendência de melhora a partir de 2021. A cadeia é
rastreável do parâmetro ao resultado, que é o único critério que importa aqui.

### Decisão registrada na F2: a tendência de liderança fica como está

A F2 mediu o efeito de `leadership_trend_per_year_from_2021` e encontrou algo
que vale registrar: **o parâmetro quase não tem efeito**.

O motivo é estrutural. A tendência é aplicada na amostragem demográfica, que
acontece no momento da admissão. Mas a população de liderança da NOVAORA se
forma majoritariamente por **promoção interna**, e quem é promovido carrega o
gênero que recebeu quando entrou, possivelmente dez anos antes. A tendência só
alcança quem é contratado externamente já em posição de liderança, que é uma
fração pequena.

Havia duas saídas. A primeira, aplicar a tendência também na promoção, modelando
a política de diversidade como algo que atua nos dois caminhos de entrada. A
segunda, deixar como está e registrar a limitação.

**Decisão da Sam: deixar como está.** Não alterar a promoção interna para
produzir efeito de DEI.

O raciocínio por trás: mexer na promoção para que o número de mulheres na
liderança suba é exatamente a classe de intervenção que o ADR-0017 proíbe, ainda
que pudesse ser apresentada como modelagem de política. A diferença entre
"modelar uma política declarada" e "otimizar um resultado" é fina demais aqui
para ser decidida por conveniência, e na dúvida o projeto fica com a opção que
não empurra número.

Consequência assumida e declarada: a série de mulheres na liderança oscila em
torno de 40% a 42% sem tendência clara, e a validação V35 é um **WARNING** e não
um bloqueio, justamente porque a tendência configurada não se realiza. Isso está
visível no relatório de métricas em vez de escondido.

---

## 5. Uma nota sobre por que isso está documentado

A memória de um dataset sintético é curta. Daqui a seis meses, um gráfico
bonito com 42% de mulheres na liderança da NOVAORA pode aparecer numa
apresentação sem o contexto de que a NOVAORA não existe.

O projeto inteiro é sobre a diferença entre um número e um número em que se
pode confiar. Seria incoerente construir essa tese sobre um dataset cuja
natureza não está declarada no lugar onde alguém vai ler.
