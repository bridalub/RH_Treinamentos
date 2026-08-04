"""Auditoria: histórico de ações realizadas no sistema."""
import pandas as pd
import streamlit as st

from components import tables
from services.logs_service import carregar_logs, limpar_logs_antigos, registrar
from services.usuarios_service import carregar_usuarios
from utils.auth import usuario_atual
from utils.formatacao import MESES

_OPCOES_LIMPEZA = {
    "Mais antigos que 10 dias": 10,
    "Mais antigos que 1 mês": 30,
    "Todos os registros": None,
}


def render():
    st.markdown("## Logs")

    df = carregar_logs()
    if df.empty:
        st.info("Nenhuma ação registrada ainda.")
        return

    df = df.copy()
    df["_data_hora_dt"] = pd.to_datetime(df["data_hora"], errors="coerce")

    # o log grava o login (identificador estável); a tela mostra o nome da
    # pessoa — se o usuário foi excluído depois, cai no login como reserva.
    usuarios = carregar_usuarios()
    mapa_nome = dict(zip(usuarios["login"], usuarios["nome"]))
    df["Usuário"] = df["usuario"].map(mapa_nome).fillna(df["usuario"])

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        usuario_sel = st.selectbox("Usuário", ["Todos"] + sorted(df["Usuário"].unique()))
    with col2:
        acao_sel = st.selectbox("Ação", ["Todas"] + sorted(df["acao"].unique()))
    with col3:
        anos_disponiveis = sorted(df["_data_hora_dt"].dt.year.dropna().unique().astype(int), reverse=True)
        ano_sel = st.selectbox("Ano", ["Todos"] + [str(a) for a in anos_disponiveis])
    with col4:
        mes_sel_nome = st.selectbox("Mês", ["Todos"] + MESES)

    resultado = df
    if usuario_sel != "Todos":
        resultado = resultado[resultado["Usuário"] == usuario_sel]
    if acao_sel != "Todas":
        resultado = resultado[resultado["acao"] == acao_sel]
    if ano_sel != "Todos":
        resultado = resultado[resultado["_data_hora_dt"].dt.year == int(ano_sel)]
    if mes_sel_nome != "Todos":
        resultado = resultado[resultado["_data_hora_dt"].dt.month == MESES.index(mes_sel_nome) + 1]

    if resultado.empty:
        st.info("Nenhum registro encontrado para esse filtro.")
    else:
        resultado = resultado.sort_values("data_hora", ascending=False)
        tabela = resultado[["log_id", "data_hora", "Usuário", "acao", "detalhes"]].rename(
            columns={"log_id": "ID", "data_hora": "Data/Hora", "acao": "Ação", "detalhes": "Detalhes"}
        )
        tables.listview(tabela, altura=520, colunas_data=["Data/Hora"])

    _secao_limpeza(len(df))


def _secao_limpeza(total_atual: int):
    with st.expander("🧹 Limpar registros antigos"):
        st.caption(
            f"{total_atual} registro(s) no total. A limpeza remove sempre do mais antigo para o mais novo, "
            "a partir do período escolhido — não afeta os filtros acima."
        )
        opcao = st.selectbox("Remover registros...", list(_OPCOES_LIMPEZA.keys()), key="logs_limpar_opcao")
        confirmar = st.checkbox("Confirmo que quero excluir esses registros permanentemente", key="logs_limpar_confirma")
        if st.button("🗑️ Limpar registros", disabled=not confirmar, type="primary"):
            usuario = usuario_atual()
            login_atual = usuario["login"] if usuario else "sistema"
            removidos = limpar_logs_antigos(_OPCOES_LIMPEZA[opcao])
            if removidos:
                registrar(login_atual, "LOGS_LIMPOS", f"{removidos} registro(s) removido(s) — {opcao}")
                st.success(f"{removidos} registro(s) removido(s).")
            else:
                st.info("Nenhum registro corresponde a esse período.")
            st.rerun()
