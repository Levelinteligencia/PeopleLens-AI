# ADR-0017: Coerencia estrutural acima de aderencia a targets agregados

- **Status:** Aceita
- **Data:** 2026-09-11
- **Origem:** decisao da Sam na aprovacao da F1, itens 1, 2 e 4
- **Fase:** vigora do F1 em diante, para toda a camada de verdade

## Contexto

Durante a F1 apareceram duas divergencias entre o que a configuracao declara e
o que a simulacao produz:

1. a **taxa de promocao** configurada como propensao anual (7% a 13% por
   segmento) se realizou entre 3,5% e 6,8%, porque promocao so acontece quando
   ha vaga na piramide alvo;
2. a **piramide de niveis** realizada ficou com mais IC2 (28,5% contra 23,9%
   alvo) e menos M1 (6,8% contra 7,7% alvo).

Nos dois casos havia um caminho facil para fechar o numero: afrouxar a
tolerancia de vaga no primeiro, forcar redistribuicao no segundo. Esse caminho
foi rejeitado.

## Decisao

**O gerador prioriza coerencia causal e estrutural sobre aderencia artificial a
targets agregados.**

Em termos operacionais:

1. Um parametro de `config/generation.yaml` declara uma **propensao ou um
   alvo**, nao um resultado garantido. A diferenca entre o declarado e o
   realizado e informacao legitima sobre o mundo simulado.
2. Uma divergencia entre alvo e realizado e **aceitavel enquanto for
   consequencia explicavel das regras do mundo**. Ela precisa ter causa
   nomeavel, documentada e reproduzivel.
3. Uma divergencia **sem causa explicavel e um bug**, e vira falha de
   validacao, nao ajuste de parametro.
4. E proibido introduzir mecanismo cujo unico proposito seja fazer um numero
   agregado coincidir com o alvo. Correcao pos-simulacao, redistribuicao
   forcada e reponderacao de resultado estao fora.
5. Toda divergencia conhecida e reportada em `metrics.py`, lado a lado com o
   valor configurado, para que ninguem descubra por acidente.

### A excecao, que confirma a regra

`turnover_modifiers.realized_calibration` **parece** violar o principio e nao
viola, porque corrige uma **ambiguidade de definicao**, nao um resultado.
`turnover_base` e a taxa de turnover como o KPI e reportado (desligamentos
sobre headcount medio), enquanto o hazard precisa de probabilidade por pessoa.
As duas grandezas sao diferentes por construcao, e a calibracao e a conversao
entre elas. Nenhum resultado foi empurrado para um alvo.

O teste para distinguir os dois casos: se o ajuste muda **como o mundo
funciona**, e proibido; se muda apenas **a unidade em que um parametro e
expresso**, e conversao e e permitido.

## Alternativas consideradas

1. **Afrouxar `vacancy_tolerance` ate a promocao bater com a propensao.**
   Rejeitada: promocao sem vaga nao existe em organizacao nenhuma, e o dataset
   perderia justamente a restricao que torna o KPI Promotion Rate interessante.
2. **Redistribuir os niveis no fim da simulacao para bater a piramide.**
   Rejeitada: quebraria o encadeamento de eventos, que e a propriedade que
   sustenta o ADR-0001.
3. **Reescrever os parametros de config para os valores realizados.**
   Rejeitada: apagaria a informacao. Saber que a propensao e 9% e a realizacao
   e 5,3% diz algo sobre a organizacao; igualar os dois numeros nao diz nada.

## Consequencias

**Positivas**

- Todo numero do dataset tem cadeia causal ate uma regra declarada.
- A diferenca entre propensao e realizacao vira material de analise: "por que a
  taxa de promocao e menor que a politica prevê?" e uma pergunta de People
  Analytics de verdade, e o dataset a responde.
- Protege a F2 da tentacao equivalente: injetar defeito extra so para fechar a
  distribuicao alvo de trust score.

**Negativas**

- Os numeros do dataset nao vao coincidir exatamente com a tabela de
  dimensionamento do Technical Design. Cada divergencia precisa de explicacao
  escrita, o que e trabalho.

**Riscos e mitigacao**

- *Risco:* o principio virar desculpa para nao investigar divergencia.
  *Mitigacao:* a regra 3 acima. Divergencia sem causa nomeada e bug, e
  `metrics.py` reporta configurado e realizado lado a lado justamente para
  que a investigacao seja obrigatoria.

## Referencias

- Technical Design v0.3, secao 17 (R1)
- ADR-0001 (geracao em dois passos), ADR-0008 (calibragem de defeitos)
- `docs/f1_validation_findings.md`
