FROM php:8.3.20-fpm-alpine3.21

COPY php/php.ini /usr/local/etc/php/conf.d/app.ini
COPY php/www.conf /usr/local/etc/php-fpm.d/zz-app.conf
COPY --chown=www-data:www-data php/src/ /var/www/html/

WORKDIR /var/www/html
USER www-data

EXPOSE 9000

CMD ["php-fpm", "--nodaemonize"]
