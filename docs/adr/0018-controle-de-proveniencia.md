# ADR-0018: Controle de proveniencia antes de qualquer comparacao com o gabarito

- **Status:** Aceita
- **Data:** 2026-09-11
- **Origem:** decisao da Sam na aprovacao da F3, item 5
- **Fase:** vigora da F3 em diante, para sempre

## Contexto

A F3 comparou a camada de verdade com o resultado do pipeline e reportou desvio
de headcount de 7.075.727%. O numero absurdo foi o que chamou atencao, mas nao
era o problema: era o sintoma.

A causa era que a camada de verdade tinha sido escrita por uma execucao no
perfil `dev` e o RAW por uma execucao posterior no perfil `smoke`, disparada
pela suite de testes. Os dois lados existiam, tinham a forma certa, e descreviam
empresas diferentes.

O que torna isso grave nao e o erro em si, e a classe a que ele pertence. Se o
desvio tivesse dado 4% em vez de 7 milhoes, ninguem teria percebido. A
comparacao roda, produz numeros plausiveis, e a conclusao sobre a qualidade do
pipeline sai errada sem nenhum sinal de alarme.

O agravante: o manifesto ja carregava `seed`, `profile`, `scale` e `config_hash`
desde a F1, exatamente para tornar isso verificavel. Faltava alguem conferir.
**Informacao existir nao e o mesmo que informacao ser usada.**

## Decisao

`check_provenance` e **controle obrigatorio** e roda antes de qualquer
comparacao entre a camada de verdade e as camadas RAW, standardized, conformed
ou analitica.

Regras:

1. O controle compara os manifestos de `data/synthetic/truth/` e de `data/raw/`
   em `seed`, `profile` e `scale`.
2. Em caso de divergencia, a comparacao com o gabarito **nao roda**. O relatorio
   diz por que, em vez de exibir numeros invalidos.
3. O status aparece na primeira linha da execucao do pipeline, nao escondido num
   JSON.
4. O controle nao pode ser desligado por parametro. Se alguem precisar comparar
   execucoes diferentes de proposito, escreve outro script e assume o que esta
   fazendo.
5. O mesmo controle vale para qualquer fase futura que compare contra o
   gabarito, incluindo a avaliacao final da F12.

## Alternativas consideradas

1. **Confiar na disciplina de sempre regerar tudo junto.** E o que estava em
   vigor, implicitamente, e falhou na primeira oportunidade. Disciplina humana
   nao e controle.
2. **Avisar em vez de bloquear.** Descartada: um aviso ao lado de uma tabela de
   numeros e ignorado. Se os numeros nao valem, eles nao devem aparecer.
3. **Comparar o `config_hash` tambem.** Considerada e adiada: o hash muda a cada
   edicao de configuracao, inclusive comentario, e bloquearia comparacoes
   legitimas durante desenvolvimento. `seed`, `profile` e `scale` sao
   suficientes para pegar o caso real. Se aparecer um caso que passe por esses
   tres e ainda assim seja incompativel, o hash entra.

## Consequencias

**Positivas**

- Elimina uma classe de erro que produz conclusao errada sem sinal de alarme.
- Torna explicito que o gabarito so vale se vier da mesma execucao.
- Custa milissegundos: le dois arquivos JSON pequenos.

**Negativas**

- Durante desenvolvimento, rodar a suite de testes invalida a comparacao ate a
  proxima geracao completa. E o comportamento correto e ja acontece: os testes
  passaram a escrever em diretorio temporario por causa disso.

**Riscos e mitigacao**

- *Risco:* alguem contornar o controle para "ver o numero rapido".
  *Mitigacao:* nao ha parametro para desligar, e o teste
  `test_pipeline_bloqueia_comparacao_com_proveniencia_divergente` garante o
  comportamento.

## Referencias

- `docs/f3_validation_findings.md`, achado 1
- ADR-0001 (camada de verdade como gabarito)
- `src/pipeline.py`, funcao `check_provenance`
