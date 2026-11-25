"""Public password recovery using Django's expiring user-bound token mechanism."""
import hashlib
import uuid
from datetime import timedelta
from django import forms
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetConfirmView, PasswordResetCompleteView
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import User, RecoveryThrottle, TenantAuditLog, AuditLogAction
from .email_service import queue_email
from .onboarding_service import resolve_recovery_destination, revoke_user_sessions


class RecoveryForm(forms.Form):
    email = forms.CharField(
        max_length=254,
        label='Recovery Email or Username',
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'email'})
    )


class RecoveryPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control', 'maxlength': 1024, 'autocomplete': 'new-password'})


@never_cache
@require_http_methods(['GET', 'POST'])
def request_recovery(request):
    form = RecoveryForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        raw_lookup = form.cleaned_data['email'].strip().lower()
        key = hashlib.sha256(raw_lookup.encode()).hexdigest()
        with transaction.atomic():
            window, _ = RecoveryThrottle.objects.get_or_create(pk=key)
            window = RecoveryThrottle.objects.select_for_update().get(pk=key)
            if window.window_started_at < timezone.now() - timedelta(hours=1):
                window.attempts = 0
                window.window_started_at = timezone.now()
            if window.attempts < 3:
                window.attempts += 1
                window.save()
                # Match via verified recovery_email, internal identifier, unique email, or exact username
                candidates = list(
                    User.objects.filter(
                        is_active=True,
                        security_profile__recovery_email__iexact=raw_lookup,
                        security_profile__recovery_email_verified=True,
                    ).distinct()[:2]
                )
                if not candidates:
                    candidates = list(User.objects.filter(email__iexact=raw_lookup, is_active=True)[:2])
                if not candidates:
                    candidates = list(User.objects.filter(security_profile__internal_identifier__iexact=raw_lookup, is_active=True)[:2])
                if not candidates:
                    candidates = list(User.objects.filter(username__iexact=raw_lookup, is_active=True)[:2])

                if len(candidates) == 1:
                    user = candidates[0]
                    if user.has_usable_password():
                        dest, _ = resolve_recovery_destination(user)
                        if dest:
                            token = default_token_generator.make_token(user)
                            url = request.build_absolute_uri(
                                reverse(
                                    'password-reset-confirm',
                                    kwargs={'uidb64': urlsafe_base64_encode(force_bytes(user.pk)), 'token': token},
                                )
                            )
                            queue_email(
                                user,
                                'RECOVERY',
                                f"recovery:{key}:{window.attempts}:{uuid.uuid4().hex[:8]}",
                                {'url': url},
                                recipient=dest,
                            )
        return redirect('password-reset-done')
    return render(request, 'tenants/recovery_form.html', {'form': form})


class RecoveryConfirmView(PasswordResetConfirmView):
    template_name = 'tenants/recovery_confirm.html'
    form_class = RecoveryPasswordForm
    success_url = reverse_lazy('password-reset-complete')

    def form_valid(self, form):
        response = super().form_valid(form)
        if getattr(self, 'user', None):
            revoke_user_sessions(self.user)
            TenantAuditLog.objects.create(
                tenant=None,
                actor=self.user,
                action=AuditLogAction.CREDENTIALS_UPDATED,
                summary=f"Password recovered and active sessions revoked for {self.user.username}",
                details={'user_id': self.user.pk},
            )
        return response


class RecoveryCompleteView(PasswordResetCompleteView):
    template_name = 'tenants/recovery_complete.html'
