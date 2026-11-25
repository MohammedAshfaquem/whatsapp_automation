"""
Hardened Signed Outbound Webhook Service for Neoriz WhatsApp Automation.
Enforces strict SSRF protection, DNS rebinding prevention, TLS SNI verification,
thread-safe IP pinning, and durable at-least-once delivery with exponential backoff and jitter.
"""
import hashlib
import hmac
import ipaddress
import json
import logging
import random
import re
import socket
import uuid
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpcore
import httpx
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.crm.models import WebhookEndpoint, WebhookDeliveryLog

logger = logging.getLogger(__name__)

FORBIDDEN_HOST_PATTERNS = [
    re.compile(r'^(localhost|0\.0\.0\.0|127\.\d+\.\d+\.\d+)$', re.IGNORECASE),
    re.compile(r'^(169\.254\.169\.254|metadata\.google\.internal|instance-data)$', re.IGNORECASE),
    re.compile(r'^(.*\.local|.*\.internal|.*\.localhost)$', re.IGNORECASE),
]


def is_destination_ip_safe(ip_str: str) -> Tuple[bool, str]:
    """
    Validates an individual IPv4 or IPv6 address against private, loopback,
    link-local, multicast, reserved, and cloud-metadata addresses.
    """
    try:
        ip = ipaddress.ip_address(ip_str)

        # Unpack IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1 or ::ffff:169.254.169.254)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped

        # Explicit Cloud Metadata IP guards first
        ip_text = str(ip).lower()
        if ip_text in ('169.254.169.254', 'fd00:ec2::254'):
            return False, f"Cloud metadata destination {ip} is forbidden."

        if ip.is_loopback:
            return False, f"Loopback destination {ip} is forbidden."
        if ip.is_link_local:
            return False, f"Link-local destination {ip} is forbidden."
        if ip.is_private:
            return False, f"Private network destination {ip} is forbidden."
        if ip.is_multicast:
            return False, f"Multicast destination {ip} is forbidden."
        if ip.is_unspecified:
            return False, f"Unspecified destination {ip} is forbidden."
        if ip.is_reserved:
            return False, f"Reserved destination {ip} is forbidden."

        return True, ""
    except ValueError as exc:
        return False, f"Invalid IP representation: {exc}"


