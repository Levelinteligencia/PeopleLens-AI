"""Modelo de risco de desligamento.

Nao e sorteio uniforme: a probabilidade mensal de saida depende de tempo de
casa, segmento, nivel, performance, engajamento, gestor, pais e ano.

Sobre o efeito de gestor (item 4 da aprovacao da F0): ele existe para
reproduzir um padrao plausivel de concentracao de risco, ou seja, o fato
observavel em organizacoes reais de que a rotatividade nao se distribui de
forma homogenea entre times equivalentes. E um mecanismo de heterogeneidade
organizacional, e nao um recurso para deixar o dashboard mais interessante.

Nota sobre causalidade (ADR-0015): os fatores abaixo sao ASSOCIACOES embutidas
no gerador por construcao. Eles nao autorizam nenhuma afirmacao causal sobre o
dataset resultante, nem devem ser apresentados como achado.
"""
from __future__ import annotations

import numpy as np

from ..config import Config


def annual_rate(cfg: Config, segment: str, year: int) -> float:
    """Probabilidade anual de saida POR PESSOA.

    Nao confundir com a taxa de turnover reportada, que e desligamentos sobre
    headcount medio. As duas divergem por reposicao: uma posicao pode girar mais
    de uma vez no ano. `realized_calibration` faz a ponte entre as duas.
    """
    tm = cfg.generation["turnover_modifiers"]
    base = cfg.segments[segment]["turnover_base"]
    mod = tm["by_year"].get(year, 1.0)
    calib = tm.get("realized_calibration", {}).get(segment, 1.0)
    return float(base * mod * calib)


def _band_factor(bands: list[dict], value: float, key: str) -> float:
    for b in bands:
        lo, hi = b[key]
        if lo <= value < hi:
            return float(b["factor"])
    return float(bands[-1]["factor"])


def tenure_factor(cfg: Config, tenure_months: int) -> float:
    curve = cfg.generation["termination_hazard"]["tenure_curve"]
    return _band_factor(curve, tenure_months, "months")


def performance_factor(cfg: Config, rating_std: str | None) -> float:
    curve = cfg.generation["termination_hazard"]["performance_curve"]
    key = (rating_std or "not_rated").lower().replace(" ", "_")
    return float(curve.get(key, curve["not_rated"]))


def level_factor(cfg: Config, job_level: str) -> float:
    return float(cfg.generation["termination_hazard"]["job_level_factor"][job_level])


def engagement_factor(cfg: Config, score: float | None) -> float:
    if score is None:
        return 1.0
    bands = cfg.generation["termination_hazard"]["engagement_factor"]["by_score_band"]
    return _band_factor(bands, float(score), "score")


def country_factor(cfg: Config, country: str) -> float:
    return float(cfg.generation["termination_hazard"]["country_factor"][country])


def draw_manager_effect(cfg: Config, rng: np.random.Generator) -> float:
    me = cfg.generation["termination_hazard"]["manager_effect"]
    lo, hi = me["clip"]
    return float(np.clip(rng.lognormal(mean=0.0, sigma=me["sigma"]), lo, hi))


def monthly_probabilities(
    cfg: Config,
    segment: str,
    year: int,
    scores: np.ndarray,
) -> np.ndarray:
    """Converte escores relativos de risco em probabilidade mensal.

    Os escores sao normalizados pela media da propria populacao do segmento no
    mes, de modo que a taxa agregada realizada respeita a taxa configurada em
    `config/generation.yaml` enquanto a heterogeneidade entre pessoas e
    preservada. Sem essa normalizacao, o produto dos multiplicadores explodiria
    a taxa alvo.
    """
    if scores.size == 0:
        return scores
    a = annual_rate(cfg, segment, year)
    monthly_target = 1.0 - (1.0 - a) ** (1.0 / 12.0)
    mean = float(scores.mean())
    if mean <= 0:
        return np.full_like(scores, monthly_target)
    p = monthly_target * (scores / mean)
    return np.clip(p, 0.0, 0.5)
