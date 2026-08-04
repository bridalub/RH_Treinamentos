"""Gestores — painel executivo da liderança (RH, Gerência e Diretoria).

Reaproveita exclusivamente os dados já existentes em colaboradores.csv e
treinamentos.csv (mesmas fontes de Equipes/Análises/Dashboard) — nenhuma
tabela, coluna ou relacionamento novo. "Gestor" é identificado do mesmo jeito
que em Equipes: qualquer pessoa que apareça como gestor_nome de outro
colaborador. "Equipe" de um gestor são os colaboradores cujo gestor_nome
aponta para ele (o próprio gestor nunca entra na própria média de equipe).
"""
import pandas as pd
import streamlit as st

from components import cards, charts, tables
from components.theme import CORES
from services.colaboradores_service import carregar_colaboradores
from services.treinamentos_service import carregar_treinamentos, STATUS_CONCLUIDOS
from utils.auth import usuario_atual
from utils.formatacao import MESES, formatar_numero_br as _fmt, formatar_percentual_br as _pct, formatar_data_br
from utils.normalizacao import normalizar_nome

EM_ANDAMENTO = {"Em Andamento", "Em Andamento/Vencido"}

# Reaproveita os mesmos sinais já usados nos insights do Dashboard (30 dias
# sem acesso, taxa de conclusão abaixo de 50%) — não são regras novas, só os
# mesmos números já validados em outra tela, aplicados aqui ao painel de
# atenção dos gestores.
DIAS_SEM_ACESSO_ATENCAO = 30
TAXA_BAIXA_ATENCAO = 50.0


