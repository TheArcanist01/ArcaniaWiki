import re

from django.db.models import Case, F, IntegerField, Min, Prefetch, Q, Value, When
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify

from .choices import (
    ARTICLE_TYPE_BY_SLUG,
    ARTICLE_TYPE_PAGES,
    ITEM_TYPE_BY_SLUG,
    ITEM_TYPE_PAGES,
    ArticleType,
    ItemCollection,
    ItemType,
    Rarity,
    SourceType,
)
from .markdown_utils import markdown_to_text, render_markdown
from .models import Article, Enemy, Item, ItemSourceDrop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _choice_order(field, choices):
    """Expression that sorts a choice field in the given order (e.g. rarity tiers).
    `choices` is a TextChoices class or a list of values."""
    values = list(getattr(choices, "values", choices))
    return Case(
        *[When(**{field: value}, then=Value(index)) for index, value in enumerate(values)],
        default=Value(len(values)),
        output_field=IntegerField(),
    )


def _apply_sort(request, queryset, columns, order_fields, default="name"):
    """
    Order `queryset` from ?sort=&direction= and return (queryset, header columns).

    columns: list of (key, label); key None = not sortable.
    order_fields: {key: [field names / expressions]}.
    """
    sort = request.GET.get("sort", default)
    if sort not in order_fields:
        sort = default
    direction = request.GET.get("direction", "asc")
    if direction not in ("asc", "desc"):
        direction = "asc"

    ordering = []
    for field in order_fields[sort]:
        expression = F(field) if isinstance(field, str) else field
        if direction == "desc":
            ordering.append(expression.desc(nulls_last=True))
        else:
            ordering.append(expression.asc(nulls_last=True))
    queryset = queryset.order_by(*ordering, "name")

    header = []
    for key, label in columns:
        column = {"key": key, "label": label, "sortable": key in order_fields}
        if column["sortable"]:
            active = key == sort
            next_direction = "desc" if active and direction == "asc" else "asc"
            column.update(
                active=active,
                url=f"?sort={key}&direction={next_direction}",
                arrow=("↑" if direction == "asc" else "↓") if active else "",
                aria_sort=("ascending" if direction == "asc" else "descending") if active else None,
            )
        header.append(column)
    return queryset, header


# Drop sources are listed missions first, then enemies, then everything else.
SOURCE_TYPE_ORDER = [SourceType.MISSION, SourceType.ENEMY, SourceType.OTHER]


def _source_drops_prefetch():
    return Prefetch(
        "source_drops",
        queryset=(
            ItemSourceDrop.objects
            .select_related("source__enemy", "unlocked_by")
            .order_by(_choice_order("source__source_type", SOURCE_TYPE_ORDER), "source__name")
        ),
    )


def _enemy_queryset():
    return (
        Enemy.objects
        .select_related("game_origin", "level", "drop_source")
        .prefetch_related(
            Prefetch(
                "drop_source__item_drops",
                queryset=ItemSourceDrop.objects.select_related("item", "unlocked_by").order_by("item__name"),
            )
        )
    )


# ---------------------------------------------------------------------------
# Home and site-wide search
# ---------------------------------------------------------------------------

def home(request):
    counts = {
        "new_items": Item.objects.filter(is_vanilla=False).count(),
        "vanilla_items": Item.objects.filter(is_vanilla=True).count(),
        "enemies": Enemy.objects.count(),
        "changelogs": Article.objects.filter(article_type=ArticleType.CHANGELOG).count(),
        "balance_changes": Article.objects.filter(article_type=ArticleType.BALANCE_CHANGE).count(),
    }
    return render(request, "arcaniawiki/home.html", {"counts": counts})


def search(request):
    """Header search: items and enemies only (articles have their own live search)."""
    query = request.GET.get("q", "").strip()
    items = Item.objects.none()
    enemies = Enemy.objects.none()

    if query:
        item_match = Q(name__icontains=query) | Q(sources__name__icontains=query)
        if slugify(query):  # "jotunn" also finds "Jötunn"
            item_match |= Q(slug__icontains=slugify(query))
        items = (
            Item.objects
            .filter(item_match)
            .distinct()
            .order_by("is_vanilla", "name")
        )
        enemies = (
            Enemy.objects
            .select_related("level")
            .filter(
                Q(name__icontains=query)
                | Q(enemy_type__icontains=query)
                | Q(level__name__icontains=query)
            )
            .order_by("name")
        )

    return render(
        request,
        "arcaniawiki/search_results.html",
        {"query": query, "items": items, "enemies": enemies},
    )


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

