# F4: proposta de resolucao das excecoes de mapeamento

> **Nada aqui foi aplicado.** Este documento e insumo de decisao. A aprovacao
> acontece por chamada explicita de `Governance.approve`, com valor padrao,
> responsavel e justificativa, e escreve no arquivo de referencia versionado.


57 excecoes abertas, classificadas em 3 grupos.

| Classe | Quantas | O que significa |
|---|---|---|
| VARIANTE_DE_ESCRITA | 0 | mesma palavra, escrita de outro jeito (acento, caixa, espaco, abreviacao) |
| APELIDO_CONHECIDO | 43 | sigla ou nome alternativo do mesmo conceito, com candidato unico e claro |
| CANDIDATO_PROVAVEL | 0 | candidato plausivel mas nao obvio; exige conferencia antes de aprovar |
| DECISAO_DE_NEGOCIO | 2 | o sistema de origem nao distingue o que a NOVAORA distingue; nao existe resposta tecnica |
| TRADUCAO_PENDENTE | 12 | origem e dominio corporativo estao em linguas diferentes; a similaridade nao e evidencia aqui |
| CANDIDATO_FRACO | 0 | nenhum candidato plausivel; sugestao do pipeline provavelmente errada |

## DECISAO_DE_NEGOCIO

_o sistema de origem nao distingue o que a NOVAORA distingue; nao existe resposta tecnica_

| Valor de origem | Sistema | Lingua | Campo | Ocorrencias | Melhor candidato | Casou com | Score | Criterio | Recomendacao |
|---|---|---|---|---|---|---|---|---|---|
| `N4` | VIVAMARKET_LEGACY | pt-BR | job_level | 30 | nenhum | - | 0.50 | nao aplicavel | decidir com People Analytics; manter em excecao ate la |
| `N5` | VIVAMARKET_LEGACY | pt-BR | job_level | 12 | nenhum | - | 0.50 | nao aplicavel | decidir com People Analytics; manter em excecao ate la |

Justificativa caso a caso:

- **`N4`** (30 ocorrencias): `N4` pertence a escala propria de VIVAMARKET_LEGACY. A escala de origem tem menos niveis que a da NOVAORA, entao um mesmo valor cobre mais de um nivel corporativo. Nao ha traducao correta, ha decisao de People Analytics.
- **`N5`** (12 ocorrencias): `N5` pertence a escala propria de VIVAMARKET_LEGACY. A escala de origem tem menos niveis que a da NOVAORA, entao um mesmo valor cobre mais de um nivel corporativo. Nao ha traducao correta, ha decisao de People Analytics.

## TRADUCAO_PENDENTE

_origem e dominio corporativo estao em linguas diferentes; a similaridade nao e evidencia aqui_

| Valor de origem | Sistema | Lingua | Campo | Ocorrencias | Melhor candidato | Casou com | Score | Criterio | Recomendacao |
|---|---|---|---|---|---|---|---|---|---|
| `OPER LOJA` | HRIS_LEGACY | pt-BR | department | 68 | nenhum | - | 0.57 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |
| `Operações Loja` | HRIS_LEGACY | pt-BR | department | 67 | nenhum | - | 0.47 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |
| `Transportes` | HRIS_LEGACY | pt-BR | department | 37 | nenhum | - | 0.53 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |
| `Centro de Distribuição` | HRIS_LEGACY | pt-BR | department | 35 | nenhum | - | 0.48 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |
| `Controladoria` | HRIS_LEGACY | pt-BR | department | 19 | nenhum | - | 0.61 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |
| `Desenvolvimento` | HRIS_LEGACY | pt-BR | department | 17 | nenhum | - | 0.61 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |
| `DHO` | HRIS_LEGACY | pt-BR | department | 17 | nenhum | - | 0.40 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |
| `Operações Loja` | VIVAMARKET_LEGACY | pt-BR | department | 10 | nenhum | - | 0.47 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |
| `Transportes` | VIVAMARKET_LEGACY | pt-BR | department | 6 | nenhum | - | 0.53 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |
| `OPER LOJA` | VIVAMARKET_LEGACY | pt-BR | department | 6 | nenhum | - | 0.57 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |
| `OUTRO` | VIVAMARKET_LEGACY | pt-BR | gender | 2 | nenhum | - | 0.35 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |
| `Centro de Distribuição` | VIVAMARKET_LEGACY | pt-BR | department | 2 | nenhum | - | 0.48 | nao aplicavel | traduzir com quem conhece os dois vocabularios; nao decidir por score |

Justificativa caso a caso:

