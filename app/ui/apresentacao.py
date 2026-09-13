"""Envelope governado -> blocos de tela. Formatação, e nada além disso.

A regra que organiza este módulo: **se o número não veio do envelope, ele não
aparece.** Aqui não há cálculo de KPI, não há agregação, não há reconstrução de
linha suprimida, não há segunda definição de nada. O que existe é escolha de
rótulo, formatação de percentual e montagem de tabela.

É isso que torna a decisão R-1/B honesta. Os blocos executivos em EN-US não são
tradução da prosa do agente: são leitura dos campos estruturados do envelope,
que são neutros de idioma. O texto do agente continua existindo, em português,
na seção técnica, exatamente como ele o escreveu.
"""
from __future__ import annotations

from .textos import EN, PT, t

# Cores do chip de trust. Semáforo, e a ordem importa: verde só para CERTIFIED.
CORES_TRUST = {
    "CERTIFIED": ("#0f7b3f", "#e7f5ec", "🟢"),
    "LIMITED":   ("#8a5a00", "#fdf3e0", "🟡"),
    "BLOCKED":   ("#9b1c1c", "#fdeaea", "🔴"),
    "INDETERMINADO": ("#4b5563", "#f1f2f4", "⚪"),
}

# Situação do resultado -> como a faixa se apresenta. Recusa e supressão são
# **resultados**, e por isso nenhuma delas usa a cor de erro técnico.
FAIXAS = {
    "AMBIGUIDADE":      ("smart_refusal",    "#8a5a00", "#fdf3e0"),
    "RECUSA_GOVERNADA": ("recusa_governada", "#8a5a00", "#fdf3e0"),
    "SUPRESSAO":        ("supressao",        "#1e40af", "#eaf0fd"),
}
PARCIAIS = ("LIMITE_ITERACOES", "LIMITE_CHAMADAS", "TIMEOUT", "REPETICAO")


# --------------------------------------------------------------------------- #
# Formatação
# --------------------------------------------------------------------------- #
def valor(v, unidade: str | None, idioma: str) -> str:
    """Número do envelope, na notação do idioma. Sem conversão de unidade."""
    if v is None:
        return "—"
    if unidade == "taxa":
        texto = f"{v * 100:.2f}%"
        return texto.replace(".", ",") if idioma == PT else texto
    if isinstance(v, float) and not v.is_integer():
        texto = f"{v:,.2f}"
    else:
        texto = f"{int(v):,}"
    return (texto.replace(",", "·").replace(".", ",").replace("·", ".")
            if idioma == PT else texto)


def delta(v, unidade: str | None, idioma: str) -> str:
    if v is None:
        return "—"
    sinal = "+" if v > 0 else ""
    return sinal + valor(v, unidade, idioma)


def periodo(p: dict | None) -> str:
    """Período como o envelope o declara. Nunca reinterpretado."""
    if not p:
        return "—"
    ini, fim = p.get("from"), p.get("to")
    return str(ini) if not fim or fim == ini else f"{ini} → {fim}"


def escopo(envelope: dict, idioma: str) -> str:
    """Os filtros pedidos, com os membros governados **sem tradução**."""
    aplicados = (envelope.get("data") or {}).get("filters_applied") or {}
    pedidos = aplicados.get("requested_by_caller") or []
    partes = []
    for f in pedidos:
        valores = f.get("in") or []
        partes.append(", ".join(str(v) for v in valores))
    return " · ".join(partes) if partes else t("toda_a_empresa", idioma)


def chip_trust(trust: dict | None) -> tuple[str, str, str, str]:
    """(status, cor, fundo, emoji). O status vem decidido do envelope."""
    status = (trust or {}).get("status") or "INDETERMINADO"
    cor, fundo, emoji = CORES_TRUST.get(status, CORES_TRUST["INDETERMINADO"])
    return status, cor, fundo, emoji


def direcao(d: str | None, idioma: str) -> str:
    return t(d, idioma) if d else "—"


