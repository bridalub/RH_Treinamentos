"""Tela de Login — identidade BRIDA, autenticação via usuarios.csv."""
import streamlit as st

from components.theme import CORES
from services.usuarios_service import autenticar
from services.logs_service import registrar
from utils.auth import iniciar_sessao


def render():
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] > .main { display:flex; align-items:center; justify-content:center; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col_esq, col_centro, col_dir = st.columns([1, 1.1, 1])
    with col_centro:
        st.markdown(
            f"""
            <div style="text-align:center; margin-top:4rem; margin-bottom:1.2rem;">
                <div style="width:64px;height:64px;border-radius:16px;background:{CORES['accent']};
                            display:flex;align-items:center;justify-content:center;margin:0 auto 1rem auto;
                            font-size:1.6rem;font-weight:800;color:white;">B</div>
                <h2 style="color:{CORES['texto_primario']};margin-bottom:4px;">BRIDA · Treinamentos</h2>
                <p style="color:{CORES['texto_secundario']};font-size:0.9rem;">Painel de acompanhamento de treinamentos e colaboradores</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("form_login", border=True):
            login = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True, type="primary")

        if entrar:
            usuario = autenticar(login.strip(), senha)
            if usuario is None:
                st.error("Usuário ou senha inválidos.")
                registrar(login or "desconhecido", "LOGIN_FALHOU")
            else:
                iniciar_sessao(usuario)
                registrar(usuario["login"], "LOGIN")
                st.rerun()
