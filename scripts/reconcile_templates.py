"""
Safe Reconciliation Script for WhatsApp Templates.
Converts unverified local sample templates from APPROVED to DRAFT without deleting any records or history.
If live Meta WABA credentials exist, optionally syncs official template approval statuses from Meta.
Usage:
    python scripts/reconcile_templates.py [--sync-meta]
"""
import os
import sys
import argparse

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from apps.crm.models import WhatsAppTemplate
from apps.tenants.models import Tenant

SAMPLE_NAMES = {'welcome_greeting', 'appointment_reminder', 'service_followup', 'account_update'}

def reconcile_templates(sync_meta=False):
    print("=== Reconciling WhatsApp Templates ===")
    total_reconciled = 0
    total_synced = 0

    # 1. Reconcile seeded samples to DRAFT
    samples = WhatsAppTemplate.objects.filter(name__in=SAMPLE_NAMES, meta_status='APPROVED')
    count = samples.count()
    if count > 0:
        samples.update(meta_status='DRAFT')
        total_reconciled += count
        print(f"[*] Reconciled {count} seeded sample template(s) to DRAFT status.")
    else:
        print("[*] No unverified seeded sample templates found in APPROVED status.")

    # 2. If sync_meta requested, query Meta API for each tenant
    if sync_meta:
        for tenant in Tenant.objects.filter(is_active=True):
            from apps.whatsapp.template_sync import sync_templates
            ok, err = sync_templates(tenant)
            if ok:
                total_synced += 1
                print(f"[*] Complete template snapshot synchronized for tenant ID {tenant.pk}")
            else:
                print(f"[!] Sync unavailable for tenant ID {tenant.pk}; existing state preserved")

    print(f"=== Reconciliation Complete: {total_reconciled} reconciled to DRAFT, {total_synced} synced from Meta ===")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Reconcile WhatsApp templates safely.")
    parser.add_argument('--sync-meta', action='store_true', help="Sync official approval status from Meta WABA")
    args = parser.parse_args()
    reconcile_templates(sync_meta=args.sync_meta)
