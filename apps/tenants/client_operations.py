"""Private diagnostics for the active client workspace, without platform-wide access."""
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from apps.tenants.models import TenantMembership, TenantRole
from apps.tenants.capabilities import can_perform_action
from .platform_operations import _query, _serialize, RESOURCES

@require_GET
def client_operations(request, resource, pk=None):
    if not request.user.is_authenticated:
        return JsonResponse({'error':'Authentication required.'},status=401)
    tenant=getattr(request,'tenant',None)
    if not tenant:return JsonResponse({'error':'Active client workspace required.'},status=403)
    member=TenantMembership.objects.filter(tenant=tenant,user=request.user,is_active=True).first()
    if not request.user.is_superuser and (not member or member.role not in (TenantRole.OWNER,TenantRole.ADMIN)):
        return JsonResponse({'error':'Workspace administrator access required.'},status=403)
    allowed,reason=can_perform_action(request.user,tenant,'whatsapp_settings','view')
    if not allowed:return JsonResponse({'error':'Permission denied.','reason':reason},status=403)
    if resource not in ('deliveries','webhooks','templates'):
        return JsonResponse({'error':'Unknown diagnostic resource.'},status=404)
    query=_query(resource).filter(tenant=tenant)
    if pk is not None:
        row=query.filter(pk=pk).first()
        return JsonResponse({'item':_serialize(row,resource,True)}) if row else JsonResponse({'error':'Not found.'},status=404)
    try:
        page=int(request.GET.get('page',1));page_size=min(int(request.GET.get('page_size',25)),100)
        if page<1 or page_size<1:raise ValueError
    except (ValueError,TypeError):return JsonResponse({'error':'Invalid pagination.'},status=400)
    search=request.GET.get('q','').strip()[:200]
    if search:
        from django.db.models import Q
        predicate=Q(pk=int(search)) if search.isdecimal() else Q(pk__in=[])
        for field in RESOURCES[resource][2]:predicate|=Q(**{field+'__icontains':search})
        query=query.filter(predicate)
    status=request.GET.get('status','').strip()
    field=RESOURCES[resource][3]
    if status:
        if field=='is_processed':
            if status.lower() not in ('true','false','1','0'):return JsonResponse({'error':'Invalid status.'},status=400)
            status=status.lower() in ('true','1')
        query=query.filter(**{field:status})
    total=query.count()
    return JsonResponse({'resource':resource,'items':[_serialize(o,resource) for o in query.order_by('-pk')[(page-1)*page_size:page*page_size]],'total':total,'page':page,'page_size':page_size})
