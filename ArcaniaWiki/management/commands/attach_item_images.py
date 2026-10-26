"""
Attach images made by tools/extract_item_images.py to items.

    python manage.py attach_item_images pictures/extracted
    python manage.py attach_item_images pictures/extracted --vanilla
    python manage.py attach_item_images pictures/extracted --dry-run

Files are matched to items by URL slug:

    <slug>-look.png   -> Look        (e.g. titus-look.png -> Titus)
    <slug>-stats.png  -> Stats card  (e.g. titus-stats.png -> Titus)

New Arcania items are matched by default; --vanilla matches vanilla items
instead (their -look image becomes the base game look). Images are copied into
the media folder; an item's previous image of the same kind is replaced.
"""

import re
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from arcaniawiki.models import Item

KINDS = {"look": "image", "stats": "stats_image"}
IMAGE_EXTENSIONS = {".png", ".webp", ".jpg", ".jpeg"}


class Command(BaseCommand):
    help = "Attach <slug>-look.png / <slug>-stats.png images to items."

    def add_arguments(self, parser):
        parser.add_argument("folder", help="Folder with the extracted images.")
        parser.add_argument("--vanilla", action="store_true", help="Match vanilla items instead of new items.")
        parser.add_argument("--dry-run", action="store_true", help="Report what would be attached, change nothing.")

    def handle(self, *args, folder, vanilla, dry_run, **options):
        folder = Path(folder)
        if not folder.is_dir():
            raise CommandError(f"{folder} is not a folder")

        attached, unmatched = [], []
        for path in sorted(folder.iterdir()):
            match = re.fullmatch(r"(.+)-(look|stats)", path.stem)
            if path.suffix.lower() not in IMAGE_EXTENSIONS or not match:
                continue
            slug, kind = match.group(1).lower(), match.group(2)
            item = Item.objects.filter(is_vanilla=vanilla, slug=slug).first()
            if item is None:
                unmatched.append(path.name)
                continue
            if not dry_run:
                self._attach(item, KINDS[kind], path)
            attached.append(f"{path.name} -> {item.name} ({kind})")

        prefix = "[dry run] would attach" if dry_run else "Attached"
        self.stdout.write(self.style.SUCCESS(f"{prefix} {len(attached)} image(s)."))
        for line in attached:
            self.stdout.write(f"  {line}")
        if unmatched:
            collection = "vanilla" if vanilla else "new"
            self.stdout.write(self.style.WARNING(
                f"\nNo {collection} item with a matching slug for {len(unmatched)} file(s):"
            ))
            for name in unmatched:
                self.stdout.write(f"  {name}")

    @staticmethod
    def _attach(item, field_name, path):
        field = getattr(item, field_name)
        target_name = f"{item.slug}-{'look' if field_name == 'image' else 'stats'}{path.suffix.lower()}"
        if field:
            field.delete(save=False)  # replace instead of piling up copies
        # A file may already sit under the target name without being linked to this
        # item (e.g. the database was restored); overwrite it instead of letting the
        # storage add a random suffix like "-look_Ab12Cd3.png".
        full_name = field.field.generate_filename(item, target_name)
        if field.storage.exists(full_name):
            field.storage.delete(full_name)
        with path.open("rb") as handle:
            field.save(target_name, File(handle), save=False)
        item.save(update_fields=[field_name, "updated_at"])
