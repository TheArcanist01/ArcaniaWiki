"""
Import Arcania items from the "Loot Sources" spreadsheet.

    python manage.py import_items "Loot Sources.xlsx"
    python manage.py import_items "Loot Sources.xlsx" --dry-run
    python manage.py import_items "Loot Sources.xlsx" --skip "Fabricator" --skip "Smother"

Spreadsheet layout (one sheet):
    - a section header row (e.g. "Borderlands 2", "Sir Hammerlock's Big Game Hunt")
      -> the Game / DLC of the items below it,
    - a column header row ("Item Name", "Manufacturer", "Type", ...),
    - item rows. The fill colour of the item name cell is the rarity.

Safe to run again: items are matched by slug and updated, and their drop
sources are replaced with the ones from the sheet. Images and custom enemy
pages are never touched. Rows the importer cannot interpret with certainty
are skipped and listed at the end.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify

from arcaniawiki.choices import Element, ItemType, Manufacturer, Rarity, SourceType, WeaponType
from arcaniawiki.models import Enemy, GameOrigin, Item, ItemSource, ItemSourceDrop

# Fill colour of the item name cell -> rarity (standard Borderlands 2 colours).
RARITY_BY_FILL = {
    "FF3C8EFF": Rarity.RARE,         # blue
    "FFFFB400": Rarity.LEGENDARY,    # orange
    "FFFF9AB8": Rarity.SERAPH,       # pink
    "FF00FFFF": Rarity.PEARLESCENT,  # cyan
}

WEAPON_TYPES = {
    "pistol": WeaponType.PISTOL,
    "shotgun": WeaponType.SHOTGUN,
    "smg": WeaponType.SMG,
    "assault rifle": WeaponType.ASSAULT_RIFLE,
    "sniper rifle": WeaponType.SNIPER_RIFLE,
    "rocket launcher": WeaponType.ROCKET_LAUNCHER,
}

GRENADE_TYPES = {
    "grenade", "frag grenade", "area of effect", "mirv",
    "bouncing betty", "singularity", "transfusion",
}

# Drop sources whose name contains one of these are not enemies.
NON_ENEMY_KEYWORDS = ("chest", "loot sources", "loot nests", "altar", "loot train", "presents", "vendor", "pod")

CUSTOM_ENEMY_MARKER = "- custom enemy"
PERCENT = r"\d+(?:[.,]\d+)?%"

# Section headers in the sheet -> short Game / DLC names used on the site.
GAME_ORIGIN_NAMES = {
    "Borderlands 2": "Base Game",
    "Captain Scarlett and her Pirate's Booty": "Pirate's Booty",
    "Mr Torgue's Campaign of Carnage": "Campaign of Carnage",
    "Sir Hammerlock's Big Game Hunt": "Big Game Hunt",
    "Tiny Tina's Assault on Dragon Keep": "Assault on Dragon Keep",
    "Commander Lilith and the Fight for Sanctuary": "Fight for Sanctuary",
    "How Marcus Saved Mercenary Day": "Mercenary Day",
    "The Horrible Hunger of the Ravenous Wattle Gobbler": "Horrible Hunger",
    "Mad Moxxi and the Wedding Day Massacre": "Wedding Day Massacre",
    "Sir Hammerlock vs. the Son of Crawmerax": "Son of Crawmerax",
    "T.K. Baha's Bloody Harvest": "Bloody Harvest",
    "The Raid on Digistruct Peak": "Digistruct Peak",
}


def game_origin_for(section):
    """Find or create the Game / DLC for a sheet section, under its short name."""
    short = GAME_ORIGIN_NAMES.get(section, section)
    origin = GameOrigin.objects.filter(
        Q(name=short) | Q(slug=slugify(short)) | Q(name=section) | Q(slug=slugify(section))
    ).first()
    if origin is None:
        return GameOrigin.objects.create(name=short, slug=slugify(short))
    if origin.name != short:
        origin.name, origin.slug = short, slugify(short)
        origin.save(update_fields=["name", "slug"])
    return origin


class Doubt(Exception):
    """Raised when a row cannot be interpreted with certainty."""


@dataclass
class ParsedDrop:
    source: str
    source_type: str
    chance: Decimal | None = None
    note: str = ""
    unlocked_by: str | None = None  # mission that must be completed first


@dataclass
class ParsedItem:
    row: int
    name: str
    item_type: str
    weapon_type: str
    rarity: str
    manufacturer: str
    game_origin: str
    content: str
    order: int
    elements: str = ""
    drops: list = field(default_factory=list)
    custom_enemy: tuple | None = None  # (name, [location lines])


def _lines(value):
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _percent(text):
    return Decimal(text.rstrip("%").replace(",", "."))


def _source_type(name):
    lowered = name.lower()
    if any(keyword in lowered for keyword in NON_ENEMY_KEYWORDS):
        return SourceType.OTHER
    return SourceType.ENEMY


def parse_chance(text):
    """'10%' -> (10, ''), '50% (on rare roll)' -> (None, '50% (on rare roll)'), 'N/A' -> (None, '')."""
    text = (text or "").strip()
    if text in ("", "N/A"):
        return None, ""
    if re.fullmatch(PERCENT, text):
        return _percent(text), ""
    if re.fullmatch(rf"{PERCENT}\s*\(.+\)", text):
        return None, text
    raise Doubt(f"unclear drop chance “{text}”")


def parse_mission(name):
    """'My First Gun (as Axton)' -> ('My First Gun', 'Quest Reward (as Axton)').
    The tier is part of the mission name: 'Bar Room Blitz - Tier 3' -> 'Bar Room Blitz (Tier 3)'."""
    match = re.fullmatch(r"(.+?)\s*\((as .+)\)", name)
    if match:
        return match.group(1), f"Quest Reward ({match.group(2)})"
    match = re.fullmatch(r"(.+?)\s*-\s*(Tier \d+)", name)
    if match:
        return f"{match.group(1)} ({match.group(2)})", "Quest Reward"
    return name, "Quest Reward"


def split_names(text, shared_tail=False):
    """'Warlord Turge/Warlord Grug' -> both names.
    With shared_tail: 'Badass/Elemental Varkid' -> 'Badass Varkid', 'Elemental Varkid'."""
    parts = [part.strip() for part in text.split("/") if part.strip()]
    if shared_tail and len(parts) > 1 and len(parts[-1].split()) > 1:
        tail = parts[-1].split()[-1]
        parts = [part if len(part.split()) > 1 else f"{part} {tail}" for part in parts]
    return parts


def parse_drops(source_cell, chance_cell):
    """Returns (drops, custom_enemy). Raises Doubt for anything ambiguous."""
    sources = _lines(source_cell)
    chances = _lines(chance_cell)
    if not sources:
        raise Doubt("no drop source")
    first = sources[0]

    # Custom Arcania enemy: name line + location lines.
    if first.lower().endswith(CUSTOM_ENEMY_MARKER):
        name = first[: -len(CUSTOM_ENEMY_MARKER)].strip()
        if len(chances) > 1:
            raise Doubt("several drop chances for one custom enemy")
        chance, note = parse_chance(chances[0] if chances else "")
        return [ParsedDrop(name, SourceType.ENEMY, chance, note)], (name, sources[1:])

    # Mission reward, optionally followed by "post quest completion: <enemy>" / "enemy drop: N%".
    if chances and chances[0].lower() == "mission reward":
        mission, note = parse_mission(first)
        drops = [ParsedDrop(mission, SourceType.MISSION, note=note)]
        if len(sources) == 1 and len(chances) == 1:
            return drops, None
        # "post quest completion: Torgue vendor" with no second chance -> buyable from that vendor.
        if len(sources) == 2 and len(chances) == 1:
            after = re.fullmatch(r"post quest completion:\s*(.+)", sources[1], re.IGNORECASE)
            if after and "vendor" in after.group(1).lower():
                vendor = after.group(1).strip()
                drops.append(ParsedDrop(vendor, SourceType.OTHER, note="Buyable", unlocked_by=mission))
                return drops, None
        if len(sources) == 2 and len(chances) == 2:
            after = re.fullmatch(r"post quest completion:\s*(.+)", sources[1], re.IGNORECASE)
            enemy_chance = re.fullmatch(r"enemy drop:\s*(.+)", chances[1], re.IGNORECASE)
            if after and enemy_chance:
                chance, chance_note = parse_chance(enemy_chance.group(1))
                enemy = after.group(1).strip()
                drops.append(ParsedDrop(enemy, _source_type(enemy), chance, chance_note, unlocked_by=mission))
                return drops, None
        raise Doubt("mission reward with an unclear second source or chance")

    # One chance per enemy variant: "5% (Craboid)" / "33% (Giant Craboid)".
    if len(chances) > 1:
        if len(sources) > 1:
            raise Doubt("multi-line drop source and chance")
        drops = []
        for line in chances:
            match = re.fullmatch(rf"({PERCENT})\s*\((.+)\)", line)
            if not match:
                raise Doubt(f"unclear drop chance “{line}”")
            for name in split_names(match.group(2), shared_tail=True):
                drops.append(ParsedDrop(name, _source_type(name), _percent(match.group(1))))
        return drops, None

    if len(sources) > 1:
        raise Doubt("drop source spans several lines: “" + " / ".join(sources) + "”")

    chance, note = parse_chance(chances[0] if chances else "")
    return [ParsedDrop(name, _source_type(name), chance, note) for name in split_names(first)], None


def parse_type(text):
    lowered = text.strip().lower()
    if lowered in WEAPON_TYPES:
        return ItemType.WEAPON, WEAPON_TYPES[lowered]
    if lowered.endswith("shield"):
        return ItemType.SHIELD, ""
    if lowered in GRENADE_TYPES:
        return ItemType.GRENADE_MOD, ""
    if lowered.endswith("relic"):
        return ItemType.RELIC, ""
    raise Doubt(f"unknown item type “{text}”")


def parse_manufacturer(text):
    lowered = (text or "").strip().lower()
    if lowered in Manufacturer.values:
        return lowered
    raise Doubt(f"unknown manufacturer “{text}”")


def parse_elements(text):
    """'nicsl' -> 'nicsl' (standard order), 'N/A' or empty -> ''."""
    text = str(text or "").strip().lower()
    if text in ("", "n/a"):
        return ""
    unknown = set(text) - set(Element.values)
    if unknown:
        raise Doubt(f"unknown element code(s) “{''.join(sorted(unknown))}”")
    return "".join(code for code in Element.values if code in text)


def format_content(text):
    """Keep the text as written; only add the blank line Markdown needs before a list."""
    lines = [line.rstrip() for line in str(text or "").strip().splitlines()]
    result = []
    for line in lines:
        if line.lstrip().startswith("- ") and result and result[-1] and not result[-1].lstrip().startswith("- "):
            result.append("")
        result.append(line)
    return "\n".join(result)


def read_sheet(path):
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise CommandError("openpyxl is required: pip install -r requirements.txt") from exc

    sheet = openpyxl.load_workbook(path).active
    section = None
    items, doubts = [], []
    order = 0  # position of the item row in the sheet = order of appearance

    for row in sheet.iter_rows(min_row=1):
        name_cell = row[0]
        values = [cell.value for cell in row[:7]]
        name = str(values[0]).strip() if values[0] is not None else ""
        if not name or name == "Item Name":
            continue
        if all(value is None for value in values[1:]):
            section = name
            continue

        order += 1
        try:
            if section is None:
                raise Doubt("no Game / DLC section above this row")
            rarity = RARITY_BY_FILL.get(name_cell.fill.fgColor.rgb if name_cell.fill.fill_type else None)
            if rarity is None:
                raise Doubt("row colour does not match a rarity")
            item_type, weapon_type = parse_type(str(values[2] or ""))
            drops, custom_enemy = parse_drops(values[3], values[4])
            items.append(ParsedItem(
                row=name_cell.row,
                name=name,
                item_type=item_type,
                weapon_type=weapon_type,
                rarity=rarity,
                manufacturer=parse_manufacturer(values[1]),
                game_origin=section,
                content=format_content(values[6]),
                order=order,
                elements=parse_elements(values[5]),
                drops=drops,
                custom_enemy=custom_enemy,
            ))
        except Doubt as doubt:
            doubts.append((name_cell.row, name, str(doubt)))

    return items, doubts


class Command(BaseCommand):
    help = "Import new Arcania items from the Loot Sources spreadsheet (.xlsx)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to the .xlsx file.")
        parser.add_argument("--dry-run", action="store_true", help="Parse and report, change nothing.")
        parser.add_argument(
            "--skip", action="append", default=[], metavar="NAME",
            help="Item name to leave out (can be repeated).",
        )

    def handle(self, *args, path, dry_run, skip, **options):
        items, doubts = read_sheet(path)

        skip_names = {name.strip().lower() for name in skip}
        skipped = [item for item in items if item.name.lower() in skip_names]
        items = [item for item in items if item.name.lower() not in skip_names]

        seen = {}
        for item in list(items):
            slug = slugify(item.name)
            if slug in seen:
                doubts.append((item.row, item.name, f"same URL slug as “{seen[slug]}”"))
                items.remove(item)
            seen[slug] = item.name

        created, updated = self._import(items, dry_run)
        self._report(items, doubts, skipped, created, updated, dry_run)

    @transaction.atomic
    def _import(self, items, dry_run):
        created = updated = 0
        sid = transaction.savepoint()

        for parsed in items:
            slug = slugify(parsed.name)
            origin = game_origin_for(parsed.game_origin)
            item, was_created = Item.objects.update_or_create(
                is_vanilla=False,
                slug=slug,
                defaults={
                    "name": parsed.name,
                    "item_type": parsed.item_type,
                    "weapon_type": parsed.weapon_type,
                    "character_class": "",
                    "rarity": parsed.rarity,
                    "manufacturer": parsed.manufacturer,
                    "game_origin": origin,
                    "content": parsed.content,
                    "appearance_order": parsed.order,
                    "elements": parsed.elements,
                },
            )
            created += was_created
            updated += not was_created

            item.source_drops.all().delete()
            sources_by_name = {}
            for drop in parsed.drops:
                # Case-insensitive match, so "Torgue vendor" reuses "Torgue Vendor".
                source = ItemSource.objects.filter(name__iexact=drop.source).first()
                source_created = source is None
                if source_created:
                    source = ItemSource.objects.create(name=drop.source, source_type=drop.source_type)
                if (
                    not source_created
                    and source.source_type == SourceType.OTHER
                    and drop.source_type != SourceType.OTHER
                    and source.custom_enemy is None
                ):
                    source.source_type = drop.source_type
                    source.save(update_fields=["source_type"])
                sources_by_name[drop.source] = source
                ItemSourceDrop.objects.create(
                    item=item,
                    source=source,
                    drop_chance=drop.chance,
                    drop_note=drop.note,
                    unlocked_by=sources_by_name.get(drop.unlocked_by),
                )

        if dry_run:
            transaction.savepoint_rollback(sid)
        else:
            transaction.savepoint_commit(sid)
        return created, updated

    def _report(self, items, doubts, skipped, created, updated, dry_run):
        write = self.stdout.write
        prefix = "[dry run] would have " if dry_run else ""
        write(self.style.SUCCESS(f"{prefix}created {created}, updated {updated} items."))

        if skipped:
            write(self.style.WARNING(f"\nSkipped on request ({len(skipped)}):"))
            for item in skipped:
                write(f"  row {item.row}: {item.name}")

        if doubts:
            write(self.style.WARNING(f"\nNot imported — needs checking ({len(doubts)}):"))
            for row, name, reason in sorted(doubts):
                write(f"  row {row}: {name} — {reason}")

        enemies = {}
        for item in items:
            if item.custom_enemy:
                enemies.setdefault(item.custom_enemy[0], item.custom_enemy[1])
        with_pages = set(Enemy.objects.filter(name__in=enemies).values_list("name", flat=True))
        enemies = {name: location for name, location in enemies.items() if name not in with_pages}
        if enemies:
            write("\nCustom enemies in the sheet without a page yet (add them in the admin):")
            for name, location in sorted(enemies.items()):
                write(f"  {name}: " + " / ".join(location))

        others = sorted({d.source for item in items for d in item.drops if d.source_type == SourceType.OTHER})
        if others:
            write("\nDrop sources marked as Other (not an enemy or mission): " + ", ".join(others))
