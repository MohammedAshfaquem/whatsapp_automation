"""Tenant workspace tools and software-provider controls, with separate authorization."""
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .spa_api import api_login_required
from .models import (Tenant, TenantMembership, TenantSubscription, SavedReply,
                     PlatformServiceConfig, TransactionalEmail, ManualBillingEntry, TenantAuditLog)
from .context import user_can_manage_tenant, user_can_access_tenant
from .capabilities import can_access_capability
from .meta_setup import meta_setup_state
from .email_service import queue_email, ready, seal, validate_smtp_host
from .platform_auth import can_platform_access, reclaim_all_expired_leases
from apps.whatsapp.models import WhatsAppDelivery
from apps.chatbot.models import Customer


def response(data, status=200):
    result=JsonResponse(data,status=status);result['Cache-Control']='no-store';return result


def page(request, queryset, fields):
    try: number=max(1,min(100000,int(request.GET.get('page',1))))
    except ValueError: number=1
    return {'results':list(queryset.values(*fields)[(number-1)*25:number*25]),'page':number,'count':queryset.count()}


@api_login_required
@require_http_methods(['GET','POST','DELETE'])
def workspace_tools(request, resource):
    tenant=getattr(request,'tenant',None)
    if not tenant or not user_can_access_tenant(request.user,tenant):return response({'error':'Workspace access required'},403)
    manager=user_can_manage_tenant(request.user,tenant)
    if resource=='subscription':
        if not manager:return response({'error':'Owner or administrator required'},403)
        if request.method!='GET':return response({'error':'Read only'},405)
        sub=TenantSubscription.objects.select_related('effective_plan').filter(tenant=tenant).first()
        return response({
            'billing_mode':'MANUAL',
            'status':sub.status if sub else 'UNASSIGNED',
            'plan':sub.effective_plan.name if sub and sub.effective_plan else 'Unassigned',
            'end_date':sub.end_date if sub else None,
            'grace_until':sub.grace_until if sub else None,
            'grace_notes':sub.grace_notes if sub else '',
            'is_in_grace':bool(sub and sub.is_in_grace),
            'last_reminder_sent_at':sub.last_reminder_sent_at if sub else None,
            'payments':list(ManualBillingEntry.objects.filter(tenant=tenant).order_by('-received_on','-pk').values('amount','currency','reference','received_on')[:100]),
        })
    cap='growth' if resource=='consent' else ('inbox' if resource in ('replies','deliveries') else None)
    if not cap:return response({'error':'Unknown resource'},404)
    allowed,reason=can_access_capability(request.user,tenant,cap)
    if not allowed:return response({'error':reason},403)
    if resource=='consent':
        if request.method!='GET':return response({'error':'Read only; manage evidence in Growth & Broadcasts'},405)
        from apps.crm.models import ContactConsent
        return response(page(request,ContactConsent.objects.filter(tenant=tenant,contact__tenant=tenant).order_by('-updated_at'),['id','contact_id','contact__name','contact__phone_number','has_consented','marketing_allowed','utility_allowed','is_opted_out','source','updated_at']))
    if resource=='deliveries':
        if request.method!='GET':return response({'error':'Read only'},405)
        if not manager:return response({'error':'Owner or administrator required'},403)
        rows=WhatsAppDelivery.objects.filter(tenant=tenant).order_by('-pk')
        status=request.GET.get('status','')
        if status:rows=rows.filter(status=status[:20])
        return response(page(request,rows,['id','recipient_phone','status','attempts','created_at','updated_at']))
    rows=SavedReply.objects.filter(tenant=tenant).order_by('title')
    if request.method=='GET':return response({'results':list(rows.values('id','title','body')[:200]),'can_manage':manager})
    if not manager:return response({'error':'Owner or administrator required'},403)
    try:
        data=json.loads(request.body)
        if not isinstance(data,dict):raise ValueError()
        if request.method=='DELETE':
            removed,_=rows.filter(pk=int(data['id'])).delete()
            return response({'deleted':bool(removed)})
        title=data['title'].strip();body=data['body'].strip()
        if not title or len(title)>100 or not body or len(body)>2000:raise ValueError()
        with transaction.atomic():
            if rows.count()>=200:return response({'error':'Maximum 200 saved replies'},400)
            item=SavedReply.objects.create(tenant=tenant,title=title,body=body,created_by=request.user)
        return response({'id':item.pk},201)
    except IntegrityError:return response({'error':'A reply with this title already exists'},409)
    except (ValueError,KeyError,TypeError,AttributeError):return response({'error':'Enter a title (100 characters) and reply (2000 characters)'},400)


