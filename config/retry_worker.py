"""Run the existing durable delivery retry command once per minute."""
import logging
import os
import signal
from threading import Event

import django
from django.core.management import call_command
from django.db import close_old_connections


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    stopped = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    logger = logging.getLogger(__name__)
    while not stopped.is_set():
        try:
            close_old_connections()
            call_command('retry_whatsapp')
        except Exception:
            logger.exception('Delivery retry failed; trying again next minute')
        finally:
            close_old_connections()
        stopped.wait(60)


if __name__ == '__main__':
    main()
