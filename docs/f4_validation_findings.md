# F4: o que a governança encontrou

Quarta edição do registro de achados. Mesmo princípio das três anteriores: os
erros ficam documentados porque uma camada de validação que nunca falhou não
provou nada.

A F4 teve quatro achados. Três deles são da mesma família, e essa família merece
nome: **os três são mecanismos que apagavam ou escondiam informação sem que
ninguém tivesse decidido apagá-la.** Nenhum quebrava a execução. Todos
corrompiam a capacidade de auditar o que o sistema fez.

---

## Achado 1: reexecutar o pipeline apagava a fila inteira de exceções

| | |
|---|---|
| **Sintoma** | nenhum, até o teste de ciclo governado existir |
| **Severidade** | **crítica**, e invisível por construção |

### O que acontecia

`ExceptionQueue.reset()` fazia `DELETE FROM mapping_exceptions` a cada execução,
para recontar do zero. Faz sentido enquanto a fila é só um contador. Deixou de
fazer no momento em que a fila passou a carregar decisão humana.

O efeito: um valor rejeitado por alguém, com justificativa registrada, voltava a
aparecer como `OPEN` na execução seguinte. **Rejeitar virava sinônimo de
esquecer.** Pior, virava esquecimento silencioso, porque o `resolution_log`
continuava mostrando a rejeição e a fila mostrava o valor aberto: os dois
artefatos diziam coisas diferentes e nada apontava a contradição.

O mesmo valia para `UNDER_REVIEW`. Alguém assumia a análise de uma exceção, a
execução noturna rodava, e a marca de que a análise estava em curso sumia.

### Por que passou despercebido até agora

Porque na F3 a fila era só um contador. O erro não existia quando o código foi
escrito; ele nasceu quando a semântica da tabela mudou e o `reset` não mudou
junto. É a classe de defeito que não aparece em revisão do diff que o introduz,
porque o diff que o introduz não toca na linha errada.

### A correção

`reset()` apaga apenas o que está `OPEN`, que vai ser recontado, e zera a
contagem do resto preservando status, responsável e justificativa. Um valor
`REJECTED` que reaparece volta com contagem nova e continua rejeitado.

Um teste percorre o ciclo inteiro: decide, reexecuta o pipeline, e exige que
cada item decidido continue no estado em que foi deixado.

---

## Achado 2: a fila de identidade acumulava resíduo de outro universo

| | |
|---|---|
| **Sintoma** | 1.845 casos pendentes onde a execução corrente produz 1.579 |
| **Severidade** | média em consequência, alta em disfarce |

### O que acontecia

A fila de identidade é cumulativa de propósito: apagar um caso pendente seria
perder uma decisão em aberto. Mas cumulativa **sem marca de observação** é uma
fila que cresce com resíduo.

Os 266 casos a mais vieram de execuções no perfil `smoke`, disparadas durante o
desenvolvimento. São pessoas de um universo que não existe mais. Na fila,
ficavam indistinguíveis de um caso pendente legítimo, e um revisor gastaria
tempo decidindo sobre alguém que não está na base.

### Por que é parente do achado 1 da F3

O achado 1 da F3 foi RAW de uma execução comparado com a verdade de outra. A
guarda que nasceu dali, `check_provenance`, protege a **comparação com o
gabarito**. Não protegia a fila de governança, que é outro artefato que
atravessa execuções. Proteger um caminho não protege o outro; a lição é que
todo artefato que sobrevive à execução precisa dizer de qual execução ele veio.

### A correção

Cada caso guarda o `run_id` da última execução em que foi observado.
`identity_stale(run_id)` devolve os que continuam `OPEN` sem terem aparecido na
execução atual.

**Não foram apagados.** Um caso pode sumir por motivo legítimo (a pessoa saiu do
recorte) ou ilegítimo (resíduo de outro universo), e os dois merecem
visibilidade em vez de deleção silenciosa. O número aparece no relatório do
pipeline. Decidir o que fazer com os 266 é da Sam.

---

## Achado 3: similaridade entre línguas diferentes, apresentada como evidência

| | |
|---|---|
| **Encontrado em** | classificação das 57 exceções |
| **Sintoma** | `Controladoria → Engineering, 0,61`, na classe "candidato provável" |

### O que acontecia

O motor de sugestão pontua semelhança de escrita: sequência, sigla, prefixo,
sobreposição de tokens. Funciona bem para o problema que foi construído para
resolver — `CS → Customer Service`, `Regi.Oper. → Regional Operations`.

O cadastro legado da NOVAORA está em português e o domínio corporativo em
inglês. Para um valor que não tem apelido aprovado, o que a pontuação mede é
coincidência de letras entre dois vocabulários. E o resultado é pior que ruído,
porque **ordena errado**:

| Valor de origem | Melhor candidato | Score | Classe antiga | Está certo? |
|---|---|---|---|---|
| `Controladoria` | Engineering | 0,61 | candidato provável | não |
| `Desenvolvimento` | Customer Service | 0,61 | candidato provável | não |
| `Transportes` | Strategy | 0,53 | candidato fraco | não |
| `Centro de Distribuição` | Distribution Centers | 0,48 | candidato fraco | **sim** |
| `Operações Loja` | Store Operations | 0,47 | candidato fraco | **sim** |

