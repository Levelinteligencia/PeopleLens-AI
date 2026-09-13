"""Agent Harness: o ambiente que executa o Loop (SPEC Parte IV).

O Harness **não raciocina**. Ele carrega o contexto fechado, mantém o estado,
faz valer as políticas e os limites, aplica as proteções que não podem depender
do modelo (A-03) e registra o que aconteceu.

A tese da SPEC está na ordem em que as coisas acontecem aqui: quando o agente
tenta algo que a Parte II proíbe, ele falha contra **estrutura** — o MCP não tem
a capacidade, a Semantic Layer não tem a regra, o Harness não deixa a chamada
passar. Só uma proibição depende de política, a de escolher em silêncio um KPI
parecido, e por isso o plano é artefato e a seleção vem da matriz.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from generator.config import Config
from mcp import actor as mcp_actor
from mcp.server import Server

from . import context as ctx_mod
from . import limits as lim
from . import loop as L
from . import observability, plan as plan_mod, redaction, render
from .interpreter import Interpreter, RuleInterpreter
from .intent import (CAUSAL, COMPARACAO, CONFIANCA, DEFINICAO, LINHAGEM,
                     RANKING, VALOR, resolve)
from .privacy_guard import PrivacyGuard


@dataclass
class Execucao:
    """O resultado de uma execução: resposta, estado e proteções acionadas."""
    resposta: render.Resposta
    state: L.State
    bloqueios_de_privacidade: list[dict] = field(default_factory=list)
    duracao_ms: int = 0
    # Metadados do interpretador: qual foi usado, versão, modelo, retry,
    # fallback e motivo. Vazio quando o interpretador não declara registro,
    # que é o caso do `RuleInterpreter`.
    interpretacao: dict = field(default_factory=dict)

    @property
    def stop_reason(self) -> str | None:
        return self.state.stop_reason

    def to_dict(self) -> dict:
        return {**self.state.to_dict(),
                "resposta": self.resposta.to_dict(),
                "bloqueios_de_privacidade": list(self.bloqueios_de_privacidade),
                "interpretacao": dict(self.interpretacao),
                "duracao_ms": self.duracao_ms}


@dataclass
class Harness:
    cfg: Config
    servidor: Server
    contexto: ctx_mod.Contexto
    interpreter: Interpreter
    limites: lim.Limites = field(default_factory=lambda: lim.PADRAO)

    # --------------------------------------------------------------- ciclo de vida
    @classmethod
    def start(cls, cfg: Config, actor: mcp_actor.Actor | None = None,
              interpreter: Interpreter | None = None,
              limites: lim.Limites | None = None,
              servidor: Server | None = None) -> "Harness":
        srv = servidor or Server.start(cfg)
        ator = actor or mcp_actor.ATOR_PADRAO
        contexto = ctx_mod.construir(srv, ator, cfg, politica={
            "limites": (limites or lim.PADRAO).to_dict(),
            "teto_do_ator": ator.max_response_level,
        })
        return cls(cfg=cfg, servidor=srv, contexto=contexto,
                   interpreter=interpreter or RuleInterpreter(),
                   limites=limites or lim.PADRAO)

    def close(self) -> None:
        self.servidor.close()

    # ------------------------------------------------------------------ execução
    def run(self, pergunta: str, actor: mcp_actor.Actor | None = None,
            trace_anterior: str | None = None, registrar: bool = True) -> Execucao:
        ator = actor or mcp_actor.ATOR_PADRAO
        t0 = time.perf_counter()
        state = L.State(run_id=uuid.uuid4().hex[:16],
                        request_id=uuid.uuid4().hex[:16],
                        pergunta=pergunta, actor_ref=ator.ref())
        guarda = PrivacyGuard()

        resposta = self._ciclo(pergunta, ator, state, guarda, trace_anterior)

        # Nenhum caminho sai daqui sem `stop_reason`.
        if state.stop_reason is None:                        # pragma: no cover
            state.stop_reason = resposta.stop_reason or L.FALHA_TECNICA
        dur = int((time.perf_counter() - t0) * 1000)
        exec_ = Execucao(resposta=resposta, state=state,
                         bloqueios_de_privacidade=guarda.to_dict(),
                         interpretacao=self._interpretacao(), duracao_ms=dur)
        if registrar:
            observability.registrar(self.cfg, exec_, ator, self.contexto)
        return exec_

    def _interpretacao(self) -> dict:
        """Registro do interpretador, quando ele declara um.

        Lido por `getattr` de propósito: o protocolo `Interpreter` tem um método
        só, e acrescentar um segundo obrigaria o `RuleInterpreter` a mudar para
        atender observabilidade de outro componente.
        """
        registro = getattr(self.interpreter, "registro", None)
        to_dict = getattr(registro, "to_dict", None)
        return to_dict() if callable(to_dict) else {}

    # --------------------------------------------------------------------- loop
    def _ciclo(self, pergunta: str, ator, state: L.State,
               guarda: PrivacyGuard, trace_anterior: str | None) -> render.Resposta:
        inicio = time.perf_counter()

        # UNDERSTAND ---------------------------------------------------------
        intent = self.interpreter.understand(pergunta, self.contexto)
        state.intent = intent
        state.decidir("UNDERSTAND", intent.question_type,
                      "tipo de pergunta identificado")

        # Perguntas de seguimento herdam o trace anterior.
        if intent.question_type == LINHAGEM and trace_anterior:
            return self._linhagem_por_trace(state, ator, trace_anterior, guarda)

        # RESOLVE ------------------------------------------------------------
        intent = resolve(intent, self.contexto)
        if intent.ambiguity:
            # A-01: nenhuma chamada de valor enquanto a ambiguidade existir.
            state.stop_reason = L.AMBIGUIDADE
            state.decidir("RESOLVE", "ASK",
                          f"{len(intent.ambiguity)} ponto(s) não resolvem contra "
                          "o catálogo e o vocabulário governados")
            return render.ambiguidade(intent)
        state.decidir("RESOLVE", "RESOLVIDO", "intenção resolve contra o catálogo")

        # PLAN ---------------------------------------------------------------
        plano = plan_mod.montar(intent, self.contexto)
        state.plano = plano
        if not plano.steps:
            state.stop_reason = L.AMBIGUIDADE
            return render.ambiguidade(intent)
        state.decidir("PLAN", ",".join(plano.capacidades),
                      f"matriz da SPEC para {intent.question_type}")

        # ACT / OBSERVE / INTERPRET / DECIDE ---------------------------------
        passo_n = len(plano.steps)
        for step in list(plano.steps):
            parada = self._checar_limites(state, inicio)
            if parada:
                return render.parada_por_limite(
                    parada, [o.envelope for o in state.observacoes])

            envelope, bloqueio = self._chamar(state, guarda, ator, step)
            if bloqueio:
                state.stop_reason = L.SUPRESSAO
                return render.bloqueio_de_privacidade(bloqueio)
            if envelope is None:
                state.stop_reason = L.REPETICAO
                return render.parada_por_limite(
                    L.REPETICAO, [o.envelope for o in state.observacoes])

            resultado = self._interpretar(state, intent, envelope, step,
                                          guarda, plano, passo_n)
            if resultado is not None:
                return resultado
            passo_n = len(plano.steps)

        # RESPOND ------------------------------------------------------------
        return self._responder(state, intent)

    # ------------------------------------------------------------------- passos
    def _checar_limites(self, state: L.State, inicio: float) -> str | None:
        state.iteracoes += 1
        if state.iteracoes > self.limites.max_iteracoes:
            state.limites_atingidos.append("max_iteracoes")
            state.stop_reason = L.LIMITE_ITERACOES
            return L.LIMITE_ITERACOES
        if state.chamadas_efetivas >= self.limites.max_chamadas_mcp:
            state.limites_atingidos.append("max_chamadas_mcp")
            state.stop_reason = L.LIMITE_CHAMADAS
            return L.LIMITE_CHAMADAS
        if time.perf_counter() - inicio > self.limites.timeout_s:
            state.limites_atingidos.append("timeout_s")
            state.stop_reason = L.TIMEOUT
            return L.TIMEOUT
        return None

    def _chamar(self, state: L.State, guarda: PrivacyGuard, ator,
                step: plan_mod.Step):
        """ACT + OBSERVE. Devolve (envelope, motivo_de_bloqueio)."""
        tool, args = step.capacidade, dict(step.args)

        # P-09: repetição idêntica não produz informação nova.
        if state.ja_chamou(tool, args):
            state.decidir("DECIDE", "PARAR", "a próxima chamada repetiria uma já feita")
            return None, None

        # A-03: o Harness barra a sequência de contorno, antes de chamar.
        pode, motivo = guarda.permite(tool, args)
        if not pode:
            state.chamadas.append(L.Chamada(
                passo=step.passo, tool=tool, args=args, outcome="BLOQUEADA",
                trace_id="", bloqueada=True, motivo_bloqueio=motivo))
            state.decidir("ACT", "BLOQUEADA", motivo)
            return None, motivo

        # Limite de consultas vizinhas ao mesmo KPI e período.
        if (tool in ("get_kpi", "breakdown_kpi", "compare_kpi")
                and state.vizinhas(args.get("kpi"), args.get("period"))
                >= self.limites.max_consultas_vizinhas):
            state.limites_atingidos.append("max_consultas_vizinhas")
            state.chamadas.append(L.Chamada(
                passo=step.passo, tool=tool, args=args, outcome="BLOQUEADA",
                trace_id="", bloqueada=True,
                motivo_bloqueio="limite de consultas vizinhas ao mesmo recorte"))
            return None, "limite de consultas vizinhas ao mesmo KPI e período"

        t0 = time.perf_counter()
        env = self.servidor.call(tool, args, actor=ator)
        dur = int((time.perf_counter() - t0) * 1000)
        d = env.to_dict()

        state.chamadas.append(L.Chamada(
            passo=step.passo, tool=tool, args=args, outcome=env.outcome,
            trace_id=env.trace_id,
            refusal_class=(env.refusal or {}).get("classe"), duracao_ms=dur))
        state.observacoes.append(L.Observacao(step.passo, tool, d))

        if env.outcome == "SUPPRESSED":
            guarda.registrar_supressao(tool, args)
        return d, None

    def _interpretar(self, state: L.State, intent, envelope: dict,
                     step: plan_mod.Step, guarda: PrivacyGuard,
                     plano: plan_mod.Plan, passo_n: int):
        """INTERPRET + DECIDE. Devolve uma resposta quando o loop deve parar."""
        outcome = envelope.get("outcome")

        if outcome == "ERROR":
            state.stop_reason = L.FALHA_TECNICA
            state.decidir("INTERPRET", "PARAR", "erro técnico do MCP")
            return render.falha_tecnica(envelope)

        if outcome == "SUPPRESSED":
            state.stop_reason = L.SUPRESSAO
            state.decidir("INTERPRET", "PARAR",
                          "supressão por privacidade; não há recorte alternativo "
                          "legítimo a tentar")
            return render.supressao(envelope)

        if outcome == "REFUSAL":
            classe = (envelope.get("refusal") or {}).get("classe")
            # A-05: comparação recusada permite dois get_kpi lado a lado, sem conta.
            if (step.capacidade == plan_mod.COMPARE_KPI
                    and classe in ("COMPARACAO_NAO_RESPONDIVEL",
                                   "COMPARACAO_ENTRE_VERSOES")):
                extras = plan_mod.fallback_a05(intent, self.contexto, passo_n + 1)
                if extras:
                    plano.steps.extend(extras)
                    state.decidir(
                        "DECIDE", "FALLBACK_A05",
                        "comparação recusada; dois valores independentes, sem "
                        "calcular diferença")
                    return None
            state.stop_reason = L.RECUSA_GOVERNADA
            state.decidir("INTERPRET", "PARAR", f"recusa governada: {classe}")
            return render.recusa(envelope, self.contexto)

        # ANSWER: segue para o próximo passo do plano, se houver.
        nivel = (envelope.get("response_level") or {}).get("granted")
        state.decidir("INTERPRET", "SEGUIR",
                      f"resposta obtida em {nivel}; "
                      f"{(envelope.get('trust') or {}).get('status')}")
        return None

    def _linhagem_por_trace(self, state: L.State, ator, trace_id: str,
                            guarda: PrivacyGuard) -> render.Resposta:
        step = plan_mod.passo_de_seguimento(
            plan_mod.GET_LINEAGE, {"trace_id": trace_id},
            "pergunta de linhagem sobre a resposta anterior",
            "encadear os degraus até a fonte", passo=1)
        state.plano = plan_mod.Plan(steps=[step],
                                    justificativa="linhagem da resposta anterior")
        envelope, _ = self._chamar(state, guarda, ator, step)
        if envelope is None:
            state.stop_reason = L.FALHA_TECNICA
            return render.parada_por_limite(L.FALHA_TECNICA, [])
        if envelope.get("outcome") != "ANSWER":
            state.stop_reason = L.RECUSA_GOVERNADA
            return render.recusa(envelope, self.contexto)
        state.stop_reason = L.SUFICIENTE
        return render.resposta_de_linhagem(envelope)

    # ---------------------------------------------------------------- RESPOND
    def _responder(self, state: L.State, intent) -> render.Resposta:
        uteis = [o for o in state.observacoes
                 if o.envelope.get("outcome") == "ANSWER"]
        if not uteis:
            state.stop_reason = L.FALHA_TECNICA        # pragma: no cover
            return render.parada_por_limite(L.FALHA_TECNICA, [])

        envs = [o.envelope for o in uteis]
        tipo = intent.question_type
        state.stop_reason = L.SUFICIENTE

        if tipo == CAUSAL:
            return render.negacao_causal(intent, envs)

        fallback = [o for o in uteis
                    if o.tool == plan_mod.GET_KPI and len(uteis) == 2
                    and tipo == COMPARACAO]
        if fallback:
            return render.resposta_lado_a_lado([o.envelope for o in fallback])

        ultimo = uteis[-1]
        if tipo == RANKING:
            unidade = (self.contexto.kpi(intent.kpi) or {}).get("unit") or ""
            resposta = render.resposta_de_ranking(ultimo.envelope, unidade)
            correcao = render.corrigir_premissa(intent, ultimo.envelope)
            return resposta

        por_tipo = {
            COMPARACAO: render.resposta_de_comparacao,
            DEFINICAO: render.resposta_de_definicao,
            CONFIANCA: render.resposta_de_trust,
            LINHAGEM: render.resposta_de_linhagem,
        }
        montar = por_tipo.get(tipo, render.resposta_de_valor)
        resposta = montar(ultimo.envelope)

        correcao = render.corrigir_premissa(intent, ultimo.envelope)
        if correcao:
            resposta.texto = f"{correcao} {resposta.texto}"
        return resposta
