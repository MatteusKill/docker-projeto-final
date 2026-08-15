#!/bin/sh
set -eu

interval=${BACKUP_INTERVAL_SECONDS:-86400}
retry_interval=${BACKUP_RETRY_SECONDS:-60}

case "$interval:$retry_interval" in
    *[!0-9:]* | *::* | :* | *:)
        echo "Erro: os intervalos de backup devem ser números inteiros." >&2
        exit 1
        ;;
esac

if [ "$interval" -lt 60 ] || [ "$retry_interval" -lt 10 ]; then
    echo "Erro: use pelo menos 60s entre backups e 10s entre tentativas." >&2
    exit 1
fi

mkdir -p /backups
umask 077

while true; do
    timestamp=$(date -u +%Y%m%dT%H%M%SZ)
    backup_file="/backups/${MYSQL_DATABASE}_${timestamp}.sql"
    temporary_file="${backup_file}.tmp"

    echo "Iniciando backup automático: $backup_file"
    if MYSQL_PWD="$MYSQL_PASSWORD" mysqldump \
        --host="$MYSQL_HOST" \
        --user="$MYSQL_USER" \
        --single-transaction \
        --quick \
        --no-tablespaces \
        "$MYSQL_DATABASE" > "$temporary_file"; then
        mv "$temporary_file" "$backup_file"
        chmod 600 "$backup_file"
        printf '%s\n' "$timestamp" > /backups/.last-success
        echo "Backup automático concluído. Próximo em ${interval}s."
        sleep "$interval"
    else
        rm -f "$temporary_file"
        echo "Falha no backup. Nova tentativa em ${retry_interval}s." >&2
        sleep "$retry_interval"
    fi
done