@api_login_required
@require_http_methods(['GET','POST'])
def platform_tools(request, resource):
    area_map = {
        'health': 'health',
        'onboarding': 'onboarding',
        'emails': 'emails',
        'smtp': 'smtp',
        'billing': 'billing',
    }
    area = area_map.get(resource)
    if not area:
        return response({'error': 'Unknown resource or method'}, 404)
    allowed, reason = can_platform_access(request.user, area, write=(request.method != 'GET'))
    if not allowed:
        return response({'error': reason}, 403)

    if resource == 'health':
        from datetime import timedelta
        from apps.crm.models import BusinessEvent, WebhookDeliveryLog
        now = timezone.now()
        if request.method == 'POST':
            try:
                data = json.loads(request.body or '{}')
            except ValueError:
                return response({'error': 'Invalid JSON'}, 400)
            action = str(data.get('action') or '').strip()
            if action == 'release_expired_leases':
                can_release, lease_reason = can_platform_access(request.user, 'health_leases', write=True)
                if not can_release:
                    return response({'error': lease_reason}, 403)
                reclaimed = reclaim_all_expired_leases()
                TenantAuditLog.objects.create(
                    actor=request.user,
                    action='TENANT_STATUS_CHANGED',
                    summary='Expired platform processing leases released',
                    details=reclaimed,
                )
                return response({'status': 'ok', 'reclaimed': reclaimed})
            if action == 'toggle_global_pause':
                can_pause, pause_reason = can_platform_access(request.user, 'outbound_pause', write=True)
                if not can_pause:
                    return response({'error': pause_reason}, 403)
                paused = bool(data.get('paused'))
                pause_note = str(data.get('reason') or '').strip()[:255]
                config, _ = PlatformServiceConfig.objects.get_or_create(pk=1)
                config.global_outbound_paused = paused
                config.global_outbound_pause_reason = pause_note if paused else ''
                config.save(update_fields=['global_outbound_paused', 'global_outbound_pause_reason', 'updated_at'])
                TenantAuditLog.objects.create(
                    actor=request.user,
                    action='OUTBOUND_PAUSE_CHANGED',
                    summary=f"Global outbound WhatsApp {'paused' if paused else 'resumed'}",
                    details={'global_outbound_paused': paused, 'reason': pause_note},
                )
                return response({'status': 'ok', 'global_outbound_paused': config.global_outbound_paused, 'reason': config.global_outbound_pause_reason})
            return response({'error': 'Unsupported health action'}, 400)

        config = PlatformServiceConfig.objects.filter(pk=1).first()
        expired_customer_leases = Customer.objects.filter(processing_until__lt=now).exclude(processing_token='').count()
        active_customer_leases = Customer.objects.filter(processing_until__gt=now).exclude(processing_token='').count()
        expired_event_leases = BusinessEvent.objects.filter(status='PROCESSING', lease_expires_at__lt=now).count()
        expired_webhook_leases = WebhookDeliveryLog.objects.filter(state='PROCESSING', lease_expires_at__lt=now).count()
        expired_delivery_leases = WhatsAppDelivery.objects.filter(status='SENDING', updated_at__lt=now - timedelta(minutes=10)).count()
        paused_tenants = list(Tenant.objects.filter(outbound_paused=True).values('id', 'name', 'outbound_pause_reason')[:100])
        return response({
            'delivery_queue': list(WhatsAppDelivery.objects.values('status').annotate(count=Count('id')).order_by('status')),
            'expired_processing_leases': expired_customer_leases + expired_event_leases + expired_webhook_leases + expired_delivery_leases,
            'expired_customer_leases': expired_customer_leases,
            'expired_event_leases': expired_event_leases,
            'expired_webhook_leases': expired_webhook_leases,
            'expired_delivery_leases': expired_delivery_leases,
            'active_processing_leases': active_customer_leases,
            'email_queue': list(TransactionalEmail.objects.values('status').annotate(count=Count('id')).order_by('status')),
            'smtp_ready': ready(),
            'global_outbound_paused': bool(config and config.global_outbound_paused),
            'global_outbound_pause_reason': config.global_outbound_pause_reason if config else '',
            'maintenance_mode': bool(config and config.maintenance_mode),
            'paused_tenants': paused_tenants,
            'billing_mode': 'MANUAL',
            'meta_onboarding': 'Client-owned verified configuration; Embedded Signup requires separate Meta app approval and configuration.',
        })
    if resource=='onboarding' and request.method=='GET':
        rows=Tenant.objects.order_by('-pk');result=page(request,rows,['id','name','is_active','whatsapp_number'])
        for row in result['results']:
            tenant=rows.get(pk=row['id']);row['meta']=meta_setup_state(tenant)
            row['owners']=list(TenantMembership.objects.filter(tenant=tenant,role='OWNER',is_active=True).values_list('user__username',flat=True))
        return response(result)
    if resource=='emails':
        if request.method=='GET':return response({**page(request,TransactionalEmail.objects.order_by('-created_at'),['id','recipient','purpose','status','attempts','last_error','created_at']),'smtp_ready':ready()})
        try:
            data=json.loads(request.body)
            with transaction.atomic():
                job=TransactionalEmail.objects.select_for_update().get(pk=data['id'])
                if job.status!='FAILED' or job.attempts>=3:return response({'error':'Only confirmed failed jobs below three attempts can be retried. Inspect uncertain outcomes with your provider.'},409)
                job.status='PENDING';job.save(update_fields=['status','updated_at'])
                TenantAuditLog.objects.create(actor=request.user,action='TENANT_STATUS_CHANGED',summary='Transactional email retry queued',details={'job_id':str(job.pk)})
            return response({'status':'PENDING'})
        except (ValueError,KeyError,TypeError,AttributeError,ValidationError,TransactionalEmail.DoesNotExist):return response({'error':'Invalid email job'},400)
    if resource=='smtp':
        config=PlatformServiceConfig.objects.filter(pk=1).first()
        if request.method=='POST':
            try:
                data=json.loads(request.body)
                host=data.get('host','').strip();port=int(data.get('port',587));security=data.get('security','TLS');sender=data.get('from_email','').strip();username=data.get('username','').strip();password=data.get('password','')
                if type(data.get('enabled')) is not bool or security not in ('TLS','SSL') or not 1<=port<=65535 or len(username)>254 or len(password)>1024:raise ValueError()
                if data['enabled']:validate_email(sender);validate_smtp_host(host)
                if len(sender)>254 or len(host)>253:raise ValueError()
                with transaction.atomic():
                    PlatformServiceConfig.objects.get_or_create(pk=1)
                    config=PlatformServiceConfig.objects.select_for_update().get(pk=1)
                    if data['enabled'] and username and not (password or config.encrypted_secrets):raise ValueError()
                    config.smtp_enabled=data['enabled'];config.smtp_host=host;config.smtp_port=port;config.smtp_security=security;config.smtp_username=username;config.smtp_from_email=sender
                    if password:config.encrypted_secrets=seal({'smtp_password':password})
                    config.save()
                    TenantAuditLog.objects.create(actor=request.user,action='TENANT_STATUS_CHANGED',summary='Platform SMTP configuration updated',details={'enabled':config.smtp_enabled})
            except (ValueError,KeyError,TypeError,AttributeError,ValidationError,OSError):return response({'error':'Enter a valid public SMTP host, sender, TLS/SSL port and credentials'},400)
        return response({'enabled':config.smtp_enabled if config else False,'host':config.smtp_host if config else '', 'port':config.smtp_port if config else 587,'username':config.smtp_username if config else '', 'from_email':config.smtp_from_email if config else '', 'security':config.smtp_security if config else 'TLS','password_present':bool(config and config.encrypted_secrets),'ready':ready()})
    if resource=='billing':
        from datetime import timedelta
        if request.method=='POST':
            try:
                data=json.loads(request.body)
                action=str(data.get('action') or 'record_payment').strip()
                if action=='set_grace':
                    grace_raw=data.get('grace_until')
                    grace_date=date.fromisoformat(grace_raw) if grace_raw else None
                    grace_notes=str(data.get('grace_notes') or '').strip()[:1000]
                    if grace_date and grace_date<timezone.localdate():
                        raise ValueError('Grace date cannot be in the past.')
                    with transaction.atomic():
                        tenant=Tenant.objects.select_for_update().get(pk=int(data['tenant_id']))
                        sub=TenantSubscription.objects.select_for_update().get(tenant=tenant)
                        sub.grace_until=grace_date
                        sub.grace_notes=grace_notes
                        sub.save(update_fields=['grace_until','grace_notes','updated_at'])
                        TenantAuditLog.objects.create(
                            tenant=tenant,
                            actor=request.user,
                            action='BILLING_GRACE_UPDATED',
                            summary=f"Billing grace period {'set to '+str(grace_date) if grace_date else 'cleared'}",
                            details={'grace_until':str(grace_date) if grace_date else None,'grace_notes':grace_notes},
                        )
                    return response({'status':'ok','grace_until':str(grace_date) if grace_date else None,'grace_notes':grace_notes,'is_in_grace':sub.is_in_grace})
                if action=='send_reminder':
                    with transaction.atomic():
                        tenant=Tenant.objects.select_for_update().get(pk=int(data['tenant_id']))
                        sub=TenantSubscription.objects.select_for_update(of=('self',)).select_related('effective_plan').get(tenant=tenant)
                        owner_m=TenantMembership.objects.filter(tenant=tenant,role='OWNER',is_active=True).select_related('user').first()
                        recipient=(tenant.contact_email or (owner_m.user.email if owner_m else '') or '').strip()
                        if not recipient or '@' not in recipient or recipient.endswith('.local'):
                            return response({'error':'No deliverable client billing contact email is configured for this tenant.'},400)
                        note_text=str(data.get('note') or '').strip()[:500]
                        plan_label=sub.effective_plan.name if sub.effective_plan else tenant.plan
                        body_lines=[
                            f"Hello {tenant.name},",
                            "",
                            f"This is a subscription renewal reminder for your Neoriz workspace ({plan_label}).",
                            f"Current status: {sub.status}. Term end date: {sub.end_date or 'Not set'}.",
                        ]
                        if sub.grace_until:
                            body_lines.append(f"Active grace extension until: {sub.grace_until}.")
                        if note_text:
                            body_lines.extend(["", f"Note from Neoriz Billing: {note_text}"])
                        body_lines.extend(["", "Please contact Neoriz support to confirm renewal payment.", "Neoriz Solutions"])
                        now_ts=timezone.now()
                        import secrets as _sec
                        dedup=f"billing-reminder:{tenant.pk}:{int(now_ts.timestamp())}:{_sec.token_hex(4)}"
                        job=queue_email(
                            owner_m.user if owner_m else None,
                            'BILLING_REMINDER',
                            dedup,
                            {'subject':f'Subscription renewal notice for {tenant.name}','body':'\n'.join(body_lines)},
                            tenant=tenant,
                            recipient=recipient,
                        )
                        sub.last_reminder_sent_at=now_ts
                        sub.save(update_fields=['last_reminder_sent_at','updated_at'])
                        TenantAuditLog.objects.create(
                            tenant=tenant,
                            actor=request.user,
                            action='BILLING_GRACE_UPDATED',
                            summary=f"Billing renewal reminder queued to {recipient}",
                            details={'recipient':recipient,'email_job_id':str(job.pk) if job else None},
                        )
                    return response({'status':'queued','recipient':recipient,'last_reminder_sent_at':now_ts.isoformat()},201)

                amount=Decimal(str(data['amount']));reference=data['reference'].strip();currency=data.get('currency','INR');received=date.fromisoformat(data['received_on']);renewal=date.fromisoformat(data['renew_until']) if data.get('renew_until') else None
                if not amount.is_finite() or amount<=0 or amount>=Decimal('10000000000') or amount.as_tuple().exponent < -2 or not reference or len(reference)>100 or currency not in ('INR','USD','EUR','GBP','AED') or received>timezone.localdate() or (renewal and renewal<timezone.localdate()):raise ValueError()
                with transaction.atomic():
                    tenant=Tenant.objects.select_for_update().get(pk=int(data['tenant_id']))
                    entry=ManualBillingEntry.objects.create(tenant=tenant,amount=amount,currency=currency,reference=reference,received_on=received,created_by=request.user)
                    if renewal:
                        sub=TenantSubscription.objects.select_for_update().get(tenant=tenant)
                        if not sub.effective_plan or renewal<sub.start_date or (sub.end_date and renewal<sub.end_date):raise ValueError()
                        sub.end_date=renewal;sub.save(update_fields=['end_date','updated_at'])
                    TenantAuditLog.objects.create(tenant=tenant,actor=request.user,action='TENANT_STATUS_CHANGED',summary='Manual subscription payment recorded',details={'payment_id':entry.pk,'renew_until':str(renewal) if renewal else None})
                return response({'id':entry.pk},201)
            except IntegrityError:return response({'error':'Payment reference already recorded for this client'},409)
            except (ValueError,TypeError,KeyError,AttributeError,InvalidOperation,Tenant.DoesNotExist,TenantSubscription.DoesNotExist):return response({'error':'Enter a valid client, positive payment, unique reference and valid dates. Renewals cannot shorten the current term.'},400)
        clients=[]
        for sub in TenantSubscription.objects.select_related('tenant','effective_plan').order_by('tenant__name')[:1000]:
            clients.append({
                'tenant_id':sub.tenant_id,
                'tenant__name':sub.tenant.name,
                'status':sub.status,
                'end_date':sub.end_date,
                'grace_until':sub.grace_until,
                'grace_notes':sub.grace_notes,
                'is_in_grace':sub.is_in_grace,
                'last_reminder_sent_at':sub.last_reminder_sent_at,
                'effective_plan__name':sub.effective_plan.name if sub.effective_plan else None,
                'tenant__contact_email':sub.tenant.contact_email,
            })
        return response({**page(request,ManualBillingEntry.objects.order_by('-created_at'),['id','tenant_id','tenant__name','amount','currency','reference','received_on']),'clients':clients,'billing_mode':'MANUAL'})
    return response({'error':'Unknown resource or method'},404)


