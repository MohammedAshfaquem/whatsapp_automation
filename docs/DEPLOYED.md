# Deployed backend — 16 November 2026

- AWS account: ending 6390.
- Region: Mumbai, ap-south-1.
- Instance: wapp-api-production, Ubuntu 24.04, small_3_1 (2 GB RAM, 2 GB swap).
- Cost: USD 12/month before taxes and additional usage. The new account rejected the initially approved USD 24/month plan.
- Static IPv4: 52.66.43.85.
- Application directory: /opt/wapp.
- Containers: Django API (Waitress), PostgreSQL 16, existing WhatsApp delivery retry command every minute.
- Database and API health verified; 37 migrations applied. Database starts empty except for the generated administrator.
- API binding: 127.0.0.1:8000 on the instance. PostgreSQL has no published host port.
- Cloudflare DNS and the public HTTPS proxy are deferred at the user's request. There is no public API URL yet.
- Gemini and WhatsApp provider credentials are not configured. Live WhatsApp is disabled until configuration and acceptance checks.
- Daily database backups: 02:30 UTC / 08:00 India time, in /opt/wapp/.backups. With user authorization, the initial backup was downloaded to local .backups/lightsail-wapp-20261116T082653884327Z.dump and its SHA-256 matched the server file. Recurring off-instance backup automation remains to be configured.
- SSH key: local ignored .deployment-secrets/wapp-production.pem. SSH firewall allows the deployment computer's public IP; update it if that IP changes.
- Administrator credentials: local ignored .deployment-secrets/admin-credentials.json. Do not commit or send these files through chat.

## Server verification

```sh
cd /opt/wapp
python3 deploy/lightsail.py status
curl --fail -H 'Host: wapp.neorizsolutions.com' -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/health/
```

To enable public domain access later, point the Cloudflare A record for wapp to 52.66.43.85, confirm DNS/proxy TLS settings, then start the proxy with `docker compose --env-file .env.lightsail -f docker-compose.lightsail.yml up -d proxy`. Verify the public HTTPS health endpoint before connecting a frontend or registering the Meta webhook.
