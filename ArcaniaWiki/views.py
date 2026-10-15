
import markdown
import nh3

from django.shortcuts import render, get_object_or_404
from .models import Article
from django.db import models


def article_list(request):
    query = request.GET.get("q", "").strip()

    articles = Article.objects.order_by("-created_at")

    if query:
        articles = articles.filter(
            models.Q(title__icontains=query)
            | models.Q(content__icontains=query)
        )

    return render(
        request,
        "arcaniawiki/article_list.html",
        {
            "articles": articles,
            "query": query,
        },
    )



def article_detail(request, slug):
    article = get_object_or_404(Article, slug=slug)

    rendered_content = markdown.markdown(
        article.content,
        extensions=["extra", "sane_lists"],
    )

    safe_content = nh3.clean(
        rendered_content,
        tags={
            "p", "br", "hr",
            "h1", "h2", "h3", "h4", "h5", "h6",
            "strong", "em", "del", "blockquote",
            "ul", "ol", "li",
            "a", "code", "pre",
            "table", "thead", "tbody", "tr", "th", "td",
        },
        attributes={
            "a": {"href", "title"},
        },
        url_schemes={"http", "https", "mailto"},
    )

    return render(
        request,
        "arcaniawiki/article_detail.html",
        {
            "article": article,
            "rendered_content": safe_content,
        },
    )
