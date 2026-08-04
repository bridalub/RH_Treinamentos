-- Script de criação das tabelas do sistema BRIDA Treinamentos no Supabase.
-- Cole este arquivo inteiro no SQL Editor do Supabase (menu lateral > SQL
-- Editor > New query) e clique em "Run". Cria as 7 tabelas de uma vez,
-- todas com colunas de texto (mesmo formato que os CSVs de hoje — o
-- sistema sempre tratou tudo como texto, nunca como número/data nativos).

create table if not exists colaboradores (
    id bigint generated always as identity primary key,
    colaborador_id text,
    nome text,
    nome_normalizado text,
    cpf text,
    equipe_id text,
    cargo text,
    email text,
    celular text,
    horario_trabalho text,
    gestor_nome text,
    is_pessoa_valida text,
    atualizado_em text
);

create table if not exists treinamentos (
    id bigint generated always as identity primary key,
    treinamento_id text,
    nome_colaborador_planilha text,
    nome_normalizado text,
    cpf text,
    titulo_treinamento text,
    status text,
    data_inscricao text,
    data_conclusao text,
    dtb_lider text,
    dtb_area text,
    dtb_lob text,
    dtb_cargo text,
    dtb_data_desligamento text,
    data_contratacao text,
    ultimo_acesso text,
    tipo_treino text,
    situacao_relacionamento text,
    nome_colaborador_relacionado text,
    importado_em text
);

create table if not exists usuarios (
    id bigint generated always as identity primary key,
    usuario_id text,
    login text,
    nome text,
    senha_hash text,
    perfil text,
    ativo text,
    criado_em text,
    ultimo_login text
);

create table if not exists logs (
    id bigint generated always as identity primary key,
    log_id text,
    data_hora text,
    usuario text,
    acao text,
    detalhes text
);

create table if not exists revisoes (
    id bigint generated always as identity primary key,
    nome_planilha_normalizado text,
    nome_planilha_original text,
    decisao text,
    nome_colaborador_normalizado text,
    nome_colaborador_exibicao text,
    decidido_por text,
    decidido_em text
);

create table if not exists colaboradores_ajustes (
    id bigint generated always as identity primary key,
    chave text,
    tipo text,
    nome text,
    cpf text,
    cargo text,
    equipe_id text,
    email text,
    celular text,
    horario_trabalho text,
    gestor_nome text,
    ajustado_por text,
    ajustado_em text
);

create table if not exists estado (
    id bigint generated always as identity primary key,
    nome text,
    json text
);

-- Guarda uma cópia do conteúdo de cada tabela antes de toda gravação (o
-- Supabase gratuito não tem histórico de versões automático como o Google
-- Sheets teria) — mesmo papel da pasta data/backups/ no modo local.
create table if not exists backups (
    id bigint generated always as identity primary key,
    nome text,
    criado_em text,
    dados_json text
);

-- Sem isso, a chave service_role recebe "permission denied for table X" ao
-- tentar ler/gravar — o GRANT nas tabelas não é sempre automático dependendo
-- da configuração/tipo de chave do projeto.
grant usage on schema public to service_role;

grant select, insert, update, delete on
    public.colaboradores,
    public.treinamentos,
    public.usuarios,
    public.logs,
    public.revisoes,
    public.colaboradores_ajustes,
    public.estado,
    public.backups
to service_role;

grant usage, select on all sequences in schema public to service_role;
