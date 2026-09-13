# Architecture Decision Records, PeopleLens AI

Registro das decisões de arquitetura do projeto. Cada ADR é imutável depois de
aceito: se uma decisão mudar, criamos um novo ADR que a substitui e marcamos o
antigo como **Substituída**.

Formato: contexto, decisão, alternativas consideradas e consequências. As
alternativas descartadas são parte obrigatória do registro, porque sem elas
ninguém consegue avaliar a decisão seis meses depois.

## Índice

| ADR | Título | Decisão | Status |
|---|---|---|---|
| [0001](0001-geracao-em-dois-passos.md) | Geração em dois passos: ground truth e projeção | D1 | Aceita |
| [0002](0002-inventario-de-sistemas-fonte.md) | Inventário de sistemas-fonte e implementação em duas ondas | D2 | Aceita |
| [0003](0003-pipeline-e-metadados-transversais.md) | Separação entre pipeline em linha e metadados transversais | D3 | Aceita |
| [0004](0004-resolucao-de-identidade.md) | Resolução de identidade via `xref_employee_identity` | D4 | Aceita |
| [0005](0005-split-requisicao-candidatura.md) | Separação de `fact_requisition` e `fact_application` | D5 | Aceita |
| [0006](0006-moeda-e-cambio.md) | Tratamento de moeda e câmbio | D6 | Aceita |
| [0007](0007-pseudonimizacao-e-n-minimo.md) | Pseudonimização e supressão por n mínimo | D7 | Aceita |
| [0008](0008-catalogo-de-defeitos.md) | Catálogo de defeitos: estrutura aprovada, taxas provisórias | D8 | Parcial |
| [0009](0009-armazenamento-e-governanca.md) | Armazenamento: Parquet, DuckDB, SQLite e Git | D9 | Aceita |
| [0010](0010-severidade-em-data-quality.md) | Severidade nos resultados de data quality | D10 | Aceita |
| [0011](0011-dependencias-no-contrato-de-kpi.md) | Dependências declaradas no contrato de KPI | D11 | Aceita |
| [0012](0012-biblioteca-de-dataframe.md) | Biblioteca de dataframe | D12 | Aceita |
| [0013](0013-ferramenta-de-data-quality.md) | Ferramenta de Data Quality: GE, Soda, Pandera ou runner próprio | D13 | Aceita |
| [0014](0014-estrutura-de-diretorios.md) | Estrutura de diretórios | D14 | Aceita |
| [0015](0015-niveis-de-resposta-e-causalidade.md) | Níveis de resposta e proibição de causalidade sem evidência | seção 11.4 | Aceita |
| [0016](0016-papel-do-rag.md) | Papel do RAG no projeto | seção 17, R10 | Aceita |
| [0017](0017-coerencia-acima-de-target.md) | Coerência estrutural acima de aderência a targets agregados | F1, itens 1, 2 e 4 | Aceita |
| [0018](0018-controle-de-proveniencia.md) | Controle de proveniência antes de comparar com o gabarito | F3, item 5 | Aceita |
| [0019](0019-universo-de-referencia-em-checks.md) | Universo de referência de check de integridade é a camada de identidade | F3, item 6 | Aceita |
| [0020](0020-sugestao-nao-atravessa-fronteira-de-lingua.md) | Sugestão de mapeamento não atravessa fronteira de língua | F4, achado 3 | Aceita |
| [0021](0021-durabilidade-das-filas-de-governanca.md) | Decisão registrada sobrevive à reexecução | F4, achados 1 e 2 | Aceita |
| [0022](0022-classe-de-achado-e-natureza-da-perda-de-confianca.md) | Classe de achado, e a natureza da perda de confiança | F5, princípio da Sam | Aceita, com Emenda 1 |
| [0023](0023-calibragem-do-trust-score-por-recorte-fino.md) | Calibragem do trust score por recorte fino, bandas preservadas | F5, DQ-04 | Aceita |
| [0024](0024-separacao-entre-camada-de-verdade-e-camada-analitica.md) | Nomes de camada, e a separação entre verdade e analítico | F6, C-01 e C-02 | **Proposta** |
| [0025](0025-membros-reservados-nas-dimensoes.md) | Pendência de governança vira membro nomeado, nunca nulo | F6 | **Proposta, com Emenda 1** |
| [0026](0026-sistema-observador-no-grain-do-fato.md) | O sistema observador faz parte do grain do fato | F6 | **Proposta** |
| [0027](0027-proveniencia-nao-e-identidade.md) | Proveniência não é identidade | F6, diretriz 1 | **Proposta** |
| [0028](0028-saida-da-ia-e-consulta-semantica.md) | A saída da IA é consulta semântica, nunca SQL nem número | F7, D7-02 | **Proposta** |
| [0029](0029-certificacao-limita-o-nivel-de-resposta.md) | Certificação de KPI limita o nível de resposta, independente da qualidade do dado | F7, D7-03 | **Proposta** |
| [0030](0030-ciclo-de-vida-e-versionamento-de-kpi.md) | Ciclo de vida e versionamento de KPI, com a versão anterior consultável | F7, D7-04 | **Proposta** |
| [0031](0031-mcp-expoe-capacidades-nao-conexao.md) | O MCP expõe capacidades, não uma conexão | MCP v0.1, M-01 | **Proposta** |
| [0032](0032-recusa-e-resultado-nao-erro-de-protocolo.md) | Recusa é resultado da ferramenta, não erro de protocolo | MCP v0.1, M-02 | **Proposta** |
| [0033](0033-teto-do-ator-compoe-com-teto-de-evidencia.md) | O teto do ator compõe com o teto de evidência, e nunca o substitui | MCP v0.1, M-05 | **Proposta** |
| [0034](0034-plano-do-agente-e-artefato.md) | O plano do agente é um artefato, não um raciocínio | Agent Harness v0.1, Parte XXI | **Proposta** |
| [0035](0035-saida-do-llm-e-entrada-nao-confiavel.md) | A saída do LLM é entrada não confiável | LLM Interpreter v0.1, Parte XVI | **Proposta** |

