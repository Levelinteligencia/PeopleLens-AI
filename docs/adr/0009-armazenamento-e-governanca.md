# ADR-0009: Armazenamento, Parquet, DuckDB, SQLite e Git

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D9 (Technical Design v0.3)
- **Fase:** F0, vigora a partir da F4

## Contexto

O dimensionamento da seção 4 do Technical Design fechou em ~4,3 milhões de
linhas e ~170 MB em Parquet. Esse volume cabe na memória de qualquer máquina.

Porém, nem tudo no projeto é dado analítico. A fila de exceções de DE/PARA
recebe **escrita** com aprovação humana, possivelmente concorrente, e os
mapeamentos aprovados precisam de trilha de auditoria com autor e data, porque
os campos `approved_by` e `approved_at` da seção 16 da Especificação não podem
ser decorativos.

## Decisão

Modelo híbrido, dividido pela natureza de cada objeto:

| Objeto | Onde | Por quê |
|---|---|---|
| dados de todas as camadas | Parquet + zstd | volume e leitura analítica |
| camada de consulta | DuckDB, views sobre Parquet e tabelas materializadas em `semantic` | agregação rápida sem infraestrutura |
| `mapping_exceptions` (fila operacional) | SQLite (`data/governance/peoplelens_gov.db`) | escrita transacional, volume alto, efêmero por natureza |
| `ref_*_mapping` **aprovado** | CSV versionado em `data/reference/` | é conhecimento curado; o histórico do Git vira a trilha de auditoria |

Com um **comando de promoção**: aprovar uma exceção escreve no arquivo de
referência, e a mudança entra por commit. Assim `approved_by` é o autor do
commit e `approved_at` é a data do commit, com rastro externo verificável.

A fila é operacional. O mapeamento aprovado é patrimônio.

Supabase fica registrado como caminho de evolução, não como MVP.

## Alternativas consideradas

1. **Tudo em DuckDB.** Descartada: escrita concorrente trava o arquivo, e
   aprovação de exceção é escrita.
2. **Postgres ou Supabase desde o MVP.** Funciona bem e está na stack da
   LevelInteligencIA. Descartada para o MVP por exigir infraestrutura em pé
   para que alguém consiga clonar e rodar o repositório, o que atrapalha
   exatamente o público avaliador do portfólio.
3. **Tudo em SQLite para governança, inclusive os mapeamentos aprovados.**
   Funciona, e perde a trilha de aprovação que o Git dá de graça.
4. **Modelo híbrido.** Escolhida.

## Consequências

**Positivas**

- Zero infraestrutura para rodar o projeto inteiro.
- A aprovação de mapeamento passa a ter revisão por pull request, que é
  governança real e não campo preenchido por sistema.
- Separação limpa entre o que muda o tempo todo e o que é curado.

**Negativas**

- Duas tecnologias de persistência para explicar.
- O comando de promoção é código adicional e precisa ser idempotente.

**Riscos e mitigação**

- *Risco:* divergência entre o que está no SQLite e o que está no CSV.
  *Mitigação:* o CSV é a fonte de verdade dos mapeamentos aprovados; o SQLite
  guarda apenas exceções, e um check de DQ compara os dois.
- *Risco:* migração futura para Postgres. *Mitigação:* o acesso à governança
  fica atrás de uma interface única, para que a troca seja local.

## Referências

- Technical Design v0.3, seções 9.3, 12 e 18 (D9)
- Especificação do Universo v1.0, seções 16 e 17
