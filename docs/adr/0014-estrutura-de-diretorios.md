# ADR-0014: Estrutura de diretórios

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D14 (Technical Design v0.3)
- **Fase:** F0

## Contexto

A estrutura inicial do repositório não tem casa natural para três coisas que o
desenho exige: os arquivos de configuração declarativa (ADR-0001 e R8), o
gerador do universo, e a camada de governança em SQLite (ADR-0009). Além
disso, `data/processed/` precisa refletir as camadas do ADR-0003.

## Decisão

```
peoplelens/
├── config/                      # NOVO: parâmetros declarativos do universo
│   ├── generation.yaml
│   ├── incidents.yaml
│   ├── defects.yaml
│   └── sources.yaml
├── data/
│   ├── raw/<source_system>/     # formato nativo, imutável
│   ├── reference/               # ref_* aprovados, versionados no Git
│   ├── processed/
│   │   ├── standardized/        # NOVO: subcamadas do ADR-0003
│   │   ├── conformed/
│   │   ├── analytical/
│   │   └── semantic/
│   ├── synthetic/
│   │   ├── truth/               # NOVO: ground truth, fora do pipeline
│   │   └── manifest.json
│   ├── samples/                 # NOVO: 1.000 linhas por dataset, versionado
│   └── governance/              # NOVO: peoplelens_gov.db (SQLite)
├── docs/
│   ├── technical_design.md
│   ├── data_dictionary.md
│   ├── kpi_definitions.md
│   ├── incidents.md
│   └── adr/                     # NOVO
├── src/
│   ├── generator/               # NOVO: world, events, projection, defects
│   ├── ingestion/
│   ├── cleaning/
│   ├── mapping/
│   ├── quality/
│   ├── analytics/               # models, kpis, semantic
│   └── mcp/
├── notebooks/
├── app/
└── tests/
    ├── unit/
    ├── integration/
    └── truth/                   # NOVO: pipeline medido contra a verdade
```

## Alternativas consideradas

1. **Manter a estrutura atual e acomodar tudo nela.** O gerador acabaria em
   `src/ingestion/`, que é o oposto do que ele faz.
2. **Gerador em repositório separado.** Separa responsabilidades e quebra a
   narrativa do portfólio, porque o gerador é parte do argumento.
3. **Estrutura expandida.** Escolhida.

## Consequências

**Positivas**

- Cada artefato tem lugar óbvio, o que também ajuda quem for ler o repositório.
- `config/` na raiz sinaliza de cara que o universo é declarativo.

**Negativas**

- Mais diretórios para navegar.

**Riscos e mitigação**

- Nenhum relevante. Esta é a decisão mais trivialmente reversível das quatorze:
  mover pasta é barato enquanto não há código.

## Referências

- Technical Design v0.3, seções 15 e 18 (D14)
