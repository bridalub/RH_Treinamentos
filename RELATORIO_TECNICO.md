# Relatório Técnico — Sistema de Treinamentos BRIDA

Análise das duas planilhas-fonte, realizada diretamente nos arquivos reais encontrados na pasta do projeto (não em suposições):

- `Cópia de BASE FUNCIONÁRIOS BRIDA_23_07.xls`
- `DTB_Bridalub_-_Por_Usuário_-_20260727_06_58_58_PM.xlsx`

---

## 1. Estrutura completa das duas planilhas

### 1.1 `BASE FUNCIONÁRIOS BRIDA` (.xls)

Uma única aba: **`BASE COMERCIAL`** — 120 linhas de dados, 6 colunas.

| Coluna | Tipo observado | Preenchimento |
|---|---|---|
| EQUIPE | número (1 a 15, pula o 8) | 119/120 |
| COLABORADOR | texto | 120/120 |
| E-MAIL | texto | 113/120 |
| CELULAR | texto | 113/120 |
| HORÁRIO DE TRABALHO | texto (ex.: "08H ÀS 18H - 1H15 ALMOÇO") | 113/120 |
| CARGO | texto (COORDENADOR, GERENTE, SUPORTE, EXTERNO, INTERNA) | 113/120 |

**Não existem** nesta planilha: CPF, matrícula, data de admissão, data de nascimento, gênero, PCD, situação de afastamento/férias, gestor separado do coordenador de equipe, e-mail corporativo formal separado, etc. As imagens de referência enviadas (perfil de colaborador e dashboard executivo) servem **apenas como inspiração visual/layout**, conforme instruído — não representam colunas realmente disponíveis. O sistema só pode exibir/derivar o que existe nesta planilha.

### 1.2 `DTB Bridalub - Por Usuário` (.xlsx)

Três abas:

| Aba (nome real no arquivo) | Conteúdo |
|---|---|
| `DTB Bridalub - Por Usuário -` | **Vazia** (0 linhas) — artefato do export |
| `DTB Bridalub - Por Usuário  (3)` | **Resumo/pivot** por pessoa: colunas Completo, Concluído (Equivalente), Em Andamento, Em Andamento/Vencido, Não Iniciada, Registrado, Reprovado (contagens). 50 linhas. |
| `DTB Bridalub - Por Usuário  (2)` | **Fonte oficial** (granular, um registro por treinamento por pessoa). 8 linhas de metadados do relatório + cabeçalho na linha 9 + 422 linhas de dados. |

⚠️ **Atenção**: o nome real da aba tem **dois espaços** antes de "(2)" (`"...Usuário  (2)"`), não um espaço como no texto da instrução. A validação de existência da aba precisa normalizar espaços (`re.sub(r'\s+', ' ', nome).strip()`) antes de comparar, senão a aba nunca será encontrada.

Cabeçalho real da aba `(2)` (linha 9 do arquivo bruto), 15 colunas:

`Distribuidor, Nome, CPF, Título do Treinamento, Status da Minha Formação, Data de Inscrição da Minha Formação, Data de Conclusão da Minha Formação, DTB Líder, DTB Área, DTB LOB, DTB Cargo, DTB Data Desligamento, Última Data de Contratação do Usuário, Último Acesso do Usuário, Tipo de Treino`

Granularidade: **1 linha = 1 treinamento de 1 pessoa** (chave natural = Nome + Título do Treinamento). É a fonte correta para tudo — status, datas, treinamento por treinamento.

⚠️ **Achado crítico de qualidade de dados**: o bloco de metadados da própria aba diz `Contagem de Registros: 5158`, mas a aba exportada contém apenas **422 linhas de dados**, cobrindo somente **18 pessoas únicas** (de ~112 colaboradores reais). Ou seja, o export atual é uma amostra parcial/filtrada do relatório completo, não o relatório inteiro. O sistema deve comparar a "Contagem de Registros" declarada com a quantidade de linhas realmente lidas e **alertar visivelmente o usuário** quando forem diferentes, para não passar a falsa impressão de que os dashboards refletem 100% da base.

---

## 2. Relação de colunas — uso pelo sistema

### colaboradores.csv (a partir de BASE COMERCIAL)

| Coluna origem | Usada? | Observação |
|---|---|---|
| EQUIPE | Sim | vira `equipe_id` |
| COLABORADOR | Sim | nome original (exibição) + versão normalizada (matching) |
| E-MAIL | Sim | contato |
| CELULAR | Sim | contato |
| HORÁRIO DE TRABALHO | Sim | ficha do colaborador |
| CARGO | Sim | categoria (COORDENADOR/GERENTE/SUPORTE/EXTERNO/INTERNA) |

