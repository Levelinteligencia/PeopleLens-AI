"""MCP v0.1 — a fronteira controlada entre o futuro Agent e a Semantic Layer.

    "PeopleLens não dá ao agente acesso aos dados.
     PeopleLens dá ao agente capacidades governadas para perguntar aos dados."

Seis capacidades, read-only, e **nenhuma outra**. A escrita, a leitura de RAW e o
SQL arbitrário não são negados por permissão: a ferramenta não existe, então não
há chamada a negar (ADR-0031). Permissão é a segunda cerca, mais estreita, dentro
de uma superfície que já é fechada.

Esta camada **não calcula** e **não decide**. Ela autoriza, valida a forma,
aplica limites, chama `analytics.semantic.ask` e preserva integralmente o que
volta: trust, teto de nível, supressão por privacidade e estados governados.
Duplicar qualquer regra da Semantic Layer aqui criaria uma segunda camada
semântica que diverge da primeira — exatamente o defeito que este projeto já
pagou duas vezes.

    Agent  ->  MCP  ->  Semantic Layer (F7)  ->  Analytical Model (F6)
               ^
               autoriza, limita, registra. Não calcula.
"""
