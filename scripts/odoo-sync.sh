#!/usr/bin/env bash
# odoo-sync.sh — Update Odoo Community Edition submodule to latest 19.0
#
# Usage:
#   ./scripts/odoo-sync.sh          # Update to latest 19.0
#   ./scripts/odoo-sync.sh --check  # Check for updates without applying
#
set -euo pipefail

SUBMODULE_PATH="vendor/odoo/community"
BRANCH="19.0"

cd "$(git rev-parse --show-toplevel)"

if [ ! -f ".gitmodules" ]; then
    echo "ERROR: .gitmodules not found. Run from the repository root."
    exit 1
fi

current_commit=$(git -C "$SUBMODULE_PATH" rev-parse HEAD 2>/dev/null || echo "not initialized")

if [ "${1:-}" = "--check" ]; then
    echo "Current Odoo commit: $current_commit"
    git -C "$SUBMODULE_PATH" fetch origin "$BRANCH" --depth 1
    latest=$(git -C "$SUBMODULE_PATH" rev-parse FETCH_HEAD)
    if [ "$current_commit" = "$latest" ]; then
        echo "Already up to date."
    else
        echo "Update available: $latest"
    fi
    exit 0
fi

echo "Updating Odoo submodule to latest $BRANCH..."
git submodule update --remote --depth 1 "$SUBMODULE_PATH"

new_commit=$(git -C "$SUBMODULE_PATH" rev-parse HEAD)
echo "Updated: $current_commit -> $new_commit"
echo ""
echo "To commit this update:"
echo "  git add $SUBMODULE_PATH"
echo "  git commit -m 'chore: update Odoo CE submodule to latest 19.0'"
