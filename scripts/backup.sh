#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_ROOT"

if [ ! -f .env ]; then
    echo "Erro: execute ./scripts/setup.sh primeiro." >&2
    exit 1
fi

database_name=$(awk -F= '$1 == "MYSQL_DATABASE" { print substr($0, index($0, "=") + 1) }' .env)
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_file="backups/${database_name}_${timestamp}.sql"
temporary_file="${backup_file}.tmp"

mkdir -p backups
umask 077

echo "Criando backup em $backup_file"
if docker compose exec -T mysql sh -c \
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump --host=127.0.0.1 --user=root --single-transaction --quick --no-tablespaces "$MYSQL_DATABASE"' \
    > "$temporary_file"; then
    mv "$temporary_file" "$backup_file"
    chmod 600 "$backup_file"
    echo "Backup concluído."
else
    rm -f "$temporary_file"
    echo "Falha ao criar backup." >&2
    exit 1
fi
