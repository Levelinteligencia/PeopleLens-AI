# ADR-0021: Decisao registrada sobrevive a reexecucao, e o que some fica visivel

- **Status:** Aceita
- **Data:** 2026-09-11
- **Origem:** achados 1 e 2 da F4
- **Fase:** vigora da F4 em diante

## Contexto

As filas de governanca — excecoes de mapeamento e decisoes de identidade — sao
reconstruidas a cada execucao do pipeline, porque as contagens de ocorrencia
precisam refletir o dado atual. Enquanto as filas eram apenas contadores, isso
era trivialmente correto.

Deixou de ser no momento em que passaram a carregar decisao humana. Dois modos
de falha apareceram, e os dois sao da mesma familia: **mecanismos que apagavam
ou escondiam informacao sem que ninguem tivesse decidido apaga-la**.

1. `ExceptionQueue.reset()` fazia `DELETE` na tabela inteira. Um valor rejeitado
   por alguem, com justificativa registrada, voltava como `OPEN` na execucao
   seguinte. **Rejeitar virava sinonimo de esquecer**, e de forma
   contraditoria: o `resolution_log` mostrava a rejeicao e a fila mostrava o
   valor aberto, sem nada apontar a divergencia. Valia tambem para
   `UNDER_REVIEW`: a marca de que alguem estava analisando sumia na execucao
   noturna.
2. A fila de identidade, que e cumulativa de proposito, nao guardava marca de
   observacao. Acumulou 266 casos de execucoes em outro perfil, indistinguiveis
   de caso pendente legitimo. Um revisor gastaria tempo decidindo sobre pessoas
   que nao estao na base.

O segundo e parente direto do achado 1 da F3. A guarda que nasceu daquele
achado, `check_provenance` (ADR-0018), protege a **comparacao com o gabarito**.
Nao protegia outro artefato que tambem atravessa execucoes. Proteger um caminho
nao protege o outro.

## Decisao

1. **Reexecutar o pipeline nao apaga decisao.** `reset()` remove apenas itens
   `OPEN`, que serao recontados, e zera a contagem dos demais preservando
   status, responsavel, justificativa e data. Um valor `REJECTED` que reaparece
   volta com contagem nova e continua rejeitado.
2. **Todo artefato que sobrevive a execucao declara de qual execucao ele veio.**
   Cada caso de identidade guarda o `run_id` da ultima execucao em que foi
   observado.
3. **O que sumiu fica visivel, nao apagado.** `identity_stale(run_id)` lista os
   casos ainda `OPEN` que a execucao atual nao observou, e o numero aparece no
   relatorio do pipeline. Um caso pode sumir por motivo legitimo (a pessoa saiu
   do recorte) ou ilegitimo (residuo de outro universo); os dois merecem
   visibilidade, e nenhum merece delecao silenciosa.
4. **Quem limpa residuo e uma decisao humana**, pelo mesmo caminho de qualquer
   outra: registrada no `resolution_log`, com responsavel e justificativa.
5. **A suite de testes nao escreve nos dados do projeto.** Um guarda de sessao
   tira impressao digital de `data/raw`, `data/synthetic/truth` e
   `data/reference` antes e depois da suite, e reprova a suite inteira se algum
   dos tres mudou.

## Alternativas consideradas

1. **Manter o `DELETE` e confiar no `resolution_log` como historico.** Descartada:
   o log sobreviveria, mas a fila mentiria, e a fila e o que o humano olha. Dois
   artefatos dizendo coisas diferentes e pior que um artefato incompleto.
2. **Apagar automaticamente o que nao foi observado.** Descartada: e correcao
   silenciosa com outro nome. Alem disso perde o caso legitimo junto com o
   residuo, sem distinguir os dois.
3. **Nao acumular: recriar a fila de identidade do zero a cada execucao.**
   Descartada: perderia decisao em aberto, que e justamente o que a fila existe
   para nao perder.
4. **Comparar `config_hash` da fila com o da execucao.** Considerada e adiada,
   pela mesma razao do ADR-0018: o hash muda a cada edicao de configuracao,
   inclusive comentario. O `run_id` resolve o caso real.

## Consequencias

**Positivas**

- Decisao humana passa a ser duravel, que era o pressuposto implicito de toda a
  camada de governanca.
- Residuo de execucao vira numero reportado em vez de ruido invisivel.
- O guarda de sessao encontrou um segundo ponto de escrita nos dados do projeto
  que a correcao manual tinha deixado passar.

**Negativas**

- A fila de identidade continua crescendo, agora com a distincao entre observado
  e nao observado. Em volume completo isso pode virar um problema de tamanho, e
  a decisao de arquivar so deve ser tomada com evidencia, nao por antecipacao.

**Riscos e mitigacao**

- *Risco:* um item `UNDER_REVIEW` que deixou de aparecer na base fica na fila
  para sempre. *Mitigacao:* fica com contagem zero e aparece como nao observado,
  entao e visivel; fechar e decisao humana.

## Referencias

- `docs/f4_validation_findings.md`, achados 1, 2 e 4
- `src/mapping/depara.py`, `ExceptionQueue.reset`
- `src/mapping/resolution.py`, `load_identity_queue` e `identity_stale`
- `tests/conftest.py`, guarda de sessao
- ADR-0018 (controle de proveniencia), ADR-0009 (armazenamento e governanca)
