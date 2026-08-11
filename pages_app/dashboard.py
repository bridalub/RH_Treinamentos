"""Dashboard Inicial — indicadores executivos, gráficos e insights automáticos.

Fluxo único (item 9 do ajuste solicitado): carregar -> normalizar -> aplicar
permissão do usuário -> aplicar filtros em cascata -> calcular métricas -> cartões
-> gráficos -> análise inteligente. Todos os componentes leem do MESMO par de
DataFrames já filtrados (`pessoas_escopo` e `treinos_escopo`), para que cartões,
gráficos e insights nunca divirjam entre si.
"""
import pandas as pd
import streamlit as st

from components import cards, charts
from components.theme import CORES, STATUS_TREINAMENTO_COR
from services.colaboradores_service import carregar_colaboradores
from services.treinamentos_service import carregar_treinamentos, STATUS_CONCLUIDOS
from services.revisoes_service import nomes_planilha_do_colaborador
from services import matching_service as ms
from utils.csv_io import carregar_estado
from utils.normalizacao import normalizar_nome
from utils.formatacao import formatar_numero_br, formatar_percentual_br, MESES
from utils.auth import usuario_atual


def _fmt(n) -> str:
    return formatar_numero_br(n)


def _pct(n, casas: int = 0) -> str:
    return formatar_percentual_br(n, casas)


def _stats_concluidos(
    df_treino: pd.DataFrame,
    nomes: set[str] | None = None,
    nomes_norm: set[str] | None = None,
    nomes_planilha_norm: set[str] | None = None,
) -> tuple[int, int, float]:
    """total, concluídos e taxa % — NaN na taxa quando não há treinamentos atribuídos.

    Aceita três chaves (qualquer combinação):
    - nomes: grafia de exibição em nome_colaborador_relacionado
    - nomes_norm: normalizar_nome(relacionado) — cobre (B2C) e variações
    - nomes_planilha_norm: nome_normalizado da plataforma (ex.: ALEXANDRE COSTA
      via override), mesmo se o vínculo em CSV ainda estiver defasado
    """
    if df_treino.empty:
        return 0, 0, float("nan")
    nomes = nomes or set()
    nomes_norm = nomes_norm or set()
    nomes_planilha_norm = nomes_planilha_norm or set()
    if not nomes and not nomes_norm and not nomes_planilha_norm:
        return 0, 0, float("nan")

    mascara = pd.Series(False, index=df_treino.index)
    if nomes:
        mascara |= df_treino["nome_colaborador_relacionado"].isin(nomes)
    if nomes_norm:
        mascara |= df_treino["nome_colaborador_relacionado"].map(normalizar_nome).isin(nomes_norm)
    if nomes_planilha_norm:
        mascara |= df_treino["nome_normalizado"].isin(nomes_planilha_norm)

    base = df_treino[mascara]
    total = len(base)
    concluidos = int(base["status"].isin(STATUS_CONCLUIDOS).sum()) if total else 0
    taxa = round(concluidos / total * 100, 1) if total else float("nan")
    return total, concluidos, taxa


def _media_cursos_concluidos(
    df_treino: pd.DataFrame,
    nomes: set[str],
) -> tuple[float, int, int]:
    """Média de cursos concluídos por pessoa, total concluídos e qtd de pessoas no cálculo."""
    if not nomes:
        return float("nan"), 0, 0
    por_pessoa = []
    for nome in nomes:
        _, concluidos, _ = _stats_concluidos(df_treino, nomes={nome}, nomes_norm={normalizar_nome(nome)})
        por_pessoa.append(concluidos)
    qtd = len(por_pessoa)
    total_concluidos = int(sum(por_pessoa))
    media = round(total_concluidos / qtd, 1) if qtd else float("nan")
    return media, total_concluidos, qtd


