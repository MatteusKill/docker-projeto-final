# Projeto Final — Containerização Segura com Diferenciais

Aplicação web containerizada com PHP, Nginx, FastAPI e MySQL. A versão também
inclui Traefik, Redis, backup automático, Prometheus, Grafana, Portainer e um
teste de carga k6.

## Arquitetura

```text
Navegador
    |
    v
Traefik :8081                    Portainer :9443
    |                                |
    v                                v
  Nginx                        socket do Docker
    |---- .php ----> PHP-FPM
    |
    |---- /api/* -> FastAPI ----+----> Redis (cache)
                               |
                               +----> MySQL <---- Backup automático
                                                    |
                                                    v
                                                backups/

Prometheus <---- métricas do FastAPI e Traefik
    |
    v
Grafana :3000
```

Somente interfaces HTTP necessárias são publicadas, sempre em `127.0.0.1`.
MySQL, Redis, PHP-FPM e FastAPI não publicam portas no computador.
As redes `data`, `monitoring` e `management` são internas; a rede
`local-access` fornece gateway apenas às interfaces publicadas no host.

## Serviços

| Serviço | Responsabilidade | Persistência |
|---|---|---|
| `traefik` | entrada e proxy para o Nginx | logs em `logs/traefik` |
| `nginx` | arquivos web, PHP e proxy `/api` | logs em `logs/nginx` |
| `php` | renderização da página | não precisa |
| `backend` | API FastAPI e regras da aplicação | logs em `logs/backend` |
| `mysql` | dados permanentes | volume `mysql_data` |
| `redis` | cache temporário do total de visitas | não precisa |
| `backup` | dump periódico do MySQL | pasta `backups/` |
| `prometheus` | coleta e armazenamento de métricas | volume `prometheus_data` |
| `grafana` | dashboard das métricas | volume `grafana_data` |
| `portainer` | administração visual do Docker | volume `portainer_data` |
| `load-test` | teste k6 executado sob demanda | não precisa |

O serviço `load-test` usa um profile e não permanece rodando com a stack.

## Requisitos atendidos

| Requisito | Implementação |
|---|---|
| Dockerfiles otimizados | imagens próprias multi-stage ou mínimas |
| Docker Compose | serviços, redes, volumes e dependências |
| Banco persistente | volume nomeado `mysql_data` |
| Proxy reverso | Traefik na entrada e Nginx na aplicação |
| Banco não exposto | MySQL existe somente na rede interna `data` |
| Usuário não-root | imagens próprias e serviços compatíveis usam UID explícito |
| Healthchecks | serviços de execução contínua possuem verificação |
| Credenciais | `.env` ignorado pelo Git e criado com permissão `600` |
| Limites | CPU, memória e PIDs definidos por serviço |
| Logs | arquivos em `logs/` e rotação do driver Docker |
| Backup e restore | dump automático, dump manual e restore validado |
| Redis | cache com TTL e política LRU |
| Métricas | Prometheus e dashboard Grafana provisionado |
| Orquestração visual | Portainer CE |
| Teste de carga | cenário k6 com limites de erro e latência |

## Setup

Pré-requisitos:

- Docker Engine;
- Docker Compose v2;
- aproximadamente 2 GB de memória disponíveis;
- portas `8081`, `8082`, `3000`, `9090` e `9443` disponíveis.

Prepare o `.env`, as senhas e as pastas de logs:

```bash
./scripts/setup.sh
```

O script não sobrescreve credenciais existentes. Quando o projeto recebe uma
nova variável, ele adiciona somente a variável ausente. O `.env` fica com
permissão `600` e não é enviado ao Git.

## Execução e acessos

Construa e inicie os serviços permanentes:

```bash
docker compose up -d --build
docker compose ps
```

| Interface | Endereço |
|---|---|
| Aplicação | <http://localhost:8081> |
| Documentação FastAPI | <http://localhost:8081/api/docs> |
| Dashboard Traefik | <http://localhost:8082/dashboard/> |
| Grafana | <http://localhost:3000> |
| Prometheus | <http://localhost:9090> |
| Portainer | <https://localhost:9443> |

O usuário do Grafana e sua senha estão nas variáveis
`GRAFANA_ADMIN_USER` e `GRAFANA_ADMIN_PASSWORD` do `.env`.

No primeiro acesso ao Portainer, aceite o certificado local autoassinado, crie
o administrador e selecione o ambiente Docker local. O Portainer interrompe o
setup inicial após alguns minutos sem atividade; se isso ocorrer, reinicie-o:

```bash
docker compose restart portainer
```

Para parar sem apagar dados:

```bash
docker compose down
```

Não use `docker compose down --volumes` se quiser preservar MySQL, Prometheus,
Grafana e Portainer.

## Fluxo do proxy

```text
GET http://localhost:8081/api/visits
  → Traefik recebe na porta pública
  → Traefik encaminha ao Nginx
  → Nginx identifica /api e encaminha ao FastAPI
  → FastAPI procura o total no Redis
  → se houver cache: responde sem consultar o MySQL
  → se não houver: consulta MySQL, grava cache e responde
```

O dashboard do Traefik usa uma porta de gerenciamento separada. A configuração
está em `traefik/traefik.yml` e `traefik/dynamic.yml`; não é necessário montar
o socket do Docker no Traefik.

## Cache Redis

O Redis guarda somente `visits:total` durante 30 segundos. Ele é cache, não a
fonte definitiva dos dados. Ao registrar uma visita ou restaurar o banco, essa
chave é removida.

```text
GET: cache hit  → responde pelo Redis
GET: cache miss → consulta MySQL e preenche Redis
POST            → grava no MySQL e invalida Redis
```

