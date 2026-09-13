# ADR-0031: O MCP expõe capacidades, não uma conexão

- **Status:** **Proposta** (MCP v0.1, aguardando aprovação)
- **Data:** 2026-09-12
- **Origem:** MCP v0.1, decisão M-01
- **Fase:** vigora do MCP v0.1 em diante

## Contexto

O ADR-0028 decidiu o que a IA **emite**: uma consulta semântica, nunca SQL nem
um número. Isso resolve a forma da saída e deixa uma pergunta diferente em
aberto: **o que existe para ser chamado?**

São fronteiras distintas. Um agente pode estar perfeitamente proibido de
escrever SQL e ainda assim receber uma ferramenta `read_table(nome)` que o leva
ao RAW sem uma linha de SQL. A forma da saída não determina o tamanho da
superfície.

Há três desenhos possíveis, e a diferença entre eles é onde mora a defesa:

| Desenho | Onde mora a defesa | Como falha |
|---|---|---|
| tool genérica (`execute_sql`, `query_database`, `read_table`) | validação de string em tempo de execução | o agente alcança o que souber nomear; validar SQL arbitrário é mais difícil que gerá-lo |
| tools específicas **mais** permissões que negam o resto | na configuração de permissão | uma permissão mal configurada abre o que a superfície oferecia |
| **só tools específicas, e nenhuma outra existe** | na superfície | não falha por configuração: não há o que configurar errado |

O projeto já escolheu a terceira forma duas vezes, em camadas diferentes, e por
isso ela não é novidade de princípio — é a aplicação do mesmo princípio numa
camada nova. Na F6, o teste F-13 provou por AST que nenhum literal de código
aponta para a camada de verdade. Na F7, a camada de verdade simplesmente **não é
registrada** na conexão DuckDB da camada semântica: `truth.dim_employee` não é
um acesso negado, é um nome que não resolve.

A mesma lógica se aplica à escrita. Negar escrita por permissão pressupõe uma
chamada de escrita para negar. Se a chamada não existe, não há nada a negar, e
não há como configurar errado.

## Decisão

### 1. Seis capacidades, e nenhuma outra

O servidor MCP v0.1 registra exatamente seis ferramentas: `get_kpi`,
`compare_kpi`, `breakdown_kpi`, `get_kpi_definition`, `get_trust`,
`get_lineage`. Uma sétima ferramenta é uma mudança de SPEC, não de configuração.

### 2. Nenhuma ferramenta genérica, em nenhuma versão

Ficam proibidas, por nome e por forma: `execute_sql`, `query_database`,
`read_table`, `arbitrary_query`, `run_python`, `read_file`, `list_tables`,
`describe_schema`, e qualquer ferramenta cujo parâmetro seja o **nome do que
será lido**. O teste é esse: se o chamador escolhe o objeto, a ferramenta é
genérica, ainda que o nome pareça específico.

### 3. Nenhuma ferramenta de escrita, e nenhum escopo de escrita

A v0.1 é read-only por ausência, não por permissão. Não existe escopo
`kpi:write:*`, e ele não deve ser criado "para o futuro": escopo que existe
acaba sendo concedido, e o argumento de que ninguém o concederá é a mesma
confiança em disciplina que este ADR recusa.

### 4. Permissão é a segunda cerca, não a primeira

Os quatro escopos (`value`, `definition`, `trust`, `lineage`) estreitam uma
superfície que já é fechada. São defesa em profundidade. Se alguém descrever a
permissão como o que impede o agente de escrever, a descrição está errada — o
que impede é a ausência da capacidade.

### 5. O input não nomeia objeto físico

Nenhum parâmetro de nenhuma ferramenta aceita nome de tabela, coluna, junção,
schema, caminho de arquivo ou fragmento de SQL, e campo desconhecido **reprova**
em vez de ser ignorado. É a mesma regra do `SemanticQuery.parse` do ADR-0028,
agora como contrato de transporte: ignorar o campo extra seria a porta por onde
`{"table": ...}` entraria sem ninguém notar.

## Alternativas consideradas

1. **Uma ferramenta `query_semantic_layer` genérica, recebendo o objeto de
   consulta inteiro.** Tecnicamente honesta — o objeto já é governado pelo
   ADR-0028 — e ruim como fronteira de agente: o agente perde a distinção entre
   pedir um valor, quebrar por dimensão e pedir linhagem, e o log perde a
   intenção. Tools específicas são a documentação executável do que se pode
   pedir.
2. **`execute_sql` com allowlist de tabelas e colunas.** Descartada pelo mesmo
   motivo do ADR-0028: a allowlist aceita `FROM fact_headcount_snapshot` sem o
   `is_system_of_record`, que é justamente o erro que importa.
3. **`read_table` restrito ao schema `semantic`.** Melhor, e ainda entrega ao
   chamador a escolha do objeto e os nomes físicos — o oposto do que a Semantic
   Layer existe para evitar. E uma view nova, adicionada sem revisão, vira
   capacidade nova sem decisão.
4. **Superfície ampla com permissões estreitas.** É o desenho mais comum e o que
   falha em produção: a superfície é permanente, a configuração é editável, e a
   segunda acaba se afastando da primeira.
5. **Criar escopos de escrita desativados.** Descartada: um escopo existente é
   um escopo concedível.

## Consequências

**Positivas**

- Escrita, leitura de RAW e SQL arbitrário deixam de depender de configuração:
  não há chamada a negar.
- A superfície é auditável por enumeração. "O que o agente pode fazer?" tem
  resposta de seis linhas, verificável contra o servidor.
- Cada ferramenta carrega intenção, então o log diz o que foi pedido e não
  apenas que algo foi consultado.
- Uma capacidade nova exige passar pela SPEC, que é onde a discussão deve
  acontecer.

**Negativas**

- Toda pergunta que as seis ferramentas não cobrem é uma recusa até alguém
  estender a SPEC. A superfície é deliberadamente menos capaz que um banco.
- Seis schemas para manter, e cada um é contrato público com o agente: mudar um
  campo quebra o consumidor.
- Casos legítimos e raros — uma exploração ad hoc de analista — não passam por
  aqui, e vão precisar de outro caminho, com outra governança.

**Riscos e mitigação**

- *Risco:* a pressão prática ("só uma ferramentazinha de consulta livre, para
  destravar") adicionar a sétima tool. *Mitigação:* ACm-01, que verifica que o
  servidor registra exatamente seis, e este ADR como o lugar onde a sétima
  precisa ser argumentada.
- *Risco:* uma das seis crescer parâmetros até virar genérica. *Mitigação:* o
  teste da decisão 2 — se o chamador escolhe o objeto, é genérica — e a regra de
  que campo desconhecido reprova.

## Referências

- `docs/MCP_SPEC_v0.1.md`, Partes II, V e X
- ADR-0016 (papel do RAG), ADR-0024 (separação entre camada de verdade e
  analítica), ADR-0028 (saída da IA é consulta semântica)
- Teste F-13 da F6 e AC-05 da F7, os dois precedentes do mesmo princípio