def validate_webhook_url(url: str) -> Tuple[bool, str, List[str]]:
    """
    Validates that a webhook destination URL is safe to connect to:
    - Scheme must be HTTPS (or HTTP in explicit debug mode)
    - No embedded user credentials
    - Permitted destination ports (443, 8443; 80 in debug only)
    - Resolves all A and AAAA DNS records and rejects any private/loopback/cloud-metadata addresses
    Returns (is_safe, error_message, resolved_ip_list).
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string.", []

    try:
        parsed = urlparse(url)
    except Exception as exc:
        return False, f"Malformed URL: {exc}", []

    # 1. Scheme check: HTTPS enforced by default
    is_debug = getattr(settings, 'DEBUG', False)
    if parsed.scheme != 'https':
        if not (is_debug and parsed.scheme == 'http'):
            return False, f"Webhook URLs must use HTTPS. Insecure scheme '{parsed.scheme}' rejected.", []

    # 2. Embedded credentials check
    if parsed.username or parsed.password:
        return False, "URLs with embedded credentials (user:pass@host) are forbidden.", []

    hostname = (parsed.hostname or '').strip().lower()
    if not hostname:
        return False, "Missing hostname in destination URL.", []

    # 3. Port check
    try:
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    except ValueError:
        return False, 'Invalid destination port.', []
    permitted_ports = {443, 8443}
    if is_debug:
        permitted_ports.add(80)
    if port not in permitted_ports:
        return False, f"Port {port} is not in permitted webhook ports {sorted(permitted_ports)}.", []

    # 4. Hostname pattern blocklist
    for pattern in FORBIDDEN_HOST_PATTERNS:
        if pattern.match(hostname):
            return False, f"Hostname '{hostname}' matches forbidden internal destination pattern.", []

    # 5. Resolve all A and AAAA DNS addresses
    resolved_ips: List[str] = []

    # Check if the hostname is directly an IP literal
    try:
        ipaddress.ip_address(hostname)
        resolved_ips.append(hostname)
    except ValueError:
        # Domain name: resolve via socket
        try:
            addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            for item in addr_info:
                sockaddr = item[4]
                ip_addr = sockaddr[0]
                if ip_addr not in resolved_ips:
                    resolved_ips.append(ip_addr)
        except socket.gaierror:
            return False, f"Could not resolve destination hostname '{hostname}'.", []

    if not resolved_ips:
        return False, f"No IP addresses resolved for hostname '{hostname}'.", []

    # 6. Validate every resolved IP
    for ip in resolved_ips:
        is_safe, reason = is_destination_ip_safe(ip)
        if not is_safe:
            return False, f"SSRF Security Violation: {reason}", []

    return True, "", resolved_ips


def is_ssrf_safe_url(url: str) -> bool:
    """
    SSRF helper function maintaining backward compatibility with existing tests.
    """
    safe, _, _ = validate_webhook_url(url)
    return safe


class PinnedDNSBackend(httpcore.SyncBackend):
    """
    Thread-safe network backend that pins TCP connections to pre-validated IP addresses.
    Eliminates TOCTOU DNS rebinding without any global monkeypatching of socket.getaddrinfo.
    """
    def __init__(self, pinned_map: Dict[str, str]):
        super().__init__()
        self.pinned_map = pinned_map

    def connect_tcp(self, host: str, port: int, timeout: Optional[float] = None,
                    local_address: Optional[str] = None, socket_options = None):
        target_host = self.pinned_map.get(host, host)
        return super().connect_tcp(
            target_host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options
        )


@contextmanager
def pinned_dns_resolver(pinned_map: Dict[str, str]):
    """
    Backward-compatibility context manager for external callers.
    """
    yield


def enqueue_outbound_webhooks(tenant, event_type: str, event_id: str, payload_data: dict) -> List[WebhookDeliveryLog]:
    """
    Persists durable webhook delivery jobs for all active endpoints subscribed to event_type.
    Uses deterministic delivery IDs and idempotent get_or_create to prevent duplicate enqueueing.
    """
    if not event_id:
        event_id = uuid.uuid4().hex

    endpoints = WebhookEndpoint.objects.filter(tenant=tenant, is_active=True)
    matching = [
        ep for ep in endpoints
        if not ep.subscribed_events or event_type in ep.subscribed_events or '*' in ep.subscribed_events
    ]

    payload_json = json.dumps(payload_data, default=str, sort_keys=True)
    payload_digest = hashlib.sha256(payload_json.encode('utf-8')).hexdigest()
    created_deliveries = []

    for ep in matching:
        delivery_id = hashlib.sha256(f"{ep.id}:{event_id}".encode()).hexdigest()[:32]
        delivery, _ = WebhookDeliveryLog.objects.get_or_create(
            endpoint=ep,
            event_id=event_id,
            defaults={
                'event_type': event_type,
                'delivery_id': delivery_id,
                'state': 'PENDING',
                'payload_digest': payload_digest,
                'payload_data': payload_data,
                'next_attempt_at': timezone.now(),
                'attempts': 0,
                'max_attempts': 5,
            }
        )
        created_deliveries.append(delivery)

    return created_deliveries


def execute_webhook_delivery_attempt(delivery: WebhookDeliveryLog) -> bool:
    """
    Executes a single delivery attempt for a WebhookDeliveryLog record.
    Signs payload with HMAC-SHA256, connects safely using thread-safe PinnedDNSBackend,
    streams response body reading at most 2048 bytes, and handles retries with jitter.
    """
    endpoint = delivery.endpoint
    safe, error_msg, resolved_ips = validate_webhook_url(endpoint.target_url)

    if not safe:
        delivery.state = 'FAILED'
        delivery.is_success = False
        delivery.status_code = 400
        delivery.error_message = f"SSRF Blocked: {error_msg}"
        delivery.response_body = "Destination blocked by outbound security policy."
        delivery.save(update_fields=['state', 'is_success', 'status_code', 'error_message', 'response_body'])
        return False

    parsed = urlparse(endpoint.target_url)
    target_hostname = (parsed.hostname or '').lower()
    pinned_ip = resolved_ips[0] if resolved_ips else target_hostname

    payload_bytes = json.dumps(delivery.payload_data or {}, default=str, sort_keys=True).encode('utf-8')
    timestamp_str = str(int(timezone.now().timestamp()))

    # Stripe/Slack style signature: t=timestamp,v1=hmac
    signed_payload = f"{timestamp_str}.".encode('utf-8') + payload_bytes
    v1_sig = hmac.new(endpoint.signing_secret.encode('utf-8'), signed_payload, hashlib.sha256).hexdigest()
    raw_sig = hmac.new(endpoint.signing_secret.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()

    headers = {
        'Content-Type': 'application/json',
        'X-Neoriz-Event': delivery.event_type,
        'X-Neoriz-Delivery-Id': delivery.delivery_id or '',
        'X-Neoriz-Timestamp': timestamp_str,
        'X-Neoriz-Signature': f"sha256={raw_sig}",  # Backward-compatible with existing tests
        'X-Neoriz-Signature-V1': f"t={timestamp_str},v1={v1_sig}",
        'User-Agent': 'Neoriz-Outbound-Webhook/1.0',
    }

    delivery.attempts += 1
    status_code = None
    response_snippet = ""
    success = False

    try:
        transport = httpx.HTTPTransport(verify=True)
        transport._pool = httpcore.ConnectionPool(
            network_backend=PinnedDNSBackend({target_hostname: pinned_ip})
        )
        with httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0),
            follow_redirects=False,
        ) as client:
            with client.stream("POST", endpoint.target_url, content=payload_bytes, headers=headers) as res:
                status_code = res.status_code
                chunks = []
                total_bytes = 0
                for chunk in res.iter_bytes(chunk_size=1024):
                    chunks.append(chunk)
                    total_bytes += len(chunk)
                    if total_bytes >= 2048:
                        break
                raw_snippet = b"".join(chunks)[:2048]
                response_snippet = raw_snippet.decode("utf-8", errors="replace")
                success = (200 <= status_code < 300)

    except Exception as exc:
        response_snippet = f"Network Exception: {str(exc)[:500]}"
        logger.warning("Webhook delivery attempt %d failed to %s: %s", delivery.attempts, endpoint.target_url, exc)

    delivery.status_code = status_code
    delivery.response_body = response_snippet
    delivery.is_success = success

    if success:
        delivery.state = 'DELIVERED'
        delivery.error_message = ''
    else:
        # Determine retry policy
        is_client_error = status_code is not None and (400 <= status_code < 500 and status_code != 429)
        if is_client_error or delivery.attempts >= delivery.max_attempts:
            delivery.state = 'DEAD_LETTER' if delivery.attempts >= delivery.max_attempts else 'FAILED'
            delivery.error_message = response_snippet
        else:
            # Recoverable: apply exponential backoff with jitter
            backoff_seconds = min(300, (2 ** delivery.attempts) * 5 + random.uniform(0.5, 3.0))
            delivery.state = 'PENDING'
            delivery.next_attempt_at = timezone.now() + timezone.timedelta(seconds=backoff_seconds)
            delivery.error_message = response_snippet

    # If delivery was claimed by a specific token, ensure we only update if token still matches
    update_fields = [
        'attempts', 'status_code', 'response_body', 'is_success',
        'state', 'error_message', 'next_attempt_at'
    ]
    if delivery.claim_token:
        updated = WebhookDeliveryLog.objects.filter(
            id=delivery.id,
            claim_token=delivery.claim_token
        ).update(
            attempts=delivery.attempts,
            status_code=delivery.status_code,
            response_body=delivery.response_body,
            is_success=delivery.is_success,
            state=delivery.state,
            error_message=delivery.error_message,
            next_attempt_at=delivery.next_attempt_at,
            lease_expires_at=None,
            claim_token=''
        )
        if not updated:
            logger.warning("Delivery %d lease lost or expired before completion (claim_token mismatch)", delivery.id)
    else:
        delivery.save(update_fields=update_fields)

    return success


def reclaim_expired_webhook_leases() -> int:
    """
    Reclaims webhook delivery jobs stuck in PROCESSING past their lease_expires_at.
    Returns them to PENDING if attempts < max_attempts, or DEAD_LETTER if exceeded.
    """
    now = timezone.now()
    reclaimed = WebhookDeliveryLog.objects.filter(
        state='PROCESSING',
        lease_expires_at__lt=now,
        attempts__lt=models.F('max_attempts')
    ).update(
        state='PENDING',
        lease_expires_at=None,
        claim_token='',
        error_message='Processing lease expired; returned to pending queue.'
    )
    dead_lettered = WebhookDeliveryLog.objects.filter(
        state='PROCESSING',
        lease_expires_at__lt=now,
        attempts__gte=models.F('max_attempts')
    ).update(
        state='DEAD_LETTER',
        lease_expires_at=None,
        claim_token='',
        error_message='Processing lease expired and maximum attempts reached.'
    )
    return reclaimed + dead_lettered


def process_pending_webhook_deliveries(batch_size: int = 25) -> int:
    """
    Worker routine to claim and process queued outbound webhook deliveries atomically with lease tokens.
    """
    now = timezone.now()
    claim_token = uuid.uuid4().hex

    with transaction.atomic():
        pending_ids = list(
            WebhookDeliveryLog.objects.filter(
                state='PENDING',
                next_attempt_at__lte=now
            )
            .select_for_update(skip_locked=True)
            .values_list('id', flat=True)[:batch_size]
        )

        if not pending_ids:
            return 0

        # Mark as PROCESSING with a 2-minute lease and unique claim_token
        WebhookDeliveryLog.objects.filter(id__in=pending_ids).update(
            state='PROCESSING',
            lease_expires_at=now + timezone.timedelta(minutes=2),
            claim_token=claim_token
        )

    processed_count = 0
    for delivery_id in pending_ids:
        try:
            delivery = WebhookDeliveryLog.objects.select_related('endpoint').get(id=delivery_id)
            execute_webhook_delivery_attempt(delivery)
            processed_count += 1
        except Exception as exc:
            logger.error("Error dispatching delivery %d: %s", delivery_id, exc)

    return processed_count


def dispatch_outbound_webhook(tenant, event_type: str, payload_data: dict) -> list:
    """
    Authoritative outbound webhook entrypoint.
    Enqueues delivery jobs and executes the first attempt synchronously.
    """
    event_id = hashlib.sha256(f"{tenant.id}:{event_type}:{timezone.now().timestamp()}".encode()).hexdigest()[:24]
    deliveries = enqueue_outbound_webhooks(tenant, event_type, event_id, payload_data)
    results = []

    for d in deliveries:
        success = execute_webhook_delivery_attempt(d)
        results.append({
            'endpoint_id': d.endpoint_id,
            'delivery_id': d.delivery_id,
            'success': success,
            'status_code': d.status_code
        })

    return results
