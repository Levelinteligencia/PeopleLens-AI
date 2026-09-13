# ADR-0027: Proveniência não é identidade

- **Status:** **Proposta** (F6, aguardando aprovação)
- **Data:** 2026-09-12
- **Origem:** diretriz 1 da revisão da SPEC da F6, decisão D-01
- **Fase:** vigora da F6 em diante

## Contexto

A primeira versão da SPEC da F6 propunha derivar a origem de uma pessoa —
crescimento orgânico ou aquisição — a partir de `xref_employee_identity`, quando
o vínculo entre o cadastro da VivaMarket e o HRIS corporativo estivesse
resolvido.

A proposta era defensável e estava errada, e o número mostra por quê: a
identidade da VivaMarket está **0% resolvida**, os 320 registros estão em
`MANUAL_REVIEW` aguardando decisão humana, e a regra renderia **zero pessoas
classificadas** por tempo indeterminado.

O erro de fundo é conceitual, não de calibragem. A regra amarrava duas perguntas
que são independentes:

| | Proveniência | Identidade |
|---|---|---|
| pergunta | de qual sistema este registro veio, e o que isso prova sobre como a pessoa entrou | estes dois registros são a mesma pessoa? |
| unidade | o registro | o par de registros |
| quando é conhecida | **sempre**: o registro veio de algum lugar | só quando o vínculo é aprovado |
| erra como | classificação errada, visível na configuração | fusão errada de pessoas, invisível |

Um registro em `VIVAMARKET_LEGACY.employee_master` é, inequivocamente, de alguém
que entrou pela aquisição. Isso é verdade pelo arquivo em que ele chegou, e não
depende de resolver com quem ele corresponde no HRIS. Exigir identidade para
afirmá-lo é exigir a resposta de uma pergunta difícil para responder uma fácil.

## Decisão

### 1. Proveniência é atributo do registro, determinada pela fonte

`config/sources.yaml` ganha o campo `determines_origin` por sistema. Quando
preenchido, todo registro daquele sistema recebe aquela origem, sem exceção e
sem inferência:

```yaml
VIVAMARKET_LEGACY:
  determines_origin: AQUISICAO_VIVAMARKET
COMPRAFACIL_ERP:
  determines_origin: AQUISICAO_COMPRAFACIL
HRIS_CORE:
  determines_origin: null      # nao determina origem
HRIS_LEGACY:
  determines_origin: null      # nao determina origem
```

**`HRIS_CORE` e `HRIS_LEGACY` não determinam origem, e isso é declarado.**
Marcá-los como orgânico faria toda pessoa absorvida da aquisição aparecer como
contratação, fechando o headcount com uma mentira.

### 2. Três níveis de determinação, avaliados em ordem

| Nível | Regra | Base declarada |
|---|---|---|
| **P1** | o sistema-fonte determina | `sources.yaml`, `determines_origin` |
| **P2** | admissão anterior ao início da série | `generation.yaml`, início da série |
| **P3** | candidatura no ATS que resultou em admissão, com identidade resolvida | `ATS_CLOUD.application` |
| — | nenhuma se aplica | `INDETERMINADA` |

P3 usa identidade, e isso não contradiz este ADR: ali a identidade é
**evidência positiva de processo** (a pessoa passou pelo funil de recrutamento),
não pré-requisito para classificar. Onde P1 se aplica, P3 é irrelevante.

### 3. `INDETERMINADA` é um resultado legítimo e frequente

Hoje, 58,1% das pessoas do HRIS corporativo ficam `INDETERMINADA`. É
desconfortável e é a resposta correta. A alternativa — chamar o resto de orgânico
— daria 100% de cobertura e uma taxa de contratação inflada em até 7,8%, com
cara de fato.

O teto da contaminação é conhecido e declarável: no máximo 320 das 4.111 pessoas
classificadas como `INDETERMINADA` são da aquisição, e esse teto cai conforme as
320 decisões de identidade forem tomadas.

### 4. Origem nunca é inferida por atributo da pessoa

