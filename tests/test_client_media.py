import io
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from PIL import Image
from django.test import RequestFactory, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.tenants.models import Tenant, TenantMembership, MembershipRole, TenantAuditLog, UserSecurityProfile
from django.contrib.auth.models import User


def photo():
    out = io.BytesIO()
    Image.new('RGB', (256, 256), 'red').save(out, 'PNG')
    return out.getvalue()


def test_media_module_available():
    import importlib.util
    assert importlib.util.find_spec('apps.tenants.media_api') is not None


@pytest.mark.django_db
def test_private_logo_upload_and_presigned_display():
    from apps.tenants.media_api import client_media_api, client_media_url
    tenant = Tenant.objects.create(name='Media', slug='media')
    user = User.objects.create_user(username='mediaowner')
    TenantMembership.objects.create(tenant=tenant, user=user, role=MembershipRole.OWNER)
    UserSecurityProfile.objects.create(user=user, email_verified=True)
    req = RequestFactory().post('/', {'kind':'workspace_logo', 'file':SimpleUploadedFile('x.png', photo(), content_type='image/png')})
    req.user, req.tenant = user, tenant
    storage = Mock()
    storage.generate_presigned_url.return_value = 'https://signed.example/image'
    with override_settings(CLIENT_MEDIA_S3_BUCKET='private'), patch('apps.tenants.media_api.s3_client', return_value=storage):
        response = client_media_api(req)
        assert response.status_code == 200
        tenant.refresh_from_db()
        assert tenant.logo_url.startswith(f's3://private/tenants/{tenant.pk}/workspace-logo/')
        assert client_media_url(tenant) == 'https://signed.example/image'
    upload = storage.put_object.call_args.kwargs
    assert 'ACL' not in upload
    assert upload['ContentType'] == 'image/png'
    assert TenantAuditLog.objects.filter(tenant=tenant).count() == 1


def test_reject_corrupt_and_oversized_images():
    from apps.tenants.media_api import validate_image, MediaError
    for data in (b'fake png', b'x' * (5*1024*1024+1)):
        with pytest.raises(MediaError):
            validate_image(SimpleUploadedFile('x.png', data, content_type='image/png'))


def test_meta_resumable_upload_requires_explicit_success():
    from apps.whatsapp.profile_media import upload_profile_picture, ProfileMediaError
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    responses = [Mock(status_code=200), Mock(status_code=200), Mock(status_code=200)]
    for response, value in zip(responses, [{'id':'upload:abc?sig=xyz'}, {'h':'handle'}, {'success':True}]):
        response.json.return_value = value
    client.post.side_effect = responses
    cfg = {'enabled':True, 'phone_number_id':'123', 'access_token':'secret'}
    with override_settings(META_APP_ID='456'), patch('apps.whatsapp.profile_media.WhatsAppConfig.get_settings', return_value=cfg), patch('apps.whatsapp.profile_media.httpx.Client', return_value=client):
        upload_profile_picture(object(), photo(), 'image/png')
        assert client.post.call_args_list[1].kwargs['headers']['file_offset'] == '0'
        assert client.post.call_args_list[1].kwargs['headers']['Authorization'] == 'OAuth secret'
        assert client.post.call_args_list[2].kwargs['json']['profile_picture_handle'] == 'handle'
        responses[-1].json.return_value = {'success':False, 'error':{'message':'secret'}}
        client.post.side_effect = responses
        with pytest.raises(ProfileMediaError, match='Meta rejected') as exc:
            upload_profile_picture(object(), photo(), 'image/png')
        assert 'secret' not in str(exc.value)


@pytest.mark.django_db
def test_failed_meta_upload_preserves_previous_s3_photo():
    from apps.tenants.media_api import client_media_api
    from apps.whatsapp.models import WhatsAppBusinessProfile
    from apps.whatsapp.profile_media import ProfileMediaError
    tenant = Tenant.objects.create(name='MetaMedia', slug='meta-media')
    user = User.objects.create_user(username='metamedia', is_superuser=True)
    profile = WhatsAppBusinessProfile.objects.create(tenant=tenant, profile_picture_storage_key='tenants/old/photo.png')
    req = RequestFactory().post('/', {'kind':'whatsapp_profile', 'file':SimpleUploadedFile('x.png', photo(), content_type='image/png')})
    req.user, req.tenant = user, tenant
    storage = Mock()
    with override_settings(CLIENT_MEDIA_S3_BUCKET='private'), patch('apps.tenants.media_api.s3_client', return_value=storage), patch('apps.tenants.media_api.upload_profile_picture', side_effect=ProfileMediaError('Meta rejected the profile photo update.')):
        response = client_media_api(req)
    assert response.status_code == 502
    profile.refresh_from_db()
    assert profile.profile_picture_storage_key == 'tenants/old/photo.png'
    assert storage.delete_object.called
    assert not TenantAuditLog.objects.filter(tenant=tenant).exists()

