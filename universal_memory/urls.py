from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
    path('privacy-policy/', TemplateView.as_view(template_name="privacy_policy.html"), name='privacy-policy'),
]
