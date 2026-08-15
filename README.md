# Projeto Final — Containerização Básica e Segura

Aplicação mínima com quatro serviços:

- Nginx como servidor HTTP e proxy reverso;
- PHP-FPM para renderizar a página;
- FastAPI como backend;
- MySQL como banco persistente.

Não foram adicionados os diferenciais Redis, Traefik, Grafana, Prometheus,
Portainer ou PHPMyAdmin.

## Arquitetura

```text
Navegador
    |
    | http://localhost:8081
    v
  Nginx
    |---- arquivos .php ----> PHP-FPM
    |
    |---- /api/* -----------> FastAPI
                                  |
                                  v
                                MySQL
```

Somente o Nginx publica uma porta. O MySQL existe apenas na rede interna
`data`.

## Requisitos atendidos

| Requisito | Implementação |
|---|---|
| Dockerfiles | imagens próprias para Nginx, PHP e FastAPI |
| Docker Compose | quatro serviços e duas redes |
| Banco persistente | volume nomeado `mysql_data` |
| Proxy reverso | Nginx encaminha `/api/*` ao FastAPI |
| Banco não exposto | MySQL não possui `ports` |
| Usuário não-root | usuários explícitos nas imagens e no Compose |
| Healthchecks | Nginx, PHP, FastAPI e MySQL |
| Credenciais | `.env` local, ignorado pelo Git e com permissão 600 |
| Limites | CPU, memória e PIDs por serviço |
| Logs | `logs/nginx` e `logs/backend` |
| Backup e restore | scripts manuais em `scripts/` |
| Monitoramento mínimo | healthchecks, logs e `docker stats` |

## Estrutura principal

```text
backend/
  app/main.py          API e acesso ao MySQL
  Dockerfile
  requirements.txt

nginx/
  Dockerfile
  default.conf         rotas PHP e /api

php/
  src/index.php        página da aplicação
  Dockerfile
  php.ini
  www.conf

scripts/
  setup.sh
  backup.sh
  restore.sh

docker-compose.yml
```

## Setup

Pré-requisitos:

- Docker Engine;
- Docker Compose v2;
- portas locais disponíveis.

Crie o `.env`, as senhas e os diretórios:

```bash
./scripts/setup.sh
```

O script cria senhas aleatórias e salva o `.env` com permissão 600. Se o
arquivo já existir, ele não será sobrescrito.

## Execução

Construa e inicie:

```bash
docker compose up -d --build
```

Confira os healthchecks:

```bash
docker compose ps
```

Acesse:

- aplicação: <http://localhost:8081>
- documentação da API: <http://localhost:8081/api/docs>

Para parar sem apagar o banco:

```bash
docker compose down
```

Não use `docker compose down --volumes` se quiser preservar os dados.

## Fluxo da aplicação

Ao abrir a página:

```text
Nginx recebe GET /
  → encontra index.php
  → encaminha para PHP-FPM
  → PHP gera HTML
```

Ao consultar visitas:

```text
Navegador chama GET /api/visits
  → Nginx encaminha ao FastAPI
  → FastAPI executa COUNT no MySQL
  → resposta volta ao navegador
```

Ao registrar uma visita:

```text
Navegador chama POST /api/visits
  → FastAPI insere uma linha no MySQL
  → transação é confirmada
```

## Logs e saúde

Logs em arquivo:

```text
logs/nginx/access.log
logs/nginx/error.log
logs/backend/backend.log
```

Logs agregados:

```bash
docker compose logs --tail=100 -f
```

Estado:

```bash
docker compose ps
curl --fail http://localhost:8081/health
docker stats --no-stream
```

O endpoint `/health` público verifica o Nginx. A prontidão do backend e do
banco pode ser verificada dentro do container:

```bash
docker compose exec backend python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"
```

## Backup

O volume mantém dados entre recriações do container, mas não substitui backup.

Crie um dump:

```bash
./scripts/backup.sh
```

O arquivo será salvo em:

```text
backups/projeto_final_DATA_HORA.sql
```

Confirme que o arquivo existe e não está vazio:

```bash
ls -lh backups/
```

## Restore

O restore sobrescreve tabelas e dados do banco. Faça um backup atual antes.

```bash
./scripts/restore.sh backups/projeto_final_DATA_HORA.sql
```

O script:

1. valida se o arquivo está dentro de `backups/`;
2. pede confirmação;
3. pausa o FastAPI;
4. importa o dump no MySQL;
5. inicia o FastAPI novamente.

## Troubleshooting

| Problema | Verificação | Solução |
|---|---|---|
| variável obrigatória ausente | `docker compose config` | execute `./scripts/setup.sh` |
| porta 8081 ocupada | erro `port is already allocated` | altere `APP_PORT` no `.env` |
| serviço `unhealthy` | `docker compose ps` | consulte `docker compose logs SERVICO` |
| backend retorna 503 | logs do backend/MySQL | confirme que o MySQL está saudável |
| logs sem permissão | permissões de `logs/` | execute o setup com o usuário que opera Docker |
| backup falha | estado do MySQL | confirme que o serviço está rodando e saudável |

Valide a estrutura do Compose:

```bash
docker compose config --quiet
```

## Rollback

Antes de uma nova versão, crie um tag Git e um backup:

```bash
git tag v1.0.0
./scripts/backup.sh
```

Para voltar o código, selecione a versão anterior e reconstrua as imagens:

```bash
git switch --detach v1.0.0
docker compose up -d --build
```

Se a versão alterou dados de forma incompatível, restaure também um dump
anterior. Restore pode perder dados criados depois do backup e deve ser uma
decisão consciente.

## Limites desta versão

- não possui HTTPS;
- não possui autenticação;
- o backup permanece no mesmo computador;
- usa `.env`, adequado ao requisito acadêmico, mas não um secret manager;
- cria a tabela automaticamente, sem migrations;
- roda em um único host;
- não possui cache, dashboard ou teste de carga.
