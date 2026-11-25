"""Encrypted, single-send transactional email jobs. No secrets in API output or logs."""
import base64
import hashlib
import ipaddress
import json
import logging
import smtplib
import socket
import sys
import threading
import uuid
from datetime import timedelta
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from .models import (
    AccountActivationToken,
    ClientOnboarding,
    EmailVerificationToken,
    PlatformServiceConfig,
    TransactionalEmail,
    User,
    VerificationPurpose,
)

logger = logging.getLogger(__name__)


def cipher():
    key = getattr(settings, 'SAAS_SECRETS_KEY', '') or base64.urlsafe_b64encode(
        hashlib.sha256(('neoriz-service-secrets-v1:' + settings.SECRET_KEY).encode()).digest()
    )
    return Fernet(key)


def seal(value):
    return cipher().encrypt(json.dumps(value).encode()).decode()


def unseal(value):
    return json.loads(cipher().decrypt(value.encode())) if value else {}


def safe_secrets(value):
    try:
        return unseal(value)
    except (InvalidToken, ValueError):
        return {}


def configuration():
    c = PlatformServiceConfig.objects.filter(pk=1).first()
    if c and c.smtp_enabled:
        return {
            'enabled': True,
            'host': c.smtp_host,
            'port': c.smtp_port,
            'username': c.smtp_username,
            'password': safe_secrets(c.encrypted_secrets).get('smtp_password', ''),
            'from_email': c.smtp_from_email,
            'security': c.smtp_security,
        }
    return {'enabled': False}


def ready():
    c = configuration()
    return bool(c.get('enabled') and c.get('host') and c.get('from_email') and (not c.get('username') or c.get('password')))


def _absolute_url(request, path: str) -> str:
    if request is not None:
        return request.build_absolute_uri(path)
    base = getattr(settings, 'SITE_URL', 'https://wapp.neorizsolutions.com').rstrip('/')
    return f"{base}{path}"


def _should_dispatch_async() -> bool:
    if 'pytest' in sys.modules or getattr(settings, 'TESTING', False):
        return False
    db_engine = settings.DATABASES.get('default', {}).get('ENGINE', '')
    if 'sqlite3' in db_engine:
        return False
    return ready()


def _dispatch_async(job_pk):
    def _runner():
        try:
            send_email_job(job_pk)
        except Exception:
            logger.exception("Background email dispatch failed for job %s", job_pk)

    threading.Thread(target=_runner, daemon=True).start()


def email_status_label(status: str) -> str:
    return {
        'PENDING': 'Queued',
        'SENDING': 'Sending via SMTP',
        'ACCEPTED': 'SMTP Accepted (mailbox delivery unconfirmed)',
        'DELIVERED': 'Delivered',
        'FAILED': 'Delivery Failed',
        'UNKNOWN': 'SMTP Outcome Uncertain',
        'EXPIRED': 'Expired / Superseded',
    }.get(status or '', status or 'Unknown')


def queue_activation(request, token, tenant=None, onboarding=None):
    url = _absolute_url(request, '/activate/' + token.token + '/')
    return queue_email(
        token.user,
        'ACTIVATION',
        'activation:' + str(token.pk),
        {'url': url},
        tenant,
        token,
        recipient=onboarding.owner_email if onboarding else token.user.email,
        onboarding=onboarding,
    )


def queue_verification_email(*, request=None, token: EmailVerificationToken, recipient: str, onboarding=None, tenant=None, user=None):
    url = _absolute_url(request, reverse('verify-email', args=[token.token]))
    return queue_email(
        user,
        'VERIFICATION',
        f"verify:{token.pk}",
        {'url': url},
        tenant=tenant,
        recipient=recipient,
        onboarding=onboarding,
        verification_token=token,
    )


