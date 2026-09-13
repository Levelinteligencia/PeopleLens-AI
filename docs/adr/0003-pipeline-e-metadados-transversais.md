# ADR-0003: Separação entre pipeline em linha e metadados transversais

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D3 (Technical Design v0.3)
- **Fase:** F0, vigora a partir da F3

## Contexto

O diagrama conceitual da Especificação lista PROFILING, DATA QUALITY e
QUARANTINE na mesma sequência vertical das camadas de dados. Implementado
literalmente, isso coloca a camada de qualidade **dentro** da linha de
transformação, entre uma camada e a próxima.

O problema é o princípio 1: o RAW nunca é alterado. Esse princípio não se
sustenta por boa vontade. Se o módulo de DQ estiver na linha, existe caminho
técnico para ele corrigir de passagem, e em algum momento alguém vai resolver
um bug fazendo exatamente isso.

## Decisão

Separar fisicamente duas famílias de operação.

**Operações que transformam** e produzem uma nova camada de dados:

```
L0 raw  ->  L1 standardized  ->  L2 conformed  ->  L3 analytical  ->  L4 semantic
```

**Operações que observam** e produzem apenas metadados, sem serem donas de
nenhuma camada de dados: `profiling_results`, `data_quality_results`,
`data_lineage`.

**Quarentena é desvio lateral**, não passo adiante: `data_quarantine` e
`mapping_exceptions` recebem o registro reprovado com a regra que o reprovou
anexada. O registro não é apagado nem corrigido, e o original permanece no RAW.

Responsabilidade por camada:

| Camada | Faz | Não faz |
|---|---|---|
| L0 raw | copia o que a fonte entregou, tudo como texto | não converte tipo, não corta espaço, não interpreta data |
| L1 standardized | normaliza forma: encoding, espaços, caixa, parse de data e número | não traduz significado |
| L2 conformed | aplica DE/PARA, resolve identidade, separa quarentena e exceções | não calcula indicador |
| L3 analytical | dim e fact, SCD2, chaves substitutas, integridade garantida | não interpreta |
| L4 semantic | métricas certificadas, trust score | não responde perguntas |

O **diagrama conceitual da Especificação permanece intacto** no README e na
apresentação. Este ADR define a visão física que o implementa. Os dois convivem
documentados.

## Alternativas consideradas

1. **Implementar o diagrama conceitual literalmente.** Descartada: cria caminho
   técnico para violar o princípio 1.
2. **DQ como camada que filtra destrutivamente.** Descartada: a seção 19 da
   Especificação exige que a quarentena preserve o registro original.
3. **Profiling como camada materializada de dados.** Descartada: profiling
   produz estatística sobre dados, não uma nova versão deles.

## Consequências

**Positivas**

- O princípio 1 passa a ser propriedade da arquitetura, não promessa.
- A camada de metadados fica reutilizável por lineage e trust score sem
  acoplamento com a ordem do pipeline.
- Permissão de leitura por camada fica simples de declarar, o que sustenta o
  ADR-0015 e a restrição de acesso da IA.

**Negativas**

- Duas visões (conceitual e física) para manter em sincronia na documentação.

**Riscos e mitigação**

- *Risco:* alguém confundir as duas visões numa apresentação. *Mitigação:* as
  duas aparecem lado a lado em `docs/`, com rótulo explícito.

## Referências

- Technical Design v0.3, seções 5 e 17 (R2)
- Especificação do Universo v1.0, seções 18, 19 e princípio 1
