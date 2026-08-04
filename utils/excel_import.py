"""Leitura das planilhas de origem (BASE FUNCIONÁRIOS e DTB Bridalub - Por Usuário).

Não altera a estrutura original das planilhas — apenas lê e extrai o que o
sistema precisa. Toda a validação da aba oficial de treinamentos vive aqui.
"""
import re

import pandas as pd

ABA_OFICIAL_TREINAMENTOS = "DTB Bridalub - Por Usuário (2)"
ABA_RESUMO_PROIBIDA = "DTB Bridalub - Por Usuário"
ABA_COLABORADORES = "BASE COMERCIAL"

_ESPACOS_RE = re.compile(r"\s+")


class AbaOficialNaoEncontradaError(Exception):
    """Levantado quando a aba oficial de treinamentos não existe no arquivo enviado."""


class ColunaEsperadaNaoEncontradaError(Exception):
    """Levantado quando a estrutura da planilha não bate com o esperado."""


def _normalizar_nome_aba(nome: str) -> str:
    return _ESPACOS_RE.sub(" ", str(nome)).strip()


def encontrar_aba_oficial(xls: pd.ExcelFile) -> str:
    """Localiza, de forma tolerante a espaçamento, a aba oficial 'DTB Bridalub - Por Usuário (2)'.

    Interrompe a importação (levanta AbaOficialNaoEncontradaError) se a aba não existir,
    mesmo que exista uma aba de resumo com nome parecido.
    """
    alvo = _normalizar_nome_aba(ABA_OFICIAL_TREINAMENTOS)
    for nome_aba in xls.sheet_names:
        if _normalizar_nome_aba(nome_aba) == alvo:
            return nome_aba
    raise AbaOficialNaoEncontradaError(
        f"A aba oficial \"{ABA_OFICIAL_TREINAMENTOS}\" não foi encontrada no arquivo. "
        f"Abas disponíveis: {', '.join(xls.sheet_names)}. "
        "A importação foi interrompida para não usar a aba de resumo por engano."
    )


def _localizar_linha_cabecalho(df_bruto: pd.DataFrame) -> int:
    """Encontra a linha onde a tabela de dados realmente começa (procura a célula 'Distribuidor')."""
    primeira_coluna = df_bruto.iloc[:, 0].astype(str).str.strip()
    candidatos = primeira_coluna[primeira_coluna == "Distribuidor"]
    if candidatos.empty:
        raise ColunaEsperadaNaoEncontradaError(
            "Não foi possível localizar a linha de cabeçalho (coluna 'Distribuidor') "
            "na aba oficial de treinamentos. O layout do relatório pode ter mudado."
        )
    return int(candidatos.index[0])


def _extrair_metadados(df_bruto: pd.DataFrame, linha_cabecalho: int) -> dict:
    metadados = {}
    bloco = df_bruto.iloc[:linha_cabecalho, :2]
    for _, linha in bloco.iterrows():
        chave = str(linha.iloc[0]).strip() if pd.notna(linha.iloc[0]) else ""
        if chave.endswith(":"):
            metadados[chave.rstrip(":")] = linha.iloc[1] if pd.notna(linha.iloc[1]) else None
    return metadados


RENOMEIO_COLUNAS_TREINAMENTOS = {
    "Distribuidor": "distribuidor",
    "Nome": "nome_colaborador_planilha",
    "CPF": "cpf",
    "Título do Treinamento": "titulo_treinamento",
    "Status da Minha Formação": "status",
    "Data de Inscrição da Minha Formação": "data_inscricao",
    "Data de Conclusão da Minha Formação": "data_conclusao",
    "DTB Líder": "dtb_lider",
    "DTB Área": "dtb_area",
    "DTB LOB": "dtb_lob",
    "DTB Cargo": "dtb_cargo",
    "DTB Data Desligamento": "dtb_data_desligamento",
    "Última Data de Contratação do Usuário": "data_contratacao",
    "Último Acesso do Usuário": "ultimo_acesso",
    "Tipo de Treino": "tipo_treino",
}


def ler_planilha_treinamentos(caminho_arquivo) -> tuple[pd.DataFrame, dict]:
    """Lê a aba oficial de treinamentos. Levanta AbaOficialNaoEncontradaError se a aba não existir.

    Retorna (dataframe_dados, metadados_do_relatorio). metadados inclui
    'Contagem de Registros' (declarada) e 'linhas_lidas' (real) para o sistema
    poder alertar quando o export estiver parcial.
    """
    xls = pd.ExcelFile(caminho_arquivo)
    nome_aba = encontrar_aba_oficial(xls)

    df_bruto = xls.parse(nome_aba, header=None)
    linha_cabecalho = _localizar_linha_cabecalho(df_bruto)
    metadados = _extrair_metadados(df_bruto, linha_cabecalho)

    df = xls.parse(nome_aba, header=linha_cabecalho)
    df = df.rename(columns=RENOMEIO_COLUNAS_TREINAMENTOS)
    colunas_esperadas = list(RENOMEIO_COLUNAS_TREINAMENTOS.values())
    faltando = [c for c in colunas_esperadas if c not in df.columns]
    if faltando:
        raise ColunaEsperadaNaoEncontradaError(
            f"As colunas esperadas não foram encontradas na aba oficial: {faltando}"
        )
    df = df[colunas_esperadas].dropna(how="all")

    metadados["linhas_lidas"] = len(df)
    try:
        contagem_declarada = int(str(metadados.get("Contagem de Registros", "")).strip())
    except (TypeError, ValueError):
        contagem_declarada = None
    metadados["contagem_declarada"] = contagem_declarada
    metadados["export_parcial"] = bool(
        contagem_declarada is not None and contagem_declarada != len(df)
    )

    return df, metadados


def ler_planilha_colaboradores(caminho_arquivo) -> pd.DataFrame:
    """Lê a planilha BASE FUNCIONÁRIOS BRIDA (aba 'BASE COMERCIAL') sem alterar sua estrutura original."""
    xls = pd.ExcelFile(caminho_arquivo)
    if ABA_COLABORADORES not in xls.sheet_names:
        raise ColunaEsperadaNaoEncontradaError(
            f"A aba \"{ABA_COLABORADORES}\" não foi encontrada em {caminho_arquivo}. "
            f"Abas disponíveis: {', '.join(xls.sheet_names)}."
        )
    df = xls.parse(ABA_COLABORADORES, header=0)
    df = df.dropna(how="all")
    return df