def _filtro_multiselect(label: str, opcoes: list[str], key: str) -> list[str] | None:
    """Multiselect com opção 'Todos'. Retorna None quando não há restrição.

    Também limpa do session_state quaisquer valores que não existam mais nas
    opções atuais — necessário porque os filtros de Colaborador e Cargo são
    dependentes (cascata) e suas opções mudam quando o filtro anterior muda.

    'Todos' e opções específicas são mutuamente excludentes: escolher um nome
    remove 'Todos' da seleção, e escolher 'Todos' limpa as escolhas específicas
    (senão o Streamlit apenas soma as duas e o filtro nunca é aplicado de fato).
    """
    opcoes_validas = ["Todos"] + opcoes
    chave_prev = key + "__prev"

    valor_atual = [v for v in st.session_state.get(key, ["Todos"]) if v in opcoes_validas] or ["Todos"]
    st.session_state[key] = valor_atual
    st.session_state[chave_prev] = list(valor_atual)

    def _on_change():
        atual = st.session_state.get(key, [])
        anterior = st.session_state.get(chave_prev, ["Todos"])
        novos = [v for v in atual if v not in anterior]
        if "Todos" in novos:
            atual = ["Todos"]
        elif "Todos" in atual and len(atual) > 1:
            atual = [v for v in atual if v != "Todos"]
        st.session_state[key] = atual or ["Todos"]

    escolha = st.multiselect(label, opcoes_validas, key=key, on_change=_on_change)
    if not escolha or "Todos" in escolha:
        return None
    return escolha


def _mapa_lideres(validos: pd.DataFrame) -> tuple[dict, list[tuple[str, str]]]:
    """gestor_normalizado -> nome de exibição, e lista (norm, nome) ordenada alfabeticamente."""
    grupos = validos[validos["gestor_normalizado"] != ""]
    mapa = {}
    for gestor_norm, grupo in grupos.groupby("gestor_normalizado"):
        candidatos = validos.loc[validos["nome_normalizado"] == gestor_norm, "nome"]
        nome_exibicao = candidatos.mode().iloc[0] if not candidatos.empty else grupo["gestor_nome"].mode().iloc[0]
        mapa[gestor_norm] = nome_exibicao
    lista_ordenada = sorted(mapa.items(), key=lambda par: par[1])
    return mapa, lista_ordenada


