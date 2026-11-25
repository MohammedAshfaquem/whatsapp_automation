from django.contrib import admin
from apps.tenants.admin import TenantScopedAdminMixin
from .models import BusinessProfile, Product, ProductCapability, ProductIntegration, ProductPricingPlan


@admin.register(BusinessProfile)
class BusinessProfileAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('shop_name', 'contact_phone', 'is_active', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('shop_name', 'contact_phone', 'address', 'service_areas')
    fieldsets = (
        ('Basic Information', {
            'fields': ('shop_name', 'contact_phone', 'address', 'google_maps_url', 'is_active')
        }),
        ('Operations & Working Hours', {
            'fields': ('working_hours', 'holiday_information', 'service_areas')
        }),
        ('Technical Capability', {
            'fields': ('supported_ac_types', 'supported_ac_brands')
        }),
        ('Policies & Commercials', {
            'fields': ('warranty_policies', 'accepted_payment_methods', 'general_service_policies')
        }),
    )


class ProductCapabilityInline(admin.TabularInline):
    model = ProductCapability
    extra = 1
    fields = ('name', 'category', 'status', 'description', 'source_reference', 'is_active')


class ProductIntegrationInline(admin.TabularInline):
    model = ProductIntegration
    extra = 1
    fields = ('name', 'status', 'description', 'is_active')


class ProductPricingPlanInline(admin.TabularInline):
    model = ProductPricingPlan
    extra = 1
    fields = ('name', 'billing_frequency', 'price_amount', 'currency', 'is_quote_based', 'setup_fee', 'is_active')


@admin.register(Product)
class ProductAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'pricing_status', 'last_verified_at', 'is_active', 'updated_at')
    list_filter = ('pricing_status', 'is_active', 'last_verified_at')
    search_fields = ('name', 'tagline', 'description', 'intended_customers', 'aliases')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductCapabilityInline, ProductIntegrationInline, ProductPricingPlanInline]
    fieldsets = (
        ('Overview', {
            'fields': ('name', 'slug', 'tagline', 'description', 'intended_customers', 'aliases', 'is_active')
        }),
        ('Capabilities & Boundaries', {
            'fields': ('limitations',)
        }),
        ('Deployment & Operations', {
            'fields': ('deployment_onboarding', 'support_info', 'demo_process')
        }),
        ('Pricing & Commercials', {
            'fields': ('pricing_status', 'pricing_details')
        }),
        ('Verification & Sources', {
            'fields': ('source_references', 'last_verified_at')
        }),
    )


@admin.register(ProductCapability)
class ProductCapabilityAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'category', 'status', 'is_active')
    list_filter = ('status', 'product', 'category', 'is_active')
    search_fields = ('name', 'description', 'source_reference')


@admin.register(ProductIntegration)
class ProductIntegrationAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'status', 'is_active')
    list_filter = ('status', 'product', 'is_active')
    search_fields = ('name', 'description')


@admin.register(ProductPricingPlan)
class ProductPricingPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'price_amount', 'billing_frequency', 'is_quote_based', 'is_active')
    list_filter = ('is_quote_based', 'product', 'is_active')
    search_fields = ('name', 'description')