# --------------------------------------------------------------------------- #
# Leitura da execução
# --------------------------------------------------------------------------- #
def envelope_final(execucao) -> dict:
    """O último envelope com resposta. Vazio quando o loop parou antes."""
    uteis = [o.envelope for o in execucao.state.observacoes
             if o.envelope.get("outcome") in ("ANSWER", "REFUSAL", "SUPPRESSED")]
    return uteis[-1] if uteis else {}


def forma(execucao) -> str:
    """Qual bloco desenhar: VALOR, COMPARACAO, RANKING ou TEXTO.

    Decidido pela **ferramenta que respondeu**, não por adivinhação sobre a
    pergunta. Se o agente chamou `compare_kpi`, a tela mostra comparação.
    """
    env = envelope_final(execucao)
    if env.get("outcome") != "ANSWER":
        return "TEXTO"
    dados = env.get("data") or {}
    if "rows" in dados:
        return "RANKING"
    if "baseline" in dados and "current" in dados:
        return "COMPARACAO"
    if "value" in dados:
        return "VALOR"
    return "TEXTO"


def faixa(execucao) -> tuple[str, str, str] | None:
    """Rótulo e cores da situação, quando não é uma resposta factual limpa."""
    parada = execucao.stop_reason
    if parada in FAIXAS:
        chave, cor, fundo = FAIXAS[parada]
        return chave, cor, fundo
    if parada in PARCIAIS:
        return "parcial", "#8a5a00", "#fdf3e0"
    return None


def ambiguidades(execucao) -> list[dict]:
    """O que o `RESOLVE` não resolveu, com as opções que ele mesmo ofereceu."""
    intent = execucao.state.intent
    if not intent or not getattr(intent, "ambiguity", None):
        return []
    return [{"campo": a.campo, "motivo": a.motivo, "opcoes": list(a.opcoes)}
            for a in intent.ambiguity]


def linhas_do_ranking(envelope: dict, idioma: str) -> tuple[list[dict], int, int]:
    """Tabela do breakdown, linha a linha, exatamente como vieram.

    Linha suprimida entra **na tabela**, com o valor vazio e o motivo à vista.
    Escondê-la faria a tabela parecer completa; preenchê-la seria reconstruir o
    que a supressão existe para impedir. Nem uma coisa nem outra.
    """
    dados = envelope.get("data") or {}
    linhas, suprimidas = [], 0
    for r in dados.get("rows") or []:
        chaves = " · ".join(str(v) for v in (r.get("keys") or {}).values())
        oculta = bool(r.get("suppressed"))
        suprimidas += int(oculta)
        linhas.append({
            "_dim": chaves,
            t("col_valor", idioma): ("—" if oculta else
                                     valor(r.get("value"), dados.get("unit")
                                           or (envelope.get("kpi") or {}).get("unit")
                                           or "taxa", idioma)),
            # String sempre: uma coluna que mistura inteiro e travessão não
            # serializa para Arrow, e o Streamlit "conserta" o tipo sozinho.
            t("col_populacao", idioma): ("—" if oculta
                                         else str(r.get("population") or "—")),
            t("col_situacao", idioma): (r.get("suppression_reason")
                                        or t("suprimido", idioma)) if oculta
                                       else t("publicado", idioma),
        })
    return linhas, suprimidas, len(linhas)


def regra_e_porque(item) -> str:
    """Exclusão ou filtro fixo do contrato, como o contrato os declara.

    O contrato não guarda uma frase: guarda `{o_que, porque}` ou
    `{regra, porque}`, porque uma exclusão sem justificativa registrada é uma
    decisão que ninguém consegue auditar depois. A UI mostra os dois campos, e
    não resume um deles.
    """
    if not isinstance(item, dict):
        return str(item)
    o_que = item.get("o_que") or item.get("regra") or ""
    porque = item.get("porque")
    return f"**{o_que}** — {porque}" if porque else str(o_que)


def interpretacao(execucao) -> dict:
    """Metadados do interpretador, quando ele declara algum."""
    return dict(getattr(execucao, "interpretacao", None) or {})


def usou_llm(execucao) -> bool:
    return interpretacao(execucao).get("interpreter_used") == "LLM"
