# Kong Gateway Dockerfile
# DB-less mode with declarative configuration

FROM kong:3.4

# Install gettext for envsubst (environment variable substitution)
USER root
RUN apt-get update && apt-get install -y gettext-base && rm -rf /var/lib/apt/lists/*

# Preserve original entrypoint
RUN cp /docker-entrypoint.sh /docker-entrypoint-original.sh

USER kong

# Set environment variables for DB-less mode
ENV KONG_DATABASE=off
ENV KONG_DECLARATIVE_CONFIG=/usr/local/kong/declarative/kong.yaml
ENV KONG_PROXY_LISTEN=0.0.0.0:8000
ENV KONG_ADMIN_LISTEN=0.0.0.0:8001
ENV KONG_PROXY_ACCESS_LOG=/dev/stdout
ENV KONG_ADMIN_ACCESS_LOG=/dev/stdout
ENV KONG_PROXY_ERROR_LOG=/dev/stderr
ENV KONG_ADMIN_ERROR_LOG=/dev/stderr

# Enable bundled plugins (Kafka plugins require Enterprise or custom build)
# For MVP, we use http-log plugin to send to Django endpoint which forwards to Kafka
ENV KONG_PLUGINS=bundled,jwt,cors,request-transformer,rate-limiting,response-transformer,http-log

# Copy declarative configuration template
COPY kong.yaml /usr/local/kong/declarative/kong.yaml.template

# Copy custom entrypoint script
COPY docker-entrypoint.sh /custom-entrypoint.sh

# Expose ports
# 8000 - Proxy (HTTP)
# 8443 - Proxy (HTTPS)
# 8001 - Admin API (HTTP)
# 8444 - Admin API (HTTPS)
EXPOSE 8000 8443 8001 8444

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD kong health || exit 1

# Run custom entrypoint which processes env vars then calls Kong's entrypoint
USER root
RUN chmod +x /custom-entrypoint.sh
USER kong
ENTRYPOINT ["/custom-entrypoint.sh"]
CMD ["kong", "docker-start"]
