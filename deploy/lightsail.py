"""Deployment helper. Run from any directory using Python 3.12+."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / '.env.lightsail'
COMPOSE = ['docker', 'compose', '--env-file', str(ENV), '-f', str(ROOT / 'docker-compose.lightsail.yml')]


def compose(*args, **kwargs):
    return subprocess.run(COMPOSE + list(args), cwd=ROOT, check=True, **kwargs)


def initialize(domain):
    if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', domain):
        raise ValueError('Use a hostname only, such as wapp.neorizsolutions.com')
    # Exclusive creation: never rotate credentials under an existing database.
    fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as output:
        output.write(f'''APP_DOMAIN={domain}
DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}
POSTGRES_PASSWORD={secrets.token_hex(32)}
GEMINI_API_KEY=
GEMINI_CHAT_MODEL=gemini-3.5-flash-lite
GEMINI_EMBEDDING_MODEL=text-embedding-004
WHATSAPP_ENABLED=False
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_BOOKING_FLOW_ID=
WHATSAPP_TYPING_INDICATOR_ENABLED=True
WHATSAPP_BOOKING_STATUS_TEMPLATE=
WHATSAPP_TEMPLATE_LANGUAGE=en
META_APP_SECRET=
DEFAULT_CURRENCY=INR
''')
    print('Created .env.lightsail with unique secrets. Edit provider credentials on the server; do not share this file.')


def backup():
    directory = ROOT / '.backups'
    directory.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = directory / f'wapp-{stamp}.dump'
    temporary = path.with_suffix('.partial')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as output:
            compose('exec', '-T', 'db', 'pg_dump', '-U', 'wapp', '-d', 'wapp', '-Fc', stdout=output)
        with temporary.open('rb') as source:
            compose('exec', '-T', 'db', 'pg_restore', '--list', stdin=source, stdout=subprocess.DEVNULL)
        temporary.rename(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    print(f'Backup saved: {path}. Copy it to encrypted off-instance storage.')


def deploy(backend_only=False):
    compose('config', '--quiet')
    compose('build', 'web')
    compose('up', '-d', '--wait', 'db')
    backup()
    compose('run', '--rm', 'web', 'python', 'manage.py', 'check', '--deploy', '--fail-level', 'ERROR')
    # Maintenance window prevents writes during schema changes.
    compose('stop', 'proxy', 'retry', 'web')
    compose('run', '--rm', 'web', 'python', 'manage.py', 'migrate', '--noinput')
    services = ['web', 'retry'] if backend_only else ['web', 'retry', 'proxy']
    compose('up', '-d', '--wait', '--wait-timeout', '240', *services)
    print('Backend started; DNS and public HTTPS deferred.' if backend_only else
          'Containers started. Verify public HTTPS, login and signed WhatsApp messages before going live.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'deploy', 'backup', 'status', 'admin'])
    parser.add_argument('--domain', default='wapp.neorizsolutions.com')
    parser.add_argument('--backend-only', action='store_true', help='Start API, database and retry worker without the public HTTPS proxy.')
    args = parser.parse_args()
    try:
        if args.action == 'init':
            initialize(args.domain)
        elif not ENV.is_file():
            parser.error('Run init first.')
        elif args.action == 'deploy':
            deploy(backend_only=args.backend_only)
        elif args.action == 'backup':
            backup()
        elif args.action == 'status':
            compose('ps')
        elif args.action == 'admin':
            compose('exec', 'web', 'python', 'manage.py', 'createsuperuser')
    except (ValueError, FileExistsError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\nDeployment stopped; inspect container logs before retrying.\n')


if __name__ == '__main__':
    main()
