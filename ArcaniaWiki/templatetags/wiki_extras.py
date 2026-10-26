import os
from decimal import Decimal

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def versioned_static(path):
    """
    Static URL with the file's modification time appended (style.css?v=1793030810).
    When the file changes, the URL changes too, so browsers fetch the new version
    instead of reusing an old cached copy.
    """
    url = static(path)
    found = finders.find(path)
    if found:
        url += f"?v={int(os.path.getmtime(found))}"
    return url


@register.filter
def percent(value):
    """Decimal drop chance -> '12.5%', '10%', '0.25%' (no trailing zeros)."""
    if value is None or value == "":
        return ""
    number = Decimal(value).normalize()
    text = format(number, "f")
    return f"{text}%"
