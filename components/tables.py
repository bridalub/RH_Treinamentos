"""ListView moderna reutilizável (wrapper sobre st.dataframe com formatação BRIDA)."""
import pandas as pd
import streamlit as st

from utils.formatacao import formatar_data_br


def listview(
    df: pd.DataFrame, altura: int = 460,
    colunas_data: list[str] | None = None, colunas_data_sem_hora: list[str] | None = None,
):
    """colunas_data / colunas_data_sem_hora: nomes de coluna a formatar no padrão
    brasileiro (DD/MM/AAAA HH:mm ou DD/MM/AAAA) antes de exibir a tabela."""
    if colunas_data or colunas_data_sem_hora:
        df = df.copy()
        for coluna in colunas_data or []:
            if coluna in df.columns:
                df[coluna] = df[coluna].map(lambda v: formatar_data_br(v, com_hora=True))
        for coluna in colunas_data_sem_hora or []:
            if coluna in df.columns:
                df[coluna] = df[coluna].map(lambda v: formatar_data_br(v, com_hora=False))

    st.dataframe(df, use_container_width=True, hide_index=True, height=altura)
