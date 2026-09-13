# F2: o que as validações pegaram

Continuação de `docs/f1_validation_findings.md`. Mesmo princípio: os erros ficam
registrados porque uma suíte de validação que nunca falhou não provou nada.

A F2 teve cinco achados. O primeiro é de natureza diferente dos outros e recebe
tratamento separado, por decisão da Sam na aprovação da fase: ele não é um
defeito nos dados, é um **defeito no próprio mecanismo de injeção de defeitos**.

---

## Achado 1 (crítico): o ledger registrava corrupção que não existia no arquivo

| | |
|---|---|
| **Encontrado por** | teste `test_defeito_registrado_tem_valor_verdadeiro_e_valor_gravado` |
| **Sintoma** | 126 das 780 substituições tinham `truth_value` igual a `raw_value` |
| **Severidade** | **crítica**, e a razão está abaixo |

### O que acontecia

A função `free_text_variant` produz variações típicas de digitação manual:
caixa alta, caixa baixa, espaço sobrando, espaço duplo, `&` virando `e`,
abreviação. Ela sorteava **uma** dessas variações e devolvia o resultado.

Para um departamento de palavra única e sem `&`, três das seis variações não
mudam nada: espaço duplo não tem onde agir, `&` não existe, e a abreviação não
encurta uma palavra curta. `UX` sorteando "espaço duplo" saía `UX`.

O código então registrava a ocorrência no ledger como se a corrupção tivesse
acontecido.

### Por que isso é crítico e não cosmético

Os outros quatro achados desta fase produzem dados errados, e dado errado é
detectável: alguém compara, estranha, investiga.

Este produz um **gabarito errado**, e gabarito errado não é detectável por
comparação, porque o gabarito é justamente aquilo contra o que se compara.

O efeito prático, se tivesse passado: na F5, o pipeline processaria o arquivo,
não encontraria nada errado naqueles 126 registros (porque de fato não havia
nada errado), e a medição diria que o pipeline **falhou em detectar 126
defeitos**. A conclusão seria que a camada de qualidade tem 16% de falso
negativo em D04, quando o número verdadeiro é zero.

O erro se propagaria na direção mais perigosa possível: contra o pipeline e a
favor do gerador. Toda a tese do projeto, "eu recuperei X% da realidade e sei
onde perdi o resto", depende de o gabarito estar certo.

### A correção

`free_text_variant` passou a **garantir** a mudança: percorre as seis variações
em ordem sorteada e devolve a primeira que produza valor diferente. Se nenhuma
produzir, devolve o valor com espaço à direita, que é uma variante real e
bastante desagradável de detectar.

Em paralelo, os três pontos de chamada passaram a só gravar no ledger quando o
valor de fato mudou. Cinto e suspensório de propósito: a garantia na função
resolve o caso conhecido, e a guarda no ponto de chamada protege de qualquer
função de injeção futura que não garanta.

### A distinção que ficou explícita: tentativa versus corrupção

O achado tornou visível uma distinção que estava implícita e que agora é
estrutura do projeto. O ledger conta **duas coisas diferentes**:

| Conceito | Significado | Onde vive |
|---|---|---|
| **Tentativa** | um registro foi oferecido ao defeito, com a taxa esperada daquele momento (já considerando escopo temporal, picos por incidente e taxa por país) | `Ledger.attempts` |
| **Corrupção observada** | o valor gravado no RAW ficou de fato diferente do valor verdadeiro | `Ledger.rows` |

As duas só coincidem se a função de injeção garantir mudança. Três
consequências que passaram a valer:

1. **A calibragem é medida sobre tentativas**, não sobre o total do ledger.
   Comparar ocorrências com a taxa nominal dá falso positivo sempre que um
   defeito ocorre em mais de um dataset ou tem escopo temporal, e foi isso que
   aconteceu na primeira versão da validação R07.
2. **A razão corrupções ÷ tentativas é ela própria um indicador de saúde do
   gerador.** Se cair abaixo da taxa esperada, alguma função de injeção está
   devolvendo valor idêntico.
3. **O relatório de cobertura reporta as duas colunas lado a lado**
   (`docs/f2_defect_coverage.md`), justamente para que a divergência entre elas
   fique visível em vez de ficar escondida num número só.

---

## Achado 2: `sources.yaml` e `defects.yaml` descreviam a mesma coisa sem se falarem

