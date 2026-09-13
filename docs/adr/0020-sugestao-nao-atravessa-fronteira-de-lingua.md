# ADR-0020: Sugestao de mapeamento nao atravessa fronteira de lingua

- **Status:** Aceita
- **Data:** 2026-09-11
- **Origem:** achado 3 da F4
- **Fase:** vigora da F4 em diante

## Contexto

O motor de sugestao pontua semelhanca de escrita: sequencia de caracteres,
sigla, prefixo e sobreposicao de tokens. Foi construido para um problema real e
o resolve bem: `CS` para Customer Service, `Regi.Oper.` para Regional
Operations, `People & Culture` para People.

O cadastro legado da NOVAORA esta em portugues e o dominio corporativo em
ingles. Para um valor que ainda nao tem apelido aprovado, a pontuacao passa a
medir coincidencia de letras entre dois vocabularios, e o resultado nao e
apenas impreciso: e **sistematicamente invertido**.

| Valor de origem | Melhor candidato | Score | Correto? |
|---|---|---|---|
| `Controladoria` | Engineering | 0,61 | nao |
| `Desenvolvimento` | Customer Service | 0,61 | nao |
| `Transportes` | Strategy | 0,53 | nao |
| `Centro de Distribuicao` | Distribution Centers | 0,48 | **sim** |
| `Operacoes Loja` | Store Operations | 0,47 | **sim** |

As duas sugestoes corretas receberam os menores scores da tabela. Um revisor
apressado aprovaria as erradas e recusaria as certas, e o documento de proposta
teria produzido o resultado oposto ao que existe para produzir.

Nenhum limiar separa as duas metades, porque a informacao que separa nao esta na
escrita. O problema nao e o numero, e a pergunta: similaridade de caractere nao
responde "estas duas palavras significam o mesmo em linguas diferentes".

## Decisao

1. **A lingua e declarada, nao inferida.** `sources.yaml` declara
   `field_language` para os doze sistemas e `canonical_field_language` para o
   dominio corporativo, que e o alvo do DE/PARA.
2. Quando a lingua do sistema difere da do dominio **e** nenhum apelido aprovado
   cobre o valor, a proposta classifica a excecao como `TRADUCAO_PENDENTE`,
   **nao oferece candidato** e registra que o score nao e evidencia ali.
3. Um valor coberto por apelido ja aprovado nao entra nesta regra: o apelido e
   evidencia registrada e auditavel, e a pontuacao contra ele e legitima.
4. **A sugestao aceita passa a mostrar o apelido que casou.** `JUR -> Legal,
   0,82 por prefixo` e inconferivel, porque `JUR` nao e prefixo de `Legal`: e
   prefixo de `JURIDICO`. Sem o intermediario visivel, revisao vira fe.
5. Esta regra muda **apresentacao**, nunca aplicacao. Nenhum mapeamento e
   promovido, alterado ou bloqueado por ela, e o principio 5 continua valendo
   integralmente.

## Alternativas consideradas

1. **Calibrar o limiar.** Descartada: subir tira as corretas junto, baixar traz
   mais absurdos. E a intervencao que o ADR-0017 proibe em outro contexto e pelo
   mesmo motivo: mexer no numero para o resultado parecer bom.
2. **Dicionario de traducao pt-BR para en embutido no codigo.** Descartada por
   duas razoes. Traduzir `Controladoria` para a area correta da NOVAORA e
   decisao de negocio, nao de lingua: pode ser Finance, pode ser um
   sub-departamento proprio. E um dicionario em codigo e exatamente a regra de
   negocio escondida que a F3 proibiu.
3. **Inferir a lingua do proprio dado.** Descartada: inferencia automatica e a
   porta de entrada da correcao silenciosa, como ja registrado no cabecalho de
   `standardization.yaml`. A lingua de um sistema e um fato conhecido e cabe em
   uma linha de configuracao.
4. **Nao classificar e deixar a fila homogenea.** E o estado anterior. Produz
   uma fila que ninguem trabalha, e fila que ninguem trabalha acaba aprovada em
   bloco.

## Consequencias

**Positivas**

- Remove sugestoes confiantes e erradas do documento que sustenta decisao.
- Separa quem decide: 43 excecoes sao trabalho de analista, 12 exigem alguem que
  conheca os dois vocabularios, 2 exigem People Analytics.
- Toda sugestao aceita passa a ser conferivel pelo apelido intermediario.

**Negativas**

- A proposta admite que, para 12 casos, o pipeline nao tem nada a sugerir. E
  menos impressionante e mais verdadeiro.
- Exige manter `field_language` atualizado quando a onda 2 entrar. Um sistema
  sem a declaracao cai na regra antiga, que e o comportamento conservador
  correto, mas silencioso.

**Riscos e mitigacao**

- *Risco:* alguem declarar `field_language` errado e desligar a protecao sem
  perceber. *Mitigacao:* a lingua de cada excecao aparece no documento de
  proposta, ao lado do valor, entao a declaracao errada fica visivel para quem
  revisa.

## Referencias

- `docs/f4_validation_findings.md`, achado 3
- `config/sources.yaml`, `meta.canonical_field_language` e `field_language`
- `src/mapping/proposal.py`, `src/mapping/similarity.py`
- ADR-0017 (nao ajustar parametro para o resultado parecer bom)
