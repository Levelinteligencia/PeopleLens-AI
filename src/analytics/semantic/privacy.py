"""Supressão por privacidade linha a linha (G-01, ADR-0007).

O `minimum_n` do ADR-0007 sempre foi supressão por **privacidade**, não por
qualidade: "o grupo é pequeno demais para preservar anonimato" é diferente de
"não confio no dado". O que faltava era o **grão** em que ele é avaliado.

Até aqui a camada semântica comparava `minimum_n` com a população agregada do
resultado. Numa quebra por dimensão isso protege a pergunta e não a pessoa:

    women_in_leadership por país, 2019-06, minimum_n = 20

        AR   0,6667   n =  6      <- passa, porque o total passa
        BR   0,5333   n = 75
        CO      —     n =  1      <- revela o gênero de UMA pessoa

O total (82) passa no mínimo, e a linha do CO expõe uma pessoa. É a proteção
falhando exatamente onde ela existe para funcionar.

Este módulo aplica o **mesmo** `minimum_n`, no grão certo. Nenhum limiar novo é
criado, nenhuma definição de KPI muda.

## Por que não basta suprimir a linha pequena

Suprimir só a linha pequena resolve metade do problema e cria a outra metade. Se
exatamente uma linha for suprimida, o total da mesma consulta sem quebra
continua disponível por `get_kpi`, e a subtração devolve a linha protegida:

    total conhecido 82  −  BR 75  −  AR 6  =  1     <- o CO, de volta

É divulgação por complemento, e é tão eficaz quanto ler o valor. Por isso, se
uma única linha ficar suprimida, **a menor linha restante é suprimida junto**,
de forma que o resíduo nunca seja atribuível a um recorte só. É supressão
complementar, e é a parte que não se pode pular.

A chave da linha continua visível. Saber que o Chile aparece na quebra não é o
valor protegido; o valor protegido é quantas pessoas há nele e quanto elas
medem.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Campos que carregam o valor protegido, ou permitem reconstruí-lo. Todos saem
# da linha suprimida: devolver `numerador` e `denominador` de uma razão entrega
# a razão e a população de brinde.
CAMPOS_DE_VALOR = ("valor", "numerador", "denominador", "populacao")

MOTIVO_PRIMARIA = "ABAIXO_DO_MINIMO"
MOTIVO_COMPLEMENTAR = "COMPLEMENTAR"


@dataclass
class Resultado:
    linhas: list[dict]
    suprimidas: int = 0
    publicadas: int = 0
    populacao_publicada: int = 0
    minimum_n: int = 0
    complementares: int = 0
    tudo_suprimido: bool = False

    @property
    def houve_supressao(self) -> bool:
        return self.suprimidas > 0

    def to_dict(self) -> dict:
        return dict(motivo="PRIVACIDADE", minimum_n=self.minimum_n,
                    linhas_publicadas=self.publicadas,
                    linhas_suprimidas=self.suprimidas,
                    supressoes_complementares=self.complementares,
                    nota=("supressao por privacidade, nao por qualidade do dado; "
                          "a populacao das linhas suprimidas nao e divulgada"))


def _populacao(linha: dict) -> int:
    return int(linha.get("populacao") or 0)


def _suprime(linha: dict, motivo: str) -> dict:
    """Apaga o valor protegido e mantém a chave do recorte.

    A população sai junto. Publicar "o Chile tem 1 pessoa em liderança e o valor
    é reservado" protege o número e entrega a pessoa.
    """
    saida = {k: v for k, v in linha.items() if k not in CAMPOS_DE_VALOR}
    saida["valor"] = None
    saida["populacao"] = None
    saida["suprimido"] = True
    saida["motivo_supressao"] = motivo
    return saida


def aplicar(linhas: list[dict], minimum_n: int, dimensoes: list[str],
            plano=None) -> Resultado:
    """Aplica `minimum_n` a cada linha do resultado.

    Sem dimensões não há quebra, e a avaliação agregada de quem chama já cobre o
    caso: as linhas voltam marcadas como publicadas, sem alteração.
    """
    linhas = [dict(l) for l in linhas]

    if not dimensoes or minimum_n <= 0:
        for l in linhas:
            l["suprimido"] = False
        return Resultado(linhas=linhas, publicadas=len(linhas),
                         populacao_publicada=sum(_populacao(l) for l in linhas),
                         minimum_n=minimum_n)

    # 1. Supressão primária: a linha não atinge o mínimo.
    #    Fronteira: população IGUAL a `minimum_n` publica. O mínimo é o que
    #    basta, não o que falta.
    abaixo = [i for i, l in enumerate(linhas) if _populacao(l) < minimum_n]

    # 2. Supressão complementar: uma única linha suprimida é reconstruível por
    #    subtração contra o total, que a mesma consulta sem quebra devolve.
    complementares: list[int] = []
    if len(abaixo) == 1 and len(linhas) >= 2:
        restantes = [i for i in range(len(linhas)) if i not in abaixo]
        vitima = min(restantes, key=lambda i: (_populacao(linhas[i]), i))
        complementares.append(vitima)

    alvo = set(abaixo) | set(complementares)

    saida = []
    for i, l in enumerate(linhas):
        if i in complementares:
            saida.append(_suprime(l, MOTIVO_COMPLEMENTAR))
        elif i in abaixo:
            saida.append(_suprime(l, MOTIVO_PRIMARIA))
        else:
            l["suprimido"] = False
            saida.append(l)

    publicadas = [l for l in saida if not l["suprimido"]]
    return Resultado(
        linhas=saida,
        suprimidas=len(alvo),
        publicadas=len(publicadas),
        populacao_publicada=sum(_populacao(l) for l in publicadas),
        minimum_n=minimum_n,
        complementares=len(complementares),
        tudo_suprimido=bool(saida) and not publicadas,
    )
