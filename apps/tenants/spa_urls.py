from django.urls import path
from . import saas_api, spa_api, account_api, platform_operations, media_api, client_operations, broadcast_api, onboarding_api, support_api, inbox_enhancements

urlpatterns = [
    path('workspace/tools/<str:resource>/', saas_api.workspace_tools),
    path('platform/tools/<str:resource>/', saas_api.platform_tools),
    path('platform/tenants/<int:tenant_id>/activation/', account_api.client_activation_link_api, name='api-client-activation-link'),
    path('crm/campaigns/preview/', broadcast_api.campaign_preview_api, name='api-crm-campaigns-preview'),
    path('crm/campaigns/<int:campaign_id>/', broadcast_api.campaign_detail_api, name='api-campaign-detail'),
    path('whatsapp/templates/manage/', broadcast_api.templates_api, name='api-template-management'),
    path('whatsapp/templates/<int:template_id>/submit/', broadcast_api.submit_template_api, name='api-template-submit'),
    path('client/operations/<str:resource>/', client_operations.client_operations, name='api-client-operations'),
    path('client/operations/<str:resource>/<int:pk>/', client_operations.client_operations, name='api-client-operation-detail'),
    path('settings/media/', media_api.client_media_api, name='api-client-media'),
    path('auth/password/', account_api.account_password_api, name='api-account-password'),
    path('auth/profile/', account_api.account_profile_api, name='api-account-profile'),
    path('auth/recovery-email/', account_api.recovery_email_api, name='api-account-recovery-email'),
    path('platform/operations/<str:resource>/', platform_operations.platform_operations, name='api-platform-operations'),
    path('platform/operations/<str:resource>/<int:pk>/', platform_operations.platform_operation_detail, name='api-platform-operation-detail'),
    path('platform/operations/users/<int:pk>/revoke-sessions/', platform_operations.platform_user_revoke_sessions, name='api-platform-user-revoke-sessions'),
    path('platform/system-settings/', saas_api.platform_system_settings, name='api-platform-system-settings'),
    # Bootstrap & Auth
    path('auth/bootstrap/', spa_api.session_bootstrap_api, name='api-bootstrap'),
    path('auth/switch-tenant/', spa_api.switch_tenant_api, name='api-switch-tenant'),
    path('platform/inspect/<int:tenant_id>/', spa_api.platform_inspect_api, name='api-platform-inspect'),
    path('platform/inspect/exit/', spa_api.platform_exit_inspect_api, name='api-platform-exit-inspect'),

    # CRM
    path('crm/overview/', spa_api.crm_overview_api, name='api-crm-overview'),
    path('crm/contacts/', spa_api.crm_contacts_api, name='api-crm-contacts'),
    path('crm/contacts/import-preview/', inbox_enhancements.crm_contacts_import_preview_api, name='api-crm-contacts-import-preview'),
    path('crm/contacts/import/', inbox_enhancements.crm_contacts_import_api, name='api-crm-contacts-import'),
    path('crm/contacts/<int:contact_id>/', spa_api.crm_contact_detail_api, name='api-crm-contact-detail'),
    path('crm/contacts/<int:contact_id>/notes/', spa_api.crm_contact_note_add_api, name='api-crm-contact-notes'),
    path('crm/contacts/merge/', spa_api.crm_contact_merge_api, name='api-crm-contacts-merge'),
    path('crm/companies/', spa_api.crm_companies_api, name='api-crm-companies'),
    path('crm/deals/', spa_api.crm_deals_api, name='api-crm-deals'),
    path('crm/deals/<int:deal_id>/stage/', spa_api.crm_deal_stage_api, name='api-crm-deal-stage'),
    path('crm/activities/', spa_api.crm_activities_api, name='api-crm-activities'),
    path('crm/activities/<int:activity_id>/complete/', spa_api.crm_activity_complete_api, name='api-crm-activity-complete'),

    # Inbox / Conversations
    path('inbox/conversations/', spa_api.chat_conversations_list_api, name='api-inbox-conversations'),
    path('inbox/conversations/start/', spa_api.chat_start_conversation_api, name='api-inbox-conversations-start'),
    path('inbox/conversations/<int:conversation_id>/media/', inbox_enhancements.chat_media_reply_api, name='api-inbox-conversation-media'),
    path('inbox/conversations/<int:conversation_id>/transfer/', inbox_enhancements.chat_transfer_api, name='api-inbox-conversation-transfer'),
    path('inbox/conversations/<int:conversation_id>/mark-read/', inbox_enhancements.chat_mark_read_api, name='api-inbox-conversation-mark-read'),
    path('inbox/media/<int:message_id>/', inbox_enhancements.inbox_media_download_api, name='api-inbox-media-download'),
    path('inbox/delivery/<int:delivery_id>/retry/', spa_api.delivery_retry_api, name='api-inbox-delivery-retry'),
    path('whatsapp/templates/', spa_api.whatsapp_templates_api, name='api-whatsapp-templates'),

    # Bookings
    path('bookings/', spa_api.bookings_list_api, name='api-bookings-list'),

    # Services
    path('services/', spa_api.services_api, name='api-services'),

    # Knowledge Base
    path('knowledge/', spa_api.knowledge_overview_api, name='api-knowledge-overview'),
    path('knowledge/faqs/', spa_api.knowledge_faq_create_api, name='api-knowledge-faq-create'),
    path('knowledge/faqs/<int:faq_id>/', spa_api.knowledge_faq_delete_api, name='api-knowledge-faq-delete'),
    path('knowledge/documents/', spa_api.knowledge_doc_create_api, name='api-knowledge-doc-create'),

    # Team & Settings
    path('team/', spa_api.team_api, name='api-team'),
    path('team/members/', onboarding_api.team_member_create_api, name='api-team-member-create'),
    path('team/members/<int:membership_id>/', onboarding_api.team_member_update_api, name='api-team-member-update'),
    path('team/members/<int:membership_id>/reset-password/', onboarding_api.team_member_reset_password_api, name='api-team-member-reset-password'),
    path('team/invite/', spa_api.team_invite_api, name='api-team-invite'),
    path('team/request-staff/', spa_api.team_request_staff_api, name='api-team-request-staff'),
    path('team/reassign-work/', spa_api.team_reassign_work_api, name='api-team-reassign-work'),
    path('team/members/<int:membership_id>/remove/', spa_api.team_remove_member_api, name='api-team-remove-member'),
    path('settings/workspace/', spa_api.workspace_settings_api, name='api-workspace-settings'),
    path('settings/whatsapp/', spa_api.whatsapp_settings_api, name='api-whatsapp-settings'),
    path('settings/whatsapp/profile/', spa_api.whatsapp_business_profile_api, name='api-whatsapp-business-profile'),
    path('settings/whatsapp/verify/', spa_api.whatsapp_verify_api, name='api-whatsapp-verify'),

    # Onboarding, Reports & Usage
    path('onboarding/status/', spa_api.onboarding_status_api, name='api-onboarding-status'),
    path('onboarding/test-assistant/', spa_api.onboarding_test_assistant_api, name='api-onboarding-test-assistant'),
    path('reports/overview/', spa_api.reports_overview_api, name='api-reports-overview'),
    path('usage/overview/', spa_api.usage_overview_api, name='api-usage-overview'),

    # Platform Admin & Matrix
    path('platform/metrics/', spa_api.platform_metrics_api, name='api-platform-metrics'),
    path('platform/tenants/', spa_api.platform_tenants_api, name='api-platform-tenants'),
    path('platform/tenants/<int:tenant_id>/toggle/', spa_api.platform_tenant_toggle_api, name='api-platform-tenant-toggle'),
    path('platform/tenants/<int:tenant_id>/outbound-pause/', spa_api.platform_tenant_outbound_pause_api, name='api-platform-tenant-outbound-pause'),
    path('platform/tenants/<int:tenant_id>/update/', spa_api.platform_tenant_update_api, name='api-platform-tenant-update'),
    path('platform/tenants/<int:tenant_id>/overrides/', spa_api.platform_tenant_overrides_api, name='api-platform-tenant-overrides'),
    path('platform/staff-requests/', spa_api.platform_staff_requests_api, name='api-platform-staff-requests'),
    path('platform/staff-requests/<uuid:request_id>/<str:action>/', spa_api.platform_staff_request_action_api, name='api-platform-staff-request-action'),
    path('platform/matrix/', spa_api.platform_matrix_api, name='api-platform-matrix'),
    path('platform/matrix/plan/<str:plan_code>/', spa_api.platform_plan_bundle_api, name='api-platform-plan-bundle'),
    path('platform/matrix/copy-bundle/', spa_api.platform_copy_bundle_api, name='api-platform-copy-bundle'),
    path('platform/matrix/bulk-assign-preview/', spa_api.platform_bulk_assign_preview_api, name='api-platform-bulk-assign-preview'),
    path('platform/matrix/bulk-assign/', spa_api.platform_bulk_assign_api, name='api-platform-bulk-assign'),
    path('platform/audit/', spa_api.platform_audit_api, name='api-platform-audit'),
    path('platform/clients/create/', spa_api.platform_client_create_api, name='api-platform-clients-create'),
    path('platform/monitoring/', spa_api.platform_monitoring_api, name='api-platform-monitoring'),
    path('platform/onboarding/', onboarding_api.platform_onboarding_list_api, name='api-platform-onboarding'),
    path('platform/onboarding/invite/', onboarding_api.platform_onboarding_invite_api, name='api-platform-onboarding-invite'),
    path('platform/onboarding/<uuid:onboarding_id>/approve/', onboarding_api.platform_onboarding_approve_api, name='api-platform-onboarding-approve'),
    path('platform/onboarding/<uuid:onboarding_id>/reject/', onboarding_api.platform_onboarding_reject_api, name='api-platform-onboarding-reject'),
    path('platform/onboarding/<uuid:onboarding_id>/resend-verification/', onboarding_api.platform_onboarding_resend_verification_api, name='api-platform-onboarding-resend-verification'),
    path('platform/onboarding/<uuid:onboarding_id>/resend-activation/', onboarding_api.platform_onboarding_resend_activation_api, name='api-platform-onboarding-resend-activation'),
    path('platform/onboarding/<uuid:onboarding_id>/change-email/', onboarding_api.platform_onboarding_change_email_api, name='api-platform-onboarding-change-email'),

    # Release 2: Client-to-Platform Support & Emergency SLA Escalations
    path('support/tickets/', support_api.client_support_tickets_api, name='api-client-support-tickets'),
    path('support/tickets/<uuid:ticket_id>/', support_api.client_support_ticket_detail_api, name='api-client-support-ticket-detail'),
    path('support/tickets/<uuid:ticket_id>/reply/', support_api.client_support_ticket_reply_api, name='api-client-support-ticket-reply'),
    path('support/tickets/<uuid:ticket_id>/status/', support_api.client_support_ticket_status_api, name='api-client-support-ticket-status'),
    path('support/tickets/<uuid:ticket_id>/attachments/<uuid:message_id>/', support_api.client_support_attachment_api, name='api-client-support-attachment'),
    path('platform/support/tickets/', support_api.platform_support_tickets_api, name='api-platform-support-tickets'),
    path('platform/support/tickets/<uuid:ticket_id>/', support_api.platform_support_ticket_detail_api, name='api-platform-support-ticket-detail'),
    path('platform/support/tickets/<uuid:ticket_id>/reply/', support_api.platform_support_ticket_reply_api, name='api-platform-support-ticket-reply'),
    path('platform/support/tickets/<uuid:ticket_id>/update/', support_api.platform_support_ticket_update_api, name='api-platform-support-ticket-update'),
    path('platform/support/tickets/<uuid:ticket_id>/attachments/<uuid:message_id>/', support_api.platform_support_attachment_api, name='api-platform-support-attachment'),

    # Sales Work Queue, Quotations, Qualification & Scoring
    path('crm/work-queue/', spa_api.sales_work_queue_api, name='api-crm-work-queue'),
    path('crm/qualification/', spa_api.qualification_api, name='api-crm-qualification'),
    path('crm/scoring/<int:contact_id>/', spa_api.scoring_api, name='api-crm-scoring'),
    path('crm/deals/<int:deal_id>/quotes/', spa_api.deal_quotes_api, name='api-crm-deal-quotes'),
    path('crm/quotes/<int:quote_id>/pdf/', spa_api.quote_pdf_api, name='api-crm-quote-pdf'),
    path('crm/quotes/<int:quote_id>/status/', spa_api.quote_status_api, name='api-crm-quote-status'),

    # Workflow Automation
    path('crm/automations/', spa_api.automations_api, name='api-crm-automations'),
    path('crm/automations/settings/', spa_api.automation_settings_api, name='api-crm-automations-settings'),
    path('crm/automations/<int:rule_id>/toggle/', spa_api.automation_toggle_api, name='api-crm-automation-toggle'),
    path('crm/automations/<int:rule_id>/dry-run/', spa_api.automation_dry_run_api, name='api-crm-automation-dry-run'),

    # Customer Support & Post-Sale Onboarding
    path('crm/tickets/', spa_api.support_tickets_api, name='api-crm-tickets'),
    path('crm/tickets/<int:ticket_id>/status/', spa_api.ticket_status_api, name='api-crm-ticket-status'),
    path('crm/tickets/<int:ticket_id>/notes/', spa_api.ticket_notes_api, name='api-crm-ticket-notes'),
    path('crm/onboarding/', spa_api.onboarding_checklists_api, name='api-crm-onboarding'),
    path('crm/onboarding/tasks/<int:task_id>/toggle/', spa_api.onboarding_task_toggle_api, name='api-crm-onboarding-task-toggle'),

    # Growth Tools, Campaigns & Integrations
    path('crm/consent/<int:contact_id>/', broadcast_api.contact_consent_api, name='api-crm-consent'),
    path('crm/campaigns/', broadcast_api.campaigns_api, name='api-crm-campaigns'),
    path('crm/integrations/', spa_api.integrations_api, name='api-crm-integrations'),
    path('crm/webhooks/', spa_api.webhooks_api, name='api-crm-webhooks'),
]
