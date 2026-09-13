import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _fingerprint(base: Path) -> dict[str, str]:
    if not base.exists():
        return {}
    out = {}
    for p in sorted(base.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(base))] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return out


@pytest.fixture(scope="session", autouse=True)
def _suite_nao_escreve_nos_dados_do_projeto():
    """A suite roda em universos descartaveis e nao pode tocar os dados reais.

    Existe por causa do achado 1 da F3: um teste que escrevia no `data/raw` do
    projeto deixou o RAW no perfil `smoke` e a camada de verdade no perfil
    `dev`. A comparacao com o gabarito passou a produzir numeros plausiveis e
    falsos, e nada avisou. `check_provenance` passou a avisar; este guarda
    impede que volte a acontecer.

    Vale para RAW, verdade e referencia. Os tres sao entrada de julgamento: se
    o teste puder reescreve-los, o teste julga o proprio universo que criou.
    """
    alvos = {
        "data/raw": ROOT / "data" / "raw",
        "data/synthetic/truth": ROOT / "data" / "synthetic" / "truth",
        "data/reference": ROOT / "data" / "reference",
    }
    antes = {k: _fingerprint(v) for k, v in alvos.items()}
    yield
    sujos = [k for k, v in alvos.items() if _fingerprint(v) != antes[k]]
    assert not sujos, f"a suite escreveu nos dados do projeto: {sujos}"
