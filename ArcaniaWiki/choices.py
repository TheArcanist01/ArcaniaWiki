"""
Fixed vocabularies used across the wiki.

The order of every list matters: it is the order used for sorting
(e.g. rarity tiers) and for navigation menus.
"""

from django.db import models


class ItemType(models.TextChoices):
    WEAPON = "weapon", "Weapon"
    SHIELD = "shield", "Shield"
    GRENADE_MOD = "grenade_mod", "Grenade Mod"
    RELIC = "relic", "Relic"
    CLASS_MOD = "class_mod", "Class Mod"


# URL slug and plural page title for every item type.
ITEM_TYPE_PAGES = {
    ItemType.WEAPON: ("weapons", "Weapons"),
    ItemType.SHIELD: ("shields", "Shields"),
    ItemType.GRENADE_MOD: ("grenade-mods", "Grenade Mods"),
    ItemType.RELIC: ("relics", "Relics"),
    ItemType.CLASS_MOD: ("class-mods", "Class Mods"),
}

ITEM_TYPE_BY_SLUG = {slug: item_type for item_type, (slug, _) in ITEM_TYPE_PAGES.items()}


class Rarity(models.TextChoices):
    # Listed from lowest to highest tier.
    COMMON = "common", "Common"
    UNCOMMON = "uncommon", "Uncommon"
    RARE = "rare", "Rare"
    VERY_RARE = "very_rare", "Very Rare"
    E_TECH = "e_tech", "E-tech"
    LEGENDARY = "legendary", "Legendary"
    SERAPH = "seraph", "Seraph"
    PEARLESCENT = "pearlescent", "Pearlescent"
    EFFERVESCENT = "effervescent", "Effervescent"


class Manufacturer(models.TextChoices):
    ANSHIN = "anshin", "Anshin"
    BANDIT = "bandit", "Bandit"
    DAHL = "dahl", "Dahl"
    ERIDIAN = "eridian", "Eridian"
    HYPERION = "hyperion", "Hyperion"
    JAKOBS = "jakobs", "Jakobs"
    MALIWAN = "maliwan", "Maliwan"
    PANGOLIN = "pangolin", "Pangolin"
    TEDIORE = "tediore", "Tediore"
    TORGUE = "torgue", "Torgue"
    VLADOF = "vladof", "Vladof"


class WeaponType(models.TextChoices):
    PISTOL = "pistol", "Pistol"
    SHOTGUN = "shotgun", "Shotgun"
    SMG = "smg", "SMG"
    ASSAULT_RIFLE = "assault_rifle", "Assault Rifle"
    SNIPER_RIFLE = "sniper_rifle", "Sniper Rifle"
    ROCKET_LAUNCHER = "rocket_launcher", "Rocket Launcher"


class Element(models.TextChoices):
    # Codes match the Elements column of the spreadsheet.
    NON_ELEMENTAL = "n", "Non-Elemental"
    INCENDIARY = "i", "Incendiary"
    CORROSIVE = "c", "Corrosive"
    SHOCK = "s", "Shock"
    SLAG = "l", "Slag"
    EXPLOSIVE = "e", "Explosive"


class CharacterClass(models.TextChoices):
    COMMANDO = "commando", "Commando (Axton)"
    SIREN = "siren", "Siren (Maya)"
    GUNZERKER = "gunzerker", "Gunzerker (Salvador)"
    ASSASSIN = "assassin", "Assassin (Zer0)"
    MECHROMANCER = "mechromancer", "Mechromancer (Gaige)"
    PSYCHO = "psycho", "Psycho (Krieg)"


class ItemCollection:
    """The two separate item collections: Arcania's new gear and base game gear."""

    NEW = "new-items"
    VANILLA = "vanilla-items"

    TITLES = {
        NEW: "New Items",
        VANILLA: "Vanilla Items",
    }


class SourceType(models.TextChoices):
    ENEMY = "enemy", "Enemy"
    MISSION = "mission", "Mission"
    OTHER = "other", "Other"


class ArticleType(models.TextChoices):
    CHANGELOG = "changelog", "Changelog"
    BALANCE_CHANGE = "balance_change", "Balance Change"


# URL slug and page title for every article type.
ARTICLE_TYPE_PAGES = {
    ArticleType.CHANGELOG: ("changelogs", "Changelogs"),
    ArticleType.BALANCE_CHANGE: ("balance-changes", "Balance Changes"),
}

ARTICLE_TYPE_BY_SLUG = {slug: article_type for article_type, (slug, _) in ARTICLE_TYPE_PAGES.items()}
