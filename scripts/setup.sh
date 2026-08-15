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

if [ ! -f .env ]; then
    umask 077
    mysql_password=$(generate_secret)
    mysql_root_password=$(generate_secret)

    {
        printf '%s\n' "APP_PORT=8081"
        printf '%s\n' "APP_VERSION=dev"
        printf '%s\n' "LOCAL_UID=$(id -u)"
        printf '%s\n' "LOCAL_GID=$(id -g)"
        printf '\n'
        printf '%s\n' "MYSQL_DATABASE=projeto_final"
        printf '%s\n' "MYSQL_USER=projeto_final_user"
        printf '%s\n' "MYSQL_PASSWORD=$mysql_password"
        printf '%s\n' "MYSQL_ROOT_PASSWORD=$mysql_root_password"
        printf '\n'
        printf '%s\n' "BACKUP_INTERVAL_SECONDS=86400"
    } > .env
    chmod 600 .env
    echo "Arquivo .env criado com senhas aleatórias."
else
    chmod 600 .env
    echo "Arquivo .env existente preservado."
fi

mkdir -p logs/nginx logs/backend backups
chmod 750 logs logs/nginx logs/backend backups

docker compose config --quiet
echo "Configuração válida."