Proibido derivar origem de data de admissão, departamento, localidade, nome,
cargo, senioridade, faixa salarial ou qualquer combinação deles. Nenhum desses
campos carrega a informação. Dois casos de falha protegem a regra: um pico de
entradas em agosto de 2022 e qualquer contagem de contratação que inclua
`INDETERMINADA`.

### 5. Identidade continua sendo o único mecanismo de junção

`xref_employee_identity` segue governado pelo ADR-0004, com as mesmas regras e
as mesmas proibições. Proveniência classifica; identidade junta. Uma não
substitui a outra e nenhuma das duas ganha atribuição nova por causa deste ADR.

### 6. Registro sem identidade resolvida vira pessoa provisória

Consequência necessária, e sem ela a decisão 1 não produz nada contável: se a
chave de `dim_employee` fosse apenas o `employee_id` corporativo, os 320
registros da VivaMarket — que não têm um — colapsariam num membro reservado e
deixariam de ser pessoas.

`dim_employee.party_key` é `EMP:<employee_id>` quando a identidade é `RESOLVED`,
e `SRC:<sistema>:<id de origem>` em qualquer outro caso, com
`is_provisional_person = true`. A fusão de uma pessoa provisória com a
consolidada é **evento governado e registrado**, nunca efeito colateral de
recarga.

Isto não cria matching: é o oposto, recusa fundir sem decisão humana.

## Alternativas consideradas

1. **Manter a origem dependente da identidade** (proposta original). Correta no
   princípio de não inventar vínculo, e errada na consequência: adia
   indefinidamente uma informação que já está disponível, e confunde duas
   perguntas independentes.
2. **Marcar `HRIS_CORE` como origem orgânica.** Daria cobertura total e
   classificaria como contratação toda pessoa absorvida. É exatamente o que a
   diretriz 4 proíbe.
3. **Inferir a aquisição por concentração de datas de admissão.** Verificado e
   descartado por evidência: agosto de 2022 tem 45 admissões contra 39 em julho
   e 44 em setembro. As pessoas entraram com a data de admissão original, que vai
   de 2000 a 2022. Não há pico porque não há o que detectar.
4. **Uma dimensão de origem e outra de tipo de entrada.** Dois vocabulários para
   o mesmo conceito, que podem divergir. `dim_origin` exerce os dois papéis.
5. **Deixar a origem como coluna de texto no fato.** Perderia
   `determination_rule`, `evidence_source` e a capacidade de contar por classe
   sem depender de string.

## Consequências

**Positivas**

- 320 pessoas classificadas como aquisição imediatamente, sem resolver uma única
  identidade e sem inferir nada.
- A separação torna explícito que origem conhecida não implica identidade
  resolvida, o que estava implícito e sendo violado.
- `determination_rule` e `evidence_source` viajam com cada classificação, então
  "por que esta pessoa é da aquisição" tem resposta sem consultar código.
- O teto de contaminação vira um número declarável em vez de uma incerteza.

**Negativas**

- 58,1% de `INDETERMINADA` é um número ruim de apresentar, e é o número certo.
  Qualquer melhora dele tem que vir de evidência nova, não de regra nova.
- Pessoa provisória faz a mesma pessoa existir duas vezes no modelo enquanto o
  vínculo não for aprovado. `is_system_of_record` evita a dupla contagem no
  headcount, mas quem consultar fora dessa guarda vai encontrar as duas.
- Um campo novo em `sources.yaml` que, preenchido errado, classifica uma
  população inteira errado. É visível em diff, o que é a mitigação possível.

**Riscos e mitigação**

- *Risco:* alguém preencher `determines_origin` em `HRIS_CORE` para reduzir os
  58% de `INDETERMINADA`. *Mitigação:* o caso de falha F-15 e a decisão D-10, que
  torna a não determinação uma escolha registrada e não um esquecimento.

## Referências

- `docs/F6_analytical_model.md`, Partes II e X
- ADR-0004 (identidade), ADR-0022 (natureza da perda), ADR-0025 (membros
  reservados), ADR-0026 (sistema observador no grain)
- `config/sources.yaml`, `headcount_brought: 3200` e `load_type: one_shot`
