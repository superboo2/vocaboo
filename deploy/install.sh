#!/bin/bash
# Set up the server for Vocaboo once: the app as a service (gunicorn), nginx and the nightly
# jobs. Before it: PostgreSQL with the database, the vocaboo user, the code in
# /srv/vocaboo/app and its .env (see README.md, Server). Then:
#
#     cd /srv/vocaboo/app && sudo deploy/install.sh
#
# Running it again does no harm; the nginx file is kept when it exists (certbot changes it).

main() {
    set -euo pipefail

    local app=/srv/vocaboo/app
    local here="$app/deploy"

    if [[ $EUID -ne 0 ]]; then
        echo "Run it with sudo: cd $app && sudo deploy/install.sh" >&2
        exit 1
    fi
    if ! id vocaboo >/dev/null 2>&1; then
        echo "The vocaboo user is missing, see README.md (Server, step 1)." >&2
        exit 1
    fi
    if [[ ! -f "$app/.env" ]]; then
        echo "$app/.env is missing, see README.md (Server, step 2)." >&2
        exit 1
    fi

    echo "==> nginx"
    if ! command -v nginx >/dev/null; then
        apt-get install -y nginx
    fi

    echo "==> Access rights"
    # Only the vocaboo user reads the secrets; nginx (www-data) gets into the vocaboo group
    # to read the static files and to talk to the socket
    chmod 600 "$app/.env"
    chown vocaboo:vocaboo "$app/.env"
    usermod -aG vocaboo www-data
    chmod 750 /srv/vocaboo "$app"

    echo "==> The app as a service"
    install -m 644 "$here/vocaboo.service" /etc/systemd/system/vocaboo.service
    systemctl daemon-reload
    systemctl enable vocaboo

    # Libraries, tables, static files, (re)start of the service
    "$here/deploy.sh" --no-pull

    echo "==> nginx site"
    if [[ -f /etc/nginx/sites-available/vocaboo ]]; then
        echo "    /etc/nginx/sites-available/vocaboo exists, kept as it is"
    else
        install -m 644 "$here/nginx.conf" /etc/nginx/sites-available/vocaboo
    fi
    ln -sf /etc/nginx/sites-available/vocaboo /etc/nginx/sites-enabled/vocaboo
    # The welcome page of nginx would take the IP address of the Pi
    rm -f /etc/nginx/sites-enabled/default
    nginx -t
    # A restart (not a reload), so nginx gets the new group of www-data
    systemctl restart nginx

    echo "==> Nightly jobs (backup, cleanup)"
    install -m 755 "$here/cron-daily" /etc/cron.daily/vocaboo

    echo "==> Check"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: vocaboo.me" http://127.0.0.1/accounts/login/ || true)
    if [[ "$code" == "200" || "$code" == "301" ]]; then
        echo "    The login page answers (HTTP $code)."
        echo "Done. At home open http://$(hostname -I | cut -d' ' -f1)/"
    else
        echo "    The login page answers HTTP $code instead of 200, see:" >&2
        echo "    journalctl -u vocaboo -n 50   and   sudo tail /var/log/nginx/error.log" >&2
        exit 1
    fi
}

main "$@"