Campos derivados (não existem na planilha, calculados pelo sistema): `nome_normalizado`, `gestor` (colaborador com CARGO em {COORDENADOR, GERENTE} da mesma EQUIPE), `is_pessoa_valida` (falso para as linhas-cabeçalho de divisão, ver seção 5).

### treinamentos.csv (a partir da aba `(2)`)

Todas as 15 colunas são mantidas (renomeadas para snake_case). Acrescenta-se: `nome_normalizado`, `situacao_relacionamento` (RELACIONADO_AUTOMATICO / REVISAO_MANUAL / NAO_ENCONTRADO), `nome_colaborador_relacionado` (nome oficial do colaborador quando houver match).

---

## 3. Estratégia de relacionamento entre as bases

Relacionamento é feito **exclusivamente por nome**, nunca por CPF (o CPF só existe hoje na planilha de treinamentos; a de colaboradores não tem essa coluna — logo, hoje, CPF nem estaria disponível como critério, mesmo que fosse permitido).

### 3.1 Normalização (`normalizar_nome`)

1. Maiúsculo.
2. Remove conteúdo entre parênteses (`(B2C)`, `(KA)`, `(INT)`, `(SUP)` — tags de papel, não fazem parte do nome).
3. Remove acentos (NFKD + strip de combining marks) — ex.: `ÉRIKA` → `ERIKA`.
4. Remove tudo que não for letra/espaço (remove `-`, `/`, pontuação).
5. Colapsa espaços múltiplos, `strip()`.
6. Nome original é preservado em campo separado, só para exibição.

### 3.2 Ordem do algoritmo (por pessoa da planilha de treinamentos, contra a lista de colaboradores)

1. **Exata**: nome normalizado igual, byte a byte.
2. **Completo × abreviado**: os tokens de um nome são um prefixo ordenado dos tokens do outro (ex.: colaboradores tem `GABRIEL DI POLLI`, treinamentos tem `GABRIEL DI POLLI MACHADO QUEIROZ` → primeiro é prefixo do segundo).
3. **Primeiro nome + último sobrenome**: primeiro token e último token iguais nos dois lados (ex.: `EMERSON BEZERRA CAVALCANTE` × `EMERSON CAVALCANTE`; `INGRID MARQUES` × `INGRID TEIXEIRA MARQUES`).
4. **Nomes intermediários**: mesmo primeiro token + interseção de pelo menos um token do meio/sobrenome, quando 1-3 não resolveram.
5. Se **mais de um colaborador** satisfizer qualquer critério acima (ambiguidade), **não relaciona automaticamente** → vai para fila de **Revisão Manual**.
6. Se **nenhum** colaborador satisfizer nenhum critério → **"Nome não encontrado"**.

CPF, quando existir dos dois lados no futuro, é usado só como **informação complementar exibida na tela de revisão** (nunca decide o match sozinho).

### 3.3 Casos reais encontrados nesta base (evidência concreta, não hipotética)

| Nome em Treinamentos | Nome em Colaboradores | Resultado esperado |
|---|---|---|
| EMERSON BEZERRA CAVALCANTE | EMERSON CAVALCANTE | Automático (regra 3) |
| FABIO MUNIZ SOARES | FABIO SOARES | Automático (regra 3) |
| INGRID MARQUES | INGRID TEIXEIRA MARQUES | Automático (regra 3) |
| ÉRIKA GIMENES DA SILVA | ERIKA SILVA | Automático (regra 3) |
| GABRIEL DI POLLI MACHADO QUEIROZ | GABRIEL DI POLLI | Automático (regra 2, prefixo) |
| JULIANA DUARTE COSTA GUIDETTI | JULIANA DUARTE COSTA | Automático (regra 2, prefixo) |
| **CRISTINA DA SILVA ROCHA** | **CRIS SILVA ROCHA** | **Revisão manual** — "CRIS" é apelido, não abreviação/prefixo determinístico de "CRISTINA" (poderia ser apelido de outro nome também); não deve ser resolvido automaticamente. |
| **EDUARDO SOUSA DA SILVA** | **EDURADO SOUSA** (sic) | **Revisão manual** — erro de digitação na planilha de origem ("EDURADO"); nenhuma regra determinística cobre erro de digitação com segurança. |
| **IVANILDO ALVES DO CARMO** | *(não existe em Colaboradores)* | **"Nome não encontrado"** |

---

## 4. Casos de nomes iguais, abreviados ou inconsistentes

