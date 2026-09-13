"""Avaliação dos interpretadores: casos A–M, em PT-BR e EN-US (SPEC Parte XV).

Estrutura para rodar **o mesmo conjunto** contra qualquer implementação do
`Interpreter`. O `RuleInterpreter` é a linha de base, e não um adversário: o LLM
precisa **igualar** o que a regra já acerta antes de substituí-la, e onde a
regra falha o resultado fica registrado como falha, não como desculpa.

**Nenhum score é inventado.** `avaliar` devolve o que de fato aconteceu, caso a
caso, com a verificação que falhou nomeada. Um caso que não pôde ser executado
sai como `NAO_EXECUTADO`, nunca como aprovado.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PT = "pt-BR"
EN = "en-US"


@dataclass
class Caso:
    id: str
    pergunta: str
    idioma: str
    espera: dict = field(default_factory=dict)
    par: str | None = None          # caso equivalente no outro idioma


# Os treze casos da avaliação, mais os equivalentes em inglês. As chaves de
# `espera` são verificações, e cada uma é conferida por `_conferir`.
CASOS: tuple[Caso, ...] = (
    Caso("A", "Qual foi o turnover em 2025?", PT,
         {"question_type": "VALOR", "kpi": ["turnover_rate"],
          "periodo": {"grain": "ano", "from": "2025"}, "filtros": {}}),
    Caso("B", "Qual foi o turnover de Customer Service em 2025?", PT,
         {"question_type": "VALOR", "kpi": ["turnover_rate"],
          "periodo": {"grain": "ano", "from": "2025"},
          "filtros": {"departamento": "Customer Service"},
          "sem_dimensao": ["business_unit"]},
         par="B-EN"),
    Caso("C", "Compare o turnover de 2024 e 2025.", PT,
         {"question_type": "COMPARACAO", "kpi": ["turnover_rate"],
          "compare_to_preenchido": True}),
    Caso("D", "Qual área teve maior turnover em 2024?", PT,
         {"question_type": "RANKING", "kpi": ["turnover_rate"]},
         par="D-EN"),
    Caso("E", "Por que o turnover caiu em 2025?", PT,
         {"question_type": "CAUSAL", "premissa": "QUEDA"},
         par="E-EN"),
    Caso("F", "O trabalho remoto causou o aumento do turnover?", PT,
         {"question_type": "CAUSAL"},
         par="F-EN"),
    Caso("G", "Qual foi o turnover de Tecnologia no segundo trimestre de 2026?", PT,
         {"question_type": "VALOR",
          "periodo": {"grain": "trimestre", "from": "2026-Q2"},
          "filtros": {"departamento": "Tecnologia"},
          "termo_nao_traduzido": ("departamento", "Engineering")}),
    Caso("H", "Qual a definição de turnover?", PT,
         {"question_type": "DEFINICAO", "kpi": ["turnover_rate"]}),
    Caso("I", "Mostre a linhagem desse indicador.", PT,
         {"question_type": "LINHAGEM"}),
    Caso("J", "Qual foi a taxa de promoção?", PT,
         {"kpi": ["promotion_rate"]}),
    Caso("K", "Qual foi o turnover de Data & Analytics em 2025?", PT,
         {"question_type": "VALOR",
          "filtros": {"departamento": "Data & Analytics"}}),
    Caso("L", "Qual foi o turnover de Customer Service na Business Unit "
              "Customer em 2025?", PT,
         {"question_type": "VALOR",
          "filtros": {"departamento": "Customer Service",
                      "business_unit": "Customer"}}),
    Caso("M", "Qual foi o turnover de Customer Service?", PT,
         {"question_type": "VALOR", "periodo_ausente": True,
          "filtros": {"departamento": "Customer Service"}}),

    Caso("B-EN", "What was the turnover rate for Customer Service in 2025?", EN,
         {"question_type": "VALOR", "kpi": ["turnover_rate"],
          "periodo": {"grain": "ano", "from": "2025"},
          "filtros": {"departamento": "Customer Service"},
          "sem_dimensao": ["business_unit"]},
         par="B"),
    Caso("D-EN", "Which department had the highest turnover in 2024?", EN,
         {"question_type": "RANKING", "kpi": ["turnover_rate"]},
         par="D"),
    Caso("E-EN", "Why did turnover decrease in 2025?", EN,
         {"question_type": "CAUSAL", "premissa": "QUEDA"},
         par="E"),
    Caso("F-EN", "The remote work policy caused turnover to increase.", EN,
         {"question_type": "CAUSAL"},
         par="F"),
)

POR_ID = {c.id: c for c in CASOS}


# --------------------------------------------------------------------------- #
# Verificações
# --------------------------------------------------------------------------- #
def _filtros(intent) -> dict:
    return {f["dimension"]: (f.get("terms") or [None])[0] for f in intent.filters}


def _conferir(intent, espera: dict) -> list[str]:
    """Devolve a lista de verificações que falharam. Vazia significa aprovado."""
    falhas = []
    f = _filtros(intent)

    if "question_type" in espera and intent.question_type != espera["question_type"]:
        falhas.append(f"question_type={intent.question_type} "
                      f"(esperado {espera['question_type']})")

    if "kpi" in espera and sorted(intent.kpi_candidates) != sorted(espera["kpi"]):
        falhas.append(f"kpi_candidates={intent.kpi_candidates} "
                      f"(esperado {espera['kpi']})")

    if "periodo" in espera:
        p = intent.period or {}
        alvo = espera["periodo"]
        if p.get("grain") != alvo["grain"] or p.get("from") != alvo["from"]:
            falhas.append(f"period={intent.period} (esperado {alvo})")

    if espera.get("periodo_ausente") and intent.period:
        falhas.append(f"period={intent.period} (esperado ausente)")

    if "filtros" in espera and f != espera["filtros"]:
        falhas.append(f"filtros={f} (esperado {espera['filtros']})")

    for dim in espera.get("sem_dimensao", ()):
        if dim in f:
            falhas.append(f"dimensão {dim} inferida, e não foi dita")

    if "premissa" in espera and intent.premissa != espera["premissa"]:
        falhas.append(f"premissa={intent.premissa} "
                      f"(esperado {espera['premissa']})")

    if espera.get("compare_to_preenchido") and not intent.compare_to:
        falhas.append("compare_to vazio")

    if "termo_nao_traduzido" in espera:
        dim, proibido = espera["termo_nao_traduzido"]
        if f.get(dim) == proibido:
            falhas.append(f"{dim} traduzido para {proibido!r} por semelhança")

    return falhas


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #
def avaliar(interpreter, contexto, casos=CASOS) -> list[dict]:
    """Roda os casos contra um interpretador. Não inventa resultado."""
    saida = []
    for caso in casos:
        linha = {"id": caso.id, "idioma": caso.idioma}
        try:
            intent = interpreter.understand(caso.pergunta, contexto)
        except Exception as e:                                # pragma: no cover
            linha.update(resultado="NAO_EXECUTADO", falhas=[type(e).__name__])
            saida.append(linha)
            continue
        falhas = _conferir(intent, caso.espera)
        linha.update(resultado="PASSOU" if not falhas else "FALHOU",
                     falhas=falhas,
                     interpretador=getattr(
                         getattr(interpreter, "registro", None),
                         "interpreter_used", "RULE"))
        saida.append(linha)
    return saida


def equivalencias(interpreter, contexto) -> list[dict]:
    """PT e EN da mesma pergunta produzem o mesmo `Intent` semântico.

    O que se compara é o que a governança usa: tipo, KPI, período, filtros e
    quebras. Não se compara texto, e valor governado **não** é traduzido:
    "Customer Service" é "Customer Service" nos dois idiomas.
    """
    saida = []
    vistos = set()
    for caso in CASOS:
        if not caso.par or caso.id in vistos:
            continue
        outro = POR_ID[caso.par]
        vistos.update({caso.id, outro.id})
        a = interpreter.understand(caso.pergunta, contexto)
        b = interpreter.understand(outro.pergunta, contexto)
        difs = []
        if a.question_type != b.question_type:
            difs.append(f"question_type {a.question_type} != {b.question_type}")
        if sorted(a.kpi_candidates) != sorted(b.kpi_candidates):
            difs.append(f"kpi {a.kpi_candidates} != {b.kpi_candidates}")
        if (a.period or {}).get("from") != (b.period or {}).get("from"):
            difs.append(f"period {a.period} != {b.period}")
        if _filtros(a) != _filtros(b):
            difs.append(f"filtros {_filtros(a)} != {_filtros(b)}")
        saida.append({"par": f"{caso.id}/{outro.id}",
                      "resultado": "EQUIVALENTE" if not difs else "DIVERGENTE",
                      "diferencas": difs})
    return saida


def resumo(resultados: list[dict]) -> dict:
    """Contagem do que aconteceu. Sem nota, sem percentual ponderado."""
    contagem: dict[str, int] = {}
    for r in resultados:
        contagem[r["resultado"]] = contagem.get(r["resultado"], 0) + 1
    return {"total": len(resultados), "por_resultado": contagem,
            "falharam": [r["id"] for r in resultados if r["resultado"] != "PASSOU"]}
