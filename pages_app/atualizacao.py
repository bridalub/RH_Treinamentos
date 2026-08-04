"""Atualização de Treinamentos: importação manual/automática + Revisão de Correspondências."""
from datetime import datetime

import streamlit as st

from components import cards, tables
from components.cards import badge_status
from services.colaboradores_service import importar_colaboradores, salvar_colaboradores, carregar_colaboradores, nomes_normalizados_validos
from services.treinamentos_service import importar_treinamentos, salvar_treinamentos, carregar_treinamentos, montar_listview, pendentes_revisao, aplicar_override_em_csv
from services.revisoes_service import carregar_overrides, salvar_override
from services.logs_service import registrar
from services import matching_service as ms
from utils.auth import usuario_atual
from utils.csv_io import salvar_estado
from utils.excel_import import AbaOficialNaoEncontradaError, ColunaEsperadaNaoEncontradaError
from utils.formatacao import formatar_numero_br as _fmt
from utils.normalizacao import normalizar_nome


def render():
    st.markdown("## Atualização de Treinamentos")

    aba_colab, aba_treino, aba_revisao = st.tabs(["Base de Colaboradores", "Treinamentos", "Revisão de Correspondências"])

    with aba_colab:
        _secao_colaboradores()
    with aba_treino:
        _secao_treinamentos()
    with aba_revisao:
        _secao_revisao()


def _secao_colaboradores():
    st.markdown("#### Importar BASE FUNCIONÁRIOS BRIDA")
    st.caption("Envie o arquivo .xls/.xlsx da planilha BASE FUNCIONÁRIOS BRIDA (aba 'BASE COMERCIAL'). A estrutura original não é alterada — apenas lida.")
    arquivo = st.file_uploader("Arquivo de colaboradores", type=["xls", "xlsx"], key="upload_colab")

    if arquivo is not None:
        try:
            df_preview = importar_colaboradores(arquivo)
        except Exception as e:
            st.error(f"Não foi possível importar o arquivo: {e}")
            return

        validos = int((df_preview["is_pessoa_valida"] == "True").sum())
        invalidos = len(df_preview) - validos
        c1, c2, c3 = st.columns(3)
        c1.metric("📄 Linhas lidas", _fmt(len(df_preview)))
        c2.metric("✅ Colaboradores válidos", _fmt(validos))
        c3.metric("⚠️ Linhas ignoradas (sem cargo)", _fmt(invalidos))

        if invalidos:
            with st.expander("Ver linhas ignoradas (cabeçalhos de subdivisão / sem cargo)"):
                st.dataframe(df_preview[df_preview["is_pessoa_valida"] == "False"][["nome", "equipe_id"]], hide_index=True, use_container_width=True)

        if st.button("Confirmar e salvar base de colaboradores", type="primary"):
            backup = salvar_colaboradores(df_preview)
            usuario = usuario_atual()
            registrar(usuario["login"] if usuario else "sistema", "IMPORTAR_COLABORADORES", f"{len(df_preview)} linhas, backup={backup}")
            st.success("Base de colaboradores atualizada com sucesso.")
            st.rerun()