Verifique o Redis:

```bash
docker compose exec redis sh -c \
  'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping'
```

Se o Redis falhar, o GET continua consultando o MySQL e o backend registra a
degradação nos logs.

## Prometheus e Grafana

O FastAPI publica `/metrics` apenas na rede de monitoramento. O Prometheus
consulta esse endpoint e as métricas internas do Traefik a cada 10 segundos.
O Grafana consulta o Prometheus e carrega automaticamente o dashboard
`Projeto Final - Aplicação`.

O dashboard mostra:

- disponibilidade dos alvos;
- requisições por rota;
- latência p95;
- hits, misses e erros do Redis;
- erros de acesso ao MySQL.

Confira os alvos do Prometheus em <http://localhost:9090/targets>. Todos devem
aparecer como `UP`.

## Portainer e risco do socket

O Portainer recebe `/var/run/docker.sock` para listar e administrar containers.
Quem controla o Portainer praticamente controla o Docker e pode afetar todo o
host. Por isso:

- a porta está limitada a `127.0.0.1`;
- o primeiro acesso exige criação de administrador;
- o volume `portainer_data` preserva a configuração;
- o painel não deve ser publicado na internet sem proteção adicional.

O mount `:ro` impede alteração do arquivo do socket, mas não transforma a API
do Docker em somente leitura; o Portainer continua podendo administrar o host.

## Teste de carga

Execute o teste sob demanda:

```bash
docker compose run --rm load-test
```

O cenário em `load-tests/load-test.js` sobe gradualmente até cinco usuários
virtuais, consulta a página e a API durante 25 segundos e falha se:

- mais de 1% das requisições falhar;
- menos de 99% das verificações passarem;
- a latência p95 ultrapassar 1 segundo.

Durante o teste, acompanhe o dashboard Grafana para visualizar tráfego, latência
e utilização do cache.

## Logs e saúde

Logs em arquivos:

```text
logs/traefik/access.log
logs/traefik/traefik.log
logs/nginx/access.log
logs/nginx/error.log
logs/backend/backend.log
```

Comandos operacionais:

```bash
docker compose ps
docker compose logs --tail=100 -f
curl --fail http://localhost:8081/health
docker stats --no-stream
```

Prontidão do backend e dependências:

```bash
docker compose exec backend python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"
```

## Backup automático e manual

O serviço `backup` cria um dump quando inicia e repete a cada 24 horas:

```text
backups/projeto_final_DATA_HORA.sql
```

O intervalo fica no `.env`:

```text
BACKUP_INTERVAL_SECONDS=86400
```

Confira a execução:

```bash
docker compose logs --tail=20 backup
ls -lh backups/
```

Para criar um dump adicional imediatamente:

```bash
./scripts/backup.sh
```

Os arquivos antigos não são apagados automaticamente. Monitore o espaço em
disco e copie backups importantes para outro equipamento.

## Restore

O restore sobrescreve dados. Crie um backup atual e então execute:

```bash
./scripts/restore.sh backups/projeto_final_DATA_HORA.sql
```

O script valida o arquivo, pede confirmação, pausa o backend, importa o dump,
invalida o cache Redis e inicia o backend novamente.

## Troubleshooting

| Problema | Verificação | Solução |
|---|---|---|
| variável obrigatória ausente | `docker compose config` | execute novamente `./scripts/setup.sh` |
| porta ocupada | erro `port is already allocated` | altere a porta correspondente no `.env` |
| serviço `unhealthy` | `docker compose ps` | use `docker compose logs SERVICO` |
| Traefik retorna 502/503 | logs de Traefik e Nginx | confira `nginx` e `backend` |
| alvo Prometheus `DOWN` | página `/targets` | confira rede e endpoint `/metrics` |
| Grafana sem dados | fonte Prometheus | aguarde duas coletas e confira `/targets` |
| Redis indisponível | logs de Redis/backend | confira senha e healthcheck |
| Portainer mostra timeout | logs do Portainer | `docker compose restart portainer` |
| backup falha | logs do serviço `backup` | confirme que MySQL está saudável |
| falta memória | `docker stats` | pare serviços ou aumente recursos do Docker |

Valide o Compose sem iniciar containers:

```bash
docker compose config --quiet
```

## Rollback

Antes de uma atualização:

```bash
git tag v1.0.0
./scripts/backup.sh
```

Para voltar ao código de uma tag e reconstruir:

```bash
git switch --detach v1.0.0
docker compose up -d --build
```

Os volumes permanecem, mas uma versão antiga pode não entender dados alterados
por uma versão nova. Nesse caso, restaure também o dump compatível. O restore
remove dados criados depois daquele backup.

## Limitações

- ambiente local sem certificado HTTPS público;
- Traefik Dashboard e Prometheus não possuem login, mas escutam apenas no host;
- Portainer possui acesso altamente privilegiado ao Docker;
- backups permanecem no mesmo computador;
- `.env` atende ao projeto acadêmico, mas não substitui um secret manager;
- aplicação usa criação automática de tabela, sem migrations;
- monitoramento não inclui logs centralizados nem alertas;
- execução em um único host, sem alta disponibilidade.

## Referências oficiais

- [Traefik — configuração por arquivo](https://doc.traefik.io/traefik/reference/dynamic-configuration/file/)
- [Prometheus — execução com Docker](https://prometheus.io/docs/prometheus/latest/installation/)
- [Grafana — provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [Portainer CE — Docker Standalone](https://docs.portainer.io/2.33-lts/start/install-ce/server/docker/linux)
- [Grafana k6 — execução de testes](https://grafana.com/docs/k6/latest/get-started/running-k6/)