- **`OPER LOJA`** (68 ocorrencias): HRIS_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `OPER LOJA`, entao o melhor score (0.57, com `Store Operations`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**
- **`Operações Loja`** (67 ocorrencias): HRIS_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `Operações Loja`, entao o melhor score (0.47, com `Store Operations`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**
- **`Transportes`** (37 ocorrencias): HRIS_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `Transportes`, entao o melhor score (0.53, com `Strategy`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**
- **`Centro de Distribuição`** (35 ocorrencias): HRIS_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `Centro de Distribuição`, entao o melhor score (0.48, com `Distribution Centers`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**
- **`Controladoria`** (19 ocorrencias): HRIS_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `Controladoria`, entao o melhor score (0.61, com `Engineering`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**
- **`Desenvolvimento`** (17 ocorrencias): HRIS_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `Desenvolvimento`, entao o melhor score (0.62, com `Customer Service`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**
- **`DHO`** (17 ocorrencias): HRIS_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `DHO`, entao o melhor score (0.40, com `Distribution Centers`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**
- **`Operações Loja`** (10 ocorrencias): VIVAMARKET_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `Operações Loja`, entao o melhor score (0.47, com `Store Operations`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**
- **`Transportes`** (6 ocorrencias): VIVAMARKET_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `Transportes`, entao o melhor score (0.53, com `Strategy`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**
- **`OPER LOJA`** (6 ocorrencias): VIVAMARKET_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `OPER LOJA`, entao o melhor score (0.57, com `Store Operations`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**
- **`OUTRO`** (2 ocorrencias): VIVAMARKET_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `OUTRO`, entao o melhor score (0.35, com `Not informed`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**
- **`Centro de Distribuição`** (2 ocorrencias): VIVAMARKET_LEGACY declara `pt-BR` e o dominio corporativo e `en`. Nenhum apelido aprovado cobre `Centro de Distribuição`, entao o melhor score (0.48, com `Distribution Centers`) mede semelhanca de letras entre linguas diferentes e nao significa nada. **Nenhum candidato e proposto.**

## APELIDO_CONHECIDO

_sigla ou nome alternativo do mesmo conceito, com candidato unico e claro_

| Valor de origem | Sistema | Lingua | Campo | Ocorrencias | Melhor candidato | Casou com | Score | Criterio | Recomendacao |
|---|---|---|---|---|---|---|---|---|---|
| `Visu.Merc.` | HRIS_LEGACY | pt-BR | department | 66 | `Visual Merchandising` | `Visual Merchandising` | 0.93 | prefixo | aprovar como `Visual Merchandising` |
| `Regi.Oper.` | HRIS_LEGACY | pt-BR | department | 62 | `Regional Operations` | `Regional Operations` | 0.93 | prefixo | aprovar como `Regional Operations` |
| `Operação de Lojas` | HRIS_LEGACY | pt-BR | department | 62 | `Store Operations` | `Lojas` | 0.80 | tokens | aprovar como `Store Operations` |
| `Proc.` | HRIS_LEGACY | pt-BR | department | 61 | `Procurement` | `Procurement` | 0.90 | prefixo | aprovar como `Procurement` |
| `Central de Atendimento` | HRIS_LEGACY | pt-BR | department | 48 | `Customer Service` | `Atendimento` | 0.80 | tokens | aprovar como `Customer Service` |
| `LOG` | HRIS_LEGACY | pt-BR | department | 41 | `Logistics` | `Logistica` | 0.82 | prefixo | aprovar como `Logistics` |
| `CDs` | HRIS_LEGACY | pt-BR | department | 39 | `Distribution Centers` | `CD` | 0.80 | sequencia | aprovar como `Distribution Centers` |
| `CS` | HRIS_LEGACY | pt-BR | department | 39 | `Customer Service` | `Customer Service` | 0.97 | sigla | aprovar como `Customer Service` |
| `Plan.` | HRIS_LEGACY | pt-BR | department | 35 | `Planning` | `Planning` | 0.90 | prefixo | aprovar como `Planning` |
| `JUR` | HRIS_LEGACY | pt-BR | department | 33 | `Legal` | `Juridico` | 0.82 | prefixo | aprovar como `Legal` |
| `Cust.Expe.` | HRIS_LEGACY | pt-BR | department | 33 | `Customer Experience` | `Customer Experience` | 0.93 | prefixo | aprovar como `Customer Experience` |
| `Depto Juridico` | HRIS_LEGACY | pt-BR | department | 29 | `Legal` | `Juridico` | 0.80 | tokens | aprovar como `Legal` |
| `Cust.Oper.` | HRIS_LEGACY | pt-BR | department | 22 | `Customer Operations` | `Customer Operations` | 0.93 | prefixo | aprovar como `Customer Operations` |
| `Marketing e Comunicação` | HRIS_LEGACY | pt-BR | department | 22 | `Marketing` | `Marketing` | 0.80 | tokens | aprovar como `Marketing` |
| `Mktg` | HRIS_LEGACY | pt-BR | department | 21 | `Marketing` | `MKT` | 0.86 | sequencia | aprovar como `Marketing` |
| `Finanças` | HRIS_LEGACY | pt-BR | department | 20 | `Finance` | `Finance` | 0.80 | sequencia | aprovar como `Finance` |
| `FIN` | HRIS_LEGACY | pt-BR | department | 20 | `Finance` | `Finance` | 0.82 | prefixo | aprovar como `Finance` |
| `Prod.` | HRIS_LEGACY | pt-BR | department | 15 | `Product` | `Product` | 0.90 | prefixo | aprovar como `Product` |
| `REC HUMANOS` | HRIS_LEGACY | pt-BR | department | 15 | `People` | `Recursos Humanos` | 0.93 | prefixo | aprovar como `People` |
| `Eng` | HRIS_LEGACY | pt-BR | department | 13 | `Engineering` | `Engineering` | 0.82 | prefixo | aprovar como `Engineering` |
| `Data&Anal.` | HRIS_LEGACY | pt-BR | department | 13 | `Data & Analytics` | `Data & Analytics` | 0.93 | prefixo | aprovar como `Data & Analytics` |
| `Visu.Merc.` | VIVAMARKET_LEGACY | pt-BR | department | 12 | `Visual Merchandising` | `Visual Merchandising` | 0.93 | prefixo | aprovar como `Visual Merchandising` |
| `Stra.` | HRIS_LEGACY | pt-BR | department | 11 | `Strategy` | `Strategy` | 0.90 | prefixo | aprovar como `Strategy` |
| `R.H.` | HRIS_LEGACY | pt-BR | department | 10 | `People` | `RH` | 0.80 | sequencia | aprovar como `People` |
| `Regi.Oper.` | VIVAMARKET_LEGACY | pt-BR | department | 10 | `Regional Operations` | `Regional Operations` | 0.93 | prefixo | aprovar como `Regional Operations` |
| `Digi.Mark.` | HRIS_LEGACY | pt-BR | department | 9 | `Digital Marketing` | `Digital Marketing` | 0.93 | prefixo | aprovar como `Digital Marketing` |
| `People & Culture` | HRIS_LEGACY | pt-BR | department | 9 | `People` | `People` | 0.80 | tokens | aprovar como `People` |
| `Operação de Lojas` | VIVAMARKET_LEGACY | pt-BR | department | 8 | `Store Operations` | `Lojas` | 0.80 | tokens | aprovar como `Store Operations` |
| `LOG` | VIVAMARKET_LEGACY | pt-BR | department | 6 | `Logistics` | `Logistica` | 0.82 | prefixo | aprovar como `Logistics` |
| `CDs` | VIVAMARKET_LEGACY | pt-BR | department | 5 | `Distribution Centers` | `CD` | 0.80 | sequencia | aprovar como `Distribution Centers` |
| `Proc.` | VIVAMARKET_LEGACY | pt-BR | department | 5 | `Procurement` | `Procurement` | 0.90 | prefixo | aprovar como `Procurement` |
| `Central de Atendimento` | VIVAMARKET_LEGACY | pt-BR | department | 5 | `Customer Service` | `Atendimento` | 0.80 | tokens | aprovar como `Customer Service` |
| `E-co.` | HRIS_LEGACY | pt-BR | department | 4 | `E-commerce` | `E-commerce` | 0.90 | prefixo | aprovar como `E-commerce` |
| `Plan.` | VIVAMARKET_LEGACY | pt-BR | department | 3 | `Planning` | `Planning` | 0.90 | prefixo | aprovar como `Planning` |
| `Cust.Expe.` | VIVAMARKET_LEGACY | pt-BR | department | 3 | `Customer Experience` | `Customer Experience` | 0.93 | prefixo | aprovar como `Customer Experience` |
| `Cust.Oper.` | VIVAMARKET_LEGACY | pt-BR | department | 2 | `Customer Operations` | `Customer Operations` | 0.93 | prefixo | aprovar como `Customer Operations` |
| `Depto Juridico` | VIVAMARKET_LEGACY | pt-BR | department | 2 | `Legal` | `Juridico` | 0.80 | tokens | aprovar como `Legal` |
| `CS` | VIVAMARKET_LEGACY | pt-BR | department | 2 | `Customer Service` | `Customer Service` | 0.97 | sigla | aprovar como `Customer Service` |
| `Prod.` | VIVAMARKET_LEGACY | pt-BR | department | 2 | `Product` | `Product` | 0.90 | prefixo | aprovar como `Product` |
| `Eng` | VIVAMARKET_LEGACY | pt-BR | department | 2 | `Engineering` | `Engineering` | 0.82 | prefixo | aprovar como `Engineering` |
| `JUR` | VIVAMARKET_LEGACY | pt-BR | department | 1 | `Legal` | `Juridico` | 0.82 | prefixo | aprovar como `Legal` |
| `Mktg` | VIVAMARKET_LEGACY | pt-BR | department | 1 | `Marketing` | `MKT` | 0.86 | sequencia | aprovar como `Marketing` |
| `REC HUMANOS` | VIVAMARKET_LEGACY | pt-BR | department | 1 | `People` | `Recursos Humanos` | 0.93 | prefixo | aprovar como `People` |

## Como aprovar

```python
from mapping.resolution import Governance
g = Governance(cfg)
g.approve("HRIS_LEGACY|department|Mktg",
          standard_value="Marketing",
          by="sam",
          rationale="abreviacao usada no sistema legado para a mesma area")
```

Nao existe funcao de aprovacao em lote por limiar de confianca, e isso e deliberado (principio 5 da Especificacao, Technical Design R4). O custo assimetrico nao mudou: um valor nao mapeado e visivel e sai do numerador; um valor mapeado errado e invisivel e contamina o numerador.

