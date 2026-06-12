#!/bin/sh
set -eu
mkdir -p /etc/nginx/certs
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj '/CN=ito.local' -keyout /etc/nginx/certs/ito.key -out /etc/nginx/certs/ito.crt >/dev/null 2>&1