- **Pessoa com múltiplas linhas em Colaboradores**: pessoal de suporte compartilhado entre equipes aparece repetido (ex.: `BEATRIZ OLIVEIRA` em 3 equipes, `GABRIEL DI POLLI` em 3 equipes, `GABRIELLE ROCHA - JAIANE DOS SANTOS` em 3 equipes, `MAYARA LISBOA` e `JESSICA SANTANA` em 2 equipes cada). Não é erro — é a mesma pessoa dando suporte a times diferentes. O matching deve deduplicar pelo nome normalizado (uma pessoa = um registro canônico), e a tela de Equipes deve listar essa pessoa sob cada gestor que ela atende.
- **Sufixos de papel entre parênteses**: `(B2C)`, `(KA)`, `(INT)`, `(SUP)` — removidos na normalização, mas guardados como metadado opcional.
- **Sufixo "- REALOCADO"**: ex.: `DAIANE CARRASCO - REALOCADO`, `ELTON VIEIRA - REALOCADO`, `TAMARA SANTOS - REALOCADO`. Também existe a versão sem sufixo (`DAIANE CARRASCO`, `ELTON VIEIRA`, `TAMARA SANTOS`) em outra equipe — são a mesma pessoa remanejada, mas hoje aparecem como duas linhas físicas na planilha (equipes diferentes). Normalização remove "REALOCADO", o que faz as duas linhas colidirem no nome normalizado — tratado como a mesma pessoa, presente em duas equipes.
- **Duas pessoas em uma única célula** (defeito real da planilha, não pode ser corrigido automaticamente com segurança):
  - `GABRIELLE ROCHA - JAIANE DOS SANTOS`
  - `RAFAEL PEDRESCHI E JORGE IAMAMURA`
  Como o separador não é padronizado (uma usa " - ", outra usa " E "), o sistema **não tenta dividir automaticamente** — mantém como está e deixa a cargo do RH corrigir na origem; na prática, essas células nunca vão dar match com um nome real de treinamentos, o que é o comportamento correto (cairiam em "revisão manual" apenas se por acaso colidirem parcialmente com algum nome, senão ficam simplesmente sem treinamentos vinculados).
- **Linhas que não são pessoas** (cabeçalhos de subdivisão dentro da planilha, sem e-mail/cargo/celular): `CONCESSIONÁRIA`, `ARLA`, `B2B INSIDE SALES`, `B2B FROTAS`, `B2B INDÚSTRIA`, `POSTOS` (6 linhas) — marcadas com `is_pessoa_valida = False` e excluídas de contagens/dashboards, mas mantidas no CSV para rastreabilidade (não altera a estrutura original da planilha-fonte, só como for lida).
- **Espaços/typos**: `CARGO` com espaço sobrando (`"SUPORTE "` vs `"SUPORTE"`, `"INTERNA "`), nomes com espaço duplo (`"JONATHAN  DOS SANTOS DE FRANÇA"`), nomes com espaço à direita. Tratado por `strip()` + colapso de espaços em todos os campos de texto na importação, não só no nome.

---

## 5. Possíveis problemas de qualidade dos dados (resumo consolidado)

1. Export de treinamentos parcial (422 de 5158 registros declarados) — ver seção 1.2.
2. Aba `(2)` tem nome com espaçamento diferente do especificado — precisa de matching tolerante.
3. Erro de digitação em nome de colaborador (`EDURADO` → `EDUARDO`).
4. Duas pessoas somadas em uma célula (2 ocorrências).
5. 6 linhas de "cabeçalho de subdivisão" misturadas no meio da lista de colaboradores.
6. 1 colaborador sem EQUIPE atribuída (`RAFAEL PEDRESCHI E JORGE IAMAMURA`).
7. Pessoal de suporte duplicado entre equipes (esperado, não é bug, mas precisa dedupe na hora de contar "total de colaboradores").
8. `Status da Minha Formação` na aba oficial usa só 5 valores (`Completo, Em Andamento, Em Andamento/Vencido, Não Iniciada, Registrado`); os valores `Concluído (Equivalente)` e `Reprovado` só aparecem no resumo `(3)`, reforçando que `(3)` não deve alimentar o sistema (taxonomia diferente/desatualizada).
9. `DTB Cargo` (vindo da plataforma de treinamento: SUPORTE/VENDEDOR) não bate com o vocabulário de `CARGO` em Colaboradores (COORDENADOR/GERENTE/SUPORTE/EXTERNO/INTERNA) — os dois campos são mantidos separados, sem tentar unificar.

---

## 6. Modelo final dos 4 CSVs

### `colaboradores.csv`
```
colaborador_id, nome, nome_normalizado, equipe_id, cargo, email, celular,
horario_trabalho, gestor_nome, is_pessoa_valida, atualizado_em
```

