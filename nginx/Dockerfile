FROM nginxinc/nginx-unprivileged:1.27.5-alpine3.21

COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --chown=101:101 php/src/ /var/www/html/

USER 101

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
