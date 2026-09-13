"""PeopleLens AI — interface de demonstração.

    Governed People Analytics, powered by AI

Uma tela, uma pergunta, uma chamada a `harness.run`. Tudo que aparece veio do
envelope governado: valor, período, escopo, confiança, nível de resposta,
ressalvas, supressão. A UI escolhe o rótulo e o layout, e nada mais.

Rodar:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui import apresentacao as ap                          # noqa: E402
from ui import sessao                                      # noqa: E402
from ui.textos import EN, EXEMPLOS, IDIOMAS, PT, t         # noqa: E402

st.set_page_config(page_title="PeopleLens AI",
                   page_icon="◧", layout="centered")

CSS = """
<style>
  .block-container {max-width: 860px; padding-top: 3rem;}
  h1, h2, h3 {letter-spacing: -0.02em;}
  .pl-marca {font-size: 2.1rem; font-weight: 700; letter-spacing: -0.03em;
             margin-bottom: .1rem;}
  .pl-sub {color: #6b7280; font-size: 1rem; margin-bottom: 2rem;}
  .pl-valor {font-size: 3.6rem; font-weight: 700; line-height: 1;
             letter-spacing: -0.04em; margin: .2rem 0 .1rem 0;}
  .pl-kpi {font-size: 1.15rem; font-weight: 600; color: #111827;}
  .pl-escopo {color: #6b7280; font-size: .95rem; margin-bottom: 1rem;}
  .pl-chip {display: inline-block; padding: .22rem .7rem; border-radius: 999px;
            font-size: .82rem; font-weight: 600; margin-right: .4rem;}
  .pl-faixa {padding: .9rem 1.1rem; border-radius: 10px; font-weight: 600;
             margin: .4rem 0 1rem 0;}
  .pl-regua {height: 1px; background: #e5e7eb; margin: 2rem 0 1.4rem 0;}
  .pl-rot {text-transform: uppercase; font-size: .72rem; letter-spacing: .08em;
           color: #9ca3af; font-weight: 600; margin-bottom: .15rem;}
  .pl-val {font-size: 1.05rem; font-weight: 600; color: #111827;}
  .pl-rodape {color: #9ca3af; font-size: .8rem; margin-top: 3rem;}
  .stButton button {border-radius: 8px;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def chip(texto: str, cor: str, fundo: str) -> str:
    return (f'<span class="pl-chip" style="color:{cor};background:{fundo}">'
            f'{texto}</span>')


def rotulo(nome: str, valor: str) -> None:
    st.markdown(f'<div class="pl-rot">{nome}</div>'
                f'<div class="pl-val">{valor}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Cabeçalho
# --------------------------------------------------------------------------- #
topo, sel = st.columns([4, 1])
with topo:
    st.markdown('<div class="pl-marca">PeopleLens AI</div>',
                unsafe_allow_html=True)
with sel:
    idioma = st.selectbox(t("idioma", PT) + " / " + t("idioma", EN),
                          IDIOMAS, label_visibility="collapsed")
st.markdown(f'<div class="pl-sub">{t("subtitulo", idioma)}</div>',
            unsafe_allow_html=True)

if not sessao.tem_credencial():
    st.info(t("sem_credencial", idioma), icon="ℹ️")

# --------------------------------------------------------------------------- #
# Pergunta
# --------------------------------------------------------------------------- #
if "pergunta" not in st.session_state:
    st.session_state.pergunta = ""

st.markdown(f"**{t('pergunta', idioma)}**")
pergunta = st.text_input("q", key="pergunta", label_visibility="collapsed",
                         placeholder=t("placeholder", idioma))

st.caption(t("exemplos", idioma))
for linha in (EXEMPLOS[idioma][:2], EXEMPLOS[idioma][2:]):
    for col, exemplo in zip(st.columns(len(linha)), linha):
        if col.button(exemplo, key=exemplo, width="stretch"):
            st.session_state.pergunta = exemplo
            st.rerun()

if not pergunta:
    st.markdown(f'<div class="pl-rodape">{t("rodape", idioma)}</div>',
                unsafe_allow_html=True)
    st.stop()

# --------------------------------------------------------------------------- #
# Execução: uma chamada, e só
# --------------------------------------------------------------------------- #
with st.spinner(t("pensando", idioma)):
    execucao = sessao.perguntar(pergunta)

env = ap.envelope_final(execucao)
dados = env.get("data") or {}
kpi_id = (env.get("kpi") or {}).get("id") or getattr(
    execucao.state.intent, "kpi", None)
unidade = dados.get("unit") or "taxa"

st.markdown('<div class="pl-regua"></div>', unsafe_allow_html=True)

# Faixa de situação, quando não é resposta factual limpa.
situacao = ap.faixa(execucao)
if situacao:
    chave, cor, fundo = situacao
    st.markdown(f'<div class="pl-faixa" style="color:{cor};background:{fundo}">'
                f'{t(chave, idioma)}</div>', unsafe_allow_html=True)

forma = ap.forma(execucao)

# --------------------------------------------------------------------------- #
# VALOR
# --------------------------------------------------------------------------- #
if forma == "VALOR":
    st.markdown(f'<div class="pl-valor">'
                f'{ap.valor(dados.get("value"), unidade, idioma)}</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="pl-kpi">{kpi_id or ""}</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="pl-escopo">{ap.escopo(env, idioma)} · '
                f'{ap.periodo(dados.get("period"))}</div>',
                unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# COMPARAÇÃO
# --------------------------------------------------------------------------- #
elif forma == "COMPARACAO":
    atual, base = dados.get("current") or {}, dados.get("baseline") or {}
    st.markdown(f'<div class="pl-valor">'
                f'{ap.delta(dados.get("delta"), unidade, idioma)}</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="pl-kpi">{kpi_id or ""} · '
                f'{ap.direcao(dados.get("direction"), idioma)}</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="pl-escopo">{ap.escopo(env, idioma)}</div>',
                unsafe_allow_html=True)

    a, b, c = st.columns(3)
    with a:
        rotulo(t("periodo_atual", idioma),
               f'{ap.valor(atual.get("value"), unidade, idioma)} · '
               f'{ap.periodo(atual.get("period"))}')
    with b:
        rotulo(t("periodo_base", idioma),
               f'{ap.valor(base.get("value"), unidade, idioma)} · '
               f'{ap.periodo(base.get("period"))}')
    with c:
        rotulo(t("variacao_relativa", idioma),
               ap.delta(dados.get("delta_relative"), "taxa", idioma))
    st.caption(t("nota_associacao", idioma))

# --------------------------------------------------------------------------- #
# RANKING
# --------------------------------------------------------------------------- #
elif forma == "RANKING":
    linhas, suprimidas, total = ap.linhas_do_ranking(env, idioma)
    st.markdown(f'<div class="pl-kpi">{t("ranking", idioma)} · {kpi_id or ""}</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="pl-escopo">{ap.periodo(dados.get("period"))} · '
                f'{", ".join(dados.get("dimensions") or [])}</div>',
                unsafe_allow_html=True)
    if suprimidas:
        st.warning(t("linhas_suprimidas", idioma, n=suprimidas, total=total)
                   + " · " + t("suprimido_aviso", idioma), icon="🔒")
    st.dataframe(
        [{"": l["_dim"], **{k: v for k, v in l.items() if k != "_dim"}}
         for l in linhas],
        width="stretch", hide_index=True)

# --------------------------------------------------------------------------- #
# Ambiguidade e recusa: resultado, não erro
# --------------------------------------------------------------------------- #
if execucao.stop_reason in ("AMBIGUIDADE", "RECUSA_GOVERNADA", "SUPRESSAO"):
    ambiguidades = ap.ambiguidades(execucao)
    if ambiguidades:
        st.markdown(f"**{t('o_que_falta', idioma)}**")
        for a in ambiguidades:
            st.markdown(f"- `{a['campo']}` — {a['motivo']}")
            if a["opcoes"]:
                st.caption(t("opcoes_validas", idioma) + ": "
                           + ", ".join(a["opcoes"][:12]))
    if env.get("refusal"):
        r = env["refusal"]
        st.markdown(f"- `{r.get('classe')}` — {r.get('mensagem')}")
        if r.get("o_que_resolveria"):
            st.caption(r["o_que_resolveria"])
    st.caption(t("sem_reformular", idioma))

# --------------------------------------------------------------------------- #
# Confiança, nível e ressalvas
# --------------------------------------------------------------------------- #
if env.get("trust") or env.get("response_level"):
    status, cor, fundo, emoji = ap.chip_trust(env.get("trust"))
    nivel = env.get("response_level") or {}
    linha = chip(f"{emoji} {status}", cor, fundo)
    if nivel.get("granted"):
        linha += chip(f'{nivel["granted"]} · {t("teto_de", idioma)} '
                      f'{nivel.get("ceiling_from", "")}', "#374151", "#f3f4f6")
    st.markdown(linha, unsafe_allow_html=True)

if env.get("caveats"):
    with st.expander(t("ressalvas", idioma) + f' ({len(env["caveats"])})'):
        for c in env["caveats"]:
            st.markdown(f"- {c}")

# Em PT-BR a narrativa do agente é a resposta principal. Em EN-US ela desce
# para os detalhes, porque o `render.py` do core escreve em português e a UI
# não reescreve resposta de camada governada.
if idioma == PT:
    st.markdown('<div class="pl-regua"></div>', unsafe_allow_html=True)
    st.markdown(f"**{t('resposta_agente', idioma)}**")
    st.write(execucao.resposta.texto)

# --------------------------------------------------------------------------- #
# Como foi calculado
# --------------------------------------------------------------------------- #
if kpi_id and forma in ("VALOR", "COMPARACAO", "RANKING"):
    with st.expander(t("como_calculado", idioma)):
        d = sessao.definicao(kpi_id)
        if d:
            rotulo(t("definicao", idioma), d.get("business_definition") or "—")
            rotulo(t("formula", idioma), d.get("formula_plain") or "—")
            a, b = st.columns(2)
            with a:
                rotulo(t("populacao", idioma), str(d.get("population") or "—"))
                rotulo(t("minimo_n", idioma), str(d.get("minimum_n") or "—"))
            with b:
                gov = d.get("governance") or {}
                rotulo(t("status", idioma), str(gov.get("status") or "—"))
                rotulo(t("owner", idioma), str(gov.get("owner") or "—"))
            if d.get("exclusions"):
                st.markdown(f'<div class="pl-rot">{t("exclusoes", idioma)}</div>',
                            unsafe_allow_html=True)
                for item in d["exclusions"]:
                    st.markdown(f"- {ap.regra_e_porque(item)}")
            if d.get("fixed_filters"):
                st.markdown(f'<div class="pl-rot">'
                            f'{t("filtros_contrato", idioma)}</div>',
                            unsafe_allow_html=True)
                for item in d["fixed_filters"]:
                    st.markdown(f"- {ap.regra_e_porque(item)}")
        cobertura = dados.get("coverage") or {}
        if cobertura.get("verificacao") is not None:
            rotulo(t("verificacao", idioma),
                   f'{cobertura["verificacao"] * 100:.0f}%')
        st.markdown(f"**{t('linhagem', idioma)}**")
        lin = sessao.linhagem(kpi_id, env.get("trace_id"))
        degraus = (lin or {}).get("degraus")
        if degraus:
            for passo in degraus:
                st.markdown(f"- {json.dumps(passo, ensure_ascii=False)}")
        else:
            st.caption(t("sem_linhagem", idioma))

# --------------------------------------------------------------------------- #
# Detalhes da execução
# --------------------------------------------------------------------------- #
with st.expander(t("detalhes", idioma)):
    interp = ap.interpretacao(execucao)
    a, b = st.columns(2)
    with a:
        rotulo(t("interpretador", idioma),
               interp.get("interpreter_used") or "RuleInterpreter")
        rotulo(t("stop_reason", idioma), str(execucao.stop_reason))
        rotulo(t("chamadas", idioma), str(execucao.state.chamadas_efetivas))
    with b:
        rotulo(t("modelo", idioma),
               f'{interp.get("provider") or "—"} / {interp.get("model") or "—"}')
        rotulo(t("duracao", idioma), f"{execucao.duracao_ms} ms")
        rotulo("trace_id", ", ".join(execucao.resposta.trace_ids) or "—")
    if interp.get("orcamento"):
        o = interp["orcamento"]
        rotulo(t("orcamento", idioma),
               f'{o.get("usadas")}/{o.get("teto")} · {o.get("origem")}')
    if interp.get("fallback"):
        st.warning(f'{t("fallback_ativo", idioma)}: '
                   f'{interp.get("fallback_reason")}', icon="⚠️")

    if execucao.state.plano:
        st.markdown(f"**{t('plano', idioma)}**")
        st.json(execucao.state.plano.to_dict(), expanded=False)
    if execucao.state.intent:
        st.markdown(f"**{t('intent', idioma)}**")
        st.json(execucao.state.intent.to_dict(), expanded=False)

    if idioma == EN:
        st.markdown(f"**{t('texto_original', idioma)}**")
        st.write(execucao.resposta.texto)
        st.caption(t("nota_idioma", idioma))

st.markdown(f'<div class="pl-rodape">{t("rodape", idioma)}</div>',
            unsafe_allow_html=True)
