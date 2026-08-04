"""Equipes: agrupamento automático de colaboradores por gestor (a partir da base de funcionários)."""
import pandas as pd
import streamlit as st

from components import cards, tables
from pages_app import cadastro_colaboradores
from services.colaboradores_service import carregar_colaboradores, salvar_colaboradores
from services.colaboradores_ajustes_service import salvar_ajuste, remover_ajuste
from services.treinamentos_service import carregar_treinamentos
from services.logs_service import registrar
from utils.auth import usuario_atual
from utils.formatacao import MESES, formatar_numero_br as _fmt, formatar_percentual_br as _pct
from utils.normalizacao import normalizar_nome


def render():
    st.markdown("## Equipes")

    df_colab = carregar_colaboradores()
    validos = df_colab[df_colab["is_pessoa_valida"] == "True"].copy()
    if validos.empty:
        st.info("Nenhum colaborador importado ainda. Vá em **Atualização**.")
        return

    df_treino = carregar_treinamentos()
    df_treino = _filtrar_por_periodo(df_treino)
    stats_por_pessoa = _stats_por_pessoa(df_treino)

    # o mesmo gestor pode aparecer com pequenas variações de grafia entre equipes
    # (ex.: "TATIANE FRITZ" e "TATIANE FRITZ (INT)") — agrupa pelo nome normalizado
    # do gestor para não duplicar a mesma pessoa em cards separados.
    validos["gestor_normalizado"] = validos["gestor_nome"].map(normalizar_nome)

    gestores_norm = sorted(g for g in validos["gestor_normalizado"].unique() if g)

    # perfil GESTOR só pode ver a própria equipe, nunca a estrutura inteira.
    usuario = usuario_atual() or {}
    if usuario.get("perfil") == "GESTOR":
        meu_norm = normalizar_nome(usuario.get("nome", ""))
        if meu_norm not in gestores_norm:
            st.warning(
                "Nenhuma equipe foi encontrada para o seu usuário na base de colaboradores. "
                "Fale com o administrador para vincular seu login ao nome correto do coordenador/líder."
            )
            return
        gestores_norm = [meu_norm]
    else:
        lideres = validos[validos["gestor_normalizado"] == ""].drop_duplicates("nome_normalizado")
        st.caption(f"{lideres.shape[0]} liderança(s) no topo da estrutura (sem gestor acima na base atual).")
    for gestor_norm in gestores_norm:
        membros = validos[validos["gestor_normalizado"] == gestor_norm].drop_duplicates("nome_normalizado")
        linha_lider_df = validos[validos["nome_normalizado"] == gestor_norm]
        nome_gestor_exibicao = linha_lider_df["nome"].mode().iloc[0] if not linha_lider_df.empty else gestor_norm
        cargo_lider = linha_lider_df["cargo"].iloc[0] if not linha_lider_df.empty else ""

        membros_norm = membros["nome_normalizado"]
        completos_time = sum(stats_por_pessoa.get(m, (0, 0))[1] for m in membros_norm)
        total_time = sum(stats_por_pessoa.get(m, (0, 0))[0] for m in membros_norm)
        pct = _pct(completos_time / total_time * 100) if total_time else "—"

        with st.expander(f"👤 {nome_gestor_exibicao} ({cargo_lider}) — {len(membros)} colaborador(es) · conclusão {pct}"):
            _tabela_membros_com_acoes(membros, stats_por_pessoa, usuario.get("login", "sistema"))


_LARGURAS_COLUNAS = [2.2, 1.1, 0.7, 1, 1, 1, 0.5, 0.5]


