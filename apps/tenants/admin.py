from django.contrib import admin
from .models import (
    Tenant, TenantMembership, TenantInvitation, TenantAuditLog,
    PlanTier, TenantSubscription, LegalDocument, LegalAcceptance,
    OnboardingProgress, DemoRequest, SubscriptionStatus,
    UserSecurityProfile, TenantFeatureOverride, TenantMonthlyUsage,
    StaffAccessRequest, AccountActivationToken
)


class TenantScopedAdminMixin:
    """
    Ensures that for non-superusers:
    1. Querysets are strictly scoped to request.tenant.
    2. Newly saved objects are automatically assigned to request.tenant.
    3. Foreign key choices in forms are restricted to objects belonging to request.tenant.
    4. Cross-tenant view, edit, or delete is strictly blocked.
    """
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return qs.none()
        if hasattr(self.model, 'tenant'):
            return qs.filter(tenant=tenant)
        return qs

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            tenant = getattr(request, 'tenant', None)
            if tenant and hasattr(obj, 'tenant') and not obj.tenant_id:
                obj.tenant = tenant
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and hasattr(db_field.remote_field.model, 'tenant'):
            tenant = getattr(request, 'tenant', None)
            if tenant:
                kwargs["queryset"] = db_field.remote_field.model.objects.filter(tenant=tenant)
            else:
                kwargs["queryset"] = db_field.remote_field.model.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_view_permission(self, request, obj=None):
        if not super().has_view_permission(request, obj):
            return False
        if obj and not request.user.is_superuser and hasattr(obj, 'tenant'):
            tenant = getattr(request, 'tenant', None)
            return bool(tenant and obj.tenant_id == tenant.id)
        return True

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj and not request.user.is_superuser and hasattr(obj, 'tenant'):
            tenant = getattr(request, 'tenant', None)
            return bool(tenant and obj.tenant_id == tenant.id)
        return True

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj and not request.user.is_superuser and hasattr(obj, 'tenant'):
            tenant = getattr(request, 'tenant', None)
            return bool(tenant and obj.tenant_id == tenant.id)
        return True


@admin.register(PlanTier)
class PlanTierAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'price_display_mode', 'monthly_price', 'max_staff', 'max_contacts', 'is_published', 'is_featured', 'ordering')
    list_filter = ('price_display_mode', 'is_published', 'is_featured')
    search_fields = ('name', 'code')
    ordering = ('ordering', 'name')

    def has_module_permission(self, request):
        return request.user.is_superuser


@admin.register(TenantSubscription)
class TenantSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'requested_plan', 'effective_plan', 'status', 'start_date', 'approved_by', 'created_at')
    list_filter = ('status', 'effective_plan', 'requested_plan')
    search_fields = ('tenant__name', 'notes')
    readonly_fields = ('created_at', 'updated_at')
    actions = ['approve_subscriptions', 'suspend_subscriptions']

    def has_module_permission(self, request):
        return request.user.is_superuser

    @admin.action(description="Approve selected subscriptions")
    def approve_subscriptions(self, request, queryset):
        for sub in queryset:
            sub.approve(request.user)
        self.message_user(request, f"{queryset.count()} subscription(s) approved.")

    @admin.action(description="Suspend selected subscriptions")
    def suspend_subscriptions(self, request, queryset):
        count = queryset.update(status=SubscriptionStatus.SUSPENDED)
        self.message_user(request, f"{count} subscription(s) suspended.")


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'plan', 'is_active', 'created_at')
    list_filter = ('is_active', 'plan')
    search_fields = ('name', 'slug')
    readonly_fields = ('created_at', 'updated_at')
    actions = ['activate_tenants', 'suspend_tenants']

    def has_module_permission(self, request):
        return request.user.is_superuser

    @admin.action(description="Activate selected tenants")
    def activate_tenants(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} tenant(s) activated.")

    @admin.action(description="Suspend selected tenants")
    def suspend_tenants(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} tenant(s) suspended.")


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'tenant', 'role', 'is_active', 'created_at')
    list_filter = ('tenant', 'role', 'is_active')
    search_fields = ('user__username', 'user__email', 'tenant__name')
    autocomplete_fields = ('user', 'tenant')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        tenant = getattr(request, 'tenant', None)
        return qs.filter(tenant=tenant) if tenant else qs.none()

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        membership = getattr(request, 'membership', None)
        return bool(membership and membership.is_owner_or_admin)


@admin.register(TenantInvitation)
class TenantInvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'tenant', 'role', 'is_accepted', 'expires_at', 'created_at')
    list_filter = ('tenant', 'role', 'is_accepted')
    search_fields = ('email', 'tenant__name')
    readonly_fields = ('token', 'created_at', 'accepted_at')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        tenant = getattr(request, 'tenant', None)
        return qs.filter(tenant=tenant) if tenant else qs.none()

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        membership = getattr(request, 'membership', None)
        return bool(membership and membership.is_owner_or_admin)


