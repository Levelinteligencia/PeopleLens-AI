# ADR-0019: O universo de referencia de um check de integridade e a camada de identidade

- **Status:** Aceita
- **Data:** 2026-09-11
- **Origem:** decisao da Sam na aprovacao da F3, item 6
- **Fase:** vigora da F3 em diante

## Contexto

O check `DQ_REF_002` verificava se o gestor de cada pessoa existe no cadastro, e
acusou **23,3% de gestores orfaos** contra uma taxa injetada de 1,8%.

A causa: o check comparava `HRIS_LEGACY.GESTOR` contra
`HRIS_LEGACY.MATRICULA`, ou seja, usava **um dataset** como universo de
referencia. O cadastro legado cobre apenas quem esteve ativo entre 2016 e 2019.
Um gestor pode existir na empresa sem estar naquele recorte de arquivo.

Dos 348 orfaos acusados, cerca de 24 eram o defeito D09 de verdade. O resto era
artefato do escopo do arquivo.

## A tentacao que esta decisao proibe

A saida rapida seria mexer no limiar: de 3% para 25%, o check passa. E ai ele
nunca mais detecta nada, porque o limiar agora acomoda o ruido que ele deveria
denunciar.

**Ajustar limiar para compensar universo de referencia inadequado e proibido.**
Um limiar responde a pergunta "quanto de falha e tolerado". Um universo de
referencia responde a pergunta "falha em relacao a que". Sao perguntas
diferentes, e usar a resposta de uma para consertar a outra destroi as duas.

Esta e a mesma familia do ADR-0017: nao se empurra um numero para o resultado
desejado.

## Decisao

**Quando a entidade existe em mais de um sistema, o universo de referencia de um
check de integridade referencial e a camada de identidade conformada, nunca um
dataset isolado.**

Em termos operacionais:

1. `xref_employee_identity` (ADR-0004) e exposto ao runner de qualidade como
   dataset consultavel sob o nome `CONFORMED.identity`.
2. Checks de integridade sobre entidades multi-sistema (pessoa, requisicao,
   centro de custo) referenciam esse universo.
3. Checks sobre entidades que existem em um sistema so continuam referenciando
   aquele dataset, e isso e correto.
4. Quando um check de integridade der taxa muito acima do defeito injetado
   conhecido, a primeira hipotese a investigar e o universo de referencia, e nao
   o limiar.

Consequencia de ordem: **a camada de identidade e pre-requisito da camada de
qualidade**, e nao uma etapa paralela. O pipeline reflete isso: identidade roda
na L2, antes dos checks.

## Alternativas consideradas

1. **Afrouxar o limiar.** Proibida pelo argumento acima.
2. **Ampliar o dataset de referencia** (juntar os dois HRIS no check).
   Funcionaria para este caso e quebraria no proximo, quando entrar a folha ou a
   segunda aquisicao. Trata o sintoma.
3. **Marcar o check como WARNING** para nao incomodar. Pior de todas: mantem o
   ruido e remove a consequencia.
4. **Universo de identidade conformada.** Escolhida. Resolve a classe, nao o caso.

## Consequencias

**Positivas**

- A taxa caiu de 23,3% para 0,99%, que e a ordem do defeito injetado, e o check
  voltou a detectar o que deveria.
- Fica explicito que identidade precede qualidade.
- Vale para os sistemas da onda 2 sem alteracao.

**Negativas**

- Cria dependencia de ordem no pipeline: um check de integridade multi-sistema
  nao pode rodar antes da resolucao de identidade.
- Se a propria camada de identidade estiver incompleta, o check herda o
  problema. Por isso a cobertura de identidade e reportada junto.

**Riscos e mitigacao**

- *Risco:* identidade incompleta produzir falso positivo de novo.
  *Mitigacao:* o relatorio da F4 traz a taxa de resolucao por sistema, e um
  check de cobertura de identidade entra na F5.

## Referencias

- `docs/f3_validation_findings.md`, achado 2
- ADR-0004 (resolucao de identidade), ADR-0010 (severidade), ADR-0017 (nao empurrar numero)
- `config/quality_checks.yaml`, check `DQ_REF_002`
