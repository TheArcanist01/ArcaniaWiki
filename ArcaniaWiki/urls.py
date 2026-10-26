from django.urls import path, register_converter

from . import views
from .choices import ARTICLE_TYPE_BY_SLUG, ITEM_TYPE_BY_SLUG, ItemCollection


class _FixedChoiceConverter:
    """Matches only a fixed set of URL segments, so sections never collide."""

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


class CollectionConverter(_FixedChoiceConverter):
    regex = f"{ItemCollection.NEW}|{ItemCollection.VANILLA}"


class ItemTypeConverter(_FixedChoiceConverter):
    regex = "|".join(ITEM_TYPE_BY_SLUG)


class ArticleSectionConverter(_FixedChoiceConverter):
    regex = "|".join(ARTICLE_TYPE_BY_SLUG)


register_converter(CollectionConverter, "collection")
register_converter(ItemTypeConverter, "item_type")
register_converter(ArticleSectionConverter, "article_section")

app_name = "arcaniawiki"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),

    path("enemies/", views.enemy_list, name="enemy_list"),
    path("enemies/<slug:slug>/", views.enemy_detail, name="enemy_detail"),

    path("<article_section:section>/", views.article_list, name="article_list"),
    path(
        "<article_section:section>/<slug:slug>/",
        views.article_detail,
        name="article_detail",
    ),

    path("<collection:collection>/", views.item_list, name="item_collection"),
    path(
        "<collection:collection>/<item_type:type_slug>/",
        views.item_list,
        name="item_list",
    ),
    path(
        "<collection:collection>/<item_type:type_slug>/<slug:slug>/",
        views.item_detail,
        name="item_detail",
    ),
]
