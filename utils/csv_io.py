"""Camada central de persistência dos "CSVs" do sistema — nenhum outro
arquivo deve ler/gravar dado diretamente por fora daqui (nem caminho de
arquivo fixo, nem cliente de banco direto).

Dois modos, controlados por STORAGE_MODE (st.secrets ou variável de
ambiente; "auto" por padrão):

- local: lê/grava arquivos em data/*.csv, com backup automático
  (data/backups/) antes de cada gravação, gravação atômica (arquivo
  temporário + substituição) e uma trava de arquivo simples contra duas
  gravações simultâneas corromperem o mesmo CSV. É o que roda hoje sem
  nenhuma configuração — nada muda pra quem só usa localmente.
- remote: cada "CSV" vira uma tabela num banco Postgres gerenciado pelo
  Supabase — sobrevive à hibernação/reinício do Streamlit Community Cloud
  (o disco do container é apagado a cada reinício; o banco no Supabase,
  não). Ativado sozinho quando existem st.secrets["SUPABASE_URL"] e
  st.secrets["SUPABASE_KEY"] (modo "auto"), ou forçado via
  STORAGE_MODE="remote"/"local". Ver .streamlit/secrets.toml.example e
  supabase_setup.sql (script que cria as tabelas).

Se o armazenamento remoto estiver configurado mas inacessível (rede fora,
credencial errada, projeto pausado), as funções de leitura/gravação levantam
ArmazenamentoIndisponivelError em vez de devolver dado vazio silenciosamente
— um "banco vazio" nunca deve ser confundido com "sem colaboradores
cadastrados". app.py trata esse erro de forma centralizada.
"""
import json
import os
import shutil
import tempfile
import time
from datetime import datetime

import pandas as pd
import streamlit as st

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
BACKUPS_DIR = os.path.join(DATA_DIR, "backups")

CAMINHOS = {
    "colaboradores": os.path.join(DATA_DIR, "colaboradores.csv"),
    "treinamentos": os.path.join(DATA_DIR, "treinamentos.csv"),
    "usuarios": os.path.join(DATA_DIR, "usuarios.csv"),
    "logs": os.path.join(DATA_DIR, "logs.csv"),
    "revisoes": os.path.join(DATA_DIR, "revisoes_manuais.csv"),
    "colaboradores_ajustes": os.path.join(DATA_DIR, "colaboradores_ajustes.csv"),
}

# nome da chave == nome da tabela no Postgres do Supabase. Precisam existir
# de antemão (ver supabase_setup.sql) — a conexão só lê/escreve tabelas já
# criadas, não cria tabela nova sozinha.


class ArmazenamentoIndisponivelError(Exception):
    """Levantada quando o armazenamento remoto está configurado mas não
    responde — nunca deve ser confundida/engolida como "sem dados"."""


def _detalhes_erro(e: Exception) -> str:
    """Extrai o máximo de detalhe disponível do erro original (tipo sempre;
    código/mensagem/details/hint da API do Supabase quando for esse tipo de
    erro — ex.: "permission denied", tabela inexistente, coluna NOT NULL
    vazia; senão só a mensagem padrão da exceção, ex.: timeout/erro de
    rede/ValueError de serialização). `details`/`hint` vêm direto do corpo
    JSON de erro do PostgREST (postgrest.exceptions.APIError) e costumam
    conter a causa real quando `message` sozinha é genérica demais. Incluído
    na mensagem da ArmazenamentoIndisponivelError pra quem for investigar um
    incidente não precisar adivinhar às cegas — antes só chegava a mensagem
    genérica, sem tipo/código/detalhe nenhum do problema real."""
    partes = [type(e).__name__]
    codigo = getattr(e, "code", None)
    if codigo:
        partes.append(f"code={codigo}")
    mensagem = getattr(e, "message", None) or str(e)
    if mensagem:
        partes.append(str(mensagem)[:300])
    details = getattr(e, "details", None)
    if details:
        partes.append(f"details={str(details)[:300]}")
    hint = getattr(e, "hint", None)
    if hint:
        partes.append(f"hint={str(hint)[:300]}")
    return " | ".join(partes)


# --------------------------------------------------------- modo de operação

