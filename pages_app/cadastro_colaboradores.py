"""Cadastro de Colaboradores: gestores e administradores usam a base OFICIAL
da PLATAFORMA DE TREINAMENTOS (não a planilha de funcionários) para conferir
se um colaborador existe, e cadastrar/corrigir/excluir o registro dele em
colaboradores.csv com o nome exatamente igual ao da plataforma — é assim que
as duas bases se conectam (o relacionamento é sempre feito só pelo nome)."""
import pandas as pd
import streamlit as st

from services.colaboradores_service import carregar_colaboradores, salvar_colaboradores, criar_ou_atualizar_colaborador
from services.colaboradores_ajustes_service import salvar_ajuste, remover_ajuste
from services.treinamentos_service import carregar_treinamentos, salvar_treinamentos, aplicar_override_em_csv
from services.revisoes_service import salvar_override
from services.logs_service import registrar
from services import matching_service as ms
from utils.auth import usuario_atual
from utils.normalizacao import normalizar_nome

_CHAVE_EDITANDO = "cadastro_colab_editando_id"
_CHAVE_SUGESTAO = "cadastro_colab_sugestao"
_CHAVE_MOSTRAR_NOVO = "cadastro_colab_mostrar_novo"

_ROTULO_SITUACAO = {
    "RELACIONADO_AUTOMATICO": "✅ Relacionado",
    "RELACIONADO_MANUAL": "✅ Relacionado (manual)",
    "NAO_ENCONTRADO": "❌ Não encontrado na base de funcionários",
    "REVISAO_MANUAL": "⚠️ Revisão manual pendente",
}


