from django import forms
from django.contrib.auth.models import User
from apps.chatbot.models import Customer, ContactLifecycleStatus, ContactSource
from apps.services.models import Service
from apps.business.models import Product
from .models import (
    Company,
    Pipeline,
    DealStage,
    Deal,
    Activity,
    ActivityType,
    ActivityPriority,
    ContactNote
)


class ContactForm(forms.ModelForm):
    tags_string = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. VIP, Retail, Prospect (comma-separated)'
        }),
        help_text="Comma-separated tags"
    )

    class Meta:
        model = Customer
        fields = [
            'name',
            'phone_number',
            'email',
            'company',
            'owner',
            'lifecycle_status',
            'source',
            'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Full Name'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+919876543210'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'email@example.com'}),
            'company': forms.Select(attrs={'class': 'form-select'}),
            'owner': forms.Select(attrs={'class': 'form-select'}),
            'lifecycle_status': forms.Select(attrs={'class': 'form-select'}),
            'source': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Initial contact notes...'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['company'].queryset = Company.objects.filter(tenant=tenant)
            self.fields['owner'].queryset = User.objects.filter(
                tenant_memberships__tenant=tenant,
                tenant_memberships__is_active=True
            ).distinct()
        if self.instance and self.instance.pk and self.instance.tags:
            self.fields['tags_string'].initial = ", ".join(self.instance.tags)

    def clean_tags_string(self):
        val = self.cleaned_data.get('tags_string', '')
        if val:
            return [t.strip() for t in val.split(',') if t.strip()]
        return []


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            'name',
            'domain',
            'phone',
            'industry',
            'address',
            'owner',
            'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Acme Corp'}),
            'domain': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. acme.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. +91 11 23456789'}),
            'industry': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Hospitality, Retail'}),
            'address': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'Full address'}),
            'owner': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Company background...'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['owner'].queryset = User.objects.filter(
                tenant_memberships__tenant=tenant,
                tenant_memberships__is_active=True
            ).distinct()


class DealForm(forms.ModelForm):
    class Meta:
        model = Deal
        fields = [
            'title',
            'contact',
            'company',
            'pipeline',
            'stage',
            'owner',
            'amount',
            'currency',
            'product',
            'service',
            'expected_close_date',
            'probability',
            'requirements_summary',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Website Revamp + POS Setup'}),
            'contact': forms.Select(attrs={'class': 'form-select'}),
            'company': forms.Select(attrs={'class': 'form-select'}),
            'pipeline': forms.Select(attrs={'class': 'form-select'}),
            'stage': forms.Select(attrs={'class': 'form-select'}),
            'owner': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '50000.00', 'step': '0.01'}),
            'currency': forms.TextInput(attrs={'class': 'form-input', 'value': 'INR'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'service': forms.Select(attrs={'class': 'form-select'}),
            'expected_close_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'probability': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '10-100', 'min': '0', 'max': '100'}),
            'requirements_summary': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Customer problem statement or requirements...'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['contact'].queryset = Customer.objects.filter(tenant=tenant)
            self.fields['company'].queryset = Company.objects.filter(tenant=tenant)
            self.fields['pipeline'].queryset = Pipeline.objects.filter(tenant=tenant)
            self.fields['stage'].queryset = DealStage.objects.filter(pipeline__tenant=tenant)
            self.fields['owner'].queryset = User.objects.filter(
                tenant_memberships__tenant=tenant,
                tenant_memberships__is_active=True
            ).distinct()
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant, is_active=True)
            self.fields['service'].queryset = Service.objects.filter(tenant=tenant, is_active=True)


class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = [
            'activity_type',
            'title',
            'due_date',
            'priority',
            'assigned_to',
            'contact',
            'deal',
            'company',
            'notes',
        ]
        widgets = {
            'activity_type': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Schedule online demo with founder'}),
            'due_date': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'contact': forms.Select(attrs={'class': 'form-select'}),
            'deal': forms.Select(attrs={'class': 'form-select'}),
            'company': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Agenda, call outcome, or action items...'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['contact'].queryset = Customer.objects.filter(tenant=tenant)
            self.fields['company'].queryset = Company.objects.filter(tenant=tenant)
            self.fields['deal'].queryset = Deal.objects.filter(tenant=tenant)
            self.fields['assigned_to'].queryset = User.objects.filter(
                tenant_memberships__tenant=tenant,
                tenant_memberships__is_active=True
            ).distinct()


class ContactNoteForm(forms.ModelForm):
    class Meta:
        model = ContactNote
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Add internal team note (never visible to customer)...',
                'required': 'required'
            })
        }


class ContactImportForm(forms.Form):
    csv_file = forms.FileField(
        label="Select Contacts CSV File",
        widget=forms.FileInput(attrs={'class': 'form-input', 'accept': '.csv'})
    )
    duplicate_action = forms.ChoiceField(
        choices=[
            ('skip', 'Skip duplicates (Keep existing records untouched)'),
            ('update', 'Update existing contacts with imported details'),
            ('error', 'Halt import if duplicates are detected'),
        ],
        initial='skip',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