def _modo_storage() -> str:
    """'local' | 'remote' | 'auto' (padrão). 'auto' liga o modo remoto
    sozinho quando as credenciais do Supabase existem em st.secrets —
    preserva o comportamento de hoje (zero configuração local).

    Variável de ambiente tem prioridade sobre st.secrets de propósito: é o
    mecanismo que scripts internos (migrar_storage.py) usam pra forçar um
    modo especificamente NAQUELA chamada, mesmo com um STORAGE_MODE fixo em
    secrets.toml (ex.: "local" fixado ali como trava de segurança) — sem
    essa prioridade, a variável de ambiente nunca conseguiria "furar" o que
    já está fixo no arquivo."""
    valor = os.environ.get("STORAGE_MODE")
    if not valor:
        try:
            valor = st.secrets.get("STORAGE_MODE")
        except Exception:
            valor = None
    valor = valor or "auto"
    return str(valor).strip().lower()


def _credenciais_supabase() -> tuple[str, str] | None:
    """st.secrets primeiro (produção/Streamlit Cloud), variável de ambiente
    como alternativa — útil pro script de migração rodar fora do runtime
    completo do Streamlit (python scripts/migrar_storage.py), sem precisar
    de um secrets.toml só pra isso."""
    try:
        url = st.secrets.get("SUPABASE_URL")
        chave = st.secrets.get("SUPABASE_KEY")
    except Exception:
        url = chave = None
    url = url or os.environ.get("SUPABASE_URL")
    chave = chave or os.environ.get("SUPABASE_KEY")
    return (url, chave) if url and chave else None


def _usar_supabase() -> bool:
    modo = _modo_storage()
    if modo == "local":
        return False
    if modo == "remote":
        return True
    return _credenciais_supabase() is not None


@st.cache_resource(show_spinner=False)
def _cliente_supabase():
    from supabase import create_client
    credenciais = _credenciais_supabase()
    if credenciais is None:
        raise ArmazenamentoIndisponivelError("SUPABASE_URL/SUPABASE_KEY não configurados.")
    url, chave = credenciais
    return create_client(url, chave)


def garantir_pastas():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUPS_DIR, exist_ok=True)


def caminho_csv(nome: str) -> str:
    """Só faz sentido no modo local — no modo remoto não existe caminho de
    arquivo nenhum, os dados moram no banco."""
    if nome not in CAMINHOS:
        raise ValueError(f"CSV desconhecido: {nome}")
    return CAMINHOS[nome]


def arquivo_existe(nome: str) -> bool:
    """Já existe algum conteúdo gravado pra esse nome?"""
    if _usar_supabase():
        try:
            resposta = _cliente_supabase().table(nome).select("id").limit(1).execute()
            return bool(resposta.data)
        except Exception as e:
            raise ArmazenamentoIndisponivelError(f"Não foi possível verificar '{nome}' no armazenamento remoto. ({_detalhes_erro(e)})") from e
    return os.path.exists(caminho_csv(nome))


def obter_data_modificacao(nome: str) -> datetime | None:
    """Local: data de modificação do arquivo. Remoto: data do backup mais
    recente registrado pra esse nome (aproximação — é atualizado a cada
    gravação real, ver fazer_backup)."""
    if _usar_supabase():
        try:
            resposta = (
                _cliente_supabase().table("backups").select("criado_em")
                .eq("nome", nome).order("criado_em", desc=True).limit(1).execute()
            )
            linhas = resposta.data or []
        except Exception as e:
            raise ArmazenamentoIndisponivelError(f"Não foi possível consultar a data de '{nome}' no armazenamento remoto. ({_detalhes_erro(e)})") from e
        if not linhas:
            return None
        return datetime.strptime(linhas[0]["criado_em"], "%Y-%m-%d %H:%M:%S")
    caminho = caminho_csv(nome)
    if not os.path.exists(caminho):
        return None
    return datetime.fromtimestamp(os.path.getmtime(caminho))