### `treinamentos.csv`
```
treinamento_id, nome_colaborador_planilha, nome_normalizado, cpf,
titulo_treinamento, status, data_inscricao, data_conclusao,
dtb_lider, dtb_area, dtb_lob, dtb_cargo, dtb_data_desligamento,
data_contratacao, ultimo_acesso, tipo_treino,
situacao_relacionamento, colaborador_id_relacionado, nome_colaborador_relacionado,
importado_em
```

### `usuarios.csv`
```
usuario_id, login, nome, senha_hash, perfil, ativo, criado_em, ultimo_login
```

### `logs.csv`
```
log_id, data_hora, usuario, acao, detalhes
```

---

## 7. Fluxo completo da importação

1. RH aciona "Atualizar" (Playwright, `app.py`) ou faz upload manual do `.xlsx`.
2. Sistema abre o arquivo, localiza a aba cujo nome — após normalizar espaços — é igual a `"DTB Bridalub - Por Usuário (2)"`. Se não encontrar → **interrompe a importação** e mostra mensagem clara ao usuário.
3. Lê o bloco de metadados (linhas 1-6) para extrair `Contagem de Registros` declarada.
4. Localiza a linha de cabeçalho real (linha com `"Distribuidor"` na primeira coluna) e lê os dados a partir dali.
5. Compara total de linhas lidas × `Contagem de Registros` declarada; se diferente, gera aviso (não bloqueia, mas fica visível na tela de Atualização e registrado em log).
6. Faz **backup** do `treinamentos.csv` atual (timestamp) antes de qualquer gravação.
7. Normaliza nomes, roda o algoritmo de relacionamento (seção 3) contra `colaboradores.csv`.
8. Classifica cada linha: novo registro / registro atualizado (mesma chave Nome+Treinamento, dado mudou) / inalterado.
9. Grava `treinamentos.csv`, grava `logs.csv` com o resumo (novos, atualizados, relacionados automaticamente, pendentes de revisão, não encontrados).
10. Tela de Atualização exibe a ListView + link para a área de Revisão de Correspondências.

## 8. Fluxo completo do relacionamento

1. Para cada nome único em `treinamentos.csv`, aplica `normalizar_nome`.
2. Roda as regras 1→4 da seção 3.2, nessa ordem, parando na primeira que resolver sem ambiguidade.
3. Grava resultado em `situacao_relacionamento` (RELACIONADO_AUTOMATICO / REVISAO_MANUAL / NAO_ENCONTRADO) + `colaborador_id_relacionado`.
4. Casos `REVISAO_MANUAL` e `NAO_ENCONTRADO` aparecem na tela "Revisão de Correspondências", onde o RH escolhe manualmente o colaborador correto (ou confirma "não é ninguém da base"); a decisão manual é persistida e passa a valer como override permanente para aquele nome de planilha nas próximas importações.

## 9. Arquitetura do projeto

```
app.py                      # ponto de entrada Streamlit (login + roteamento)
automations/
  atualizar_treinamentos.py # script Playwright (existente, referências.py será substituído)
pages_app/
  dashboard.py
  atualizacao.py
  colaboradores.py
  equipes.py
  analises.py
  usuarios.py
  logs.py
services/
  colaboradores_service.py  # CRUD sobre colaboradores.csv
  treinamentos_service.py   # CRUD + importação sobre treinamentos.csv
  usuarios_service.py       # auth, CRUD usuarios.csv
  logs_service.py           # append/consulta logs.csv
  matching_service.py       # normalização + algoritmo de relacionamento
utils/
  auth.py                   # hash de senha, sessão
  normalizacao.py           # normalizar_nome, normalizar_texto
  csv_io.py                 # leitura/escrita segura + backup automático
  excel_import.py           # leitura da planilha DTB (validação de aba, metadados)
components/
  cards.py, tables.py, charts.py, theme.py   # componentes reutilizáveis de UI
data/
  colaboradores.csv, treinamentos.csv, usuarios.csv, logs.csv
  backups/
```

Nenhum banco de dados, nenhuma dependência além de Python + Streamlit + Pandas + Plotly (+ Playwright, já usado no `app.py` original, apenas para a automação de coleta).

---

## 10. Próximos passos

Implementação incremental, validando cada etapa:

1. Utilitários base (`normalizacao.py`, `csv_io.py`, `excel_import.py`) + `matching_service.py` com testes usando os casos reais da seção 3.3.
2. Geração inicial de `colaboradores.csv` a partir da planilha (rodar e conferir os 120 registros).
3. Importação de `treinamentos.csv` a partir da aba `(2)` + relacionamento.
4. Autenticação + `usuarios.csv` + `logs.csv`.
5. Telas, na ordem: Login → Dashboard → Atualização (+ Revisão de Correspondências) → Colaboradores → Equipes → Análises → Usuários → Logs.
6. Tema visual dark BRIDA aplicado a todos os componentes.