def render():
    st.markdown("## Gestores")
    st.caption("Painel executivo da liderança — desempenho dos gestores e influência sobre suas equipes")

    df_colab = carregar_colaboradores()
    df_treino_total = carregar_treinamentos()
    # data de conclusão convertida e nome relacionado normalizado UMA vez
    # aqui — reaproveitados por _aplicar_status_periodo (Ano/Mês), pela lista
    # de anos do filtro, por _stats_por_pessoa e pelos dois gráficos de
    # evolução, que antes recalculavam cada um por conta própria em cima do
    # mesmo dado (mesmo padrão que dashboard.py já usa para a data).
    if not df_treino_total.empty:
        df_treino_total = df_treino_total.copy()
        df_treino_total["_data_conclusao_dt"] = pd.to_datetime(df_treino_total["data_conclusao"], errors="coerce")
        df_treino_total["_nome_norm"] = df_treino_total["nome_colaborador_relacionado"].map(normalizar_nome)
    validos = df_colab[df_colab["is_pessoa_valida"] == "True"].copy()

    if validos.empty:
        st.info("Nenhum colaborador importado ainda. Vá em **Atualização**.")
        return

    validos["gestor_normalizado"] = validos["gestor_nome"].map(normalizar_nome)
    gestores_norm_todos = sorted(g for g in validos["gestor_normalizado"].unique() if g)

    if not gestores_norm_todos:
        st.info("Nenhum gestor identificado na base de colaboradores atual (ninguém aparece como gestor de outra pessoa).")
        return

    # Perfil GESTOR só veria a própria equipe se um dia acessasse esta
    # página — hoje o menu só é exibido para ADMIN/RH (ver app.py); esta
    # ramificação só prepara a estrutura, sem alterar quem acessa a tela.
    usuario = usuario_atual() or {}
    if usuario.get("perfil") == "GESTOR":
        meu_norm = normalizar_nome(usuario.get("nome", ""))
        gestores_norm_todos = [g for g in gestores_norm_todos if g == meu_norm]
        if not gestores_norm_todos:
            st.warning(
                "Nenhuma equipe foi encontrada para o seu usuário na base de colaboradores. "
                "Fale com o administrador para vincular seu login ao nome correto do gestor."
            )
            return

    area_pessoa = _area_por_pessoa(df_treino_total)
    opcoes_base = _opcoes_gestores(validos, gestores_norm_todos, area_pessoa)

    # ---------------------------------------------------------------- filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        sel_gestor = st.multiselect("Gestor", opcoes_base["Gestor"].tolist(), key="gestores_f_gestor", placeholder="Todos")
    with col2:
        sel_area = st.multiselect("Área", sorted(opcoes_base["Área"].unique()), key="gestores_f_area", placeholder="Todas")
    with col3:
        sel_cargo = st.multiselect("Cargo", sorted(opcoes_base["Cargo"].unique()), key="gestores_f_cargo", placeholder="Todos")

    col4, col5, col6 = st.columns(3)
    with col4:
        opcoes_status = sorted(df_treino_total["status"].dropna().unique().tolist()) if not df_treino_total.empty else []
        sel_status = st.multiselect("Status do Treinamento", opcoes_status, key="gestores_f_status", placeholder="Todos")
    with col5:
        anos_disponiveis = (
            sorted(df_treino_total["_data_conclusao_dt"].dt.year.dropna().unique().astype(int), reverse=True)
            if not df_treino_total.empty else []
        )
        ano_sel = st.selectbox("Ano", ["Todos"] + [str(a) for a in anos_disponiveis], key="gestores_f_ano")
    with col6:
        mes_sel_nome = st.selectbox("Mês", ["Todos"] + MESES, key="gestores_f_mes")

    gestores_norm_sel = set(opcoes_base["gestor_norm"])
    if sel_gestor:
        gestores_norm_sel &= set(opcoes_base.loc[opcoes_base["Gestor"].isin(sel_gestor), "gestor_norm"])
    if sel_area:
        gestores_norm_sel &= set(opcoes_base.loc[opcoes_base["Área"].isin(sel_area), "gestor_norm"])
    if sel_cargo:
        gestores_norm_sel &= set(opcoes_base.loc[opcoes_base["Cargo"].isin(sel_cargo), "gestor_norm"])

    opcoes_selecionadas = opcoes_base[opcoes_base["gestor_norm"].isin(gestores_norm_sel)]
    if opcoes_selecionadas.empty:
        st.info("Nenhum gestor corresponde à combinação de filtros selecionada.")
        return

    df_treino_periodo = _aplicar_status_periodo(df_treino_total, sel_status, ano_sel, mes_sel_nome)
    stats_pessoa = _stats_por_pessoa(df_treino_periodo)
    df_gestores = _montar_dataset(opcoes_selecionadas, validos, stats_pessoa)
    df_gestores = _marcar_base_reduzida(df_gestores)

    st.divider()
    _cards_executivos(df_gestores)
    st.write("")

    _grafico_ranking_gestores(df_gestores)
    st.write("")
    _grafico_comparativo_gestor_equipe(df_gestores)
    st.write("")
    _grafico_ranking_equipes(df_gestores)
    st.write("")
    _grafico_situacao_lideranca(df_gestores)
    st.write("")

    gestores_norm_final = set(df_gestores["gestor_norm"])
    membros_norm_final = set(validos.loc[validos["gestor_normalizado"].isin(gestores_norm_final), "nome_normalizado"])
    col_g5, col_g6 = st.columns(2)
    with col_g5:
        _grafico_evolucao_lideranca(df_treino_periodo, gestores_norm_final)
    with col_g6:
        _grafico_evolucao_equipes(df_treino_periodo, membros_norm_final)
    st.write("")

    _grafico_desempenho_area(df_gestores)
    st.write("")

    _tabela_executiva(df_gestores)
    st.write("")
    _painel_atencao(df_gestores)
    st.write("")
    _comparativo_gestor_equipe_tabela(df_gestores)


# --------------------------------------------------------------- montagem dos dados

def _area_por_pessoa(df_treino: pd.DataFrame) -> dict:
    """Área não existe em colaboradores.csv — só a plataforma de treinamentos
    tem essa informação (dtb_area), por pessoa/linha. Usa a área mais
    frequente entre os treinamentos de cada pessoa como sua área de exibição."""
    if df_treino.empty:
        return {}
    base = df_treino[(df_treino["nome_colaborador_relacionado"] != "") & (df_treino["dtb_area"] != "")]
    if base.empty:
        return {}
    moda = base.groupby("nome_colaborador_relacionado")["dtb_area"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "")
    return moda.to_dict()


def _opcoes_gestores(validos: pd.DataFrame, gestores_norm: list[str], area_pessoa: dict) -> pd.DataFrame:
    """Nome de exibição, área e cargo de cada gestor — independente dos
    filtros de status/período, para as opções dos filtros ficarem estáveis."""
    linhas = []
    for gestor_norm in gestores_norm:
        linha_lider = validos[validos["nome_normalizado"] == gestor_norm]
        nome_gestor = linha_lider["nome"].mode().iloc[0] if not linha_lider.empty else gestor_norm
        cargo_gestor = (linha_lider["cargo"].iloc[0] if not linha_lider.empty else "") or "Não informado"
        area_gestor = area_pessoa.get(nome_gestor, "") or "Não informado"
        linhas.append({"gestor_norm": gestor_norm, "Gestor": nome_gestor, "Área": area_gestor, "Cargo": cargo_gestor})
    return pd.DataFrame(linhas)


