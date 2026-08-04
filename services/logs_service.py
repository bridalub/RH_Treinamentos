"""Auditoria de ações do sistema (logs.csv)."""
from datetime import timedelta

import pandas as pd

from utils.csv_io import ler_csv, salvar_csv, inserir_linha
from utils.formatacao import agora_br

COLUNAS = ["log_id", "data_hora", "usuario", "acao", "detalhes"]


def carregar_logs() -> pd.DataFrame:
    return ler_csv("logs", COLUNAS)


def _proximo_log_id(df: pd.DataFrame) -> str:
    """Baseado no maior log_id numérico já existente (não na contagem de
    linhas): usar len(df)+1 gerava o mesmo ID pra duas gravações próximas no
    tempo (duas leituras viam a mesma contagem antes de qualquer uma das
    duas escrever) — já aconteceu de verdade em produção (vários log_id
    duplicados encontrados em auditoria)."""
    if df.empty:
        return "LOG000001"
    numeros = df["log_id"].str.extract(r"LOG(\d+)", expand=False).dropna()
    proximo = (numeros.astype(int).max() + 1) if not numeros.empty else 1
    return f"LOG{proximo:06d}"


def registrar(usuario: str, acao: str, detalhes: str = "") -> None:
    """Grava uma linha de auditoria. Não passa pelo fluxo de backup (usado a
    cada ação do usuário; gerar um backup timestampado por log geraria
    excesso de dados). Usa inserir_linha (não reescreve o CSV inteiro no
    modo remoto — vira um INSERT de verdade, sem risco de duas gravações
    simultâneas se sobrescreverem)."""
    nova_linha = {
        "log_id": _proximo_log_id(carregar_logs()),
        "data_hora": agora_br().strftime("%Y-%m-%d %H:%M:%S"),
        "usuario": usuario,
        "acao": acao,
        "detalhes": detalhes,
    }
    inserir_linha("logs", nova_linha)


def limpar_logs_antigos(dias: int | None) -> int:
    """Remove os registros mais antigos que `dias` dias (do mais antigo para o
    mais novo); `dias=None` remove todos. Ao contrário de `registrar`, passa
    pelo fluxo de backup — é uma operação destrutiva. Retorna quantas linhas
    foram removidas."""
    df = carregar_logs()
    if df.empty:
        return 0

    if dias is None:
        removidos = len(df)
        salvar_csv("logs", pd.DataFrame(columns=COLUNAS))
        return removidos

    datas = pd.to_datetime(df["data_hora"], errors="coerce")
    # sem tzinfo (.replace(tzinfo=None)): "datas" acima vem de strings sem
    # fuso gravado, então é naive — comparar direto contra um datetime com
    # tzinfo quebraria com TypeError. O valor de agora_br() já está certo
    # (horário de Brasília); só tira a marca de fuso pra poder comparar.
    corte = agora_br().replace(tzinfo=None) - timedelta(days=dias)
    mascara_manter = datas >= corte
    removidos = int((~mascara_manter).sum())
    if removidos:
        salvar_csv("logs", df[mascara_manter].reset_index(drop=True))
    return removidos
