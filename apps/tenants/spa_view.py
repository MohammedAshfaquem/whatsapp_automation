from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie

@ensure_csrf_cookie
@login_required(login_url='login')
def spa_app_view(request, path=''):
    """
    Renders the React Single Page Application container.
    """
    return render(request, 'app/index.html', {
        'page_title': 'Neoriz WhatsApp Automation',
    })
