"""Ajustes manuais (edição/exclusão/criação) feitos em Cadastro de Colaboradores
ou em Equipes, persistidos para que uma nova importação da BASE FUNCIONÁRIOS
não desfaça o trabalho de conferência da RH. Mesma ideia de revisoes_service.py
(que já faz isso para o relacionamento treinamentos x colaborador), agora
para o cadastro de funcionários em si: a planilha de origem pode ser
reimportada à vontade, mas quem foi editado ou excluído manualmente continua
editado/excluído depois da importação seguinte."""
import pandas as pd

from utils.csv_io import ler_csv, salvar_csv
from utils.formatacao import agora_br

COLUNAS = [
    "chave", "tipo",  # tipo: EDITADO | EXCLUIDO | CRIADO
    "nome", "cpf", "cargo", "equipe_id", "email", "celular", "horario_trabalho", "gestor_nome",
    "ajustado_por", "ajustado_em",
]


def carregar_ajustes() -> pd.DataFrame:
    return ler_csv("colaboradores_ajustes", COLUNAS)


def salvar_ajuste(chave: str, tipo: str, usuario: str, **valores) -> None:
    """Grava (substituindo qualquer ajuste anterior com a mesma chave) a
    decisão manual a ser reaplicada em toda importação futura."""
    df = carregar_ajustes()
    df = df[df["chave"] != chave]
    nova = {
        "chave": chave, "tipo": tipo,
        "nome": valores.get("nome", ""), "cpf": valores.get("cpf", ""),
        "cargo": valores.get("cargo", ""), "equipe_id": valores.get("equipe_id", ""),
        "email": valores.get("email", ""), "celular": valores.get("celular", ""),
        "horario_trabalho": valores.get("horario_trabalho", ""), "gestor_nome": valores.get("gestor_nome", ""),
        "ajustado_por": usuario, "ajustado_em": agora_br().strftime("%Y-%m-%d %H:%M:%S"),
    }
    df = pd.concat([df, pd.DataFrame([nova], columns=COLUNAS)], ignore_index=True)
    salvar_csv("colaboradores_ajustes", df)


def remover_ajuste(chave: str) -> None:
    df = carregar_ajustes()
    if df.empty:
        return
    df = df[df["chave"] != chave]
    salvar_csv("colaboradores_ajustes", df)