def render():
    st.markdown("## Painel de Controle Inicial")
    st.caption("Acompanhe a evolução dos treinamentos por líder, colaborador e período")

    df_colab = carregar_colaboradores()
    df_treino_total = carregar_treinamentos()
    validos = df_colab[df_colab["is_pessoa_valida"] == "True"].copy()

    if validos.empty:
        st.info("Nenhum colaborador importado ainda. Vá em **Atualização** para importar as planilhas.")
        return

    if not df_treino_total.empty:
        df_treino_total = df_treino_total.copy()
        df_treino_total["_data_conclusao_dt"] = pd.to_datetime(df_treino_total["data_conclusao"], errors="coerce")

    validos["gestor_normalizado"] = validos["gestor_nome"].map(normalizar_nome)
    validos["cargo"] = validos["cargo"].replace("", "Não informado")
    mapa_lideres, lideres_ordenados = _mapa_lideres(validos)

    # ------------------------------------------------------ permissão do usuário
    usuario = usuario_atual() or {}
    perfil = usuario.get("perfil")
    lideres_norm_filtro: list[str] | None = None
    bloqueado_para_um_lider = False

    if perfil == "GESTOR":
        meu_norm = normalizar_nome(usuario.get("nome", ""))
        if meu_norm in mapa_lideres:
            lideres_norm_filtro = [meu_norm]
            bloqueado_para_um_lider = True
        else:
            st.warning(
                "Nenhuma equipe foi encontrada para o seu usuário na base de colaboradores. "
                "Fale com o administrador para vincular seu login ao nome correto do coordenador/líder."
            )
            return

    # -------------------------------------------------------------------- filtros
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)

    with col_f1:
        if bloqueado_para_um_lider:
            st.text_input("Coordenador ou Líder", value=mapa_lideres[lideres_norm_filtro[0]], disabled=True)
        else:
            opcoes_lideres = [nome for _, nome in lideres_ordenados]
            sel = _filtro_multiselect("Coordenador ou Líder", opcoes_lideres, "dash_lideres")
            if sel:
                lideres_norm_filtro = [norm for norm, nome in lideres_ordenados if nome in sel]

    pessoas_escopo = validos if not lideres_norm_filtro else validos[validos["gestor_normalizado"].isin(lideres_norm_filtro)]

    with col_f2:
        anos_disponiveis = (
            sorted(df_treino_total["_data_conclusao_dt"].dt.year.dropna().unique().astype(int), reverse=True)
            if not df_treino_total.empty else []
        )
        ano_sel = st.selectbox("Ano", ["Todos"] + [str(a) for a in anos_disponiveis], key="dash_ano")

    with col_f3:
        mes_sel_nome = st.selectbox("Mês", ["Todos"] + MESES, key="dash_mes")
        mes_sel = MESES.index(mes_sel_nome) + 1 if mes_sel_nome != "Todos" else None

    with col_f4:
        status_observados = set(df_treino_total["status"].unique()) if not df_treino_total.empty else set()
        status_disponiveis = [s for s in STATUS_TREINAMENTO_COR if s in status_observados]
        status_disponiveis += sorted(status_observados - set(status_disponiveis))
        status_sel = _filtro_multiselect("Status do Treinamento", status_disponiveis, "dash_status")

    if pessoas_escopo.empty:
        st.info("Nenhum colaborador corresponde à combinação de filtros selecionada.")
        return

    nomes_escopo = set(pessoas_escopo["nome"])
    # filtros de status/período antes do recorte por nome: o comparativo
    # Gestor x Equipe precisa dos treinamentos do próprio líder (que normalmente
    # não está em pessoas_escopo) com a MESMA regra de período/status da equipe.
    treinos_filtrados = df_treino_total if not df_treino_total.empty else df_treino_total
    if status_sel and not treinos_filtrados.empty:
        treinos_filtrados = treinos_filtrados[treinos_filtrados["status"].isin(status_sel)]
    if not treinos_filtrados.empty and (ano_sel != "Todos" or mes_sel is not None):
        # o período filtra pela Data de Conclusão: só entra quem foi concluído
        # naquele mês/ano — registros ainda sem conclusão ficam de fora quando
        # o filtro está ativo (comportamento escolhido para este painel).
        datas_conclusao = treinos_filtrados["_data_conclusao_dt"]
        mascara = pd.Series(True, index=treinos_filtrados.index)
        if ano_sel != "Todos":
            mascara &= datas_conclusao.dt.year == int(ano_sel)
        if mes_sel is not None:
            mascara &= datas_conclusao.dt.month == mes_sel
        treinos_filtrados = treinos_filtrados[mascara]
    treinos_escopo = (
        treinos_filtrados[treinos_filtrados["nome_colaborador_relacionado"].isin(nomes_escopo)]
        if not treinos_filtrados.empty else treinos_filtrados
    )

    # ----------------------------------------------------------------------- kpis
    total_pessoas = pessoas_escopo.drop_duplicates("nome_normalizado").shape[0]
    total_atribuidos = len(treinos_escopo)
    total_concluidos = int(treinos_escopo["status"].isin(STATUS_CONCLUIDOS).sum()) if total_atribuidos else 0
    taxa_geral = (total_concluidos / total_atribuidos * 100) if total_atribuidos else 0.0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        cards.kpi("Pessoas na Seleção", _fmt(total_pessoas), "Colaboradores acompanhados no filtro atual", icone="👥")
    with c2:
        cards.kpi("Treinamentos Atribuídos", _fmt(total_atribuidos), "Total de cursos vinculados aos colaboradores", icone="📚")
    with c3:
        cards.kpi("Treinamentos Concluídos", _fmt(total_concluidos), "Cursos finalizados na seleção atual", icone="✅")
    with c4:
        cards.kpi("Taxa de Conclusão", _pct(taxa_geral), f"{_fmt(total_concluidos)} de {_fmt(total_atribuidos)} treinamentos concluídos", icone="📈")

    estado_import = carregar_estado("ultima_importacao_treinamentos")
    if estado_import and estado_import.get("export_parcial"):
        st.warning(
            f"⚠️ A última importação de treinamentos trouxe **{estado_import.get('linhas_lidas')}** registros, "
            f"mas o relatório de origem declarava **{estado_import.get('contagem_declarada')}**. "
            "Os indicadores abaixo refletem apenas os dados efetivamente importados — não é a base completa."
        )

    st.write("")

    # ------------------------------------------------- gráfico 1: por colaborador
    # Dois recortes lado a lado do MESMO conjunto de pessoas (mesma ordem): a
    # taxa % sozinha é injusta (quem fez 1 curso e concluiu bate 100%, à frente
    # de quem concluiu 100 cursos) — por isso o volume absoluto de concluídos
    # aparece ao lado, como contexto.
    #
    # O gráfico parte do ROSTER completo de pessoas_escopo (não só de quem tem
    # linha em treinos_escopo) e faz left-join com os treinamentos — senão
    # colaboradores sem nenhum treinamento (0 registros) somem do gráfico
    # enquanto o card "Pessoas na Seleção" continua contando com eles, gerando
    # números que não batem entre o card e os gráficos.
    agg = pd.DataFrame()
    roster = pessoas_escopo.drop_duplicates("nome")[["nome", "cargo", "gestor_nome"]].copy()
    if roster.empty:
        charts.cabecalho("Taxa de Conclusão por Colaborador", "Percentual de treinamentos concluídos por colaborador dentro da seleção atual")
        st.caption("Nenhum colaborador na seleção atual.")
    else:
        if not treinos_escopo.empty:
            agg_treinos = (
                treinos_escopo[treinos_escopo["nome_colaborador_relacionado"] != ""]
                .groupby("nome_colaborador_relacionado")
                .agg(total=("status", "size"), concluidos=("status", lambda s: s.isin(STATUS_CONCLUIDOS).sum()))
                .reset_index()
                .rename(columns={"nome_colaborador_relacionado": "nome"})
            )
        else:
            agg_treinos = pd.DataFrame(columns=["nome", "total", "concluidos"])

        agg = roster.merge(agg_treinos, on="nome", how="left")
        agg["total"] = agg["total"].fillna(0).astype(int)
        agg["concluidos"] = agg["concluidos"].fillna(0).astype(int)
        agg["pendentes"] = agg["total"] - agg["concluidos"]
        agg["taxa"] = agg.apply(lambda r: round(r["concluidos"] / r["total"] * 100, 1) if r["total"] else 0.0, axis=1)
        agg["gestor_nome"] = agg["gestor_nome"].replace("", "Sem líder definido").fillna("Sem líder definido")
        agg["cargo"] = agg["cargo"].fillna("Não informado")

        agg = agg.sort_values(["concluidos", "taxa"], ascending=[False, False])

        total_no_grafico = len(agg)
        agg_exibida = agg.head(10)

        if len(agg_exibida) < total_no_grafico:
            st.caption(f"Exibindo {len(agg_exibida)} de {total_no_grafico} colaboradores na seleção atual.")

        cores = [charts.cor_por_taxa(t) for t in agg_exibida["taxa"]]
        hovers = [
            f"<b>{r['nome']}</b><br>Cargo: {r['cargo']}<br>Coordenador/líder: {r['gestor_nome']}<br>"
            f"Atribuídos: {_fmt(r['total'])}<br>Concluídos: {_fmt(r['concluidos'])}<br>"
            f"Pendentes: {_fmt(r['pendentes'])}<br>Taxa: {_pct(r['taxa'])}"
            for _, r in agg_exibida.iterrows()
        ]

        col_qtd, col_taxa = st.columns(2)
        with col_qtd:
            charts.cabecalho(
                "📚 Quantidade de Cursos Concluídos por Colaborador",
                "Total de treinamentos concluídos por colaborador — mesma seleção e ordem do gráfico ao lado",
            )
            # gráfico de QUANTIDADE (não de desempenho): uma única cor para
            # todas as barras — a cor por faixa de taxa (`cores`) é só para o
            # gráfico de Taxa ao lado, nunca para volume/contagem.
            textos_qtd = [f"{_fmt(c)} concluído" if c == 1 else f"{_fmt(c)} concluídos" for c in agg_exibida["concluidos"]]
            charts.mostrar(charts.ranking_horizontal(
                agg_exibida["nome"].tolist(), agg_exibida["concluidos"].tolist(),
                textos_barra=textos_qtd, hovertexts=hovers,
            ))

        with col_taxa:
            charts.cabecalho(
                "📈 Taxa de Conclusão por Colaborador",
                "Percentual de treinamentos concluídos por colaborador dentro da seleção atual",
            )
            textos_taxa = [f"{_pct(t)} — {_fmt(c)} de {_fmt(tt)}" for t, c, tt in zip(agg_exibida["taxa"], agg_exibida["concluidos"], agg_exibida["total"])]
            charts.mostrar(charts.ranking_horizontal(
                agg_exibida["nome"].tolist(), agg_exibida["taxa"].tolist(),
                cores=cores, textos_barra=textos_taxa, hovertexts=hovers, sufixo_eixo_x="%",
            ))

    st.write("")

    # -------------------------------------------- gráfico 2: gestor x equipe
    # Só para perfil GESTOR: total de cursos concluídos do gestor vs média de
    # cursos concluídos por pessoa na equipe (sem contar o gestor).
    agg_comp = pd.DataFrame()
    if perfil == "GESTOR" and lideres_norm_filtro:
        charts.cabecalho(
            "⚖️ Gestor × Média da Equipe",
            "Seu total de cursos concluídos comparado à média de cursos concluídos por pessoa da sua equipe",
        )
        gestor_norm = lideres_norm_filtro[0]
        nome_gestor = mapa_lideres.get(gestor_norm, gestor_norm)
        nomes_gestor = set(validos.loc[validos["nome_normalizado"] == gestor_norm, "nome"])
        if not nomes_gestor:
            nomes_gestor = {nome_gestor}
        # inclui nomes da plataforma ligados a este gestor (semente/override),
        # ex.: ALEXANDRE COSTA → ALEXANDRE DAUFENBACH — mesmo se o CSV ainda
        # estiver com vínculo antigo, o filtro por nome_normalizado da planilha
        # encontra os cursos.
        planilha_gestor = nomes_planilha_do_colaborador(gestor_norm)

        membros = pessoas_escopo[pessoas_escopo["gestor_normalizado"] == gestor_norm]
        nomes_equipe = set(membros.loc[membros["nome_normalizado"] != gestor_norm, "nome"])

        total_g, concl_g, pct_g = _stats_concluidos(
            treinos_filtrados,
            nomes=nomes_gestor,
            nomes_norm={gestor_norm},
            nomes_planilha_norm=planilha_gestor,
        )
        media_e, concl_e, qtd_e = _media_cursos_concluidos(treinos_filtrados, nomes_equipe)
        total_e, _, pct_e = _stats_concluidos(
            treinos_filtrados,
            nomes=nomes_equipe,
            nomes_norm={normalizar_nome(n) for n in nomes_equipe},
        )

        if concl_g == 0 and (pd.isna(media_e) or media_e == 0):
            st.caption("Sem cursos concluídos por você ou pela sua equipe nos filtros atuais.")
        else:
            agg_comp = pd.DataFrame([{
                "gestor_norm": gestor_norm,
                "gestor": nome_gestor,
                "colaboradores": qtd_e,
                "total_gestor": total_g, "concluidos_gestor": concl_g, "pct_gestor": pct_g,
                "total_equipe": total_e, "concluidos_equipe": concl_e, "pct_equipe": pct_e,
                "media_equipe": media_e,
            }])
            # Gestor = total dele; Equipe = média por pessoa
            categorias = ["Gestor", "Média da Equipe"]
            valores = [
                float(concl_g),
                float(media_e) if pd.notna(media_e) else 0.0,
            ]
            textos = [
                f"{_fmt(concl_g)} concluído" if concl_g == 1 else f"{_fmt(concl_g)} concluídos",
                (
                    "Sem dados"
                    if pd.isna(media_e)
                    else f"{_fmt(media_e)} por pessoa — {_fmt(concl_e)} no total"
                ),
            ]
            cores = [CORES["accent"], CORES["categorica"][2]]
            hovers = [
                (
                    f"<b>Gestor</b><br>{nome_gestor}<br>"
                    f"Concluídos: {_fmt(concl_g)}<br>Atribuídos: {_fmt(total_g)}<br>"
                    f"Taxa: {_pct(pct_g, 1) if pd.notna(pct_g) else '—'}"
                ),
                (
                    f"<b>Média da Equipe</b><br>{_fmt(qtd_e)} colaborador(es)<br>"
                    f"Média: {_fmt(media_e) if pd.notna(media_e) else '—'} cursos concluídos/pessoa<br>"
                    f"Total da equipe: {_fmt(concl_e)} de {_fmt(total_e)}<br>"
                    f"Taxa agregada: {_pct(pct_e, 1) if pd.notna(pct_e) else '—'}"
                ),
            ]
            charts.mostrar(charts.ranking_horizontal(
                categorias, valores, cores=cores, textos_barra=textos,
                hovertexts=hovers, altura=260,
            ))

        st.write("")

    # ---------------------------------- situação dos treinamentos + análise (lado a lado)
    col_sit, col_insight = st.columns([0.62, 0.38])

    with col_sit:
        charts.cabecalho("📊 Situação dos Treinamentos", "Distribuição dos treinamentos conforme o status atual na plataforma")
        if treinos_escopo.empty:
            st.caption("Nenhum treinamento na seleção atual.")
        else:
            contagem_status = treinos_escopo["status"].value_counts()
            total_status = int(contagem_status.sum())
            ordem = list(contagem_status.index)
            valores_status = [int(contagem_status[s]) for s in ordem]
            cores_status = [STATUS_TREINAMENTO_COR.get(s, CORES["texto_mudo"]) for s in ordem]
            textos_status = [f"{_fmt(v)} ({_pct(v / total_status * 100, 1)})" for v in valores_status]
            hovers_status = [
                f"<b>{s}</b><br>Quantidade: {_fmt(v)}<br>Percentual: {_pct(v / total_status * 100, 1)}"
                for s, v in zip(ordem, valores_status)
            ]
            charts.mostrar(charts.ranking_horizontal(
                ordem, valores_status, cores=cores_status, textos_barra=textos_status,
                hovertexts=hovers_status, altura=max(260, 40 * len(ordem)),
            ))

    with col_insight:
        insights = _gerar_insights(pessoas_escopo, treinos_escopo, df_treino_total, agg, agg_comp, lideres_norm_filtro, mapa_lideres)
        cards.callout("🧠 Análise Inteligente", "Principais destaques e pontos de atenção da seleção atual", insights)


