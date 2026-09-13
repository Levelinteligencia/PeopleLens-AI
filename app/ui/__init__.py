"""Camada de apresentação do PeopleLens AI.

Três módulos, e uma fronteira:

    sessao.py        o Harness em cache; o único caminho até o projeto
    apresentacao.py  envelope governado -> blocos de tela
    textos.py        rótulos em PT-BR e EN-US

Nada aqui calcula KPI, abre arquivo de dado, fala SQL ou conhece DuckDB. A UI
faz uma chamada, `harness.run`, e desenha o que voltou.
"""
