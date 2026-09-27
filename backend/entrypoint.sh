#!/bin/sh
# Starts as root only long enough to hand /app/data and /app/uploads to the
# unprivileged `lpm` user, then drops privileges for good with gosu (the pattern
# of the official postgres/redis images). A plain `USER lpm` in the Dockerfile
# would break every install whose bind-mounted data/ and uploads/ Docker created
# as root — including every instance upgrading from <= 1.3.2, which ran as root.
set -e

LPM_UID=$(id -u lpm)

if [ "$(id -u)" = "0" ]; then
    for dir in /app/data /app/uploads; do
        mkdir -p "$dir"
        if [ "$(stat -c %u "$dir")" != "$LPM_UID" ]; then
            echo "entrypoint: handing $dir over to lpm (uid $LPM_UID) — one-time, on upgrade from a root install"
            # Contents first, the directory itself last: if this is interrupted
            # (a slow chown of a big uploads/ on a Pi), the directory is still
            # root-owned and the next boot resumes instead of skipping.
            find "$dir" -mindepth 1 ! -user lpm -exec chown lpm:lpm {} + \
                || echo "entrypoint: WARNING could not chown everything in $dir"
            chown lpm:lpm "$dir" || echo "entrypoint: WARNING could not chown $dir"
        fi
        # Fail loudly at boot rather than with a "permission denied" mid-request:
        # anything directly inside data/ or uploads/ that lpm can't write
        # (lanparty.db, its -wal/-shm, backups/, media/…) stops the container here.
        blocked=$(gosu lpm find "$dir" -maxdepth 1 ! -writable 2>&1 || echo "$dir (not readable by lpm)")
        if [ -n "$blocked" ]; then
            echo "entrypoint: ERROR lpm (uid $LPM_UID) cannot write:" >&2
            echo "$blocked" >&2
            echo "entrypoint: fix on the host with: sudo chown -R $LPM_UID:$LPM_UID <host path of $dir>" >&2
            exit 1
        fi
    done
    exec gosu lpm "$@"
fi

# Already started as non-root (e.g. `user:` set in the compose file): nothing to hand over.
exec "$@"
