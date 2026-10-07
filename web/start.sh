#!/bin/sh
# Web entrypoint: apply migrations, then serve.
# A repo script (not an inline Railway startCommand) so the quoting and the
# ${PORT} expansion are testable and reviewable, and migrations always run.
set -e

python web/manage.py migrate --noinput

exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
