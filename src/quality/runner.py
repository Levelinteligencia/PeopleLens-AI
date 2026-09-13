"""Runner proprio de Data Quality (ADR-0013).

Le os checks de `config/quality_checks.yaml`, executa, grava em
`data_quality_results` com severidade e classe de achado, e devolve as linhas
reprovadas por checks BLOCKER para a quarentena (ADR-0010).

O que este modulo NAO faz, por desenho: corrigir. Ele reprova. Corrigir dado
reprovado e decisao humana e acontece na fila de excecoes ou no proximo ciclo
de carga da fonte, nunca aqui. O teste
`test_runner_nao_altera_nenhuma_frame` exige isso valor a valor.

**Classe de achado (F5).** Reprovar nao e uma coisa so. Um salario negativo e
um departamento sem mapeamento aprovado sao os dois "fail", e sao problemas de
natureza diferente: o primeiro e dado errado, o segundo e decisao pendente. A
Sam fixou a distincao na abertura da F5:

    dado invalido != dado nao mapeado != decisao pendente
                  != identidade nao resolvida != dado quarentenado

Cada check declara `finding_class`, o resultado carrega a classe, e o trust
score usa a classe para dizer **de onde vem** a perda de confianca em vez de
somar tudo num numero so (ADR-0022).

Vocabulario de expectativas deliberadamente proximo ao do Great Expectations,
para que a familiaridade conceitual fique evidente na leitura do codigo. A
escolha de nao usar a ferramenta esta justificada no ADR-0013.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import polars as pl
import yaml

from generator.config import Config

# Classes de achado. Declaradas aqui e em quality_checks.yaml; o teste
# test_toda_classe_de_achado_declarada_existe exige que as duas listas batam.
FINDING_CLASSES = (
    "INVALIDO",                  # o valor viola uma regra e esta errado
    "NAO_MAPEADO",               # valor legitimo na origem, sem mapeamento aprovado
    "DECISAO_PENDENTE",          # ha decisao de negocio em aberto; nao existe resposta tecnica
    "IDENTIDADE_NAO_RESOLVIDA",  # a pessoa existe, o vinculo entre sistemas nao foi feito
    "AUSENCIA_LEGITIMA",         # o campo nao existia, ou nao declarar e opcao da pessoa
    "DIVERGENCIA",               # duas fontes discordam; nenhuma esta necessariamente errada
)

# Classes que representam pendencia de decisao ou de evidencia, e nao erro no
# dado. A distincao muda o trust status (ADR-0022).
PENDENCY_CLASSES = ("NAO_MAPEADO", "DECISAO_PENDENTE", "IDENTIDADE_NAO_RESOLVIDA",
                    "AUSENCIA_LEGITIMA")


def load_checks(cfg: Config) -> dict:
    with open(Path(cfg.root) / "config" / "quality_checks.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _key(name: str) -> tuple[str, str]:
    system, dataset = name.split(".", 1)
    return system, dataset


def _today() -> str:
    return date.today().isoformat()


# --------------------------------------------------------------------------- #
# Expectativas. Cada uma devolve (linhas reprovadas, linhas avaliadas).
#
# Coluna ausente devolve (vazio, 0), que o runner traduz em NOT_RUN. Nao e o
# mesmo que passar: um check que nao rodou nao e evidencia de qualidade, e o
# relatorio separa os dois.
# --------------------------------------------------------------------------- #
def _apply_filter(df: pl.DataFrame, f: dict | None) -> pl.DataFrame:
    """Recorte declarado do escopo do check.

    Existe por causa do achado 1 da F5: reconciliar duas fontes sem igualar o
    escopo mede a diferenca de escopo, nao a diferenca de dado. A folha cobre
    so o Brasil e so a partir de 2016; o HRIS corporativo cobre cinco paises e
    comeca em 2019. Comparar os dois inteiros responde uma pergunta que
    ninguem fez.

    O recorte fica declarado no YAML e nunca em codigo, pela mesma razao de
    sempre: recorte escondido e regra de negocio escondida.
    """
    if not f or df.is_empty():
        return df
    col = f["column"]
    if col not in df.columns:
        return df.head(0)
    out = df.filter(pl.col(col).is_not_null())
    if "equals" in f:
        out = out.filter(pl.col(col) == f["equals"])
    if "in" in f:
        out = out.filter(pl.col(col).is_in(f["in"]))
    if "min" in f:
        out = out.filter(pl.col(col) >= f["min"])
    if "max" in f:
        out = out.filter(pl.col(col) <= f["max"])
    return out


def _failing_rows(spec: dict, df: pl.DataFrame, frames: dict) -> tuple[pl.DataFrame, int]:
    e = spec["expectation"]
    col = spec.get("column")
    df = _apply_filter(df, spec.get("filter"))
    vazio = df.head(0)

    def falta(*cols: str) -> bool:
        return not set(c for c in cols if c) <= set(df.columns)

    # ------------------------------------------------------------ presenca
    if e == "expect_column_values_to_not_be_null":
        if falta(col):
            return vazio, 0
        return df.filter(pl.col(col).is_null()), df.height

    if e == "expect_column_values_to_not_be_in_set":
        # marcador de vazio disfarcado de valor: "N/A", "-", "0000", "SEM INFO"
        if falta(col):
            return vazio, 0
        sub = df.filter(pl.col(col).is_not_null())
        return sub.filter(pl.col(col).str.strip_chars().is_in(spec["value_set"])), sub.height

    # ------------------------------------------------------------- dominio
    if e == "expect_column_values_to_be_in_set":
        if falta(col):
            return vazio, 0
        sub = df.filter(pl.col(col).is_not_null())
        return sub.filter(~pl.col(col).is_in(spec["value_set"])), sub.height

    if e == "expect_column_values_to_not_equal":
        if falta(col):
            return vazio, 0
        sub = df.filter(pl.col(col).is_not_null())
        return sub.filter(pl.col(col) == spec["value"]), sub.height

    if e == "expect_distinct_count_between":
        if falta(col):
            return vazio, 0
        n = df[col].drop_nulls().n_unique()
        ok = spec["min_distinct"] <= n <= spec["max_distinct"]
        return (vazio if ok else df.head(1)), df.height

    # ------------------------------------------------------------- numerico
    if e == "expect_column_values_to_be_between":
        if falta(col):
            return vazio, 0
        sub = df.filter(pl.col(col).is_not_null())
        return sub.filter((pl.col(col) < spec["min"]) | (pl.col(col) > spec["max"])), sub.height

    if e == "expect_column_mean_to_be_between":
        if falta(col):
            return vazio, 0
        sub = df.filter(pl.col(col).is_not_null())
        if sub.is_empty():
            return vazio, 0
        media = sub[col].mean()
        ok = spec["min"] <= media <= spec["max"]
        return (vazio if ok else sub.head(1)), sub.height

    # --------------------------------------------------------------- texto
    if e == "expect_column_values_to_not_match_regex":
        if falta(col):
            return vazio, 0
        sub = df.filter(pl.col(col).is_not_null())
        return sub.filter(pl.col(col).str.contains(spec["regex"])), sub.height

    if e == "expect_column_values_to_match_regex":
        if falta(col):
            return vazio, 0
        sub = df.filter(pl.col(col).is_not_null())
        return sub.filter(~pl.col(col).str.contains(spec["regex"])), sub.height

    if e == "expect_column_value_lengths_to_be_between":
        if falta(col):
            return vazio, 0
        sub = df.filter(pl.col(col).is_not_null())
        n = pl.col(col).str.strip_chars().str.len_chars()
        return sub.filter((n < spec["min_length"]) | (n > spec["max_length"])), sub.height

    # ----------------------------------------------------------------- data
    if e == "expect_parse_ok":
        flag = f"{col}__parse"
        if falta(flag):
            return vazio, 0
        sub = df.filter(pl.col(flag) != "vazio")
        return sub.filter(pl.col(flag) != "ok"), sub.height

    if e == "expect_not_ambiguous":
        flag = f"{col}__ambiguous"
        if falta(flag):
            return vazio, 0
        return df.filter(pl.col(flag) == True), df.height  # noqa: E712

    if e == "expect_date_between":
        # opera sobre coluna ISO ja convertida; comparacao lexical serve
        if falta(col):
            return vazio, 0
        mx = spec.get("max_date") or _today()
        sub = df.filter(pl.col(col).is_not_null() & (pl.col(col) != ""))
        return sub.filter((pl.col(col) < spec["min_date"]) | (pl.col(col) > mx)), sub.height

    if e == "expect_column_a_to_be_before_b":
        a, b = col, spec["column_b"]
        if falta(a, b):
            return vazio, 0
        sub = df.filter(pl.col(a).is_not_null() & pl.col(b).is_not_null()
                        & (pl.col(a) != "") & (pl.col(b) != ""))
        return sub.filter(pl.col(b) < pl.col(a)), sub.height

    if e == "expect_max_date_after":
        if falta(col):
            return vazio, 0
        mx = df[col].drop_nulls().max()
        ok = mx is not None and str(mx) >= spec["min_date"]
        return (vazio if ok else df.head(1)), df.height

    if e == "expect_date_gap_below":
        """Maior intervalo entre datas consecutivas de um snapshot.

        Detecta buraco de carga (D18): a serie chega ao fim e mesmo assim tem
        meses faltando no meio, que uma verificacao de data maxima nao pega.
        """
        if falta(col):
            return vazio, 0
        datas = sorted({d[:7] for d in df[col].drop_nulls().to_list() if d})
        if len(datas) < 2:
            return vazio, 0
        def idx(m: str) -> int:
            a, b = m.split("-")
            return int(a) * 12 + int(b)
        maior = max(idx(b) - idx(a) for a, b in zip(datas, datas[1:]))
        ok = maior <= spec["max_gap_months"]
        return (vazio if ok else df.head(1)), len(datas)

    # ----------------------------------------------------------- unicidade
    if e == "expect_column_values_to_be_unique":
        if falta(col):
            return vazio, 0
        dup = df.group_by(col).len().filter(pl.col("len") > 1)[col].to_list()
        return df.filter(pl.col(col).is_in(dup)), df.height

    if e == "expect_compound_columns_to_be_unique":
        cols = spec["columns"]
        if falta(*cols):
            return vazio, 0
        dup = df.group_by(cols).len().filter(pl.col("len") > 1).drop("len")
        return df.join(dup, on=cols, how="inner"), df.height

    # ------------------------------------------------ integridade referencial
    if e == "expect_column_values_to_be_in_reference":
        ref = frames.get(_key(spec["reference_dataset"]))
        if ref is None or falta(col) or spec["reference_column"] not in ref.columns:
            return vazio, 0
        valid = set(ref[spec["reference_column"]].drop_nulls().to_list())
        sub = df.filter(pl.col(col).is_not_null())
        return sub.filter(~pl.col(col).is_in(list(valid))), sub.height

    if e == "expect_identity_resolved":
        """Cobertura de identidade: quantos registros deste sistema tem vinculo
        RESOLVED no xref.

        Falhar aqui NAO significa dado errado. Significa que o vinculo entre
        sistemas nao foi estabelecido, que e a classe IDENTIDADE_NAO_RESOLVIDA.

        Guarda contra chave errada: se a coluna declarada nao tem NENHUMA
        intersecao com o universo de chaves do sistema no xref, o check nao
        esta medindo cobertura baixa, esta comparando coisas diferentes. Nesse
        caso ele nao roda, em vez de reportar 100% de nao resolvido, que e um
        numero plausivel para um sistema de identidade fraca e por isso
        ninguem questionaria (mesma familia do achado 2 da F3).
        """
        xref = frames.get(("CONFORMED", "identity_xref"))
        if xref is None or falta(col):
            return vazio, 0
        system = spec.get("identity_system")
        do_sistema = xref.filter(pl.col("source_system") == system) if system else xref
        universo = set(do_sistema["source_employee_id"].to_list())
        sub = df.filter(pl.col(col).is_not_null())
        if sub.is_empty() or not universo:
            return vazio, 0
        presentes = set(sub[col].to_list())
        if not (presentes & universo):
            return vazio, 0   # chave incompativel: NOT_RUN, nao 100% de falha
        resolvidos = set(do_sistema.filter(pl.col("match_status") == "RESOLVED")
                         ["source_employee_id"].to_list())
        return sub.filter(~pl.col(col).is_in(list(resolvidos))), sub.height

    # ------------------------------------------------------- reconciliacao
    if e == "expect_row_count_ratio_between":
        ref = _apply_filter(frames.get(_key(spec["reference_dataset"])),
                            spec.get("reference_filter"))
        if ref is None or df.is_empty() or ref.is_empty():
            return vazio, 0
        ratio = df.height / ref.height
        ok = spec["min_ratio"] <= ratio <= spec["max_ratio"]
        return (vazio if ok else df.head(1)), df.height

    if e == "expect_group_count_ratio_between":
        """Reconciliacao periodo a periodo, nao no total.

        Comparar so o total esconde duas coisas. A primeira e compensacao: um
        mes 20% acima e outro 20% abaixo fecham em zero. A segunda e diferenca
        de vigencia: periodo em que so uma das fontes existe entra no total e
        dilui a razao. O `join` interno aqui resolve as duas, porque so compara
        periodo que existe dos dois lados.
        """
        ref = _apply_filter(frames.get(_key(spec["reference_dataset"])),
                            spec.get("reference_filter"))
        gcol, rcol = spec["group_column"], spec["reference_group_column"]
        if ref is None or falta(gcol) or rcol not in ref.columns:
            return vazio, 0
        a = df.with_columns(pl.col(gcol).str.slice(0, 7).alias("_g")).group_by("_g").len()
        b = ref.with_columns(pl.col(rcol).str.slice(0, 7).alias("_g")).group_by("_g").len()
        j = a.join(b, on="_g", how="inner", suffix="_ref")
        if j.is_empty():
            return vazio, 0
        j = j.with_columns((pl.col("len") / pl.col("len_ref")).alias("_ratio"))
        fora = j.filter((pl.col("_ratio") < spec["min_ratio"]) | (pl.col("_ratio") > spec["max_ratio"]))
        return df.head(min(fora.height, df.height)), j.height

    if e == "expect_sum_ratio_between":
        ref = _apply_filter(frames.get(_key(spec["reference_dataset"])),
                            spec.get("reference_filter"))
        rcol = spec["reference_column"]
        if ref is None or falta(col) or rcol not in ref.columns:
            return vazio, 0
        a, b = df[col].drop_nulls().sum(), ref[rcol].drop_nulls().sum()
        if not b:
            return vazio, 0
        ratio = a / b
        ok = spec["min_ratio"] <= ratio <= spec["max_ratio"]
        return (vazio if ok else df.head(1)), df.height

    raise ValueError(f"expectativa desconhecida: {e}")


# --------------------------------------------------------------------------- #
def _expose_identity(frames: dict, xref: pl.DataFrame | None) -> dict:
    """Expoe a camada de identidade como dois datasets consultaveis.

    `CONFORMED.identity` e o universo de employee_id conformados, usado como
    referencia por checks de integridade (ADR-0019). `CONFORMED.identity_xref`
    e a tabela de vinculos, usada pelos checks de cobertura de identidade.
    """
    if xref is None or xref.is_empty():
        return frames
    frames = dict(frames)
    frames[("CONFORMED", "identity")] = xref.filter(
        pl.col("employee_id").is_not_null()).select(
        pl.col("employee_id").cast(pl.Utf8).alias("employee_id")).unique()
    frames[("CONFORMED", "identity_xref")] = xref.select([
        pl.col("source_system"),
        pl.col("source_employee_id").cast(pl.Utf8).alias("source_employee_id"),
        pl.col("employee_id").cast(pl.Utf8).alias("employee_id"),
        pl.col("match_status"), pl.col("match_method")])
    return frames


def run_for_cut(cfg: Config, frames: dict[tuple[str, str], pl.DataFrame],
                cut: dict[tuple[str, str], dict], xref: pl.DataFrame | None = None,
                only: set[str] | None = None, catalog_cache: dict | None = None) -> dict[str, dict]:
    """Executa o catalogo restrito a um recorte, para o trust score por recorte.

    `cut` mapeia dataset -> filtro adicional. Dataset que nao esta no `cut` fica
    de fora: um check sobre dataset que o recorte nao alcanca **nao e um check
    que passou**, e contar como passado inflaria a confianca do recorte
    exatamente onde ha menos evidencia (ADR-0022).

    Devolve {check_id: {failure_rate, records_checked, status}} apenas para os
    checks que efetivamente rodaram no recorte.
    """
    catalog = catalog_cache or load_checks(cfg)
    frames = _expose_identity(frames, xref)
    out: dict[str, dict] = {}
    for spec in catalog["checks"]:
        if only and spec["check_id"] not in only:
            continue
        key = _key(spec["dataset"])
        extra = cut.get(key)
        if extra is None or key not in frames:
            continue
        df = _apply_filter(frames[key], extra)
        if df.is_empty():
            continue
        failed, checked = _failing_rows(spec, df, frames)
        if not checked:
            continue
        rate = failed.height / checked
        out[spec["check_id"]] = {
            "failure_rate": rate, "records_checked": checked,
            "records_failed": failed.height,
            "status": "PASS" if rate <= spec["threshold"]["max_failure_rate"] else "FAIL"}
    return out


def run_all(cfg: Config, frames: dict[tuple[str, str], pl.DataFrame], lineage,
            xref: pl.DataFrame | None = None) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Executa o catalogo. Devolve (data_quality_results, linhas a quarentenar).

    Nao altera nenhuma frame de entrada. As unicas saidas sao os dois
    dataframes de metadados.
    """
    catalog = load_checks(cfg)
    frames = _expose_identity(frames, xref)
    run_at = datetime.utcnow().isoformat(timespec="seconds")
    results: list[dict] = []
    quarantine: list[dict] = []

    for spec in catalog["checks"]:
        system, dataset = _key(spec["dataset"])
        base = dict(check_id=spec["check_id"], name=spec["name"], dimension=spec["dimension"],
                    severity=spec["severity"], finding_class=spec["finding_class"],
                    dataset=spec["dataset"], source_system=system,
                    threshold=spec["threshold"]["max_failure_rate"], run_date=run_at)
        df = frames.get((system, dataset))
        if df is None:
            results.append({**base, "records_checked": 0, "records_failed": 0,
                            "failure_rate": None, "status": "NOT_RUN"})
            continue

        failed, checked = _failing_rows(spec, df, frames)
        if not checked:
            results.append({**base, "records_checked": 0, "records_failed": 0,
                            "failure_rate": None, "status": "NOT_RUN"})
            continue

        rate = failed.height / checked
        limite = spec["threshold"]["max_failure_rate"]
        status = "PASS" if rate <= limite else "FAIL"
        results.append({**base, "records_checked": checked, "records_failed": failed.height,
                        "failure_rate": round(rate, 6), "status": status})

        # Quarentena e acionada por REGRA, nao por resultado agregado: a linha
        # reprovada por um check BLOCKER sai, mesmo que o check como um todo
        # tenha passado dentro do limiar. O limiar governa o status do check; a
        # severidade governa o destino da linha (ADR-0010).
        if spec["severity"] == "BLOCKER" and failed.height:
            for r in failed.to_dicts():
                quarantine.append(dict(
                    quarantine_id=f"Q{len(quarantine) + 1:08d}",
                    source_system=system, dataset=dataset,
                    record_id=r.get("_row_id"), failed_rule=spec["check_id"],
                    failed_rule_name=spec["name"], finding_class=spec["finding_class"],
                    original_value=str(r.get(spec.get("column"))) if spec.get("column") else None,
                    severity=spec["severity"], detected_at=run_at,
                    resolution_status="OPEN", resolution_action=None,
                ))

    res = pl.DataFrame(results, infer_schema_length=None)
    qua = pl.DataFrame(quarantine, infer_schema_length=None) if quarantine else pl.DataFrame(
        schema={"quarantine_id": pl.Utf8, "source_system": pl.Utf8, "dataset": pl.Utf8,
                "record_id": pl.Utf8, "failed_rule": pl.Utf8, "failed_rule_name": pl.Utf8,
                "finding_class": pl.Utf8, "original_value": pl.Utf8, "severity": pl.Utf8,
                "detected_at": pl.Utf8, "resolution_status": pl.Utf8, "resolution_action": pl.Utf8})
    lineage.object("metadata", "data_quality_results", "dataset", "conformed.*",
                   f"execucao de {len(catalog['checks'])} checks declarados", rows=res.height)
    lineage.object("metadata", "data_quarantine", "dataset", "conformed.*",
                   "desvio lateral das linhas reprovadas por check BLOCKER", rows=qua.height)
    return res, qua


def write(cfg: Config, results: pl.DataFrame, quarantine: pl.DataFrame) -> Path:
    base = Path(cfg.root) / "data" / "processed" / "metadata"
    base.mkdir(parents=True, exist_ok=True)
    results.write_parquet(base / "data_quality_results.parquet", compression="zstd")
    if not quarantine.is_empty():
        quarantine.write_parquet(base / "data_quarantine.parquet", compression="zstd")
    return base
