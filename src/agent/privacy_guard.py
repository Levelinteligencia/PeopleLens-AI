"""A-03 — o Harness bloqueia a sequência de contorno de supressão.

A proteção **não vive no prompt**. Uma instrução pedindo ao modelo que não tente
descobrir o valor protegido é exatamente o tipo de garantia que este projeto
recusa desde a F6: ela depende de o modelo obedecer.

O padrão que se bloqueia:

    consulta A   women_in_leadership, 2019-06, pais=CL   -> SUPPRESSED
    consulta B   women_in_leadership, 2019-06, pais=CL, quebra por nivel
                 ou pais=CL + departamento=X
                 -> a mesma população, recortada de outro jeito

A regra, em uma linha: **depois de uma supressão, só se sobe de agregação.**

| Movimento no mesmo KPI e período | Situação |
|---|---|
| menos filtros, sem quebra | **permitido** — agregar para cima é legítimo |
| mesmos filtros com quebra por dimensão | bloqueado |
| mais filtros, ou filtro diferente | bloqueado |
| outro KPI, ou outro período | **permitido**, intocado |

O bloqueio não é uma opinião sobre a intenção do agente: é uma propriedade
estrutural da consulta seguinte. Consultar mais amplo não revela o recorte
protegido; consultar mais fino ou de lado, sim.

Limite conhecido: isto protege dentro de **uma execução**. Um adversário
paciente, espalhando as consultas por várias execuções, não é coberto por estado
de execução — a supressão complementar da F7 (G-01) continua sendo a proteção de
fundo, e ela não depende de memória nenhuma.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MOTIVO = "A03_CONTORNO_DE_SUPRESSAO"

# Capacidades que leem valor. As de metadado não alcançam o recorte protegido.
CAPACIDADES_DE_VALOR = ("get_kpi", "compare_kpi", "breakdown_kpi")


def _chave_periodo(period: dict | None) -> str:
    p = period or {}
    return f"{p.get('grain')}:{p.get('from')}:{p.get('to') or p.get('from')}"


def _filtros_congelados(args: dict) -> frozenset:
    saida = set()
    for f in args.get("filters") or ():
        for v in f.get("in") or ():
            saida.add((f.get("dimension"), str(v)))
    return frozenset(saida)


@dataclass
class Supressao:
    kpi: str
    periodo: str
    filtros: frozenset
    dimensoes: frozenset


@dataclass
class PrivacyGuard:
    """Estado das supressões da execução, e a decisão sobre a próxima chamada."""
    supressoes: list[Supressao] = field(default_factory=list)
    bloqueios: list[dict] = field(default_factory=list)

    def registrar_supressao(self, tool: str, args: dict) -> None:
        if tool not in CAPACIDADES_DE_VALOR:
            return
        self.supressoes.append(Supressao(
            kpi=str(args.get("kpi")),
            periodo=_chave_periodo(args.get("period")),
            filtros=_filtros_congelados(args),
            dimensoes=frozenset(args.get("dimensions") or ())))

    def permite(self, tool: str, args: dict) -> tuple[bool, str | None]:
        """(pode_chamar, motivo_do_bloqueio)."""
        if tool not in CAPACIDADES_DE_VALOR or not self.supressoes:
            return True, None

        kpi = str(args.get("kpi"))
        periodo = _chave_periodo(args.get("period"))
        filtros = _filtros_congelados(args)
        dims = frozenset(args.get("dimensions") or ())

        for s in self.supressoes:
            if s.kpi != kpi or s.periodo != periodo:
                continue          # outro KPI ou outro período: livre
            # Estritamente mais amplo: menos filtros e sem quebra.
            mais_amplo = filtros < s.filtros and not dims
            if mais_amplo:
                continue
            motivo = (
                f"a consulta anterior a {kpi} neste período foi suprimida por "
                "privacidade, e esta não é mais ampla que ela. Depois de uma "
                "supressão, só é possível subir de agregação.")
            self.bloqueios.append({
                "motivo": MOTIVO, "kpi": kpi, "periodo": periodo,
                "tool": tool,
                "dimensoes_pedidas": sorted(dims),
                "explicacao": motivo})
            return False, motivo
        return True, None

    @property
    def houve_bloqueio(self) -> bool:
        return bool(self.bloqueios)

    def to_dict(self) -> list[dict]:
        return list(self.bloqueios)