@api_login_required
@require_http_methods(['GET','POST'])
def platform_system_settings(request):
    """Super Admin global platform policy, outbound pause, maintenance mode, and backup verification log."""
    allowed, reason = can_platform_access(request.user, 'system_settings', write=(request.method != 'GET'))
    if not allowed:
        return response({'error': reason}, 403)
    cfg, _ = PlatformServiceConfig.objects.get_or_create(pk=1)
    if request.method == 'GET':
        return response({
            'verification_expiry_minutes': cfg.verification_expiry_minutes,
            'resend_cooldown_seconds': cfg.resend_cooldown_seconds,
            'resend_max_per_hour': cfg.resend_max_per_hour,
            'support_alert_email': cfg.support_alert_email,
            'support_escalation_minutes': cfg.support_escalation_minutes,
            'global_outbound_paused': cfg.global_outbound_paused,
            'global_outbound_pause_reason': cfg.global_outbound_pause_reason,
            'maintenance_mode': cfg.maintenance_mode,
            'maintenance_message': cfg.maintenance_message,
            'last_backup_verified_at': cfg.last_backup_verified_at.isoformat() if cfg.last_backup_verified_at else None,
            'last_backup_note': cfg.last_backup_note,
            'updated_at': cfg.updated_at.isoformat() if cfg.updated_at else None,
        })
    try:
        data = json.loads(request.body or '{}')
        if not isinstance(data, dict):
            raise ValueError('Invalid payload.')
        if 'verification_expiry_minutes' in data:
            v = int(data['verification_expiry_minutes'])
            if not 5 <= v <= 1440:
                raise ValueError('Verification expiry must be between 5 and 1440 minutes.')
            cfg.verification_expiry_minutes = v
        if 'resend_cooldown_seconds' in data:
            v = int(data['resend_cooldown_seconds'])
            if not 15 <= v <= 600:
                raise ValueError('Resend cooldown must be between 15 and 600 seconds.')
            cfg.resend_cooldown_seconds = v
        if 'resend_max_per_hour' in data:
            v = int(data['resend_max_per_hour'])
            if not 1 <= v <= 50:
                raise ValueError('Max resends per hour must be between 1 and 50.')
            cfg.resend_max_per_hour = v
        if 'support_escalation_minutes' in data:
            v = int(data['support_escalation_minutes'])
            if not 1 <= v <= 120:
                raise ValueError('Support escalation threshold must be between 1 and 120 minutes.')
            cfg.support_escalation_minutes = v
        if 'support_alert_email' in data:
            email_val = str(data['support_alert_email'] or '').strip()
            validate_email(email_val)
            cfg.support_alert_email = email_val
        if 'global_outbound_paused' in data:
            cfg.global_outbound_paused = bool(data['global_outbound_paused'])
        if 'global_outbound_pause_reason' in data:
            cfg.global_outbound_pause_reason = str(data['global_outbound_pause_reason'] or '').strip()[:255]
        if not cfg.global_outbound_paused and 'global_outbound_paused' in data:
            cfg.global_outbound_pause_reason = ''
        if 'maintenance_mode' in data:
            cfg.maintenance_mode = bool(data['maintenance_mode'])
        if 'maintenance_message' in data:
            cfg.maintenance_message = str(data['maintenance_message'] or '').strip()[:255] or (
                'Scheduled maintenance is in progress. Please try again shortly.'
            )
        if data.get('record_backup_verification'):
            cfg.last_backup_verified_at = timezone.now()
            cfg.last_backup_note = str(data.get('backup_note') or '').strip()[:255] or 'Manual operator backup check recorded'
        cfg.save()
        TenantAuditLog.objects.create(
            actor=request.user,
            action='SYSTEM_SETTINGS_UPDATED',
            summary=f"Platform system settings updated by @{request.user.username}",
            details={
                'global_outbound_paused': cfg.global_outbound_paused,
                'maintenance_mode': cfg.maintenance_mode,
                'support_escalation_minutes': cfg.support_escalation_minutes,
            },
        )
        return response({
            'status': 'saved',
            'verification_expiry_minutes': cfg.verification_expiry_minutes,
            'resend_cooldown_seconds': cfg.resend_cooldown_seconds,
            'resend_max_per_hour': cfg.resend_max_per_hour,
            'support_alert_email': cfg.support_alert_email,
            'support_escalation_minutes': cfg.support_escalation_minutes,
            'global_outbound_paused': cfg.global_outbound_paused,
            'global_outbound_pause_reason': cfg.global_outbound_pause_reason,
            'maintenance_mode': cfg.maintenance_mode,
            'maintenance_message': cfg.maintenance_message,
            'last_backup_verified_at': cfg.last_backup_verified_at.isoformat() if cfg.last_backup_verified_at else None,
            'last_backup_note': cfg.last_backup_note,
        })
    except (ValueError, TypeError, ValidationError) as exc:
        return response({'error': str(exc) or 'Invalid system settings values.'}, 400)
