"""Análises — visão de Cientista de Dados sobre colaboradores x treinamentos (só Pandas + Plotly)."""
import pandas as pd
import streamlit as st

from components import charts, tables
from services.colaboradores_service import carregar_colaboradores
from services.treinamentos_service import carregar_treinamentos, montar_listview
from services import matching_service as ms
from utils.auth import usuario_atual
from utils.formatacao import formatar_numero_br as _fmt, formatar_percentual_br as _pct

NAO_COMPLETO = {"Em Andamento", "Em Andamento/Vencido", "Não Iniciada", "Registrado"}
# altura fixa dos pares lado a lado (evita um gráfico baixo e outro alto na mesma linha)
ALTURA_PAR = 400


def render():
    st.markdown("## Análises")

    df_colab = carregar_colaboradores()
    df_treino = carregar_treinamentos()
    if df_treino.empty or df_colab.empty:
        st.info("Importe colaboradores e treinamentos em **Atualização** para ver as análises.")
        return

    listview = montar_listview(df_treino, df_colab)

    # visões 1 e 2 comparam áreas/gestores da empresa inteira — não são
    # apropriadas para o perfil GESTOR, que só deve enxergar a própria equipe.
    usuario = usuario_atual() or {}
    if usuario.get("perfil") != "GESTOR":
        _par_graficos_1_e_2(df_treino, listview)
    _linha(
        ("3. Quem não acessa a plataforma há mais tempo?", _acesso_mais_antigo, df_treino),
        ("4. Quais treinamentos têm maior índice de não conclusão?", _treinos_maior_nao_conclusao, df_treino),
    )

    # visão 5 (antiga 6) compara TODAS as equipes/gestores entre si — mesmo
    # motivo das visões 1 e 2: um GESTOR não pode ver o risco das equipes de
    # outros gestores.
    if usuario.get("perfil") != "GESTOR":
        _pergunta("5. Quais equipes apresentam maior risco?", _equipes_maior_risco, listview)
    _pergunta("6. Quais nomes existem na plataforma mas não foram encontrados na base?", _nao_encontrados, df_treino)


def _par_graficos_1_e_2(df_treino: pd.DataFrame, listview: pd.DataFrame):
    """Títulos no padrão #### + um único Plotly (2 colunas) com base alinhada."""
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.markdown("#### 1. Qual área possui maior taxa de conclusão?")
    with col_t2:
        st.markdown("#### 2. Qual gestor possui maior quantidade de pendências?")

    cats_area, vals_area = [], []
    if not df_treino.empty:
        grupo = (
            df_treino.groupby("dtb_area")["status"]
            .apply(lambda s: (s == "Completo").mean() * 100)
            .sort_values(ascending=False)
        )
        cats_area, vals_area = grupo.index.tolist(), grupo.round(1).tolist()

    cats_gestor, vals_gestor = [], []
    base = listview[listview["Gestor"].fillna("") != ""]
    if not base.empty:
        contagem = (
            base[base["Status"].isin(NAO_COMPLETO)]
            .groupby("Gestor").size()
            .sort_values(ascending=False).head(10)
        )
        if not contagem.empty:
            cats_gestor, vals_gestor = contagem.index.tolist(), contagem.values.tolist()

    if not cats_area and not cats_gestor:
        st.caption("Sem dados para as análises 1 e 2.")
    else:
        # Q1 é taxa de conclusão (desempenho) -> cor por faixa + rótulo em %.
        # Q2 é quantidade de pendências -> cor única azul + rótulo numérico simples,
        # igual à mesma regra já usada no Painel Inicial.
        cores_area = [charts.cor_por_taxa(v) for v in vals_area]
        textos_area = [_pct(v, 1) for v in vals_area]
        textos_gestor = [_fmt(v) for v in vals_gestor]
        charts.mostrar(
            charts.barra_horizontal_dupla(
                cats_area, vals_area, cats_gestor, vals_gestor, altura=ALTURA_PAR,
                cores_esq=cores_area, textos_esq=textos_area, textos_dir=textos_gestor,
            ),
            altura=ALTURA_PAR,
            ocultar_rotulos_x=True,
        )
    st.divider()


def _linha(*perguntas):
    """Renderiza exatamente 2 perguntas na mesma linha (50% / 50%)."""
    col_esq, col_dir = st.columns(2, vertical_alignment="bottom")
    (t1, f1, d1), (t2, f2, d2) = perguntas[0], perguntas[1]
    with col_esq:
        st.markdown(f"#### {t1}")
        f1(d1)
    with col_dir:
        st.markdown(f"#### {t2}")
        f2(d2)
    st.divider()


def _pergunta(titulo, funcao, dados):
    st.markdown(f"#### {titulo}")
    funcao(dados)
    st.divider()


