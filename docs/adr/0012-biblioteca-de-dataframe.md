# ADR-0012: Biblioteca de dataframe

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D12 (Technical Design v0.3)
- **Fase:** F0, vigora a partir da F1

## Contexto

O projeto precisa escolher a biblioteca de dataframe do gerador e dos
notebooks. Vale registrar de saída que **esta é a decisão de menor impacto
estrutural do projeto**: a carga pesada de transformação é SQL executado no
DuckDB, e a 4,3 milhões de linhas não existe emergência de performance.

## Decisão

**Polars no gerador**, **pandas nos notebooks de análise**. Não padronizar por
padronizar.

Motivo do Polars no gerador: a simulação de eventos é vetorizada e cheia de
condicionais encadeadas, e a API de expressão do Polars deixa esse código
substancialmente mais legível que o equivalente em pandas.

Motivo do pandas nos notebooks: é o que qualquer pessoa avaliando o repositório
lê sem fricção, e notebook é material de leitura.

## Alternativas consideradas

1. **pandas em tudo.** Mais universal, mais material de apoio. Funciona bem
   neste volume.
2. **Polars em tudo.** Mais rápido e mais consistente, menos universal em
   notebook.
3. **SQL no DuckDB para quase tudo, dataframe apenas nas bordas.** Vale
   registrar porque é parcialmente o que vai acontecer de qualquer forma nas
   camadas de transformação.
4. **Polars no gerador, pandas nos notebooks.** Escolhida.

## Consequências

**Positivas**

- Código de simulação mais legível onde a complexidade está.
- Notebooks acessíveis para quem for avaliar o projeto.

**Negativas**

- Duas bibliotecas no `requirements.txt` e duas convenções no repositório.

**Riscos e mitigação**

- *Risco:* conversões desnecessárias entre as duas. *Mitigação:* a fronteira é
  o arquivo Parquet, não o objeto em memória: o gerador escreve Parquet, o
  notebook lê Parquet.

## Referências

- Technical Design v0.3, seções 14 e 18 (D12)
