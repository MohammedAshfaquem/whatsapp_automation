"""Tenant-scoped profile image uploads backed by private S3 objects."""
import io
import uuid
import warnings
from urllib.parse import urlsplit
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.http import require_http_methods
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantAuditLog, AuditLogAction
from apps.tenants.capabilities import can_perform_action
from apps.whatsapp.models import WhatsAppBusinessProfile, WhatsAppConfig
from apps.whatsapp.profile_media import upload_profile_picture, ProfileMediaError


class MediaError(Exception):
    pass


def s3_client():
    return boto3.client('s3', region_name=getattr(settings, 'CLIENT_MEDIA_S3_REGION', '') or None,
                        endpoint_url=getattr(settings, 'CLIENT_MEDIA_S3_ENDPOINT_URL', '') or f"https://s3.{getattr(settings, 'CLIENT_MEDIA_S3_REGION', '') or 'ap-south-1'}.amazonaws.com",
                        config=Config(connect_timeout=5, read_timeout=15, retries={'max_attempts':2}, signature_version='s3v4'))


def validate_image(upload):
    if not upload or upload.size > 5 * 1024 * 1024:
        raise MediaError('Choose a JPEG or PNG image up to 5 MB.')
    data = upload.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise MediaError('Choose a JPEG or PNG image up to 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('JPEG', 'PNG') or min(image.size) < 64 or max(image.size) > 4096 or image.width * image.height > 16_000_000:
                    raise MediaError('Use a JPEG or PNG between 64 and 4096 pixels per side.')
                mime_type = 'image/png' if image.format == 'PNG' else 'image/jpeg'
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise MediaError('The image could not be decoded. Choose a valid JPEG or PNG.') from None
    return data, mime_type


def client_media_url(tenant):
    value = tenant.logo_url or ''
    if not value.startswith('s3://'):
        return tenant.effective_logo_url
    parsed = urlsplit(value)
    bucket = getattr(settings, 'CLIENT_MEDIA_S3_BUCKET', '')
    key = parsed.path.lstrip('/')
    if parsed.netloc != bucket or not key.startswith(f'tenants/{tenant.pk}/workspace-logo/'):
        return ''
    try:
        return s3_client().generate_presigned_url('get_object', Params={'Bucket':bucket, 'Key':key}, ExpiresIn=900)
    except (BotoCoreError, ClientError):
        return ''


def whatsapp_profile_media_url(tenant, profile=None):
    profile = profile or WhatsAppBusinessProfile.objects.filter(tenant=tenant).first()
    if not profile:
        return ''
    key = profile.profile_picture_storage_key
    bucket = getattr(settings, 'CLIENT_MEDIA_S3_BUCKET', '')
    if key and bucket and key.startswith(f'tenants/{tenant.pk}/whatsapp-profile/'):
        try:
            return s3_client().generate_presigned_url('get_object', Params={'Bucket':bucket, 'Key':key}, ExpiresIn=900)
        except (BotoCoreError, ClientError):
            pass
    return profile.profile_picture_url or ''


@require_http_methods(['GET', 'POST'])
@transaction.atomic
def client_media_api(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return JsonResponse({'error':'Authentication required'}, status=401)
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        return JsonResponse({'error':'Active tenant context required'}, status=400)
    if not request.user.is_superuser:
        membership = TenantMembership.objects.filter(tenant=tenant, user=request.user, is_active=True).first()
        if not membership or membership.role not in (TenantRole.OWNER, TenantRole.ADMIN):
            return JsonResponse({'error':'Owner or Administrator access required.'}, status=403)
        kind = request.POST.get('kind') if request.method == 'POST' else request.GET.get('kind', 'workspace_logo')
        allowed, reason = can_perform_action(request.user, tenant, 'whatsapp_settings', 'edit' if request.method == 'POST' else 'view')
        if not allowed:
            return JsonResponse({'error':'Permission denied', 'reason':reason}, status=403)
    if request.method == 'GET':
        kind = request.GET.get('kind', 'workspace_logo')
        if kind not in ('workspace_logo', 'whatsapp_profile'):
            return JsonResponse({'error':'Choose workspace_logo or whatsapp_profile.'}, status=400)
        cfg = WhatsAppConfig.get_settings(tenant=tenant)
        meta_ready = bool((cfg.get('app_id') or getattr(settings, 'META_APP_ID', '')) and cfg.get('enabled') and cfg.get('access_token') and cfg.get('phone_number_id'))
        profile = WhatsAppBusinessProfile.objects.filter(tenant=tenant).first() if kind == 'whatsapp_profile' else None
        return JsonResponse({'kind':kind, 'url':whatsapp_profile_media_url(tenant, profile) if kind == 'whatsapp_profile' else client_media_url(tenant), 'expires_in':900, 'configured':bool(getattr(settings, 'CLIENT_MEDIA_S3_BUCKET', '')) and (meta_ready if kind == 'whatsapp_profile' else True)})
    kind = request.POST.get('kind', '')
    if kind not in ('workspace_logo', 'whatsapp_profile'):
        return JsonResponse({'error':'Choose workspace_logo or whatsapp_profile.'}, status=400)
    try:
        data, mime_type = validate_image(request.FILES.get('file'))
        bucket = getattr(settings, 'CLIENT_MEDIA_S3_BUCKET', '')
        if not bucket:
            return JsonResponse({'error':'Private image storage is not configured.'}, status=503)
        if kind == 'whatsapp_profile':
            # Serialize provider updates and active preview changes for this tenant.
            Tenant.objects.select_for_update().get(pk=tenant.pk)
        folder = 'whatsapp-profile' if kind == 'whatsapp_profile' else 'workspace-logo'
        key = f'tenants/{tenant.pk}/{folder}/{uuid.uuid4().hex}.{"png" if mime_type == "image/png" else "jpg"}'
        storage = s3_client()
        storage.put_object(Bucket=bucket, Key=key, Body=data, ContentType=mime_type, ServerSideEncryption='AES256')
        url = storage.generate_presigned_url('get_object', Params={'Bucket':bucket, 'Key':key}, ExpiresIn=900)
        if kind == 'whatsapp_profile':
            try:
                upload_profile_picture(tenant, data, mime_type)
            except ProfileMediaError:
                try:
                    storage.delete_object(Bucket=bucket, Key=key)
                except (BotoCoreError, ClientError):
                    pass
                raise
            profile, _ = WhatsAppBusinessProfile.objects.get_or_create(tenant=tenant)
            profile.profile_picture_storage_key = key
            profile.save(update_fields=['profile_picture_storage_key'])
        else:
            tenant.logo_url = f's3://{bucket}/{key}'
            tenant.logo = None
            tenant.save(update_fields=['logo_url', 'logo'])
        TenantAuditLog.objects.create(tenant=tenant, actor=request.user, action=AuditLogAction.TENANT_STATUS_CHANGED,
                                      summary='Workspace logo updated' if kind == 'workspace_logo' else 'WhatsApp profile photo updated on Meta', details={'kind':kind})
        return JsonResponse({'kind':kind, 'url':url, 'status':'META_SYNCED' if kind == 'whatsapp_profile' else 'SAVED', 'expires_in':900, 'meta_synced':kind == 'whatsapp_profile',
                             'message':'Profile photo updated on Meta. Sync the live profile to refresh its display.' if kind == 'whatsapp_profile' else 'Workspace logo saved.'})
    except MediaError as exc:
        return JsonResponse({'error':str(exc)}, status=400)
    except ProfileMediaError as exc:
        return JsonResponse({'error':str(exc)}, status=exc.status)
    except (BotoCoreError, ClientError):
        return JsonResponse({'error':'Private image storage is unavailable. Please retry.'}, status=503)
