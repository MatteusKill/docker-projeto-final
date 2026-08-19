#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_ROOT"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "Erro: Docker e Docker Compose v2 são obrigatórios." >&2
    exit 1
fi

generate_secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 24
    else
        od -An -N24 -tx1 /dev/urandom | tr -d ' \n'
    fi
}

ensure_setting() {
    key=$1
    value=$2
    if ! grep -q "^${key}=" .env; then
        printf '%s=%s\n' "$key" "$value" >> .env
        echo "Configuração $key adicionada ao .env existente."
    fi
}

ensure_secret() {
    key=$1
    if ! grep -q "^${key}=" .env; then
        printf '%s=%s\n' "$key" "$(generate_secret)" >> .env
        echo "Credencial $key adicionada ao .env existente."
    fi
}

if [ ! -f .env ]; then
    umask 077
    mysql_password=$(generate_secret)
    mysql_root_password=$(generate_secret)
    redis_password=$(generate_secret)
    grafana_password=$(generate_secret)

    {
        printf '%s\n' "APP_PORT=8081"
        printf '%s\n' "TRAEFIK_DASHBOARD_PORT=8082"
        printf '%s\n' "APP_VERSION=dev"
        printf '%s\n' "LOCAL_UID=$(id -u)"
        printf '%s\n' "LOCAL_GID=$(id -g)"
        printf '\n'
        printf '%s\n' "MYSQL_DATABASE=projeto_final"
        printf '%s\n' "MYSQL_USER=projeto_final_user"
        printf '%s\n' "MYSQL_PASSWORD=$mysql_password"
        printf '%s\n' "MYSQL_ROOT_PASSWORD=$mysql_root_password"
        printf '\n'
        printf '%s\n' "REDIS_PASSWORD=$redis_password"
        printf '%s\n' "CACHE_TTL_SECONDS=30"
        printf '\n'
        printf '%s\n' "PROMETHEUS_PORT=9090"
        printf '%s\n' "GRAFANA_PORT=3000"
        printf '%s\n' "GRAFANA_ADMIN_USER=admin"
        printf '%s\n' "GRAFANA_ADMIN_PASSWORD=$grafana_password"
        printf '%s\n' "PORTAINER_PORT=9443"
        printf '\n'
        printf '%s\n' "BACKUP_INTERVAL_SECONDS=86400"
    } > .env
    chmod 600 .env
    echo "Arquivo .env criado com senhas aleatórias."
else
    chmod 600 .env
    echo "Arquivo .env existente preservado."
fi

umask 077
ensure_setting TRAEFIK_DASHBOARD_PORT 8082
ensure_secret REDIS_PASSWORD
ensure_setting CACHE_TTL_SECONDS 30
ensure_setting PROMETHEUS_PORT 9090
ensure_setting GRAFANA_PORT 3000
ensure_setting GRAFANA_ADMIN_USER admin
ensure_secret GRAFANA_ADMIN_PASSWORD
ensure_setting PORTAINER_PORT 9443
ensure_setting BACKUP_INTERVAL_SECONDS 86400

mkdir -p logs/nginx logs/backend logs/traefik backups
chmod 750 logs logs/nginx logs/backend logs/traefik backups

docker compose config --quiet
echo "Configuração válida."