def _secao_treinamentos():
    st.markdown("#### Importar DTB Bridalub - Por Usuário")
    st.caption(
        "O sistema usa exclusivamente a aba oficial **\"DTB Bridalub - Por Usuário (2)\"**. "
        "Se essa aba não existir no arquivo enviado, a importação é interrompida."
    )

    modo = st.radio("Como deseja obter a planilha?", ["Upload manual", "Executar automação"], horizontal=True)

    caminho_arquivo = None
    if modo == "Upload manual":
        caminho_arquivo = st.file_uploader("Arquivo de treinamentos (.xlsx)", type=["xlsx"], key="upload_treino")
    else:
        st.info("A automação abre o navegador, faz login no CSOD e baixa o relatório atualizado. As credenciais não são armazenadas.")
        col_cpf, col_senha = st.columns(2)
        cpf = col_cpf.text_input("CPF (apenas números)", key="cpf_csod")
        senha = col_senha.text_input("Senha", type="password", key="senha_csod")
        if st.button("Executar automação"):
            if not cpf or not senha:
                st.warning("Informe CPF e senha para executar a automação.")
            else:
                from automations.atualizar_treinamentos import (
                    baixar_planilha_treinamentos, AutomacaoError, LoginInvalidoError,
                )
                import os

                status = st.status("Iniciando automação no CSOD...", expanded=True)

                def _progresso(mensagem: str, _status=status):
                    _status.write(mensagem)

                try:
                    destino = os.path.join("data", "downloads")
                    # headless=True: a automação roda em segundo plano — o
                    # usuário nunca vê o navegador do CSOD abrindo na tela,
                    # só o andamento reportado abaixo (via on_progress).
                    caminho_baixado = baixar_planilha_treinamentos(
                        cpf, senha, destino, headless=True, on_progress=_progresso,
                    )
                    st.session_state["_caminho_treino_baixado"] = caminho_baixado
                    status.update(label="Automação concluída com sucesso!", state="complete", expanded=False)
                    st.success(f"Download concluído: {caminho_baixado}")
                except LoginInvalidoError as e:
                    status.update(label="Login recusado pelo CSOD — automação cancelada", state="error")
                    st.error(f"❌ {e}")
                except AutomacaoError as e:
                    status.update(label="Falha na automação", state="error")
                    st.error(f"Falha na automação: {e}")
                except Exception as e:
                    status.update(label="Falha inesperada na automação", state="error")
                    st.error(f"Falha inesperada na automação: {e}")
        caminho_arquivo = st.session_state.get("_caminho_treino_baixado")

    if not caminho_arquivo:
        return

    df_colab = carregar_colaboradores()
    if df_colab.empty:
        st.warning("Importe primeiro a base de colaboradores (aba anterior) — o relacionamento por nome depende dela.")
        return

    try:
        df_overrides = carregar_overrides()
        df_novo, resumo = importar_treinamentos(caminho_arquivo, df_colab, df_overrides)
    except AbaOficialNaoEncontradaError as e:
        st.error(str(e))
        return
    except ColunaEsperadaNaoEncontradaError as e:
        st.error(str(e))
        return
    except Exception as e:
        st.error(f"Erro inesperado ao importar: {e}")
        return

    if resumo.get("metadados_relatorio", {}).get("export_parcial"):
        meta = resumo["metadados_relatorio"]
        st.warning(
            f"⚠️ Export parcial: o relatório declara **{meta.get('contagem_declarada')}** registros, "
            f"mas apenas **{meta.get('linhas_lidas')}** foram lidos neste arquivo."
        )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🆕 Novos", _fmt(resumo.get("novos", 0)))
    c2.metric("🔄 Atualizados", _fmt(resumo.get("atualizados", 0)))
    c3.metric("➖ Inalterados", _fmt(resumo.get("inalterados", 0)))
    c4.metric("🔗 Relacionados", _fmt(resumo.get("relacionados_automatico", 0)))
    c5.metric("❗ Revisão / Não encontrado", _fmt(resumo.get("revisao_manual", 0) + resumo.get("nao_encontrado", 0)))

    st.markdown("##### Pré-visualização")
    listview = montar_listview(df_novo, df_colab)
    tables.listview(
        listview.head(200),
        colunas_data=["Data de Inscrição", "Data de Conclusão", "Último Acesso"],
    )

    if st.button("Confirmar e salvar treinamentos", type="primary"):
        backup = salvar_treinamentos(df_novo)
        salvar_estado("ultima_importacao_treinamentos", resumo["metadados_relatorio"])
        usuario = usuario_atual()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        registrar(
            usuario["login"] if usuario else "sistema", "IMPORTAR_TREINAMENTOS",
            f"novos={resumo.get('novos')} atualizados={resumo.get('atualizados')} "
            f"revisao={resumo.get('revisao_manual')} nao_encontrado={resumo.get('nao_encontrado')} backup={backup}",
        )
        st.session_state.pop("_caminho_treino_baixado", None)
        # mesmo sem nenhum registro novo ou alterado, a verificação em si
        # aconteceu — deixa isso explícito, em vez de uma mensagem genérica
        # que pode passar a impressão de que nada foi executado.
        if not resumo.get("novos") and not resumo.get("atualizados"):
            st.success(
                f"✅ Verificação concluída em {agora} — nenhum treinamento novo ou alterado, "
                "a base já estava em dia."
            )
        else:
            st.success(f"✅ Treinamentos atualizados com sucesso em {agora}.")
        st.rerun()


