from django.contrib import admin
from .models import FAQ, KnowledgeDocument, KnowledgeSyncStatus

@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'category', 'is_active', 'updated_at')
    list_filter = ('category', 'is_active', 'created_at')
    search_fields = ('question', 'answer', 'category')
    list_editable = ('is_active',)

@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'is_active', 'updated_at')
    list_filter = ('category', 'is_active', 'created_at')
    search_fields = ('title', 'content')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('is_active',)

@admin.register(KnowledgeSyncStatus)
class KnowledgeSyncStatusAdmin(admin.ModelAdmin):
    list_display = ('source_type', 'source_id', 'status', 'last_synced_at', 'updated_at')
    list_filter = ('source_type', 'status')
    search_fields = ('vector_id', 'last_error')
    readonly_fields = ('created_at', 'updated_at')
