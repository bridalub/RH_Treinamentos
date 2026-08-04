"""Componentes reutilizáveis de UI (cabeçalho, badges, cards de ficha, KPIs, callout)."""
import html

import streamlit as st

from components.theme import CORES


def _iniciais(nome: str) -> str:
    partes = [p for p in nome.split() if p]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def cabecalho_perfil(nome: str, subtitulo: str, badge_texto: str | None = None, badge_tipo: str = "ativo"):
    badge_html = ""
    if badge_texto:
        badge_html = f'<span class="brida-badge brida-badge-{badge_tipo}">{html.escape(badge_texto)}</span>'
    # container com key amarrada ao nome: força o Streamlit a remontar este
    # bloco do zero quando a pessoa selecionada muda, em vez de tentar
    # reaproveitar o nó do DOM da pessoa anterior (st.markdown sozinho não
    # aceita key nesta versão do Streamlit — por isso o wrapper).
    with st.container(key=f"cab_perfil_{nome}"):
        st.markdown(
            f"""
            <div class="brida-header">
                <div class="brida-avatar">{html.escape(_iniciais(nome))}</div>
                <div>
                    <p class="brida-title">{html.escape(nome)} {badge_html}</p>
                    <p class="brida-subtitle">{html.escape(subtitulo)}</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _linha_campo(label: str, valor) -> str:
    valor_texto = "Não informado" if valor is None or str(valor).strip() in ("", "nan", "NaN") else str(valor)
    return (
        f'<div class="brida-field"><span class="brida-field-label">{html.escape(label)}</span>'
        f'<span class="brida-field-value">{html.escape(valor_texto)}</span></div>'
    )


def card(titulo: str, campos: list[tuple[str, object]], icone: str = "", colunas: int = 1):
    """Renderiza um card completo (título + linhas de campo) em uma única chamada.

    Precisa ser uma única st.markdown: Streamlit isola cada chamada em seu próprio
    nó do DOM, então abrir a <div> em uma chamada e fechá-la em outra não produz
    um único container visual — o navegador fecha a tag no fim de cada fragmento.

    colunas > 1 organiza os campos em grade (ex.: 4 campos em 2 colunas vira 2x2),
    para aproveitar toda a largura em vez de empilhar tudo em uma coluna estreita.
    """
    linhas = "".join(_linha_campo(label, valor) for label, valor in campos)
    grade = f'style="display:grid;grid-template-columns:repeat({colunas},1fr);column-gap:2rem;"' if colunas > 1 else ""
    valores_campos = "|".join(str(v) for _, v in campos)
    with st.container(key=f"card_{titulo}_{hash(valores_campos) & 0xffffff}"):
        st.markdown(
            f'<div class="brida-card"><h4>{icone} {html.escape(titulo)}</h4><div {grade}>{linhas}</div></div>',
            unsafe_allow_html=True,
        )


def kpi(label: str, valor, sub: str = "", icone: str = ""):
    icone_html = f'<span class="brida-kpi-icone">{icone}</span>' if icone else ""
    st.markdown(
        f"""
        <div class="brida-kpi">
            <div class="brida-kpi-label">{icone_html}{html.escape(label)}</div>
            <div class="brida-kpi-value">{html.escape(str(valor))}</div>
            <div class="brida-kpi-sub">{html.escape(sub)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


_NIVEL_ICONE = {"positivo": "✅", "atencao": "⚠️", "critico": "🔴", "informativo": "ℹ️"}


def _cor_nivel(nivel: str) -> str:
    return {
        "positivo": CORES["status_bom"],
        "atencao": CORES["status_alerta"],
        "critico": CORES["status_critico"],
        "informativo": CORES["texto_secundario"],
    }.get(nivel, CORES["texto_secundario"])


def callout(titulo: str, subtitulo: str, insights: list[dict], limite: int = 6):
    """Card de análise automática. Cada insight é {"nivel": "positivo"/"atencao"/
    "critico"/"informativo", "texto": str}. Mostra até `limite` na tela e o
    restante em um expander, para não poluir o dashboard."""
    principais, resto = insights[:limite], insights[limite:]

    def _linha(item: dict) -> str:
        cor = _cor_nivel(item["nivel"])
        icone = _NIVEL_ICONE.get(item["nivel"], "•")
        return (
            f'<li style="margin-bottom:7px;"><span style="color:{cor};">{icone}</span> '
            f'<span style="color:{CORES["texto_secundario"]};">{html.escape(item["texto"])}</span></li>'
        )

    linhas = "".join(_linha(i) for i in principais)
    sub_html = f'<div style="color:{CORES["texto_secundario"]};font-size:0.8rem;margin:-4px 0 10px 0;">{html.escape(subtitulo)}</div>' if subtitulo else ""
    st.markdown(
        f'<div class="brida-callout"><h4>{html.escape(titulo)}</h4>{sub_html}'
        f'<ul style="list-style:none;padding-left:0;margin:0;">{linhas}</ul></div>',
        unsafe_allow_html=True,
    )
    if resto:
        with st.expander(f"Ver análise completa ({len(insights)} itens)"):
            for item in resto:
                st.markdown(f'{_NIVEL_ICONE.get(item["nivel"], "•")} {item["texto"]}')


def badge_status(situacao: str) -> str:
    mapa = {
        "Completo": ("ativo", "Completo"),
        "Em Andamento": ("alerta", "Em Andamento"),
        "Registrado": ("inativo", "Registrado"),
        "Não Iniciada": ("alerta", "Não Iniciada"),
        "Em Andamento/Vencido": ("critico", "Vencido"),
        "RELACIONADO_AUTOMATICO": ("ativo", "Relacionado"),
        "RELACIONADO_MANUAL": ("ativo", "Relacionado (manual)"),
        "REVISAO_MANUAL": ("alerta", "Revisão manual"),
        "NAO_ENCONTRADO": ("critico", "Não encontrado"),
        "NAO_ENCONTRADO_CONFIRMADO": ("inativo", "Confirmado: não é da base"),
    }
    tipo, texto = mapa.get(situacao, ("inativo", situacao))
    return f'<span class="brida-badge brida-badge-{tipo}">{html.escape(texto)}</span>'