def queue_recovery_email_verification(*, request=None, token: EmailVerificationToken, recipient: str, user):
    url = _absolute_url(request, reverse('verify-recovery-email', args=[token.token]))
    return queue_email(
        user,
        'RECOVERY_EMAIL_VERIFY',
        f"recovery_verify:{token.pk}",
        {'url': url},
        tenant=None,
        recipient=recipient,
        verification_token=token,
    )


def queue_email(
    user,
    purpose,
    dedup,
    payload,
    tenant=None,
    token=None,
    *,
    recipient=None,
    onboarding=None,
    verification_token=None,
):
    target_recipient = (recipient or (user.email if user else '') or '').strip()
    if not target_recipient:
        return None
    job, created = TransactionalEmail.objects.get_or_create(
        dedup_key=dedup,
        defaults={
            'tenant': tenant,
            'user': user,
            'onboarding': onboarding,
            'activation_token': token,
            'verification_token': verification_token,
            'purpose': purpose,
            'recipient': target_recipient,
            'encrypted_payload': seal(payload),
        },
    )
    if created and _should_dispatch_async():
        transaction.on_commit(lambda job_pk=job.pk: _dispatch_async(job_pk))
    return job


def validate_smtp_host(host):
    if not host or len(host) > 253 or any(x in host for x in ('/', '@', ':', ' ')) or '.' not in host:
        raise ValueError('Use a public SMTP provider hostname.')
    addresses = socket.getaddrinfo(host, None)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('SMTP must resolve to a public provider address.')


