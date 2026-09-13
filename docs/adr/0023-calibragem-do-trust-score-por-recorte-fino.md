# ADR-0023: Calibragem do trust score por recorte fino, com as bandas preservadas

- **Status:** Aceita
- **Data:** 2026-09-11
- **Origem:** decisao DQ-04, fechamento da F5
- **Fase:** vigora na F7, e restringe o que a F6 pode assumir

## Contexto

`config/defects.yaml` declara uma distribuicao alvo de confianca:

| Status | Alvo | Realizado na F5 |
|---|---|---|
| CERTIFIED | 60% a 70% | **96,8%** |
| LIMITED | 20% a 25% | 2,6% |
| BLOCKED | 10% a 15% | 0,5% |

A distancia e grande, e a causa e mecanica, nao um erro de calculo.

O trust score e uma media ponderada sobre a populacao do recorte, e os defeitos
deste universo sao **concentrados**: a aquisicao VivaMarket sao 320 de 300.419
linhas. Num recorte grosso, 320 linhas 100% problematicas movem o score em
0,001. O recorte `pais=BR` sai em 0,9986 e **isso esta certo**: contar pessoas
no Brasil e confiavel, e dizer o contrario por causa de 320 linhas seria repetir
o achado 4 da F5, em que componentes nao comensuraveis derrubavam um recorte de
208 mil linhas por causa de um check sobre 320.

Havia entao duas formas de aproximar o realizado do alvo, e elas nao sao
equivalentes.

## Decisao

**A calibragem da F7 acontece por recorte fino. As bandas de trust score nao se
movem.**

1. As faixas permanecem como estao: `CERTIFIED >= 0,95`, `LIMITED >= 0,70`,
   `PISO_PENDENCIA = 0,40`. Elas seguem marcadas como provisorias no codigo ate
   a F7 confirma-las, e confirmar aqui significa **manter**, nao ajustar.
2. A F7 avalia confianca na granularidade da **pergunta**, nao numa grade fixa.
   O recorte de um KPI e determinado por: o grao declarado no contrato, a
   populacao efetivamente envolvida, e as dependencias daquele KPI.
3. Os recortes da F5 (pais, ano, sistema de origem, avaliados isoladamente) sao
   **de demonstracao da logica**, nao de calibragem. A F7 usa combinacoes, e as
   que isolam populacao problematica sao as que importam: a aquisicao, a janela
   de migracao de 2019, o periodo 2016 a 2018, os paises menores.
4. Se, com recorte fino, a distribuicao continuar fora da faixa, **a faixa alvo
   e que e revista**, com evidencia, e nao os limiares do score. A faixa alvo em
   `defects.yaml` e uma expectativa de desenho; o score e medida.

## Alternativas consideradas

1. **Mexer nas bandas ate a distribuicao bater no alvo.** Descartada, e e o
   ponto inteiro deste ADR. Baixar `CERTIFIED` de 0,95 para, digamos, 0,999
   produziria a distribuicao desejada em uma tarde e destruiria o significado
   do numero: a banda passaria a ser escolhida pelo resultado que produz, que e
   exatamente a intervencao que o ADR-0017 proibe. Um trust score cujo limiar
   foi escolhido para dar uma distribuicao bonita nao mede confianca, mede a
   vontade de quem o calibrou.
2. **Mexer nas bandas e nos recortes ao mesmo tempo.** Pior que a anterior: com
   dois graus de liberdade e um alvo, sempre existe solucao, e nenhuma delas e
   informativa. Se as duas coisas mudam, nao da para saber qual explicou o
   resultado.
3. **Aceitar a distribuicao atual e ajustar a expectativa em `defects.yaml`.**
   Considerada e adiada. Pode ser a conclusao correta da F7, mas so depois de
   medir com recorte fino: mudar a expectativa antes de medir seria desistir da
   pergunta.
4. **Ponderar o score por severidade do defeito em vez de por populacao.**
   Descartada: reintroduz o problema do achado 4, porque severidade e populacao
   sao grandezas diferentes e combina-las num peso unico esconde qual das duas
   moveu o numero.

## Consequencias

**Positivas**

- O trust score continua sendo uma medida, e nao um parametro ajustado ao
  resultado esperado.
- A F7 passa a ter um criterio de sucesso claro e falsificavel: com recorte
  fino, a aquisicao e a janela de 2019 precisam produzir LIMITED e BLOCKED sem
  que ninguem toque em limiar.
- Fecha um dos criterios de saida da calibragem em `defects.yaml`: "pelo menos
  um KPI CERTIFIED e um BLOCKED respondiveis pela mesma pergunta em recortes
  diferentes". A F5 ja demonstrou isso entre KPIs na mesma populacao; a F7 tem
  que demonstrar entre recortes.

**Negativas**

- Recorte fino multiplica o numero de pares KPI x recorte, e cada par re-executa
  os checks das dependencias naquele recorte. A F5 gasta cerca de 4 segundos com
  22 recortes; uma grade de pais x ano x business unit e uma ordem de grandeza
  maior. A instrumentacao da F4 ja mede isso, e a decisao de otimizar continua
  dependendo de evidencia.
- Recorte fino cai mais rapido no n minimo do ADR-0007, entao mais respostas
  passam a ser suprimidas por privacidade. Isso e correto e vai parecer
  cobertura pior; a distincao entre "suprimido por privacidade" e "sem
  confianca" ja existe em campo proprio desde a F5 (ADR-0022, decisao 7),
  justamente para que os dois nao sejam confundidos quando isso acontecer.

**Riscos e mitigacao**

- *Risco:* alguem, na F7, mover a banda "so um pouquinho" para fechar a
  distribuicao. *Mitigacao:* as bandas vivem em `src/analytics/trust.py` numa
  constante unica, com este ADR citado ao lado, e a mudanca aparece como uma
  linha de diff em revisao.

## Referencias

- `config/defects.yaml`, `calibration.target_trust_distribution` e
  `trust_calibration_phase: F7`
- `src/analytics/trust.py`, constantes `BANDS` e `PISO_PENDENCIA`
- `docs/f5_validation_findings.md`, achados 4 e 5
- ADR-0017 (coerencia acima de aderencia a target), ADR-0022 (natureza da
  perda), ADR-0007 (n minimo)
