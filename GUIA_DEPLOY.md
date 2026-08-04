# Guia de Deploy — Streamlit Community Cloud + Supabase

Este sistema grava dados em tabelas (hoje, arquivos `.csv` locais). No
Streamlit Community Cloud o disco do app **não é persistente** — a cada
"dormida" por inatividade ou novo `git push`, o container é recriado do zero
e qualquer CSV local escrito durante o uso é perdido. Por isso, em produção,
os mesmos dados passam a morar num banco Supabase (Postgres gerenciado,
plano gratuito permanente) — o código já está pronto pra isso, só falta a
configuração abaixo, que só você consegue fazer (é a sua conta).

Sem essa configuração, o sistema continua funcionando 100% normal em CSV
local — nada quebra rodando localmente.

## 1. Criar o projeto no Supabase

1. Crie uma conta em [supabase.com](https://supabase.com) (dá pra entrar com Google).
2. "New project" > escolha organização > nome `brida-treinamentos` > defina uma senha de banco forte (guarde) > região mais próxima > "Create new project". Espera 1-2 minutos.

## 2. Criar as tabelas

1. No painel do projeto, menu lateral > **SQL Editor** > **New query**.
2. Abra o arquivo `supabase_setup.sql` (na raiz deste repositório), copie o conteúdo inteiro e cole no editor.
3. Clique em **Run**. Isso cria as 8 tabelas de uma vez (`colaboradores`, `treinamentos`, `usuarios`, `logs`, `revisoes`, `colaboradores_ajustes`, `estado`, `backups`).
4. Confirme em **Table Editor** (menu lateral) que as 8 tabelas aparecem, todas vazias.

## 3. Pegar as credenciais

1. Menu lateral > **Project Settings** (ícone de engrenagem) > **Data API**.
2. Copie o campo **Project URL** — isso é o `SUPABASE_URL`.
3. Role até **Project API keys** e copie a chave **`service_role`** (não a `anon public`) — isso é o `SUPABASE_KEY`. Essa chave dá acesso total ao banco, sem restrição — por isso só pode ir em secrets, nunca em código commitado.

## 4. Configurar os secrets

Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` (esse
arquivo real nunca vai pro Git — já está no `.gitignore`) e preencha
`SUPABASE_URL` e `SUPABASE_KEY` com os valores do passo 3.

No **Streamlit Community Cloud**, esses valores não vão em arquivo nenhum:
depois de publicar o app, vá em **⋮ (menu do app) > Settings > Secrets** e
cole o conteúdo completo do `.streamlit/secrets.toml` preenchido lá.

## 5. Testar localmente antes de confiar em produção

Com o `.streamlit/secrets.toml` preenchido, rode o app localmente
(`streamlit run app.py`) e confirme no **Table Editor** do Supabase que
login, cadastro de colaborador e importação de treinamentos gravam de
verdade nas tabelas (as linhas aparecem lá em tempo real). Faça esse teste
antes do primeiro uso real em produção.

## 6. Publicar

1. `git push` para o repositório no GitHub.
2. Em [share.streamlit.io](https://share.streamlit.io), conecte o repositório e aponte para `app.py`.
3. Configure os secrets (passo 4) antes do primeiro acesso real — sem eles o app sobe, mas fica 100% ephemeral (volta ao CSV local vazio a cada reinício).

## Limitações conhecidas dessa abordagem

- **Automação de download (CSOD via Playwright)**: não é suportada de forma
  confiável no Streamlit Community Cloud (sem um jeito padrão de instalar o
  navegador headless nesse ambiente). Use sempre o upload manual do `.xlsx`
  quando estiver rodando na nuvem — continua funcionando normalmente.
- **Gravação continua sendo "tabela inteira de uma vez"**: pra não precisar
  reescrever a lógica de todos os services, cada gravação apaga e reinsere
  a tabela inteira (igual o CSV local faz hoje, só que num banco de
  verdade). Funciona bem pro volume de uso desta equipe, mas duas pessoas
  salvando quase ao mesmo tempo ainda podem se sobrescrever — não há trava
  de linha. Uma migração futura pra escrita linha a linha resolveria isso,
  mas é um trabalho maior, fora do escopo desta migração inicial.
- **Plano gratuito do Supabase**: projeto pausa sozinho após ~1 semana sem
  nenhum acesso (reativa automaticamente no próximo acesso, sem perder
  dados — só demora alguns segundos a mais nesse primeiro acesso). Tem
  limite de 500MB de banco, bem acima do que este sistema usa hoje.
