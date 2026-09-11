# PeopleLens

> Projeto autoral da **LevelInteligencIA**. People Analytics + Data Engineering + Data Quality + Data Governance + IA/MCP.

---

## O problema

Dados de RH raramente chegam prontos. Eles vêm de vários sistemas, em formatos diferentes, com nomenclaturas divergentes para o mesmo conceito, campos ausentes, duplicidades, IDs inconsistentes, datas inválidas e quebras de integridade referencial. Somam-se a isso as mudanças organizacionais ao longo dos anos, que fazem a mesma área mudar de nome, de estrutura e de dono.

O resultado prático é conhecido: cada pessoa calcula turnover de um jeito, ninguém sabe de onde veio o número e a confiança na área de People Analytics se perde.

## O que é o PeopleLens

O PeopleLens transforma dados de RH heterogêneos, inconsistentes e de baixa qualidade em uma **camada analítica governada**, permitindo consultas em linguagem natural através de uma interface de IA que sabe o que pode responder e, principalmente, o que **não** pode.

O projeto é construído sobre uma empresa fictícia com aproximadamente 10 anos de histórico de RH. A base é sintética e propositalmente complexa, reproduzindo os problemas reais listados acima.

## Arquitetura conceitual

```
FONTES
  ↓
RAW DATA
  ↓
DATA PROFILING
  ↓
STANDARDIZATION
  ↓
DE/PARA / MAPPING
  ↓
DATA QUALITY
  ↓
QUARANTINE / EXCEPTIONS
  ↓
ANALYTICAL DATA MODEL
  ↓
SEMANTIC / KPI LAYER
  ↓
CERTIFIED KPIs
  ↓
MCP
  ↓
PEOPLELENS AI
  ↓
NATURAL LANGUAGE INTERFACE
```

### A camada de DE/PARA

Uma parte central do projeto é a camada de mapeamento (mapping / reference layer), responsável por traduzir valores diferentes em uma representação padronizada.

Exemplo:

| Valor na origem | Valor padronizado |
| --- | --- |
| `RH` | `People` |
| `HR` | `People` |
| `Human Resources` | `People` |
| `People & Culture` | `People` |

Valores desconhecidos **não são corrigidos automaticamente**. Eles são encaminhados para uma camada de exceções, onde ficam visíveis e aguardam revisão humana.

## Princípios do projeto

1. O RAW nunca é alterado.
2. A IA nunca define a regra de negócio de um KPI.
3. KPIs possuem definições governadas.
4. Dados de baixa qualidade não geram respostas confiáveis.
5. Valores desconhecidos são identificados e encaminhados para exceção.
6. Todo KPI tem definição, fórmula, granularidade, fonte e regras de inclusão e exclusão.
7. É possível rastrear a origem de qualquer resposta (data lineage).
8. A IA sabe quando **não** responder.
9. O projeto diferencia fato, cálculo e interpretação.
10. Nada de tecnologia por tecnologia: cada componente resolve um problema real de People Analytics.

## Estrutura do repositório

```
peoplelens/
├── README.md
├── requirements.txt
├── docs/               # documentação, decisões, dicionário de dados, definições de KPI
├── data/
│   ├── raw/            # dados brutos, imutáveis
│   ├── reference/      # tabelas de DE/PARA e domínios padronizados
│   ├── processed/      # saídas das etapas de tratamento
│   └── synthetic/      # geradores e artefatos da base sintética
├── notebooks/          # exploração, profiling, validações
├── src/
│   ├── ingestion/      # leitura das fontes e carga no RAW
│   ├── cleaning/       # padronização e normalização
│   ├── mapping/        # camada de DE/PARA e exceções
│   ├── quality/        # regras de data quality e quarentena
│   ├── analytics/      # modelo analítico e camada semântica de KPIs
│   └── mcp/            # servidor MCP que expõe os KPIs certificados
├── app/                # interface em linguagem natural
└── tests/
```

## Status

**Fase atual: estrutura inicial.**

O repositório contém somente o esqueleto do projeto. Ainda não foram definidos ou implementados:

- [ ] especificação da empresa fictícia
- [ ] geração do dataset sintético
- [ ] dicionário de dados e campos
- [ ] regras de data quality
- [ ] camada de DE/PARA
- [ ] modelo analítico
- [ ] catálogo de KPIs certificados
- [ ] servidor MCP
- [ ] interface em linguagem natural

## Autoria

**LevelInteligencIA**, consultoria de dados e IA para pequenas e médias empresas no Brasil.
