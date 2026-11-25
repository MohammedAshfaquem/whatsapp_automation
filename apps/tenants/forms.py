import re
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import PlanTier, Tenant, TenantRole, TenantInvitation
from apps.business.models import BusinessProfile
from apps.whatsapp.models import WhatsAppConfig
from .onboarding_service import OnboardingError, is_synthetic_email, normalize_email_safe, validate_whatsapp_e164, USERNAME_RE

User = get_user_model()


class SignupForm(forms.Form):
    full_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Your Full Name',
            'required': True,
            'autocomplete': 'name',
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'name@company.com',
            'required': True,
            'autocomplete': 'email',
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Create a strong password (min 8 chars)',
            'required': True,
            'autocomplete': 'new-password',
        })
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Confirm your password',
            'required': True,
            'autocomplete': 'new-password',
        })
    )
    business_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Business or Organization Name',
            'required': True,
            'autocomplete': 'organization',
        })
    )
    phone = forms.CharField(
        required=False,
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '+91 98765 43210 (Optional)',
            'autocomplete': 'tel',
        })
    )
    plan = forms.ModelChoiceField(
        queryset=PlanTier.objects.filter(is_published=True).order_by('ordering'),
        empty_label=None,
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )
    terms_accepted = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-checkbox',
        })
    )
    marketing_consent = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-checkbox',
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email or '@' not in email:
            raise ValidationError("Please provide a valid work email address.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('confirm_password')

        if p1 and p2 and p1 != p2:
            self.add_error('confirm_password', "Passwords do not match.")

        if p1:
            try:
                validate_password(p1)
            except ValidationError as e:
                self.add_error('password', e)

        return cleaned_data


class OnboardingProfileForm(forms.ModelForm):
    contact_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'contact@company.com'})
    )
    website = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://example.com'})
    )
    business_hours = forms.CharField(
        required=False,
        label='Business Hours',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Mon - Sat: 9:00 AM - 7:00 PM'})
    )
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'City, State, Country'})
    )

    class Meta:
        model = BusinessProfile
        fields = ['shop_name', 'contact_phone', 'address']
        widgets = {
            'shop_name': forms.TextInput(attrs={'class': 'form-input', 'required': True}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-input', 'required': True}),
            'address': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'City, State, Country'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.working_hours:
            self.fields['business_hours'].initial = self.instance.working_hours

    def save(self, commit=True):
        instance = super().save(commit=False)
        bh = self.cleaned_data.get('business_hours')
        if bh:
            instance.working_hours = bh
        if commit:
            instance.save()
        return instance


class OnboardingWhatsAppForm(forms.ModelForm):
    is_active = forms.BooleanField(
        required=False,
        label="Enable WhatsApp Automation",
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'})
    )

    class Meta:
        model = WhatsAppConfig
        fields = ['phone_number_id', 'business_account_id', 'verify_token', 'app_secret', 'access_token', 'is_enabled']
        widgets = {
            'phone_number_id': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. 1432169266641522'}),
            'business_account_id': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. 1170352185515741'}),
            'verify_token': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Your custom webhook secret'}),
            'app_secret': forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Meta App Secret', 'render_value': True}),
            'access_token': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'System User Permanent Access Token'}),
            'is_enabled': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['is_active'].initial = self.instance.is_enabled

    def save(self, commit=True):
        instance = super().save(commit=False)
        if 'is_active' in self.cleaned_data:
            instance.is_enabled = bool(self.cleaned_data['is_active'])
        if commit:
            instance.save()
        return instance


class OnboardingTeamInviteForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'colleague@company.com', 'required': True})
    )
    role = forms.ChoiceField(
        choices=TenantRole.choices,
        initial=TenantRole.STAFF,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class ClientRegistrationForm(forms.Form):
    """
    Public approval-gated client registration form (Entry Point A).
    Deliberately does NOT collect a password at registration time.
    """
    business_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. Acme Services Pvt Ltd',
            'required': True,
            'autocomplete': 'organization',
        })
    )
    owner_full_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. Aarav Menon',
            'required': True,
            'autocomplete': 'name',
        })
    )
    owner_email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'owner@company.com',
            'required': True,
            'autocomplete': 'email',
        })
    )
    desired_username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. acme_owner',
            'required': True,
            'autocomplete': 'username',
        })
    )
    whatsapp_number = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '+919876543210 (Optional, E.164 format)',
            'autocomplete': 'tel',
        })
    )
    requested_plan = forms.ModelChoiceField(
        queryset=PlanTier.objects.filter(is_published=True).order_by('ordering'),
        required=False,
        empty_label='Select plan (recommended during review)',
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    notes = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={
            'class': 'form-input',
            'rows': 2,
            'placeholder': 'Optional notes about team size or WhatsApp onboarding timeline...',
        })
    )
    terms_accepted = forms.BooleanField(
        required=True,
        error_messages={'required': 'You must agree to the Terms of Service and Privacy Policy.'},
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'})
    )
    marketing_consent = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'})
    )

    def clean_owner_email(self):
        raw = self.cleaned_data.get('owner_email', '')
        try:
            normalized = normalize_email_safe(raw)
        except OnboardingError as exc:
            raise ValidationError(exc.message)
        if is_synthetic_email(normalized):
            raise ValidationError("Please enter a valid deliverable business email address.")
        return normalized

    def clean_desired_username(self):
        un = (self.cleaned_data.get('desired_username') or '').strip()
        if not USERNAME_RE.match(un):
            raise ValidationError("Username must be 3–150 characters using letters, numbers, dots, underscores, +, or hyphens.")
        return un

    def clean_whatsapp_number(self):
        raw = self.cleaned_data.get('whatsapp_number', '')
        try:
            return validate_whatsapp_e164(raw, required=False)
        except OnboardingError as exc:
            raise ValidationError(exc.message)
