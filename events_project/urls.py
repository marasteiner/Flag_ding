from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    # 1) Override the admin logout route so that /admin/logout/ redirects to "/"
    path('admin/logout/', auth_views.LogoutView.as_view(next_page='/'), name='admin_logout_override'),
    
    # 2) The standard built-in admin site
    path('admin/', admin.site.urls),
    
    # 3) Your custom admin views (if you use them)
    path('custom_admin/', include('events.urls_custom_admin')),
    
    # 4) Public site URLs
    path('', include('events.urls')),
]
