"""Semantic Layer, KPI Catalog e Trust Layer da F7 (camada L4 do ADR-0003).

A divisao de trabalho que este pacote faz valer:

    People Analytics define e governa os KPIs.   -> config/kpis/*.yaml
    A camada analitica calcula.                  -> L3 (F6), via executor
    A Semantic Layer certifica e descreve.       -> este pacote
    A IA interpreta.                             -> fora daqui

A IA **nao calcula KPI sobre RAW nem sobre tabela intermediaria**, e isso nao e
uma instrucao em prompt: e a forma da saida. A IA emite um `SemanticQuery`, que
nao tem onde escrever nome de tabela, coluna, junção ou fragmento de SQL
(ADR-0028). O resto e determinístico.

    pergunta  --IA-->  SemanticQuery  --validacao-->  plano  --DuckDB-->  Answer
                       (unico passo         (deterministico, sobre a L3 e so a L3)
                        com latitude)
"""
