import json
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import TenantAuditLog, UserSecurityProfile, ClientOnboarding
from .onboarding_service import OnboardingError, initiate_recovery_email_change
from django.db import transaction

@login_required
@require_http_methods(['GET','POST'])
def account_profile_api(request):
    user=request.user
    if request.method=='POST':
        try:
            data=json.loads(request.body)
            if not isinstance(data,dict) or set(data)-{'full_name','email'}:
                raise ValueError('Only display name and email may be changed here.')
            name=data.get('full_name',user.get_full_name()).strip()
            email=data.get('email',user.email).strip().lower()
            if not name or len(name)>300:raise ValueError('Enter a display name under 300 characters.')
            validate_email(email)
            if len(email)>254:raise ValueError('Email is too long.')
        except (ValueError,TypeError,AttributeError,ValidationError):
            return JsonResponse({'error':'Enter a valid name/email. Role and login credentials cannot be changed here.'},status=400)
        first,_,last=name.partition(' ')
        if len(first)>150 or len(last)>150:return JsonResponse({'error':'Name is too long.'},status=400)
        changed_email = email.casefold() != user.email.casefold()
        with transaction.atomic():
            user.first_name=first;user.last_name=last;user.email=email
            user.save(update_fields=['first_name','last_name','email'])
            if changed_email:
                security = UserSecurityProfile.get_or_create_for_user(user)
                security.email_verified = False
                security.email_verified_at = None
                security.save(update_fields=['email_verified', 'email_verified_at'])
        TenantAuditLog.objects.create(tenant=getattr(request,'tenant',None),actor=user,action='TENANT_STATUS_CHANGED',summary='User updated their account profile',details={'user_id':user.pk})
    security = UserSecurityProfile.get_or_create_for_user(user)
    return JsonResponse({
        'username':user.username,
        'full_name':user.get_full_name() or user.username,
        'email':user.email,
        'email_verified': security.email_verified,
        'email_verification_required':not security.email_verified and not security.skip_mailbox_gate,
        'internal_identifier': security.internal_identifier or '',
        'is_synthetic_identifier': security.is_synthetic_identifier,
        'recovery_email': security.recovery_email,
        'recovery_email_verified': security.recovery_email_verified,
        'pending_recovery_email': security.pending_recovery_email,
        'password_change_supported':True,
    })


@login_required
@require_http_methods(['POST'])
def recovery_email_api(request):
    try:
        data = json.loads(request.body or '{}')
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
    new_email = (data.get('recovery_email') or '').strip()
    try:
        res = initiate_recovery_email_change(user=request.user, new_recovery_email=new_email, request=request)
    except OnboardingError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code, **exc.extra}, status=exc.status)
    return JsonResponse({
        'status': 'verification_sent',
        'pending_recovery_email': res['pending_recovery_email'],
        'email_job_id': res['email_job_id'],
        'message': f"Verification link sent to {res['pending_recovery_email']}. Your previous recovery destination remains active until verified.",
    })


@login_required
@require_http_methods(['POST'])
def account_password_api(request):
    error = {'error': 'Unable to change password. Check your current password and use a stronger matching new password.'}
    try:
        if len(request.body) > 16384:
            raise ValueError
        data = json.loads(request.body)
        fields = {'current_password', 'new_password', 'new_password_confirmation'}
        if not isinstance(data, dict) or set(data) != fields:
            raise ValueError
        if any(not isinstance(data[key], str) or not 1 <= len(data[key]) <= 1024 for key in fields):
            raise ValueError
        if not request.user.check_password(data['current_password']):
            raise ValueError
        if data['new_password'] != data['new_password_confirmation']:
            raise ValueError
        validate_password(data['new_password'], request.user)
    except (ValueError, TypeError, UnicodeDecodeError, ValidationError):
        return JsonResponse(error, status=400)
    with transaction.atomic():
        request.user.set_password(data['new_password'])
        request.user.save(update_fields=['password'])
        TenantAuditLog.objects.create(
            tenant=getattr(request, 'tenant', None), actor=request.user,
            action='TENANT_STATUS_CHANGED', summary='User changed their account password',
            details={'user_id': request.user.pk},
        )
    update_session_auth_hash(request, request.user)
    return JsonResponse({'success': True})

@require_http_methods(['POST'])
def client_activation_link_api(request, tenant_id):
    """Regenerate a pending client's setup link; never reset an active owner's password."""
    from django.contrib.auth.models import User
    from django.shortcuts import get_object_or_404
    from django.urls import reverse
    from .models import Tenant, TenantMembership, AccountActivationToken
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({'error': 'Super Admin access required.'}, status=403)
    tenant = get_object_or_404(Tenant, pk=tenant_id)
    member = TenantMembership.objects.filter(tenant=tenant, role='OWNER', is_active=True).first()
    if not member:
        return JsonResponse({'error': 'No active client owner found.'}, status=409)
    with transaction.atomic():
        owner = User.objects.select_for_update().get(pk=member.user_id)
        if owner.is_superuser or owner.has_usable_password():
            return JsonResponse({'error': 'This owner already has a password. Activation links are only for pending accounts.'}, status=409)
        onboarding = ClientOnboarding.objects.filter(tenant=tenant).first()
        if onboarding and not onboarding.email_verified:
            return JsonResponse({'error': "Owner's email address must be verified before issuing a password setup link."}, status=409)
        token = AccountActivationToken.create_for_user(owner)
        url = request.build_absolute_uri(reverse('activate-account', args=[token.token]))
        from .email_service import queue_activation
        queue_activation(request, token, tenant, onboarding=onboarding)
        TenantAuditLog.objects.create(tenant=tenant, actor=request.user, action='CREDENTIALS_UPDATED', summary='Pending client activation link regenerated', details={'user_id': owner.pk})
    response = JsonResponse({'activation_url': url, 'owner_username': owner.username, 'expires_at': token.expires_at.isoformat()})
    response['Cache-Control'] = 'no-store'
    return response
