"""Tenant-only Meta template and broadcast management APIs."""
import json
import re
from functools import wraps
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods
from apps.tenants.context import user_can_manage_tenant
from apps.tenants.capabilities import can_access_capability
from apps.tenants.models import TenantAuditLog
from apps.chatbot.models import Customer, ContactLifecycleStatus
from apps.crm.models import Campaign, ContactConsent, ConsentSource, WhatsAppTemplate
from apps.crm.broadcasts import eligible_audience, launch, totals, variables, validate_parameters, campaign_ready
from apps.whatsapp.whatsapp_client import WhatsAppClient
from apps.whatsapp.template_sync import sync_templates


def client_admin(fn):
    @wraps(fn)
    def wrapped(request,*args,**kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error':'Authentication required'},status=401)
        tenant=getattr(request,'tenant',None)
        if not tenant or not user_can_manage_tenant(request.user,tenant):
            return JsonResponse({'error':'Client owner or administrator access required.'},status=403)
        allowed,reason=can_access_capability(request.user,tenant,'growth')
        if not allowed:return JsonResponse({'error':reason},status=403)
        try:
            return fn(request,*args,**kwargs)
        except (ValueError,TypeError,json.JSONDecodeError) as e:
            return JsonResponse({'error':str(e)[:300]},status=400)
    return wrapped


def body(request):
    if len(request.body)>50000:raise ValueError('Request too large')
    data=json.loads(request.body or b'{}')
    if not isinstance(data,dict):raise ValueError('Expected a JSON object')
    return data


def audit(request,summary,details=None):
    TenantAuditLog.objects.create(tenant=request.tenant,actor=request.user,action='TENANT_STATUS_CHANGED',summary=summary,details=details or {})


def template_json(t):
    return {'id':t.pk,'name':t.name,'language':t.language,'category':t.category,'body_text':t.body_text,
            'meta_status':t.meta_status,'variables':t.variables,'meta_id':t.meta_id,'submission_error':t.submission_error,
            'last_synced_at':t.last_synced_at.isoformat() if t.last_synced_at else None}


def campaign_json(c):
    return {'id':c.pk,'name':c.name,'status':c.status,'template_id':c.template_id,
        'template_name':c.template.name if c.template else None,'template_parameters':c.template_parameters,
        'variable_mapping':getattr(c,'variable_mapping',[]) or [],
        'target_lifecycle_status':c.target_lifecycle_status,'target_tags':getattr(c,'target_tags',[]) or [],
        'audience_count':c.audience_count,
        'scheduled_at':c.scheduled_at.isoformat() if c.scheduled_at else None,'created_at':c.created_at.isoformat(),**totals(c)}


@client_admin
@require_http_methods(['GET','POST'])
def campaigns_api(request):
    if request.method=='GET':
        return JsonResponse({'campaigns':[campaign_json(c) for c in Campaign.objects.filter(tenant=request.tenant).select_related('template').order_by('-pk')[:100]],
            'templates':[template_json(t) for t in WhatsAppTemplate.objects.filter(tenant=request.tenant).order_by('name','language')]})
    data=body(request);name=data.get('name','')
    if not isinstance(name,str) or not name.strip() or len(name)>150:raise ValueError('Campaign name is required (maximum 150 characters).')
    template=get_object_or_404(WhatsAppTemplate,tenant=request.tenant,pk=data['template_id']) if data.get('template_id') else None
    lifecycle=data.get('target_lifecycle_status','')
    if lifecycle and lifecycle not in ContactLifecycleStatus.values:raise ValueError('Invalid lifecycle segment')
    raw_tags=data.get('target_tags',[])
    if isinstance(raw_tags,str):
        target_tags=[t.strip()[:40] for t in raw_tags.split(',') if t.strip()][:20]
    elif isinstance(raw_tags,list):
        target_tags=[str(t).strip()[:40] for t in raw_tags if str(t).strip()][:20]
    else:
        target_tags=[]
    raw_mapping=data.get('variable_mapping',[])
    values=[]
    if template:
        from apps.crm.broadcasts import variables as tpl_vars
        expected_len=len(tpl_vars(template.body_text))
        if isinstance(raw_mapping,list) and len(raw_mapping)==expected_len and expected_len>0:
            values=[str((m or {}).get('fallback') or (m or {}).get('value') or 'Customer').strip()[:1024] for m in raw_mapping]
        else:
            raw_mapping=[]
            values=validate_parameters(template,data.get('template_parameters',[]))
    else:
        raw_mapping=[]
    c=Campaign(tenant=request.tenant,name=name.strip(),template=template,template_parameters=values,
        variable_mapping=raw_mapping,target_lifecycle_status=lifecycle,target_tags=target_tags,created_by=request.user)
    c.audience_count=eligible_audience(c).count();c.save()
    audit(request,'Broadcast draft created',{'campaign_id':c.pk})
    return JsonResponse({'status':'created','campaign_id':c.pk,'audience_count':c.audience_count},status=201)


@client_admin
@require_http_methods(['POST'])
def campaign_preview_api(request):
    """Dry-run preview showing eligible audience count and per-contact variable rendering."""
    from apps.crm.broadcasts import resolve_recipient_parameters
    data=body(request)
    template=get_object_or_404(WhatsAppTemplate,tenant=request.tenant,pk=data['template_id']) if data.get('template_id') else None
    lifecycle=data.get('target_lifecycle_status','')
    if lifecycle and lifecycle not in ContactLifecycleStatus.values:raise ValueError('Invalid lifecycle segment')
    raw_tags=data.get('target_tags',[])
    if isinstance(raw_tags,str):
        target_tags=[t.strip()[:40] for t in raw_tags.split(',') if t.strip()][:20]
    elif isinstance(raw_tags,list):
        target_tags=[str(t).strip()[:40] for t in raw_tags if str(t).strip()][:20]
    else:
        target_tags=[]
    temp_campaign=Campaign(
        tenant=request.tenant,
        template=template,
        target_lifecycle_status=lifecycle,
        target_tags=target_tags,
        template_parameters=data.get('template_parameters') or [],
        variable_mapping=data.get('variable_mapping') or [],
    )
    qs=eligible_audience(temp_campaign).select_related('company')
    eligible_count=qs.count()
    samples=[]
    for contact in qs[:5]:
        rendered=template.body_text if template else ''
        if template:
            try:
                vals=resolve_recipient_parameters(temp_campaign,contact)
                rendered=re.sub(r'\{\{(\d+)\}\}',lambda m:vals[int(m[1])-1],template.body_text)
            except ValueError:
                rendered=template.body_text
        samples.append({'id':contact.pk,'name':contact.name,'phone_number':contact.phone_number,'rendered_preview':rendered})
    return JsonResponse({'eligible_count':eligible_count,'sample_recipients':samples})


@client_admin
@require_http_methods(['GET','POST'])
def campaign_detail_api(request,campaign_id):
    c=get_object_or_404(Campaign,tenant=request.tenant,pk=campaign_id)
    if request.method=='GET':
        recipients=[]
        for r in c.recipients.select_related('contact','delivery').order_by('pk')[:200]:
            d=r.delivery
            recipients.append({'id':r.pk,'contact_name':r.contact.name,'phone':r.contact.phone_number,'status':d.status if d else r.status,
                'attempts':d.attempts if d else 0,'reason':r.reason if not d else ('Provider delivery requires review' if d.last_error else ''),'delivery_id':r.delivery_id})
        return JsonResponse({'campaign':campaign_json(c),'eligible_now':eligible_audience(c).count(),'recipients':recipients,'recipient_limit':200})
    data=body(request);action=data.get('action')
    if action=='launch':
        if data.get('confirm_send') is not True:raise ValueError('Explicit confirmation is required to launch a broadcast.')
        scheduled=None
        if data.get('scheduled_at'):
            scheduled=parse_datetime(data['scheduled_at'])
            if not scheduled or timezone.is_naive(scheduled) or scheduled<=timezone.now():raise ValueError('Schedule must be a future time with a timezone.')
        try:c=launch(c.pk,request.tenant,scheduled)
        except ValueError as e:return JsonResponse({'error':str(e)},status=409)
    elif action in ('pause','resume','cancel'):
        with transaction.atomic():
            c=Campaign.objects.select_for_update(of=('self',)).select_related('template','tenant').get(pk=c.pk)
            permitted={'pause':('RUNNING','SCHEDULED'),'resume':('PAUSED',),'cancel':('DRAFT','RUNNING','SCHEDULED','PAUSED')}
            if c.status not in permitted[action]:return JsonResponse({'error':'Campaign state changed; refresh before continuing.'},status=409)
            if action=='resume':campaign_ready(c)
            c.status={'pause':'PAUSED','resume':('SCHEDULED' if c.scheduled_at and c.scheduled_at>timezone.now() else 'RUNNING'),'cancel':'CANCELLED'}[action];c.save(update_fields=['status','updated_at'])
    else:raise ValueError('Unknown campaign action')
    audit(request,'Broadcast '+action,{'campaign_id':c.pk,'audience_count':c.audience_count})
    return JsonResponse({'campaign':campaign_json(c)})


@client_admin
@require_http_methods(['GET','POST'])
def templates_api(request):
    if request.method=='GET':
        return JsonResponse({'templates':[template_json(t) for t in WhatsAppTemplate.objects.filter(tenant=request.tenant).order_by('name','language')]})
    data=body(request)
    if data.get('action')=='sync':
        ok,error=sync_templates(request.tenant)
        if not ok:return JsonResponse({'error':error},status=502)
        audit(request,'Meta template approvals synchronized')
        return JsonResponse({'status':'synced'})
    name=data.get('name','');language=data.get('language','en');category=data.get('category','UTILITY');text=data.get('body_text','')
    if not isinstance(name,str) or not re.fullmatch(r'[a-z0-9_]{1,100}',name):raise ValueError('Use a lowercase template name with letters, numbers and underscores.')
    if not isinstance(language,str) or not re.fullmatch(r'[a-z]{2,3}(?:_[A-Z]{2})?',language):raise ValueError('Invalid language code')
    if category not in ('UTILITY','MARKETING'):raise ValueError('Create utility or marketing templates here. Authentication templates require the Meta OTP workflow.')
    if not isinstance(text,str) or not text.strip() or len(text)>1024:raise ValueError('Body text must contain 1–1024 characters.')
    positions=variables(text)
    t,created=WhatsAppTemplate.objects.get_or_create(tenant=request.tenant,name=name,language=language,
        defaults={'category':category,'body_text':text.strip(),'variables':[f'Variable {p}' for p in positions],'meta_status':'DRAFT'})
    if not created:return JsonResponse({'error':'This template name and language already exist. Use a new name.'},status=409)
    audit(request,'WhatsApp template drafted',{'template_id':t.pk})
    return JsonResponse({'template':template_json(t)},status=201)


@client_admin
@require_http_methods(['POST'])
def submit_template_api(request,template_id):
    data=body(request)
    with transaction.atomic():
        t=get_object_or_404(WhatsAppTemplate.objects.select_for_update(),tenant=request.tenant,pk=template_id)
        if t.meta_status not in ('DRAFT','REJECTED') or t.meta_id:
            return JsonResponse({'error':'Sync Meta before resubmitting. This template may already exist on Meta.'},status=409)
        if t.category not in ('UTILITY','MARKETING'):raise ValueError('This template category requires a separate Meta workflow.')
        examples=validate_parameters(t,data.get('examples',[]))
        t.meta_status='SUBMITTING';t.submission_error='';t.save(update_fields=['meta_status','submission_error'])
    # Commit the claim before the external POST so crashes cannot cause duplicate submissions.
    ok,result,error,uncertain=WhatsAppClient.create_template(t,examples)
    with transaction.atomic():
        t=WhatsAppTemplate.objects.select_for_update().get(pk=t.pk)
        # A concurrent sync is authoritative and must not be overwritten by an old POST response.
        if t.meta_status=='SUBMITTING':
            t.meta_status=(result.get('status') or 'PENDING') if ok else ('UNKNOWN' if uncertain else 'DRAFT')
            t.meta_id=str(result.get('id',''))[:100];t.submission_error=error;t.save()
    audit(request,'WhatsApp template submission attempted',{'template_id':t.pk,'confirmed':ok,'uncertain':uncertain})
    return JsonResponse({'template':template_json(t),**({'error':error} if not ok else {})},status=200 if ok else 502)


@client_admin
@require_http_methods(['GET','POST'])
def contact_consent_api(request,contact_id):
    contact=get_object_or_404(Customer,tenant=request.tenant,pk=contact_id)
    if request.method=='POST':
        data=body(request)
        for key in ('has_consented','marketing_allowed','utility_allowed','is_opted_out'):
            if key in data and not isinstance(data[key],bool):raise ValueError(f'{key} must be a boolean')
        with transaction.atomic():
            Customer.objects.select_for_update().get(pk=contact.pk)
            c,_=ContactConsent.objects.get_or_create(tenant=request.tenant,contact=contact)
            for key in ('has_consented','marketing_allowed','utility_allowed','is_opted_out'):
                if key in data:setattr(c,key,data[key])
            for key,maxlen in (('evidence_text',2000),('purpose',100),('source',30)):
                if key in data:
                    if not isinstance(data[key],str) or len(data[key])>maxlen:raise ValueError(f'Invalid {key}')
                    setattr(c,key,data[key].strip())
            if c.source not in ConsentSource.values:raise ValueError('Invalid consent source')
            if c.has_consented and (c.marketing_allowed or c.utility_allowed) and not c.evidence_text.strip():raise ValueError('Record consent evidence before enabling outbound messaging.')
            c.opted_out_at=timezone.now() if c.is_opted_out else None;c.save()
        audit(request,'Contact messaging permission updated',{'contact_id':contact.pk,'opted_out':c.is_opted_out})
    c=ContactConsent.objects.filter(tenant=request.tenant,contact=contact).first()
    return JsonResponse({'contact_id':contact.pk,'phone':contact.phone_number,'has_consented':bool(c and c.has_consented),
        'marketing_allowed':bool(c and c.marketing_allowed),'utility_allowed':bool(c and c.utility_allowed),'is_opted_out':bool(c and c.is_opted_out),
        'source':c.source if c else '', 'purpose':c.purpose if c else '', 'evidence_text':c.evidence_text if c else '',
        'opted_out_at':c.opted_out_at.isoformat() if c and c.opted_out_at else None,'updated_at':c.updated_at.isoformat() if c else None})
