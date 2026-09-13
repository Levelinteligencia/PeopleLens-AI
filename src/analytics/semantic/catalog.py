"""KPI Catalog: ciclo de vida, versionamento e teto de governanca (ADR-0029, ADR-0030).

Este modulo responde a pergunta que o trust score da F5 nao responde: **alguem
assinou esta definicao?**

    trust_dado        quanto do dado esta certo          (F5, medido)
    trust_governanca  teto do status de certificacao     (F7, declarado)
    trust_resposta    o menor dos dois

As duas sao independentes, e o caso que prova isso esta no proprio catalogo:
`internal_mobility_rate` tem trust de dado 0,9939 e nao tem definicao fechada,
porque `movement_type` carrega dois vocabularios ao mesmo tempo. O numero sai
limpo e sai errado. Sem a segunda dimensao ele sairia como CERTIFIED.

`CERTIFIED` NAO e calculavel: e aprovacao humana registrada, com dono e data.
Promover um KPI porque o dado melhorou e o mesmo erro que a F4 proibe na
promocao automatica de mapeamento, e nao existe funcao aqui que o faca.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from generator.config import Config

from .. import contracts
from ..trust import BANDS

# --------------------------------------------------------------------------- #
# Ciclo de vida (ADR-0030)
# --------------------------------------------------------------------------- #
#
#   DRAFT -> DECLARED -> CERTIFIED -> DEPRECATED
#                     \-> BLOCKED
#
STATUSES = ("DRAFT", "DECLARED", "CERTIFIED", "BLOCKED", "DEPRECATED")

TRANSICOES = {
    ("DRAFT", "DECLARED"): ("owner", "business_definition", "formula", "grain", "population"),
    ("DECLARED", "CERTIFIED"): ("certification.approved_by", "certification.approved_at"),
    ("CERTIFIED", "DEPRECATED"): ("deprecated_by",),
}

# Ordem de forca dos status de confianca. `trust_resposta` e o MINIMO nesta
# ordem entre o status do dado (F5) e o teto de governanca (F7). Implementar a
# composicao como minimo de status, e nao como produto ou media de numeros,
# preserva a regra da F5 de nao inventar score: o unico numero medido continua
# sendo `trust_dado`.
ORDEM_TRUST = {"BLOCKED": 0, "INDETERMINADO": 0, "LIMITED": 1, "CERTIFIED": 2}

# Teto que o status do KPI impoe. Nao e um numero inventado: e um mapeamento
# declarado de status para banda ja existente da F5 (ADR-0023, bandas intactas).
TETO_TRUST = {
    "CERTIFIED":  "CERTIFIED",     # sem teto
    "DECLARED":   "LIMITED",
    "DEPRECATED": "LIMITED",
    "BLOCKED":    None,            # recusa
    "DRAFT":      None,            # recusa
}

# Teto de nivel de resposta por status (ADR-0029, secao 2).
TETO_NIVEL = {
    "CERTIFIED":  "CAUSALITY",     # so com estudo registrado; ver response.py
    "DECLARED":   "CONTEXT",
    "DEPRECATED": "CONTEXT",
    "BLOCKED":    None,
    "DRAFT":      None,
}

NIVEIS = ("FACT", "CONTEXT", "INTERPRETATION", "CAUSALITY")
ORDEM_NIVEL = {n: i for i, n in enumerate(NIVEIS)}

CAMPOS_OBRIGATORIOS = (
    "kpi_id", "name", "description", "business_definition", "formula", "grain",
    "population", "period_grain", "allowed_dimensions", "filters", "exclusions",
    "source_tables", "owner", "version", "status", "certification",
    "depends_on_checks", "depends_on_mappings", "minimum_n", "response_levels",
)

# Prefixo unico de tabela que a camada semantica pode ler. Qualquer outra coisa
# e RAW, standardized, conformed ou camada de verdade, e nenhuma delas e
# endereçavel daqui (AC-04, AC-05).
TABELAS_L3_PREFIXOS = ("fact_", "dim_")


@dataclass(frozen=True)
class Kpi:
    """Um contrato de KPI ja validado, com o que a camada precisa saber."""
    kpi_id: str
    doc: dict

    # ------------------------------------------------------------- identidade
    @property
    def status(self) -> str:
        return self.doc["status"]

    @property
    def version(self) -> str:
        return str(self.doc["version"])

    @property
    def owner(self) -> str:
        return self.doc["owner"]

    @property
    def minimum_n(self) -> int:
        return int(self.doc.get("minimum_n") or 0)

    # ------------------------------------------------------------- governanca
    @property
    def teto_trust(self) -> str | None:
        return TETO_TRUST[self.status]

    @property
    def teto_nivel(self) -> str | None:
        """Teto de nivel de resposta, ja considerando a evidencia disponivel.

        CERTIFIED so alcanca INTERPRETATION se houver regra registrada, e
        CAUSALITY se houver estudo. Sem isso o teto cai, e nao ha como
        "destravar" um nivel preenchendo o campo com um valor plausivel: a
        regra exige dono e data de aprovacao.
        """
        teto = TETO_NIVEL[self.status]
        if teto is None:
            return None
        if teto == "CAUSALITY" and not self.doc.get("causal_studies"):
            teto = "INTERPRETATION"
        if teto == "INTERPRETATION" and not self.doc.get("interpretation_rules"):
            teto = "CONTEXT"
        return teto

    @property
    def bloqueadores(self) -> list[dict]:
        return list((self.doc.get("certification") or {}).get("blockers") or [])

    @property
    def responde(self) -> bool:
        return self.status in ("CERTIFIED", "DECLARED", "DEPRECATED")

    # ------------------------------------------------------------- consulta
    @property
    def allowed_dimensions(self) -> list[str]:
        return list(self.doc.get("allowed_dimensions") or [])

    @property
    def period_grain(self) -> str:
        return self.doc["period_grain"]

    @property
    def period_rollup(self) -> str | None:
        return self.doc.get("period_rollup")

    @property
    def period_coverage(self) -> tuple[str, str] | None:
        c = self.doc.get("period_coverage")
        if not c:
            return None
        return str(c["from"]), str(c["to"])

    @property
    def source_tables(self) -> list[str]:
        return list(self.doc.get("source_tables") or [])

    @property
    def cobertura_declarada(self) -> dict | None:
        return self.doc.get("coverage")


@dataclass
class Catalog:
    kpis: dict[str, Kpi] = field(default_factory=dict)

    def __contains__(self, kpi_id: str) -> bool:
        return kpi_id in self.kpis

    def __getitem__(self, kpi_id: str) -> Kpi:
        return self.kpis[kpi_id]

    def get(self, kpi_id: str) -> Kpi | None:
        return self.kpis.get(kpi_id)

    def por_status(self, status: str) -> list[Kpi]:
        return [k for k in self.kpis.values() if k.status == status]

    @property
    def ids(self) -> list[str]:
        return sorted(self.kpis)


def load(cfg: Config) -> Catalog:
    docs = contracts.load(cfg)
    return Catalog({k: Kpi(k, d) for k, d in docs.items()})


# --------------------------------------------------------------------------- #
# Verificacao de governanca
# --------------------------------------------------------------------------- #
def verify(cfg: Config) -> list[str]:
    """Problemas de governanca do catalogo. Vazio e o esperado.

    Complementa `contracts.verify` (que cuida da derivacao de checks) com o que
    a F7 acrescentou: campos obrigatorios, ciclo de vida, versionamento e a
    proibicao de apontar para fora da L3.
    """
    cat = load(cfg)
    problemas: list[str] = []

    for kpi in cat.kpis.values():
        d, i = kpi.doc, kpi.kpi_id

        # AC-01: campos obrigatorios
        for campo in CAMPOS_OBRIGATORIOS:
            if campo not in d or d[campo] is None:
                problemas.append(f"{i}: campo obrigatorio ausente: {campo}")

        if d.get("status") not in STATUSES:
            problemas.append(f"{i}: status invalido: {d.get('status')!r}")

        # AC-03: CERTIFIED exige dono, versao, data de aprovacao e zero bloqueadores
        if d.get("status") == "CERTIFIED":
            cert = d.get("certification") or {}
            if not cert.get("approved_by"):
                problemas.append(f"{i}: CERTIFIED sem approved_by")
            if not cert.get("approved_at"):
                problemas.append(f"{i}: CERTIFIED sem approved_at")
            if cert.get("blockers"):
                problemas.append(f"{i}: CERTIFIED com bloqueador declarado")
            if not kpi.period_coverage:
                problemas.append(f"{i}: CERTIFIED sem period_coverage")

        # ADR-0030: BLOCKED exige bloqueador declarado E o que o resolve
        if d.get("status") == "BLOCKED":
            if not kpi.bloqueadores:
                problemas.append(f"{i}: BLOCKED sem bloqueador declarado")
            for b in kpi.bloqueadores:
                if not b.get("resolvido_por"):
                    problemas.append(f"{i}: bloqueador sem `resolvido_por`")

        # AC-04: source_tables so aponta para a L3
        for t in kpi.source_tables:
            if not t.startswith(TABELAS_L3_PREFIXOS):
                problemas.append(f"{i}: source_tables aponta para fora da L3: {t}")

        # ADR-0030: versionamento semantico
        v = str(d.get("version") or "")
        partes = v.split(".")
        if len(partes) != 3 or not all(p.isdigit() for p in partes):
            problemas.append(f"{i}: version fora do versionamento semantico: {v!r}")

        # AC-13 / AC-14: regra e estudo exigem dono e data. Nao ha nivel
        # destravado por campo preenchido pela metade.
        for regra in d.get("interpretation_rules") or []:
            if not (regra.get("owner") and regra.get("approved_at")):
                problemas.append(f"{i}: interpretation_rule sem owner/approved_at")
        for est in d.get("causal_studies") or []:
            faltando = [c for c in ("design", "treatment", "control", "effect",
                                    "interval", "limitations") if not est.get(c)]
            if faltando:
                problemas.append(f"{i}: causal_study incompleto, faltando {faltando}")

        if kpi.period_rollup not in (None, "soma", "ultimo_periodo"):
            problemas.append(f"{i}: period_rollup desconhecido: {kpi.period_rollup!r}")

    return problemas


def trust_resposta(trust_dado: str, teto: str | None) -> str:
    """O menor entre o status do dado e o teto de governanca (AC-09).

    Um KPI nao certificado nunca responde como CERTIFIED, por mais limpo que
    esteja o dado. E um KPI certificado cujo dado degradou responde com o
    status do dado: a certificacao continua valida, o numero e que nao esta bom.
    """
    if teto is None:
        return "BLOCKED"
    return trust_dado if ORDEM_TRUST[trust_dado] <= ORDEM_TRUST[teto] else teto


def banda(score: float | None) -> str:
    """Status de trust de um score, pelas bandas da F5. Elas nao se movem."""
    if score is None:
        return "INDETERMINADO"
    if score >= BANDS["CERTIFIED"]:
        return "CERTIFIED"
    if score >= BANDS["LIMITED"]:
        return "LIMITED"
    return "BLOCKED"