def _gerar_insights(
    pessoas_escopo: pd.DataFrame, treinos_escopo: pd.DataFrame, df_treino_total: pd.DataFrame,
    agg: pd.DataFrame, agg_comp: pd.DataFrame, lideres_norm_filtro: list[str] | None, mapa_lideres: dict,
) -> list[dict]:
    insights = []
    total_pessoas = pessoas_escopo.drop_duplicates("nome_normalizado").shape[0]
    insights.append({"nivel": "informativo", "texto": f"{total_pessoas} colaborador(es) analisado(s) na seleção atual."})

    if not lideres_norm_filtro:
        insights.append({"nivel": "informativo", "texto": "Nenhum coordenador ou líder específico selecionado — exibindo todos."})
    elif len(lideres_norm_filtro) == 1:
        insights.append({"nivel": "informativo", "texto": f"Visão da equipe de {mapa_lideres.get(lideres_norm_filtro[0], '—')}."})
    else:
        insights.append({"nivel": "informativo", "texto": f"{len(lideres_norm_filtro)} coordenadores/líderes selecionados."})

    if not agg.empty:
        melhor = agg.sort_values(["taxa", "total"], ascending=[False, False]).iloc[0]
        pior = agg.sort_values(["taxa", "total"], ascending=[True, False]).iloc[0]
        mais_pendencias = agg.sort_values("pendentes", ascending=False).iloc[0]

        insights.append({"nivel": "positivo", "texto": f"{melhor['nome']} tem a maior taxa de conclusão: {_pct(melhor['taxa'])}."})
        if pior["nome"] != melhor["nome"]:
            nivel_pior = "critico" if pior["taxa"] < 40 else "atencao"
            insights.append({"nivel": nivel_pior, "texto": f"{pior['nome']} tem a menor taxa de conclusão: {_pct(pior['taxa'])}."})
        if mais_pendencias["pendentes"] > 0:
            insights.append({"nivel": "atencao", "texto": f"{mais_pendencias['nome']} é quem mais tem treinamentos pendentes: {int(mais_pendencias['pendentes'])}."})

        abaixo_50 = int((agg["taxa"] < 50).sum())
        if abaixo_50:
            nivel = "critico" if total_pessoas and abaixo_50 / total_pessoas > 0.3 else "atencao"
            insights.append({"nivel": nivel, "texto": f"{abaixo_50} colaborador(es) estão com taxa de conclusão abaixo de 50%."})

        sem_conclusao = int((agg["concluidos"] == 0).sum())
        if sem_conclusao:
            insights.append({"nivel": "atencao", "texto": f"{sem_conclusao} colaborador(es) ainda não concluíram nenhum treinamento."})

    if not agg_comp.empty:
        r = agg_comp.iloc[0]
        media_e = r.get("media_equipe", float("nan"))
        if r["concluidos_gestor"] > 0 and pd.notna(media_e):
            if r["concluidos_gestor"] > media_e:
                insights.append({
                    "nivel": "positivo",
                    "texto": (
                        f"Você concluiu {_fmt(r['concluidos_gestor'])} curso(s); "
                        f"a média da equipe é {_fmt(media_e)} por pessoa."
                    ),
                })
            elif r["concluidos_gestor"] < media_e:
                insights.append({
                    "nivel": "atencao",
                    "texto": (
                        f"Você concluiu {_fmt(r['concluidos_gestor'])} curso(s); "
                        f"a média da equipe é {_fmt(media_e)} por pessoa."
                    ),
                })
            else:
                insights.append({
                    "nivel": "positivo",
                    "texto": f"Seu total de conclusões está alinhado com a média da equipe ({_fmt(media_e)} por pessoa).",
                })
        elif r["concluidos_gestor"] == 0 and pd.notna(media_e) and media_e > 0:
            insights.append({
                "nivel": "atencao",
                "texto": f"Você ainda não concluiu cursos próprios — a média da equipe é {_fmt(media_e)} por pessoa.",
            })

    if not treinos_escopo.empty:
        vencidos = treinos_escopo[treinos_escopo["status"] == "Em Andamento/Vencido"]
        qtd_vencidos = vencidos["nome_colaborador_relacionado"].nunique()
        if qtd_vencidos:
            insights.append({"nivel": "critico", "texto": f"{qtd_vencidos} colaborador(es) têm treinamentos em andamento e vencidos."})

        acesso = treinos_escopo.copy()
        acesso["ultimo_acesso_dt"] = pd.to_datetime(acesso["ultimo_acesso"], errors="coerce")
        por_pessoa_acesso = acesso.groupby("nome_colaborador_relacionado")["ultimo_acesso_dt"].max()
        limite = pd.Timestamp.now() - pd.Timedelta(days=30)
        sem_acesso_recente = int(((por_pessoa_acesso < limite) | por_pessoa_acesso.isna()).sum())
        if sem_acesso_recente:
            insights.append({"nivel": "atencao", "texto": f"{sem_acesso_recente} colaborador(es) sem acesso à plataforma nos últimos 30 dias."})

    if not df_treino_total.empty:
        sem_relacionamento = int(df_treino_total["situacao_relacionamento"].isin([ms.NAO_ENCONTRADO, ms.REVISAO_MANUAL]).sum())
        if sem_relacionamento:
            total_registros = len(df_treino_total)
            nivel = "critico" if total_registros and sem_relacionamento / total_registros > 0.1 else "atencao"
            insights.append({
                "nivel": nivel,
                "texto": (
                    f"{_fmt(sem_relacionamento)} treinamentos ainda não estão relacionados a um colaborador da base de "
                    "funcionários. Isso pode afetar os indicadores por equipe, cargo e liderança — veja Atualização."
                ),
            })

    return insights
