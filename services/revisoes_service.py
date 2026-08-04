"""Decisões manuais de relacionamento (RH), persistidas para valer também nas próximas importações."""
import pandas as pd

from utils.csv_io import ler_csv, salvar_csv
from utils.formatacao import agora_br

COLUNAS = [
    "nome_planilha_normalizado", "nome_planilha_original", "decisao",
    "nome_colaborador_normalizado", "nome_colaborador_exibicao",
    "decidido_por", "decidido_em",
]


def carregar_overrides() -> pd.DataFrame:
    return ler_csv("revisoes", COLUNAS)


def salvar_override(nome_normalizado: str, nome_original: str, decisao: str,
                     nome_colaborador_normalizado: str | None, nome_colaborador_exibicao: str | None,
                     usuario: str) -> None:
    df = carregar_overrides()
    df = df[df["nome_planilha_normalizado"] != nome_normalizado]
    nova = {
        "nome_planilha_normalizado": nome_normalizado,
        "nome_planilha_original": nome_original,
        "decisao": decisao,
        "nome_colaborador_normalizado": nome_colaborador_normalizado or "",
        "nome_colaborador_exibicao": nome_colaborador_exibicao or "",
        "decidido_por": usuario,
        "decidido_em": agora_br().strftime("%Y-%m-%d %H:%M:%S"),
    }
    df = pd.concat([df, pd.DataFrame([nova], columns=COLUNAS)], ignore_index=True)
    salvar_csv("revisoes", df)
