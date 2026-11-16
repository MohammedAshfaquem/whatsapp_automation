"""Minimal readiness endpoint; never exposes credentials or database errors."""
from django.db import connections, DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def health_check(request):
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except DatabaseError:
        response = JsonResponse({'status': 'unavailable'}, status=503)
    else:
        response = JsonResponse({'status': 'ok'})
    response['Cache-Control'] = 'no-store'
    return response
