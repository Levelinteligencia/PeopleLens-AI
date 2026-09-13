# ADR-0022: Classe de achado, e a natureza da perda de confianca

- **Status:** Aceita
- **Data:** 2026-09-11
- **Origem:** principio fixado pela Sam na abertura da F5
- **Fase:** vigora da F5 em diante
- **Emenda 1 (DQ-03, fechamento da F5):** `DESATUALIZADO` e `DIVERGENCIA`,
  propostas durante a implementacao, foram **aprovadas oficialmente** e passam a
  integrar a taxonomia de findings do PeopleLens. A taxonomia tem sete classes,
  e nao cinco.

## Contexto

Ate a F4, um check de qualidade tinha duas dimensoes: `threshold`, que diz
**quando** ele reprova, e `severity`, que diz **o que acontece** com a linha
reprovada. Faltava a terceira, e a falta era estrutural.

Um salario negativo e um departamento sem mapeamento aprovado sao os dois
"fail". Sao problemas de natureza inteiramente diferente:

- o salario negativo **esta errado**. Alguem precisa corrigir na fonte;
- o departamento sem mapa **esta certo na origem**. Alguem precisa decidir.

Com uma dimensao so, os dois entram no mesmo saco. A consequencia pratica e que
o sistema passa a tratar uma fila de decisao como defeito de dado, e a pressao
que ele gera e para "corrigir" aquilo que nao esta quebrado. No limite, para
fazer o numero subir, alguem aprova um mapeamento qualquer, que e exatamente o
erro invisivel que o principio 5 existe para impedir.

A Sam fixou a distincao ao abrir a F5:

> Tratar explicitamente `DECISAO_DE_NEGOCIO`, `TRADUCAO_PENDENTE` e identidade
> orfa como estados de governanca com impacto na confianca do dado, e nao como
> valores faltantes comuns. O fato de um valor nao estar resolvido nao significa
> necessariamente que ele esteja "errado"; significa que existe uma decisao ou
> evidencia pendente.
>
> `dado invalido != dado nao mapeado != decisao pendente != identidade nao
> resolvida != dado quarentenado`

## Decisao

### 1. Todo check declara `finding_class`

Sete classes, declaradas em `config/quality_checks.yaml`, cada uma com
`is_pendency`:

| Classe | Pendencia? | O que significa |
|---|---|---|
| `INVALIDO` | nao | o valor viola uma regra e esta errado |
| `DIVERGENCIA` | nao | duas leituras ou duas fontes discordam; nenhuma necessariamente errada |
| `NAO_MAPEADO` | sim | valor legitimo na origem, sem mapeamento aprovado |
| `DECISAO_PENDENTE` | sim | nao existe resposta tecnica correta; falta decisao de negocio |
| `IDENTIDADE_NAO_RESOLVIDA` | sim | a pessoa existe, o vinculo entre sistemas nao foi estabelecido |
| `DESATUALIZADO` | sim | o dado existe na fonte e nao chegou, ou chegou atrasado |
| `AUSENCIA_LEGITIMA` | sim | o campo nao existia, ou nao declarar e opcao da pessoa |

Quarentena **nao e uma classe**: e um efeito, governado pela severidade. A
quinta desigualdade da Sam se sustenta por uma regra separada, na decisao 4.

### 2. O trust score e uma media ponderada unica, com atribuicao por classe

```
perda_total   = media ponderada das taxas de falha dos checks BLOCKER e CRITICAL
                das dependencias do KPI, com peso igual a records_checked
trust_score   = 1 - perda_total
perda[classe] = contribuicao daquela classe, e as contribuicoes SOMAM perda_total
```

`perda_por_erro` reune as classes nao pendentes; `perda_por_pendencia` reune as
pendentes. O relatorio mostra as duas separadas, sempre.

`quality_score` na forma do ADR-0011 (validade x cobertura) continua sendo
calculado e reportado, para continuidade com aquele ADR.

### 3. `AUSENCIA_LEGITIMA` nao entra em nenhum componente

Penalizar a confianca porque alguem optou por nao declarar raca, cor ou
deficiencia transformaria o trust score em pressao por preenchimento. A taxa e
reportada ao lado do numero como contexto de leitura, e nunca como desconto.
`WARNING` e `INFO` tambem nao entram, por ADR-0010.

### 4. Classe de pendencia nunca pode ter severidade `BLOCKER`

