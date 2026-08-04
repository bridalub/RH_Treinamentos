"""Formatação de datas e números no padrão brasileiro, usada em todas as telas."""
import math

import pandas as pd

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def formatar_numero_br(valor, casas_decimais: int = 0) -> str:
    """Formata um número com separador de milhar '.' e decimal ',' (padrão BR).
    Ex.: 3940 -> '3.940'; 48.5 -> '48,5'. Vazio para None/NaN — nunca 'nan'/'None'."""
    if valor is None:
        return ""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    if math.isnan(numero) or math.isinf(numero):
        return ""
    texto = f"{numero:,.{casas_decimais}f}"
    return texto.replace(",", "@").replace(".", ",").replace("@", ".")


def formatar_percentual_br(valor, casas_decimais: int = 0) -> str:
    """Formata um percentual no padrão BR, com o símbolo % já incluso.
    Ex.: 59.7 -> '59,7%'; 48 -> '48%'. Vazio para None/NaN (nunca 'nan%')."""
    texto = formatar_numero_br(valor, casas_decimais)
    return f"{texto}%" if texto != "" else ""


def formatar_data_br(valor, com_hora: bool = True) -> str:
    """Converte qualquer valor de data (string ISO, Timestamp, NaT/None) para
    'DD/MM/AAAA' ou 'DD/MM/AAAA HH:mm'. Retorna string vazia para valores vazios
    e devolve o valor original (sem quebrar a tela) se não for reconhecível como data."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    if texto == "" or texto.lower() in ("nan", "nat", "none"):
        return ""
    dt = pd.to_datetime(valor, errors="coerce")
    if pd.isna(dt):
        return texto
    return dt.strftime("%d/%m/%Y %H:%M") if com_hora else dt.strftime("%d/%m/%Y")
