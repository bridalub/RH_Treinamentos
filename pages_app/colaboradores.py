"""Perfil completo do colaborador: dados cadastrais (BASE FUNCIONÁRIOS) + treinamentos (plataforma)."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import cards, charts, tables
from components.theme import CORES
from services.colaboradores_service import carregar_colaboradores
from services.treinamentos_service import STATUS_CONCLUIDOS, carregar_treinamentos
from utils.auth import usuario_atual
from utils.formatacao import MESES, formatar_numero_br, formatar_percentual_br
from utils.normalizacao import normalizar_nome


def render():
    st.markdown("## Colaboradores")

    df_colab = carregar_colaboradores()
    validos = df_colab[df_colab["is_pessoa_valida"] == "True"].copy()
    if validos.empty:
        st.info("Nenhum colaborador importado ainda. Vá em **Atualização**.")
        return

    # perfil GESTOR só pode ver/buscar dentro da própria equipe.
    usuario = usuario_atual() or {}
    if usuario.get("perfil") == "GESTOR":
        validos["gestor_normalizado"] = validos["gestor_nome"].map(normalizar_nome)
        meu_norm = normalizar_nome(usuario.get("nome", ""))
        validos = validos[validos["gestor_normalizado"] == meu_norm]
        if validos.empty:
            st.warning(
                "Nenhuma equipe foi encontrada para o seu usuário na base de colaboradores. "
                "Fale com o administrador para vincular seu login ao nome correto do coordenador/líder."
            )
            return

    nomes_unicos = sorted(validos["nome"].unique())

    nome_selecionado = st.selectbox(
        "Colaborador", nomes_unicos, index=None, placeholder="Selecione um colaborador...", key="colab_selecionado",
    )
    if nome_selecionado is None:
        st.info("Selecione um colaborador acima para ver o perfil completo.")
        return

    linhas_pessoa = validos[validos["nome"] == nome_selecionado]
    linha_principal = linhas_pessoa.iloc[0]

    contato = " · ".join(v for v in (linha_principal["email"], linha_principal["celular"]) if str(v).strip())
    subtitulo = f"{linha_principal['cargo']} · {len(linhas_pessoa)} equipe(s) · BRIDA · {contato}"
    cards.cabecalho_perfil(
        nome_selecionado, subtitulo,
        badge_texto="ATIVO", badge_tipo="ativo",
    )

    df_treino = carregar_treinamentos()
    # por nome_normalizado, não pelo texto literal: cobre o caso de a mesma
    # pessoa ter mais de uma linha na base de funcionários com grafias
    # levemente diferentes (ex.: sufixo "- REALOCADO").
    nome_norm_selecionado = normalizar_nome(nome_selecionado)
    treinos_pessoa = (
        df_treino[df_treino["nome_colaborador_relacionado"].map(normalizar_nome) == nome_norm_selecionado]
        if not df_treino.empty else df_treino
    )

    cards.card("Profissional", [
        ("Cargo", linha_principal["cargo"]),
        ("Equipe(s)", ", ".join(sorted(linhas_pessoa["equipe_id"].unique()))),
        ("Gestor(es)", ", ".join(sorted(set(g for g in linhas_pessoa["gestor_nome"] if g))) or None),
        ("Horário de Trabalho", linha_principal["horario_trabalho"]),
    ], icone="💼", colunas=2)

    st.markdown("#### 📚 Treinamentos na Plataforma")
    if treinos_pessoa.empty:
        st.info("Nenhum treinamento encontrado para este colaborador na última importação.")
        return

    total = len(treinos_pessoa)
    completos = int((treinos_pessoa["status"] == "Completo").sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("📚 Total de treinamentos", formatar_numero_br(total))
    c2.metric("✅ Completos", formatar_numero_br(completos))
    c3.metric("📈 Progresso", formatar_percentual_br(completos / total * 100))
    st.progress(completos / total if total else 0)

    tabela = treinos_pessoa[[
        "titulo_treinamento", "tipo_treino", "status", "data_inscricao", "data_conclusao", "ultimo_acesso",
    ]].rename(columns={
        "titulo_treinamento": "Treinamento", "tipo_treino": "Tipo", "status": "Status",
        "data_inscricao": "Inscrição", "data_conclusao": "Conclusão", "ultimo_acesso": "Último Acesso",
    }).sort_values("Status")
    tables.listview(tabela, altura=380, colunas_data=["Inscrição", "Conclusão", "Último Acesso"])

    _grafico_cursos_concluidos_por_mes(treinos_pessoa)


def _grafico_cursos_concluidos_por_mes(treinos_pessoa: pd.DataFrame):
    """Barras mensais de conclusões do colaborador já exibido — isolado da ListView."""
    concluidos = treinos_pessoa[treinos_pessoa["status"].isin(STATUS_CONCLUIDOS)].copy()
    if concluidos.empty:
        st.caption("Este colaborador ainda não possui treinamentos concluídos para exibição no gráfico.")
        return

    concluidos["_data_conclusao_dt"] = pd.to_datetime(concluidos["data_conclusao"], errors="coerce")
    concluidos = concluidos[concluidos["_data_conclusao_dt"].notna()]
    if concluidos.empty:
        st.caption("Este colaborador ainda não possui treinamentos concluídos para exibição no gráfico.")
        return

    anos = sorted(concluidos["_data_conclusao_dt"].dt.year.unique().astype(int).tolist(), reverse=True)
    ano_sel = st.selectbox("Ano", anos, index=0, key="colab_grafico_ano_conclusoes")

    charts.cabecalho(
        "Cursos Concluídos ao Longo dos Meses",
        "Quantidade de treinamentos concluídos pelo colaborador em cada mês do ano selecionado",
    )

    do_ano = concluidos[concluidos["_data_conclusao_dt"].dt.year == int(ano_sel)]
    if do_ano.empty:
        st.caption("Não foram encontradas conclusões no ano selecionado.")
        return

    por_mes = do_ano.groupby(do_ano["_data_conclusao_dt"].dt.month).size()
    valores = [int(por_mes.get(m, 0)) for m in range(1, 13)]
    textos = [str(v) if v > 0 else "" for v in valores]
    hovers = [
        f"<b>{mes}</b><br>Quantidade de cursos concluídos: {qtd}<br>Ano: {ano_sel}"
        for mes, qtd in zip(MESES, valores)
    ]

    fig = go.Figure(
        go.Bar(
            x=MESES,
            y=valores,
            marker=dict(color=CORES["accent"], cornerradius=6),
            text=textos,
            textposition="outside",
            textfont=dict(color=CORES["texto_primario"]),
            hovertext=hovers,
            hoverinfo="text",
            showlegend=False,
        )
    )
    fig = charts._aplicar_layout_padrao(fig, "", altura=380)
    maior = max(valores) if valores else 0
    fig.update_layout(margin=dict(l=40, r=20, t=20, b=60), showlegend=False)
    fig.update_yaxes(title_text="", rangemode="tozero", range=[0, max(maior * 1.25, 1)])
    fig.update_xaxes(title_text="", tickangle=-30)
    charts.mostrar(fig, altura=380)
