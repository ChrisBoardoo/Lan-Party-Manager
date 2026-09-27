FROM python:3.11-slim

WORKDIR /app

# Pillow native libs (JPEG/PNG) + ffmpeg for video thumbnail generation
# All packages available on ARM64 (Raspberry Pi 4/5) without modification
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    ffmpeg \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# The app runs as this unprivileged user; entrypoint.sh starts as root only to
# hand data/ and uploads/ over to it. uid 1000 on purpose: it's the default `pi`
# user on Raspberry Pi OS, so the Pi's SSH user reads those folders without sudo.
RUN useradd --uid 1000 --user-group --no-create-home --shell /usr/sbin/nologin lpm

# /app stays root-owned and read-only for lpm: without this, every start would
# try (and fail) to write __pycache__ next to the sources.
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The sed strips CRLF: a Windows checkout with core.autocrlf breaks the shebang
# (.gitattributes forces LF too — this is the backstop, as in frontend/Dockerfile).
RUN mkdir -p /app/data /app/uploads \
    && chown lpm:lpm /app/data /app/uploads \
    && sed -i 's/\r$//' /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

# --proxy-headers/--forwarded-allow-ips: trust X-Forwarded-Proto (and -For/-Host)
# from whatever's in front of this container (the bundled Nginx, or a self-hoster's
# own external reverse proxy). Without this, Starlette's redirect_slashes builds
# absolute-URL Location headers from the *literal* connection scheme (always
# "http" here, since Nginx always talks to Uvicorn over plain HTTP) even when the
# original request came in over https — silently downgrading https to http on any
# no-trailing-slash redirect, which strips the Authorization header on the
# client's next hop. "*" is safe here specifically because this port is never
# meant to be reachable directly (only via the bundled Nginx / a self-hoster's own
# reverse proxy in front of it) — see README's self-hosting section.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
