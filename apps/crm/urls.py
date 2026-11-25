from django.urls import path
from . import views

urlpatterns = [
    # CRM Overview
    path('', views.crm_overview_view, name='crm-overview'),

    # Contacts
    path('contacts/', views.contact_list_view, name='crm-contact-list'),
    path('contacts/create/', views.contact_create_view, name='crm-contact-create'),
    path('contacts/export/', views.contact_export_view, name='crm-contact-export'),
    path('contacts/import/', views.contact_import_view, name='crm-contact-import'),
    path('contacts/<int:contact_id>/', views.contact_detail_view, name='crm-contact-detail'),
    path('contacts/<int:contact_id>/edit/', views.contact_edit_view, name='crm-contact-edit'),
    path('contacts/<int:contact_id>/notes/create/', views.contact_note_create_view, name='crm-contact-note-create'),
    path('contacts/<int:contact_id>/send_message/', views.contact_send_message_view, name='crm-contact-send-message'),
    path('contacts/<int:contact_id>/merge/', views.contact_merge_view, name='crm-contact-merge'),

    # Companies
    path('companies/', views.company_list_view, name='crm-company-list'),
    path('companies/create/', views.company_create_view, name='crm-company-create'),
    path('companies/<int:company_id>/', views.company_detail_view, name='crm-company-detail'),

    # Deals & Pipelines
    path('deals/board/', views.deal_board_view, name='crm-deal-board'),
    path('deals/', views.deal_list_view, name='crm-deal-list'),
    path('deals/create/', views.deal_create_view, name='crm-deal-create'),
    path('deals/<int:deal_id>/', views.deal_detail_view, name='crm-deal-detail'),
    path('deals/<int:deal_id>/move/', views.deal_move_stage_api, name='crm-deal-move-stage'),

    # Tasks & Activities
    path('activities/', views.activity_list_view, name='crm-activity-list'),
    path('activities/create/', views.activity_create_view, name='crm-activity-create'),
    path('activities/<int:activity_id>/toggle/', views.activity_toggle_api, name='crm-activity-toggle'),

    # Settings
    path('settings/', views.crm_settings_view, name='crm-settings'),
]
