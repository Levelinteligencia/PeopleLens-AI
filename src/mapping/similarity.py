"""Sugestao de candidato para valor sem mapeamento.

Sugerir nao e aplicar (principio 5). Ainda assim, a qualidade da sugestao
importa: uma fila de excecoes com sugestoes ruins e uma fila que ninguem
trabalha, e uma sugestao ruim aumenta o risco de alguem aprovar no automatico
so para se livrar dela.

Similaridade de caractere pura falha justamente nos padroes mais comuns em
cadastro de RH brasileiro:

| valor de origem | alvo | por que a similaridade falha |
|---|---|---|
| `CS` | Customer Service | duas letras contra dezesseis |
| `LOG` | Logistics | prefixo curto |
| `Regi.Oper.` | Regional Operations | truncamento por palavra |
| `People & Culture` | People | conjunto de tokens, nao sequencia |

Por isso a pontuacao combina quatro estrategias e fica com a melhor, guardando
qual delas venceu. Saber POR QUE um candidato foi sugerido e parte da
informacao que quem decide precisa.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

STOP = {"de", "da", "do", "e", "of", "and", "the", "&"}


def norm(v: str) -> str:
    s = unicodedata.normalize("NFKD", v or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", " ").replace("&", " ").split())


def tokens(v: str) -> list[str]:
    return [t for t in norm(v).split() if t and t not in STOP]


@dataclass(frozen=True)
class Candidate:
    value: str
    score: float
    method: str
    via: str = ""      # o texto que de fato casou: o apelido aprovado ou o proprio valor padrao

    def as_dict(self) -> dict:
        return {"candidate": self.value, "score": round(self.score, 3),
                "method": self.method, "via": self.via}


def _sequence(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def _acronym(a: str, b: str) -> float:
    """`CS` para Customer Service, `DHO` para Desenvolvimento Humano e Organizacional."""
    ta, tb = tokens(a), tokens(b)
    if len(ta) != 1 or len(tb) < 2:
        return 0.0
    sigla = ta[0]
    iniciais = "".join(t[0] for t in tb)
    if sigla == iniciais:
        return 0.97
    if len(sigla) >= 2 and iniciais.startswith(sigla):
        return 0.85
    return 0.0


def _prefix(a: str, b: str) -> float:
    """`LOG` para Logistics, `Stra.` para Strategy, `Eng` para Engineering."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    if len(ta) == 1 and len(tb) == 1:
        curto, longo = (ta[0], tb[0]) if len(ta[0]) <= len(tb[0]) else (tb[0], ta[0])
        if len(curto) >= 3 and longo.startswith(curto):
            return 0.90 if len(curto) >= 4 else 0.82
        return 0.0
    # truncamento palavra a palavra: Regi.Oper. para Regional Operations
    if len(ta) == len(tb):
        casam = sum(1 for x, y in zip(ta, tb) if len(x) >= 3 and y.startswith(x))
        if casam == len(ta):
            return 0.93
        if casam:
            return 0.55 + 0.2 * casam / len(ta)
    return 0.0


def _token_overlap(a: str, b: str) -> float:
    """`People & Culture` para People: conjunto de tokens, nao sequencia."""
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    if not inter:
        return 0.0
    jaccard = len(inter) / len(ta | tb)
    contido = 1.0 if (ta <= tb or tb <= ta) else 0.0
    return max(jaccard, 0.80 * contido)


SCORERS = (("sequencia", _sequence), ("sigla", _acronym),
           ("prefixo", _prefix), ("tokens", _token_overlap))


def score(source_value: str, target: str) -> Candidate:
    melhor = Candidate(target, 0.0, "nenhum", target)
    for nome, fn in SCORERS:
        s = fn(source_value, target)
        if s > melhor.score:
            melhor = Candidate(target, s, nome, target)
    return melhor


def rank(source_value: str, targets: dict[str, str], top: int = 3) -> list[Candidate]:
    """Ordena candidatos. `targets` mapeia chave de origem conhecida -> valor padrao.

    A pontuacao considera tanto a chave de origem quanto o valor padrao: `JUR`
    combina com `Juridico` (uma chave ja aprovada) e o resultado util e `Legal`
    (o valor padrao correspondente).

    `via` guarda qual dos dois casou. Sem isso, a proposta mostra
    `JUR -> Legal, 0,82 por prefixo` e quem revisa nao consegue conferir, porque
    `JUR` nao e prefixo de `Legal`: e prefixo de `JURIDICO`, um apelido ja
    aprovado. Esconder o intermediario transforma uma sugestao auditavel numa
    sugestao que so resta acreditar.
    """
    vistos: dict[str, Candidate] = {}
    for chave, padrao in targets.items():
        c = max(score(source_value, chave), score(source_value, padrao), key=lambda x: x.score)
        c = Candidate(padrao, c.score, c.method, c.via)
        anterior = vistos.get(padrao)
        if anterior is None or c.score > anterior.score:
            vistos[padrao] = c
    return sorted(vistos.values(), key=lambda c: -c.score)[:top]
