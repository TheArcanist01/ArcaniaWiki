import html
import re

import markdown
import nh3
from django.utils.html import strip_tags

ALLOWED_TAGS = {
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "del", "blockquote",
    "ul", "ol", "li",
    "a", "code", "pre", "img",
    "table", "thead", "tbody", "tr", "th", "td",
}

ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
}


def render_markdown(text):
    """Markdown -> sanitized HTML, safe to output with |safe."""
    rendered = markdown.markdown(text or "", extensions=["extra", "sane_lists"])
    return nh3.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
    )


def markdown_to_text(text):
    """Markdown -> plain text (for the live search on article lists)."""
    plain = html.unescape(strip_tags(render_markdown(text)))
    return re.sub(r"\s+", " ", plain).strip()