| | |
|---|---|
| **Encontrado por** | validação R02, "todo defeito ocorre só em sistema que declara carregá-lo" |
| **Sintoma** | quatro combinações defeito/sistema injetadas e não declaradas |

O `sources.yaml` já trazia, na metadata de cada sistema,
`VIVAMARKET_LEGACY.gender_values: ["MASC","FEM"]` e
`ATS_CLOUD.enterprise_id_fill_rate: 0.63`. São exatamente os defeitos D01 e D05,
descritos com outro vocabulário. Nenhum dos dois constava em `source_systems` do
defeito correspondente.

Não era divergência de opinião entre os arquivos, era omissão em um deles. A
correção virou a **Emenda 1 do ADR-0008**, e a R02 passa a ser a guarda
permanente: qualquer defeito injetado em sistema não declarado quebra a fase.

O ponto mais amplo: com dois arquivos de configuração descrevendo aspectos
diferentes do mesmo mundo, a reconciliação entre eles precisa ser executável.
Foi por isso que o relatório de cobertura é gerado por código.

---

## Achado 3: D07 e D22 declarados e nunca injetados

| | |
|---|---|
| **Encontrado por** | validação R04, cobertura da onda 1 |
| **Sintoma** | dois defeitos previstos sem nenhuma ocorrência |

Causas diferentes para o mesmo sintoma:

- **D07**, formato de data divergente, vale para 100% das datas do sistema. Não
  é sorteio por registro, é propriedade do formato, e o código nunca registrava
  nada. Passou a gravar um registro por dataset, declarando o formato nativo
  contra o ISO.
- **D22**, duplicidade por recontratação, tem `rate_type: absolute` com
  contagem, e o código chamava a função de sorteio por taxa, que devolvia zero
  porque `rate` é nulo. Passou a calcular o alvo absoluto escalado pelo perfil.

Lição para o catálogo: defeitos com naturezas diferentes (taxa, contagem
absoluta, propriedade universal do formato) precisam de tratamento diferente no
código, e a R04 é o que impede que algum deles seja esquecido.

---

## Achado 4: o defeito de encoding não tinha o que corromper

| | |
|---|---|
| **Encontrado por** | validação R04 |
| **Sintoma** | D23 sem nenhuma ocorrência |

O pool de nomes sintéticos era `Ana`, `Silva`, `Oliveira`, tudo sem acento, e os
apelidos de departamento também. O mojibake de latin-1 lido como utf-8 não tem
efeito sobre ASCII puro, então a função rodava e devolvia o valor intacto.

Correção: nomes e apelidos ganharam acentuação (`José`, `João`, `Luíza`,
`Jurídico`, `Operações Loja`, `Logística`). É um caso em que a qualidade do
defeito dependia de uma escolha aparentemente decorativa na geração do mundo.

---

## Achado 5: a divergência da folha estava calibrada na perna errada

| | |
|---|---|
| **Encontrado por** | validação R16, reconciliação HRIS versus folha |
| **Sintoma** | divergência líquida de 0,70% contra os 2% a 5% configurados |

O código incluía terceiros e estagiários de agência (60% da taxa) e excluía
afastados de longa duração (40% da taxa). As duas pernas quase se cancelavam, e
a divergência líquida saía em 0,2 da taxa configurada.

A causa é de leitura da especificação: a taxa em D11 é a divergência
**líquida** de headcount, porque é assim que o check de reconciliação a mede, e
não o tamanho de cada perna. Inclusões e exclusões foram recalibradas para
1,30 e 0,30 da taxa, de modo que a diferença líquida fique na faixa.

---

## O que muda daqui para frente

| Achado | Guarda permanente criada |
|---|---|
| 1, ledger mentindo | teste de substituição efetiva + garantia na função + guarda no ponto de chamada |
| 2, configs divergentes | R02 e o relatório de cobertura gerado por código |
| 3, defeitos sem injeção | R04, cobertura da onda |
| 4, defeito sem efeito | R04, e o teste de substituição do achado 1 |
| 5, calibragem na perna errada | R16, com a faixa lida do próprio catálogo |

Nenhum dos cinco quebrava a execução. Os cinco produziam arquivos plausíveis à
primeira vista. É o mesmo argumento da F1, aplicado agora ao mecanismo que
fabrica os problemas: quem fabrica defeito de propósito precisa de validação
tanto quanto quem os detecta.
