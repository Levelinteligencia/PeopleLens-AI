"""Ciclo de vida do Harness dentro do Streamlit.

O Streamlit reexecuta o script inteiro a cada interação. Sem cache, cada clique
subiria um servidor MCP novo, releria o catálogo e reconstruiria o vocabulário —
segundos por pergunta, e uma conexão DuckDB nova a cada vez.

`@st.cache_resource` mantém **um** Harness por processo. É a única coisa que
este módulo faz, e é deliberadamente a única: nenhuma lógica de People
Analytics mora aqui, e a UI conversa com o projeto por um caminho só,
`harness.run`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st


def raiz() -> Path:
    """A raiz do projeto, a partir deste arquivo: app/ui/ -> app/ -> raiz."""
    return Path(__file__).resolve().parents[2]


def _preparar_path() -> None:
    src = str(raiz() / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


@st.cache_resource(show_spinner=False)
def harness():
    """Um Harness por processo, com o interpretador que o ambiente permitir.

    Com credencial, o `LLMInterpreter` real, tendo o `RuleInterpreter` como
    fallback declarado (D-05). Sem credencial, o determinístico direto — e a
    tela **diz** qual dos dois está respondendo, porque um demo que parece usar
    LLM sem usar é pior do que um demo sem LLM.
    """
    _preparar_path()
    from agent.harness import Harness
    from agent.interpreter import RuleInterpreter
    from generator import config

    cfg = config.load(raiz())

    if os.environ.get("OPENAI_API_KEY"):
        from agent import llm_client as cli
        from agent.llm_interpreter import LLMInterpreter
        interpretador = LLMInterpreter(cliente=cli.ClienteOpenAI(),
                                       fallback=RuleInterpreter())
    else:
        interpretador = RuleInterpreter()

    return Harness.start(cfg, interpreter=interpretador)


def tem_credencial() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def perguntar(pergunta: str):
    """O único ponto de contato entre a UI e o projeto.

    `registrar=False`: a demo não escreve no banco de governança. O registro
    continua existindo no fluxo normal; aqui ele é omitido de propósito, para
    que apresentar a tela não polua o log de execuções reais.
    """
    return harness().run(pergunta, registrar=False)


def definicao(kpi_id: str) -> dict:
    """Contrato do KPI, pela capacidade que existe para isso."""
    env = harness().servidor.call("get_kpi_definition", {"kpi": kpi_id},
                                  registrar=False)
    return env.data if env.ok else {}


def linhagem(kpi_id: str, trace_id: str | None = None) -> dict:
    """Degraus da linhagem, pela capacidade que existe para isso."""
    args = {"kpi": kpi_id}
    if trace_id:
        args["trace_id"] = trace_id
    env = harness().servidor.call("get_lineage", args, registrar=False)
    return env.data if env.ok else {}