@pytest.mark.django_db
def test_staff_cannot_upload_and_missing_storage_is_truthful():
    from apps.tenants.media_api import client_media_api
    tenant = Tenant.objects.create(name='Denied', slug='denied-media')
    user = User.objects.create_user(username='mediastaff')
    TenantMembership.objects.create(tenant=tenant, user=user, role=MembershipRole.STAFF)
    def request():
        req = RequestFactory().post('/', {'kind':'workspace_logo', 'file':SimpleUploadedFile('x.png', photo(), content_type='image/png')})
        req.user, req.tenant = user, tenant
        return req
    assert client_media_api(request()).status_code == 403
    user.is_superuser = True
    with override_settings(CLIENT_MEDIA_S3_BUCKET=''):
        assert client_media_api(request()).status_code == 503
    tenant.refresh_from_db()
    assert not tenant.logo_url


def test_meta_missing_app_never_simulates_success():
    from apps.whatsapp.profile_media import upload_profile_picture, ProfileMediaError
    with override_settings(META_APP_ID='', DEBUG=True), patch('apps.whatsapp.profile_media.WhatsAppConfig.get_settings', return_value={'enabled':False}):
        with pytest.raises(ProfileMediaError) as exc:
            upload_profile_picture(object(), photo(), 'image/png')
    assert exc.value.status == 503


@pytest.mark.django_db
def test_confirmed_meta_photo_uses_private_storage_preview():
    from apps.tenants.media_api import client_media_api, whatsapp_profile_media_url
    from apps.whatsapp.models import WhatsAppBusinessProfile
    tenant = Tenant.objects.create(name='Confirmed', slug='confirmed-media')
    user = User.objects.create_user(username='confirmedmedia', is_superuser=True)
    req = RequestFactory().post('/', {'kind':'whatsapp_profile', 'file':SimpleUploadedFile('x.png', photo(), content_type='image/png')})
    req.user, req.tenant = user, tenant
    storage = Mock()
    storage.generate_presigned_url.return_value = 'https://signed.example/meta'
    with override_settings(CLIENT_MEDIA_S3_BUCKET='private'), patch('apps.tenants.media_api.s3_client', return_value=storage), patch('apps.tenants.media_api.upload_profile_picture'):
        response = client_media_api(req)
        assert response.status_code == 200
        assert whatsapp_profile_media_url(tenant) == 'https://signed.example/meta'
    assert WhatsAppBusinessProfile.objects.get(tenant=tenant).profile_picture_storage_key.startswith(f'tenants/{tenant.pk}/whatsapp-profile/')
    assert TenantAuditLog.objects.filter(tenant=tenant).count() == 1

@pytest.mark.django_db
def test_meta_app_id_is_selected_tenant_configuration():
    from apps.whatsapp.models import WhatsAppConfig
    first = Tenant.objects.create(name='First app', slug='first-app')
    second = Tenant.objects.create(name='Second app', slug='second-app')
    WhatsAppConfig.objects.create(tenant=first, app_id='111')
    WhatsAppConfig.objects.create(tenant=second, app_id='222')
    with override_settings(META_APP_ID='999'):
        assert WhatsAppConfig.get_settings(tenant=first)['app_id'] == '111'
        assert WhatsAppConfig.get_settings(tenant=second)['app_id'] == '222'


def test_tenant_meta_app_id_overrides_global_upload_app():
    from apps.whatsapp.profile_media import upload_profile_picture
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    responses = [Mock(status_code=200), Mock(status_code=200), Mock(status_code=200)]
    for response, data in zip(responses, [{'id':'upload:abc'}, {'h':'handle'}, {'success':True}]):
        response.json.return_value = data
    client.post.side_effect = responses
    cfg = {'enabled':True, 'phone_number_id':'123', 'access_token':'secret', 'app_id':'111'}
    with override_settings(META_APP_ID='999'), patch('apps.whatsapp.profile_media.WhatsAppConfig.get_settings', return_value=cfg), patch('apps.whatsapp.profile_media.httpx.Client', return_value=client):
        upload_profile_picture(object(), photo(), 'image/png')
    assert client.post.call_args_list[0].args[0].endswith('/111/uploads')
def test_s3_presigning_uses_regional_endpoint_without_redirects():
    from apps.tenants.media_api import s3_client
    with override_settings(CLIENT_MEDIA_S3_REGION='ap-south-1',CLIENT_MEDIA_S3_ENDPOINT_URL=''),patch('apps.tenants.media_api.boto3.client') as client:
        s3_client()
    assert client.call_args.kwargs['endpoint_url']=='https://s3.ap-south-1.amazonaws.com'
