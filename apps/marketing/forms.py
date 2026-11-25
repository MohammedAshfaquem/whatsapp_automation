from django import forms
from apps.tenants.models import DemoRequest


class DemoRequestForm(forms.ModelForm):
    class Meta:
        model = DemoRequest
        fields = ['name', 'email', 'phone', 'company_name', 'team_size', 'primary_interest', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Your Full Name',
                'required': True,
                'autocomplete': 'name',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'work@company.com',
                'required': True,
                'autocomplete': 'email',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+91 98765 43210',
                'required': True,
                'autocomplete': 'tel',
            }),
            'company_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Company or Business Name',
                'required': True,
                'autocomplete': 'organization',
            }),
            'team_size': forms.Select(choices=[
                ('', 'Select Sales / Support Team Size'),
                ('1-5', '1 - 5 Agents'),
                ('6-15', '6 - 15 Agents'),
                ('16-50', '16 - 50 Agents'),
                ('50+', '50+ Enterprise Agents'),
            ], attrs={
                'class': 'form-select',
            }),
            'primary_interest': forms.Select(choices=[
                ('', 'Primary Focus Area'),
                ('whatsapp_crm', 'WhatsApp Multi-Agent Shared Inbox + CRM'),
                ('ai_assistant', '24/7 AI Knowledge Assistant & Auto-Reply'),
                ('lead_generation', 'Lead Qualification & Consultation Booking'),
                ('tablo_integration', 'TABLO Restaurant Software Inquiry'),
                ('custom_enterprise', 'Custom Solution & Integration'),
            ], attrs={
                'class': 'form-select',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Tell us about your current customer inquiry process or specific requirements...',
            }),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        # Basic validation: ensure digits present
        digits = [c for c in phone if c.isdigit()]
        if len(digits) < 7:
            raise forms.ValidationError("Please provide a valid phone number with country code.")
        return phone
