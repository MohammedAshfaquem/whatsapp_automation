from django import forms
from django.contrib.auth.models import User
from apps.services.models import Service, PriceType
from apps.chatbot.models import Customer

class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter username or phone number',
            'autocomplete': 'username',
            'required': 'required',
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter password',
            'autocomplete': 'current-password',
            'required': 'required',
        })
    )

class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = [
            'name',
            'category',
            'price_type',
            'price_amount',
            'max_price',
            'currency',
            'estimated_duration',
            'contact_number',
            'description',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Jet Pump Deep Cleaning Service',
                'required': 'required',
            }),
            'category': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Maintenance, Repair, Gas Refill',
                'required': 'required',
            }),
            'price_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'price_amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. 799.00',
                'step': '0.01',
                'required': 'required',
            }),
            'max_price': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Optional max price for range (e.g. 1499.00)',
                'step': '0.01',
            }),
            'currency': forms.TextInput(attrs={
                'class': 'form-input',
                'value': 'INR',
            }),
            'estimated_duration': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., 45-60 mins or 1.5 hours',
            }),
            'contact_number': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., +91 98765 43210 (WhatsApp dedicated helpline)',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Describe what is included in this service...',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-checkbox',
            }),
        }

class CustomerCreationForm(forms.Form):
    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g., Chloe Wilson',
            'required': 'required',
        })
    )
    phone_number = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g., +919876543210',
            'required': 'required',
        })
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g., chloe@example.com',
        })
    )
    portal_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Password for customer to log into portal (optional)',
        }),
        help_text="If provided, a login account will be generated with username = phone number"
    )
    tagged_services = forms.ModelMultipleChoiceField(
        queryset=Service.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'service-checkbox-grid',
        }),
        help_text="Select services to tag to this customer. Customer will only see these services."
    )

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number'].strip()
        if Customer.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError(f"Customer with phone number {phone} already exists.")
        if User.objects.filter(username=phone).exists():
            raise forms.ValidationError('An account already uses this phone number. Ask an administrator to link it safely.')
        return phone

class StaffUserCreationForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g., john_staff',
            'required': 'required',
        })
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g., John',
        })
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g., Doe',
        })
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g., john@acshop.com',
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Create strong password',
            'required': 'required',
        })
    )
    role = forms.ChoiceField(
        choices=[
            ('staff', 'Staff Member (Can manage services, tag customers, view chats & bookings)'),
            ('admin', 'Superadmin (Full administrative access and user management)'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username


class TenantInviteForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'colleague@example.com',
            'required': 'required',
        })
    )
    role = forms.ChoiceField(
        choices=[
            ('ADMIN', 'Tenant Administrator'),
            ('STAFF', 'Tenant Staff'),
        ],
        initial='STAFF',
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class PlatformTenantCreateForm(forms.Form):
    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. Apex Tech Solutions',
            'required': 'required',
        })
    )
    plan = forms.ChoiceField(
        choices=[
            ('STARTER', 'Starter Plan'),
            ('PRO', 'Professional Plan'),
            ('ENTERPRISE', 'Enterprise Plan'),
        ],
        initial='STARTER',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    owner_username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'apexadmin',
            'required': 'required',
        })
    )
    owner_email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'admin@apextech.com',
            'required': 'required',
        })
    )
    owner_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Secure temporary password',
            'required': 'required',
        })
    )
