from io import BytesIO

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.files.base import ContentFile
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse

from .choices import (
    ARTICLE_TYPE_PAGES,
    ITEM_TYPE_PAGES,
    ArticleType,
    CharacterClass,
    Element,
    ItemCollection,
    ItemType,
    Manufacturer,
    Rarity,
    SourceType,
    WeaponType,
)


class Article(models.Model):
    article_type = models.CharField(
        max_length=30,
        choices=ArticleType.choices,
        default=ArticleType.CHANGELOG,
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    content = models.TextField(help_text="Markdown.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title

    @property
    def section_slug(self):
        return ARTICLE_TYPE_PAGES[self.article_type][0]

    @property
    def section_title(self):
        return ARTICLE_TYPE_PAGES[self.article_type][1]

    def get_absolute_url(self):
        return reverse(
            "arcaniawiki:article_detail",
            kwargs={"section": self.section_slug, "slug": self.slug},
        )


class GameOrigin(models.Model):
    """Base game or a DLC."""

    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Game / DLC"
        verbose_name_plural = "Games / DLCs"

    def __str__(self):
        return self.name


class ItemSource(models.Model):
    """A drop source (enemy, mission, chest...) shared by any number of items."""

    name = models.CharField(max_length=150, unique=True)
    source_type = models.CharField(
        "Type",
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.OTHER,
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Drop source"
        verbose_name_plural = "Drop sources"

    def __str__(self):
        return self.name

    @property
    def custom_enemy(self):
        """The Arcania enemy this source represents, or None for anything else."""
        try:
            return self.enemy
        except ObjectDoesNotExist:
            return None


class Level(models.Model):
    """A game map. Shared by every enemy that appears on it."""

    name = models.CharField(max_length=150, unique=True)
    game_origin = models.ForeignKey(
        GameOrigin,
        on_delete=models.PROTECT,
        related_name="levels",
        null=True,
        blank=True,
        verbose_name="Game / DLC",
    )
    map_image = models.ImageField(upload_to="levels/", blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# Lists show items at most 148x64 CSS px; twice that keeps them sharp on HiDPI screens.
THUMBNAIL_SIZE = (320, 140)


class Item(models.Model):
    is_vanilla = models.BooleanField(
        "Vanilla item",
        default=False,
        help_text="Tick for base game items. Leave unticked for new Arcania items.",
    )
    item_type = models.CharField(max_length=30, choices=ItemType.choices)
    name = models.CharField(max_length=200)
    slug = models.SlugField()

    image = models.ImageField(
        "Look",
        upload_to="items/",
        blank=True,
        help_text=(
            "The item cut out from the background (<name>-look.png from "
            "tools/extract_item_images.py). For vanilla items: the base game look."
        ),
    )
    arcania_image = models.ImageField(
        "Arcania look",
        upload_to="items/arcania/",
        blank=True,
        help_text="Vanilla items only: the new look Arcania gives this item.",
    )
    stats_image = models.ImageField(
        "Stats card",
        upload_to="items/stats/",
        blank=True,
        help_text="The in-game card with stats and flavor text (<name>-stats.png).",
    )
    thumbnail = models.ImageField(
        upload_to="items/thumbs/",
        blank=True,
        editable=False,
        help_text="Small copy of the list image, made automatically on save.",
    )
    thumbnail_source = models.CharField(max_length=255, blank=True, editable=False)

    rarity = models.CharField(max_length=30, choices=Rarity.choices)
    manufacturer = models.CharField(
        max_length=30,
        choices=Manufacturer.choices,
        blank=True,
    )
    weapon_type = models.CharField(
        max_length=30,
        choices=WeaponType.choices,
        blank=True,
        help_text="Weapons only.",
    )
    character_class = models.CharField(
        "Class",
        max_length=30,
        choices=CharacterClass.choices,
        blank=True,
        help_text="Class mods only.",
    )
    elements = models.CharField(
        max_length=10,
        blank=True,
        help_text="Elements the item can spawn with. Empty for items without elements (shields, relics).",
    )
    game_origin = models.ForeignKey(
        GameOrigin,
        on_delete=models.PROTECT,
        related_name="items",
        null=True,
        blank=True,
        verbose_name="Game / DLC",
    )
    sources = models.ManyToManyField(
        ItemSource,
        through="ItemSourceDrop",
        through_fields=("item", "source"),
        blank=True,
        related_name="items",
    )

    appearance_order = models.PositiveIntegerField(
        "Order of appearance",
        null=True,
        blank=True,
        help_text=(
            "Position in the natural order the player can get items (base game, then DLCs). "
            "Set by the spreadsheet import from the row order; empty items are listed last."
        ),
    )

    content = models.TextField("Item effects", blank=True, help_text="Markdown.")
    trivia = models.TextField(
        blank=True,
        help_text="Markdown. Interesting facts, e.g. where the flavor text comes from.",
    )
    changes = models.TextField(
        blank=True,
        help_text="Markdown. History of changes to this item.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_vanilla", "slug"],
                name="unique_item_slug_per_collection",
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.weapon_type and self.item_type != ItemType.WEAPON:
            errors["weapon_type"] = "Only weapons have a weapon type."
        if self.character_class and self.item_type != ItemType.CLASS_MOD:
            errors["character_class"] = "Only class mods have a class."
        if set(self.elements) - set(Element.values):
            errors["elements"] = "Unknown element code."
        if self.arcania_image and not self.is_vanilla:
            errors["arcania_image"] = (
                "Only vanilla items have a separate Arcania look. "
                "For new items use the main image."
            )
        if errors:
            raise ValidationError(errors)

    @property
    def collection(self):
        return ItemCollection.VANILLA if self.is_vanilla else ItemCollection.NEW

    @property
    def collection_title(self):
        return ItemCollection.TITLES[self.collection]

    @property
    def type_slug(self):
        return ITEM_TYPE_PAGES[self.item_type][0]

    @property
    def type_title(self):
        return ITEM_TYPE_PAGES[self.item_type][1]

    @property
    def type_label(self):
        """Weapon type for weapons, item type for everything else."""
        if self.item_type == ItemType.WEAPON and self.weapon_type:
            return self.get_weapon_type_display()
        return self.get_item_type_display()

    @property
    def element_list(self):
        """[(code, label), ...] in the standard element order."""
        return [(code, label) for code, label in Element.choices if code in self.elements]

    @property
    def list_image(self):
        """The image shown in lists: Arcania's look when there is one."""
        return self.arcania_image or self.image

    @property
    def list_thumbnail(self):
        """The small, fast-loading version of list_image (falls back to it)."""
        return self.thumbnail or self.list_image

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.thumbnail_is_stale():
            self.update_thumbnail()
            super().save(update_fields=["thumbnail", "thumbnail_source"])

    def _thumbnail_signature(self):
        """Identifies the list image file, so a replaced file is noticed too."""
        source = self.list_image
        if not source:
            return ""
        try:
            stamp = source.storage.get_modified_time(source.name).timestamp()
            return f"{source.name}|{source.size}|{stamp:.0f}"
        except (OSError, NotImplementedError):
            return source.name

    def thumbnail_is_stale(self):
        return self._thumbnail_signature() != self.thumbnail_source or (
            bool(self.list_image) and not self.thumbnail
        )

    def update_thumbnail(self):
        """Rebuild the thumbnail from list_image (does not save the item)."""
        from PIL import Image

        if self.thumbnail:
            self.thumbnail.delete(save=False)
        source = self.list_image
        self.thumbnail_source = self._thumbnail_signature()
        if not source:
            return
        with source.open("rb") as handle:
            picture = Image.open(handle)
            picture.load()
        picture = picture.convert("RGBA")
        picture.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        buffer = BytesIO()
        picture.save(buffer, "WEBP", quality=88, method=6)
        prefix = "vanilla-" if self.is_vanilla else ""
        filename = f"{prefix}{self.slug}.webp"
        # The full name uses the OS path separator (backslashes on Windows), so it is
        # only used to find a leftover file; save() gets the bare filename.
        name = self.thumbnail.field.generate_filename(self, filename)
        if self.thumbnail.storage.exists(name):  # left over: overwrite, don't add a suffix
            self.thumbnail.storage.delete(name)
        self.thumbnail.save(filename, ContentFile(buffer.getvalue()), save=False)

    def get_absolute_url(self):
        return reverse(
            "arcaniawiki:item_detail",
            kwargs={
                "collection": self.collection,
                "type_slug": self.type_slug,
                "slug": self.slug,
            },
        )


class ItemSourceDrop(models.Model):
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="source_drops",
    )
    source = models.ForeignKey(
        ItemSource,
        on_delete=models.PROTECT,
        related_name="item_drops",
    )
    drop_chance = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        null=True,
        blank=True,
        help_text="Percent. Leave empty if unknown or if you use a note instead.",
    )
    drop_note = models.CharField(
        "Note",
        max_length=100,
        blank=True,
        help_text="Shown instead of the drop chance, e.g. Quest Reward.",
    )
    unlocked_by = models.ForeignKey(
        ItemSource,
        on_delete=models.SET_NULL,
        related_name="unlocked_drops",
        null=True,
        blank=True,
        limit_choices_to={"source_type": SourceType.MISSION},
        verbose_name="Post quest completion",
        help_text="Mission that must be completed before this source drops the item.",
    )

    class Meta:
        ordering = ["source__name"]
        verbose_name = "Drop source"
        verbose_name_plural = "Drop sources"
        constraints = [
            models.UniqueConstraint(
                fields=["item", "source"],
                name="unique_source_per_item",
            )
        ]

    def __str__(self):
        return f"{self.item.name} — {self.source.name}"


class Enemy(models.Model):
    """A custom enemy added by Arcania."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    enemy_type = models.CharField(
        max_length=100,
        help_text="The kind of enemy it is based on, e.g. Marauder, Skag, Loader.",
    )
    image = models.ImageField("Screenshot", upload_to="enemies/", blank=True)
    game_origin = models.ForeignKey(
        GameOrigin,
        on_delete=models.PROTECT,
        related_name="enemies",
        null=True,
        blank=True,
        verbose_name="Game / DLC",
    )
    level = models.ForeignKey(
        Level,
        on_delete=models.PROTECT,
        related_name="enemies",
        null=True,
        blank=True,
    )
    drop_source = models.OneToOneField(
        ItemSource,
        on_delete=models.SET_NULL,
        related_name="enemy",
        null=True,
        blank=True,
        help_text=(
            "The drop source that represents this enemy. Every item with this "
            "drop source is listed as this enemy's drop."
        ),
    )
    location_note = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Optional note shown in brackets after the level name in the Location "
            "heading, e.g. \"rare spawn anywhere in the map\"."
        ),
    )
    trivia = models.TextField(blank=True, help_text="Markdown.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Enemies"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # A drop source tied to a custom enemy is always an enemy source.
        if self.drop_source and self.drop_source.source_type != SourceType.ENEMY:
            self.drop_source.source_type = SourceType.ENEMY
            self.drop_source.save(update_fields=["source_type"])

    def get_absolute_url(self):
        return reverse("arcaniawiki:enemy_detail", kwargs={"slug": self.slug})