def _aplicar_status_periodo(df_treino: pd.DataFrame, sel_status: list[str], ano_sel: str, mes_sel_nome: str) -> pd.DataFrame:
    """`df_treino` já chega com `_data_conclusao_dt` pré-calculada (ver
    render()) — sem filtro nenhum ativo (caso mais comum: primeira abertura
    da tela), devolve o próprio DataFrame recebido sem copiar nem filtrar
    nada, em vez de sempre pagar o custo de um .copy() do treinamentos.csv
    inteiro só pra devolver ele idêntico."""
    if df_treino.empty:
        return df_treino
    mes_sel = MESES.index(mes_sel_nome) + 1 if mes_sel_nome != "Todos" else None
    if not sel_status and ano_sel == "Todos" and mes_sel is None:
        return df_treino

    if sel_status:
        df_treino = df_treino[df_treino["status"].isin(sel_status)]
    if ano_sel == "Todos" and mes_sel is None:
        return df_treino

    # período filtra pela Data de Conclusão, igual em Equipes/Dashboard:
    # treinamentos ainda não concluídos ficam fora quando o filtro está ativo.
    mascara = pd.Series(True, index=df_treino.index)
    if ano_sel != "Todos":
        mascara &= df_treino["_data_conclusao_dt"].dt.year == int(ano_sel)
    if mes_sel is not None:
        mascara &= df_treino["_data_conclusao_dt"].dt.month == mes_sel
    return df_treino[mascara]


def _stats_por_pessoa(df_treino: pd.DataFrame) -> dict:
    """Chave por nome_normalizado — mesma lógica de Equipes/Análises, para que
    pequenas variações de grafia do mesmo nome não dividam a mesma pessoa em
    dois registros diferentes. `_nome_norm` é reaproveitado de render() quando
    já vem pronto (é o caso comum); só recalcula se receber um DataFrame que
    não passou por lá. Monta um DataFrame só com as 3 colunas realmente
    usadas em vez de copiar as ~19 colunas de df_treino inteiro."""
    if df_treino.empty:
        return {}
    nome_norm = (
        df_treino["_nome_norm"] if "_nome_norm" in df_treino.columns
        else df_treino["nome_colaborador_relacionado"].map(normalizar_nome)
    )
    df = pd.DataFrame({
        "_nome_norm": nome_norm,
        "status": df_treino["status"],
        "_ultimo_acesso_dt": pd.to_datetime(df_treino["ultimo_acesso"], errors="coerce"),
    })
    resultado = {}
    for nome_norm, grupo in df.groupby("_nome_norm"):
        if not nome_norm:
            continue
        total = len(grupo)
        concluidos = int(grupo["status"].isin(STATUS_CONCLUIDOS).sum())
        em_andamento = int(grupo["status"].isin(EM_ANDAMENTO).sum())
        resultado[nome_norm] = {
            "total": total, "concluidos": concluidos, "em_andamento": em_andamento,
            "ultimo_acesso": grupo["_ultimo_acesso_dt"].max(),
        }
    return resultado


def _montar_dataset(opcoes: pd.DataFrame, validos: pd.DataFrame, stats_pessoa: dict) -> pd.DataFrame:
    linhas = []
    for _, base in opcoes.iterrows():
        gestor_norm = base["gestor_norm"]
        membros = validos[validos["gestor_normalizado"] == gestor_norm].drop_duplicates("nome_normalizado")
        qtd_colaboradores = len(membros)

        s_gestor = stats_pessoa.get(gestor_norm, {"total": 0, "concluidos": 0, "em_andamento": 0, "ultimo_acesso": pd.NaT})

        total_equipe = concluidos_equipe = 0
        for m_norm in membros["nome_normalizado"]:
            s = stats_pessoa.get(m_norm, {"total": 0, "concluidos": 0})
            total_equipe += s["total"]
            concluidos_equipe += s["concluidos"]

        pct_gestor = round(s_gestor["concluidos"] / s_gestor["total"] * 100, 1) if s_gestor["total"] else float("nan")
        pct_equipe = round(concluidos_equipe / total_equipe * 100, 1) if total_equipe else float("nan")

        linhas.append({
            "gestor_norm": gestor_norm,
            "Gestor": base["Gestor"], "Área": base["Área"], "Cargo": base["Cargo"],
            "Quantidade de Colaboradores": qtd_colaboradores,
            "pct_gestor": pct_gestor, "pct_equipe": pct_equipe,
            "concluidos_gestor": s_gestor["concluidos"],
            "pendente_gestor": s_gestor["total"] - s_gestor["concluidos"],
            "total_gestor": s_gestor["total"],
            "em_andamento_gestor": s_gestor["em_andamento"],
            "total_equipe": total_equipe, "concluidos_equipe": concluidos_equipe,
            "pendente_equipe": total_equipe - concluidos_equipe,
            # NaN quando falta base de qualquer um dos dois lados — "diferença
            # zero" seria uma afirmação falsa (não é que empatam, é que não
            # dá pra comparar); pd.Series propaga NaN sozinho na subtração.
            "diferenca_pct": pct_gestor - pct_equipe,
            "ultimo_acesso": s_gestor["ultimo_acesso"],
        })
    return pd.DataFrame(linhas)


