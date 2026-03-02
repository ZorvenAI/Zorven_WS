#!/usr/bin/env python3
"""
Railway Setup Script — Creates and configures all missing services.

Usage:
    python deployment/scripts/railway-setup.py

This script:
1. Adds missing env vars to the backend service
2. Creates 10 missing services (celery-worker, celery-beat, mcp-server,
   orchestrator, discovery-agent, intelligence-agent, chat-titling-worker,
   content-agent, social-agent, rag-uploader)
3. Configures each service with the correct Dockerfile path, root dir,
   start command, and health check
4. Sets environment variables for each service
"""

import json
import subprocess
import sys
import time

# ─── Constants ──────────────────────────────────────────────────────────────

PROJECT_ID = "aa532d23-9787-4e12-abdd-995b1e80cd2a"
ENV_ID = "d78f43db-b019-46e2-b56f-0fd30b8f77c9"

# Read token from Railway config
with open("/Users/naveenhanuman/.railway/config.json") as f:
    config = json.load(f)
TOKEN = config["user"]["token"]

GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"

# Redis base URL (internal)
REDIS_BASE = "redis://default:stByFAnjnFfyjBquClceRkDpocLRHrnD@redis.railway.internal:6379"

# Shared secrets
SERVICE_TOKEN = "Q5Gwa0oiDWcDEXyP7jLmepM8TwIXKBlj5TLTfaOJA3o"
CALLBACK_TOKEN = "JcvbEPOKQz9gv8WR43yIEcapoh0rf2PaqZGpaAIRrRM"
WORKER_TOKEN = "yBVV1W8PWGYfKj3WvwrBoofCbWNW0MkMRPkEZKUfboU"

# Google API Key (from backend env)
GOOGLE_API_KEY = "AIzaSyAyyFMj47QoOUrIU0jIP4WSMC8IWPlc144"
GCS_PROJECT_ID = "brandsol-project"
GCS_BUCKET_NAME = "onboarding-brandsol-customer-bucket-1"

# Backend service name (used to derive internal Railway hostname)
BACKEND_SERVICE_NAME = "Prevision-WS"
BACKEND_PORT = "8000"
BACKEND_INTERNAL_URL = f"http://{BACKEND_SERVICE_NAME}.railway.internal:{BACKEND_PORT}"

# Existing service IDs
BACKEND_SERVICE_ID = "9422b6c8-da15-4f68-ace4-6ab6f3512037"


# ─── Service Definitions ─────────────────────────────────────────────────

