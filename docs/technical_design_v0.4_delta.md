# Technical Design v0.4: delta sobre a v0.3

A v0.3 continua sendo a **linha de base aprovada**. Este documento registra, seção
por seção, o que as fases F4 e F5 mudaram nela, e por quê. É um delta e não uma
reescrita, de propósito: reescrever um documento aprovado de 95 KB para acomodar
mudanças pontuais é a forma mais eficiente de perder o rastro de qual decisão
mudou o quê.

Formato de cada entrada: **seção da v0.3 → o que muda → ADR que autoriza.**

---

## Seção 10.1, catálogo de Data Quality

**v0.3:** "aproximadamente 70 checks, a serem detalhados na F5".

**v0.4:** 87 checks implementados, cobrindo as sete dimensões obrigatórias e os
cinco sistemas da onda 1, com 21 expectativas distintas. A onda 2 acrescenta os
checks dos seus próprios sistemas quando entrar.

Cada check ganha dois campos que a v0.3 não previa:

| Campo | Valores | Por quê |
|---|---|---|
| `finding_class` | sete classes (ver 10.2) | ADR-0022 |
| `threshold_basis` | `invariante`, `derivado`, `provisional` | limiar sem base declarada é palpite, e palpite não marcado vira fato |

Distribuição da base dos limiares: 49 invariantes, 18 derivados, 20 provisionais.
Os 20 provisionais permanecem **não congelados** até a F7 (decisão DQ-02).

Dois campos opcionais foram acrescentados ao contrato do check, ambos declarativos:

- `filter` e `reference_filter`: recorte declarado do escopo, exigido por
  qualquer reconciliação entre fontes de vigência ou população diferentes.
  Nasceu do achado 1 da F5;
- `identity_system`: qual sistema do `xref` serve de universo para um check de
  cobertura de identidade.

## Seção 10.2, `data_quality_results`

**v0.3:** a tabela carrega `check_id`, `dataset`, `status`, `threshold`,
`severity`, `records_checked`, `records_failed`, `failure_rate`, `run_date`.

**v0.4:** acrescenta **`finding_class`**, e a taxonomia é fechada em sete valores
(ADR-0022, Emenda 1 aprovada em DQ-03):

| Classe | Pendência? |
|---|---|
| `INVALIDO` | não |
| `DIVERGENCIA` | não |
| `NAO_MAPEADO` | sim |
| `DECISAO_PENDENTE` | sim |
| `IDENTIDADE_NAO_RESOLVIDA` | sim |
| `DESATUALIZADO` | sim |
| `AUSENCIA_LEGITIMA` | sim |

A razão está no ADR-0022: `threshold` diz **quando** o check reprova, `severity`
diz **o que acontece** com a linha, e faltava dizer **que natureza** tem o
problema. Sem a terceira dimensão, um salário negativo e um departamento sem
mapa entram no mesmo saco, e o sistema passa a tratar fila de decisão como
defeito de dado.

Acrescentar uma oitava classe exige nova decisão, porque classe nova muda a
leitura de todos os scores já calculados.

## Seção 10.3, quarentena

**v0.3:** a linha reprovada por check BLOCKER vai para `data_quarantine`.

**v0.4:** sem mudança de mecanismo, com duas precisões e um campo novo:

1. `data_quarantine` carrega `finding_class`, herdada do check acionador;
2. **classe de pendência nunca pode ter severidade BLOCKER**, e um teste reprova
   o catálogo se alguém declarar uma. Tirar do analítico uma linha cujo único
   problema é um mapeamento não aprovado apagaria dado correto por causa de uma
   fila de trabalho;
3. a quarentena é acionada **por regra, não por resultado agregado**: a linha
   reprovada por um BLOCKER sai mesmo que o check como um todo tenha passado
   dentro do limiar. O limiar governa o status do check; a severidade governa o
   destino da linha.

## Seção 11.2 e 11.3, contrato de KPI e trust score

**v0.3 (via ADR-0011):** contratos em `src/analytics/kpis/<kpi>.yaml`, com
`depends_on_checks` e `depends_on_mappings`, e a fórmula

```
quality_score = média ponderada do pass rate dos checks em depends_on_checks
              × (1 − taxa de UNMAPPED nos campos de depends_on_mappings)
```

**v0.4:**

- os contratos vivem em **`config/kpis/<kpi>.yaml`**, não em `src/`. São
  configuração declarativa, e `src/` é código;
- **`depends_on_checks` não é digitado**: é derivado de `consumed_by_kpis` no
  catálogo de checks. Duas listas descrevendo a mesma relação em lugares
  diferentes divergem, e a divergência é silenciosa. `contracts.verify` reprova
  nos dois sentidos;
- 18 contratos, cada um com `grain`, `formula`, `minimum_n` e `response_levels`
  declarados;
- `quality_score` continua calculado na forma do ADR-0011, e o **trust score
  passa a ser outra coisa**:

```
perda_total   = média ponderada das taxas de falha dos checks BLOCKER e CRITICAL
                das dependências, com peso = records_checked no recorte
trust_score   = 1 − perda_total
perda[classe] = contribuição daquela classe; as contribuições SOMAM perda_total
```

A mudança de forma está justificada no ADR-0022 e no achado 4 da F5: um produto
de componentes por classe não funciona porque os componentes não são
comensuráveis — cada um é uma média dentro da própria classe, e classes
diferentes cobrem frações diferentes do recorte.

O que fica **fora** do score, por decisão e não por omissão: `AUSENCIA_LEGITIMA`,
`WARNING`, `INFO`, e a supressão por n mínimo.

## Seção 11.4 e 23, `trust_status`

**v0.3:** `CERTIFIED`, `LIMITED`, `BLOCKED`.

**v0.4:** os três permanecem, e acrescenta-se **`INDETERMINADO`**, para o par
(KPI, recorte) que não tem nenhum check aplicável. Ausência de evidência não é
evidência de qualidade, e sem esse quarto valor um recorte sem cobertura sairia
como `CERTIFIED`.

Dois campos acompanham o status e não existiam na v0.3:

- `motivo` ∈ `OK`, `ERRO`, `PENDENCIA`, `IDENTIDADE`, `ATUALIDADE`,
  `SEM_EVIDENCIA`, para que a recusa seja explicável;
- `suprimido_por_n_minimo`, em campo próprio, porque recusa por privacidade
  (ADR-0007) é diferente de recusa por confiança.

Regra nova, do ADR-0022: **perda que vem só de pendência não derruba para
`BLOCKED`** enquanto o score estiver acima de `PISO_PENDENCIA` (0,40) e a perda
por erro for zero.

Bandas provisórias: `CERTIFIED ≥ 0,95`, `LIMITED ≥ 0,70`. Por DQ-04 e ADR-0023,
**elas não se movem na calibragem da F7**, que acontece por recorte fino.

## Seção 14, DE/PARA

**v0.3:** mapeamento com `valid_from` e `valid_to`, e ciclo de vida
`APPROVED`/`PROPOSED`/`DEPRECATED`/`REJECTED`.

**v0.4 (F4):**

- a vigência passa a ser **aplicada de verdade**: `DATASET_SPEC` declara, por
  dataset, qual coluna dá a data de referência do registro, e `lookup()` só
  considera uma linha aprovada dentro da janela. `performance_rating` tem duas
  janelas e fica com zero `UNMAPPED`;
- **vigência padrão é aberta.** Janela fechada é reservada para mudança real de
  significado. A primeira versão dava `valid_from: 2016-01-01` a todo mapeamento
  semeado, e pessoas admitidas antes de 2016 caíam em `UNMAPPED`;
- a fila de exceções ganha `suggestion_method` e a proposta de resolução
  classifica cada exceção em cinco classes, incluindo `TRADUCAO_PENDENTE`
  (ADR-0020): quando a língua declarada do sistema difere da do domínio
  corporativo, **nenhum candidato é oferecido**, porque similaridade de
  caractere entre vocabulários diferentes não é evidência.

## Seção 17, filas de governança

**v0.4 (F4, ADR-0021):**

- reexecutar o pipeline **não apaga decisão**: `reset()` remove apenas itens
  `OPEN`. Antes, um valor rejeitado voltava `OPEN` na execução seguinte, e
  rejeitar virava sinônimo de esquecer;
- todo caso de identidade guarda o `run_id` da última execução em que foi
  observado, e o que some fica **visível, não apagado**.

## Seção 3, inventário de sistemas

**v0.4 (F4, ADR-0020):** `sources.yaml` passa a declarar `field_language` para
os doze sistemas, e `meta.canonical_field_language` para o domínio corporativo.
A distância entre as duas é o que separa "variação de escrita" de "tradução", e
as duas exigem revisores diferentes.

## Seções sem mudança

Continuam valendo exatamente como na v0.3: 1 a 2 (contexto e princípios), 4 a 9
(modelo físico, geração, defeitos, camadas), 12 e 13 (lineage), 15 e 16
(pseudonimização, n mínimo), 18 a 22 (decisões arquiteturais, RAG, MCP,
interface), 24 em diante (roadmap).

---

## Rastro de decisões desta versão

| Decisão | O que fixa | Onde vive |
|---|---|---|
| DQ-01 | `centro_custo` fica como veio do RAW; finding de completude permanente | `docs/f5_completeness_gaps.md` |
| DQ-02 | os 20 limiares provisionais não são congelados na F5 | `config/quality_checks.yaml`, `meta` |
| DQ-03 | `DESATUALIZADO` e `DIVERGENCIA` entram na taxonomia oficial | ADR-0022, Emenda 1 |
| DQ-04 | calibragem da F7 por recorte fino, bandas preservadas | ADR-0023 |

ADRs criados desde a v0.3: 0018, 0019 (F3), 0020, 0021 (F4), 0022, 0023 (F5).