def _area_maior_conclusao(df_treino: pd.DataFrame):
    if df_treino.empty:
        st.caption("Sem dados.")
        return
    grupo = df_treino.groupby("dtb_area")["status"].apply(lambda s: (s == "Completo").mean() * 100).sort_values(ascending=False)
    charts.mostrar(charts.barra_horizontal(grupo.index.tolist(), grupo.round(1).tolist(), altura=ALTURA_PAR), altura=ALTURA_PAR, ocultar_rotulos_x=True)


def _gestor_mais_pendencias(listview: pd.DataFrame):
    base = listview[listview["Gestor"].fillna("") != ""]
    if base.empty:
        st.caption("Sem colaboradores relacionados a um gestor.")
        return
    pendencias = base[base["Status"].isin(NAO_COMPLETO)]
    contagem = pendencias.groupby("Gestor").size().sort_values(ascending=False).head(10)
    if contagem.empty:
        st.caption("Nenhuma pendência encontrada.")
        return
    charts.mostrar(charts.barra_horizontal(contagem.index.tolist(), contagem.values.tolist(), altura=ALTURA_PAR), altura=ALTURA_PAR, ocultar_rotulos_x=True)


def _acesso_mais_antigo(df_treino: pd.DataFrame):
    # só pessoas ativas: relacionadas à base de funcionários E sem data de
    # desligamento na própria plataforma — sem esse segundo filtro, ex-
    # colaboradores desligados (que a plataforma ainda lista) dominavam o
    # topo do ranking só por terem parado de acessar há mais tempo.
    base = df_treino[
        (df_treino["ultimo_acesso"].astype(str) != "")
        & (df_treino["nome_colaborador_relacionado"].astype(str) != "")
        & (df_treino["dtb_data_desligamento"].astype(str) == "")
    ]
    if base.empty:
        st.caption("Sem dados de último acesso.")
        return
    base = base.copy()
    base["ultimo_acesso_dt"] = pd.to_datetime(base["ultimo_acesso"], errors="coerce")
    por_pessoa = base.groupby("nome_colaborador_relacionado")["ultimo_acesso_dt"].max().sort_values().head(10)
    tabela = por_pessoa.reset_index().rename(columns={"nome_colaborador_relacionado": "Colaborador", "ultimo_acesso_dt": "Último Acesso"})
    tables.listview(tabela, altura=ALTURA_PAR, colunas_data=["Último Acesso"])


def _treinos_maior_nao_conclusao(df_treino: pd.DataFrame):
    grupo = df_treino.groupby("titulo_treinamento")["status"].apply(lambda s: (s != "Completo").mean() * 100)
    contagem = df_treino.groupby("titulo_treinamento").size()
    resultado = grupo[contagem >= 3].sort_values(ascending=False).head(10)
    if resultado.empty:
        st.caption("Poucos dados por treinamento para um ranking confiável (mínimo 3 inscrições).")
        return
    valores = resultado.round(1).tolist()
    charts.mostrar(
        charts.barra_horizontal(resultado.index.tolist(), valores, altura=ALTURA_PAR, textos=[_pct(v, 1) for v in valores]),
        altura=ALTURA_PAR, ocultar_rotulos_x=True,
    )


def _equipes_maior_risco(listview: pd.DataFrame):
    # exclui linhas sem Cargo ou sem Gestor identificado — sem isso vira uma
    # barra "em branco" no gráfico, misturando lideranças de topo (sem gestor
    # acima) e registros não relacionados com as equipes de verdade.
    base = listview[(listview["Cargo"].fillna("") != "") & (listview["Gestor"].fillna("") != "")]
    if base.empty:
        st.caption("Sem colaboradores relacionados o suficiente para avaliar risco por equipe.")
        return
    risco = base.groupby("Gestor")["Status"].apply(lambda s: (s != "Completo").mean() * 100).sort_values(ascending=False).head(10)
    valores = risco.round(1).tolist()
    charts.mostrar(charts.barra_horizontal(
        risco.index.tolist(), valores, textos=[_pct(v, 1) for v in valores],
        titulo="% de treinamentos não concluídos por equipe", altura=ALTURA_PAR,
    ), altura=ALTURA_PAR, ocultar_rotulos_x=True)


def _nao_encontrados(df_treino: pd.DataFrame):
    nomes = sorted(df_treino[df_treino["situacao_relacionamento"] == ms.NAO_ENCONTRADO]["nome_colaborador_planilha"].unique())
    if not nomes:
        st.caption("Nenhum nome pendente — todos os registros foram relacionados.")
        return
    st.dataframe(pd.DataFrame({"Nome na Plataforma": nomes}), hide_index=True, use_container_width=True, height=ALTURA_PAR)


