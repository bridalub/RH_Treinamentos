"""Hash de senha e controle de sessão/permissões do Streamlit."""
import hashlib
import hmac
import os
from datetime import timedelta

import streamlit as st
from streamlit_cookies_controller import CookieController

_ITERACOES = 100_000

# st.session_state não sobrevive a um F5 no navegador nem a uma reconexão do
# WebSocket (troca de rede, aba que volta do fundo) — o Streamlit trata isso
# como uma sessão nova e joga de volta pro login mesmo com a senha certa
# digitada minutos antes. Um cookie de verdade no navegador resolve isso: o
# token não guarda a senha, é uma assinatura HMAC amarrada ao senha_hash
# ATUAL do usuário (troca de senha invalida sozinho qualquer cookie velho,
# sem precisar de uma lista de sessões revogadas).
_NOME_COOKIE = "brida_sessao"
_DURACAO_SESSAO = timedelta(hours=12)


def _token_sessao(login: str, senha_hash: str) -> str:
    assinatura = hmac.new(senha_hash.encode("utf-8"), login.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{login}.{assinatura}"


def hash_senha(senha: str, salt: bytes | None = None) -> str:
    """Retorna 'salt_hex$hash_hex' pronto para gravar em usuarios.csv."""
    if salt is None:
        salt = os.urandom(16)
    derivado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, _ITERACOES)
    return f"{salt.hex()}${derivado.hex()}"


def verificar_senha(senha: str, senha_hash_armazenada: str) -> bool:
    try:
        salt_hex, hash_hex = senha_hash_armazenada.split("$")
    except (ValueError, AttributeError):
        return False
    salt = bytes.fromhex(salt_hex)
    derivado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, _ITERACOES)
    return derivado.hex() == hash_hex


# ---------------------------------------------------------------- sessão ----

def iniciar_sessao(usuario: dict):
    st.session_state["usuario_autenticado"] = usuario
    try:
        CookieController().set(
            _NOME_COOKIE, _token_sessao(usuario["login"], usuario["senha_hash"]),
            max_age=int(_DURACAO_SESSAO.total_seconds()),
        )
    except Exception:
        pass  # sem cookie funcional a sessão ainda funciona — só não sobrevive a um F5


def encerrar_sessao():
    for chave in ("usuario_autenticado",):
        st.session_state.pop(chave, None)
    # A causa raiz do "logout não gruda" não era o cookie continuar vivo no
    # navegador — é que a exclusão do cookie (por qualquer método) só se
    # confirma no navegador de forma assíncrona, e o app.py chama st.rerun()
    # imediatamente depois de encerrar_sessao(); nesse rerun imediato,
    # restaurar_sessao_via_cookie() lê o cookie ANTES da exclusão realmente
    # ter chegado no navegador, e loga o usuário de volta sozinho. Essa flag
    # bloqueia só essa restauração imediata (um rerun normal preserva
    # session_state — só um F5 de verdade o apaga, e nesse caso o cookie já
    # teve tempo de sobra pra ser removido de verdade).
    st.session_state["_acabou_de_sair"] = True
    try:
        # Tentativas de apagar o cookie de fato (.remove() do componente,
        # .set() com expiração no passado, JS direto via components.v1.html)
        # não pegavam no navegador — sem erro nenhum, o valor antigo
        # simplesmente continuava lá. Em vez de insistir na exclusão,
        # sobrescreve com um valor inválido usando exatamente a mesma
        # chamada .set() já comprovada funcionar (é o que grava o cookie no
        # login) — sem "." no valor, restaurar_sessao_via_cookie() descarta
        # na hora. Na prática tem o mesmo efeito de "sair".
        CookieController().set(_NOME_COOKIE, "logout", max_age=int(_DURACAO_SESSAO.total_seconds()))
    except Exception:
        pass


def restaurar_sessao_via_cookie():
    """Chamada uma vez no início de cada execução do app, antes de checar
    esta_autenticado() — sem isso, um F5 no navegador ou uma reconexão do
    WebSocket (troca de rede, aba que volta do fundo) sempre pede login de
    novo, mesmo com a sessão "válida" minutos atrás."""
    if usuario_atual() is not None:
        return
    if st.session_state.pop("_acabou_de_sair", False):
        return
    try:
        token = CookieController().get(_NOME_COOKIE)
    except Exception:
        return
    if not token or "." not in token:
        return
    login, _, _assinatura = token.partition(".")

    from services.usuarios_service import carregar_usuarios  # import tardio: evita ciclo (usuarios_service importa daqui)
    df = carregar_usuarios()
    candidatos = df[(df["login"] == login) & (df["ativo"] == "True")]
    if candidatos.empty:
        return
    linha = candidatos.iloc[0]
    esperado = _token_sessao(login, linha["senha_hash"])
    if hmac.compare_digest(token, esperado):
        st.session_state["usuario_autenticado"] = linha.to_dict()


def usuario_atual() -> dict | None:
    return st.session_state.get("usuario_autenticado")


def esta_autenticado() -> bool:
    return usuario_atual() is not None


def exigir_login():
    if not esta_autenticado():
        st.warning("Você precisa fazer login para acessar esta página.")
        st.stop()


def tem_permissao(*perfis_permitidos: str) -> bool:
    usuario = usuario_atual()
    if usuario is None:
        return False
    if not perfis_permitidos:
        return True
    return usuario.get("perfil") in perfis_permitidos


def exigir_permissao(*perfis_permitidos: str):
    exigir_login()
    if not tem_permissao(*perfis_permitidos):
        st.error("Seu perfil não tem permissão para acessar esta página.")
        st.stop()
