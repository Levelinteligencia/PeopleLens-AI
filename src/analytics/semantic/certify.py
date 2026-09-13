"""Trust Layer da resposta (ADR-0029, F7 Partes IV e XIV).

A F5 mede `trust_dado`: quanto do dado esta certo, como media ponderada da perda
dos checks BLOCKER e CRITICAL das dependencias do KPI, com a perda atribuida por
classe de achado. A F7 acrescenta a dimensao que faltava, `trust_governanca`, e
compoe as duas pelo **minimo**:

    trust_resposta = min(trust_dado, teto do status de certificacao)

A composicao e por minimo, e nao por produto, pelo mesmo motivo que a F5 ja
descobriu ao abandonar o trust composto multiplicativo: o produto cai rapido
demais e deixa de ser interpretavel. O minimo preserva a leitura "o elo mais
fraco e este", e `limitado_por` diz qual dos dois elos foi.

As bandas da F5 **nao se movem** (ADR-0023, decisao DQ-04). Nada aqui cria um
numero: o unico numero medido continua sendo o `trust_dado`, e o teto e um
mapeamento declarado de status para banda.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from generator.config import Config

from .catalog import Kpi, ORDEM_TRUST, banda, trust_resposta

TRUST_PARQUET = ("data", "processed", "metadata", "kpi_trust_score.parquet")

# Motivos pelos quais o teto veio da governanca e nao do dado. Existem separados
# porque exigem acoes de pessoas diferentes: pendencia de dado vai para
# engenharia e qualidade; pendencia de definicao vai para People Analytics.
LIMITADO_POR = ("DADO", "GOVERNANCA", "COBERTURA", "NENHUM")


@dataclass
class TrustResposta:
    status: str
    score: float | None
    limitado_por: str
    motivo: str
    trust_dado: str
    trust_governanca: str | None
    perda_por_erro: float | None = None
    perda_por_pendencia: float | None = None
    perda_por_classe: dict = field(default_factory=dict)
    checks_avaliados: int = 0
    checks_declarados: int = 0
    recorte_usado: str = "GLOBAL"
    cobertura_de_verificacao: float | None = None

    def to_dict(self) -> dict:
        return dict(status=self.status, score=self.score,
                    limitado_por=self.limitado_por, motivo=self.motivo,
                    trust_dado=self.trust_dado, trust_governanca=self.trust_governanca,
                    perda_por_erro=self.perda_por_erro,
                    perda_por_pendencia=self.perda_por_pendencia,
                    perda_por_classe=self.perda_por_classe,
                    checks_avaliados=self.checks_avaliados,
                    checks_declarados=self.checks_declarados,
                    recorte_usado=self.recorte_usado,
                    cobertura_de_verificacao=self.cobertura_de_verificacao)


def load_trust(cfg: Config) -> pl.DataFrame | None:
    p = Path(cfg.root).joinpath(*TRUST_PARQUET)
    return pl.read_parquet(p) if p.exists() else None


def _recorte(filtros: list[dict]) -> str:
    """Recorte fino da F5 que corresponde ao filtro pedido, se houver.

    A calibragem por recorte fino e o que a decisao DQ-04 escolheu em vez de
    mexer nas bandas. Aqui ela e consumida: um filtro por pais usa o trust
    daquele pais, e nao o GLOBAL.
    """
    for f in filtros or []:
        if f["dimension"] == "pais" and len(f["members"]) == 1:
            return f"pais={f['members'][0]}"
    return "GLOBAL"


def certify(cfg: Config, kpi: Kpi, resolvido: dict,
            populacao: int, cobertura_populacao: float | None = None,
            trust_df: pl.DataFrame | None = None) -> TrustResposta:
    """Compoe o trust da resposta para este KPI neste recorte."""
    df = trust_df if trust_df is not None else load_trust(cfg)
    recorte = _recorte(resolvido.get("filtros") or [])

    linha = None
    if df is not None:
        sel = df.filter((pl.col("kpi") == kpi.kpi_id) & (pl.col("recorte") == recorte))
        if sel.is_empty() and recorte != "GLOBAL":
            recorte = "GLOBAL"
            sel = df.filter((pl.col("kpi") == kpi.kpi_id) & (pl.col("recorte") == "GLOBAL"))
        if not sel.is_empty():
            linha = sel.row(0, named=True)

    if linha is None:
        # Sem evidencia nao e evidencia de qualidade. INDETERMINADO, nunca
        # CERTIFIED (F7, secao 14).
        dado, score, motivo = "INDETERMINADO", None, "SEM_EVIDENCIA"
        perda_erro = perda_pend = None
        por_classe, aval, decl = {}, 0, 0
    else:
        score = linha["trust_score"]
        dado = linha["trust_status"] if linha["trust_status"] in ORDEM_TRUST else banda(score)
        motivo = linha["motivo"]
        perda_erro = linha["perda_por_erro"]
        perda_pend = linha["perda_por_pendencia"]
        bruto = linha.get("perda_por_classe")
        por_classe = (json.loads(bruto) if isinstance(bruto, str) else (bruto or {}))
        aval = int(linha["checks_avaliados"] or 0)
        decl = int(linha["checks_declarados"] or 0)

    teto = kpi.teto_trust
    status = trust_resposta(dado, teto)

    limitado, razao = "NENHUM", motivo
    if teto is None:
        limitado, razao = "GOVERNANCA", f"KPI em {kpi.status}"
    elif ORDEM_TRUST.get(teto, 2) < ORDEM_TRUST.get(dado, 2):
        limitado = "GOVERNANCA"
        razao = f"KPI em {kpi.status}; certificacao pendente"
    elif dado != "CERTIFIED":
        limitado = "DADO"

    # Cobertura de populacao abaixo do declarado rebaixa para LIMITED, com a
    # cobertura na resposta (F7, secao 14). E o criterio novo da F7, e e o que
    # faz `hiring_volume` sair LIMITED com 30% de cobertura de origem.
    if cobertura_populacao is not None and cobertura_populacao < 1.0:
        if ORDEM_TRUST[status] > ORDEM_TRUST["LIMITED"]:
            status = "LIMITED"
        limitado = "COBERTURA"
        razao = (f"cobertura de populacao de {cobertura_populacao:.1%} "
                 "declarada no contrato")

    return TrustResposta(
        status=status, score=score, limitado_por=limitado, motivo=razao,
        trust_dado=dado, trust_governanca=teto,
        perda_por_erro=perda_erro, perda_por_pendencia=perda_pend,
        perda_por_classe=por_classe, checks_avaliados=aval, checks_declarados=decl,
        recorte_usado=recorte,
        cobertura_de_verificacao=(None if not decl else round(aval / decl, 4)))
