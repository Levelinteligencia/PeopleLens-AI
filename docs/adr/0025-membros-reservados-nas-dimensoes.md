# ADR-0025: Pendência de governança vira membro nomeado, nunca nulo

- **Status:** **Proposta** (F6, aguardando aprovação)
- **Data:** 2026-09-11
- **Origem:** SPEC da F6, Parte VI
- **Fase:** vigora da F6 em diante
- **Emenda 1 (revisao da F6, diretriz 1):** identidade nao resolvida **nao** cai
  no membro `-1` de `dim_employee`. Ela vira **pessoa provisoria**, com
  `party_key` no escopo da fonte (ADR-0027, decisao 6). O membro `-1` de
  `dim_employee` fica reservado para registro sem chave de origem utilizavel,
  que e caso raro. A razao da emenda: colapsar toda identidade nao resolvida num
  membro unico faria os 320 registros da VivaMarket deixarem de ser contaveis
  como pessoas, e a classificacao de origem do ADR-0027 nao teria sobre o que
  incidir.

## Contexto

A F5 fechou com uma taxonomia de sete classes de achado e com um princípio que a
Sam fixou: **nem tudo que não está resolvido está errado**. Um valor sem
mapeamento aprovado é legítimo na origem e espera uma decisão; uma identidade não
resolvida é uma pessoa que existe e cujo vínculo entre sistemas não foi feito.

A camada analítica é onde esse princípio corre o maior risco de ser perdido, e o
mecanismo é banal: um `join` que não encontra a chave produz nulo, e nulo não
tem classe, não tem motivo e não é contável. Três coisas muito diferentes —
`N4` da VivaMarket, um departamento sem mapa e alguém que optou por não declarar
raça — chegariam à L4 como a mesma coisa: vazio.

Depois disso, as duas saídas usuais são igualmente ruins. Filtrar os nulos apaga
a pendência do denominador e faz o número parecer melhor do que é. Substituí-los
por um valor plausível transforma pendência em valor válido, que é exatamente o
que a Sam proibiu ao abrir a F5.

## Decisão

**Nenhuma chave estrangeira do modelo analítico é nula.** Toda dimensão carrega
membros reservados com chave negativa, nomeados, e a classe de achado da F5
correspondente:

| Chave | Membro | Classe de achado | Dimensões |
|---|---|---|---|
| `-1` | não mapeado | `NAO_MAPEADO` | `dim_organization` |
| `-1` | sem chave de origem utilizável | — | `dim_employee` |
| `-1` | origem indeterminada | — | `dim_origin` |
| `-2` | decisão de negócio pendente | `DECISAO_PENDENTE` | `dim_job_level`, `dim_organization` |
| `-3` | tradução pendente | `NAO_MAPEADO` | `dim_organization` |
| `-4` | não informado | `AUSENCIA_LEGITIMA` | `dim_employee` |
| `-5` | ainda não ocorreu | — | `dim_calendar` |
| `-6` | fora da vigência do sistema | `DESATUALIZADO` | `dim_source_system` |

Regras que acompanham:

0. **Identidade não resolvida é a exceção, e vira pessoa provisória**, não
   membro reservado (Emenda 1). Pendência de mapeamento e de decisão viram
   membro; pendência de *vínculo* vira uma pessoa a mais, porque a pessoa
   existe e precisa ser contável.
1. **Nenhuma linha é descartada por apontar para um membro reservado.**
   Descartar esconderia o tamanho da pendência, que é justamente o que o trust
   score mede.
2. **Membro reservado nunca é convertido em valor plausível.** `N4` vira o
   membro `-2` de `dim_job_level` e continua sendo `N4` na coluna de origem.
3. **A classe de achado viaja junto**, para que a L4 possa distinguir na resposta
   "não sei quem é essa pessoa" de "essa pessoa optou por não declarar".
4. **O membro `-5` do calendário existe** para marcos de snapshot acumulativo
   ainda não atingidos, e é diferente de um marco que nunca vai ocorrer.
5. **Contar membros reservados é uma operação de primeira classe**, e não um
   filtro que alguém lembra de aplicar.

## Alternativas consideradas

1. **Permitir nulo e tratar na L4.** É o comportamento padrão de qualquer
   `left join`, e é a razão de este ADR existir. Nulo perde a classe, e sem a
   classe as sete distinções da F5 morrem na fronteira entre L2 e L3.
2. **Um membro único de "desconhecido" por dimensão.** Mais simples e perde
   exatamente a informação que interessa: não estar mapeado, não ter vínculo e
   não ter sido declarado exigem ações diferentes de pessoas diferentes.
3. **Excluir da L3 as linhas com pendência.** Descartada, e seria a pior de
   todas: a população analítica passaria a ser a fatia limpa, os KPIs ficariam
   bonitos, e o projeto teria construído cinco fases de governança para depois
   filtrar o resultado dela.
4. **Chaves positivas para os membros reservados.** Descartada: chave negativa é
   visível numa leitura rápida e não colide com chave substituta gerada por
   sequência.

## Consequências

**Positivas**

- As cinco distinções da Sam sobrevivem à camada analítica, que é onde elas
  seriam perdidas.
- Um KPI pode escolher excluir a pendência do numerador, e ainda assim reportar
  quanto excluiu — que é a diferença entre um número e um número em que se pode
  confiar.
- `N4` e `N5` continuam contáveis, o que preserva a decisão da F4 até a ponta.

**Negativas**

- Toda dimensão precisa das linhas reservadas, mesmo as que nunca as usam, e
  isso é trabalho de construção repetitivo.
- Consulta ingênua passa a somar membros reservados. Um `headcount` que inclua o
  membro `-1` conta pessoas cuja identidade não foi resolvida, o que pode estar
  certo ou errado dependendo da pergunta — e a L4 precisa decidir
  explicitamente, que é o ponto.

**Riscos e mitigação**

- *Risco:* alguém filtrar `sk > 0` por reflexo, em todo lugar, e a pendência
  voltar a ser invisível. *Mitigação:* o contrato de KPI da F7 declara o
  tratamento de membro reservado, e um teste verifica que o declarado e o
  calculado batem.

## Referências

- `docs/F6_analytical_model.md`, Parte VI
- ADR-0022 (classe de achado), ADR-0004 (identidade), ADR-0007 (n mínimo)
