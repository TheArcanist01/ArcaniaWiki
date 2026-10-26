"""Build the small list thumbnails for items.

    python manage.py make_thumbnails           # only missing or outdated ones
    python manage.py make_thumbnails --force   # rebuild every thumbnail

Thumbnails are also made automatically whenever an item's image changes
(admin, attach_item_images), so this is mainly for existing data.
"""

from django.core.management.base import BaseCommand

from arcaniawiki.models import Item


class Command(BaseCommand):
    help = "Create or refresh the list thumbnails of items."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rebuild all thumbnails, not just missing or outdated ones.",
        )

    def handle(self, *args, force=False, **options):
        made = 0
        for item in Item.objects.order_by("is_vanilla", "slug"):
            if not (force or item.thumbnail_is_stale()):
                continue
            item.update_thumbnail()
            Item.objects.filter(pk=item.pk).update(
                thumbnail=item.thumbnail.name, thumbnail_source=item.thumbnail_source
            )
            if item.thumbnail:
                made += 1
                self.stdout.write(f"  {item.name}: {item.thumbnail.name}")
        self.stdout.write(self.style.SUCCESS(f"Made {made} thumbnail(s)."))
