"""
Protection of the admin login against password guessing.

Failed admin logins are counted per address. After ADMIN_LOGIN_MAX_FAILURES
failures, further login attempts from that address are refused (HTTP 429) for
ADMIN_LOGIN_LOCKOUT_SECONDS. A successful login clears the counter.
"""

from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.cache import cache
from django.dispatch import receiver
from django.http import HttpResponse
from django.urls import reverse


def client_address(request):
    """The visitor's IP. Behind a trusted proxy, the first X-Forwarded-For entry."""
    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _key(request):
    return f"admin-login-failures:{client_address(request)}"


def is_locked_out(request):
    return cache.get(_key(request), 0) >= settings.ADMIN_LOGIN_MAX_FAILURES


@receiver(user_login_failed)
def _count_failure(sender, credentials, request=None, **kwargs):
    if request is None:
        return
    key = _key(request)
    cache.add(key, 0, settings.ADMIN_LOGIN_LOCKOUT_SECONDS)
    try:
        cache.incr(key)
    except ValueError:  # expired between add() and incr()
        cache.set(key, 1, settings.ADMIN_LOGIN_LOCKOUT_SECONDS)


@receiver(user_logged_in)
def _reset_failures(sender, request, user, **kwargs):
    if request is not None:
        cache.delete(_key(request))


class AdminLoginThrottleMiddleware:
    """Refuses admin login attempts from an address that failed too many times."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and request.path == reverse("admin:login") and is_locked_out(request):
            minutes = max(1, settings.ADMIN_LOGIN_LOCKOUT_SECONDS // 60)
            return HttpResponse(
                f"Too many failed login attempts. Try again in {minutes} minutes.",
                status=429,
                content_type="text/plain; charset=utf-8",
            )
        return self.get_response(request)
