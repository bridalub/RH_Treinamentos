"""Importação e consultas sobre treinamentos.csv, gerado a partir da aba oficial DTB Bridalub - Por Usuário (2)."""
import hashlib

import pandas as pd

from utils.csv_io import ler_csv, salvar_csv
from utils.excel_import import ler_planilha_treinamentos
from utils.formatacao import agora_br
from utils.normalizacao import normalizar_nome
from services import matching_service as ms
from services.colaboradores_service import nomes_normalizados_validos

COLUNAS = [
    "treinamento_id", "nome_colaborador_planilha", "nome_normalizado", "cpf",
    "titulo_treinamento", "status", "data_inscricao", "data_conclusao",
    "dtb_lider", "dtb_area", "dtb_lob", "dtb_cargo", "dtb_data_desligamento",
    "data_contratacao", "ultimo_acesso", "tipo_treino",
    "situacao_relacionamento", "nome_colaborador_relacionado",
    "importado_em",
]

STATUS_CONCLUIDOS = {"Completo", "Concluído (Equivalente)"}
STATUS_PENDENTES = {"Em Andamento", "Em Andamento/Vencido", "Não Iniciada", "Registrado", "Avaliação Pendente"}


def _gerar_id(nome_planilha: str, titulo: str) -> str:
    chave = f"{nome_planilha.strip().upper()}|{titulo.strip().upper()}"
    return "TRE" + hashlib.md5(chave.encode("utf-8")).hexdigest()[:12].upper()


def _mapa_nomes_exibicao(df_colaboradores: pd.DataFrame) -> dict:
    validos = df_colaboradores[df_colaboradores["is_pessoa_valida"] == "True"]
    mapa = {}
    for _, linha in validos.iterrows():
        mapa.setdefault(linha["nome_normalizado"], linha["nome"])
    return mapa


def importar_treinamentos(caminho_arquivo, df_colaboradores: pd.DataFrame, df_overrides: pd.DataFrame | None = None):
    """Lê a planilha oficial, relaciona com colaboradores e monta o treinamentos.csv.

    Retorna (df_treinamentos, resumo) onde resumo traz contagens para a tela
    de Atualização (novos, atualizados, relacionados, pendentes de revisão,
    não encontrados) e os metadados do relatório original (inclui alerta de
    export parcial quando aplicável).
    """
    df_bruto, metadados = ler_planilha_treinamentos(caminho_arquivo)

    df_bruto = df_bruto.copy()
    df_bruto["nome_normalizado"] = df_bruto["nome_colaborador_planilha"].map(normalizar_nome)

    candidatos = nomes_normalizados_validos(df_colaboradores)
    nomes_unicos = sorted(set(n for n in df_bruto["nome_normalizado"] if n))
    resultados = ms.relacionar_lote(nomes_unicos, candidatos)
    resultados = ms.aplicar_overrides(resultados, df_overrides)

    mapa_exibicao = _mapa_nomes_exibicao(df_colaboradores)
    agora = agora_br().strftime("%Y-%m-%d %H:%M:%S")

    linhas = []
    for _, linha in df_bruto.iterrows():
        resultado = resultados.get(linha["nome_normalizado"], ms.ResultadoMatch(ms.NAO_ENCONTRADO, None, [], None))
        nome_relacionado = mapa_exibicao.get(resultado.nome_colaborador_normalizado, "")
        linhas.append({
            "treinamento_id": _gerar_id(str(linha["nome_colaborador_planilha"]), str(linha["titulo_treinamento"])),
            "nome_colaborador_planilha": linha["nome_colaborador_planilha"],
            "nome_normalizado": linha["nome_normalizado"],
            "cpf": str(linha.get("cpf", "")).strip(),
            "titulo_treinamento": linha["titulo_treinamento"],
            "status": linha["status"],
            "data_inscricao": linha.get("data_inscricao", ""),
            "data_conclusao": linha.get("data_conclusao", ""),
            "dtb_lider": linha.get("dtb_lider", ""),
            "dtb_area": linha.get("dtb_area", ""),
            "dtb_lob": linha.get("dtb_lob", ""),
            "dtb_cargo": linha.get("dtb_cargo", ""),
            "dtb_data_desligamento": linha.get("dtb_data_desligamento", ""),
            "data_contratacao": linha.get("data_contratacao", ""),
            "ultimo_acesso": linha.get("ultimo_acesso", ""),
            "tipo_treino": linha.get("tipo_treino", ""),
            "situacao_relacionamento": resultado.situacao,
            "nome_colaborador_relacionado": nome_relacionado,
            "importado_em": agora,
        })

    df_novo = pd.DataFrame(linhas, columns=COLUNAS)
    for coluna in ["data_inscricao", "data_conclusao", "dtb_data_desligamento", "data_contratacao", "ultimo_acesso"]:
        df_novo[coluna] = df_novo[coluna].astype(str).replace({"NaT": "", "nan": ""})

    resumo = _comparar_com_existente(df_novo)
    resumo["metadados_relatorio"] = metadados
    resumo["relacionados_automatico"] = int((df_novo["situacao_relacionamento"].isin([ms.RELACIONADO_AUTOMATICO, ms.RELACIONADO_MANUAL])).sum())
    resumo["revisao_manual"] = int((df_novo["situacao_relacionamento"] == ms.REVISAO_MANUAL).sum())
    resumo["nao_encontrado"] = int((df_novo["situacao_relacionamento"] == ms.NAO_ENCONTRADO).sum())
    resumo["total_linhas"] = len(df_novo)

    return df_novo, resumo


