"""Gerenciamento de usuários do sistema (apenas perfil ADMIN)."""
import streamlit as st

from components import tables
from services.usuarios_service import carregar_usuarios, criar_usuario, alterar_status, redefinir_senha, PERFIS
from services.logs_service import registrar
from utils.auth import usuario_atual


def render():
    st.markdown("## Usuários")

    login_atual = usuario_atual()["login"]
    df = carregar_usuarios()

    # ações administrativas ficam escondidas por padrão — só abrem quando o
    # admin clica — lado a lado na mesma linha, acima da lista de usuários.
    col_novo, col_status, col_senha = st.columns(3)

    with col_novo, st.expander("➕ Novo usuário"):
        with st.form("form_novo_usuario"):
            login = st.text_input("Login")
            nome = st.text_input("Nome completo")
            senha = st.text_input("Senha", type="password")
            perfil = st.selectbox("Perfil", PERFIS)
            criar = st.form_submit_button("Criar usuário", type="primary", use_container_width=True)

        if criar:
            if not login or not nome or not senha:
                st.warning("Preencha login, nome e senha.")
            else:
                ok, resultado = criar_usuario(login.strip(), nome.strip(), senha, perfil)
                if ok:
                    registrar(login_atual, "CRIAR_USUARIO", f"{login} ({perfil})")
                    st.success("Usuário criado com sucesso.")
                    st.rerun()
                else:
                    st.error(resultado)

    with col_status, st.expander("🔄 Ativar / Desativar"):
        usuario_alvo = st.selectbox("Usuário", df["login"].tolist(), key="sel_status")
        cb1, cb2 = st.columns(2)
        if cb1.button("Ativar", use_container_width=True):
            uid = df.loc[df["login"] == usuario_alvo, "usuario_id"].iloc[0]
            alterar_status(uid, True)
            registrar(login_atual, "ATIVAR_USUARIO", usuario_alvo)
            st.rerun()
        if cb2.button("Desativar", use_container_width=True):
            uid = df.loc[df["login"] == usuario_alvo, "usuario_id"].iloc[0]
            alterar_status(uid, False)
            registrar(login_atual, "DESATIVAR_USUARIO", usuario_alvo)
            st.rerun()

    with col_senha, st.expander("🔑 Redefinir senha"):
        with st.form("form_redefinir_senha"):
            usuario_redef = st.selectbox("Usuário", df["login"].tolist(), key="sel_redef")
            nova_senha = st.text_input("Nova senha", type="password")
            redefinir = st.form_submit_button("Redefinir senha", use_container_width=True)

        if redefinir:
            if not nova_senha:
                st.warning("Informe a nova senha.")
            else:
                uid = df.loc[df["login"] == usuario_redef, "usuario_id"].iloc[0]
                redefinir_senha(uid, nova_senha)
                registrar(login_atual, "REDEFINIR_SENHA", usuario_redef)
                st.success("Senha redefinida com sucesso.")

    st.markdown("#### Usuários cadastrados")
    tabela = df[["login", "nome", "perfil", "ativo", "criado_em", "ultimo_login"]]
    tables.listview(tabela, altura=min(360, 60 + 36 * len(tabela)), colunas_data=["criado_em", "ultimo_login"])
