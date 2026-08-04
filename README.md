# BRIDA · Treinamentos

Painel Streamlit de acompanhamento de treinamentos e colaboradores da
BRIDA: cruza a base de funcionários com os registros de treinamento da
plataforma corporativa (CSOD), mostra indicadores, gráficos e listas por
equipe/colaborador, e permite à RH/gestores corrigir cadastros e
relacionamentos diretamente pela interface.

## Arquitetura

```
app.py                     ponto de entrada (login, navegação, sidebar)
pages_app/                 uma página por arquivo (Início, Análises, Equipes,
                            Colaboradores, Cadastro, Atualização, Registros, Usuários)
services/                  regra de negócio de cada domínio (colaboradores,
                            treinamentos, usuários, logs, matching, revisões,
                            ajustes de colaboradores)
components/                elementos visuais reutilizáveis (cards, gráficos,
                            tabelas, tema/paleta)
utils/
  csv_io.py                camada CENTRAL de persistência — todo o resto do
                            sistema lê/grava dado só por aqui, nunca direto
                            em arquivo ou num cliente de banco
  auth.py                  hash de senha, sessão (cookie + st.session_state)
  excel_import.py          leitura das planilhas de origem (.xls/.xlsx)
  normalizacao.py           normalização de nomes usada no relacionamento
  formatacao.py             formatação de número/data/percentual em pt-BR
automations/                automação Playwright que baixa o relatório do CSOD
scripts/migrar_storage.py   migração manual (uma vez) dos CSVs locais pro banco remoto
data/                       CSVs reais + backups (nunca vai pro Git)
data_examples/              CSVs de exemplo sem dado real (vai pro Git)
supabase_setup.sql          script que cria as tabelas no Supabase
```

Nenhuma página ou service acessa arquivo ou banco diretamente — tudo passa
por `utils/csv_io.py` (`ler_csv`, `salvar_csv`, `inserir_linha`, etc.). Isso
é o que permite trocar onde os dados moram (local ou remoto) sem mexer em
nenhuma regra de negócio.

## Origem dos dados de treinamento

A única fonte aceita é a aba oficial **"DTB Bridalub - Por Usuário (2)"**
do arquivo `DTB_Bridalub_-_Por_Usuário_*.xlsx` exportado da plataforma CSOD
(a automação em `automations/` baixa esse arquivo; upload manual também
funciona). Qualquer outra aba do mesmo arquivo é ignorada — a importação é
interrompida se essa aba não existir. Essa regra não muda com a migração de
armazenamento.

## Relacionamento colaborador × treinamento

Feito **somente por nome** (nunca por CPF — nem toda pessoa da base tem CPF
cadastrado), normalizado (maiúsculo, sem acento, sem sufixos como
"- REALOCADO", sem tags entre parênteses). Casos ambíguos ou sem
correspondência caem em "Revisão de Correspondências"; decisões manuais lá
persistem (`revisoes_manuais.csv`) e são reaplicadas em toda importação
futura — reimportar a planilha nunca desfaz uma correção já feita.

## Os quatro CSVs

| Arquivo | Conteúdo | Chave |
|---|---|---|
| `colaboradores.csv` | Base de funcionários (BASE FUNCIONÁRIOS BRIDA) | `colaborador_id` |
| `treinamentos.csv` | Registros de treinamento (plataforma CSOD) | `treinamento_id` |
| `usuarios.csv` | Login do sistema (não confundir com colaboradores) | `usuario_id` |
| `logs.csv` | Auditoria de ações do sistema | `log_id` |

(mais dois auxiliares, mesmo mecanismo: `revisoes_manuais.csv` e
`colaboradores_ajustes.csv` — decisões manuais que sobrevivem a
reimportações, ver `services/revisoes_service.py` e
`services/colaboradores_ajustes_service.py`.)

## Modo local vs. produção

Controlado automaticamente por `utils/csv_io.py` — nenhuma página precisa
saber qual está ativo:

- **Local** (padrão, sem nenhuma configuração): lê/grava em `data/*.csv`,
  com backup automático, gravação atômica e trava contra duas gravações
  simultâneas corromperem o mesmo arquivo. É o que roda no seu computador.
- **Remoto** (produção no Streamlit Community Cloud): os mesmos "CSVs"
  viram tabelas num banco Postgres gerenciado pelo Supabase — sobrevive à
  hibernação/reinício do Streamlit Cloud, que apaga o disco do container a
  cada reinício.

O modo é decidido em `STORAGE_MODE` (`.streamlit/secrets.toml` ou variável
de ambiente): `"local"` força local, `"remote"` força remoto, `"auto"`
(padrão) liga o remoto sozinho quando `SUPABASE_URL`/`SUPABASE_KEY` existem.

**Por que Supabase, e não Google Sheets/OneDrive/SharePoint**: já foi
avaliado Google Sheets primeiro — funcionalmente equivalente, mas o
processo de credenciais (Google Cloud Console: projeto, ativar duas APIs,
criar conta de serviço, gerar chave) teve mais atrito no dia a dia do que
criar um projeto Supabase e colar duas strings. SharePoint/OneDrive exigiria
registrar um app no Azure AD do tenant da empresa (normalmente precisa de
aprovação de admin de TI) e não tem um conector pronto pro Streamlit — seria
integração escrita do zero. Supabase: plano gratuito permanente (sem prazo
de trial), biblioteca cliente oficial simples (`supabase-py`), e continua
sendo "uma tabela simples" (Postgres), não uma peça de infraestrutura nova
pra manter.

