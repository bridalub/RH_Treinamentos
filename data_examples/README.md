# Dados de exemplo

Arquivos com o mesmo cabeçalho dos CSVs reais (`data/*.csv`), mas com dados
fictícios — só pra quem estiver configurando o projeto do zero entender o
formato esperado, sem precisar de nenhum dado real de RH.

`data/` inteiro está no `.gitignore` (nunca vai pro Git); esta pasta,
`data_examples/`, é versionada normalmente.

Para usar como ponto de partida local:

```
cp data_examples/colaboradores.example.csv data/colaboradores.csv
cp data_examples/treinamentos.example.csv data/treinamentos.csv
cp data_examples/usuarios.example.csv data/usuarios.csv
cp data_examples/logs.example.csv data/logs.csv
```

O usuário de exemplo em `usuarios.example.csv` é `admin` com senha
`exemplo123` — **troque essa senha assim que logar**, ela está aqui só pra
demonstrar o formato do hash (`salt$hash`, PBKDF2-SHA256), nunca use em
produção. Em uso normal do sistema, o próprio `admin` já é criado
automaticamente na primeira execução (ver `ADMIN_SENHA_PADRAO` em
`.streamlit/secrets.toml.example`) — normalmente você não precisa copiar
`usuarios.example.csv` manualmente.