Tirar do analitico uma linha cujo unico problema e um mapeamento ainda nao
aprovado apagaria dado correto na origem por causa de uma fila de trabalho.
Um teste reprova o catalogo se algum check de pendencia for declarado BLOCKER.

### 5. Perda que vem so de pendencia nao derruba para `BLOCKED`

Enquanto o trust score estiver acima de `PISO_PENDENCIA` (0,40) e a perda por
erro for zero, o status maximo e `LIMITED`, com `motivo: PENDENCIA`. Nao estar
resolvido nao e o mesmo que estar errado, e a diferenca muda o que a pessoa faz
a seguir: com erro, corrige a fonte; com pendencia, decide.

### 6. Ausencia de check nao vale como aprovacao

Par (KPI, recorte) sem nenhum check aplicavel recebe `INDETERMINADO`, nunca
`CERTIFIED`. Ausencia de evidencia nao e evidencia de qualidade.

### 7. Supressao por n minimo fica em campo proprio

`suprimido_por_n_minimo` e recusa por **privacidade** (ADR-0007), nao por
qualidade. "O grupo e pequeno demais para preservar anonimato" e uma frase
diferente de "nao confio no dado", e as duas recusas precisam continuar
distinguiveis na resposta.

## Alternativas consideradas

1. **Manter so severidade.** E o estado da F3 e da F4. Funciona enquanto o
   catalogo e pequeno; com 87 checks, perde a informacao que decide a acao.
2. **Trust score como produto de um componente por classe.** Foi a primeira
   implementacao da F5 e esta errada. Cada componente era uma media dentro da
   propria classe, e classes diferentes cobrem fracoes diferentes do recorte:
   um unico check de identidade sobre 320 linhas da aquisicao, reprovando em
   100%, zerava o componente, o produto ia a zero, e o recorte `pais=BR`
   inteiro, com 208 mil linhas e validade de 0,9997, aparecia como BLOCKED. Os
   componentes nao eram comensuraveis.
3. **Media simples entre checks, sem peso.** Descartada pelo mesmo motivo, e a
   formula do ADR-0011 ja dizia **ponderada**.
4. **Um score por classe, sem numero unico.** Honesto e inutilizavel: a camada
   de resposta precisa de um criterio para decidir se responde.
5. **Penalizar nao declaracao.** Descartada na decisao 3.

## Consequencias

**Positivas**

- A pergunta "por que a confianca caiu" passa a ter resposta exata, porque as
  contribuicoes por classe somam a perda medida.
- A populacao da aquisicao, que nao tem erro nenhum e sim vinculo e decisao
  pendentes, aparece com `perda_por_erro: 0` e status LIMITED em vez de ser
  tratada como dado ruim.
- O mesmo recorte responde diferente por KPI: contar pessoas da aquisicao nao
  exige identidade resolvida, calcular turnover exige. Sai LIMITED num caso e
  BLOCKED no outro, pelo motivo certo.

**Negativas**

- Classificar 87 checks por natureza e trabalho de julgamento, como ja era o de
  classificar por severidade, e erro de classificacao agora tem efeito sobre a
  leitura do score e nao so sobre o volume da quarentena.
- Sete classes sao mais do que as cinco distincoes que a Sam nomeou.
  `DESATUALIZADO` e `DIVERGENCIA` foram acrescentadas porque os checks de
  Timeliness e Reconciliation nao cabiam em nenhuma das cinco sem distorcao, e
  aprovadas em DQ-03 no fechamento da fase. A taxonomia e fechada em sete:
  acrescentar uma oitava exige nova decisao, porque classe nova muda a leitura
  de todos os scores ja calculados.

**Riscos e mitigacao**

- *Risco:* usar `DECISAO_PENDENTE` como escapatoria para nao corrigir dado
  errado, ja que pendencia penaliza menos. *Mitigacao:* a classe fica no YAML
  versionado, ao lado do `threshold_basis`, e muda-la e uma linha de diff
  visivel em revisao.

## Referencias

- `config/quality_checks.yaml`, bloco `finding_classes`
- `src/analytics/trust.py`, `_atribuicao` e `_status`
- `tests/pipeline/test_quality.py`, bloco "As cinco distincoes"
- ADR-0010 (severidade), ADR-0011 (dependencias do KPI), ADR-0007 (n minimo)
