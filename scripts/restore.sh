#!/bin/sh
set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Uso: $0 backups/arquivo.sql [--yes]" >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_ROOT"

if [ ! -f .env ]; then
    echo "Erro: execute ./scripts/setup.sh primeiro." >&2
    exit 1
fi

backup_file=$(realpath "$1")
backup_directory=$(realpath backups)

case "$backup_file" in
    "$backup_directory"/*.sql) ;;
    *)
        echo "Erro: informe um arquivo .sql dentro de backups/." >&2
        exit 1
        ;;
esac

if [ ! -r "$backup_file" ]; then
    echo "Erro: backup não encontrado ou sem leitura." >&2
    exit 1
fi

database_name=$(awk -F= '$1 == "MYSQL_DATABASE" { print substr($0, index($0, "=") + 1) }' .env)

if [ "${2:-}" != "--yes" ]; then
    printf 'O banco %s será sobrescrito. Digite o nome do banco para confirmar: ' "$database_name"
    read -r confirmation
    if [ "$confirmation" != "$database_name" ]; then
        echo "Restore cancelado."
        exit 1
    fi
fi

backend_stopped=false
restart_backend() {
    if [ "$backend_stopped" = "true" ]; then
        docker compose start backend >/dev/null
    fi
}
trap restart_backend 0 INT TERM

docker compose stop backend
backend_stopped=true

docker compose exec -T mysql sh -c \
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --host=127.0.0.1 --user=root "$MYSQL_DATABASE"' \
    < "$backup_file"

docker compose start backend >/dev/null
backend_stopped=false
trap - 0 INT TERM
echo "Restore concluído."