def _marcar_base_reduzida(df: pd.DataFrame) -> pd.DataFrame:
    """"Base reduzida" é relativo à própria seleção atual, não um número fixo
    inventado: sinaliza gestores cujo volume de treinamentos atribuídos está
    no quartil mais baixo (≤ 1º quartil) entre os gestores que têm ao menos 1
    treinamento atribuído — mesmo raciocínio de detectar outliers por
    percentil, não um limite absoluto chutado. Com menos de 4 gestores
    comparáveis um quartil não tem significado estatístico nenhum, então
    ninguém é sinalizado nesse caso (evita alarme falso com amostra mínima).
    Não exclui do ranking, não altera a taxa — é só um aviso de contexto."""
    df = df.copy()
    com_dados = df[df["total_gestor"] > 0]
    if len(com_dados) < 4:
        df["base_reduzida"] = False
        return df
    limite = com_dados["total_gestor"].quantile(0.25)
    df["base_reduzida"] = (df["total_gestor"] > 0) & (df["total_gestor"] <= limite)
    return df


def _ordenar_ranking(df: pd.DataFrame) -> pd.DataFrame:
    """Ordenação hierárquica e transparente (sem score oculto/fórmula
    ponderada): quem concluiu mais treinamentos aparece primeiro, mesmo que
    outro tenha uma taxa maior sobre uma base muito menor — ex.: 1 de 1
    (100%) não deve superar 100 de 110 (90,9%), que representa um volume de
    trabalho real muito maior. Critérios em ordem: 1) mais concluídos,
    2) maior taxa, 3) menos pendentes, 4) mais atribuídos, 5) nome do gestor
    (desempate final, só para o resultado ser sempre o mesmo)."""
    return df.sort_values(
        by=["concluidos_gestor", "pct_gestor", "pendente_gestor", "total_gestor", "Gestor"],
        ascending=[False, False, True, False, True],
        na_position="last", kind="mergesort",
    )


def _ordenar_tabela(df: pd.DataFrame) -> pd.DataFrame:
    """Ordenação padrão da Tabela Executiva, conforme definido: concluídos do
    gestor (decrescente), taxa do gestor (decrescente), pendentes
    (crescente) — a coluna da tabela continua ordenável manualmente pelo
    usuário clicando no cabeçalho."""
    return df.sort_values(
        by=["concluidos_gestor", "pct_gestor", "pendente_gestor"],
        ascending=[False, False, True], na_position="last", kind="mergesort",
    )


def _rotulo_percentual_base(concluidos: int, total: int, casas: int = 1) -> str:
    """'90,9% — 100 de 110': nunca mostra um percentual sem a base que gerou
    ele — é exatamente o contexto que faltava e mascarava casos de 1 de 1."""
    if not total:
        return "Sem treinamentos atribuídos"
    pct = round(concluidos / total * 100, casas)
    return f"{_pct(pct, casas)} — {_fmt(concluidos)} de {_fmt(total)}"


def _rotulo_curto(concluidos: int, total: int) -> str:
    """'100,0% (78/78)': quantidade e percentual continuam os dois visíveis
    (nenhum aparece sozinho), só em formato compacto para caber no rótulo em
    cima da barra sem sobrepor — o contexto completo por extenso vai no
    tooltip (_rotulo_percentual_base/_rotulo_ranking)."""
    if not total:
        return "sem dados"
    pct = round(concluidos / total * 100, 1)
    return f"{_pct(pct, 1)} ({_fmt(concluidos)}/{_fmt(total)})"


def _rotulo_quantidade(concluidos: int, total: int) -> str:
    """'78/78', sem percentual — usado só onde o próprio eixo já é uma escala
    de 0 a 100% (ex.: Comparativo Gestor x Equipe): repetir a porcentagem no
    rótulo em cima da barra ali é redundante com o que o eixo já mostra."""
    if not total:
        return "sem dados"
    return f"{_fmt(concluidos)}/{_fmt(total)}"