## Estados possíveis

- **Aceita**: em vigor.
- **Parcial**: parte da decisão está fechada e parte segue em aberto, com prazo declarado.
- **Substituída**: houve um ADR posterior que a revoga.
- **Proposta**: escrita e ainda não aprovada.

## Fases cobertas

| Fase | Entrega | Documento de resultado |
|---|---|---|
| F0 | ADRs e configuração declarativa | este diretório, `config/` |
| F1 | gerador do ground truth | `docs/f1_metrics.md`, `docs/f1_validation_findings.md` |
| F2 | projeção nos sistemas-fonte (onda 1) | `docs/f2_projection.md`, `docs/f2_defect_coverage.md`, `docs/f2_validation_findings.md` |
| F3 | pipeline: ingestão, profiling, padronização, identidade, DE/PARA, qualidade, quarentena | `docs/f3_pipeline.md`, `docs/f3_validation_findings.md` |
| F4 | identidade, resolução governada de exceções e DE/PARA operacional | `docs/f4_governance.md`, `docs/f4_mapping_proposal.md`, `docs/f4_validation_findings.md` |
| F5 | catálogo completo de DQ, severidade, quarentena, reconciliações e Trust Score | `docs/f5_data_quality.md`, `docs/f5_validation_findings.md`, `docs/f5_completeness_gaps.md` |
| F6 | modelo analítico (L3): dimensões, fatos, grain, temporalidade, proveniência | `docs/F6_analytical_model.md` (SPEC v1.0 final), `docs/f6_analytical_model_report.md` |
| F7 | Semantic Layer, KPI Catalog e Trust Layer (L4): contrato semântico entre People Analytics, dados e IA | `docs/F7_semantic_layer.md` (SPEC v1.0), `docs/f7_semantic_layer_report.md` |
| MCP v0.1 | fronteira controlada entre o futuro Agent e a Semantic Layer: seis capacidades read-only | `docs/MCP_SPEC_v0.1.md`, `docs/mcp_v0.1_report.md` |
| Agent v0.1 | PeopleLens Analyst Agent: Harness, Loop e políticas sobre o MCP | `docs/AGENT_HARNESS_SPEC_v0.1.md` |
| LLM Interpreter v0.1 | o componente que substituirá o `RuleInterpreter` no passo UNDERSTAND | `docs/LLM_INTERPRETER_SPEC_v0.1.md` (SPEC aprovada em 2026-09-13, com D-01 a D-10 e P-01 a P-05), `docs/llm_interpreter_p03_report.md` (avaliação empírica de P-03: `gpt-5.6-luna`, 16 de 17 casos, **aprovado com lacuna conhecida**) |

Documentos transversais:

- `docs/technical_design_v0.4_delta.md`, o que as fases F4 e F5 mudaram na linha de base v0.3
- `docs/demographics.md`, natureza e coerência dos parâmetros demográficos
- `docs/f5_completeness_gaps.md`, lacunas de completude conhecidas e o que elas impedem
- `docs/requisitos_de_produto_futuros.md`, requisitos registrados e ainda não implementados (RF-01 interface bilíngue, RF-02 comparação entre períodos arbitrários)
