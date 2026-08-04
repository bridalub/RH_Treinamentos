"""Importação e consultas sobre colaboradores.csv, gerado a partir de BASE FUNCIONÁRIOS BRIDA."""
from datetime import datetime

import pandas as pd

from utils.csv_io import ler_csv, salvar_csv
from utils.excel_import import ler_planilha_colaboradores
from utils.normalizacao import normalizar_nome, normalizar_texto, esta_vazio
from services.colaboradores_ajustes_service import carregar_ajustes

COLUNAS = [
    "colaborador_id", "nome", "nome_normalizado", "cpf", "equipe_id", "cargo",
    "email", "celular", "horario_trabalho", "gestor_nome", "is_pessoa_valida",
    "atualizado_em",
]

_RANK_CARGO_LIDERANCA = {"GERENTE": 0, "COORDENADOR": 1}

# Duas células da planilha de origem juntam o nome de DUAS pessoas num único
# campo COLABORADOR (defeito conhecido da BASE FUNCIONÁRIOS, documentado no
# relatório técnico). Como o separador não é padronizado em toda a planilha
# (" - " também aparece como sufixo de "REALOCADO", que não é um segundo
# nome), não dá para dividir por um padrão genérico sem risco de quebrar
# outros nomes — por isso a lista abaixo é curada, só para os casos já
# identificados manualmente, e cada pessoa resultante herda a mesma
# equipe/cargo/e-mail/celular da linha original (é a mesma função/contato
# compartilhado entre as duas).
_NOMES_COMBINADOS_CONHECIDOS = {
    "GABRIELLE ROCHA - JAIANE DOS SANTOS": ["GABRIELLE ROCHA", "JAIANE DOS SANTOS"],
    "RAFAEL PEDRESCHI E JORGE IAMAMURA": ["RAFAEL PEDRESCHI", "JORGE IAMAMURA"],
}


def _rank(cargo: str) -> int:
    return _RANK_CARGO_LIDERANCA.get(cargo, 99)


def invalidar_realocados_superados(df: pd.DataFrame) -> pd.DataFrame:
    """Quando a planilha de origem traz duas linhas pro mesmo nome_normalizado
    (mesma pessoa) — uma sem sufixo, da equipe antiga, e outra com
    "- REALOCADO"/"- REALOCADA", da equipe atual — a linha antiga não é
    removida da BASE FUNCIONÁRIOS pela RH, e sobra como membro "ativo" da
    equipe velha. Como o relacionamento com a plataforma de treinamentos usa
    nome_normalizado (as duas linhas empatam), só um dos dois nomes acumula
    os treinamentos de verdade — a pessoa aparece com os dados certos numa
    tela e zerada/na equipe errada em outra. Aqui a linha sem sufixo é
    marcada inválida (mesmo mecanismo já usado pra cabeçalho de subdivisão),
    então ela some das equipes/listas ativas mas nada é apagado — reaplicado
    a cada importação para o problema não voltar em outros nomes."""
    if df.empty:
        return df
    tem_sufixo = df["nome"].str.contains(r"\bREALOCAD[OA]\b", case=False, regex=True, na=False)
    normalizados_atuais = set(df.loc[tem_sufixo, "nome_normalizado"])
    mascara_superada = (~tem_sufixo) & df["nome_normalizado"].isin(normalizados_atuais) & (df["is_pessoa_valida"] == "True")
    df.loc[mascara_superada, "is_pessoa_valida"] = "False"
    return df