# --------------------------------------------------------------- cards executivos

def _cards_executivos(df: pd.DataFrame):
    total_gestores = len(df)
    total_concl_gestor = int(df["concluidos_gestor"].sum())
    total_trein_gestor = int(df["total_gestor"].sum())
    media_gestores = (total_concl_gestor / total_trein_gestor * 100) if total_trein_gestor else 0.0

    total_concl_equipe = int(df["concluidos_equipe"].sum())
    total_trein_equipe = int(df["total_equipe"].sum())
    # arredondado na mesma casa decimal de pct_equipe (1 casa) — comparar um
    # valor não-arredondado com um já arredondado classificava times cuja
    # média batia com a geral (empate na casa exibida) como "abaixo", só
    # por causa da diferença nas casas decimais escondidas.
    media_equipes = round((total_concl_equipe / total_trein_equipe * 100), 1) if total_trein_equipe else 0.0

    # denominador do card "100%" é quem TEM treinamento atribuído (só esses
    # podem de fato chegar a 100%) — contra o total geral, um gestor sem
    # nenhum dado misturaria "não tem 100%" com "não tem dado nenhum".
    com_dados = df[df["total_gestor"] > 0]
    total_com_dados = len(com_dados)
    gestores_100 = int((com_dados["pct_gestor"] == 100.0).sum())

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        cards.kpi("Total de Gestores", _fmt(total_gestores), "Gestores identificados na base atual", icone="👤")
    with c2:
        cards.kpi("Conclusão da Liderança", _pct(media_gestores, 1), f"{_fmt(total_concl_gestor)} de {_fmt(total_trein_gestor)} treinamentos", icone="📈")
    with c3:
        cards.kpi("Média Geral das Equipes", _pct(media_equipes, 1), f"{_fmt(total_concl_equipe)} de {_fmt(total_trein_equipe)} treinamentos", icone="👥")
    with c4:
        cards.kpi("Gestores com 100% de Conclusão", f"{_fmt(gestores_100)} de {_fmt(total_com_dados)}", "Só entre quem tem treinamento atribuído", icone="✅")


# ------------------------------------------------------------------------ gráficos

def _grafico_ranking_gestores(df: pd.DataFrame):
    charts.cabecalho(
        "🏆 Ranking dos Gestores",
        "Ordenado por volume concluído, não só por percentual — 1 de 1 (100%) não fica acima de 100 de 110 (90,9%)",
    )
    base = df[df["total_gestor"] > 0].copy()
    if base.empty:
        st.caption("Nenhum gestor com treinamentos atribuídos nos filtros atuais.")
        return
    base = _ordenar_ranking(base)
    # comprimento da barra = quantidade concluída (critério de ordenação);
    # cor continua por faixa de taxa, pra dar o contexto de qualidade junto
    # com o volume — as duas coisas juntas evitam tanto "só percentual
    # engana" quanto "só volume esconde quem concluiu pouco de muito".
    cores = [charts.cor_por_taxa(v) if pd.notna(v) else CORES["texto_mudo"] for v in base["pct_gestor"]]
    # rótulo em cima da barra fica curto (quantidade + % continuam os dois
    # ali, só compactos); o detalhamento por extenso — incluindo "Base
    # reduzida" — vai só no tooltip, pra não sobrepor com muitos gestores.
    textos = [_rotulo_curto(c, t) for c, t in zip(base["concluidos_gestor"], base["total_gestor"])]
    hovers = [
        f"<b>{g}</b><br>Concluídos: {_fmt(c)}<br>Atribuídos: {_fmt(t)}<br>Pendentes: {_fmt(p)}<br>Taxa: {_pct(pc, 1)}"
        + ("<br>⚠ Base reduzida (volume baixo)" if br else "")
        for g, c, t, p, pc, br in zip(
            base["Gestor"], base["concluidos_gestor"], base["total_gestor"],
            base["pendente_gestor"], base["pct_gestor"], base["base_reduzida"],
        )
    ]
    charts.mostrar(charts.ranking_horizontal(
        base["Gestor"].tolist(), base["concluidos_gestor"].tolist(),
        cores=cores, textos_barra=textos, hovertexts=hovers,
        altura=max(340, 42 * len(base) + 40),
    ))