SERVICES = [
    {
        "name": "celery-worker",
        "root_dir": "ai-brand-automator",
        "dockerfile": "Dockerfile",
        "start_command": "/app/entrypoint-worker.sh celery -A brand_automator worker -l info --concurrency=2 -Q celery,high_priority,low_priority,orchestration",
        "health_check": None,
        "env_vars": {
            "DJANGO_SETTINGS_MODULE": "brand_automator.settings",
            "PYTHONUNBUFFERED": "1",
            "BACKEND_URL": BACKEND_INTERNAL_URL,
            # CALLBACK_BASE_URL: internal URL the orchestrator uses to call
            # back with per-node progress.  Must NOT be a public/HTTPS URL
            # because cloud load balancers drop idle connections and cause
            # silent callback failures.
            "CALLBACK_BASE_URL": BACKEND_INTERNAL_URL,
            "ORCHESTRATOR_URL": "http://orchestrator.railway.internal:8010",
            "ORCHESTRATOR_SERVICE_TOKEN": SERVICE_TOKEN,
            "ORCHESTRATOR_CALLBACK_TOKEN": CALLBACK_TOKEN,
        },
        "needs_backend_vars": True,
    },
    {
        "name": "celery-beat",
        "root_dir": "ai-brand-automator",
        "dockerfile": "Dockerfile",
        "start_command": "/app/entrypoint-worker.sh celery -A brand_automator beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler",
        "health_check": None,
        "env_vars": {
            "DJANGO_SETTINGS_MODULE": "brand_automator.settings",
            "PYTHONUNBUFFERED": "1",
            "BACKEND_URL": BACKEND_INTERNAL_URL,
            "CALLBACK_BASE_URL": BACKEND_INTERNAL_URL,
            "ORCHESTRATOR_URL": "http://orchestrator.railway.internal:8010",
            "ORCHESTRATOR_SERVICE_TOKEN": SERVICE_TOKEN,
            "ORCHESTRATOR_CALLBACK_TOKEN": CALLBACK_TOKEN,
        },
        "needs_backend_vars": True,
    },
    {
        "name": "mcp-server",
        "root_dir": "ai-brand-automator",
        "dockerfile": "Dockerfile",
        "start_command": "/app/entrypoint-worker.sh python run_mcp_server.py --transport sse --port 8085 --host 0.0.0.0",
        "health_check": "/health",
        "env_vars": {
            "PORT": "8085",
            "DJANGO_SETTINGS_MODULE": "brand_automator.settings",
            "PYTHONUNBUFFERED": "1",
        },
        "needs_backend_vars": True,
    },
    {
        "name": "orchestrator",
        "root_dir": "pipeline-orchestrator-svc",
        "dockerfile": "Dockerfile",
        "start_command": None,
        "health_check": "/health",
        "env_vars": {
            "ORCHESTRATOR_SERVICE_TOKEN": SERVICE_TOKEN,
            "ORCHESTRATOR_CALLBACK_TOKEN": CALLBACK_TOKEN,
            "ORCHESTRATOR_REDIS_URL": f"{REDIS_BASE}/1",
            "ORCHESTRATOR_KAFKA_BOOTSTRAP_SERVERS": "",
            "ORCHESTRATOR_GOOGLE_API_KEY": GOOGLE_API_KEY,
            "ORCHESTRATOR_LOG_LEVEL": "INFO",
            "ORCHESTRATOR_HOST": "0.0.0.0",
            "ORCHESTRATOR_PORT": "8010",
            "ORCHESTRATOR_DISCOVERY_AGENT_URL": "http://discovery-agent.railway.internal:8020",
            "ORCHESTRATOR_CONTENT_AGENT_URL": "http://content-agent.railway.internal:8050",
            "ORCHESTRATOR_SOCIAL_AGENT_URL": "http://social-agent.railway.internal:8060",
            "ORCHESTRATOR_INTELLIGENCE_AGENT_URL": "http://intelligence-agent.railway.internal:8030",
            "ORCHESTRATOR_RAG_UPLOADER_AGENT_URL": "http://rag-uploader.railway.internal:8070",
            "ORCHESTRATOR_VERTEX_AI_PROJECT_ID": GCS_PROJECT_ID,
            "PORT": "8010",
        },
        "needs_backend_vars": False,
    },
    {
        "name": "discovery-agent",
        "root_dir": "discovery-agent-svc",
        "dockerfile": "Dockerfile",
        "start_command": None,
        "health_check": "/health",
        "env_vars": {
            "DISCOVERY_REDIS_URL": f"{REDIS_BASE}/2",
            "DISCOVERY_KAFKA_BOOTSTRAP_SERVERS": "",
            "DISCOVERY_TAVILY_API_KEY": "",
            "DISCOVERY_GOOGLE_API_KEY": GOOGLE_API_KEY,
            "DISCOVERY_GCS_PROJECT_ID": GCS_PROJECT_ID,
            "DISCOVERY_GCS_BUCKET_NAME": GCS_BUCKET_NAME,
            "DISCOVERY_LOG_LEVEL": "INFO",
            "PORT": "8020",
        },
        "needs_backend_vars": False,
    },
    {
        "name": "intelligence-agent",
        "root_dir": "intelligence-agent-svc",
        "dockerfile": "Dockerfile",
        "start_command": None,
        "health_check": "/health",
        "env_vars": {
            "INTELLIGENCE_REDIS_URL": f"{REDIS_BASE}/3",
            "INTELLIGENCE_KAFKA_BOOTSTRAP_SERVERS": "",
            "INTELLIGENCE_GEMINI_API_KEY": GOOGLE_API_KEY,
            "INTELLIGENCE_GCS_PROJECT_ID": GCS_PROJECT_ID,
            "INTELLIGENCE_GCS_BUCKET_NAME": GCS_BUCKET_NAME,
            "INTELLIGENCE_LOG_LEVEL": "INFO",
            "PORT": "8030",
        },
        "needs_backend_vars": False,
    },
    {
        "name": "chat-titling-worker",
        "root_dir": "chat-titling-worker",
        "dockerfile": "Dockerfile",
        "start_command": None,
        "health_check": "/health",
        "env_vars": {
            "TITLING_REDIS_URL": f"{REDIS_BASE}/4",
            "TITLING_KAFKA_BOOTSTRAP_SERVERS": "",
            "TITLING_GOOGLE_API_KEY": GOOGLE_API_KEY,
            "TITLING_CORE_API_URL": BACKEND_INTERNAL_URL,
            "TITLING_WORKER_TOKEN": WORKER_TOKEN,
            "TITLING_LOG_LEVEL": "INFO",
            "PORT": "8040",
        },
        "needs_backend_vars": False,
    },
    {
        "name": "content-agent",
        "root_dir": "content-agent-service",
        "dockerfile": "Dockerfile",
        "start_command": None,
        "health_check": "/health",
        "env_vars": {
            "CONTENT_REDIS_URL": f"{REDIS_BASE}/5",
            "CONTENT_KAFKA_BOOTSTRAP_SERVERS": "",
            "CONTENT_GOOGLE_API_KEY": GOOGLE_API_KEY,
            "CONTENT_GCS_PROJECT_ID": GCS_PROJECT_ID,
            "CONTENT_GCS_BUCKET_NAME": GCS_BUCKET_NAME,
            "CONTENT_CORE_API_URL": BACKEND_INTERNAL_URL,
            "CONTENT_CORE_API_TOKEN": SERVICE_TOKEN,
            "CONTENT_LOG_LEVEL": "INFO",
            "PORT": "8050",
        },
        "needs_backend_vars": False,
    },
    {
        "name": "social-agent",
        "root_dir": "social-agent-service",
        "dockerfile": "Dockerfile",
        "start_command": None,
        "health_check": "/health",
        "env_vars": {
            "SOCIAL_REDIS_URL": f"{REDIS_BASE}/6",
            "SOCIAL_KAFKA_BOOTSTRAP_SERVERS": "",
            "SOCIAL_GOOGLE_API_KEY": GOOGLE_API_KEY,
            "SOCIAL_CORE_API_URL": BACKEND_INTERNAL_URL,
            "SOCIAL_CORE_API_TOKEN": SERVICE_TOKEN,
            "SOCIAL_MCP_SERVER_URL": "http://mcp-server.railway.internal:8085/sse",
            "SOCIAL_LOG_LEVEL": "INFO",
            "PORT": "8060",
        },
        "needs_backend_vars": False,
    },
    {
        "name": "rag-uploader",
        "root_dir": "rag-uploader-agent-service",
        "dockerfile": "Dockerfile",
        "start_command": None,
        "health_check": "/health",
        "env_vars": {
            "UPLOADER_REDIS_URL": f"{REDIS_BASE}/7",
            "UPLOADER_KAFKA_BOOTSTRAP_SERVERS": "",
            "UPLOADER_GOOGLE_API_KEY": GOOGLE_API_KEY,
            "UPLOADER_GCS_PROJECT_ID": GCS_PROJECT_ID,
            "UPLOADER_GCS_BUCKET_NAME": GCS_BUCKET_NAME,
            "UPLOADER_CORE_API_URL": BACKEND_INTERNAL_URL,
            "UPLOADER_CORE_API_TOKEN": SERVICE_TOKEN,
            "UPLOADER_LOG_LEVEL": "INFO",
            "PORT": "8070",
        },
        "needs_backend_vars": False,
    },
]


