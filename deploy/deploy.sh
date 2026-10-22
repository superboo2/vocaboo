#!/bin/bash
# Update the app on the server to the newest version from GitHub:
#
#     sudo /srv/vocaboo/app/deploy/deploy.sh
#
# Gets the code (git pull), installs the libraries, updates the database tables, adds new
# packages of the dictionary (extensions/ folders copied by hand), updates the static files,
# restarts the app and checks that it runs. Stops at the first error.
# --no-pull does the same without getting new code (used by install.sh).

# Everything is in a function: git pull may change this file while it runs, and bash reads
# a function whole before it starts it
main() {
    set -euo pipefail

    local app=/srv/vocaboo/app
    local uv=/srv/vocaboo/.local/bin/uv

    if [[ $EUID -ne 0 ]]; then
        echo "Run it with sudo: sudo $app/deploy/deploy.sh" >&2
        exit 1
    fi

    cd "$app"

    # The app's files belong to the vocaboo user, so every command runs as vocaboo
    as_app() { sudo -u vocaboo -H "$@"; }
    manage() { as_app "$uv" run --no-dev python manage.py "$@"; }

    if [[ "${1:-}" != "--no-pull" ]]; then
        echo "==> Getting the new code"
        as_app git pull --ff-only
    fi

    echo "==> Libraries"
    # --frozen: exactly the versions of uv.lock, as on the developer's computer
    as_app "$uv" sync --no-dev --frozen

    echo "==> Database tables"
    manage migrate --noinput

    echo "==> New packages of the dictionary"
    # Folders in dictionary/data/extensions/ copied here by hand (they are not in git)
    manage extend_lexicon --new

    echo "==> Static files"
    manage collectstatic --noinput

    echo "==> Checking the settings"
    manage check

    echo "==> Restarting the app"
    systemctl restart vocaboo
    sleep 2
    if ! systemctl is-active --quiet vocaboo; then
        echo "The app did not start, the last lines of its log:" >&2
        journalctl -u vocaboo -n 30 --no-pager >&2
        exit 1
    fi

    echo "==> Done: $(as_app git log -1 --format='%h %s')"
}

main "$@"