def _grafico_comparativo_gestor_equipe(df: pd.DataFrame):
    charts.cabecalho(
        "⚖️ Comparativo Gestor x Equipe",
        "Desempenho individual do gestor comparado à média de conclusão da sua equipe, com a base de cada um",
    )
    base = df[(df["total_gestor"] > 0) | (df["total_equipe"] > 0)].copy()
    if base.empty:
        st.caption("Sem dados suficientes para o comparativo.")
        return
    base = _ordenar_ranking(base)
    total_gestores = len(base)
    base_exibida = base.head(15)
    if len(base_exibida) < total_gestores:
        st.caption(f"Exibindo {len(base_exibida)} de {total_gestores} gestores (mesma ordenação do Ranking dos Gestores).")

    pct_gestor = [v if pd.notna(v) else 0.0 for v in base_exibida["pct_gestor"]]
    pct_equipe = [v if pd.notna(v) else 0.0 for v in base_exibida["pct_equipe"]]
    # rótulo em cima da barra fica curto (percentual + quantidade compactos,
    # ex.: "100,0% (78/78)") — o tooltip mostra a versão por extenso, com a
    # base "N de M" explícita; nenhum dos dois mostra só o percentual sozinho.
    # sem percentual no rótulo em cima da barra — o eixo Y já é a escala de
    # 0 a 100%, então "100,0%" ali seria redundante; a quantidade continua
    # visível (é a informação que o eixo sozinho não dá).
    curtos_gestor = [_rotulo_quantidade(c, t) for c, t in zip(base_exibida["concluidos_gestor"], base_exibida["total_gestor"])]
    curtos_equipe = [_rotulo_quantidade(c, t) for c, t in zip(base_exibida["concluidos_equipe"], base_exibida["total_equipe"])]
    rotulos_gestor = [_rotulo_percentual_base(c, t) for c, t in zip(base_exibida["concluidos_gestor"], base_exibida["total_gestor"])]
    rotulos_equipe = [_rotulo_percentual_base(c, t) for c, t in zip(base_exibida["concluidos_equipe"], base_exibida["total_equipe"])]
    hovers_gestor = [f"<b>{g}</b><br>Gestor: {r}" for g, r in zip(base_exibida["Gestor"], rotulos_gestor)]
    hovers_equipe = [f"<b>{g}</b><br>Equipe: {r}" for g, r in zip(base_exibida["Gestor"], rotulos_equipe)]

    charts.mostrar(charts.barras_agrupadas(
        base_exibida["Gestor"].tolist(),
        {"Gestor": pct_gestor, "Equipe": pct_equipe},
        cores=[CORES["accent"], CORES["categorica"][2]],
        textos={"Gestor": curtos_gestor, "Equipe": curtos_equipe},
        hovertextos={"Gestor": hovers_gestor, "Equipe": hovers_equipe},
        altura=460,
    ))


def _grafico_ranking_equipes(df: pd.DataFrame):
    charts.cabecalho("🥇 Ranking das Equipes", "Média de conclusão de treinamentos dos colaboradores de cada equipe (sem contar o gestor)")
    base = df[df["total_equipe"] > 0].sort_values("pct_equipe", ascending=False)
    if base.empty:
        st.caption("Nenhuma equipe com treinamentos atribuídos nos filtros atuais.")
        return
    cores = [charts.cor_por_taxa(v) for v in base["pct_equipe"]]
    textos = [_pct(v, 1) for v in base["pct_equipe"]]
    charts.mostrar(charts.ranking_horizontal(
        base["Gestor"].tolist(), base["pct_equipe"].tolist(), cores=cores, textos_barra=textos,
        altura=max(320, 36 * len(base) + 40), sufixo_eixo_x="%",
    ))


def _grafico_situacao_lideranca(df: pd.DataFrame):
    charts.cabecalho("🧭 Situação da Liderança", "Status atual dos treinamentos dos próprios gestores (não das equipes)")
    concluido = int(df["concluidos_gestor"].sum())
    em_andamento = int(df["em_andamento_gestor"].sum())
    pendente = max(int(df["total_gestor"].sum()) - concluido - em_andamento, 0)
    if concluido + em_andamento + pendente == 0:
        st.caption("Sem treinamentos atribuídos aos gestores nos filtros atuais.")
        return
    # cores com o mesmo significado usado no resto do sistema (dashboard,
    # badges de status): verde = bom/concluído, azul = em andamento,
    # vermelho = pendência/crítico — nunca pendência em verde, que sinaliza
    # justamente o oposto (situação resolvida) em toda a aplicação.
    charts.mostrar(charts.rosca(
        ["Concluído", "Em Andamento", "Pendente"], [concluido, em_andamento, pendente],
        cores=[CORES["status_bom"], CORES["accent"], CORES["status_critico"]],
    ))


