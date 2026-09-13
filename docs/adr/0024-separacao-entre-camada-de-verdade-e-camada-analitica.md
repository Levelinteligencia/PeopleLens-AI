# ADR-0024: Nomes de camada, e a separação entre verdade e analítico

- **Status:** **Proposta** (F6, aguardando aprovação)
- **Data:** 2026-09-11
- **Origem:** conflitos C-01 e C-02 levantados na SPEC da F6
- **Fase:** vigora da F6 em diante
- **Emenda 1 (revisao da F6, diretriz 3):** a separacao passa a ter **quatro
  camadas** e nao so o schema do DuckDB. A diretriz foi explicita: Truth e
  Analytical nao podem ter objetos **fisicamente** indistinguiveis, e schema de
  consulta e distincao logica. Ver decisao 3 abaixo, reescrita.

## Contexto

Dois problemas de nome, e o segundo é perigoso.

**Primeiro.** O pipeline escreve em `data/processed/analytical_ready/`, que
contém o resultado conformado **menos** as linhas em quarentena. Isso ainda é
L2. O ADR-0014 reserva `data/processed/analytical/` para a camada L3 do
ADR-0003, que é dim e fact. Dois diretórios a um sufixo de distância,
significando camadas diferentes, num projeto cujo tema é não confundir camadas.

**Segundo, e mais grave.** A camada de verdade em `data/synthetic/truth/` já
contém `dim_employee`, `dim_organization`, `fact_headcount_snapshot`,
`fact_movement`, `fact_termination`, `fact_requisition`, `fact_application`,
`fact_performance` e `fact_compensation`. A F6 vai criar tabelas com exatamente
esses nomes a partir dos dados conformados.

São nove pares de tabelas homônimas, com a mesma forma, descrevendo universos
diferentes: um é o gabarito, o outro é o que o pipeline conseguiu reconstruir. A
distância entre os dois **é a medida do projeto**, e confundi-los inverte o
sentido da medida.

Isto é o achado 1 da F3 pré-fabricado. Lá, o RAW de uma execução foi comparado
com a verdade de outra: os dois lados existiam, tinham a forma certa, e
descreviam empresas diferentes. A comparação rodou sem erro e produziu números
plausíveis e falsos. A guarda que nasceu dali, `check_provenance`, cobre um par
de camadas. Com a L3, os pares viram três.

## Decisão

1. **`analytical_ready` passa a se chamar `conformed_approved`.** É o que ele é:
   a fatia aprovada da camada conformada. `data/processed/analytical/` fica
   livre para a L3, como o ADR-0014 sempre previu.

2. **Os nomes analíticos convencionais são mantidos.** `dim_employee` e
   `fact_headcount_snapshot` são os nomes certos para o que essas tabelas são, e
   deformá-los com prefixo defensivo tornaria o modelo pior para quem o usa.

3. **A separação é física, em quatro camadas.** Schema de consulta sozinho é
   distinção lógica: quem lê um Parquet direto do disco não passa por ele.

   | # | Camada | O que garante |
   |---|---|---|
   | 1 | caminho: `data/synthetic/truth/` × `data/processed/analytical/` | separação de armazenamento |
   | 2 | **coluna obrigatória `layer`** em toda tabela das duas camadas, com valor `truth` ou `analytical` | um leitor que receba a tabela errada descobre **pela própria tabela**, sem depender de onde ela veio |
   | 3 | manifesto próprio por camada, com `run_id`, `profile`, `scale`, `seed` e `config_hash` | proveniência verificável |
   | 4 | schemas `truth` e `analytical` no DuckDB, sem tabela não qualificada | clareza na consulta |

   A camada 2 é a que responde à diretriz: dois arquivos Parquet com o mesmo
   esquema e o mesmo nome deixam de ser indistinguíveis assim que cada um
   carrega, no próprio conteúdo, a declaração de qual camada ele é. Um guarda
   de leitura (`assert_layer`) reprova na entrada de qualquer função que espere
   uma camada e receba a outra.

4. **Toda tabela analítica carrega proveniência:** `run_id`, `profile`, `scale`,
   `seed` e `config_hash`, e a L3 escreve seu próprio manifesto.

5. **`check_provenance` passa a guardar três pares**, e não um: raw × verdade,
   raw × analítico, verdade × analítico. Divergiu em `seed`, `profile` ou
   `scale`, a comparação não roda e o relatório diz por quê.

6. **Nenhum código de construção da L3 lê `data/synthetic/truth/`.** A verdade é
   insumo de avaliação, nunca de construção. Um teste verifica a ausência dessa
   leitura, porque o atalho é tentador exatamente onde o dado conformado é ruim.

## Alternativas consideradas

1. **Prefixar as tabelas analíticas** (`an_dim_employee`). Descartada: piora o
   modelo para todo mundo, e prefixo é a forma mais fácil de um nome virar ruído
   que ninguém lê. A coluna `layer` resolve o mesmo risco sem deformar o nome, e
   resolve melhor: prefixo protege quem lê o nome do arquivo, `layer` protege
   quem lê a tabela.
2. **Renomear as tabelas da camada de verdade.** Descartada: a camada de verdade
   é anterior, está estável desde a F1 e os nomes dela são os nomes naturais do
   que ela descreve.
3. **Confiar no caminho do diretório.** É o que já existe, e o achado 1 da F3
   mostrou que caminho diferente não impede confusão quando os dois lados têm a
   mesma forma.
4. **Manter `analytical_ready` e usar outro nome para a L3.** Descartada: o nome
   errado é `analytical_ready`, e preservá-lo obrigaria a inventar um nome pior
   para a camada que o ADR-0003 já chamou de analytical.

## Consequências

**Positivas**

- Elimina, antes de existir, uma classe de erro que o projeto já pagou uma vez.
- A comparação verdade × analítico, que é a métrica central da F12, passa a ter
  guarda desde o primeiro dia.
- O nome de cada diretório volta a descrever a camada que ele contém.

**Negativas**

- Renomear um diretório quebra caminhos em código e em documentação de fases
  anteriores. É uma mudança mecânica e única, e a suíte de testes cobre o
  pipeline ponta a ponta.
- Um schema a mais no DuckDB é uma cerimônia a mais em cada consulta, e a coluna
  `layer` é uma coluna a mais em cada tabela das duas camadas. O custo é
  constante e pequeno; o erro que ele evita já custou uma fase inteira.

**Riscos e mitigação**

- *Risco:* alguém ler a verdade durante a construção da L3 para "completar" um
  campo que o conformado não tem, como a origem da aquisição.
  *Mitigação:* o teste da decisão 6, e o fato de que esse atalho produziria um
  modelo que passa na avaliação contra si mesmo.

## Referências

- `docs/F6_analytical_model.md`, conflitos C-01 e C-02
- ADR-0003 (camadas), ADR-0014 (diretórios), ADR-0018 (proveniência)
- `docs/f3_validation_findings.md`, achado 1
