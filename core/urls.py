from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from .views import ProjectViewSet, StoreMemoryView, RetrieveContextView, DeleteMemoryView, RegisterView, ProjectExportView, SiteConfigView

router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', obtain_auth_token, name='api_token_auth'),
    path('memories/store/', StoreMemoryView.as_view(), name='store-memory'),
    path('memories/retrieve/', RetrieveContextView.as_view(), name='retrieve-memory'),
    path('memories/delete/', DeleteMemoryView.as_view(), name='delete-memory'),
    path('projects/export/', ProjectExportView.as_view(), name='export-project-report'),
    path('config/sites/', SiteConfigView.as_view(), name='site-config'),
    path('', include(router.urls)),
]
