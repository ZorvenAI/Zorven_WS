#!/bin/bash
# =============================================================================
# Create Kafka Topics for AI Brand Automator
# =============================================================================
# This script creates the required Kafka topics for Kong Gateway integration.
# Run this script after Kafka is running.
#
# Topics:
#   - gateway-logs: HTTP request/response audit logs from Kong
#   - raw-ingestion-topic: Event ingestion from /ingest/event endpoint
#
# Usage:
#   ./create-kafka-topics.sh [bootstrap_server]
#
# Example:
#   ./create-kafka-topics.sh localhost:9092
#   ./create-kafka-topics.sh kafka:9092
# =============================================================================

set -e

# Configuration
BOOTSTRAP_SERVER="${1:-kafka:9092}"
PARTITIONS=3
REPLICATION_FACTOR=1  # Set to 3 in production with multiple brokers

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Creating Kafka topics on ${BOOTSTRAP_SERVER}...${NC}"

# Wait for Kafka to be ready
echo "Waiting for Kafka to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0

while ! kafka-topics.sh --bootstrap-server "$BOOTSTRAP_SERVER" --list >/dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo -e "${RED}Error: Kafka is not available after $MAX_RETRIES attempts${NC}"
        exit 1
    fi
    echo "Kafka not ready yet. Retrying in 2 seconds... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

echo -e "${GREEN}Kafka is ready!${NC}"

# Function to create topic if it doesn't exist
create_topic() {
    local topic_name=$1
    local partitions=${2:-$PARTITIONS}
    local retention_ms=${3:-604800000}  # 7 days default
    
    echo -n "Creating topic '$topic_name'... "
    
    # Check if topic exists
    if kafka-topics.sh --bootstrap-server "$BOOTSTRAP_SERVER" --list | grep -q "^${topic_name}$"; then
        echo -e "${YELLOW}already exists${NC}"
    else
        kafka-topics.sh --bootstrap-server "$BOOTSTRAP_SERVER" \
            --create \
            --topic "$topic_name" \
            --partitions "$partitions" \
            --replication-factor "$REPLICATION_FACTOR" \
            --config retention.ms="$retention_ms" \
            --config cleanup.policy=delete
        echo -e "${GREEN}created${NC}"
    fi
}

# Create topics
echo ""
echo "Creating required topics..."
echo "=========================="

# 1. Gateway Logs - High volume, shorter retention
create_topic "gateway-logs" 6 259200000  # 3 days retention, 6 partitions

# 2. Raw Ingestion - Events from /ingest/event
create_topic "raw-ingestion-topic" 3 604800000  # 7 days retention

# 3. Dead Letter Queue - Failed messages
create_topic "dlq-events" 1 2592000000  # 30 days retention

echo ""
echo "=========================="
echo -e "${GREEN}All topics created successfully!${NC}"
echo ""

# List all topics
echo "Current topics:"
kafka-topics.sh --bootstrap-server "$BOOTSTRAP_SERVER" --list

echo ""
echo "Topic details:"
for topic in gateway-logs raw-ingestion-topic dlq-events; do
    echo ""
    echo "--- $topic ---"
    kafka-topics.sh --bootstrap-server "$BOOTSTRAP_SERVER" --describe --topic "$topic" 2>/dev/null || echo "Topic not found"
done