As duas sugestões corretas receberam os scores mais baixos da tabela, e as duas
absurdas receberam os mais altos. Um revisor apressado aprovaria
`Controladoria → Engineering` e recusaria `Centro de Distribuição →
Distribution Centers`. A pontuação não estava só imprecisa: estava
sistematicamente invertida para esta classe de caso.

### Por que a correção não é calibrar o limiar

Nenhum limiar separa as duas metades desta tabela, porque a informação que
separa não está na escrita. Subir o limiar tiraria as corretas junto; baixar
traria mais absurdos. **O problema não é o número, é a pergunta**: similaridade
de caractere não responde "estas duas palavras significam o mesmo em línguas
diferentes".

### A correção

`sources.yaml` já declarava `field_language` para dois dos doze sistemas. Passou
a declarar para os doze, mais `canonical_field_language` para o domínio
corporativo, que é o alvo do DE/PARA. Declaração, não inferência.

Quando a língua do sistema difere da do domínio e nenhum apelido aprovado cobre
o valor, a proposta classifica como `TRADUCAO_PENDENTE` e **não oferece
candidato nenhum**, dizendo que o score não é evidência ali. Doze exceções
mudaram de classe. Nenhum mapeamento mudou, nenhum limiar mudou, e nada foi
aplicado: a mudança é em como a exceção é apresentada a quem decide.

Efeito colateral honesto: a proposta agora admite que, para 12 casos, o pipeline
não tem nada a sugerir. É menos impressionante e mais verdadeiro.

### Sub-achado: a sugestão aceita também era inconferível

`JUR → Legal, 0,82 por prefixo` não se sustenta na leitura: `JUR` não é prefixo
de `Legal`. É prefixo de `JURIDICO`, um apelido que já está no mapa aprovado, e
`Legal` é o valor padrão correspondente. O motor sempre pontuou contra os dois
lados da tabela e sempre esteve certo; o que ele não mostrava era **qual dos
dois casou**.

Para um documento cuja única função é sustentar decisão humana, esconder o
intermediário transforma revisão em fé. A proposta ganhou a coluna "casou com".

---

## Achado 4: a suíte de testes escrevia nos dados do projeto

| | |
|---|---|
| **Sintoma** | o RAW do perfil `dev` virava `smoke` depois de rodar os testes |
| **Severidade** | **crítica**, e já tinha cobrado o preço uma vez |

### O que acontecia

O relatório da F3 registrou que a divergência de proveniência daquele achado
veio de "uma execução no perfil `smoke` disparada pela suíte de testes". A
frase ficou no documento e o mecanismo ficou no código: a fixture da camada RAW
usava a raiz do projeto e `projection.run` escreve em `data/raw`.

Resultado: rodar os testes deixava RAW e camada de verdade em perfis
diferentes. `check_provenance` recusava a comparação com o gabarito e explicava
o motivo — a guarda funcionou nas três vezes em que isso aconteceu durante a
F4. Mas guarda que avisa não é o mesmo que causa removida, e a guarda protegia
a comparação, não o dado.

### A correção

Duas, em camadas diferentes:

1. a fixture da camada RAW passou a rodar num universo descartável, como a do
   pipeline já fazia;
2. um guarda de sessão em `tests/conftest.py` tira impressão digital de
   `data/raw`, `data/synthetic/truth` e `data/reference` antes e depois da
   suíte, e **reprova a suíte inteira** se algum dos três mudou.

O segundo é o que importa. O primeiro corrige o teste de hoje; o segundo impede
que o mesmo mecanismo volte por outra porta amanhã. Foi ele que encontrou um
segundo ponto de escrita que a correção manual tinha deixado passar.

---

## O que muda daqui para frente

| Achado | Guarda permanente criada |
|---|---|
| 1, fila apagada | `reset()` preserva decisão, e um teste reexecuta o pipeline exigindo que decisão sobreviva |
| 2, resíduo de outro universo | todo caso guarda o `run_id` da última observação, e o não observado é reportado |
| 3, score entre línguas | língua declarada por sistema em configuração, e nenhum candidato onde o score não é evidência |
| 4, teste sujando o projeto | guarda de sessão que reprova a suíte se ela tocar em RAW, verdade ou referência |

E vale a observação sobre o conjunto das quatro fases. Os achados da F1 eram
sobre **o mundo simulado**; os da F2 sobre **o mecanismo que fabrica os
defeitos**; os da F3 sobre **o instrumento que mede**; os da F4 sobre **o
mecanismo que registra decisão**.

A progressão tem uma direção. A cada camada, o objeto sob suspeita fica mais
perto de quem julga, e o modo de falha fica menos parecido com erro e mais
parecido com esquecimento. Nenhum dos quatro achados desta fase produziu um
número errado. Os quatro produziriam um histórico errado, que é o que se
descobre tarde.
