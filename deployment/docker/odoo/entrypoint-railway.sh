#!/bin/bash
set -e

# Railway injects PORT for the web server port.
# Odoo's default entrypoint reads PORT as the DB port.
# We separate them here to resolve the conflict.

WEB_PORT="${PORT:-8069}"
DB_PORT="${ODOO_DB_PORT:-5432}"

echo "[railway-entrypoint] WEB_PORT=$WEB_PORT, DB_PORT=$DB_PORT"

# Fix volume permissions (Railway volume mounts are owned by root)
mkdir -p /var/lib/odoo/sessions /var/lib/odoo/filestore
chown -R odoo:odoo /var/lib/odoo

# Override PORT to the DB port so Odoo's entrypoint uses it correctly
export PORT="$DB_PORT"

# Drop to odoo user and delegate to the official entrypoint
exec su -s /bin/bash odoo -c "/entrypoint.sh $* --http-port $WEB_PORT"
