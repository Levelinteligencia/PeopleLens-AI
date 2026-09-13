"""Agent Loop e o estado de uma execução (SPEC Parte V).

    UNDERSTAND -> RESOLVE -> PLAN -> ACT -> OBSERVE -> INTERPRET -> DECIDE
                                      ^                               |
                                      +-------------------------------+
                                                                      -> RESPOND

Duas escolhas de desenho que a SPEC fixou e este módulo faz valer:

- **não existe passo VALIDATE.** Trust, teto de nível, n mínimo e estados
  governados já chegam validados no envelope. Um passo chamado "validar"
  convidaria o agente a reavaliar o que já foi decidido, e reavaliar é meio
  caminho para discordar. O passo é `INTERPRET`: ler o que o envelope diz e
  traduzir para consequência;

- **`RESOLVE` vem antes de tudo que custa.** Ele não gasta chamada e mata a
  classe inteira de "respondi com precisão a pergunta errada".

**Toda execução termina com um `stop_reason`.** Um caminho sem ele é defeito do
Harness, não execução atípica.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Critérios de parada. A lista é fechada.
SUFICIENTE = "SUFICIENTE"
RECUSA_GOVERNADA = "RECUSA_GOVERNADA"
SUPRESSAO = "SUPRESSAO"
AMBIGUIDADE = "AMBIGUIDADE"
TETO = "TETO"
LIMITE_ITERACOES = "LIMITE_ITERACOES"
LIMITE_CHAMADAS = "LIMITE_CHAMADAS"
TIMEOUT = "TIMEOUT"
FALHA_TECNICA = "FALHA_TECNICA"
REPETICAO = "REPETICAO"

STOP_REASONS = (SUFICIENTE, RECUSA_GOVERNADA, SUPRESSAO, AMBIGUIDADE, TETO,
                LIMITE_ITERACOES, LIMITE_CHAMADAS, TIMEOUT, FALHA_TECNICA,
                REPETICAO)

# Paradas em que a resposta é parcial, e precisa dizer isso. Um parcial
# apresentado como completo é o mesmo erro que um top-50 apresentado como total.
PARADAS_PARCIAIS = (LIMITE_ITERACOES, LIMITE_CHAMADAS, TIMEOUT, REPETICAO)

PASSOS = ("UNDERSTAND", "RESOLVE", "PLAN", "ACT", "OBSERVE", "INTERPRET",
          "DECIDE", "RESPOND")


@dataclass
class Chamada:
    """Uma chamada ao MCP, com o que ela produziu. Imutável depois de gravada."""
    passo: int
    tool: str
    args: dict
    outcome: str
    trace_id: str
    refusal_class: str | None = None
    duracao_ms: int = 0
    bloqueada: bool = False
    motivo_bloqueio: str | None = None

    @property
    def assinatura(self) -> tuple:
        """Identidade de `(tool, args)` para detectar repetição idêntica."""
        return (self.tool, _congela(self.args))

    def to_dict(self) -> dict:
        return {"passo": self.passo, "tool": self.tool, "outcome": self.outcome,
                "trace_id": self.trace_id, "refusal_class": self.refusal_class,
                "duracao_ms": self.duracao_ms, "bloqueada": self.bloqueada,
                "motivo_bloqueio": self.motivo_bloqueio}


def _congela(valor):
    if isinstance(valor, dict):
        return tuple(sorted((k, _congela(v)) for k, v in valor.items()))
    if isinstance(valor, (list, tuple)):
        return tuple(_congela(v) for v in valor)
    return valor


@dataclass
class Observacao:
    """O envelope como veio. O agente pode ler e citar; não pode reescrever."""
    passo: int
    tool: str
    envelope: dict

    @property
    def outcome(self) -> str:
        return self.envelope.get("outcome", "")

    @property
    def trace_id(self) -> str:
        return self.envelope.get("trace_id", "")


@dataclass
class Decisao:
    passo: str
    escolha: str
    porque: str

    def to_dict(self) -> dict:
        return {"passo": self.passo, "escolha": self.escolha, "porque": self.porque}


@dataclass
class State:
    """O que dura uma execução. Morre com ela (SPEC Parte XII)."""
    run_id: str
    request_id: str
    pergunta: str
    actor_ref: str
    intent: object | None = None
    plano: object | None = None
    chamadas: list[Chamada] = field(default_factory=list)
    observacoes: list[Observacao] = field(default_factory=list)
    decisoes: list[Decisao] = field(default_factory=list)
    limites_atingidos: list[str] = field(default_factory=list)
    stop_reason: str | None = None
    iteracoes: int = 0

    # --------------------------------------------------------------- consultas
    @property
    def chamadas_efetivas(self) -> int:
        return sum(1 for c in self.chamadas if not c.bloqueada)

    def ja_chamou(self, tool: str, args: dict) -> bool:
        alvo = (tool, _congela(args))
        return any(c.assinatura == alvo for c in self.chamadas if not c.bloqueada)

    def vizinhas(self, kpi: str, periodo: dict | None) -> int:
        """Consultas ao mesmo KPI e período, com recortes diferentes."""
        from .privacy_guard import _chave_periodo
        chave = _chave_periodo(periodo)
        return sum(1 for c in self.chamadas
                   if not c.bloqueada
                   and c.args.get("kpi") == kpi
                   and _chave_periodo(c.args.get("period")) == chave)

    def decidir(self, passo: str, escolha: str, porque: str) -> None:
        self.decisoes.append(Decisao(passo, escolha, porque))

    @property
    def parcial(self) -> bool:
        return self.stop_reason in PARADAS_PARCIAIS

    @property
    def envelopes_uteis(self) -> list[dict]:
        return [o.envelope for o in self.observacoes
                if o.envelope.get("outcome") == "ANSWER"]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id, "request_id": self.request_id,
            "actor_ref": self.actor_ref,
            "intent": self.intent.to_dict() if self.intent else None,
            "plan": self.plano.to_dict() if self.plano else None,
            "calls": [c.to_dict() for c in self.chamadas],
            "decisions": [d.to_dict() for d in self.decisoes],
            "limits_hit": list(self.limites_atingidos),
            "stop_reason": self.stop_reason,
            "iteracoes": self.iteracoes,
            "chamadas_mcp": self.chamadas_efetivas,
        }
