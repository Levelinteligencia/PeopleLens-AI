# ADR-0010: Severidade nos resultados de data quality

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D10 (Technical Design v0.3)
- **Fase:** F0, vigora a partir da F5

## Contexto

`data_quality_results`, como especificado, tem `status` e `threshold`. O
threshold diz **quando** um check falha. Não diz **o que fazer** quando ele
falha, e essas são dimensões diferentes.

Sem essa distinção surge um dilema sem saída: ou toda falha manda o registro
para a quarentena, e quase nada sobrevive ao primeiro processamento de um
dataset propositalmente sujo, ou nenhuma manda, e a quarentena fica vazia e
decorativa.

## Decisão

Acrescentar `severity` a `data_quality_results`, com quatro níveis e efeito
declarado:

| Severidade | Efeito |
|---|---|
| `BLOCKER` | registro vai para `data_quarantine` e não entra no analítico |
| `CRITICAL` | registro entra, e o check derruba o `quality_score` do KPI que depende dele |
| `WARNING` | registra e monitora, não afeta trust score |
| `INFO` | apenas observabilidade |

A severidade é atributo **do check**, declarada no YAML do check, e não do
resultado de uma execução.

## Alternativas consideradas

1. **Só `status` pass/fail.** Leva ao dilema descrito acima.
2. **Threshold por check, sem severidade.** Confunde duas dimensões diferentes.
3. **Severidade calculada dinamicamente pela taxa de falha.** Descartada: a
   gravidade de uma data impossível não depende de quantas existem.
4. **Quatro níveis fixos.** Escolhida.

## Consequências

**Positivas**

- Liga a camada de DQ às outras duas: `BLOCKER` aciona quarentena, `CRITICAL`
  alimenta trust score, o resto observa.
- Dá regra de acionamento objetiva para dois componentes que sem isso ninguém
  saberia preencher.

**Negativas**

- Classificar 70 checks por severidade é trabalho de julgamento, e erro de
  classificação tem efeito direto no volume da quarentena.

**Riscos e mitigação**

- *Risco:* excesso de `BLOCKER` esvaziar o analítico. *Mitigação:* a proporção
  de registros em quarentena é um dos critérios de saída da calibragem da F2
  (`config/defects.yaml`, `calibration.exit_criteria`: abaixo de 3%).

## Referências

- Technical Design v0.3, seções 10.2 e 18 (D10)
- Especificação do Universo v1.0, seções 18 e 19
