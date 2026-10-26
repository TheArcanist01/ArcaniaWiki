from django import forms
from django.contrib import admin

from .choices import Element
from .models import (
    Article,
    Enemy,
    GameOrigin,
    Item,
    ItemSource,
    ItemSourceDrop,
    Level,
)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "article_type", "updated_at", "created_at")
    list_filter = ("article_type",)
    search_fields = ("title", "content")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(GameOrigin)
class GameOriginAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ItemSource)
class ItemSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "custom_enemy_page")
    list_filter = ("source_type",)
    search_fields = ("name",)

    @admin.display(description="Custom enemy page")
    def custom_enemy_page(self, obj):
        return obj.custom_enemy or "—"


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ("name", "game_origin")
    list_filter = ("game_origin",)
    search_fields = ("name",)


class ItemSourceDropInline(admin.TabularInline):
    model = ItemSourceDrop
    extra = 1
    autocomplete_fields = ("source",)
    fields = ("source", "drop_chance", "drop_note", "unlocked_by")


class ItemAdminForm(forms.ModelForm):
    elements = forms.MultipleChoiceField(
        choices=Element.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Elements the item can spawn with. Leave empty for shields and relics.",
    )

    class Meta:
        model = Item
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["elements"] = list(self.instance.elements)

    def clean_elements(self):
        chosen = self.cleaned_data["elements"]
        return "".join(code for code in Element.values if code in chosen)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    form = ItemAdminForm
    list_display = (
        "name",
        "is_vanilla",
        "item_type",
        "weapon_type",
        "rarity",
        "manufacturer",
        "game_origin",
    )
    list_filter = (
        "is_vanilla",
        "item_type",
        "weapon_type",
        "character_class",
        "rarity",
        "manufacturer",
        "game_origin",
    )
    search_fields = ("name", "content", "sources__name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ItemSourceDropInline]
    fieldsets = (
        (None, {"fields": ("is_vanilla", "item_type", "name", "slug")}),
        (
            "Details",
            {
                "fields": (
                    "rarity",
                    "manufacturer",
                    "weapon_type",
                    "character_class",
                    "elements",
                    "game_origin",
                    "appearance_order",
                )
            },
        ),
        ("Images", {"fields": ("image", "arcania_image", "stats_image")}),
        ("Item Effects", {"fields": ("content",)}),
        ("Trivia", {"fields": ("trivia",)}),
        ("Changes", {"fields": ("changes",)}),
    )


@admin.register(Enemy)
class EnemyAdmin(admin.ModelAdmin):
    list_display = ("name", "enemy_type", "game_origin", "level", "drop_source")
    list_filter = ("game_origin", "level")
    search_fields = ("name", "enemy_type", "trivia")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("level", "drop_source")
