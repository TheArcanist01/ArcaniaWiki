from django.urls import reverse

from .choices import ARTICLE_TYPE_PAGES, ITEM_TYPE_PAGES, ItemCollection
from .models import Article, Enemy, Item


def _link(label, url, path, exact=False):
    active = path == url if exact else path.startswith(url)
    return {"label": label, "url": url, "active": active}


def navigation(request):
    """
    Sidebar navigation, built from the fixed item types and article sections.

    Sections without any content (e.g. Vanilla Items before they are added, or
    Class Mods) are left out; they show up by themselves once content exists.
    """
    path = request.path
    groups = []
    present = set(Item.objects.values_list("is_vanilla", "item_type").distinct())

    for collection in (ItemCollection.NEW, ItemCollection.VANILLA):
        is_vanilla = collection == ItemCollection.VANILLA
        types = [item_type for item_type in ITEM_TYPE_PAGES if (is_vanilla, item_type) in present]
        if not types:
            continue
        root = reverse("arcaniawiki:item_collection", kwargs={"collection": collection})
        links = [_link(f"All {ItemCollection.TITLES[collection]}", root, path, exact=True)]
        for item_type in types:
            type_slug, type_title = ITEM_TYPE_PAGES[item_type]
            url = reverse(
                "arcaniawiki:item_list",
                kwargs={"collection": collection, "type_slug": type_slug},
            )
            links.append(_link(type_title, url, path))
        groups.append({
            "title": ItemCollection.TITLES[collection],
            "links": links,
            "open": path.startswith(root),
        })

    if Enemy.objects.exists():
        enemies_url = reverse("arcaniawiki:enemy_list")
        groups.append({
            "title": "Enemies",
            "links": [_link("Custom Enemies", enemies_url, path)],
            "open": path.startswith(enemies_url),
        })

    article_types = set(Article.objects.values_list("article_type", flat=True).distinct())
    update_links = [
        _link(
            title,
            reverse("arcaniawiki:article_list", kwargs={"section": slug}),
            path,
        )
        for article_type, (slug, title) in ARTICLE_TYPE_PAGES.items()
        if article_type in article_types
    ]
    if update_links:
        groups.append({
            "title": "Updates",
            "links": update_links,
            "open": any(link["active"] for link in update_links),
        })

    return {"nav_groups": groups}
