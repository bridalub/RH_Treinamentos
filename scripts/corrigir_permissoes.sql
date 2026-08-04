-- Corrige "permission denied for table X" encontrado ao testar a conexão.
-- As tabelas foram criadas, mas o role service_role ainda não tinha GRANT
-- explícito nelas (nem sempre é automático, dependendo do tipo de chave/
-- configuração do projeto). Cole isto no SQL Editor do Supabase e rode.

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

-- as colunas "id" são bigint generated always as identity: cada tabela tem
-- uma sequência interna própria que também precisa de permissão de uso,
-- senão o INSERT falha mesmo com o GRANT acima.
grant usage, select on all sequences in schema public to service_role;