@admin.register(OnboardingProgress)
class OnboardingProgressAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'current_step', 'is_completed', 'completed_at', 'updated_at')
    list_filter = ('is_completed', 'current_step')
    search_fields = ('tenant__name',)

    def has_module_permission(self, request):
        return request.user.is_superuser


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'doc_type', 'version', 'status', 'effective_date')
    list_filter = ('doc_type', 'status')
    search_fields = ('title', 'version')

    def has_module_permission(self, request):
        return request.user.is_superuser


@admin.register(LegalAcceptance)
class LegalAcceptanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'document', 'accepted_at', 'ip_address')
    list_filter = ('document__doc_type',)
    search_fields = ('user__username', 'user__email', 'document__title')
    readonly_fields = ('user', 'document', 'accepted_at', 'ip_address')

    def has_module_permission(self, request):
        return request.user.is_superuser


@admin.register(DemoRequest)
class DemoRequestAdmin(admin.ModelAdmin):
    list_display = ('name', 'company_name', 'email', 'phone', 'team_size', 'status', 'routed_to_tenant', 'created_at')
    list_filter = ('status', 'routed_to_tenant')
    search_fields = ('name', 'company_name', 'email', 'phone')


@admin.register(TenantAuditLog)
class TenantAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'tenant', 'actor', 'action', 'summary')
    list_filter = ('tenant', 'action', 'created_at')
    search_fields = ('summary', 'tenant__name', 'actor__username')
    readonly_fields = ('tenant', 'actor', 'action', 'summary', 'details', 'ip_address', 'created_at')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        tenant = getattr(request, 'tenant', None)
        return qs.filter(tenant=tenant) if tenant else qs.none()

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        membership = getattr(request, 'membership', None)
        return bool(membership and membership.is_owner_or_admin)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserSecurityProfile)
class UserSecurityProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'email_verified', 'email_verified_at', 'is_trusted_seed', 'created_at')
    list_filter = ('email_verified', 'is_trusted_seed')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')

    def has_module_permission(self, request):
        return request.user.is_superuser


@admin.register(TenantFeatureOverride)
class TenantFeatureOverrideAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'feature_key', 'override', 'reason', 'created_by', 'updated_at')
    list_filter = ('override', 'feature_key')
    search_fields = ('tenant__name', 'feature_key', 'reason')

    def has_module_permission(self, request):
        return request.user.is_superuser


@admin.register(TenantMonthlyUsage)
class TenantMonthlyUsageAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('tenant', 'year', 'month', 'outbound_messages_sent', 'outbound_messages_attempted', 'inbound_messages_received', 'updated_at')
    list_filter = ('year', 'month')
    search_fields = ('tenant__name',)
    readonly_fields = ('tenant', 'year', 'month', 'created_at', 'updated_at')


@admin.register(StaffAccessRequest)
class StaffAccessRequestAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'tenant', 'role', 'status', 'requested_by', 'created_at')
    list_filter = ('status', 'role', 'tenant')
    search_fields = ('full_name', 'email', 'tenant__name')
    readonly_fields = ('created_at', 'updated_at')

    def has_module_permission(self, request):
        return request.user.is_superuser


@admin.register(AccountActivationToken)
class AccountActivationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'purpose', 'expires_at', 'is_used', 'used_at', 'created_at')
    list_filter = ('is_used', 'purpose')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('token_digest', 'created_at')

    def has_module_permission(self, request):
        return request.user.is_superuser


from .models import PlatformSupportTicket, PlatformSupportMessage, PlatformSupportEscalation


@admin.register(PlatformSupportTicket)
class PlatformSupportTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'tenant', 'subject', 'category', 'priority', 'status', 'sla_cycle_started_at', 'escalations_count', 'updated_at')
    list_filter = ('status', 'priority', 'category')
    search_fields = ('ticket_number', 'subject', 'tenant__name')
    readonly_fields = ('created_at', 'updated_at')

    def has_module_permission(self, request):
        return request.user.is_superuser


@admin.register(PlatformSupportMessage)
class PlatformSupportMessageAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'sender', 'sender_type', 'is_internal_note', 'created_at')
    list_filter = ('sender_type', 'is_internal_note')
    readonly_fields = ('created_at',)

    def has_module_permission(self, request):
        return request.user.is_superuser


@admin.register(PlatformSupportEscalation)
class PlatformSupportEscalationAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'cycle_started_at', 'escalated_to_email', 'status', 'sent_at', 'created_at')
    list_filter = ('status',)
    readonly_fields = ('created_at', 'sent_at')

    def has_module_permission(self, request):
        return request.user.is_superuser
