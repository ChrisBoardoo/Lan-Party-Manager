#!/bin/sh
# LAN Party Manager — which reverse proxy may tell nginx the client's real IP.
#
# Runs at container start (nginx image's /docker-entrypoint.d/) and writes the
# set_real_ip_from lines nginx.conf includes. The backend rate-limits login,
# registration and password resets per client IP, read from the
# X-Forwarded-For this nginx sends it. Behind a reverse proxy (Nginx Proxy
# Manager, Caddy, Traefik…) every request arrives from the proxy's own address,
# so nginx has to believe the X-Forwarded-For the proxy adds — and only the
# proxy's: believing anyone's lets any client forge its IP and bypass the
# limits (S1 of the 2026-09-24 security review).
#
# LPM_TRUSTED_PROXIES — addresses or CIDRs the proxy connects from, separated
# by spaces or commas. The default, 172.16.0.0/12, is Docker's own networks:
# a proxy running as a container on the same host, the usual Nginx Proxy
# Manager setup. Set your proxy's LAN address if it runs on another machine,
# or "none" when nothing sits in front of LPM.
#
# Getting it wrong fails safe but badly: nginx then sees every visitor as the
# proxy's address, and the whole crew shares one login rate limit. Check the
# backend's logs after deploying: they must show visitors' own IPs.
set -eu

out=/etc/nginx/lpm-real-ip.conf
: > "$out"

list=$(printf '%s' "${LPM_TRUSTED_PROXIES:-172.16.0.0/12}" | tr ',' ' ')
[ "$list" = "none" ] && exit 0

for entry in $list; do
    case "$entry" in
        *[!0-9A-Fa-f:./]*)
            echo "$0: ignoring invalid LPM_TRUSTED_PROXIES entry: $entry" >&2
            continue
            ;;
    esac
    echo "set_real_ip_from $entry;" >> "$out"
done
