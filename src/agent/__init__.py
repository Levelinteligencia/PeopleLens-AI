"""PeopleLens Analyst Agent — Harness, Loop e políticas (SPEC v0.1).

    "O agente pode investigar os dados, mas não pode alterar a verdade dos dados."

    "Quando o PeopleLens não puder responder, ele deve explicar por quê — e,
     quando possível, ajudar a pessoa a fazer uma pergunta que possa ser
     respondida."

O agente alcança dados **somente** pelas seis capacidades do MCP. Ele não tem
conexão, não monta consulta física, não calcula e não faz aritmética entre
resultados. O que ele acrescenta ao sistema é uma coisa só: traduzir pergunta em
intenção governada, e resultado governado em texto que uma pessoa entende.

Três camadas, e a distinção entre elas não pode colapsar:

    Harness   o ambiente: contexto fechado, estado, políticas, limites, registro
    Loop      o ciclo: UNDERSTAND RESOLVE PLAN ACT OBSERVE INTERPRET DECIDE RESPOND
    Agent     o que interpreta linguagem — e só isso

`Interpreter` é a costura onde um modelo entra. Tudo que decide **o que é
verdade** está fora dele: a seleção de capacidade vem da matriz da SPEC, o
`RESOLVE` é código contra catálogo e vocabulário, e a resposta cita apenas
números que vieram de um envelope com `trace_id`.
"""
