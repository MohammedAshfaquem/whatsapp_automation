# Production deployment

The customer, booking, staff handover, WhatsApp forms and delivery retry workflows are unchanged. This deployment uses Python 3.12, Django 5.2 LTS, Waitress, WhiteNoise and an external PostgreSQL database. The existing docker-compose.yml remains a local database helper, with development credentials only.

## Configure

Copy .env.example to .env.production (never commit it). Set:

- DJANGO_DEBUG=False
- DJANGO_SECRET_KEY to a unique random secret of at least 50 characters. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- DJANGO_ALLOWED_HOSTS to the exact public hostname, without a scheme.
- DJANGO_CSRF_TRUSTED_ORIGINS to the HTTPS origin, such as https://service.example.com.
- DATABASE_URL to a production PostgreSQL connection URL; require TLS when connecting over an untrusted network (sslmode=require).
- CHROMA_PERSIST_DIRECTORY=/app/chroma_data when using Docker.
- Provider keys and WhatsApp settings as described in README.md. Confirm the Meta app secret is present before enabling live webhooks.

Configure a TLS reverse proxy to the loopback-bound port 8000. It must replace incoming X-Forwarded-Proto with its own verified scheme; only then set DJANGO_TRUST_PROXY_HEADERS=True. Waitress preserves forwarded headers so Django can apply this explicit trust setting. Restrict the container network to trusted services. Permit only your public hostname. Set request size and rate limits at the proxy, including login and webhook endpoints. Allow sufficient upstream response time for the existing synchronous AI workflow (180 seconds). Do not expose the WSGI port publicly.

## Release

Back up PostgreSQL and the knowledge volume first. Build and run release commands once before starting or replacing web instances:

```sh
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml run --rm web python manage.py check --deploy --fail-level ERROR
docker compose -f docker-compose.production.yml run --rm web python manage.py migrate --noinput
```

Start web using the command below. The provided image collects static files on every container start:

```sh
docker compose -f docker-compose.production.yml up -d
```

The image command collects static files, then execs Waitress. Migrations remain an explicit release step. Create your own administrator with `python manage.py createsuperuser`; never reuse development accounts or databases. Do not run seed_data on an existing production shop.

Review all deployment warnings. HSTS applies to the current host for one year. Subdomain coverage and preload are deliberately opt-in: enable DJANGO_HSTS_INCLUDE_SUBDOMAINS and DJANGO_HSTS_PRELOAD only after verifying HTTPS on every subdomain and understanding preload removal delays. Django reports W005 and W021 while these remain disabled.

## Verify and operate

- GET https://your-host/health/ must return 200 with {"status":"ok"}; database failure returns 503 without internal details. Monitor this through HTTPS.
- Check login, staff permissions, static assets, an existing customer chat, booking submission and staff confirmation in a staging environment before release.
- Check a signed WhatsApp webhook, duplicate delivery, human handover and outbound delivery status using a staging number.
- Schedule the existing `python manage.py retry_whatsapp` command every minute in the deployed environment. UNKNOWN and BLOCKED deliveries still require staff review; do not blindly retry them.
- Monitor container stderr/stdout and failed deliveries; restrict access because provider errors and existing application logs may contain customer information.
- Back up PostgreSQL daily and test restoration. Preserve the knowledge volume; it can also be rebuilt with sync_knowledge. Establish retention for webhook payloads, conversation data, logs and backups.
- Record the built image digest for each release; reuse the same image for release commands and web. Review dependency security updates regularly.
- Roll back to a retained image only after checking database migration compatibility. Restore from the verified backup when schema rollback is unsafe.

Infrastructure acceptance (TLS/proxy, PostgreSQL concurrency, real provider credentials, scheduled retry, backups and restore) must be verified on the target host before going live.
