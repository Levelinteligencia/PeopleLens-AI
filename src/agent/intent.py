"""Intenção estruturada e o passo RESOLVE (SPEC Partes VI e V; decisão A-01).

`UNDERSTAND` produz uma intenção **bruta**: o que a pessoa parece querer.
`RESOLVE` confronta essa intenção com o catálogo e o vocabulário governados e
devolve uma de três coisas — resolvida, ambígua, ou inválida.

O passo existe separado porque é o mais barato e o que mais evita erro: ele não
custa uma chamada ao MCP e mata a classe inteira de "respondi com precisão a
pergunta errada". A pergunta-vitrine do projeto morre aqui, três vezes:

    "turnover de Tecnologia no Q2 de 2026"
        grain      turnover_rate e apurado por ANO
        termo      nao existe departamento "Tecnologia"
        (e mesmo corrigido, o recorte cai abaixo do n minimo)

Decisão A-01: ambiguidade vira **pergunta de volta**, com as opções válidas, e
**nenhuma chamada de valor** acontece enquanto ela existir. Escolher por
similaridade é proibido (ADR-0020): um termo mapeado errado é invisível, um
termo não mapeado é visível.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Tipos de pergunta que o agente reconhece. `FORA_DE_ESCOPO` é o caminho de
# conhecimento (RAG), que não existe nesta versão.
VALOR = "VALOR"
COMPARACAO = "COMPARACAO"
RANKING = "RANKING"
DEFINICAO = "DEFINICAO"
CONFIANCA = "CONFIANCA"
LINHAGEM = "LINHAGEM"
CAUSAL = "CAUSAL"
FORA_DE_ESCOPO = "FORA_DE_ESCOPO"

TIPOS = (VALOR, COMPARACAO, RANKING, DEFINICAO, CONFIANCA, LINHAGEM, CAUSAL,
         FORA_DE_ESCOPO)

# Tipos que consultam valor. São os únicos bloqueados por ambiguidade (A-01).
TIPOS_QUANTITATIVOS = (VALOR, COMPARACAO, RANKING, CAUSAL)


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


@dataclass
class Ambiguity:
    campo: str
    motivo: str
    opcoes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"campo": self.campo, "motivo": self.motivo,
                "opcoes": list(self.opcoes)}


@dataclass
class Intent:
    """A intenção, bruta depois de UNDERSTAND e resolvida depois de RESOLVE."""
    question_type: str
    kpi_candidates: list[str] = field(default_factory=list)
    period: dict | None = None
    filters: list[dict] = field(default_factory=list)     # {dimension, terms}
    dimensions: list[str] = field(default_factory=list)
    requested_level: str = "FACT"
    compare_to: str | None = None
    ambiguity: list[Ambiguity] = field(default_factory=list)
    premissa: str | None = None          # ex.: a pergunta afirma que "aumentou"
    referencia_anterior: bool = False    # "compare com...", "esse número"

    @property
    def resolvida(self) -> bool:
        return not self.ambiguity and len(self.kpi_candidates) == 1

    @property
    def kpi(self) -> str | None:
        return self.kpi_candidates[0] if len(self.kpi_candidates) == 1 else None

    @property
    def quantitativa(self) -> bool:
        return self.question_type in TIPOS_QUANTITATIVOS

    def to_dict(self) -> dict:
        return {
            "question_type": self.question_type,
            "kpi_candidates": list(self.kpi_candidates),
            "period": self.period,
            "filters": [dict(f) for f in self.filters],
            "dimensions": list(self.dimensions),
            "requested_level": self.requested_level,
            "compare_to": self.compare_to,
            "ambiguity": [a.to_dict() for a in self.ambiguity],
            "premissa": self.premissa,
        }


# --------------------------------------------------------------------------- #
# RESOLVE
# --------------------------------------------------------------------------- #
def resolve(intent: Intent, contexto) -> Intent:
    """Confronta a intenção com o catálogo e o vocabulário fechados.

    Não chama o MCP. Não adivinha. Devolve a mesma intenção com `ambiguity`
    preenchida quando algo não resolve, e é isso que impede a chamada de valor.
    """
    amb: list[Ambiguity] = []

    # 1. KPI ------------------------------------------------------------------
    if not intent.kpi_candidates:
        if intent.quantitativa or intent.question_type in (DEFINICAO, CONFIANCA):
            amb.append(Ambiguity(
                "kpi",
                "não identifiquei a qual indicador a pergunta se refere",
                contexto.kpis_que_respondem()))
    elif len(intent.kpi_candidates) > 1:
        amb.append(Ambiguity(
            "kpi",
            "a pergunta pode se referir a mais de um indicador, e escolher um "
            "por semelhança seria inventar a definição",
            list(intent.kpi_candidates)))

    kpi = contexto.kpi(intent.kpi) if intent.kpi else None

    # 2. Período --------------------------------------------------------------
    # 2.1 Termo relativo: resolvido aqui, contra a cobertura do KPI (P-02).
    # O interpretador **marca**; quem materializa é este passo, que conhece a
    # cobertura. Quando a materialização não é inequívoca, o resultado é
    # ambiguidade, e nunca um período escolhido por aproximação.
    relativo_pendente = False
    if kpi is not None and intent.period and intent.period.get("relativo"):
        materializado, motivo = _materializar_relativo(
            intent.period, kpi, contexto)
        if materializado:
            intent.period = materializado
        else:
            relativo_pendente = True
            amb.append(Ambiguity("period", motivo,
                                 contexto.periodos_sugeridos(kpi["kpi_id"])))

    # Pergunta de valor sem período não é "o período mais recente": é uma
    # pergunta incompleta, e escolher por conta própria seria decidir em silêncio.
    if (kpi is not None and intent.quantitativa and not intent.period
            and not relativo_pendente):
        amb.append(Ambiguity(
            "period",
            "a pergunta não diz de que período",
            contexto.periodos_sugeridos(kpi["kpi_id"])))
    if kpi is not None and intent.period and not relativo_pendente:
        pedido = intent.period.get("grain")
        aceitos = contexto.grains_aceitos(kpi["kpi_id"])
        if pedido and aceitos and pedido not in aceitos:
            amb.append(Ambiguity(
                "period.grain",
                f"{kpi['kpi_id']} é apurado por {kpi['period_grain']}; "
                f"não existe versão por {pedido}",
                contexto.periodos_sugeridos(kpi["kpi_id"])))
        elif intent.period.get("from"):
            fora = contexto.fora_da_cobertura(kpi["kpi_id"], intent.period)
            if fora:
                amb.append(Ambiguity(
                    "period",
                    f"{kpi['kpi_id']} tem dado de {fora[0]} a {fora[1]}; "
                    "o período pedido está fora dessa janela",
                    contexto.periodos_sugeridos(kpi["kpi_id"])))

    # 3. Termos de filtro -----------------------------------------------------
    # Termo fora do vocabulário NUNCA vira o termo mais parecido (A-02).
    for f in intent.filters:
        dim = f.get("dimension")
        if kpi is not None and dim not in (kpi.get("allowed_dimensions") or []):
            amb.append(Ambiguity(
                f"filters.{dim}",
                f"{kpi['kpi_id']} não responde por {dim}",
                list(kpi.get("allowed_dimensions") or [])))
            continue
        desconhecidos = [t for t in f.get("terms") or []
                         if not contexto.termo_valido(dim, t)]
        for termo in desconhecidos:
            amb.append(Ambiguity(
                f"filters.{dim}",
                f"não existe {dim} chamado {termo!r} no vocabulário governado",
                contexto.termos_de(dim)))

    # 4. Dimensões de quebra --------------------------------------------------
    for d in intent.dimensions:
        if kpi is not None and d not in (kpi.get("allowed_dimensions") or []):
            amb.append(Ambiguity(
                f"dimensions.{d}",
                f"{kpi['kpi_id']} não responde por {d}",
                list(kpi.get("allowed_dimensions") or [])))

    intent.ambiguity = amb
    return intent


# --------------------------------------------------------------------------- #
# Período relativo (P-02, D-L1)
# --------------------------------------------------------------------------- #
def _materializar_relativo(period: dict, kpi: dict,
                           contexto) -> tuple[dict | None, str]:
    """Termo relativo -> período absoluto, ou o motivo de não dar.

    Três condições, todas necessárias, e **nenhuma delas é o relógio do
    sistema**:

    1. o termo está **declarado** no vocabulário governado;
    2. a resolução declarada é `coverage_end`, e o KPI responde no grain que a
       declaração fixa;
    3. o fim da cobertura do KPI é expressável **exatamente** naquele grain.

    A terceira é a que faz o trabalho silencioso. Um KPI carregado até 2026-06
    não tem "último ano" inequívoco: 2026 está pela metade, e responder 2026
    entregaria meio ano apresentado como ano inteiro. Nesse caso a resposta
    certa é ambiguidade, com os períodos válidos, e não o ano mais próximo.

    Falhando qualquer uma, devolve `(None, motivo)`. Não existe caminho que
    devolva a série inteira, um período aproximado, ou um período fora da
    cobertura: o único valor que sai daqui é o fim da cobertura declarada.
    """
    # Import adiado: `context` importa `slug` daqui, e o padrão de período é
    # declarado lá. Redigitá-lo criaria duas verdades sobre o mesmo formato.
    from .context import PADRAO_PERIODO

    termo = period.get("relativo")
    declarado = contexto.termo_relativo(termo)
    if not declarado:
        return None, (f"não existe termo relativo declarado equivalente a "
                      f"{termo!r} no vocabulário governado; diga o período")

    if declarado.get("resolves_to") != "coverage_end":
        return None, (f"o termo {termo!r} não tem resolução declarada contra a "
                      "cobertura do indicador")

    grain = declarado.get("grain")
    aceitos = contexto.grains_aceitos(kpi["kpi_id"])
    if aceitos and grain not in aceitos:
        return None, (f"{kpi['kpi_id']} é apurado por {kpi.get('period_grain')}; "
                      f"não existe versão por {grain}")

    fim = str(((kpi.get("period_coverage") or {}).get("to")) or "")
    padrao = PADRAO_PERIODO.get(grain or "")
    if not fim or padrao is None or not padrao.match(fim):
        return None, (f"a cobertura de {kpi['kpi_id']} termina em {fim or '?'}, "
                      f"que não é um período de {grain} fechado; "
                      "diga o período")

    return {"grain": grain, "from": fim, "to": fim}, ""