def invalidar_cache(nome: str | None = None):
    """ler_csv() propositalmente nunca usa st.cache_data (ver histórico no
    docstring de ler_csv) — essa função existe pra quem cria alguma cache
    própria por cima (ex.: st.cache_data numa página específica) ter um
    ponto único e óbvio pra invalidar depois de uma gravação. `nome` é
    aceito por simetria de interface mas ignorado: a limpeza é sempre
    global (st.cache_data.clear() não suporta chave parcial)."""
    try:
        st.cache_data.clear()
    except Exception:
        pass


# -------------------------------------------------------------- trava local

class _TravaArquivo:
    """Lock simples baseado em criação exclusiva de arquivo — evita que duas
    gravações simultâneas no mesmo CSV local corrompam uma à outra
    (escritas intercaladas/truncadas). Não é um lock de banco de dados de
    verdade (não protege o ciclo leitura->alteração->gravação inteiro,
    só a escrita final), mas é suficiente pro volume de uso deste sistema
    sem precisar de infraestrutura nova — trava "presa" por um processo
    morto se auto-recupera após o timeout."""

    def __init__(self, nome: str, timeout: float = 5.0):
        self.caminho_lock = os.path.join(DATA_DIR, f".{nome}.lock")
        self.timeout = timeout
        self._fd = None

    def __enter__(self):
        garantir_pastas()
        limite = time.monotonic() + self.timeout
        while True:
            try:
                self._fd = os.open(self.caminho_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.monotonic() > limite:
                    try:
                        os.remove(self.caminho_lock)  # trava presa (processo anterior morreu sem liberar)
                    except OSError:
                        pass
                    continue
                time.sleep(0.05)

    def __exit__(self, *_exc):
        if self._fd is not None:
            os.close(self._fd)
        try:
            os.remove(self.caminho_lock)
        except OSError:
            pass


# ------------------------------------------------------------------ leitura

def ler_csv(nome: str, colunas_default=None) -> pd.DataFrame:
    """Lê a tabela do sistema, sempre "ao vivo" (sem cache) — local ou
    remoto, dependendo do modo ativo. Se ainda não existir conteúdo local,
    cria vazio com as colunas informadas; no modo remoto, tabela vazia
    também retorna vazio normalmente (não é erro). Erro real de conexão
    levanta ArmazenamentoIndisponivelError em vez de devolver vazio.

    Já existiu uma versão com cache (st.cache_data, invalidado por mtime do
    arquivo) para reduzir releituras repetidas do mesmo CSV a cada rerun do
    Streamlit. Removida: um processo de longa duração ficou mostrando um
    valor de "Última atualização" desatualizado mesmo depois do arquivo já
    ter sido salvo com o conteúdo novo — leitura sempre "ao vivo" elimina
    esse risco. Reintroduzir cache aqui reabriria a mesma classe de bug;
    quem precisar de cache local a uma página deve usar invalidar_cache()
    depois de qualquer gravação.
    """
    if _usar_supabase():
        return _ler_supabase(nome, colunas_default)
    return _ler_local(nome, colunas_default)


def _ler_local(nome, colunas_default):
    garantir_pastas()
    caminho = caminho_csv(nome)
    if not os.path.exists(caminho):
        df = pd.DataFrame(columns=colunas_default or [])
        _escrever_local_atomico(caminho, df)
        return df
    return pd.read_csv(caminho, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def _normalizar_colunas(df: pd.DataFrame, colunas_default) -> pd.DataFrame:
    df = df.drop(columns=[c for c in ("id",) if c in df.columns])
    colunas_default = list(colunas_default or [])
    for coluna in colunas_default:
        if coluna not in df.columns:
            df[coluna] = ""
    colunas_extras = [c for c in df.columns if c not in colunas_default]
    return df[colunas_default + colunas_extras] if colunas_default else df


def _ler_todas_as_linhas_supabase(nome: str) -> list[dict]:
    """PostgREST (Supabase) limita o número de linhas por resposta (o padrão
    é 1000) — sem paginar explicitamente, uma tabela grande (treinamentos.csv
    já passa de 5 mil linhas) voltava só a primeira página, silenciosamente
    incompleta. Encontrado rodando a migração real: 5283 linhas locais
    viraram 1000 no remoto sem nenhum erro. Usado tanto pra leitura normal
    quanto pra backup (que também lê a tabela inteira antes de sobrescrever
    — sofria do mesmo truncamento)."""
    cliente = _cliente_supabase()
    linhas = []
    tamanho_pagina = 1000
    inicio = 0
    while True:
        resposta = cliente.table(nome).select("*").range(inicio, inicio + tamanho_pagina - 1).execute()
        pagina = resposta.data or []
        linhas.extend(pagina)
        if len(pagina) < tamanho_pagina:
            break
        inicio += tamanho_pagina
    return linhas


def _ler_supabase(nome, colunas_default) -> pd.DataFrame:
    try:
        linhas = _ler_todas_as_linhas_supabase(nome)
    except Exception as e:
        raise ArmazenamentoIndisponivelError(f"Não foi possível ler '{nome}' do armazenamento remoto. ({_detalhes_erro(e)})") from e
    df = pd.DataFrame(linhas).fillna("").astype(str) if linhas else pd.DataFrame()
    return _normalizar_colunas(df, colunas_default)


# ------------------------------------------------------------------ backup

def fazer_backup(nome: str) -> str | None:
    """Cópia de segurança do conteúdo atual antes de uma gravação.

    Local: copia o CSV pra data/backups/ com timestamp. Remoto: grava uma
    cópia do conteúdo atual (como JSON) na tabela "backups" — o Supabase
    gratuito não guarda histórico de versões automático, então isso
    continua sendo necessário lá.

    Chamada isolada (fora de salvar_csv) usa sua própria trava — quem
    precisar encadear backup + escrita sob a MESMA trava (evita que outra
    gravação simultânea invada entre as duas etapas) deve usar
    _fazer_backup_local_sem_trava dentro de um "with _TravaArquivo(nome)"
    próprio, como salvar_csv e restaurar_backup já fazem."""
    if _usar_supabase():
        _fazer_backup_supabase(nome)
        return None
    with _TravaArquivo(nome):
        return _fazer_backup_local_sem_trava(nome)


def _fazer_backup_local_sem_trava(nome: str) -> str | None:
    garantir_pastas()
    caminho = caminho_csv(nome)
    if not os.path.exists(caminho):
        return None
    # microssegundos no timestamp: duas gravações em sequência rápida (comum
    # em uso automatizado/testes, e possível também em uso real) não podem
    # colidir no mesmo nome de arquivo de backup — colisão faria a segunda
    # cópia simplesmente sobrescrever a primeira, perdendo aquele estado.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = os.path.join(BACKUPS_DIR, f"{nome}_{timestamp}.csv")
    shutil.copy2(caminho, destino)
    _limpar_backups_antigos(nome)
    return destino


_RETENCAO_BACKUPS = 20  # por nome de CSV — evita acúmulo indefinido em data/backups/


def _limpar_backups_antigos(nome: str) -> None:
    if not os.path.isdir(BACKUPS_DIR):
        return
    candidatos = sorted(
        (f for f in os.listdir(BACKUPS_DIR) if f.startswith(f"{nome}_") and f.endswith(".csv")),
        reverse=True,
    )
    for antigo in candidatos[_RETENCAO_BACKUPS:]:
        try:
            os.remove(os.path.join(BACKUPS_DIR, antigo))
        except OSError:
            pass


def _fazer_backup_supabase(nome: str) -> None:
    try:
        linhas = _ler_todas_as_linhas_supabase(nome)
    except Exception as e:
        raise ArmazenamentoIndisponivelError(f"Não foi possível fazer backup de '{nome}' antes de gravar (armazenamento remoto indisponível). ({_detalhes_erro(e)})") from e
    if not linhas:
        return
    for linha in linhas:
        linha.pop("id", None)
    _cliente_supabase().table("backups").insert({
        "nome": nome,
        "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dados_json": json.dumps(linhas, ensure_ascii=False, default=str),
    }).execute()


def restaurar_backup(nome: str, caminho_backup: str | None = None) -> bool:
    """Restaura o backup mais recente (ou um específico, no modo local, via
    caminho_backup) por cima do dado atual. Sempre faz um novo backup do
    estado atual antes de restaurar — a própria restauração é reversível.
    Retorna False se não havia nenhum backup disponível."""
    if _usar_supabase():
        return _restaurar_backup_supabase(nome)
    with _TravaArquivo(nome):
        if caminho_backup is None:
            candidatos = sorted(
                (f for f in os.listdir(BACKUPS_DIR) if f.startswith(f"{nome}_") and f.endswith(".csv")),
                reverse=True,
            ) if os.path.isdir(BACKUPS_DIR) else []
            if not candidatos:
                return False
            caminho_backup = os.path.join(BACKUPS_DIR, candidatos[0])
        if not os.path.exists(caminho_backup):
            return False
        _fazer_backup_local_sem_trava(nome)  # preserva o estado atual antes de sobrescrever — a restauração também é reversível
        shutil.copy2(caminho_backup, caminho_csv(nome))
    return True


def _restaurar_backup_supabase(nome: str) -> bool:
    try:
        resposta = (
            _cliente_supabase().table("backups").select("*").eq("nome", nome)
            .order("criado_em", desc=True).limit(1).execute()
        )
        linhas = resposta.data or []
    except Exception as e:
        raise ArmazenamentoIndisponivelError(f"Não foi possível consultar backups de '{nome}' no armazenamento remoto. ({_detalhes_erro(e)})") from e
    if not linhas:
        return False
    dados = json.loads(linhas[0]["dados_json"])
    df = pd.DataFrame(dados)
    _fazer_backup_supabase(nome)
    _escrever_supabase(nome, df)
    return True


# ------------------------------------------------------------------ escrita

def _escrever_local_atomico(caminho: str, df: pd.DataFrame) -> None:
    """Grava num arquivo temporário no mesmo diretório, confirma que ele
    ficou íntegro (mesma quantidade de linhas relida de volta) e só então
    substitui o arquivo original — os.replace é atômico tanto no Windows
    quanto no Linux, então nunca existe um instante com o CSV pela metade,
    mesmo se o processo for interrompido no meio da escrita."""
    diretorio = os.path.dirname(caminho) or "."
    fd, caminho_tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".csv", dir=diretorio)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
            df.to_csv(f, index=False)
        verificacao = pd.read_csv(caminho_tmp, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        if len(verificacao) != len(df):
            raise ValueError(f"gravação atômica inconsistente em {caminho}: {len(df)} linha(s) esperada(s), {len(verificacao)} lida(s) de volta")
        os.replace(caminho_tmp, caminho)
    except Exception:
        if os.path.exists(caminho_tmp):
            os.remove(caminho_tmp)
        raise


def _escrever(nome: str, df: pd.DataFrame) -> None:
    if _usar_supabase():
        _escrever_supabase(nome, df)
    else:
        garantir_pastas()
        with _TravaArquivo(nome):
            _escrever_local_atomico(caminho_csv(nome), df)


def _escrever_supabase(nome: str, df: pd.DataFrame) -> None:
    cliente = _cliente_supabase()
    try:
        cliente.table(nome).delete().neq("id", -1).execute()
        if not df.empty:
            # fillna ANTES do astype(str): em colunas de texto com célula
            # vazia, o pandas usa internamente o StringDtype mais novo, cujo
            # marcador de ausência sobrevive como float NaN mesmo depois do
            # astype(str) — não vira a string "nan" (só acontece isso em
            # colunas numéricas). Um NaN sozinho no payload quebra a
            # serialização JSON do cliente do Supabase ("Out of range float
            # values are not JSON compliant: nan") antes mesmo da requisição
            # sair — mesmo padrão já usado na leitura (_ler_supabase, acima).
            registros = df.fillna("").astype(str).to_dict(orient="records")
            # o Postgres tem limite de tamanho por requisição — grava em
            # lotes pra tabelas grandes (treinamentos.csv já passa de 3 mil
            # linhas hoje).
            tamanho_lote = 500
            for inicio in range(0, len(registros), tamanho_lote):
                cliente.table(nome).insert(registros[inicio:inicio + tamanho_lote]).execute()
    except Exception as e:
        raise ArmazenamentoIndisponivelError(f"Não foi possível gravar '{nome}' no armazenamento remoto — os dados NÃO foram salvos. ({_detalhes_erro(e)})") from e


def salvar_csv(nome: str, df: pd.DataFrame) -> str | None:
    """Faz backup e grava o novo conteúdo. Retorna o caminho do backup local
    (ou None — sempre None no modo remoto, que guarda o backup no próprio
    banco em vez de um arquivo).

    No modo local, backup e escrita ficam sob a MESMA trava de arquivo: as
    duas etapas fazendo trava própria cada uma (como era antes) permitia
    outra gravação simultânea entrar bem no meio das duas, e no Windows uma
    delas podia até falhar com "arquivo em uso por outro processo" — visto
    de verdade rodando o teste de concorrência desta camada."""
    if _usar_supabase():
        backup = fazer_backup(nome)
        _escrever_supabase(nome, df)
        return backup
    with _TravaArquivo(nome):
        backup = _fazer_backup_local_sem_trava(nome)
        _escrever_local_atomico(caminho_csv(nome), df)
    return backup


def salvar_csv_sem_backup(nome: str, df: pd.DataFrame) -> None:
    """Grava sem gerar backup — usada só por logs.csv: é escrita a cada ação
    do usuário, e um backup a cada linha de log geraria excesso de dados
    (arquivos no modo local, linhas na tabela "backups" no modo remoto)."""
    _escrever(nome, df)


def inserir_linha(nome: str, linha: dict) -> None:
    """Acrescenta uma linha sem reler/reescrever a tabela inteira em memória
    de forma exposta ao chamador — usada por logs.csv (escrita de alto
    volume, uma linha por ação do usuário, onde o padrão "ler tudo, somar
    uma linha, sobrescrever tudo" é o mais arriscado sob concorrência).

    Remoto: INSERT real no Postgres — seguro mesmo com dois usuários
    gravando ao mesmo tempo, cada INSERT é independente pro banco.
    Local: ainda precisa reler+regravar o arquivo inteiro (CSV não suporta
    inserção parcial), mas agora protegido pela mesma trava de arquivo e
    gravação atômica das outras operações."""
    if _usar_supabase():
        try:
            _cliente_supabase().table(nome).insert({k: str(v) for k, v in linha.items()}).execute()
        except Exception as e:
            raise ArmazenamentoIndisponivelError(f"Não foi possível gravar em '{nome}' no armazenamento remoto. ({_detalhes_erro(e)})") from e
        return
    garantir_pastas()
    with _TravaArquivo(nome):
        caminho = caminho_csv(nome)
        if os.path.exists(caminho):
            df = pd.read_csv(caminho, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        else:
            df = pd.DataFrame(columns=list(linha.keys()))
        df = pd.concat([df, pd.DataFrame([linha])], ignore_index=True)
        _escrever_local_atomico(caminho, df)


# -------------------------------------------------------------- estado (json)

def _caminho_estado(nome: str) -> str:
    garantir_pastas()
    return os.path.join(DATA_DIR, f"estado_{nome}.json")


def salvar_estado(nome: str, dados: dict):
    if _usar_supabase():
        _salvar_estado_supabase(nome, dados)
        return
    with open(_caminho_estado(nome), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2, default=str)


def carregar_estado(nome: str) -> dict | None:
    if _usar_supabase():
        return _carregar_estado_supabase(nome)
    caminho = _caminho_estado(nome)
    if not os.path.exists(caminho):
        return None
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def _salvar_estado_supabase(nome: str, dados: dict) -> None:
    cliente = _cliente_supabase()
    try:
        cliente.table("estado").delete().eq("nome", nome).execute()
        cliente.table("estado").insert({
            "nome": nome,
            "json": json.dumps(dados, ensure_ascii=False, default=str),
        }).execute()
    except Exception as e:
        raise ArmazenamentoIndisponivelError(f"Não foi possível gravar o estado no armazenamento remoto. ({_detalhes_erro(e)})") from e


def _carregar_estado_supabase(nome: str) -> dict | None:
    try:
        resposta = _cliente_supabase().table("estado").select("*").eq("nome", nome).execute()
        linhas = resposta.data or []
    except Exception as e:
        raise ArmazenamentoIndisponivelError(f"Não foi possível ler o estado do armazenamento remoto. ({_detalhes_erro(e)})") from e
    if not linhas:
        return None
    return json.loads(linhas[0]["json"])
