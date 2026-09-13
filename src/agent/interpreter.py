"""UNDERSTAND: a costura onde um modelo entra (SPEC Parte V).

Este é o **único** passo com latitude. Tudo o mais é código: `RESOLVE` confronta
com catálogo e vocabulário, `PLAN` vem da matriz da SPEC, `ACT` chama o MCP,
`RESPOND` cita apenas números que vieram de envelope.

`Interpreter` é um protocolo. Um modelo de linguagem, quando for plugado, o
implementa — e não ganha nenhuma capacidade nova por isso: continua devolvendo
uma `Intent`, que o `RESOLVE` valida e pode recusar inteira.

`RuleInterpreter` é a implementação de referência, determinística. Existe por
duas razões, e nenhuma é economia: ela torna o Harness testável sem depender de
um modelo, e torna verdadeira a reprodutibilidade que o acceptance AA-11 exige —
mesmo estado e mesma pergunta produzem o mesmo plano e as mesmas chamadas.
"""
from __future__ import annotations

import re
from typing import Protocol

from .intent import (CAUSAL, COMPARACAO, CONFIANCA, DEFINICAO, FORA_DE_ESCOPO,
                     LINHAGEM, RANKING, VALOR, Intent, slug)


class Interpreter(Protocol):
    def understand(self, pergunta: str, contexto) -> Intent:  # pragma: no cover
        ...


# --------------------------------------------------------------------------- #
# Padrões
# --------------------------------------------------------------------------- #
_CAUSAL = re.compile(
    r"\b(por que|porque|causou|causa|motivo|razao|razão|explica|"
    r"o que levou|responsavel por|responsável por)\b", re.I)
_COMPARA = re.compile(
    r"\b(compar\w+|versus|vs\.?|em rela[cç][aã]o a|contra o|"
    r"ano anterior|periodo anterior|período anterior)\b", re.I)
_RANKING = re.compile(
    r"\b(quais?|qual .*(maior|menor)|maiores|menores|ranking|"
    r"por departamento|por pais|por país|por nivel|por nível|"
    r"por business unit|por genero|por gênero|top \d+)\b", re.I)
_DEFINE = re.compile(
    r"\b(o que (e|é|significa)|defini[cç][aã]o|como .* calcula\w*|"
    r"como voces? (medem|calculam))\b", re.I)
_CONFIA = re.compile(
    r"\b(confi\w+|posso confiar|qualidade do dado|quao seguro|quão seguro|"
    r"trust)\b", re.I)
_LINHAGEM = re.compile(
    r"\b(de onde vei?o|linhagem|lineage|origem desse|origem do numero|"
    r"origem do número|como chegou|de onde saiu)\b", re.I)
_AUMENTO = re.compile(r"\b(aument\w+|subiu|cresce\w+|piorou)\b", re.I)
_QUEDA = re.compile(r"\b(caiu|diminui\w+|redu\w+|melhorou)\b", re.I)
_ANTERIOR = re.compile(
    r"\b(esse numero|esse número|este numero|este número|isso|"
    r"compare com|e com o|e no)\b", re.I)

_MES = re.compile(r"\b(20\d{2})[-/](0[1-9]|1[0-2])\b")
_TRI = re.compile(r"\b(?:q([1-4])\s*(?:de\s*)?(20\d{2})|(20\d{2})[-\s]*q([1-4])|"
                  r"([1-4])[ºo]?\s*trimestre\s*(?:de\s*)?(20\d{2}))\b", re.I)
_ANO = re.compile(r"\b(20\d{2})\b")

# Termos que apontam para um KPI. Mapa declarado, não similaridade: a escolha de
# KPI é decisão registrada, e um mapa é auditável em diff (Política P-03).
SINONIMOS_DE_KPI = {
    "turnover_rate": ("turnover", "rotatividade", "desligamento",
                      "desligamentos", "saida de pessoas", "attrition"),
    "headcount": ("headcount", "quantas pessoas", "numero de pessoas",
                  "número de pessoas", "quadro de pessoal", "efetivo"),
    "hiring_volume": ("contratacao", "contratação", "contratacoes",
                      "contratações", "admissoes", "admissões"),
    "women_in_leadership": ("mulheres em lideranca", "mulheres em liderança",
                            "mulheres na lideranca", "women in leadership"),
    "time_to_fill": ("tempo para preencher", "time to fill",
                     "tempo de preenchimento"),
    "time_to_hire": ("tempo para contratar", "time to hire"),
    "offer_acceptance_rate": ("aceite de oferta", "taxa de aceite",
                              "offer acceptance"),
    "promotion_rate": ("promocao", "promoção", "promocoes", "promoções",
                       "taxa de promocao", "taxa de promoção"),
    "internal_mobility_rate": ("mobilidade interna", "movimentacao interna",
                               "movimentação interna"),
    "tenure": ("tempo de casa", "tenure", "senioridade media"),
    "fte": ("fte", "equivalente em tempo integral"),
    "span_of_control": ("span of control", "pessoas por gestor",
                        "amplitude de controle"),
    "gender_representation": ("representatividade de genero",
                              "representatividade de gênero",
                              "distribuicao de genero"),
    "black_representation": ("representatividade negra", "pessoas negras"),
    "pcd_representation": ("pcd", "pessoas com deficiencia",
                           "pessoas com deficiência"),
    "performance_distribution": ("distribuicao de performance",
                                 "distribuição de performance",
                                 "notas de performance"),
    "compa_ratio": ("compa ratio", "compa-ratio"),
    "pay_gap": ("pay gap", "diferenca salarial", "diferença salarial"),
}