def item_list(request, collection, type_slug=None):
    is_vanilla = collection == ItemCollection.VANILLA
    item_type = ITEM_TYPE_BY_SLUG[type_slug] if type_slug else None

    items = (
        Item.objects
        .filter(is_vanilla=is_vanilla)
        .select_related("game_origin")
        .prefetch_related(_source_drops_prefetch())
        .annotate(
            rarity_order=_choice_order("rarity", Rarity),
            type_order=_choice_order("item_type", ItemType),
            first_source=Min("source_drops__source__name"),
        )
    )
    if item_type:
        items = items.filter(item_type=item_type)

    # The first column holds the images; its header sorts by order of appearance.
    columns = [("order", "Order of Appearance"), ("name", "Name")]
    if item_type is None:
        columns.append(("type", "Type"))
    if item_type == ItemType.WEAPON:
        columns.append(("weapon_type", "Weapon Type"))
    if item_type == ItemType.CLASS_MOD:
        columns.append(("class", "Class"))
    columns += [
        ("rarity", "Rarity"),
        ("manufacturer", "Manufacturer"),
        ("game_origin", "Game / DLC"),
        ("sources", "Drop Sources"),
    ]
    present_keys = {key for key, _ in columns}
    order_fields = {
        key: fields
        for key, fields in {
            "order": ["appearance_order"],
            "name": ["name"],
            "type": ["type_order", "weapon_type"],
            "weapon_type": ["weapon_type"],
            "class": ["character_class"],
            "rarity": ["rarity_order"],
            "manufacturer": ["manufacturer"],
            "game_origin": ["game_origin__name"],
            "sources": ["first_source"],
        }.items()
        if key in present_keys
    }
    items, header = _apply_sort(request, items, columns, order_fields, default="order")

    return render(
        request,
        "arcaniawiki/item_list.html",
        {
            "collection": collection,
            "collection_title": ItemCollection.TITLES[collection],
            "item_type": item_type,
            "type_title": ITEM_TYPE_PAGES[item_type][1] if item_type else None,
            "is_class_mods": item_type == ItemType.CLASS_MOD,
            "items": items,
            "columns": header,
        },
    )


_CHANGE_VERSION_RE = re.compile(r"^(\s*[-*+]\s+)(\d+(?:\.\d+)+)(?=\s+-\s)", re.MULTILINE)


def _link_change_versions(text):
    """
    In an item's change list ("- 0.4.0 - text"), make each version number bold and
    link it to the changelog titled "Arcania <version>", when that changelog exists.
    """
    if not text:
        return text
    changelogs = {
        article.title.removeprefix("Arcania ").strip(): article.get_absolute_url()
        for article in Article.objects.filter(
            article_type=ArticleType.CHANGELOG, title__startswith="Arcania "
        )
    }

    def replace(match):
        prefix, version = match.groups()
        url = changelogs.get(version)
        if url:
            return f"{prefix}[**{version}**]({url})"
        return f"{prefix}**{version}**"

    return _CHANGE_VERSION_RE.sub(replace, text)


def item_detail(request, collection, type_slug, slug):
    item = get_object_or_404(
        Item.objects
        .select_related("game_origin")
        .prefetch_related(_source_drops_prefetch()),
        is_vanilla=collection == ItemCollection.VANILLA,
        item_type=ITEM_TYPE_BY_SLUG[type_slug],
        slug=slug,
    )
    return render(
        request,
        "arcaniawiki/item_detail.html",
        {
            "item": item,
            "rendered_content": render_markdown(item.content),
            "rendered_trivia": render_markdown(item.trivia),
            "rendered_changes": render_markdown(_link_change_versions(item.changes)),
        },
    )


# ---------------------------------------------------------------------------
# Enemies
# ---------------------------------------------------------------------------

def enemy_list(request):
    enemies = _enemy_queryset().annotate(
        first_drop=Min("drop_source__item_drops__item__name"),
    )
    columns = [
        (None, ""),
        ("name", "Name"),
        ("enemy_type", "Enemy Type"),
        ("game_origin", "Game / DLC"),
        ("level", "Level"),
        ("drops", "Drops"),
    ]
    order_fields = {
        "name": ["name"],
        "enemy_type": ["enemy_type"],
        "game_origin": ["game_origin__name"],
        "level": ["level__name"],
        "drops": ["first_drop"],
    }
    enemies, header = _apply_sort(request, enemies, columns, order_fields)
    return render(
        request,
        "arcaniawiki/enemy_list.html",
        {"enemies": enemies, "columns": header},
    )


def enemy_detail(request, slug):
    enemy = get_object_or_404(_enemy_queryset(), slug=slug)
    return render(
        request,
        "arcaniawiki/enemy_detail.html",
        {"enemy": enemy, "rendered_trivia": render_markdown(enemy.trivia)},
    )


# ---------------------------------------------------------------------------
# Articles (changelogs and balance changes)
# ---------------------------------------------------------------------------

def article_list(request, section):
    article_type = ARTICLE_TYPE_BY_SLUG[section]
    articles = list(
        Article.objects.filter(article_type=article_type).order_by("-updated_at")
    )
    for article in articles:
        article.plain_text = markdown_to_text(article.content)

    return render(
        request,
        "arcaniawiki/article_list.html",
        {
            "section": section,
            "section_title": ARTICLE_TYPE_PAGES[article_type][1],
            "articles": articles,
        },
    )


def article_detail(request, section, slug):
    article = get_object_or_404(Article, slug=slug)
    if article.section_slug != section:
        raise Http404("Article not found in this section.")
    return render(
        request,
        "arcaniawiki/article_detail.html",
        {"article": article, "rendered_content": render_markdown(article.content)},
    )
