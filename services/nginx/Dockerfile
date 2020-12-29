# Source: https://testdriven.io/blog/dockerizing-flask-with-postgres-gunicorn-and-nginx/
# simple nginx docker file
FROM nginx:1.17-alpine

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d