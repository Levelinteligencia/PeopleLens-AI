"""Contexto fechado do Harness (SPEC Parte IV, §7; decisão A-02).

Três blocos, e **nenhum dado quantitativo entre eles**: catálogo, vocabulário e
política. O catálogo entra como contexto e não como conhecimento do modelo —
sem isso, o agente escolhe KPI por memória de treino, e um modelo que "sabe" o
que é turnover inventa a definição do PeopleLens.

**A-02, decidida:** o vocabulário necessário ao `RESOLVE` é carregado aqui,
derivado de fonte governada — o catálogo de KPIs (via `get_kpi_definition`) e o
vocabulário semântico da F7, lido como configuração. **Não se cria uma sétima
capacidade MCP**, e a MCP SPEC não muda.

O contexto é uma **lista fechada**, e não um orçamento de tamanho. Definir por
tamanho convidaria a caber mais coisa; definir por lista impede que um valor
entre por conveniência.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .intent import slug

# Formatos de período, por grain. Mesma gramática do vocabulário da F7.
PADRAO_PERIODO = {
    "mes": re.compile(r"^\d{4}-(0[1-9]|1[0-2])$"),
    "trimestre": re.compile(r"^\d{4}-Q[1-4]$"),
    "ano": re.compile(r"^\d{4}$"),
    "ciclo": re.compile(r"^\d{4}(-H[12])?$"),
}


@dataclass
class Contexto:
    """O que o agente recebe. Nada além disto entra."""
    catalogo: dict[str, dict] = field(default_factory=dict)   # kpi_id -> definição
    vocabulario: dict[str, list[str]] = field(default_factory=dict)  # dim -> termos
    grupos: dict[str, list[str]] = field(default_factory=dict)       # dim -> grupos
    relativos: dict[str, dict] = field(default_factory=dict)  # termo -> resolução
    politica: dict = field(default_factory=dict)

    # ----------------------------------------------------------------- catálogo
    def kpi(self, kpi_id: str | None) -> dict | None:
        return self.catalogo.get(kpi_id) if kpi_id else None

    @staticmethod
    def _status(d: dict) -> str | None:
        """O status vive em `governance`, como `get_kpi_definition` o devolve."""
        return (d.get("governance") or {}).get("status")

    def kpis_que_respondem(self) -> list[str]:
        return sorted(k for k, d in self.catalogo.items()
                      if self._status(d) in ("CERTIFIED", "DECLARED", "DEPRECATED"))

    def kpis_bloqueados(self) -> list[str]:
        return sorted(k for k, d in self.catalogo.items()
                      if self._status(d) == "BLOCKED")

    def grains_aceitos(self, kpi_id: str) -> list[str]:
        """Grains que o KPI responde: o do contrato, e os mais grossos quando
        há `period_rollup` declarado. Rollup é decisão registrada, não inferência."""
        d = self.catalogo.get(kpi_id) or {}
        base = d.get("period_grain")
        if not base:
            return []
        if not d.get("period_rollup"):
            return [base]
        ordem = {"mes": 0, "trimestre": 1, "ciclo": 1, "ano": 2}
        piso = ordem.get(base, 0)
        return [g for g, n in ordem.items() if n >= piso]

    def fora_da_cobertura(self, kpi_id: str, period: dict) -> tuple[str, str] | None:
        cov = (self.catalogo.get(kpi_id) or {}).get("period_coverage")
        if not cov:
            return None
        ini, fim = str(cov["from"]), str(cov["to"])
        for v in (period.get("from"), period.get("to")):
            if not v:
                continue
            v = str(v)
            if not (ini <= v <= fim or (len(v) == 4 and ini[:4] <= v <= fim[:4])):
                return ini, fim
        return None

    def periodos_sugeridos(self, kpi_id: str) -> list[str]:
        """Períodos válidos que a pessoa provavelmente quer, pela cobertura.

        Sugerir a janela coberta é informação verificável. Sugerir "o período
        mais parecido com o que você pediu" seria o mesmo erro de similaridade
        que o vocabulário proíbe.
        """
        cov = (self.catalogo.get(kpi_id) or {}).get("period_coverage")
        if not cov:
            return []
        fim = str(cov["to"])
        grain = (self.catalogo.get(kpi_id) or {}).get("period_grain")
        if grain == "ano":
            return [fim, str(int(fim[:4]) - 1)]
        return [fim, str(cov["from"])]

    def minimo(self, kpi_id: str) -> int:
        return int((self.catalogo.get(kpi_id) or {}).get("minimum_n") or 0)

    def teto_do_kpi(self, kpi_id: str) -> str | None:
        return ((self.catalogo.get(kpi_id) or {})
                .get("response_levels") or {}).get("ceiling")

    # -------------------------------------------------------------- vocabulário
    def termos_de(self, dimensao: str | None, limite: int = 12) -> list[str]:
        termos = list(self.vocabulario.get(dimensao or "", []))
        termos += list(self.grupos.get(dimensao or "", []))
        return sorted(termos)[:limite]

    def termo_valido(self, dimensao: str | None, termo: str) -> bool:
        """Igualdade normalizada, nunca aproximação (ADR-0020, A-02)."""
        alvo = slug(termo)
        for t in self.vocabulario.get(dimensao or "", []):
            if slug(t) == alvo:
                return True
        for g in self.grupos.get(dimensao or "", []):
            if slug(g) == alvo:
                return True
        return False

    def termo_canonico(self, dimensao: str, termo: str) -> str | None:
        alvo = slug(termo)
        for t in (*self.vocabulario.get(dimensao, []),
                  *self.grupos.get(dimensao, [])):
            if slug(t) == alvo:
                return t
        return None

    def termo_relativo(self, termo: str | None) -> dict | None:
        """A resolução **declarada** de um termo relativo, ou nada.

        Igualdade normalizada, como todo o resto do vocabulário: "último
        trimestre" encontra `ultimo_trimestre`, e "trimestre passado" não
        encontra coisa alguma. Um termo relativo sem declaração não vira o
        termo declarado mais parecido (ADR-0020), vira ambiguidade.
        """
        if not termo:
            return None
        alvo = slug(termo)
        for nome, spec in self.relativos.items():
            if slug(nome) == alvo:
                return dict(spec or {})
        return None

    def todos_os_termos(self) -> set[str]:
        """Allowlist do que é seguro registrar em log (A-04)."""
        fora = set()
        for termos in self.vocabulario.values():
            fora |= {str(t) for t in termos}
        for g in self.grupos.values():
            fora |= {str(t) for t in g}
        fora |= set(self.catalogo)
        for d in self.catalogo.values():
            if d.get("name"):
                fora.add(str(d["name"]))
        return fora


# --------------------------------------------------------------------------- #
# Construção
# --------------------------------------------------------------------------- #
def construir(servidor, ator, cfg, politica: dict | None = None) -> Contexto:
    """Monta o contexto fechado a partir de fontes governadas.

    Duas fontes, e **nenhuma delas é dado**:

    - o **catálogo** vem do MCP, pela capacidade que existe para isso;
    - o **vocabulário** vem do arquivo governado da F7 lido como configuração,
      mais os membros que a própria Semantic Layer já resolveu ao subir.

    O agente não abre arquivo de dado e não consulta tabela. Ler o nome dos
    departamentos do vocabulário que a camada governada já montou é o que a
    decisão A-02 chama de fonte governada; a alternativa — uma sétima
    capacidade MCP — seria mudança da MCP SPEC.
    """
    catalogo: dict[str, dict] = {}
    lista = servidor.call("get_kpi_definition", {}, actor=ator, registrar=False)
    for item in (lista.data or {}).get("catalog", []):
        env = servidor.call("get_kpi_definition", {"kpi": item["kpi_id"]},
                            actor=ator, registrar=False)
        if env.ok:
            catalogo[item["kpi_id"]] = env.data

    vocab, grupos, relativos = _vocabulario(cfg, servidor)
    return Contexto(catalogo=catalogo, vocabulario=vocab, grupos=grupos,
                    relativos=relativos, politica=dict(politica or {}))


def _vocabulario(cfg, servidor) -> tuple[dict, dict, dict]:
    """Termos por dimensão, do vocabulário governado da F7.

    Inclui os membros declarados, seus sinônimos aprovados e os membros que a
    dimensão de fato tem. **Não inclui** membro reservado: `UNMAPPED` e
    `DECISAO_PENDENTE` são pendência de governança, não valor consultável
    (ADR-0025).
    """
    caminho = Path(cfg.root) / "config" / "semantic" / "vocabulary.yaml"
    with open(caminho, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    termos: dict[str, list[str]] = {}
    grupos: dict[str, list[str]] = {}
    for dim, spec in (doc.get("dimensions") or {}).items():
        bloqueados = {slug(t) for t in spec.get("reserved_terms_blocked") or []}
        saida: list[str] = []
        for membro, m in (spec.get("members") or {}).items():
            saida.append(membro)
            saida.extend(m.get("terms") or [])
        for g in (spec.get("groups") or {}):
            grupos.setdefault(dim, []).append(g)
            grupos[dim].extend((spec["groups"][g].get("terms") or []))
        termos[dim] = [t for t in saida if slug(t) not in bloqueados]

    # Membros que vêm da própria dimensão (departamentos, níveis, sistemas).
    for dim, coluna in (("departamento", "department"), ("nivel", "code"),
                        ("sistema_fonte", "code")):
        spec = (doc.get("dimensions") or {}).get(dim) or {}
        if not spec.get("members_from_dimension"):
            continue
        bloqueados = {slug(t) for t in spec.get("reserved_terms_blocked") or []}
        membros = _membros_governados(servidor, dim)
        termos.setdefault(dim, [])
        termos[dim] += [m for m in membros if slug(m) not in bloqueados]

    # Termos relativos, como o vocabulário governado os declara. Eles resolvem
    # contra a **cobertura do KPI**, nunca contra o relógio: "último mês" num
    # KPI carregado até 2026-06 é 2026-06, e não o mês corrente. Sem isso a
    # mesma pergunta devolveria resposta diferente conforme o dia em que foi
    # feita, e a reprodutibilidade que AA-11 exige cairia.
    relativos = dict((doc.get("periods") or {}).get("relative_terms") or {})

    return ({d: sorted(set(v)) for d, v in termos.items()},
            {d: sorted(set(v)) for d, v in grupos.items()},
            relativos)


def _membros_governados(servidor, dimensao: str) -> list[str]:
    """Membros que a Semantic Layer já resolveu quando subiu.

    Não é leitura de dado: é o vocabulário que a camada governada montou para si
    e mantém em memória. O agente não abre Parquet, não consulta tabela e não
    conhece nome de coluna — se este caminho não existisse, a alternativa seria
    uma sétima capacidade no MCP, que a decisão A-02 descartou.
    """
    engine = getattr(servidor, "engine", None)
    vocab = getattr(engine, "vocab", None)
    membros = getattr(vocab, "membros_da_dimensao", None) or {}
    return sorted(str(m) for m in membros.get(dimensao, ()))
