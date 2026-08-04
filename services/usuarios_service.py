"""CRUD e autenticação de usuários do sistema (usuarios.csv)."""
import os

import pandas as pd
import streamlit as st

from utils.csv_io import ler_csv, salvar_csv
from utils.auth import hash_senha, verificar_senha
from utils.formatacao import agora_br

COLUNAS = ["usuario_id", "login", "nome", "senha_hash", "perfil", "ativo", "criado_em", "ultimo_login"]

PERFIS = ["ADMIN", "RH", "GESTOR", "VISUALIZADOR"]

LOGIN_ADMIN_PADRAO = "admin"


def _senha_admin_padrao() -> str:
    """Nunca fica hardcoded no código (isso vazaria pro histórico do Git assim
    que o repositório for público/compartilhado). Vem de st.secrets em
    produção (Streamlit Cloud: Settings > Secrets, chave ADMIN_SENHA_PADRAO)
    ou da variável de ambiente de mesmo nome em execução local. Sem nenhum
    dos dois, usa um valor de desenvolvimento óbvio — nunca deve chegar em
    produção assim; troque a senha do admin pela tela de Usuários assim que
    logar pela primeira vez."""
    try:
        valor = st.secrets.get("ADMIN_SENHA_PADRAO")
    except Exception:
        valor = None
    return valor or os.environ.get("ADMIN_SENHA_PADRAO") or "TROQUE-ESTA-SENHA-0000"


def carregar_usuarios() -> pd.DataFrame:
    df = ler_csv("usuarios", COLUNAS)
    if df.empty:
        df = _seed_admin(df)
    return df


def _seed_admin(df: pd.DataFrame) -> pd.DataFrame:
    linha = {
        "usuario_id": "USR0001",
        "login": LOGIN_ADMIN_PADRAO,
        "nome": "Administrador",
        "senha_hash": hash_senha(_senha_admin_padrao()),
        "perfil": "ADMIN",
        "ativo": "True",
        "criado_em": agora_br().strftime("%Y-%m-%d %H:%M:%S"),
        "ultimo_login": "",
    }
    df = pd.DataFrame([linha], columns=COLUNAS)
    salvar_csv("usuarios", df)
    return df


def autenticar(login: str, senha: str) -> dict | None:
    df = carregar_usuarios()
    candidatos = df[(df["login"] == login) & (df["ativo"] == "True")]
    if candidatos.empty:
        return None
    linha = candidatos.iloc[0]
    if not verificar_senha(senha, linha["senha_hash"]):
        return None

    df.loc[df["usuario_id"] == linha["usuario_id"], "ultimo_login"] = agora_br().strftime("%Y-%m-%d %H:%M:%S")
    salvar_csv("usuarios", df)
    return linha.to_dict()


def criar_usuario(login: str, nome: str, senha: str, perfil: str) -> tuple[bool, str]:
    df = carregar_usuarios()
    if login in df["login"].values:
        return False, "Já existe um usuário com esse login."
    if perfil not in PERFIS:
        return False, f"Perfil inválido. Use um de: {', '.join(PERFIS)}."

    novo_id = f"USR{len(df) + 1:04d}"
    nova_linha = {
        "usuario_id": novo_id,
        "login": login,
        "nome": nome,
        "senha_hash": hash_senha(senha),
        "perfil": perfil,
        "ativo": "True",
        "criado_em": agora_br().strftime("%Y-%m-%d %H:%M:%S"),
        "ultimo_login": "",
    }
    df = pd.concat([df, pd.DataFrame([nova_linha], columns=COLUNAS)], ignore_index=True)
    salvar_csv("usuarios", df)
    return True, novo_id


def alterar_status(usuario_id: str, ativo: bool) -> None:
    df = carregar_usuarios()
    df.loc[df["usuario_id"] == usuario_id, "ativo"] = str(ativo)
    salvar_csv("usuarios", df)


def redefinir_senha(usuario_id: str, nova_senha: str) -> None:
    df = carregar_usuarios()
    df.loc[df["usuario_id"] == usuario_id, "senha_hash"] = hash_senha(nova_senha)
    salvar_csv("usuarios", df)
