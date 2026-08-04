"""Identidade visual dark BRIDA: paleta central + CSS injetado uma vez por página."""
import streamlit as st

CORES = {
    "fundo_pagina": "#0b1220",
    "fundo_card": "#131D2F",
    "fundo_card_alt": "#0f1729",
    "fundo_grafico": "#111827",
    "borda": "#263449",
    "texto_primario": "#F8FAFC",
    "texto_secundario": "#CBD5E1",
    "texto_mudo": "#94A3B8",
    "cinza_neutro": "#64748B",
    "accent": "#3B82F6",
    "accent_secundario": "#60A5FA",
    "accent_escuro": "#2563EB",
    "categorica": ["#3B82F6", "#F97316", "#22C55E", "#F59E0B", "#60A5FA", "#9085e9", "#e66767"],
    "status_bom": "#22C55E",
    "status_bom_secundario": "#16A34A",
    "status_alerta": "#F59E0B",
    "status_grave": "#F97316",
    "status_critico": "#EF4444",
    "status_critico_escuro": "#DC2626",
    "grid": "#273449",
    "eixo": "#263449",
}

STATUS_TREINAMENTO_COR = {
    "Completo": CORES["status_bom"],
    "Concluído (Equivalente)": CORES["status_bom_secundario"],
    "Em Andamento": CORES["accent"],
    "Registrado": CORES["status_alerta"],
    "Não Iniciada": CORES["cinza_neutro"],
    "Em Andamento/Vencido": CORES["status_critico"],
    "Reprovado": CORES["status_critico_escuro"],
    "Avaliação Pendente": CORES["status_grave"],
}


def injetar_css():
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {CORES['fundo_pagina']}; }}
        section[data-testid="stSidebar"] {{ background-color: {CORES['fundo_card_alt']}; }}

        .brida-header {{ display:flex; align-items:center; gap:14px; margin-bottom: 1.2rem; }}
        .brida-avatar {{
            width:56px; height:56px; border-radius:50%; background:{CORES['accent']};
            display:flex; align-items:center; justify-content:center;
            font-weight:700; font-size:1.15rem; color:white; flex-shrink:0;
        }}
        .brida-title {{ font-size:1.5rem; font-weight:700; color:{CORES['texto_primario']}; margin:0; }}
        .brida-subtitle {{ color:{CORES['texto_secundario']}; font-size:0.92rem; margin-top:2px; }}

        .brida-badge {{
            display:inline-block; padding:2px 12px; border-radius:999px;
            font-size:0.75rem; font-weight:600; border:1px solid; letter-spacing:.03em;
        }}
        .brida-badge-ativo {{ color:{CORES['status_bom']}; border-color:{CORES['status_bom']}; background:rgba(12,163,12,0.12); }}
        .brida-badge-inativo {{ color:{CORES['texto_mudo']}; border-color:{CORES['texto_mudo']}; background:rgba(124,132,148,0.12); }}
        .brida-badge-alerta {{ color:{CORES['status_alerta']}; border-color:{CORES['status_alerta']}; background:rgba(250,178,25,0.12); }}
        .brida-badge-critico {{ color:{CORES['status_critico']}; border-color:{CORES['status_critico']}; background:rgba(208,59,59,0.12); }}

        .brida-card {{
            background:{CORES['fundo_card']}; border:1px solid {CORES['borda']};
            border-radius:14px; padding:1.1rem 1.3rem; margin-bottom:1rem;
        }}
        .brida-card h4 {{
            color:{CORES['accent']}; font-size:0.82rem; font-weight:700; letter-spacing:.06em;
            text-transform:uppercase; margin:0 0 .8rem 0; display:flex; align-items:center; gap:8px;
        }}
        .brida-field {{
            display:flex; justify-content:space-between; align-items:baseline;
            padding:7px 0; border-bottom:1px solid {CORES['borda']}; gap:1rem;
        }}
        .brida-field:last-child {{ border-bottom:none; }}
        .brida-field-label {{ color:{CORES['texto_secundario']}; font-size:0.85rem; white-space:nowrap; }}
        .brida-field-value {{ color:{CORES['texto_primario']}; font-weight:600; font-size:0.9rem; text-align:right; overflow-wrap:anywhere; }}

        .brida-kpi {{
            background:{CORES['fundo_card']}; border:1px solid {CORES['borda']}; border-radius:14px;
            padding:1rem 1.2rem; min-height:112px; display:flex; flex-direction:column; justify-content:center;
        }}
        .brida-kpi-label {{ color:{CORES['texto_mudo']}; font-size:0.72rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }}
        .brida-kpi-icone {{ margin-right:6px; }}
        .brida-kpi-value {{ color:{CORES['texto_primario']}; font-size:1.9rem; font-weight:700; margin:2px 0; }}
        .brida-kpi-sub {{ color:{CORES['texto_secundario']}; font-size:0.78rem; }}

        .brida-callout {{
            background:{CORES['fundo_card']}; border-left:3px solid {CORES['status_grave']}; border-radius:10px;
            padding:1rem 1.2rem; margin-bottom:1rem;
        }}
        .brida-callout h4 {{ color:{CORES['status_grave']}; font-size:0.8rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; margin:0 0 .6rem 0; }}
        .brida-callout ul {{ margin:0; padding-left:1.1rem; color:{CORES['texto_secundario']}; font-size:0.88rem; }}
        .brida-callout li {{ margin-bottom:4px; }}

        div[data-testid="stMetric"] {{
            background:{CORES['fundo_card']}; border:1px solid {CORES['borda']}; border-radius:14px; padding:.9rem 1rem;
            min-height:112px; display:flex; flex-direction:column; justify-content:center;
        }}

        /* Só força lado a lado em blocos de EXATAMENTE 2 colunas.
           Plotly/iframe com min-width alto faz o Streamlit empilhar a linha. */
        div[data-testid="stHorizontalBlock"]:has(> div:nth-child(2):last-child) {{
            flex-wrap: nowrap !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(> div:nth-child(2):last-child) > div {{
            min-width: 0 !important;
            flex: 1 1 0 !important;
            max-width: 50% !important;
        }}
        div[data-testid="stPlotlyChart"],
        div[data-testid="stPlotlyChart"] > div,
        div[data-testid="stPlotlyChart"] iframe {{
            width: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