def _serie_mensal_concluidos(df_treino: pd.DataFrame, nomes_norm: set) -> tuple[list, list]:
    """Chamada duas vezes por render (liderança e equipes) com o mesmo
    `df_treino` — reaproveita `_nome_norm`/`_data_conclusao_dt` já calculadas
    em render() em vez de normalizar nome e converter data de novo a cada
    chamada."""
    if df_treino.empty or not nomes_norm:
        return [], []
    nome_norm = (
        df_treino["_nome_norm"] if "_nome_norm" in df_treino.columns
        else df_treino["nome_colaborador_relacionado"].map(normalizar_nome)
    )
    data_conclusao_dt = (
        df_treino["_data_conclusao_dt"] if "_data_conclusao_dt" in df_treino.columns
        else pd.to_datetime(df_treino["data_conclusao"], errors="coerce")
    )
    mascara = nome_norm.isin(nomes_norm) & df_treino["status"].isin(STATUS_CONCLUIDOS)
    mes = data_conclusao_dt[mascara].dt.to_period("M").dropna()
    if mes.empty:
        return [], []
    contagem = mes.value_counts().sort_index()
    rotulos = [p.strftime("%m/%Y") for p in contagem.index]
    return rotulos, contagem.tolist()


def _grafico_evolucao_lideranca(df_treino_periodo: pd.DataFrame, gestores_norm: set):
    charts.cabecalho("📈 Evolução da Liderança", "Treinamentos concluídos pelos gestores, por mês")
    rotulos, valores = _serie_mensal_concluidos(df_treino_periodo, gestores_norm)
    if not rotulos:
        st.caption("Sem treinamentos concluídos nos filtros atuais para montar a evolução.")
        return
    charts.mostrar(charts.linha(rotulos, valores), altura=320)


def _grafico_evolucao_equipes(df_treino_periodo: pd.DataFrame, membros_norm: set):
    charts.cabecalho("📉 Evolução das Equipes", "Treinamentos concluídos pelas equipes dos gestores, por mês")
    rotulos, valores = _serie_mensal_concluidos(df_treino_periodo, membros_norm)
    if not rotulos:
        st.caption("Sem treinamentos concluídos nos filtros atuais para montar a evolução.")
        return
    charts.mostrar(charts.linha(rotulos, valores, cor=CORES["categorica"][2]), altura=320)


def _grafico_desempenho_area(df: pd.DataFrame):
    charts.cabecalho("🏢 Desempenho por Área", "Média de conclusão dos gestores agrupada por área")
    base = df[df["total_gestor"] > 0]
    if base.empty:
        st.caption("Sem dados suficientes para desempenho por área.")
        return
    agg = base.groupby("Área").agg(concluidos=("concluidos_gestor", "sum"), total=("total_gestor", "sum")).reset_index()
    agg["taxa"] = (agg["concluidos"] / agg["total"] * 100).round(1)
    agg = agg.sort_values("taxa", ascending=False)
    cores = [charts.cor_por_taxa(v) for v in agg["taxa"]]
    textos = [_pct(v, 1) for v in agg["taxa"]]
    charts.mostrar(charts.ranking_horizontal(
        agg["Área"].tolist(), agg["taxa"].tolist(), cores=cores, textos_barra=textos,
        altura=max(280, 40 * len(agg)), sufixo_eixo_x="%",
    ))


# ------------------------------------------------------------------------- tabelas

def _tabela_executiva(df: pd.DataFrame):
    charts.cabecalho(
        "📋 Tabela Executiva",
        "Detalhamento por gestor — ordenado por concluídos (desc.), depois taxa (desc.), depois pendentes (asc.); colunas também podem ser ordenadas manualmente",
    )
    ordenada = _ordenar_tabela(df)
    tabela = ordenada[[
        "Gestor", "Cargo", "Área",
        "total_gestor", "concluidos_gestor", "pendente_gestor", "pct_gestor",
        "Quantidade de Colaboradores", "total_equipe", "concluidos_equipe", "pct_equipe", "diferenca_pct",
        "ultimo_acesso",
    ]].rename(columns={
        "total_gestor": "Atribuídos (Gestor)", "concluidos_gestor": "Concluídos (Gestor)",
        "pendente_gestor": "Pendentes (Gestor)", "pct_gestor": "Taxa do Gestor",
        "Quantidade de Colaboradores": "Colaboradores na Equipe",
        "total_equipe": "Atribuídos (Equipe)", "concluidos_equipe": "Concluídos (Equipe)",
        "pct_equipe": "Taxa da Equipe", "diferenca_pct": "Diferença Gestor - Equipe",
        "ultimo_acesso": "Último Acesso",
    })
    tabela["Taxa do Gestor"] = tabela["Taxa do Gestor"].map(lambda v: _pct(v, 1) if pd.notna(v) else "—")
    tabela["Taxa da Equipe"] = tabela["Taxa da Equipe"].map(lambda v: _pct(v, 1) if pd.notna(v) else "—")
    tabela["Diferença Gestor - Equipe"] = tabela["Diferença Gestor - Equipe"].map(
        lambda v: ("—" if pd.isna(v) else (f"+{_fmt(v, 1)} p.p." if v >= 0 else f"{_fmt(v, 1)} p.p."))
    )
    tables.listview(tabela, altura=min(560, 70 + 36 * len(tabela)), colunas_data=["Último Acesso"])