def _secao_revisao():
    st.markdown("#### Revisão de Correspondências")
    st.caption("Nomes da plataforma de treinamentos que não puderam ser relacionados automaticamente a um colaborador.")

    df_treino = carregar_treinamentos()
    if df_treino.empty:
        st.info("Nenhum treinamento importado ainda.")
        return

    df_colab = carregar_colaboradores()
    candidatos = nomes_normalizados_validos(df_colab)
    mapa_exibicao = {
        linha["nome_normalizado"]: linha["nome"]
        for _, linha in df_colab[df_colab["is_pessoa_valida"] == "True"].iterrows()
    }

    pendentes = pendentes_revisao(df_treino).drop_duplicates("nome_normalizado")
    if pendentes.empty:
        st.success("Nenhuma pendência de revisão no momento.")
        return

    busca = st.text_input(
        "Pesquisar por nome", key="revisao_busca_nome",
        placeholder="Digite parte do nome para filtrar a lista abaixo...",
    )
    if busca.strip():
        termo = normalizar_nome(busca)
        pendentes = pendentes[pendentes["nome_normalizado"].str.contains(termo, na=False)]

    st.caption(f"{len(pendentes)} pendência(s) encontrada(s).")
    if pendentes.empty:
        st.info("Nenhuma pendência encontrada para essa busca.")
        return

    usuario = usuario_atual()
    login_atual = usuario["login"] if usuario else "sistema"

    for _, linha in pendentes.iterrows():
        nome_norm = linha["nome_normalizado"]
        resultado = ms.relacionar_nome(nome_norm, candidatos)
        opcoes_nomes = [mapa_exibicao.get(c, c) for c in resultado.candidatos] if resultado.candidatos else []
        outras_opcoes = [n for n in sorted(set(mapa_exibicao.values())) if n not in opcoes_nomes]

        with st.container(border=True):
            col_info, col_acao = st.columns([1.4, 1])
            with col_info:
                st.markdown(f"**{linha['nome_colaborador_planilha']}**  \n{badge_status(linha['situacao_relacionamento'])}", unsafe_allow_html=True)
                if opcoes_nomes:
                    st.caption(f"Sugestões (ambíguas): {', '.join(opcoes_nomes)}")
            with col_acao:
                escolha = st.selectbox(
                    "Relacionar com", ["— selecione —"] + opcoes_nomes + outras_opcoes,
                    key=f"sel_{nome_norm}", label_visibility="collapsed",
                )
                col_b1, col_b2 = st.columns(2)
                if col_b1.button("Confirmar", key=f"btn_ok_{nome_norm}", use_container_width=True):
                    if escolha == "— selecione —":
                        st.warning("Selecione um colaborador antes de confirmar.")
                    else:
                        nome_colab_norm = df_colab.loc[df_colab["nome"] == escolha, "nome_normalizado"].iloc[0]
                        salvar_override(nome_norm, linha["nome_colaborador_planilha"], "RELACIONADO", nome_colab_norm, escolha, login_atual)
                        aplicar_override_em_csv(nome_norm, ms.RELACIONADO_MANUAL, escolha)
                        registrar(login_atual, "REVISAO_MANUAL_CONFIRMADA", f"{linha['nome_colaborador_planilha']} -> {escolha}")
                        st.success("Relacionamento salvo e já aplicado aos treinamentos existentes.")
                        st.rerun()
                if col_b2.button("Não é da base", key=f"btn_nao_{nome_norm}", use_container_width=True):
                    salvar_override(nome_norm, linha["nome_colaborador_planilha"], "NAO_ENCONTRADO_CONFIRMADO", None, None, login_atual)
                    aplicar_override_em_csv(nome_norm, ms.NAO_ENCONTRADO_CONFIRMADO, None)
                    registrar(login_atual, "REVISAO_MANUAL_CONFIRMADA", f"{linha['nome_colaborador_planilha']} -> NAO_ENCONTRADO_CONFIRMADO")
                    st.success("Marcado como 'não é ninguém da base'.")
                    st.rerun()
