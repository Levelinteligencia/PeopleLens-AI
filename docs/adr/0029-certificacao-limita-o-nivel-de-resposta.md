# ADR-0029: Certificação de KPI limita o nível de resposta, independente da qualidade do dado

- **Status:** **Proposta** (F7, aguardando aprovação)
- **Data:** 2026-09-12
- **Origem:** F7, decisão D7-03
- **Fase:** vigora da F7 em diante

## Contexto

A F5 entregou um trust score que responde a uma pergunta: **o dado está certo?**
Ele é a média ponderada da perda dos checks BLOCKER e CRITICAL, com a perda
atribuída exatamente por classe de achado (ADR-0022), e bandas fixas
(ADR-0023): `CERTIFIED ≥ 0,95`, `LIMITED ≥ 0,70`, piso de pendência 0,40.

Existe uma segunda pergunta, que o trust score não responde e que a F7 obriga a
enfrentar: **alguém assinou esta definição?**

As duas são independentes, e o caso que prova isso já está no catálogo:

| KPI | Dado | Definição |
|---|---|---|
| `internal_mobility_rate` | `fact_movement` tem qualidade alta; os checks passam | `movement_type` tem **dois vocabulários coexistindo**: `Promotion` 491 e `PROMOCAO` 110, `Transfer` 480 e `TRANSFERENCIA` 92 |

O número sai limpo e sai errado: 491 ou 601 conforme quem escreveu a consulta.
Isso não é qualidade de dado baixa. É um KPI **sem definição fechada**, e um
trust score alto sobre ele é pior do que um trust score baixo, porque tem cara
de confiável.

O inverso também ocorre: `hiring_volume` tem definição assinada e cobertura de
origem de 30% (1.499 de 5.030 pessoas com `origin = CONTRATACAO`). Ali o
problema é do dado, e a definição está firme.

Sem uma segunda dimensão, os dois casos colapsam no mesmo número e a resposta
perde a informação que mais importa: **o que precisa acontecer para melhorar**.

## Decisão

### 1. Duas dimensões de confiança, e a menor manda

```
trust_dado        = 1 − perda ponderada dos checks das dependências, no recorte   (F5)
trust_governanca  = teto do status de certificação do KPI                         (F7)
trust_resposta    = min(trust_dado, trust_governanca)
```

`trust_dado` é da F5 e **não muda**: mesma fórmula, mesmos pesos, mesmas classes
ignoradas, mesmas bandas. Este ADR não toca em nenhum threshold de DQ.

### 2. O teto por status

| Status do KPI | Teto de confiança | Teto de nível de resposta |
|---|---|---|
| `CERTIFIED` | sem teto | INTERPRETATION com regra registrada; CAUSALITY com estudo |
| `DECLARED` | `LIMITED` | CONTEXT |
| `DEPRECATED` | `LIMITED` | CONTEXT, só período histórico |
| `BLOCKED` | — | recusa |
| `DRAFT` | — | recusa |

**Um KPI não certificado nunca responde como CERTIFIED**, por mais limpo que
esteja o dado. Um dado impecável sob uma definição que ninguém assinou produz um
número preciso sobre uma pergunta indefinida.

### 3. O motivo do teto viaja com a resposta

A resposta declara qual das duas dimensões limitou e por quê. Não basta dizer
`LIMITED`: um `LIMITED` por definição não certificada e um `LIMITED` por
cobertura de população baixa exigem ações diferentes, de pessoas diferentes.

```yaml
trust: {status: LIMITED, score: 0.71, limitado_por: GOVERNANCA,
        motivo: "KPI em DECLARED; certificação pendente"}
```

### 4. A certificação não é calculável

`CERTIFIED` é resultado de aprovação humana registrada, com dono e data, e não
de um limiar sobre o trust score. Promover automaticamente um KPI porque o dado
melhorou é o mesmo erro que a F4 proíbe na promoção de mapeamento: não há
aprovação automática.

O caminho inverso é permitido e é operação normal: um KPI `CERTIFIED` cujo dado
degradou responde com `trust_dado` baixo. A certificação continua válida; o
número é que não está bom. A distinção é o ponto inteiro deste ADR.

### 5. Nenhum score artificial

O teto de governança não é um número inventado: é um mapeamento declarado de
status para banda, e o status vem do ciclo de vida do ADR-0030. Nenhum
componente de `trust_resposta` é estimado.

## Alternativas consideradas

1. **Deixar só o trust score da F5 e sinalizar a certificação como um flag na
   resposta.** Mais simples, e falha no caso `internal_mobility_rate`: o número
   sai com trust alto e um aviso ao lado, e o aviso é o que se ignora.
2. **Rebaixar o trust score do KPI não certificado penalizando-o numericamente.**
   Foi descartado: seria score artificial, proibido pela F5, e misturaria numa
   mesma escala duas coisas que precisam ser distinguíveis na resposta.
3. **Multiplicar as duas confianças.** Mesma patologia que a F5 já corrigiu no
   trust score composto: o produto cai rápido demais e deixa de ser
   interpretável. O mínimo preserva a leitura "o elo mais fraco é este".
4. **Certificar automaticamente todo KPI cujo trust passe de 0,95.** Torna a
   certificação uma consequência do dado, e a governança some. É o oposto do
   princípio central da F7.
5. **Bloquear toda consulta a KPI não certificado.** Perde o caso útil: um KPI
   `DECLARED` respondido em CONTEXT, com o limite dito, é informação honesta.

## Consequências

**Positivas**

- Um número limpo sob definição frágil deixa de parecer confiável, que é o modo
  de falha mais caro de uma camada semântica.
- A resposta passa a dizer **quem** resolve: pendência de dado vai para
  engenharia e qualidade; pendência de definição vai para People Analytics.
- `internal_mobility_rate` pode entrar no catálogo visivelmente bloqueado, em vez
  de ficar fora e reaparecer como consulta ad hoc sem governança.
- A certificação vira um ato registrado e datado, auditável como os demais atos
  de governança do projeto.

**Negativas**

- Nove KPIs calculáveis respondem com teto `LIMITED` na v1.0, e isso é
  desconfortável de apresentar num portfólio. É a resposta correta: eles não
  foram certificados.
- Há dois estados a manter por KPI em vez de um, e eles podem divergir de forma
  não óbvia (certificado com dado ruim, declarado com dado ótimo). A resposta
  precisa explicar isso toda vez.
- Certificar exige processo humano, e nada no projeto acelera esse processo.

**Riscos e mitigação**

- *Risco:* certificar em lote para destravar a demonstração. *Mitigação:* a
  transição `DECLARED → CERTIFIED` exige dono, data e dependências verificadas,
  e o registro fica no contrato — o mesmo padrão que impediu a aprovação em lote
  dos 43 `APELIDO_CONHECIDO` na F4.
- *Risco:* alguém ler `min()` como "o trust caiu" e tentar melhorar o dado para
  destravar um teto que é de governança. *Mitigação:* `limitado_por` é campo
  obrigatório da resposta.

## Referências

- `docs/F7_semantic_layer.md`, Partes IV e VII
- ADR-0015 (níveis de resposta), ADR-0022 (classe de achado e natureza da perda),
  ADR-0023 (bandas preservadas, calibragem por recorte fino), ADR-0030 (ciclo de
  vida do KPI)
- F5, decisão DQ-04