def aplicar_ajustes(df: pd.DataFrame, df_ajustes: pd.DataFrame) -> pd.DataFrame:
    """Reaplica por cima do resultado fresco da importação as edições/exclusões/
    criações manuais feitas em Cadastro de Colaboradores ou em Equipes — sem
    isso, reimportar a BASE FUNCIONÁRIOS desfaria qualquer correção da RH
    (o import gera colaborador_id novos do zero a cada vez). A chave usada
    para casar um ajuste com a linha recém-importada correspondente é
    nome_normalizado + equipe_id (a mesma pessoa pode ter mais de uma linha,
    uma por equipe, quando é suporte compartilhado — por isso a equipe entra
    na chave)."""
    if df_ajustes is None or df_ajustes.empty:
        return df

    df = df.copy()
    df["_chave"] = df["nome_normalizado"] + "|" + df["equipe_id"].astype(str)

    excluidos = df_ajustes[df_ajustes["tipo"] == "EXCLUIDO"]
    if not excluidos.empty:
        mascara = df["_chave"].isin(set(excluidos["chave"]))
        df.loc[mascara, "is_pessoa_valida"] = "False"

    # CRIADO precisa entrar ANTES de EDITADO: uma pessoa cadastrada do zero
    # (sem equivalente na planilha) só existe no df por causa do próprio
    # ajuste CRIADO — se ela também foi editada depois, o ajuste EDITADO
    # correspondente só encontra a linha pra corrigir se o CRIADO já tiver
    # sido aplicado antes.
    criados = df_ajustes[df_ajustes["tipo"] == "CRIADO"]
    if not criados.empty:
        nomes_existentes = set(df["nome_normalizado"])
        numero = int(proximo_colaborador_id(df).replace("COL", ""))
        novas_linhas = []
        for _, ajuste in criados.iterrows():
            nome_norm = normalizar_nome(ajuste["nome"])
            if nome_norm in nomes_existentes:
                continue  # já veio fresco da planilha desta vez — não duplica
            nomes_existentes.add(nome_norm)
            novas_linhas.append({
                "colaborador_id": f"COL{numero:04d}",
                "nome": ajuste["nome"], "nome_normalizado": nome_norm, "cpf": ajuste["cpf"],
                "equipe_id": ajuste["equipe_id"], "cargo": ajuste["cargo"],
                "email": ajuste["email"], "celular": ajuste["celular"],
                "horario_trabalho": ajuste["horario_trabalho"], "gestor_nome": ajuste["gestor_nome"],
                "is_pessoa_valida": "True", "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "_chave": f"{nome_norm}|{ajuste['equipe_id']}",
            })
            numero += 1
        if novas_linhas:
            df = pd.concat([df, pd.DataFrame(novas_linhas, columns=list(COLUNAS) + ["_chave"])], ignore_index=True)

    campos_editaveis = ["nome", "cpf", "cargo", "equipe_id", "email", "celular", "horario_trabalho", "gestor_nome"]
    editados = df_ajustes[df_ajustes["tipo"] == "EDITADO"]
    for _, ajuste in editados.iterrows():
        mascara = df["_chave"] == ajuste["chave"]
        if mascara.any():
            for campo in campos_editaveis:
                df.loc[mascara, campo] = ajuste[campo]
            df.loc[mascara, "nome_normalizado"] = normalizar_nome(ajuste["nome"])
            df.loc[mascara, "is_pessoa_valida"] = "True"

    return df.drop(columns=["_chave"])


