from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    # The admin panel lives at /arcaniawikiadmin/ (settings.ADMIN_URL), not /admin/.
    path(f"{settings.ADMIN_URL}/", admin.site.urls),
    path("", include("arcaniawiki.urls")),
]

# Uploaded images (items, enemies, maps). Served by Django itself unless the
# server has a separate web server for /media/ (then set DJANGO_SERVE_MEDIA=False).
if settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
