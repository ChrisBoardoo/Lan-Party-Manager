FROM node:20-alpine AS builder

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
