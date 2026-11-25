"""Canonical app entry points; legacy management pages are navigation aliases only."""
from urllib.parse import urlsplit
from django.utils.http import url_has_allowed_host_and_scheme
from .models import TenantMembership

CLIENT_ALIASES={
 'dashboard':'/app/dashboard','crm-overview':'/app/work-queue','crm-contact-list':'/app/contacts',
 'crm-contact-detail':'/app/contacts','crm-contact-create':'/app/contacts','crm-contact-edit':'/app/contacts',
 'crm-contact-import':'/app/contacts','crm-company-list':'/app/companies','crm-company-detail':'/app/companies',
 'crm-company-create':'/app/companies','crm-deal-board':'/app/deals','crm-deal-list':'/app/deals',
 'crm-deal-detail':'/app/deals','crm-deal-create':'/app/deals','crm-activity-list':'/app/tasks',
 'crm-activity-create':'/app/tasks','crm-settings':'/app/settings','onboarding-wizard':'/app/onboarding',
}
PLATFORM_ALIASES={'platform-dashboard':'/app/platform/dashboard','platform-tenants':'/app/platform/tenants',
 'platform-access-matrix':'/app/platform/matrix','platform-audit':'/app/platform/audit',
 'platform-tenant-overrides':'/app/platform/matrix'}

def entry_destination(request, user=None, next_url=None, login=False):
 user=user or request.user
 is_operator=user.is_superuser and (login or not getattr(request,'is_inspecting',False))
 if is_operator:base='/app/platform/dashboard';tenant=None
 else:
  tenant=getattr(request,'tenant',None)
  if tenant is None:
   members=TenantMembership.objects.filter(user=user,is_active=True,tenant__is_active=True).select_related('tenant')
   member=members.filter(tenant_id=request.session.get('active_tenant_id')).first() or members.first()
   tenant=member.tenant if member else None
  if tenant is None:return '/access-pending/'
  from .meta_setup import meta_setup_state
  state=meta_setup_state(tenant)
  base='/app/settings?tab=whatsapp' if state['required'] and not state['ready'] else '/app/dashboard'
 if next_url and url_has_allowed_host_and_scheme(next_url,allowed_hosts={request.get_host()},require_https=request.is_secure()):
  target=urlsplit(next_url);path=target.path
  allowed=path=='/app/account' or (path.startswith('/app/platform/') if is_operator else path.startswith('/app/') and not path.startswith('/app/platform/'))
  if allowed and (is_operator or base=='/app/dashboard' or path in ('/app/account','/app/settings','/app/onboarding')):
   return path+('?' + target.query if target.query else '')
 return base