def _pessoas_da_plataforma(df_treino: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por pessoa única na plataforma (não por treinamento) — essa é
    a base "oficial" que colaboradores.csv precisa acompanhar em nome."""
    colunas = ["nome_colaborador_planilha", "nome_normalizado", "nome_colaborador_relacionado", "situacao_relacionamento", "cpf", "dtb_area", "dtb_cargo"]
    return (
        df_treino[colunas]
        .drop_duplicates("nome_colaborador_planilha")
        .sort_values("nome_colaborador_planilha")
        .reset_index(drop=True)
    )


def _limpar_selecao_pendente():
    st.session_state.pop(_CHAVE_EDITANDO, None)
    st.session_state.pop(_CHAVE_SUGESTAO, None)
    st.session_state[_CHAVE_MOSTRAR_NOVO] = False


def render():
    st.markdown("## Cadastro de Colaboradores")
    st.caption(
        "Os nomes abaixo vêm direto da **plataforma de treinamentos** (não da planilha de "
        "funcionários) — é a base que precisa ser conferida. Cadastre, corrija ou exclua um "
        "colaborador na base de funcionários usando o nome exatamente igual ao da plataforma."
    )

    usuario = usuario_atual() or {}
    perfil = usuario.get("perfil")
    eh_gestor = perfil == "GESTOR"
    eh_admin_rh = perfil in ("ADMIN", "RH")
    meu_nome = usuario.get("nome", "")
    meu_nome_norm = normalizar_nome(meu_nome)

    df_colab = carregar_colaboradores()
    df_treino = carregar_treinamentos()
    if df_treino.empty:
        st.info("Nenhum treinamento importado ainda. Vá em **Atualização**.")
        return

    df_plataforma = _pessoas_da_plataforma(df_treino)

    # gestor de cada colaborador já cadastrado, pra filtrar a visão do GESTOR
    # e pra alimentar o combobox de gestor (só nomes que já são gestor de alguém)
    mapa_gestor = df_colab.drop_duplicates("nome").set_index("nome")["gestor_nome"].to_dict()
    gestores_disponiveis = set(g for g in df_colab["gestor_nome"].tolist() if g)
    if eh_gestor and meu_nome:
        # gestor novo, ainda sem ninguém sob ele, precisa poder se selecionar
        # mesmo não aparecendo ainda como gestor_nome de nenhum colaborador
        gestores_disponiveis.add(meu_nome)
    gestores_disponiveis = sorted(gestores_disponiveis)

    if eh_gestor:
        def _da_minha_equipe(relacionado: str) -> bool:
            if not relacionado:
                # sem vínculo ainda: mostra pra qualquer gestor poder identificar
                # (mesma lista já visível em Análises, pergunta 7 — nada novo exposto)
                return True
            return normalizar_nome(mapa_gestor.get(relacionado, "")) == meu_nome_norm
        df_plataforma = df_plataforma[df_plataforma["nome_colaborador_relacionado"].map(_da_minha_equipe)]

    # --------------------------------------------------------------- cadastro
    editando_id = st.session_state.get(_CHAVE_EDITANDO)
    linha_edicao = None
    if editando_id:
        correspondentes = df_colab[df_colab["colaborador_id"] == editando_id]
        if not correspondentes.empty:
            linha_edicao = correspondentes.iloc[0]
        else:
            st.session_state.pop(_CHAVE_EDITANDO, None)

    if eh_gestor and linha_edicao is not None and normalizar_nome(linha_edicao["gestor_nome"]) != meu_nome_norm:
        st.warning("Esse colaborador não é da sua equipe — a edição foi cancelada.")
        st.session_state.pop(_CHAVE_EDITANDO, None)
        linha_edicao = None

    # leitura NÃO destrutiva: precisa continuar visível nos próximos reruns
    # enquanto a mesma linha da tabela seguir selecionada (senão o trecho lá
    # embaixo, que só reage quando a sugestão MUDA, nunca vê "sem mudança" e
    # fica chamando st.rerun() pra sempre — a tela "pisca" sem parar).
    sugestao = st.session_state.get(_CHAVE_SUGESTAO) if linha_edicao is None else None
    login_atual = usuario.get("login", "sistema")

    # o formulário fica oculto por padrão — só abre quando há algo pra editar
    # (linha_edicao/sugestao vindos de um clique na tabela) ou quando o
    # usuário pede explicitamente "Novo colaborador".
    mostra_form = linha_edicao is not None or bool(sugestao) or st.session_state.get(_CHAVE_MOSTRAR_NOVO, False)

    if not mostra_form:
        if st.button("➕ Novo colaborador", type="primary"):
            st.session_state[_CHAVE_MOSTRAR_NOVO] = True
            st.rerun()
    else:
        titulo_form = f"✏️ Editando: {linha_edicao['nome']}" if linha_edicao is not None else "➕ Novo colaborador"
        st.markdown(f"#### {titulo_form}")
        if sugestao:
            st.caption("Nome e CPF pré-preenchidos com o que está na plataforma de treinamentos — confira antes de cadastrar.")

        # Gestor fica FORA do form: precisa disparar um rerun sozinho ao trocar de
        # valor pra poder sugerir Equipe/Horário do gestor escolhido (widgets
        # dentro de st.form só "avisam" o resto do app quando o form é enviado).
        #
        # Combobox liberado pra GESTOR também (não só ADMIN/RH): o objetivo desta
        # tela é justamente permitir direcionar alguém que não é da própria
        # equipe para o gestor certo — travar em "meu_nome" impedia isso.
        valor_gestor_atual = linha_edicao["gestor_nome"] if linha_edicao is not None else (meu_nome if eh_gestor and sugestao else "")
        indice_gestor = gestores_disponiveis.index(valor_gestor_atual) if valor_gestor_atual in gestores_disponiveis else None
        # chave amarrada a quem está sendo editado: ao trocar de colaborador
        # (ou ir pra "novo"), o combobox precisa "esquecer" a seleção antiga
        # e voltar a respeitar o valor atual do registro carregado.
        gestor_nome = st.selectbox(
            "Gestor", gestores_disponiveis, index=indice_gestor, placeholder="Selecione um gestor...",
            key=f"cadastro_colab_gestor_{editando_id or 'novo'}",
        ) or ""

        sugestao_equipe, sugestao_horario = "", ""
        if gestor_nome:
            linha_gestor = df_colab[df_colab["nome"] == gestor_nome]
            if not linha_gestor.empty:
                sugestao_equipe = linha_gestor.iloc[0]["equipe_id"]
                sugestao_horario = linha_gestor.iloc[0]["horario_trabalho"]

        with st.form("form_cadastro_colab"):
            col1, col2 = st.columns(2)
            with col1:
                valor_nome = linha_edicao["nome"] if linha_edicao is not None else (sugestao["nome"] if sugestao else "")
                nome = st.text_input("Nome completo *", value=valor_nome)
                valor_cpf = linha_edicao["cpf"] if linha_edicao is not None else (sugestao["cpf"] if sugestao else "")
                cpf = st.text_input("CPF (opcional)", value=valor_cpf)
                cargo = st.text_input("Cargo", value=linha_edicao["cargo"] if linha_edicao is not None else "")
                valor_equipe = linha_edicao["equipe_id"] if linha_edicao is not None else sugestao_equipe
                equipe_id = st.text_input("Equipe (nº)", value=valor_equipe)
            with col2:
                email = st.text_input("E-mail", value=linha_edicao["email"] if linha_edicao is not None else "")
                celular = st.text_input("Celular", value=linha_edicao["celular"] if linha_edicao is not None else "")
                valor_horario = linha_edicao["horario_trabalho"] if linha_edicao is not None else sugestao_horario
                horario = st.text_input("Horário de trabalho", value=valor_horario)
                st.caption(f"Gestor selecionado: **{gestor_nome or '— nenhum —'}** (escolhido acima)")

            col_salvar, col_cancelar = st.columns(2)
            rotulo_salvar = "💾 Salvar alterações" if linha_edicao is not None else "💾 Cadastrar colaborador"
            salvar = col_salvar.form_submit_button(rotulo_salvar, type="primary")
            cancelar = col_cancelar.form_submit_button("Cancelar")

        # exclusão fica FORA do form: um checkbox dentro de st.form não dispara
        # rerun sozinho, então o botão nunca refletiria a marcação ao vivo — só
        # no próximo submit, tarde demais para habilitar/desabilitar corretamente.
        excluir = False
        if linha_edicao is not None:
            confirmar_exclusao = st.checkbox(
                "Confirmo que quero excluir este colaborador permanentemente",
                key="cadastro_colab_confirma_exclusao",
            )
            excluir = st.button("🗑️ Excluir colaborador", disabled=not confirmar_exclusao)

        if cancelar:
            _limpar_selecao_pendente()
            st.rerun()

        if excluir and linha_edicao is not None:
            df_sem = df_colab[df_colab["colaborador_id"] != linha_edicao["colaborador_id"]]
            salvar_colaboradores(df_sem)
            # persiste a exclusão: sem isso, a próxima importação da BASE
            # FUNCIONÁRIOS recria essa linha do zero (o import gera
            # colaborador_id novos sempre a partir da planilha crua).
            chave_ajuste = f"{linha_edicao['nome_normalizado']}|{linha_edicao['equipe_id']}"
            salvar_ajuste(chave_ajuste, "EXCLUIDO", login_atual)
            remover_ajuste(normalizar_nome(linha_edicao["nome"]))  # limpa um eventual "CRIADO" anterior — senão ele a recriaria
            registrar(login_atual, "EXCLUIR_COLABORADOR", f"{linha_edicao['nome']} (id={linha_edicao['colaborador_id']})")
            st.success(f"Colaborador '{linha_edicao['nome']}' excluído — a exclusão persiste mesmo em futuras importações da planilha.")
            _limpar_selecao_pendente()
            st.rerun()

        if salvar:
            if not nome.strip():
                st.warning("Informe o nome do colaborador.")
            else:
                nome_antigo = linha_edicao["nome"] if linha_edicao is not None else None
                df_novo, novo_id = criar_ou_atualizar_colaborador(
                    df_colab,
                    colaborador_id=linha_edicao["colaborador_id"] if linha_edicao is not None else None,
                    nome=nome, cpf=cpf, cargo=cargo, equipe_id=equipe_id,
                    email=email, celular=celular, horario_trabalho=horario,
                    gestor_nome=gestor_nome,
                )
                salvar_colaboradores(df_novo)
                acao = "ATUALIZAR_COLABORADOR" if linha_edicao is not None else "CRIAR_COLABORADOR"
                registrar(login_atual, acao, f"{nome} (id={novo_id})")

                # persiste a edição/criação: sem isso, a próxima importação da
                # BASE FUNCIONÁRIOS sobrescreve tudo do zero a partir da
                # planilha crua e desfaz a correção da RH (mesmo mecanismo da
                # Revisão de Correspondências, agora pro cadastro em si).
                valores_ajuste = dict(
                    nome=nome, cpf=cpf, cargo=cargo, equipe_id=equipe_id,
                    email=email, celular=celular, horario_trabalho=horario, gestor_nome=gestor_nome,
                )
                if linha_edicao is not None:
                    chave_ajuste = f"{linha_edicao['nome_normalizado']}|{linha_edicao['equipe_id']}"
                    salvar_ajuste(chave_ajuste, "EDITADO", login_atual, **valores_ajuste)
                else:
                    salvar_ajuste(normalizar_nome(nome), "CRIADO", login_atual, **valores_ajuste)

                # fecha o loop com a plataforma imediatamente, sem esperar a próxima
                # importação: (1) cadastro novo a partir de um "não encontrado" já
                # nasce vinculado; (2) corrigir o nome de alguém já vinculado
                # propaga a nova grafia pros treinamentos dele, sem deixar o
                # vínculo antigo orfão.
                if sugestao:
                    aplicar_override_em_csv(sugestao["nome_planilha_normalizado"], ms.RELACIONADO_MANUAL, nome)
                    salvar_override(
                        sugestao["nome_planilha_normalizado"], sugestao["nome"], "RELACIONADO",
                        normalizar_nome(nome), nome, login_atual,
                    )
                elif nome_antigo and nome_antigo != nome:
                    df_treino_atual = carregar_treinamentos()
                    mascara_antigo = df_treino_atual["nome_colaborador_relacionado"] == nome_antigo
                    if mascara_antigo.any():
                        df_treino_atual.loc[mascara_antigo, "nome_colaborador_relacionado"] = nome
                        salvar_treinamentos(df_treino_atual)

                st.success(f"Colaborador '{nome}' salvo com sucesso — já reflete na base de funcionários e na plataforma.")
                _limpar_selecao_pendente()
                st.rerun()

    # ------------------------------------------------------- trocar gestor
    if eh_admin_rh and len(gestores_disponiveis) >= 1:
        with st.expander("🔁 Trocar gestor de uma equipe inteira (o gestor saiu / foi substituído)"):
            st.caption(
                "Move TODOS os colaboradores do gestor atual para o novo gestor de uma vez. "
                "Cadastre o novo gestor primeiro (acima) se ele ainda não estiver na base."
            )
            nomes_colaboradores = sorted(df_colab["nome"].unique().tolist())
            col_de, col_para = st.columns(2)
            gestor_saindo = col_de.selectbox("Gestor atual (saindo)", [""] + gestores_disponiveis, key="cadastro_colab_troca_de")
            gestor_entrando = col_para.selectbox("Novo gestor (assume a equipe)", [""] + nomes_colaboradores, key="cadastro_colab_troca_para")

            qtd_equipe = int((df_colab["gestor_nome"] == gestor_saindo).sum()) if gestor_saindo else 0
            if gestor_saindo:
                st.caption(f"{qtd_equipe} colaborador(es) atualmente sob {gestor_saindo}.")

            confirmar_troca = st.checkbox("Confirmo a troca de gestor para toda a equipe", key="cadastro_colab_troca_confirma")
            trocar = st.button(
                "🔁 Trocar gestor",
                disabled=not (gestor_saindo and gestor_entrando and gestor_saindo != gestor_entrando and confirmar_troca and qtd_equipe > 0),
            )
            if trocar:
                df_colab_atual = carregar_colaboradores()
                mascara_equipe = df_colab_atual["gestor_nome"] == gestor_saindo
                afetados = df_colab_atual[mascara_equipe].copy()
                df_colab_atual.loc[mascara_equipe, "gestor_nome"] = gestor_entrando
                salvar_colaboradores(df_colab_atual)
                # persiste a troca linha a linha, senão some na próxima
                # reimportação da BASE FUNCIONÁRIOS (mesmo motivo de qualquer
                # edição individual via Cadastro).
                for _, linha in afetados.iterrows():
                    chave_ajuste = f"{linha['nome_normalizado']}|{linha['equipe_id']}"
                    salvar_ajuste(
                        chave_ajuste, "EDITADO", login_atual,
                        nome=linha["nome"], cpf=linha["cpf"], cargo=linha["cargo"], equipe_id=linha["equipe_id"],
                        email=linha["email"], celular=linha["celular"], horario_trabalho=linha["horario_trabalho"],
                        gestor_nome=gestor_entrando,
                    )
                registrar(
                    login_atual, "TROCAR_GESTOR",
                    f"{gestor_saindo} -> {gestor_entrando} ({qtd_equipe} colaborador(es))",
                )
                st.success(f"{qtd_equipe} colaborador(es) movido(s) de {gestor_saindo} para {gestor_entrando} — a troca persiste em futuras importações.")
                st.rerun()

    st.divider()

    # --------------------------------------------------------------- pesquisa
    st.markdown("#### Pesquisar na plataforma de treinamentos")
    termo = st.text_input(
        "Buscar por nome", key="cadastro_colab_busca",
        placeholder="Digite para filtrar...", label_visibility="collapsed",
    )

    if termo.strip():
        termo_norm = normalizar_nome(termo)
        df_lista = df_plataforma[df_plataforma["nome_colaborador_planilha"].map(normalizar_nome).str.contains(termo_norm, na=False)]
    else:
        df_lista = df_plataforma

    # --------------------------------------------------------------- listview
    st.markdown(f"#### Pessoas na plataforma ({len(df_lista)})")
    if df_lista.empty:
        st.caption("Nenhum nome encontrado na plataforma de treinamentos.")
        return

    st.caption("Clique numa linha para cadastrar (se não encontrada) ou corrigir (se já relacionada) esse nome na base de funcionários.")
    tabela = df_lista.copy()
    tabela["Situação"] = tabela["situacao_relacionamento"].map(_ROTULO_SITUACAO).fillna(tabela["situacao_relacionamento"])
    tabela_exibicao = tabela[[
        "nome_colaborador_planilha", "Situação", "nome_colaborador_relacionado", "cpf", "dtb_area", "dtb_cargo",
    ]].rename(columns={
        "nome_colaborador_planilha": "Nome na Plataforma",
        "nome_colaborador_relacionado": "Colaborador Vinculado",
        "cpf": "CPF", "dtb_area": "Área", "dtb_cargo": "Cargo (plataforma)",
    }).reset_index(drop=True)

    evento = st.dataframe(
        tabela_exibicao, hide_index=True, use_container_width=True,
        on_select="rerun", selection_mode="single-row", key="cadastro_colab_tabela",
    )
    linhas_selecionadas = evento.selection["rows"] if evento and evento.selection else []
    if not linhas_selecionadas:
        return

    linha_sel = df_lista.iloc[linhas_selecionadas[0]]
    nome_relacionado = linha_sel["nome_colaborador_relacionado"]

    if nome_relacionado:
        correspondentes = df_colab[df_colab["nome"] == nome_relacionado]
        if not correspondentes.empty:
            id_alvo = correspondentes.iloc[0]["colaborador_id"]
            if id_alvo != st.session_state.get(_CHAVE_EDITANDO):
                st.session_state[_CHAVE_EDITANDO] = id_alvo
                st.session_state.pop(_CHAVE_SUGESTAO, None)
                st.rerun()
    else:
        sugestao_atual = st.session_state.get(_CHAVE_SUGESTAO)
        nome_ja_sugerido = sugestao_atual["nome"] if sugestao_atual else None
        if nome_ja_sugerido != linha_sel["nome_colaborador_planilha"]:
            st.session_state.pop(_CHAVE_EDITANDO, None)
            st.session_state[_CHAVE_SUGESTAO] = {
                "nome": linha_sel["nome_colaborador_planilha"],
                "cpf": linha_sel["cpf"],
                "nome_planilha_normalizado": linha_sel["nome_normalizado"],
            }
            st.rerun()


# objeto de página compartilhado: criado aqui (não em app.py) pra outras
# páginas poderem chamar st.switch_page(PAGINA) diretamente — st.switch_page
# com string só aceita arquivos de verdade em pages/, e este projeto usa
# st.Page com função, registrado manualmente em app.py.
PAGINA = st.Page(render, title="Cadastro", icon="🪪", url_path="cadastro-colaboradores")
