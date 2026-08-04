"""Motor de relacionamento entre nomes de Treinamentos e nomes de Colaboradores.

Nunca usa CPF como chave. Segue a ordem de regras definida no relatório técnico:
1) exata, 2) completo x abreviado (prefixo de tokens), 3) primeiro nome + último
sobrenome, 4) nomes intermediários, 5) ambiguidade -> revisão manual,
6) nenhum candidato -> não encontrado.
"""
from dataclasses import dataclass, field

from utils.normalizacao import normalizar_nome

RELACIONADO_AUTOMATICO = "RELACIONADO_AUTOMATICO"
RELACIONADO_MANUAL = "RELACIONADO_MANUAL"
REVISAO_MANUAL = "REVISAO_MANUAL"
NAO_ENCONTRADO = "NAO_ENCONTRADO"
NAO_ENCONTRADO_CONFIRMADO = "NAO_ENCONTRADO_CONFIRMADO"


@dataclass
class ResultadoMatch:
    situacao: str
    nome_colaborador_normalizado: str | None
    candidatos: list = field(default_factory=list)
    regra: str | None = None


def _tokens(nome_normalizado: str) -> list[str]:
    return nome_normalizado.split(" ") if nome_normalizado else []


def _regra_exata(nome: str, candidatos: list[str]) -> list[str]:
    return [c for c in candidatos if c == nome]


def _regra_completo_abreviado(nome: str, candidatos: list[str]) -> list[str]:
    tokens_a = _tokens(nome)
    achados = []
    for c in candidatos:
        tokens_b = _tokens(c)
        if not tokens_a or not tokens_b or tokens_a == tokens_b:
            continue
        menor, maior = (tokens_a, tokens_b) if len(tokens_a) < len(tokens_b) else (tokens_b, tokens_a)
        if maior[: len(menor)] == menor:
            achados.append(c)
    return achados


def _regra_primeiro_ultimo(nome: str, candidatos: list[str]) -> list[str]:
    tokens_a = _tokens(nome)
    if len(tokens_a) < 2:
        return []
    primeiro_a, ultimo_a = tokens_a[0], tokens_a[-1]
    achados = []
    for c in candidatos:
        tokens_b = _tokens(c)
        if len(tokens_b) < 2 or c == nome:
            continue
        if tokens_b[0] == primeiro_a and tokens_b[-1] == ultimo_a:
            achados.append(c)
    return achados


def _regra_nomes_intermediarios(nome: str, candidatos: list[str]) -> list[str]:
    tokens_a = _tokens(nome)
    if not tokens_a:
        return []
    primeiro_a = tokens_a[0]
    meio_a = set(tokens_a[1:])
    achados = []
    for c in candidatos:
        tokens_b = _tokens(c)
        if not tokens_b or c == nome:
            continue
        if tokens_b[0] == primeiro_a and meio_a & set(tokens_b[1:]):
            achados.append(c)
    return achados


_REGRAS = [
    ("exata", _regra_exata),
    ("completo_abreviado", _regra_completo_abreviado),
    ("primeiro_ultimo", _regra_primeiro_ultimo),
    ("nomes_intermediarios", _regra_nomes_intermediarios),
]


def relacionar_nome(nome_normalizado: str, candidatos_unicos: list[str]) -> ResultadoMatch:
    if not nome_normalizado:
        return ResultadoMatch(NAO_ENCONTRADO, None, [], None)
    for nome_regra, funcao in _REGRAS:
        achados = sorted(set(funcao(nome_normalizado, candidatos_unicos)))
        if len(achados) == 1:
            return ResultadoMatch(RELACIONADO_AUTOMATICO, achados[0], achados, nome_regra)
        if len(achados) > 1:
            return ResultadoMatch(REVISAO_MANUAL, None, achados, nome_regra)
    return ResultadoMatch(NAO_ENCONTRADO, None, [], None)


def relacionar_lote(nomes_normalizados_unicos: list[str], candidatos_unicos: list[str]) -> dict[str, ResultadoMatch]:
    """Roda o matching uma única vez por nome único (cache), retorna dict nome -> resultado."""
    return {nome: relacionar_nome(nome, candidatos_unicos) for nome in nomes_normalizados_unicos}


def aplicar_overrides(resultados: dict[str, ResultadoMatch], df_overrides) -> dict[str, ResultadoMatch]:
    """Aplica decisões manuais persistidas (revisoes_manuais.csv) por cima do resultado automático."""
    if df_overrides is None or df_overrides.empty:
        return resultados
    for _, linha in df_overrides.iterrows():
        nome = linha.get("nome_planilha_normalizado")
        decisao = linha.get("decisao")
        if not nome:
            continue
        if decisao == "RELACIONADO":
            resultados[nome] = ResultadoMatch(
                RELACIONADO_MANUAL,
                linha.get("nome_colaborador_normalizado"),
                [linha.get("nome_colaborador_normalizado")],
                "revisao_manual_rh",
            )
        elif decisao == "NAO_ENCONTRADO_CONFIRMADO":
            resultados[nome] = ResultadoMatch(NAO_ENCONTRADO_CONFIRMADO, None, [], "revisao_manual_rh")
    return resultados
