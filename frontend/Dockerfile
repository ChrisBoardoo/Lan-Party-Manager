# Node 22 (node 20 reached end of life on 2026-04-30, O-7 of the 2026-10-20
# review). Build stage only: the runtime below is nginx.
# --platform=$BUILDPLATFORM: the build stage runs on the machine doing the build
# (amd64), never under QEMU. Its output (dist/) is static files, the same for
# every target; only the nginx stage below is per-platform, so multi-arch builds
# emulate one tiny step instead of npm + Vite. (The 1.4.1 arm64 build's
# "exit code: 255" was the default buildx builder having no arm64 emulation at
# all, "exec format error", not node: build with a docker-container builder,
# which ships its own QEMU. See the per-version build notes.)
FROM --platform=$BUILDPLATFORM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Writes /etc/nginx/lpm-real-ip.conf from LPM_TRUSTED_PROXIES at container start
# (see the script). The sed strips CRLF: a Windows checkout with core.autocrlf
# turns it into `#!/bin/sh\r`, and the container would then never start.
COPY nginx-real-ip.sh /docker-entrypoint.d/40-lpm-real-ip.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-lpm-real-ip.sh \
    && chmod +x /docker-entrypoint.d/40-lpm-real-ip.sh

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
