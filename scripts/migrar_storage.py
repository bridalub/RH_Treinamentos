"""Migração inicial: envia os CSVs locais (data/*.csv) para o armazenamento
remoto configurado (Supabase). Rotina administrativa manual — NÃO roda
sozinha em nenhum fluxo do sistema, só quando chamada explicitamente:

    python scripts/migrar_storage.py                  # simula, não grava nada
    python scripts/migrar_storage.py --confirmar       # executa de verdade
    python scripts/migrar_storage.py --confirmar --forcar   # sobrescreve mesmo se a tabela remota já tiver dado

Idempotente: rodar de novo com o mesmo CSV local não duplica nada (a escrita
remota sempre substitui o conteúdo da tabela pelo conteúdo enviado, nunca
soma). Por segurança, se a tabela remota já tiver alguma linha, o script
para e pede --forcar — evita sobrescrever sem querer um banco que já está
em uso.

Pré-requisito: SUPABASE_URL e SUPABASE_KEY configurados (em
.streamlit/secrets.toml ou variável de ambiente) e as tabelas já criadas
(ver supabase_setup.sql).
"""
import argparse
import os
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from utils import csv_io
from services.colaboradores_service import COLUNAS as COL_COLABORADORES
from services.treinamentos_service import COLUNAS as COL_TREINAMENTOS
from services.usuarios_service import COLUNAS as COL_USUARIOS
from services.logs_service import COLUNAS as COL_LOGS
from services.revisoes_service import COLUNAS as COL_REVISOES
from services.colaboradores_ajustes_service import COLUNAS as COL_AJUSTES

TABELAS = {
    "colaboradores": COL_COLABORADORES,
    "treinamentos": COL_TREINAMENTOS,
    "usuarios": COL_USUARIOS,
    "logs": COL_LOGS,
    "revisoes": COL_REVISOES,
    "colaboradores_ajustes": COL_AJUSTES,
}


def _com_modo(modo: str, funcao, *args, **kwargs):
    """Força utils.csv_io a operar em modo local ou remote só durante essa
    chamada — é o que permite o mesmo script ler do CSV local e escrever no
    Supabase, mesmo com as credenciais já configuradas (que sozinhas fariam
    TUDO ir pro remoto, inclusive a leitura da fonte)."""
    anterior = os.environ.get("STORAGE_MODE")
    os.environ["STORAGE_MODE"] = modo
    try:
        return funcao(*args, **kwargs)
    finally:
        if anterior is None:
            os.environ.pop("STORAGE_MODE", None)
        else:
            os.environ["STORAGE_MODE"] = anterior


def _validar_local(nome: str, colunas: list[str]):
    df = _com_modo("local", csv_io.ler_csv, nome, colunas)
    problemas = []
    faltando = [c for c in colunas if c not in df.columns]
    if faltando:
        problemas.append(f"coluna(s) obrigatória(s) ausente(s): {faltando}")
    elif list(df.columns[: len(colunas)]) != colunas:
        problemas.append("ordem das colunas difere do esperado")
    if not df.empty and colunas[0] in df.columns and df[colunas[0]].duplicated().any():
        problemas.append(f"'{colunas[0]}' duplicado")
    return df, problemas


def _backup_local_pre_migracao():
    """Cópia extra de segurança de todos os CSVs locais antes de começar,
    além do backup automático que salvar_csv já faz — o objetivo aqui é ter
    um snapshot único, fácil de achar, do estado exato de antes da
    migração."""
    destino = os.path.join(csv_io.DATA_DIR, "backups", f"pre_migracao_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(destino, exist_ok=True)
    for nome in TABELAS:
        origem = csv_io.caminho_csv(nome)
        if os.path.exists(origem):
            import shutil
            shutil.copy2(origem, os.path.join(destino, f"{nome}.csv"))
    print(f"Backup local pré-migração salvo em: {destino}")
    return destino


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--confirmar", action="store_true", help="grava de verdade (sem isso, só simula e mostra o que faria)")
    parser.add_argument("--forcar", action="store_true", help="sobrescreve tabela remota mesmo se ela já tiver dados")
    args = parser.parse_args()

    if csv_io._credenciais_supabase() is None:
        print("ERRO: SUPABASE_URL/SUPABASE_KEY não configurados (st.secrets ou variável de ambiente). Nada a migrar.")
        sys.exit(1)

    print("=== Migração local -> remoto (Supabase) ===")
    print(f"Modo: {'EXECUÇÃO REAL' if args.confirmar else 'SIMULAÇÃO (nenhum dado será gravado)'}")
    print()

    if args.confirmar:
        _backup_local_pre_migracao()
        print()

    relatorio = []
    houve_problema_bloqueante = False

    for nome, colunas in TABELAS.items():
        print(f"--- {nome} ---")
        df_local, problemas = _validar_local(nome, colunas)
        print(f"  linhas locais: {len(df_local)} | colunas: {len(df_local.columns)}")
        for p in problemas:
            print(f"  [ATENÇÃO] {p}")

        ja_existe_remoto = _com_modo("remote", csv_io.arquivo_existe, nome)
        print(f"  já existe dado remoto: {ja_existe_remoto}")

        if ja_existe_remoto and not args.forcar:
            print("  PULADO — já existe dado remoto pra essa tabela. Use --forcar se quiser mesmo assim sobrescrever (o conteúdo remoto atual vira backup antes).")
            relatorio.append((nome, len(df_local), "pulado (já existia, sem --forcar)"))
            print()
            continue

        if not args.confirmar:
            print(f"  [simulação] enviaria {len(df_local)} linha(s) pra tabela remota '{nome}'")
            relatorio.append((nome, len(df_local), "simulado"))
            print()
            continue

        try:
            _com_modo("remote", csv_io.salvar_csv, nome, df_local)
            df_remoto = _com_modo("remote", csv_io.ler_csv, nome, colunas)
        except csv_io.ArmazenamentoIndisponivelError as e:
            print(f"  ERRO — não foi possível migrar '{nome}': {e}")
            relatorio.append((nome, len(df_local), "FALHOU (armazenamento remoto indisponível)"))
            houve_problema_bloqueante = True
            print()
            continue

        ok = len(df_remoto) == len(df_local)
        print(f"  enviado. confirmação: {len(df_remoto)} linha(s) no remoto (esperado {len(df_local)}) — {'OK' if ok else 'DIVERGÊNCIA'}")
        relatorio.append((nome, len(df_local), "migrado OK" if ok else "migrado COM DIVERGÊNCIA (confira manualmente)"))
        print()

    print("=== Resumo ===")
    for nome, linhas, status in relatorio:
        print(f"  {nome}: {linhas} linha(s) — {status}")

    if not args.confirmar:
        print()
        print("Nada foi gravado (simulação). Rode de novo com --confirmar para migrar de verdade.")

    sys.exit(1 if houve_problema_bloqueante else 0)


if __name__ == "__main__":
    main()
