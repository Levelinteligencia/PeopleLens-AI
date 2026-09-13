"""Limites da execução (SPEC Parte XIV).

Nenhum valor é arbitrário, e cada um tem a justificativa ao lado. Os marcados
`CONFIGURÁVEL` são os que a calibração de uso pode mover; os outros são
estruturais.

O limite de contexto **não é um número de tokens**, e isso é deliberado: definir
por tamanho convidaria a caber mais coisa. O contexto é uma lista fechada
(catálogo, vocabulário, política), e o que não está nela não entra.
"""
from __future__ import annotations

from dataclasses import dataclass

# CONFIGURÁVEL — o fluxo mais longo previsto (causal) usa 3 iterações; 6 dá
# margem para uma correção de rota e ainda fica longe de sondagem.
MAX_ITERACOES = 6

# CONFIGURÁVEL — nenhum padrão da SPEC passa de 3 chamadas; 5 cobre um caso não
# previsto sem permitir varredura do catálogo.
MAX_CHAMADAS_MCP = 5

# CONFIGURÁVEL — o MCP já tem 30 s por chamada; 60 s cobre duas lentas e nada mais.
TIMEOUT_S = 60.0

# FIXO — repetir `(tool, args)` idêntica não produz informação nova: ou é loop,
# ou é sondagem.
MAX_REPETICAO_IDENTICA = 0

# CONFIGURÁVEL, e sujeito à decisão A-03 — a terceira consulta ao mesmo KPI e
# período com filtros diferentes é o padrão de quem procura o recorte que passa.
MAX_CONSULTAS_VIZINHAS = 2

# CONFIGURÁVEL — acima disso a ressalva de trust deixa de ser lida, que é
# exatamente o efeito que a política de resposta quer evitar.
MAX_PALAVRAS_RESPOSTA = 400

# CONFIGURÁVEL, e deliberadamente **não configurado** (P-05). Teto de uso do
# LLM por período. `None` significa "nenhum valor de produção decidido", e não
# "sem teto": quem usa cai no valor de desenvolvimento do `llm_interpreter`, que
# declara a origem DEV no registro. Fixar um número aqui agora seria inventá-lo.
ORCAMENTO_LLM_POR_PERIODO = None


@dataclass(frozen=True)
class Limites:
    max_iteracoes: int = MAX_ITERACOES
    max_chamadas_mcp: int = MAX_CHAMADAS_MCP
    timeout_s: float = TIMEOUT_S
    max_repeticao_identica: int = MAX_REPETICAO_IDENTICA
    max_consultas_vizinhas: int = MAX_CONSULTAS_VIZINHAS
    max_palavras_resposta: int = MAX_PALAVRAS_RESPOSTA
    orcamento_llm_por_periodo: int | None = ORCAMENTO_LLM_POR_PERIODO

    def to_dict(self) -> dict:
        return {
            "max_iteracoes": self.max_iteracoes,
            "max_chamadas_mcp": self.max_chamadas_mcp,
            "timeout_s": self.timeout_s,
            "max_repeticao_identica": self.max_repeticao_identica,
            "max_consultas_vizinhas": self.max_consultas_vizinhas,
            "max_palavras_resposta": self.max_palavras_resposta,
            "orcamento_llm_por_periodo": self.orcamento_llm_por_periodo,
        }


PADRAO = Limites()