def gql(query: str) -> dict:
    """Execute a GraphQL query against the Railway API."""
    import urllib.request

    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps({"query": query}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def create_service(name: str) -> str:
    """Create a new service and return its ID."""
    result = gql(
        f'mutation {{ serviceCreate(input: {{ name: "{name}", projectId: "{PROJECT_ID}" }}) {{ id name }} }}'
    )
    if "errors" in result:
        print(f"  ERROR creating {name}: {result['errors']}")
        return None
    svc = result["data"]["serviceCreate"]
    print(f"  Created service: {svc['name']} (ID: {svc['id']})")
    return svc["id"]


def update_service_instance(
    service_id: str,
    root_dir: str = None,
    dockerfile: str = None,
    start_command: str = None,
    health_check: str = None,
):
    """Update service instance configuration."""
    parts = []
    if root_dir:
        parts.append(f'rootDirectory: "{root_dir}"')
    if dockerfile:
        parts.append(f'dockerfilePath: "{dockerfile}"')
    if start_command:
        # Escape quotes in command
        escaped = start_command.replace('"', '\\"')
        parts.append(f'startCommand: "{escaped}"')
    if health_check:
        parts.append(f'healthcheckPath: "{health_check}"')
        parts.append("healthcheckTimeout: 300")

    if not parts:
        return

    input_str = ", ".join(parts)
    result = gql(
        f'mutation {{ serviceInstanceUpdate(serviceId: "{service_id}", environmentId: "{ENV_ID}", input: {{ {input_str} }}) }}'
    )
    if "errors" in result:
        print(f"  ERROR updating config: {result['errors']}")
    else:
        print(f"  Updated config: {input_str[:80]}...")


def set_variables(service_id: str, variables: dict):
    """Set environment variables for a service."""
    # Build the variables JSON
    vars_json = json.dumps(variables).replace('"', '\\"')
    result = gql(
        f'mutation {{ variableCollectionUpsert(input: {{ projectId: "{PROJECT_ID}", environmentId: "{ENV_ID}", serviceId: "{service_id}", variables: {json.dumps(variables)} }}) }}'
    )
    if "errors" in result:
        # Try alternative approach
        print(f"  Trying alternative variable set method...")
        for key, value in variables.items():
            val_escaped = value.replace('"', '\\"').replace("\n", "\\n")
            r = gql(
                f'mutation {{ variableUpsert(input: {{ projectId: "{PROJECT_ID}", environmentId: "{ENV_ID}", serviceId: "{service_id}", name: "{key}", value: "{val_escaped}" }}) }}'
            )
            if "errors" in r:
                print(f"    ERROR setting {key}: {r['errors'][0]['message']}")
            else:
                pass  # silent success
        print(f"  Set {len(variables)} variables individually")
    else:
        print(f"  Set {len(variables)} variables")


def get_existing_services() -> dict:
    """Get map of existing service names to IDs."""
    result = gql(
        f'query {{ project(id: "{PROJECT_ID}") {{ services {{ edges {{ node {{ id name }} }} }} }} }}'
    )
    services = {}
    for edge in result["data"]["project"]["services"]["edges"]:
        node = edge["node"]
        services[node["name"]] = node["id"]
    return services


def main():
    print("=" * 60)
    print("Railway Setup — AI Brand Automator")
    print("=" * 60)

    # Step 1: Get existing services
    print("\n[1/4] Checking existing services...")
    existing = get_existing_services()
    print(f"  Found {len(existing)} services: {', '.join(existing.keys())}")

    # Step 2: Add missing env vars to backend
    print("\n[2/4] Adding missing env vars to backend...")
    backend_new_vars = {
        "BACKEND_URL": BACKEND_INTERNAL_URL,
        "ORCHESTRATOR_URL": "http://orchestrator.railway.internal:8010",
        "ORCHESTRATOR_SERVICE_TOKEN": SERVICE_TOKEN,
        "ORCHESTRATOR_CALLBACK_TOKEN": CALLBACK_TOKEN,
        "WORKER_TOKEN": WORKER_TOKEN,
        "DJANGO_SETTINGS_MODULE": "brand_automator.settings",
        "PYTHONUNBUFFERED": "1",
        "PORT": "8000",
        "REDIS_URL": f"{REDIS_BASE}/0",
        "SECURE_PROXY_SSL_HEADER": "HTTP_X_FORWARDED_PROTO,https",
        "USE_X_FORWARDED_HOST": "true",
        "USE_X_FORWARDED_PORT": "true",
        "KONG_ENABLED": "false",
        "GCS_AUTO_PROVISION": "true",
        "ONBOARDING_KAFKA_ENABLED": "false",
        "KAFKA_CONSUMERS_ENABLED": "false",
        "ORCHESTRATION_KAFKA_ENABLED": "false",
        # Note: RAILWAY_ENVIRONMENT_NAME is auto-injected by Railway.
        # settings.py uses it to append .railway.internal to ALLOWED_HOSTS
        # so pipeline callbacks from the orchestrator are not rejected
        # with 400 DisallowedHost.
    }
    set_variables(BACKEND_SERVICE_ID, backend_new_vars)

    # Step 3: Create missing services
    print("\n[3/4] Creating missing services...")
    created = {}
    for svc_def in SERVICES:
        name = svc_def["name"]
        if name in existing:
            print(f"  {name}: already exists (ID: {existing[name]})")
            created[name] = existing[name]
        else:
            print(f"  Creating {name}...")
            svc_id = create_service(name)
            if svc_id:
                created[name] = svc_id
                time.sleep(0.5)  # Rate limit

    # Step 4: Configure each service
    print("\n[4/4] Configuring services...")
    for svc_def in SERVICES:
        name = svc_def["name"]
        svc_id = created.get(name)
        if not svc_id:
            print(f"  SKIP {name}: no service ID")
            continue

        print(f"\n  Configuring {name}...")

        # Update instance config
        update_service_instance(
            svc_id,
            root_dir=svc_def["root_dir"],
            dockerfile=svc_def["dockerfile"],
            start_command=svc_def.get("start_command"),
            health_check=svc_def.get("health_check"),
        )
        time.sleep(0.3)

        # Set env vars
        set_variables(svc_id, svc_def["env_vars"])
        time.sleep(0.3)

    print("\n" + "=" * 60)
    print("Setup complete!")
    print("=" * 60)
    print("\nService IDs for reference:")
    for name, sid in sorted(created.items()):
        print(f"  {name}: {sid}")
    print(f"\nBackend: {BACKEND_SERVICE_ID}")
    print(f"\nNext steps:")
    print(f"  1. Deploy each service using: railway up --service <name>")
    print(f"  2. Run health checks against deployed URLs")
    print(f"\nNote: Services that need_backend_vars=True share the")
    print(f"  same DATABASE_URL, SECRET_KEY, etc. from the backend.")
    print(f"  These are inherited from Railway's shared variables")
    print(f"  or need to be copied manually from the backend service.")


if __name__ == "__main__":
    main()
