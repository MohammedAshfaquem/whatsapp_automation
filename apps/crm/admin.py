from django.contrib import admin
from apps.tenants.admin import TenantScopedAdminMixin
from .models import (
    Company,
    Pipeline,
    DealStage,
    Deal,
    DealStageHistory,
    Activity,
    ContactNote,
    ContactMergeAudit
)


@admin.register(Company)
class CompanyAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'tenant', 'industry', 'domain', 'phone', 'owner', 'created_at')
    list_filter = ('tenant', 'industry', 'created_at')
    search_fields = ('name', 'domain', 'phone', 'industry')


class DealStageInline(admin.TabularInline):
    model = DealStage
    extra = 1
    fields = ('name', 'order', 'probability', 'is_won', 'is_lost')


@admin.register(Pipeline)
class PipelineAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'tenant', 'is_default', 'is_active', 'created_at')
    list_filter = ('tenant', 'is_default', 'is_active')
    inlines = [DealStageInline]


@admin.register(DealStage)
class DealStageAdmin(admin.ModelAdmin):
    list_display = ('name', 'pipeline', 'order', 'probability', 'is_won', 'is_lost')
    list_filter = ('pipeline__tenant', 'pipeline', 'is_won', 'is_lost')
    ordering = ('pipeline', 'order')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return qs.none()
        return qs.filter(pipeline__tenant=tenant)


class DealStageHistoryInline(admin.TabularInline):
    model = DealStageHistory
    extra = 0
    readonly_fields = ('from_stage', 'to_stage', 'changed_by', 'notes', 'created_at')
    can_delete = False


@admin.register(Deal)
class DealAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'tenant', 'contact', 'company', 'pipeline', 'stage', 'amount', 'currency', 'owner', 'won_at', 'lost_at')
    list_filter = ('tenant', 'pipeline', 'stage', 'currency', 'owner', 'created_at')
    search_fields = ('title', 'contact__name', 'contact__phone_number', 'company__name')
    inlines = [DealStageHistoryInline]


@admin.register(Activity)
class ActivityAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'activity_type', 'tenant', 'status', 'priority', 'due_date', 'assigned_to', 'contact', 'deal')
    list_filter = ('tenant', 'activity_type', 'status', 'priority', 'assigned_to', 'due_date')
    search_fields = ('title', 'notes', 'contact__name', 'deal__title')


@admin.register(ContactNote)
class ContactNoteAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('contact', 'tenant', 'author', 'created_at')
    list_filter = ('tenant', 'author', 'created_at')
    search_fields = ('content', 'contact__name', 'contact__phone_number')


@admin.register(ContactMergeAudit)
class ContactMergeAuditAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('primary_contact', 'merged_phone', 'tenant', 'performed_by', 'created_at')
    list_filter = ('tenant', 'created_at')
    readonly_fields = ('tenant', 'primary_contact', 'merged_phone', 'merged_name', 'performed_by', 'details', 'created_at')