def _painel_atencao(df: pd.DataFrame):
    charts.cabecalho("🚨 Painel de Atenção", "Gestores que precisam de acompanhamento, com base em critérios já existentes no sistema")
    total_equipe = int(df["total_equipe"].sum())
    # mesma casa decimal de pct_equipe (1 casa) — ver comentário equivalente em _cards_executivos.
    media_equipes = round((df["concluidos_equipe"].sum() / total_equipe * 100), 1) if total_equipe else 0.0
    limite_acesso = pd.Timestamp.now() - pd.Timedelta(days=DIAS_SEM_ACESSO_ATENCAO)

    def _motivos(row) -> list[str]:
        motivos = []
        if row["pendente_gestor"] > 0:
            motivos.append(f"{int(row['pendente_gestor'])} treinamento(s) pendente(s)")
        if row["total_gestor"] > 0 and (pd.isna(row["ultimo_acesso"]) or row["ultimo_acesso"] < limite_acesso):
            motivos.append(f"Sem acesso há mais de {DIAS_SEM_ACESSO_ATENCAO} dias")
        if row["total_gestor"] > 0 and row["pct_gestor"] < TAXA_BAIXA_ATENCAO:
            motivos.append(f"Taxa de conclusão baixa ({_pct(row['pct_gestor'], 1)})")
        if row["total_equipe"] > 0 and row["pct_equipe"] < media_equipes:
            motivos.append("Equipe abaixo da média geral")
        return motivos

    df = df.copy()
    df["_motivos"] = df.apply(_motivos, axis=1)
    atencao = df[df["_motivos"].map(len) > 0].sort_values("pct_gestor", na_position="first")
    if atencao.empty:
        st.caption("Nenhum gestor em situação de atenção com os critérios atuais.")
        return

    tabela = pd.DataFrame({
        "Gestor": atencao["Gestor"],
        "Motivo(s)": atencao["_motivos"].map(lambda m: "; ".join(m)),
        "Percentual do Gestor": atencao["pct_gestor"].map(lambda v: _pct(v, 1) if pd.notna(v) else "—"),
        "Último Acesso": atencao["ultimo_acesso"].map(lambda v: formatar_data_br(v, com_hora=False) if pd.notna(v) else "Nunca acessou"),
    })
    tables.listview(tabela, altura=min(360, 70 + 36 * len(tabela)))


def _comparativo_gestor_equipe_tabela(df: pd.DataFrame):
    charts.cabecalho("🔍 Comparativo Gestor x Equipe (%)", "Diferença entre o percentual individual do gestor e a média da sua equipe, com a base de cada um")
    base = df[(df["total_gestor"] > 0) | (df["total_equipe"] > 0)].copy()
    if base.empty:
        st.caption("Sem dados suficientes para o comparativo.")
        return
    base = base.sort_values("diferenca_pct", ascending=False, na_position="last")
    tabela = pd.DataFrame({
        "Gestor": base["Gestor"],
        "Gestor (%)": [_rotulo_percentual_base(c, t) for c, t in zip(base["concluidos_gestor"], base["total_gestor"])],
        "Equipe (%)": [_rotulo_percentual_base(c, t) for c, t in zip(base["concluidos_equipe"], base["total_equipe"])],
        "Diferença (p.p.)": base["diferenca_pct"].map(
            lambda v: ("—" if pd.isna(v) else (f"+{_fmt(v, 1)}" if v >= 0 else _fmt(v, 1)))
        ),
    })
    tables.listview(tabela, altura=min(420, 70 + 36 * len(tabela)))
