#!/bin/bash
# =============================================================================
# Refresh GCP Access Token for Kong Gateway
# =============================================================================
# This script generates a new GCP access token and updates the Kong container
# environment. GCP access tokens expire after 1 hour, so this script should
# be run periodically (e.g., every 45 minutes via cron).
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - Service account with appropriate GCS permissions
#   - Docker or docker-compose installed
#
# Usage:
#   ./refresh-gcp-token.sh [options]
#
# Options:
#   --service-account FILE    Path to service account JSON file
#   --project PROJECT_ID      GCP project ID
#   --container CONTAINER     Kong container name (default: kong)
#   --compose                 Use docker-compose instead of docker
#   --dry-run                 Print token without updating container
#
# Example:
#   ./refresh-gcp-token.sh --service-account ./gcp-sa.json --compose
#   ./refresh-gcp-token.sh --dry-run
# =============================================================================

set -e

# Default configuration
SERVICE_ACCOUNT_FILE=""
PROJECT_ID=""
KONG_CONTAINER="kong"
USE_COMPOSE=false
DRY_RUN=false
COMPOSE_FILE="docker-compose.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --service-account)
            SERVICE_ACCOUNT_FILE="$2"
            shift 2
            ;;
        --project)
            PROJECT_ID="$2"
            shift 2
            ;;
        --container)
            KONG_CONTAINER="$2"
            shift 2
            ;;
        --compose)
            USE_COMPOSE=true
            shift
            ;;
        --compose-file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --service-account FILE    Path to service account JSON file"
            echo "  --project PROJECT_ID      GCP project ID"
            echo "  --container CONTAINER     Kong container name (default: kong)"
            echo "  --compose                 Use docker-compose instead of docker"
            echo "  --compose-file FILE       Docker compose file (default: docker-compose.yml)"
            echo "  --dry-run                 Print token without updating container"
            echo "  -h, --help                Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}=== GCP Token Refresh for Kong Gateway ===${NC}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI is not installed${NC}"
    echo "Install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Authenticate with service account if provided
if [ -n "$SERVICE_ACCOUNT_FILE" ]; then
    if [ ! -f "$SERVICE_ACCOUNT_FILE" ]; then
        echo -e "${RED}Error: Service account file not found: $SERVICE_ACCOUNT_FILE${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}Activating service account...${NC}"
    gcloud auth activate-service-account --key-file="$SERVICE_ACCOUNT_FILE"
    
    if [ -n "$PROJECT_ID" ]; then
        gcloud config set project "$PROJECT_ID"
    fi
fi

# Generate access token
echo -e "${YELLOW}Generating GCP access token...${NC}"
GCP_ACCESS_TOKEN=$(gcloud auth print-access-token 2>/dev/null)

if [ -z "$GCP_ACCESS_TOKEN" ]; then
    echo -e "${RED}Error: Failed to generate access token${NC}"
    echo "Make sure you are authenticated with gcloud:"
    echo "  gcloud auth login"
    echo "  gcloud auth application-default login"
    exit 1
fi

# Get token expiration (approximately 1 hour from now)
TOKEN_EXPIRY=$(date -v+1H "+%Y-%m-%d %H:%M:%S" 2>/dev/null || date -d "+1 hour" "+%Y-%m-%d %H:%M:%S")

echo -e "${GREEN}Token generated successfully!${NC}"
echo "Token prefix: ${GCP_ACCESS_TOKEN:0:20}..."
echo "Expires at: $TOKEN_EXPIRY"
echo ""

# Dry run - just print the token
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Dry run mode - not updating container${NC}"
    echo ""
    echo "To use this token, set the environment variable:"
    echo "  export GCP_ACCESS_TOKEN='$GCP_ACCESS_TOKEN'"
    echo ""
    echo "Or add to .env file:"
    echo "  GCP_ACCESS_TOKEN=$GCP_ACCESS_TOKEN"
    exit 0
fi

# Update Kong container
echo -e "${YELLOW}Updating Kong container...${NC}"

if [ "$USE_COMPOSE" = true ]; then
    # Using docker-compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        echo -e "${RED}Error: docker-compose is not installed${NC}"
        exit 1
    fi
    
    # Create or update .env file with new token
    ENV_FILE=".env"
    if [ -f "$COMPOSE_FILE" ]; then
        ENV_FILE="$(dirname "$COMPOSE_FILE")/.env"
    fi
    
    # Update or add GCP_ACCESS_TOKEN in .env
    if [ -f "$ENV_FILE" ]; then
        if grep -q "^GCP_ACCESS_TOKEN=" "$ENV_FILE"; then
            # macOS compatible sed
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|^GCP_ACCESS_TOKEN=.*|GCP_ACCESS_TOKEN=$GCP_ACCESS_TOKEN|" "$ENV_FILE"
            else
                sed -i "s|^GCP_ACCESS_TOKEN=.*|GCP_ACCESS_TOKEN=$GCP_ACCESS_TOKEN|" "$ENV_FILE"
            fi
        else
            echo "GCP_ACCESS_TOKEN=$GCP_ACCESS_TOKEN" >> "$ENV_FILE"
        fi
    else
        echo "GCP_ACCESS_TOKEN=$GCP_ACCESS_TOKEN" > "$ENV_FILE"
    fi
    
    echo -e "${GREEN}Updated $ENV_FILE with new token${NC}"
    
    # Recreate Kong container to pick up new env
    echo "Recreating Kong container..."
    if docker compose version &> /dev/null 2>&1; then
        docker compose -f "$COMPOSE_FILE" up -d --force-recreate kong
    else
        docker-compose -f "$COMPOSE_FILE" up -d --force-recreate kong
    fi
    
else
    # Using docker directly
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: docker is not installed${NC}"
        exit 1
    fi
    
    # Check if container exists
    if ! docker ps -a --format '{{.Names}}' | grep -q "^${KONG_CONTAINER}$"; then
        echo -e "${RED}Error: Container '$KONG_CONTAINER' not found${NC}"
        exit 1
    fi
    
    # Update container environment
    echo "Updating Kong container environment..."
    docker update --env-add "GCP_ACCESS_TOKEN=$GCP_ACCESS_TOKEN" "$KONG_CONTAINER" 2>/dev/null || {
        echo -e "${YELLOW}Warning: docker update doesn't support --env-add${NC}"
        echo "You'll need to recreate the container with the new environment variable."
        echo ""
        echo "Add this to your docker run command:"
        echo "  -e GCP_ACCESS_TOKEN='$GCP_ACCESS_TOKEN'"
    }
fi

echo ""
echo -e "${GREEN}=== Token refresh complete ===${NC}"
echo ""
echo "Next refresh recommended at: $TOKEN_EXPIRY"
echo ""
echo "To automate, add this cron job (runs every 45 minutes):"
echo "  */45 * * * * $(pwd)/$0 --compose >> /var/log/gcp-token-refresh.log 2>&1"