## Configuração

### Rodando só localmente

Nada a configurar — `streamlit run app.py` já funciona em modo local.

### Publicando com persistência remota

Veja o passo a passo completo em **[GUIA_DEPLOY.md](GUIA_DEPLOY.md)**: criar
o projeto Supabase, rodar `supabase_setup.sql`, pegar as credenciais,
preencher `.streamlit/secrets.toml` (copie de
`.streamlit/secrets.toml.example` — o arquivo real nunca é commitado).

Variáveis esperadas em secrets (ou variável de ambiente equivalente):

| Variável | Obrigatória | Uso |
|---|---|---|
| `ADMIN_SENHA_PADRAO` | não (tem valor de desenvolvimento) | senha do usuário `admin` criado na primeira execução |
| `SUPABASE_URL` | só pra modo remoto | URL do projeto Supabase |
| `SUPABASE_KEY` | só pra modo remoto | chave `service_role` do projeto (não a `anon public`) |
| `STORAGE_MODE` | não (padrão `auto`) | força `local` ou `remote` |

No **Streamlit Community Cloud**: `⋮ (menu do app) > Settings > Secrets`,
cole o conteúdo do seu `secrets.toml` preenchido lá — não existe arquivo
nenhum no repositório com valor real.

### Migração inicial (só uma vez, manual)

Depois de configurar as credenciais remotas, envie os CSVs locais existentes
pro Supabase:

```
python scripts/migrar_storage.py                        # simula, não grava nada
python scripts/migrar_storage.py --confirmar             # executa de verdade
python scripts/migrar_storage.py --confirmar --forcar    # sobrescreve mesmo se a tabela remota já tiver dado
```

Idempotente (rodar de novo não duplica) e não roda sozinha em nenhum fluxo
do sistema.

## Executando localmente

```
python -m venv .venv
.venv\Scripts\activate          (Windows)  /  source .venv/bin/activate  (Linux/Mac)
pip install -r requirements.txt
python -m playwright install chromium      # só se for usar a automação de download
streamlit run app.py
```

Usuário inicial: `admin` / senha em `ADMIN_SENHA_PADRAO` (padrão de
desenvolvimento — troque na tela de Usuários assim que logar).

## Testes

Não há uma suíte de testes automatizados formal (pytest) no repositório —
a verificação usada durante o desenvolvimento é rodar o app com Playwright
simulando o navegador (login, navegação entre páginas, criar/editar/excluir
registro) contra um ambiente local isolado. A camada de persistência
(`utils/csv_io.py`) foi validada isoladamente: leitura/gravação local,
gravação atômica, backup/restauração, `arquivo_existe`,
`obter_data_modificacao`, concorrência (múltiplas threads gravando ao mesmo
tempo não corrompem o CSV) e fallback quando o armazenamento remoto está
indisponível.

## Restaurando um backup

- **Local**: `utils.csv_io.restaurar_backup("colaboradores")` (ou
  `"treinamentos"`, `"usuarios"`, `"logs"`) traz de volta o backup mais
  recente de `data/backups/`; um backup específico pode ser indicado via
  `caminho_backup=`.
- **Remoto**: mesma função — busca a cópia mais recente guardada na tabela
  `backups` do Supabase.

Em ambos os casos, o estado atual (antes da restauração) também vira
backup — a própria restauração é reversível.

## Limitações de concorrência

Cada gravação local é protegida por uma trava de arquivo simples (evita que
duas escritas simultâneas corrompam o CSV) e por escrita atômica
(arquivo temporário + substituição, nunca um CSV "pela metade"). `logs.csv`
usa inserção real (não relê/reescreve o arquivo inteiro a cada linha) —
no modo remoto isso é um `INSERT` de verdade no Postgres, sem risco de
conflito. O que **não** está coberto: o ciclo completo
"ler → decidir → gravar" de uma página não é atômico ponta a ponta — se
duas pessoas editarem o mesmo colaborador quase ao mesmo tempo, a segunda
gravação pode sobrescrever a primeira (comportamento "o último que salva,
vale"). Suficiente para o volume de uso interno atual; uma trava no nível
de negócio (não só de arquivo) ficaria pra uma iteração futura, se o volume
de uso justificar.

## Cuidado com dados pessoais

`data/` (CSVs reais, backups, downloads) está inteiramente no `.gitignore`
— nunca deve ir pro Git. Os CSVs reais contêm nome, CPF, e-mail e celular de
funcionários. Use `data_examples/*.example.csv` como referência de formato
sem dado real. Nunca cole conteúdo de `data/` em ferramentas externas
(chat, gist, pastebin) sem necessidade.

## Erros comuns

- **"Não foi possível conectar ao armazenamento de dados"**: Supabase fora
  do ar, projeto pausado (replana sozinho no próximo acesso, depois de
  ficar ~1 semana sem uso) ou credencial errada em Secrets. Nenhum dado é
  perdido — o sistema bloqueia a gravação até a conexão voltar, não grava
  "vazio" por cima do que já existe.
- **Automação de download não funciona no Streamlit Cloud**: esperado — não
  há suporte confiável a Chromium headless nesse ambiente. Use upload manual
  do `.xlsx` (continua funcionando normalmente na nuvem).
- **Aba "DTB Bridalub - Por Usuário (2)" não encontrada**: confira se o
  arquivo exportado tem essa aba com esse nome exato (note os dois espaços
  antes do "(2)" no nome real da aba — a validação já lida com isso, mas um
  arquivo de outra fonte pode não ter a aba de verdade).