# Dimensões de quebra, pelo jeito que a pergunta pede.
PEDE_DIMENSAO = {
    "departamento": ("por departamento", "quais departamentos", "que departamento",
                     "por area", "por área"),
    "pais": ("por pais", "por país", "quais paises", "quais países"),
    "nivel": ("por nivel", "por nível", "quais niveis", "quais níveis"),
    "business_unit": ("por business unit", "por bu", "quais business units"),
    "genero": ("por genero", "por gênero"),
    "origem": ("por origem",),
}

DIMENSOES_DE_FILTRO = ("departamento", "pais", "business_unit", "nivel",
                       "genero", "origem", "sistema_fonte")


class RuleInterpreter:
    """Implementação de referência, determinística.

    Extrai tipo de pergunta, KPI candidato, período, filtros e quebras. **Não
    resolve nada**: termo desconhecido sai como está e o `RESOLVE` o recusa, que
    é onde a decisão A-01 age.
    """

    def understand(self, pergunta: str, contexto) -> Intent:
        p = slug(pergunta)
        tipo = self._tipo(p)
        kpis = self._kpis(p, contexto)
        periodo = self._periodo(pergunta, p)
        dims = self._dimensoes(p)
        # O texto que o sinônimo do KPI consumiu sai antes da busca por filtros.
        # "mulheres em liderança" identifica `women_in_leadership`, e gênero e
        # nível já estão dentro da definição dele: reaproveitá-los como filtro
        # produziria uma ambiguidade falsa sobre a própria pergunta.
        restante = self._sem_sinonimo(p, kpis)
        filtros = self._filtros(pergunta, restante, contexto, dims)

        premissa = None
        if _AUMENTO.search(pergunta):
            premissa = "AUMENTO"
        elif _QUEDA.search(pergunta):
            premissa = "QUEDA"

        nivel = "CONTEXT" if tipo in (COMPARACAO, CAUSAL) else "FACT"
        if tipo == CAUSAL:
            nivel = "CAUSALITY"

        return Intent(
            question_type=tipo, kpi_candidates=kpis, period=periodo,
            filters=filtros, dimensions=dims, requested_level=nivel,
            compare_to=("periodo_anterior" if tipo == COMPARACAO else None),
            premissa=premissa,
            referencia_anterior=bool(_ANTERIOR.search(pergunta)))

    # ------------------------------------------------------------------ partes
    def _tipo(self, p: str) -> str:
        if _LINHAGEM.search(p):
            return LINHAGEM
        if _DEFINE.search(p):
            return DEFINICAO
        if _CONFIA.search(p):
            return CONFIANCA
        if _CAUSAL.search(p):
            return CAUSAL
        if _COMPARA.search(p):
            return COMPARACAO
        if _RANKING.search(p):
            return RANKING
        return VALOR

    def _sem_sinonimo(self, p: str, kpis: list[str]) -> str:
        restante = p
        for kpi_id in kpis:
            for termo in SINONIMOS_DE_KPI.get(kpi_id, ()):
                restante = restante.replace(slug(termo), " ")
        return restante

    def _kpis(self, p: str, contexto) -> list[str]:
        achados = []
        for kpi_id, termos in SINONIMOS_DE_KPI.items():
            if kpi_id not in contexto.catalogo:
                continue
            if any(slug(t) in p for t in termos):
                achados.append(kpi_id)
        # "turnover" e "desligamento" apontam para o mesmo KPI; dois KPIs
        # distintos na mesma pergunta é ambiguidade real, e o RESOLVE a trata.
        return sorted(set(achados))

    def _periodo(self, original: str, p: str) -> dict | None:
        m = _MES.search(original)
        if m:
            v = f"{m.group(1)}-{m.group(2)}"
            return {"grain": "mes", "from": v, "to": v}
        m = _TRI.search(original)
        if m:
            g = [x for x in m.groups() if x]
            if len(g) == 2:
                tri, ano = (g[0], g[1]) if len(g[0]) == 1 else (g[1], g[0])
                v = f"{ano}-Q{tri}"
                return {"grain": "trimestre", "from": v, "to": v}
        anos = _ANO.findall(original)
        if anos:
            return {"grain": "ano", "from": anos[0], "to": anos[0]}
        return None

    def _dimensoes(self, p: str) -> list[str]:
        for dim, pistas in PEDE_DIMENSAO.items():
            if any(slug(x) in p for x in pistas):
                return [dim]
        return []

    def _filtros(self, original: str, p: str, contexto, dims: list[str]) -> list[dict]:
        """Termos citados, mesmo os que não existem.

        Um termo inválido **precisa** chegar ao `RESOLVE`: é ele que vira a
        pergunta de volta com as opções válidas. Descartá-lo aqui faria a
        pergunta parecer resolvida e responder outra coisa.
        """
        escolhido = self._mencoes(p, contexto, dims)
        filtros = [{"dimension": dim, "terms": [escolhido[dim]]}
                   for dim in DIMENSOES_DE_FILTRO if dim in escolhido]
        # Palavras que parecem nome de recorte e não estão no vocabulário.
        for suspeito in self._suspeitos(original, contexto):
            filtros.append({"dimension": "departamento", "terms": [suspeito]})
        return filtros

    def _mencoes(self, p: str, contexto, dims: list[str]) -> dict[str, str]:
        """Dimensões **explicitamente ditas** na pergunta, uma por dimensão.

        A regra, e ela é geral: *uma dimensão só entra no Intent se tiver sido
        explicitamente identificada na linguagem da pergunta, ou se estiver
        coberta por uma regra semântica declarada e testável.*

        O que a torna operável é a **posse do trecho**. Cada menção ocupa um
        intervalo de caracteres da pergunta; o trecho mais longo é lido
        primeiro e **consome** o que ocupa. Um termo mais curto que só aparece
        dentro de um trecho já lido não foi dito: foi recortado de outra
        palavra.

        Sem isso, "turnover de Customer Service" produzia também
        `business_unit = Customer`, porque a palavra cabe dentro do nome do
        departamento. O número até coincidiria aqui — Customer Service pertence
        à BU Customer — mas a coincidência é do dado, não da pergunta, e um
        departamento que atravessasse duas BUs teria a resposta silenciosamente
        estreitada. Nada abaixo desta função conhece hierarquia organizacional,
        pertencimento, semelhança ou modelo de dados; conhece só o texto.

        A mesma regra cobre o caso dentro de uma dimensão: "Data & Analytics"
        não é lido como o departamento "Data".
        """
        ocorrencias: list[tuple[int, int, str, str]] = []
        for dim in DIMENSOES_DE_FILTRO:
            if dim in dims:
                continue
            for termo in contexto.termos_de(dim, limite=500):
                s = slug(termo)
                if len(s) < 3:
                    continue
                for m in re.finditer(rf"\b{re.escape(s)}\b", p):
                    ocorrencias.append((m.start(), m.end(), dim, termo))

        # Trecho mais longo primeiro. O desempate é declarado — posição, ordem
        # da dimensão, grafia — porque AA-11 exige a mesma saída toda vez.
        ocorrencias.sort(key=lambda o: (-(o[1] - o[0]), o[0],
                                        DIMENSOES_DE_FILTRO.index(o[2]), o[3]))

        consumido: list[tuple[int, int]] = []
        escolhido: dict[str, str] = {}
        for ini, fim, dim, termo in ocorrencias:
            if any(ini < f and i < fim for i, f in consumido):
                continue          # o trecho já foi lido como outra menção
            consumido.append((ini, fim))
            escolhido.setdefault(dim, termo)
        return escolhido

    def _suspeitos(self, original: str, contexto) -> list[str]:
        """Candidatos a recorte que o vocabulário não conhece.

        Só dispara quando a frase tem a forma "de <Algo>" com inicial
        maiúscula — o suficiente para capturar "de Tecnologia" e levar a
        ambiguidade ao RESOLVE, sem sair inventando filtro de qualquer
        substantivo.
        """
        achados = []
        for m in re.finditer(r"\bde\s+([A-ZÀ-Ý][\wÀ-ÿ&]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ&]+)?)",
                             original):
            termo = m.group(1).strip()
            if termo.lower() in ("q1", "q2", "q3", "q4"):
                continue
            if any(contexto.termo_valido(d, termo) for d in DIMENSOES_DE_FILTRO):
                continue
            if termo not in achados:
                achados.append(termo)
        return achados
