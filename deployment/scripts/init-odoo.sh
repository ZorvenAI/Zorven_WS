#!/bin/bash
# Initialize Odoo database with demo data.
# Run once after first: docker compose --profile with-odoo up

set -e

ODOO_URL="${ODOO_URL:-http://localhost:8069}"
ODOO_DB="${ODOO_DB:-odoo}"
ODOO_MASTER_PASSWORD="${ODOO_MASTER_PASSWORD:-admin}"

echo "Waiting for Odoo to be ready at $ODOO_URL ..."
for i in $(seq 1 30); do
    if curl -sf "$ODOO_URL/web/health" > /dev/null 2>&1; then
        echo "Odoo is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Odoo did not start within 5 minutes."
        exit 1
    fi
    sleep 10
done

echo "Initializing Odoo database '$ODOO_DB' with demo data..."

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$ODOO_URL/web/database/create" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "master_pwd=$ODOO_MASTER_PASSWORD&name=$ODOO_DB&login=admin&password=admin&lang=en_US&country_code=us&demo=on")

if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 303 ]; then
    echo "Odoo database '$ODOO_DB' initialized successfully."
    echo "Access at $ODOO_URL (admin/admin)"
else
    echo "WARNING: Received HTTP $HTTP_CODE — database may already exist."
    echo "Check $ODOO_URL/web/database/manager for details."
fi
