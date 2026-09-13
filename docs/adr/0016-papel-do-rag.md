# ADR-0016: Papel do RAG no projeto

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** Technical Design v0.3, seção 17 (R10)
- **Fase:** F0, vigora a partir da F10

## Contexto

O PeopleLens precisa responder perguntas em linguagem natural sobre KPIs
governados. Duas etapas distintas aparecem nesse fluxo: **encontrar** qual
métrica, definição ou regra responde à pergunta, e **calcular** o número.

A arquitetura popular hoje trata as duas com a mesma ferramenta, indexando dados
e recuperando por similaridade. Vale registrar onde cada abordagem serve.

## Decisão

**RAG é usado, e é usado sobre o acervo textual do projeto:**

- definição de negócio dos KPIs;
- regras de inclusão e exclusão;
- política de confidencialidade e regras de supressão;
- ADRs e o histórico de decisões de mapeamento;
- dicionário de dados e documentação de incidentes.

Esse acervo é linguagem, cresce com o projeto, não cabe em prompt, e é
exatamente o problema para o qual recuperação semântica foi feita.

**RAG não é usado como etapa de cálculo de KPI.** Indexar linhas de fato e
agregar o que voltou da busca é inadequado por um motivo de **completude**, não
de qualidade do modelo: busca por similaridade devolve os k itens mais
próximos, e um KPI exige o conjunto **completo** que satisfaz um predicado. As
200 linhas mais parecidas com a pergunta não são as 4.031 que compõem o turnover
do Brasil, e a diferença não aparece na resposta.

Para seleção exata sobre dado estruturado, a ferramenta é consulta com
predicado, e é o que o SQL governado faz.

**Regra que resume:** RAG para encontrar a definição, a regra e o contexto;
consulta governada sobre dado estruturado para calcular o número.

## Alternativas consideradas

1. **Text-to-SQL direto sobre o data lake, sem camada semântica.** Descartada
   pelo motivo do princípio 2 e da R3 do Technical Design: o risco não é a IA
   escrever SQL errado, é escrever o SQL certo para uma pergunta mal definida.
2. **RAG sobre linhas de fato, com agregação do recuperado.** Descartada pelo
   argumento de completude acima.
3. **Híbrido RAG mais SQL, com o RAG escolhendo as linhas e o SQL agregando.**
   Descartada: o filtro continua sendo por similaridade, então o problema de
   completude permanece.
4. **RAG apenas sobre metadados, SQL governado para o cálculo.** Escolhida.

## Nota de escopo

Isto **não** é uma afirmação de que arquiteturas híbridas de RAG sobre tabelas
sejam inúteis. Em exploração aberta, em dados semiestruturados, ou quando o
objetivo é encontrar registros relevantes para leitura humana, elas funcionam
bem e são a escolha certa. O que não cabe é usá-las onde o requisito é um
número auditável com lineage, que é o caso de todo KPI deste projeto.

## Consequências

**Positivas**

- Cada ferramenta no problema para o qual foi feita.
- O acervo de definições e ADRs vira ativo consultável, o que valoriza a
  documentação em vez de deixá-la parada.
- Mantém o caminho do número 100% auditável, o que sustenta o lineage da seção
  22 da Especificação.

**Negativas**

- Duas mecânicas de recuperação para implementar e explicar.
- Perguntas que exijam varredura exploratória de dados brutos não serão
  atendidas, por desenho.

**Riscos e mitigação**

- *Risco:* o índice textual ficar desatualizado em relação aos contratos de
  KPI. *Mitigação:* o índice é reconstruído a partir dos YAML no mesmo comando
  que gera o `kpi_catalog`.

## Referências

- Technical Design v0.3, seção 17 (R3 e R10)
- Especificação do Universo v1.0, seções 22, 28 e 29
