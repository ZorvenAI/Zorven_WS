FROM odoo:19

# Railway sets PORT for the web server, but Odoo's entrypoint uses PORT
# for the database connection. This wrapper script resolves the conflict.
COPY entrypoint-railway.sh /entrypoint-railway.sh
USER root
RUN chmod +x /entrypoint-railway.sh

# Run as root so the entrypoint can fix volume permissions before
# delegating to the official entrypoint (which drops to odoo user)
EXPOSE 8069 8072

ENTRYPOINT ["/entrypoint-railway.sh"]
CMD ["odoo"]
