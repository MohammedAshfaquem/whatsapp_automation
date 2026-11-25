from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page_view, name='marketing-landing'),
    path('features/', views.features_view, name='marketing-features'),
    path('pricing/', views.pricing_view, name='marketing-pricing'),
    path('book-demo/', views.book_demo_view, name='marketing-book-demo'),
    path('privacy/', views.privacy_view, name='marketing-privacy'),
    path('terms/', views.terms_view, name='marketing-terms'),
]
