"""Decisões manuais de relacionamento (RH), persistidas para valer também nas próximas importações.

Além das decisões gravadas em runtime, há uma semente versionada no código
(`OVERRIDES_SEMENTE`) para correções conhecidas que não podem depender só de
`data/*.csv` local (gitignored) — em cloud/deploy a semente é aplicada na
subida e em toda leitura de overrides.
"""
import pandas as pd

from utils.csv_io import ler_csv, salvar_csv
from utils.formatacao import agora_br

COLUNAS = [
    "nome_planilha_normalizado", "nome_planilha_original", "decisao",
    "nome_colaborador_normalizado", "nome_colaborador_exibicao",
    "decidido_por", "decidido_em",
]

# Correções manuais conhecidas (código versionado). `forcar=True` sobrescreve
# vínculo errado já persistido (ex.: ALEXANDRE COSTA ligado a Cris por engano).
OVERRIDES_SEMENTE: list[dict] = [
    {
        "nome_planilha_normalizado": "ALEXANDRE COSTA",
        "nome_planilha_original": "ALEXANDRE COSTA",
        "decisao": "RELACIONADO",
        "nome_colaborador_normalizado": "ALEXANDRE DAUFENBACH",
        "nome_colaborador_exibicao": "ALEXANDRE DAUFENBACH (B2C)",
        "forcar": True,
    },
]


def carregar_overrides() -> pd.DataFrame:
    garantir_overrides_semente()
    return ler_csv("revisoes", COLUNAS)


def salvar_override(nome_normalizado: str, nome_original: str, decisao: str,
                     nome_colaborador_normalizado: str | None, nome_colaborador_exibicao: str | None,
                     usuario: str) -> None:
    df = ler_csv("revisoes", COLUNAS)
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


def garantir_overrides_semente() -> int:
    """Garante que as correções versionadas existam no armazenamento remoto/local.

    Retorna quantas linhas de revisão foram criadas ou corrigidas. Não usa
    `carregar_overrides()` para evitar recursão com a própria semente.
    """
    if not OVERRIDES_SEMENTE:
        return 0

    df = ler_csv("revisoes", COLUNAS)
    agora = agora_br().strftime("%Y-%m-%d %H:%M:%S")
    alterados = 0

    for semente in OVERRIDES_SEMENTE:
        chave = semente["nome_planilha_normalizado"]
        alvo_norm = semente.get("nome_colaborador_normalizado", "")
        alvo_exib = semente.get("nome_colaborador_exibicao", "")
        decisao = semente.get("decisao", "RELACIONADO")
        forcar = bool(semente.get("forcar", False))

        existentes = df[df["nome_planilha_normalizado"] == chave] if not df.empty else df
        if existentes.empty:
            nova = {
                "nome_planilha_normalizado": chave,
                "nome_planilha_original": semente.get("nome_planilha_original", chave),
                "decisao": decisao,
                "nome_colaborador_normalizado": alvo_norm,
                "nome_colaborador_exibicao": alvo_exib,
                "decidido_por": "semente-sistema",
                "decidido_em": agora,
            }
            df = pd.concat([df, pd.DataFrame([nova], columns=COLUNAS)], ignore_index=True)
            alterados += 1
            continue

        if not forcar:
            continue

        idx = existentes.index[0]
        # Corrige só quando o vínculo normalizado (ou a decisão) está errado —
        # grafia de exibição com/sem (B2C) é resolvida na sincronização com a
        # base de colaboradores.
        if (
            str(df.at[idx, "decisao"]) == decisao
            and str(df.at[idx, "nome_colaborador_normalizado"]) == alvo_norm
        ):
            continue

        df.at[idx, "decisao"] = decisao
        df.at[idx, "nome_colaborador_normalizado"] = alvo_norm
        if alvo_exib:
            df.at[idx, "nome_colaborador_exibicao"] = alvo_exib
        df.at[idx, "decidido_por"] = "semente-sistema"
        df.at[idx, "decidido_em"] = agora
        alterados += 1

    if alterados:
        salvar_csv("revisoes", df)
    return alterados


def nomes_planilha_do_colaborador(nome_colaborador_normalizado: str) -> set[str]:
    """Nomes normalizados da plataforma que a RH/semente ligou a este colaborador."""
    df = carregar_overrides()
    if df.empty or not nome_colaborador_normalizado:
        return set()
    mascara = (
        (df["decisao"] == "RELACIONADO")
        & (df["nome_colaborador_normalizado"] == nome_colaborador_normalizado)
    )
    return set(df.loc[mascara, "nome_planilha_normalizado"].tolist())
