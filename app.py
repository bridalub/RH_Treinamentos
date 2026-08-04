"""Ponto de entrada do sistema de Treinamentos BRIDA (Streamlit)."""
import streamlit as st

from utils.formatacao import agora_br

st.set_page_config(page_title="BRIDA · Treinamentos", page_icon="🛢", layout="wide")

@st.cache_resource(show_spinner=False)
def _momento_de_inicio_do_processo() -> str:
    """Marcador temporário de diagnóstico. Precisa de st.cache_resource: sem
    isso, o valor seria recalculado a cada rerun do Streamlit (clique, troca
    de página), não só quando o processo do servidor reinicia de fato — o que
    tornaria o marcador inútil para diferenciar aba com código antigo (em
    memória, de um processo mais velho) de processo realmente reiniciado."""
    return agora_br().strftime("%d/%m %H:%M:%S")


_SERVIDOR_INICIADO_EM = _momento_de_inicio_do_processo()

from components.theme import injetar_css, CORES
from utils.auth import esta_autenticado, usuario_atual, encerrar_sessao, tem_permissao, restaurar_sessao_via_cookie
from utils.csv_io import ArmazenamentoIndisponivelError
from services.logs_service import registrar
from services.treinamentos_service import ultima_atualizacao
from pages_app import login, dashboard, atualizacao, colaboradores, cadastro_colaboradores, equipes, analises, gestores, usuarios, logs as logs_page

# Bloqueia a tradução automática do Chrome/Google Translate nesta página.
# Causa raiz confirmada de vários "bugs" fantasmas nesta sessão (números com
# vírgula, "Dashboard"->"Painel", "Playwright"->"Dramaturgo"): o Chrome
# detecta palavras soltas em inglês na tela e oferece/aplica tradução
# automática, que reescreve o DOM depois que o Streamlit já renderizou tudo
# certo — por isso nunca aparecia no meu lado, só na tela do usuário.
# <meta name="google" content="notranslate"> é o mecanismo padrão para
# desligar isso; document.documentElement.translate reforça em runtime.
st.markdown(
    """<meta name="google" content="notranslate">""",
    unsafe_allow_html=True,
)
st.components.v1.html(
    """<script>
    try {
        const doc = window.parent.document;
        doc.documentElement.setAttribute('translate', 'no');
        doc.documentElement.lang = 'pt-BR';
        if (!doc.querySelector('meta[name="google"]')) {
            const meta = doc.createElement('meta');
            meta.name = 'google';
            meta.content = 'notranslate';
            doc.head.appendChild(meta);
        }
    } catch (e) {}
    </script>""",
    height=0,
)

injetar_css()

# Erro de conexão com o armazenamento remoto (Supabase fora do ar, credencial
# errada, projeto pausado) é pego uma única vez aqui — cobrindo também a
# restauração de sessão via cookie e a tela de login, que também leem o
# armazenamento (usuarios.csv/tabela usuarios) e antes ficavam fora do
# try/except, quebrando a aplicação com uma tela de erro crua antes mesmo do
# usuário conseguir logar. Em vez de espalhar try/except pelas páginas, ou
# (pior) deixar cada leitura falhar silenciosamente devolvendo "vazio" como
# se não houvesse nenhum colaborador/treinamento cadastrado. Mensagem limpa
# pro usuário, detalhe técnico só no log.
try:
    restaurar_sessao_via_cookie()

    if not esta_autenticado():
        login.render()
        st.stop()

    usuario = usuario_atual()

    with st.sidebar:
        data_ultima_atualizacao = ultima_atualizacao()
        st.markdown(
            f"""
            <div style="background:{CORES['fundo_card']};border:1px solid {CORES['borda']};border-radius:10px;
                        padding:.55rem .8rem;margin-bottom:1rem;">
                <div style="color:{CORES['texto_mudo']};font-size:0.68rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;">
                    Última atualização
                </div>
                <div style="color:{CORES['texto_primario']};font-size:0.85rem;font-weight:600;margin-top:2px;">
                    {data_ultima_atualizacao or "Nenhuma importação registrada"}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:1rem;">
                <div style="width:38px;height:38px;border-radius:50%;background:{CORES['accent']};
                            display:flex;align-items:center;justify-content:center;color:white;font-weight:700;">
                    {usuario['nome'][:1].upper()}
                </div>
                <div>
                    <div style="color:{CORES['texto_primario']};font-weight:600;font-size:0.9rem;">{usuario['nome']}</div>
                    <div style="color:{CORES['texto_mudo']};font-size:0.75rem;">{usuario['perfil']}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Sair", use_container_width=True):
            registrar(usuario["login"], "LOGOUT")
            encerrar_sessao()
            # st.rerun() imediato interrompia a gravação do cookie de logout
            # antes dela realmente chegar no navegador (o componente de cookie
            # roda de forma assíncrona) — o usuário via a tela de login por um
            # instante, mas a sessão "ressuscitava" no próximo F5, porque o
            # cookie antigo nunca tinha sido substituído de verdade. Um recarregamento
            # real da página (não um rerun interno do Streamlit), com um
            # pequeníssimo atraso pra dar tempo do cookie ser gravado, resolve.
            st.components.v1.html(
                "<script>setTimeout(function(){ window.parent.location.reload(); }, 400);</script>",
                height=0,
            )
            st.stop()
        st.divider()
        st.caption(f"🛠️ servidor iniciado em {_SERVIDOR_INICIADO_EM}")

    paginas = [st.Page(dashboard.render, title="Início", icon="📊", url_path="dashboard", default=True)]
    paginas.append(st.Page(analises.render, title="Análises", icon="📈", url_path="analises"))
    paginas.append(st.Page(equipes.render, title="Equipes", icon="👥", url_path="equipes"))
    if tem_permissao("ADMIN", "RH"):
        paginas.append(st.Page(gestores.render, title="Gestores", icon="🧭", url_path="gestores"))
    paginas.append(st.Page(colaboradores.render, title="Colaboradores", icon="🧑‍💼", url_path="colaboradores"))
    if tem_permissao("ADMIN", "RH", "GESTOR"):
        paginas.append(cadastro_colaboradores.PAGINA)
    if tem_permissao("ADMIN", "RH"):
        paginas.append(st.Page(atualizacao.render, title="Atualização", icon="🔄", url_path="atualizacao"))
    if tem_permissao("ADMIN"):
        paginas.append(st.Page(logs_page.render, title="Registros", icon="🗒️", url_path="logs"))
        paginas.append(st.Page(usuarios.render, title="Usuários", icon="🔐", url_path="usuarios"))

    pagina_atual = st.navigation(paginas)
    pagina_atual.run()
except ArmazenamentoIndisponivelError as e:
    st.error(
        "⚠️ Não foi possível conectar ao armazenamento de dados no momento. "
        "Nenhuma informação foi perdida — tente novamente em alguns instantes. "
        "Se o problema continuar, avise o administrador do sistema."
    )
    try:
        # usuario pode não existir ainda se o erro ocorreu antes do login
        # (restaurar_sessao_via_cookie ou login.render também podem falhar
        # por armazenamento indisponível) — usuario_atual() cobre esse caso,
        # com um rótulo de fallback pra sempre haver algo no log.
        usuario_erro = usuario_atual()
        login_para_log = usuario_erro["login"] if usuario_erro else "desconhecido (pré-login)"
        registrar(login_para_log, "ERRO_ARMAZENAMENTO", str(e))
    except Exception:
        pass  # se o próprio registrar() falhar (mesma causa: armazenamento fora do ar), não deixa a tela quebrar por isso
    st.stop()