def importar_colaboradores(caminho_arquivo) -> pd.DataFrame:
    """Lê a planilha BASE FUNCIONÁRIOS BRIDA e monta o colaboradores.csv.

    Preserva uma linha por atribuição de equipe (uma mesma pessoa de suporte
    compartilhada entre várias equipes gera uma linha por equipe, como na
    planilha de origem). Linhas de cabeçalho de subdivisão (sem cargo) são
    mantidas mas marcadas como is_pessoa_valida=False. Células que juntam duas
    pessoas num nome só (ver _NOMES_COMBINADOS_CONHECIDOS) viram duas linhas.
    """
    df_raw = ler_planilha_colaboradores(caminho_arquivo)

    registros = []
    proximo_id = 1
    for _, linha in df_raw.iterrows():
        nome_bruto = normalizar_texto(linha.get("COLABORADOR"))
        nomes = _NOMES_COMBINADOS_CONHECIDOS.get(nome_bruto, [nome_bruto])
        cargo = normalizar_texto(linha.get("CARGO")).upper()
        equipe_valor = linha.get("EQUIPE")
        equipe_id = "" if pd.isna(equipe_valor) else str(int(equipe_valor))
        for nome in nomes:
            registros.append({
                "colaborador_id": f"COL{proximo_id:04d}",
                "nome": nome,
                "nome_normalizado": normalizar_nome(nome),
                "cpf": "",
                "equipe_id": equipe_id,
                "cargo": cargo,
                "email": normalizar_texto(linha.get("E-MAIL")).lower(),
                "celular": normalizar_texto(linha.get("CELULAR")),
                "horario_trabalho": normalizar_texto(linha.get("HORÁRIO DE TRABALHO")),
                "gestor_nome": "",
                "is_pessoa_valida": "True" if not esta_vazio(cargo) else "False",
                "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            proximo_id += 1

    df = pd.DataFrame(registros, columns=COLUNAS)

    # calcula o gestor de cada equipe (GERENTE tem prioridade sobre COORDENADOR)
    for equipe_id, grupo in df[df["equipe_id"] != ""].groupby("equipe_id"):
        lideres = grupo[grupo["cargo"].isin(_RANK_CARGO_LIDERANCA.keys())]
        if lideres.empty:
            continue
        lideres = lideres.assign(_rank=lideres["cargo"].map(_rank)).sort_values("_rank")
        lider = lideres.iloc[0]
        mascara_equipe = (df["equipe_id"] == equipe_id) & (df["colaborador_id"] != lider["colaborador_id"])
        df.loc[mascara_equipe, "gestor_nome"] = lider["nome"]

    df = invalidar_realocados_superados(df)
    df = aplicar_ajustes(df, carregar_ajustes())
    return df


def salvar_colaboradores(df: pd.DataFrame):
    return salvar_csv("colaboradores", df)


def carregar_colaboradores() -> pd.DataFrame:
    df = ler_csv("colaboradores", COLUNAS)
    # migração leve: colaboradores.csv gravado antes da coluna "cpf" existir
    # (ou qualquer coluna futura) não tem essa coluna no arquivo em disco —
    # sem isso, qualquer acesso a df["cpf"] quebraria com KeyError. Reindexar
    # por COLUNAS também garante a ordem certa das colunas na próxima gravação.
    for coluna in COLUNAS:
        if coluna not in df.columns:
            df[coluna] = ""
    colunas_extras = [c for c in df.columns if c not in COLUNAS]
    return df[COLUNAS + colunas_extras]


def proximo_colaborador_id(df: pd.DataFrame) -> str:
    numeros = df["colaborador_id"].str.extract(r"COL(\d+)", expand=False).dropna()
    proximo = (numeros.astype(int).max() + 1) if not numeros.empty else 1
    return f"COL{proximo:04d}"


def criar_ou_atualizar_colaborador(
    df: pd.DataFrame,
    *,
    colaborador_id: str | None,
    nome: str,
    cpf: str = "",
    cargo: str = "",
    equipe_id: str = "",
    email: str = "",
    celular: str = "",
    horario_trabalho: str = "",
    gestor_nome: str = "",
) -> tuple[pd.DataFrame, str]:
    """Cria um colaborador novo ou atualiza um existente (por colaborador_id).

    Usado pela tela de Cadastro de Colaboradores — o objetivo principal é
    deixar o campo `nome` idêntico ao que aparece na plataforma de
    treinamentos, já que o relacionamento entre as duas bases é feito só
    pelo nome normalizado. Retorna (dataframe atualizado, colaborador_id).
    """
    df = df.copy()
    for coluna in COLUNAS:
        if coluna not in df.columns:
            df[coluna] = ""

    nome = normalizar_texto(nome)
    valores = {
        "nome": nome,
        "nome_normalizado": normalizar_nome(nome),
        "cpf": normalizar_texto(cpf),
        "cargo": normalizar_texto(cargo).upper(),
        "equipe_id": normalizar_texto(equipe_id),
        "email": normalizar_texto(email).lower(),
        "celular": normalizar_texto(celular),
        "horario_trabalho": normalizar_texto(horario_trabalho),
        "gestor_nome": normalizar_texto(gestor_nome),
        "is_pessoa_valida": "True",
        "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    if colaborador_id and (df["colaborador_id"] == colaborador_id).any():
        idx = df.index[df["colaborador_id"] == colaborador_id][0]
        for coluna, valor in valores.items():
            df.loc[idx, coluna] = valor
        return df, colaborador_id

    novo_id = proximo_colaborador_id(df)
    nova_linha = {"colaborador_id": novo_id, **valores}
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    return df, novo_id


def nomes_normalizados_validos(df: pd.DataFrame) -> list[str]:
    validos = df[df["is_pessoa_valida"] == "True"]
    return sorted(set(n for n in validos["nome_normalizado"] if n))


def buscar_por_nome_normalizado(df: pd.DataFrame, nome_normalizado: str) -> pd.DataFrame:
    return df[df["nome_normalizado"] == nome_normalizado]