def _tabela_membros_com_acoes(membros: pd.DataFrame, stats_por_pessoa: dict, login_atual: str):
    """Mesma listagem de antes, mas com ação por linha: editar (leva pro
    Cadastro já com essa pessoa carregada) e excluir (some da base de
    funcionários — útil pra tirar quem não é realmente da equipe)."""
    cab = st.columns(_LARGURAS_COLUNAS)
    for col, titulo in zip(cab, ["Nome", "Cargo", "Equipe", "Treinamentos", "Completos", "Conclusão", "", ""]):
        if titulo:
            col.markdown(f"**{titulo}**")
    st.markdown("<hr style='margin:2px 0 8px 0;opacity:.15;'>", unsafe_allow_html=True)

    for _, m in membros.iterrows():
        total, completos = stats_por_pessoa.get(m["nome_normalizado"], (0, 0))
        conclusao = _pct(completos / total * 100) if total else "—"
        colaborador_id = m["colaborador_id"]

        col_nome, col_cargo, col_equipe, col_trein, col_comp, col_concl, col_editar, col_excluir = st.columns(_LARGURAS_COLUNAS)
        col_nome.write(m["nome"])
        col_cargo.write(m["cargo"])
        col_equipe.write(m["equipe_id"])
        col_trein.write(_fmt(total))
        col_comp.write(_fmt(completos))
        col_concl.write(conclusao)

        if col_editar.button("✏️", key=f"equipes_editar_{colaborador_id}", help=f"Editar {m['nome']}"):
            st.session_state["cadastro_colab_editando_id"] = colaborador_id
            st.switch_page(cadastro_colaboradores.PAGINA)

        with col_excluir.popover("🗑️", help=f"Excluir {m['nome']} da base de funcionários"):
            st.write(f"Excluir **{m['nome']}** da base de funcionários?")
            st.caption("Essa pessoa deixa de aparecer em qualquer equipe — use quando ela não faz parte da equipe de verdade.")
            if st.button("Confirmar exclusão", key=f"equipes_excluir_{colaborador_id}", type="primary"):
                df_colab_atual = carregar_colaboradores()
                df_colab_atual = df_colab_atual[df_colab_atual["colaborador_id"] != colaborador_id]
                salvar_colaboradores(df_colab_atual)
                # persiste a exclusão: sem isso, a próxima importação da BASE
                # FUNCIONÁRIOS recria essa linha do zero.
                chave_ajuste = f"{m['nome_normalizado']}|{m['equipe_id']}"
                salvar_ajuste(chave_ajuste, "EXCLUIDO", login_atual)
                remover_ajuste(normalizar_nome(m["nome"]))  # limpa um eventual "CRIADO" anterior — senão ele a recriaria
                registrar(login_atual, "EXCLUIR_COLABORADOR", f"{m['nome']} (id={colaborador_id})")
                st.success(f"{m['nome']} removido(a) da base de funcionários — a exclusão persiste em futuras importações.")
                st.rerun()


def _filtrar_por_periodo(df_treino: pd.DataFrame) -> pd.DataFrame:
    """Filtro de Ano/Mês por Data de Conclusão, disponível para qualquer perfil
    (GESTOR só enxerga a própria equipe, mas pode recortar por período do
    mesmo jeito que ADMIN/RH). Sem seleção, mostra o histórico completo."""
    if df_treino.empty:
        return df_treino
    df_treino = df_treino.copy()
    df_treino["_data_conclusao_dt"] = pd.to_datetime(df_treino["data_conclusao"], errors="coerce")

    anos_disponiveis = sorted(df_treino["_data_conclusao_dt"].dt.year.dropna().unique().astype(int), reverse=True)
    col_ano, col_mes = st.columns(2)
    with col_ano:
        ano_sel = st.selectbox("Ano", ["Todos"] + [str(a) for a in anos_disponiveis], key="equipes_ano")
    with col_mes:
        mes_sel_nome = st.selectbox("Mês", ["Todos"] + MESES, key="equipes_mes")
    mes_sel = MESES.index(mes_sel_nome) + 1 if mes_sel_nome != "Todos" else None

    if ano_sel == "Todos" and mes_sel is None:
        return df_treino

    # período filtra pela Data de Conclusão: treinamentos ainda não concluídos
    # ficam fora quando o filtro está ativo, igual ao comportamento do Dashboard.
    mascara = pd.Series(True, index=df_treino.index)
    if ano_sel != "Todos":
        mascara &= df_treino["_data_conclusao_dt"].dt.year == int(ano_sel)
    if mes_sel is not None:
        mascara &= df_treino["_data_conclusao_dt"].dt.month == mes_sel
    return df_treino[mascara]


def _stats_por_pessoa(df_treino: pd.DataFrame) -> dict:
    """Chave por nome_normalizado (não pelo texto literal de nome_colaborador_relacionado):
    quando a base de funcionários tem duas linhas pra mesma pessoa com nomes
    ligeiramente diferentes (ex.: "FULANO" e "FULANO - REALOCADO"), as duas
    devem enxergar os mesmos treinamentos, já que na plataforma ela é uma
    pessoa só."""
    if df_treino.empty:
        return {}
    df_treino = df_treino.copy()
    df_treino["_nome_norm"] = df_treino["nome_colaborador_relacionado"].map(normalizar_nome)
    agrupado = df_treino.groupby("_nome_norm")
    resultado = {}
    for nome_norm, grupo in agrupado:
        if not nome_norm:
            continue
        total = len(grupo)
        completos = int((grupo["status"] == "Completo").sum())
        resultado[nome_norm] = (total, completos)
    return resultado