def send_email_job(pk):
    if not ready():
        return False
    # A durable SENDING claim survives interruption. Unknown outcomes are never resent automatically.
    with transaction.atomic():
        job = TransactionalEmail.objects.select_for_update().get(pk=pk)
        if job.status not in ('PENDING', 'FAILED') or job.attempts >= 3:
            return False
        job.status = 'SENDING'
        job.attempts += 1
        job.save(update_fields=['status', 'attempts', 'updated_at'])
    try:
        with transaction.atomic():
            job = TransactionalEmail.objects.select_for_update().get(pk=pk)
            if job.status != 'SENDING':
                return False
            user = User.objects.select_for_update().get(pk=job.user_id) if job.user_id else None
            onboarding = (
                ClientOnboarding.objects.select_for_update().filter(pk=job.onboarding_id).first()
                if job.onboarding_id else None
            )
            token = (
                AccountActivationToken.objects.select_for_update().filter(pk=job.activation_token_id).first()
                if job.activation_token_id else None
            )
            v_token = (
                EmailVerificationToken.objects.select_for_update().filter(pk=job.verification_token_id).first()
                if job.verification_token_id else None
            )

            now = timezone.now()
            # Pre-send purpose/recipient/expiry validation
            if job.purpose == 'ACTIVATION':
                if not user or not token or not token.is_valid:
                    job.status = 'EXPIRED'
                    job.last_error = 'Activation link expired or superseded'
                    job.save()
                    return False
                expected = onboarding.owner_email if onboarding else user.email
                if expected.casefold() != job.recipient.casefold():
                    job.status = 'EXPIRED'
                    job.last_error = 'Recipient changed'
                    job.save()
                    return False
            elif job.purpose == 'VERIFICATION':
                if not v_token or not v_token.is_valid or v_token.purpose != VerificationPurpose.EMAIL_VERIFY:
                    job.status = 'EXPIRED'
                    job.last_error = 'Verification token expired, used, or superseded'
                    job.save()
                    return False
                if v_token.intended_email and v_token.intended_email.casefold() != job.recipient.casefold():
                    job.status = 'EXPIRED'
                    job.last_error = 'Recipient email mismatch'
                    job.save()
                    return False
                if onboarding and (onboarding.approval_status == 'REJECTED' or onboarding.owner_email.casefold() != job.recipient.casefold()):
                    job.status = 'EXPIRED'
                    job.last_error = 'Onboarding recipient changed or rejected'
                    job.save()
                    return False
            elif job.purpose == 'RECOVERY_EMAIL_VERIFY':
                if not user or not v_token or not v_token.is_valid or v_token.purpose != VerificationPurpose.RECOVERY_EMAIL_VERIFY:
                    job.status = 'EXPIRED'
                    job.last_error = 'Recovery email verification link expired or superseded'
                    job.save()
                    return False
                sec = getattr(user, 'security_profile', None)
                if not sec or sec.pending_recovery_email.casefold() != job.recipient.casefold():
                    job.status = 'EXPIRED'
                    job.last_error = 'Pending recovery email changed'
                    job.save()
                    return False
            elif job.purpose == 'RECOVERY':
                if not user or job.created_at < now - timedelta(hours=1):
                    job.status = 'EXPIRED'
                    job.last_error = 'Recovery request expired'
                    job.save()
                    return False
                from .onboarding_service import resolve_recovery_destination
                dest, _ = resolve_recovery_destination(user)
                expected = dest or user.email
                if not expected or expected.casefold() != job.recipient.casefold():
                    job.status = 'EXPIRED'
                    job.last_error = 'Recovery recipient changed or unverified'
                    job.save()
                    return False
            elif user and job.purpose == 'TEST':
                if user.email and user.email.casefold() != job.recipient.casefold():
                    job.status = 'EXPIRED'
                    job.last_error = 'Recipient changed'
                    job.save()
                    return False

            data = unseal(job.encrypted_payload)
            if job.purpose == 'SUPPORT_ESCALATION':
                from .models import PlatformSupportEscalation, PlatformSupportMessage, PlatformSupportTicket
                esc_id = data.get('escalation_id')
                esc = PlatformSupportEscalation.objects.select_for_update().filter(pk=esc_id).first() if esc_id else None
                tkt = PlatformSupportTicket.objects.select_for_update().filter(pk=data.get('ticket_id')).first() if data.get('ticket_id') else None
                if esc and tkt:
                    has_public_reply = PlatformSupportMessage.objects.filter(
                        ticket=tkt,
                        sender_type='PLATFORM',
                        is_internal_note=False,
                        created_at__gte=esc.cycle_started_at,
                    ).exists()
                    still_waiting = (
                        tkt.status in ('OPEN', 'AWAITING_PLATFORM')
                        and not has_public_reply
                        and tkt.sla_cycle_started_at == esc.cycle_started_at
                        and esc.status not in ('CANCELLED', 'SENT')
                    )
                    if not still_waiting:
                        if esc.status == 'PENDING':
                            esc.status = 'CANCELLED'
                            esc.reason = 'Platform reply or resolution occurred prior to SMTP dispatch'
                            esc.save(update_fields=['status', 'reason'])
                        job.status = 'EXPIRED'
                        job.last_error = 'Support ticket answered or resolved before alert dispatch'
                        job.save()
                        return False

            c = configuration()
            if not ready():
                job.status = 'FAILED'
                job.last_error = 'SMTP configuration unavailable'
                job.save()
                if job.purpose == 'SUPPORT_ESCALATION':
                    from .models import PlatformSupportEscalation
                    PlatformSupportEscalation.objects.filter(email_job_id=job.pk, status='PENDING').update(status='FAILED')
                return False
            validate_smtp_host(c['host'])
            if job.purpose == 'VERIFICATION':
                greeting = (onboarding.owner_full_name if onboarding else (user.first_name or user.username if user else 'there'))
                subject = 'Verify your email for Neoriz WhatsApp Automation'
                body = (
                    f"Hello {greeting},\n\n"
                    f"Confirm your email address by opening this single-use link (expires {v_token.expires_at.isoformat()}):\n"
                    f"{data['url']}\n\n"
                    f"Opening the link displays a confirmation button so automated mail scanners cannot consume it.\n\n"
                    f"Neoriz Solutions"
                )
            elif job.purpose == 'ACTIVATION':
                greeting = user.first_name or user.username
                subject = 'Set up your Neoriz account'
                body = (
                    f"Hello {greeting},\n\n"
                    f"Set your password using this single-use link:\n{data['url']}\n\n"
                    f"This link expires {token.expires_at.isoformat()}. If it expires, request a fresh link from your administrator.\n\n"
                    f"Neoriz Solutions"
                )
            elif job.purpose == 'RECOVERY_EMAIL_VERIFY':
                subject = 'Verify your Neoriz recovery email address'
                body = (
                    f"Hello {user.first_name or user.username},\n\n"
                    f"Confirm this email address as your verified account recovery destination (expires {v_token.expires_at.isoformat()}):\n"
                    f"{data['url']}\n\n"
                    f"If you did not request this change, you can ignore this message."
                )
            elif job.purpose == 'RECOVERY':
                subject = 'Reset your Neoriz password'
                body = (
                    f"Use this password-reset link (expires in 1 hour):\n{data['url']}\n\n"
                    f"If you did not request this, ignore this email."
                )
            elif job.purpose == 'SUPPORT_ESCALATION':
                subject = data.get('subject') or 'URGENT: Client support ticket 10-minute SLA escalation'
                body = data.get('body') or 'An unanswered client support ticket exceeded 10 minutes.'
            elif job.purpose == 'BILLING_REMINDER':
                subject = data.get('subject') or 'Neoriz Subscription Renewal & Billing Notice'
                body = data.get('body') or 'Please review your subscription renewal status in Neoriz Billing.'
            else:
                subject = 'Neoriz email configuration test'
                body = 'Neoriz successfully connected to your configured SMTP provider.'

            connection = get_connection(
                'django.core.mail.backends.smtp.EmailBackend',
                host=c['host'],
                port=c['port'],
                username=c['username'],
                password=c['password'],
                use_tls=c['security'] == 'TLS',
                use_ssl=c['security'] == 'SSL',
                timeout=15,
            )
            msg = EmailMessage(subject, body, c['from_email'], [job.recipient], connection=connection)
            count = msg.send(fail_silently=False)
            job.status = 'ACCEPTED' if count == 1 else 'FAILED'
            job.last_error = '' if count == 1 else 'SMTP did not confirm acceptance'
            if count == 1 and msg.extra_headers.get('Message-ID'):
                job.provider_message_id = str(msg.extra_headers.get('Message-ID'))[:180]
            job.save()
            if job.purpose == 'SUPPORT_ESCALATION':
                from .models import PlatformSupportEscalation
                PlatformSupportEscalation.objects.filter(email_job_id=job.pk).update(
                    status='SENT' if count == 1 else 'FAILED',
                    sent_at=timezone.now() if count == 1 else None,
                )
            return count == 1
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPConnectError, smtplib.SMTPRecipientsRefused, ValueError, socket.gaierror):
        TransactionalEmail.objects.filter(pk=pk).update(
            status='FAILED',
            last_error='SMTP configuration, authentication, connection or recipient was rejected',
            updated_at=timezone.now(),
        )
        from .models import PlatformSupportEscalation
        PlatformSupportEscalation.objects.filter(email_job_id=pk, status='PENDING').update(status='FAILED')
    except Exception:
        TransactionalEmail.objects.filter(pk=pk).update(
            status='UNKNOWN',
            last_error='SMTP outcome uncertain; inspect provider logs before retrying',
            updated_at=timezone.now(),
        )
    return False


def process_emails(limit=20):
    TransactionalEmail.objects.filter(
        status='SENDING',
        updated_at__lt=timezone.now() - timedelta(minutes=5),
    ).update(status='UNKNOWN', last_error='Interrupted SMTP send; inspect provider logs')
    if not ready():
        return 0
    ids = list(
        TransactionalEmail.objects.filter(status='PENDING')
        .order_by('created_at')
        .values_list('pk', flat=True)[:limit]
    )
    return sum(int(send_email_job(pk)) for pk in ids)
