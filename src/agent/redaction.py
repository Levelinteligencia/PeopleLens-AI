"""A-04 — sanitização de PII antes de registrar a pergunta.

A pergunta original **pode** ser registrada, porque sem ela é muito difícil
descobrir por que o agente entendeu errado. Mas nunca sem proteção.

A inversão que faz este módulo funcionar: **o vocabulário governado é a
allowlist**. Em vez de tentar reconhecer nomes de pessoas — o que erra nos dois
sentidos —, preserva-se o que é sabidamente seguro (nome de KPI, país,
departamento, nível, business unit, termo declarado) e redige-se o resto do que
parece nome próprio.

    "turnover de Customer Service em 2025"   -> intacto
    "turnover da equipe da Ana Ribeiro"      -> "turnover da equipe da [NOME]"

Padrões estruturais — e-mail, telefone, CPF, CNPJ, sequência longa de dígitos,
arroba — saem sempre, estejam onde estiverem.

O que nunca é registrado, sanitizado ou não: dado pessoal descoberto durante a
execução, linha de resultado, valor individual. Isso não é sanitização; é não
gravar.

`run_id` e `trace_id` ficam íntegros: a rastreabilidade não depende do texto.
"""
from __future__ import annotations

import re

NOME = "[NOME]"
EMAIL = "[EMAIL]"
TELEFONE = "[TELEFONE]"
DOCUMENTO = "[DOCUMENTO]"
NUMERO = "[NUMERO]"
HANDLE = "[HANDLE]"

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_HANDLE = re.compile(r"(?<!\w)@[A-Za-z][\w.-]{2,}")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_TEL = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?\(?\d{2,3}\)?[\s-]?\d{4,5}[\s-]?\d{4}(?!\d)")
_DIGITOS = re.compile(r"(?<!\d)\d{7,}(?!\d)")

# Palavras que iniciam frase ou são conectivos, e não indicam nome próprio.
_PARADAS = {
    "qual", "quais", "quanto", "quantos", "quantas", "como", "onde", "quando",
    "por", "porque", "compare", "comparar", "mostre", "me", "de", "da", "do",
    "das", "dos", "em", "no", "na", "nos", "nas", "e", "o", "a", "os", "as",
    "foi", "for", "era", "esta", "está", "eh", "é", "que", "com", "para",
    "sobre", "trimestre", "semestre", "ano", "mes", "mês", "janeiro",
    "fevereiro", "março", "marco", "abril", "maio", "junho", "julho", "agosto",
    "setembro", "outubro", "novembro", "dezembro", "turnover", "headcount",
    "posso", "confiar", "significa", "numero", "número", "esse", "este",
}

# Sequência de palavras capitalizadas: o formato típico de nome próprio.
_CAPITALIZADAS = re.compile(
    r"\b[A-ZÀ-Ý][a-zà-ÿ']{1,}(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý][a-zà-ÿ']{1,}){1,3}\b")


def _seguro(trecho: str, allowlist: set[str]) -> bool:
    """Está no vocabulário governado, comparando sem acento e sem caixa."""
    from .intent import slug
    alvo = slug(trecho)
    if not alvo:
        return True
    if alvo in {slug(t) for t in allowlist}:
        return True
    # Um trecho contido num termo governado também é seguro: "Customer" dentro
    # de "Customer Service" não é nome de pessoa.
    return any(alvo in slug(t) for t in allowlist if len(slug(t)) >= len(alvo))


def redigir(texto: str, allowlist: set[str] | None = None) -> str:
    """Devolve o texto seguro para registro."""
    if not texto:
        return texto
    allow = set(allowlist or ())
    saida = texto

    saida = _EMAIL.sub(EMAIL, saida)
    saida = _CNPJ.sub(DOCUMENTO, saida)
    saida = _CPF.sub(DOCUMENTO, saida)
    saida = _TEL.sub(TELEFONE, saida)
    saida = _DIGITOS.sub(NUMERO, saida)
    saida = _HANDLE.sub(HANDLE, saida)

    def _troca(m: re.Match) -> str:
        trecho = m.group(0)
        primeira = trecho.split()[0].lower()
        if primeira in _PARADAS:
            return trecho
        return trecho if _seguro(trecho, allow) else NOME

    return _CAPITALIZADAS.sub(_troca, saida)


def contem_pii(texto: str, allowlist: set[str] | None = None) -> bool:
    return redigir(texto, allowlist) != texto