def _comparar_com_existente(df_novo: pd.DataFrame) -> dict:
    df_antigo = ler_csv("treinamentos", COLUNAS)
    if df_antigo.empty:
        return {"novos": len(df_novo), "atualizados": 0, "inalterados": 0}

    antigo_idx = df_antigo.set_index("treinamento_id")
    colunas_comparaveis = ["status", "data_inscricao", "data_conclusao", "ultimo_acesso"]

    novos = atualizados = inalterados = 0
    for _, linha in df_novo.iterrows():
        tid = linha["treinamento_id"]
        if tid not in antigo_idx.index:
            novos += 1
            continue
        antiga = antigo_idx.loc[tid]
        mudou = any(str(antiga.get(c, "")) != str(linha.get(c, "")) for c in colunas_comparaveis)
        if mudou:
            atualizados += 1
        else:
            inalterados += 1

    return {"novos": novos, "atualizados": atualizados, "inalterados": inalterados}


def salvar_treinamentos(df: pd.DataFrame):
    return salvar_csv("treinamentos", df)


def carregar_treinamentos() -> pd.DataFrame:
    return ler_csv("treinamentos", COLUNAS)


def ultima_atualizacao() -> str:
    """Data/hora (formato brasileiro) da última importação de treinamentos
    salva com sucesso — manual ou via automação, ambas gravam 'importado_em'
    pelo mesmo caminho (importar_treinamentos -> salvar_treinamentos)."""
    df = carregar_treinamentos()
    if df.empty:
        return ""
    datas = pd.to_datetime(df["importado_em"], errors="coerce")
    maximo = datas.max()
    if pd.isna(maximo):
        return ""
    return maximo.strftime("%d/%m/%Y %H:%M")


def pendentes_revisao(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["situacao_relacionamento"].isin([ms.REVISAO_MANUAL, ms.NAO_ENCONTRADO])]


def aplicar_override_em_csv(nome_normalizado: str, situacao: str, nome_colaborador_exibicao: str | None) -> int:
    """Atualiza imediatamente o treinamentos.csv já salvo com uma decisão manual do RH,
    sem esperar a próxima importação. Retorna quantas linhas foram atualizadas."""
    df = carregar_treinamentos()
    if df.empty:
        return 0
    mascara = df["nome_normalizado"] == nome_normalizado
    if not mascara.any():
        return 0
    df.loc[mascara, "situacao_relacionamento"] = situacao
    df.loc[mascara, "nome_colaborador_relacionado"] = nome_colaborador_exibicao or ""
    salvar_treinamentos(df)
    return int(mascara.sum())


def montar_listview(df_treinos: pd.DataFrame, df_colaboradores: pd.DataFrame) -> pd.DataFrame:
    """Junta treinamentos com os dados organizacionais do colaborador relacionado
    (cargo e gestor vêm da base de funcionários; área vem da própria plataforma,
    que é a única fonte que a possui)."""
    validos = df_colaboradores[df_colaboradores["is_pessoa_valida"] == "True"]
    org = validos.drop_duplicates("nome_normalizado")[["nome_normalizado", "cargo", "gestor_nome"]]
    org = org.rename(columns={"nome_normalizado": "_nome_norm_join", "cargo": "cargo_colaborador"})

    # mapa nome -> nome_normalizado vetorizado (mesmo resultado do antigo
    # df_colaboradores.loc[...].iloc[0] por linha, porém O(n) em vez de O(n*m):
    # mantém o primeiro nome_normalizado encontrado para cada "nome" repetido,
    # exatamente como .iloc[0] fazia ao varrer df_colaboradores na ordem original.
    mapa_nome_para_norm = df_colaboradores.drop_duplicates("nome", keep="first").set_index("nome")["nome_normalizado"]

    df = df_treinos.copy()
    df["_nome_norm_join"] = df["nome_colaborador_relacionado"].map(mapa_nome_para_norm).fillna("")
    df = df.merge(org, on="_nome_norm_join", how="left").drop(columns=["_nome_norm_join"])

    return df[[
        "nome_colaborador_planilha", "nome_colaborador_relacionado", "titulo_treinamento",
        "status", "data_inscricao", "data_conclusao", "ultimo_acesso",
        "cargo_colaborador", "dtb_area", "gestor_nome", "situacao_relacionamento",
    ]].rename(columns={
        "nome_colaborador_planilha": "Nome na Plataforma",
        "nome_colaborador_relacionado": "Nome Relacionado",
        "titulo_treinamento": "Treinamento",
        "status": "Status",
        "data_inscricao": "Data de Inscrição",
        "data_conclusao": "Data de Conclusão",
        "ultimo_acesso": "Último Acesso",
        "cargo_colaborador": "Cargo",
        "dtb_area": "Área",
        "gestor_nome": "Gestor",
        "situacao_relacionamento": "Situação do Relacionamento",
    })
