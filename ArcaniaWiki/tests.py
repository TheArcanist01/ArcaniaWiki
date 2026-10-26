import re
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Article, Enemy, GameOrigin, Item, ItemSource, ItemSourceDrop, Level


class WikiTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_game = GameOrigin.objects.create(name="Base Game", slug="base-game")
        cls.big_game_hunt = GameOrigin.objects.create(name="Big Game Hunt", slug="big-game-hunt")

        cls.woundspike_source = ItemSource.objects.create(name="Woundspike")
        cls.chest_source = ItemSource.objects.create(name="Golden Chest")

        cls.level = Level.objects.create(name="Hunter's Grotto", game_origin=cls.big_game_hunt)
        cls.enemy = Enemy.objects.create(
            name="Woundspike",
            slug="woundspike",
            enemy_type="Skag",
            game_origin=cls.big_game_hunt,
            level=cls.level,
            drop_source=cls.woundspike_source,
            trivia="A **big** skag.",
        )

        cls.blister = Item.objects.create(
            name="Blister",
            slug="blister",
            item_type="weapon",
            weapon_type="assault_rifle",
            rarity="legendary",
            manufacturer="vladof",
            game_origin=cls.big_game_hunt,
            content="Shoots *blisters*.",
        )
        cls.common_gun = Item.objects.create(
            name="Aaa Common Gun", slug="aaa-common-gun", item_type="weapon",
            weapon_type="pistol", rarity="common",
        )
        cls.seraph_gun = Item.objects.create(
            name="Zzz Seraph Gun", slug="zzz-seraph-gun", item_type="weapon",
            weapon_type="smg", rarity="seraph",
        )
        cls.shield = Item.objects.create(
            name="Deflector", slug="deflector", item_type="shield",
            rarity="very_rare", manufacturer="jakobs",
        )
        cls.vanilla_shield = Item.objects.create(
            name="The Bee", slug="the-bee", item_type="shield", is_vanilla=True,
            rarity="legendary", manufacturer="hyperion", game_origin=cls.base_game,
        )
        ItemSourceDrop.objects.create(item=cls.blister, source=cls.woundspike_source, drop_chance=10)
        ItemSourceDrop.objects.create(item=cls.shield, source=cls.chest_source)

        cls.mission_source = ItemSource.objects.create(name="Shoot This Guy in the Face", source_type="mission")
        cls.vanilla_boss_source = ItemSource.objects.create(name="Hyperius", source_type="enemy")
        ItemSourceDrop.objects.create(item=cls.shield, source=cls.mission_source, drop_note="Quest Reward")
        ItemSourceDrop.objects.create(item=cls.shield, source=cls.vanilla_boss_source, drop_chance=5)


class DropSourceTests(WikiTestCase):
    def test_custom_enemy_marks_its_source_as_enemy(self):
        self.woundspike_source.refresh_from_db()
        self.assertEqual(self.woundspike_source.source_type, "enemy")
        self.assertEqual(self.woundspike_source.custom_enemy, self.enemy)
        self.assertIsNone(self.vanilla_boss_source.custom_enemy)

    def test_list_tags_are_styled_by_type_and_only_custom_enemies_link(self):
        response = self.client.get(reverse("arcaniawiki:item_collection", args=["new-items"]))
        self.assertContains(response, "source-tag--enemy")
        self.assertContains(response, "source-tag--mission")
        self.assertContains(response, "source-tag--other")
        self.assertContains(response, "Quest Reward")
        html = response.content.decode()
        # The custom enemy's tag is a link to its page...
        self.assertRegex(
            html, rf'<a href="{self.enemy.get_absolute_url()}" class="source-tag source-tag--enemy source-tag--link"'
        )
        # ...and no other source tag links anywhere.
        self.assertEqual(len(re.findall(r'<a href="[^"]*" class="source-tag ', html)), 1)

    def test_detail_links_only_custom_enemies(self):
        response = self.client.get(self.blister.get_absolute_url())
        self.assertContains(response, f'href="{self.enemy.get_absolute_url()}"')

        response = self.client.get(self.shield.get_absolute_url())
        self.assertContains(response, "Quest Reward")
        self.assertContains(response, "Hyperius")
        self.assertContains(response, "5% chance")
        # No links to enemy pages: Hyperius is not a custom enemy, the mission is not an enemy.
        self.assertNotRegex(response.content.decode(), r'href="/enemies/[^"]+/"')

    def test_filter_text_includes_drop_note(self):
        response = self.client.get(reverse("arcaniawiki:item_list", args=["new-items", "shields"]))
        self.assertRegex(response.content.decode(), r'data-filter-text="[^"]*Quest Reward[^"]*"')


class ItemPagesTests(WikiTestCase):
    def test_collections_are_separate(self):
        response = self.client.get(reverse("arcaniawiki:item_collection", args=["new-items"]))
        self.assertContains(response, "Blister")
        self.assertNotContains(response, "The Bee")

        response = self.client.get(reverse("arcaniawiki:item_collection", args=["vanilla-items"]))
        self.assertContains(response, "The Bee")
        self.assertNotContains(response, "Blister")

    def test_all_items_list_has_type_column(self):
        response = self.client.get(reverse("arcaniawiki:item_collection", args=["new-items"]))
        keys = [column["key"] for column in response.context["columns"]]
        self.assertIn("type", keys)
        self.assertNotIn("weapon_type", keys)

    def test_weapon_list_has_weapon_type_column(self):
        response = self.client.get(reverse("arcaniawiki:item_list", args=["new-items", "weapons"]))
        keys = [column["key"] for column in response.context["columns"]]
        self.assertIn("weapon_type", keys)
        self.assertNotIn("class", keys)
        self.assertContains(response, "Assault Rifle")
        self.assertNotContains(response, "Deflector")

    def test_class_mod_list_has_class_column_and_empty_message(self):
        response = self.client.get(reverse("arcaniawiki:item_list", args=["new-items", "class-mods"]))
        keys = [column["key"] for column in response.context["columns"]]
        self.assertIn("class", keys)
        self.assertContains(response, "Arcania does not add class mods yet.")

    def test_rarity_sorts_by_tier(self):
        url = reverse("arcaniawiki:item_list", args=["new-items", "weapons"])
        names = [item.name for item in self.client.get(url + "?sort=rarity").context["items"]]
        self.assertEqual(names, ["Aaa Common Gun", "Blister", "Zzz Seraph Gun"])
        names = [item.name for item in self.client.get(url + "?sort=rarity&direction=desc").context["items"]]
        self.assertEqual(names, ["Zzz Seraph Gun", "Blister", "Aaa Common Gun"])

    def test_every_sort_option_works(self):
        url = reverse("arcaniawiki:item_collection", args=["new-items"])
        for key in ["order", "name", "type", "rarity", "manufacturer", "game_origin", "sources", "bogus"]:
            for direction in ["asc", "desc"]:
                response = self.client.get(url, {"sort": key, "direction": direction})
                self.assertEqual(response.status_code, 200, key)

    def test_rows_carry_filter_text(self):
        response = self.client.get(reverse("arcaniawiki:item_list", args=["new-items", "weapons"]))
        self.assertContains(response, 'data-filter-text="Blister Assault Rifle Legendary Vladof')
        self.assertContains(response, "data-live-filter=")

    def test_item_detail(self):
        response = self.client.get(self.blister.get_absolute_url())
        self.assertEqual(self.blister.get_absolute_url(), "/new-items/weapons/blister/")
        self.assertContains(response, "<em>blisters</em>", html=True)
        self.assertContains(response, "Vladof")
        # The drop source is an Arcania enemy, so it links to the enemy page.
        self.assertContains(response, self.enemy.get_absolute_url())

    def test_item_detail_wrong_type_or_collection_is_404(self):
        self.assertEqual(self.client.get("/new-items/shields/blister/").status_code, 404)
        self.assertEqual(self.client.get("/vanilla-items/weapons/blister/").status_code, 404)
        self.assertEqual(self.client.get("/new-items/hats/").status_code, 404)

    def test_item_validation(self):
        item = Item(name="X", slug="x", item_type="shield", rarity="rare", weapon_type="smg")
        with self.assertRaises(ValidationError):
            item.full_clean()
        item = Item(name="X", slug="x", item_type="weapon", rarity="rare", character_class="siren")
        with self.assertRaises(ValidationError):
            item.full_clean()


class EnemyPagesTests(WikiTestCase):
    def test_enemy_list_shows_drops(self):
        response = self.client.get(reverse("arcaniawiki:enemy_list"))
        self.assertContains(response, "Woundspike")
        self.assertContains(response, self.blister.get_absolute_url())

    def test_enemy_sorting(self):
        for key in ["name", "enemy_type", "game_origin", "level", "drops"]:
            response = self.client.get(reverse("arcaniawiki:enemy_list"), {"sort": key, "direction": "desc"})
            self.assertEqual(response.status_code, 200, key)

    def test_enemy_detail(self):
        response = self.client.get(self.enemy.get_absolute_url())
        self.assertContains(response, "Skag")
        self.assertContains(response, "Hunter&#x27;s Grotto")
        self.assertContains(response, "<h2>Trivia</h2>", html=True)
        self.assertContains(response, "<strong>big</strong>", html=True)
        self.assertContains(response, "Blister")

    def test_location_comes_before_trivia_and_shows_note(self):
        Enemy.objects.filter(pk=self.enemy.pk).update(location_note="rare spawn anywhere in the map")
        html = self.client.get(self.enemy.get_absolute_url()).content.decode()
        self.assertIn("Location: Hunter&#x27;s Grotto (rare spawn anywhere in the map)", html)
        self.assertLess(html.index("<h2>Location"), html.index("<h2>Trivia</h2>"))

    def test_enemy_without_trivia_has_no_trivia_box(self):
        Enemy.objects.filter(pk=self.enemy.pk).update(trivia="")
        response = self.client.get(self.enemy.get_absolute_url())
        self.assertNotContains(response, "<h2>Trivia</h2>", html=True)
        self.assertNotContains(response, "Description")

    def test_enemy_screenshot_is_shown_full_width_above_details(self):
        import shutil
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile

        self.assertNotContains(self.client.get(self.enemy.get_absolute_url()), "enemy-screenshot")
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        with self.settings(MEDIA_ROOT=media):
            self.enemy.image = SimpleUploadedFile("woundspike.jpg", b"jpg", content_type="image/jpeg")
            self.enemy.save()
            html = self.client.get(self.enemy.get_absolute_url()).content.decode()
        self.assertIn('<figure class="enemy-screenshot">', html)
        self.assertLess(html.index("enemy-screenshot"), html.index('class="detail-layout '))
        # The info column is stretched to the height of the map/trivia column.
        self.assertIn("detail-layout--stretch detail-layout--enemy", html)


class ArticlePagesTests(WikiTestCase):
    def setUp(self):
        self.old = Article.objects.create(
            title="Version 0.4.0", slug="v040", article_type="changelog", content="Old **notes**."
        )
        self.new = Article.objects.create(
            title="Version 0.5.0", slug="v050", article_type="changelog", content="New notes."
        )
        self.balance = Article.objects.create(
            title="Shield balance", slug="shield-balance", article_type="balance_change", content="Shields."
        )
        Article.objects.filter(pk=self.old.pk).update(updated_at=timezone.now() - timedelta(days=3))

    def test_sections_are_separate_and_sorted_by_update(self):
        response = self.client.get(reverse("arcaniawiki:article_list", args=["changelogs"]))
        titles = [article.title for article in response.context["articles"]]
        self.assertEqual(titles, ["Version 0.5.0", "Version 0.4.0"])
        # The list shows no excerpt, but the article text stays searchable by the live filter.
        self.assertNotContains(response, "article-card__excerpt")
        self.assertRegex(response.content.decode(), r'data-filter-text="Version 0.4.0 Old notes."')
        self.assertNotContains(response, "Shield balance")

    def test_article_detail_and_wrong_section(self):
        self.assertEqual(self.client.get(self.balance.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get("/changelogs/shield-balance/").status_code, 404)


class SiteTests(WikiTestCase):
    def test_logo_and_favicon(self):
        response = self.client.get(reverse("arcaniawiki:home"))
        self.assertContains(response, 'class="site-brand__logo" src="/static/arcaniawiki/img/arcania-logo-96.png"')
        self.assertContains(response, '<link rel="icon" href="/static/arcaniawiki/img/favicon.ico"')
        self.assertContains(response, 'href="/static/arcaniawiki/img/favicon-32.png" sizes="32x32"')

    def test_image_links_open_in_preview_window_not_new_tab(self):
        response = self.client.get(reverse("arcaniawiki:home"))
        self.assertRegex(response.content.decode(), r'src="/static/arcaniawiki/js/lightbox\.js\?v=\d+"')
        for path in ("arcaniawiki/item_detail.html", "arcaniawiki/enemy_detail.html"):
            source = (settings.BASE_DIR / "arcaniawiki" / "templates" / path).read_text()
            self.assertIn("data-lightbox", source)
            self.assertNotIn('target="_blank"', source)

    def test_css_and_js_urls_change_with_the_file(self):
        response = self.client.get(reverse("arcaniawiki:home"))
        self.assertRegex(response.content.decode(), r'href="/static/arcaniawiki/css/style\.css\?v=\d+"')
        self.assertRegex(response.content.decode(), r'src="/static/arcaniawiki/js/live-filter\.js\?v=\d+"')

    def test_home_and_navigation(self):
        Article.objects.create(title="Shield Changes", slug="shield-changes", article_type="balance_change", content="x")
        response = self.client.get(reverse("arcaniawiki:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/vanilla-items/shields/"')
        self.assertContains(response, 'href="/balance-changes/"')

    def test_empty_sections_are_hidden_from_navigation_and_home(self):
        html = self.client.get(reverse("arcaniawiki:home")).content.decode()
        # No class mods and no articles exist in the test data.
        self.assertNotIn("/class-mods/", html)
        self.assertNotIn('href="/changelogs/"', html)
        self.assertNotIn('href="/balance-changes/"', html)

        Item.objects.filter(is_vanilla=True).delete()
        html = self.client.get(reverse("arcaniawiki:home")).content.decode()
        self.assertNotIn("/vanilla-items/", html)
        self.assertIn('href="/new-items/"', html)

        Item.objects.create(name="Test Mod", slug="test-mod", item_type="class_mod", rarity="rare")
        html = self.client.get(reverse("arcaniawiki:home")).content.decode()
        self.assertIn('href="/new-items/class-mods/"', html)  # shows up once content exists

    def test_admin_panel_moved_to_arcaniawikiadmin(self):
        self.assertEqual(self.client.get("/admin/").status_code, 404)
        response = self.client.get("/arcaniawikiadmin/")
        self.assertRedirects(response, "/arcaniawikiadmin/login/?next=/arcaniawikiadmin/")

    def test_admin_login_is_blocked_after_repeated_failures(self):
        from django.contrib.auth import get_user_model
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        get_user_model().objects.create_superuser("boss", password="correct horse battery")
        login = "/arcaniawikiadmin/login/"
        for _ in range(settings.ADMIN_LOGIN_MAX_FAILURES):
            response = self.client.post(login, {"username": "boss", "password": "wrong"})
            self.assertEqual(response.status_code, 200)  # form shown again with an error
        response = self.client.post(login, {"username": "boss", "password": "correct horse battery"})
        self.assertEqual(response.status_code, 429)  # even the right password is refused now

        cache.clear()  # lockout over
        response = self.client.post(login, {"username": "boss", "password": "correct horse battery"})
        self.assertEqual(response.status_code, 302)

    def test_server_error_page(self):
        from django.template.loader import render_to_string

        html = render_to_string("500.html")
        self.assertIn("Something went wrong", html)

    def test_active_navigation_link(self):
        response = self.client.get("/new-items/weapons/blister/")
        self.assertContains(response, 'href="/new-items/weapons/" class="is-active"')

    def test_search_finds_items_and_enemies_but_not_articles(self):
        Article.objects.create(title="Woundspike notes", slug="wn", content="x")
        response = self.client.get(reverse("arcaniawiki:search"), {"q": "woundspike"})
        self.assertIn(self.blister, response.context["items"])  # via drop source
        self.assertIn(self.enemy, response.context["enemies"])
        self.assertNotContains(response, "Woundspike notes")

    def test_search_ignores_accents_in_item_names(self):
        item = Item.objects.create(
            name="Jötunn", slug="jotunn", item_type=self.blister.item_type, rarity=self.blister.rarity
        )
        response = self.client.get(reverse("arcaniawiki:search"), {"q": "jotunn"})
        self.assertIn(item, response.context["items"])

    def test_search_by_level(self):
        response = self.client.get(reverse("arcaniawiki:search"), {"q": "grotto"})
        self.assertIn(self.enemy, response.context["enemies"])

    def test_empty_search(self):
        response = self.client.get(reverse("arcaniawiki:search"))
        self.assertEqual(response.status_code, 200)


class PercentFilterTests(TestCase):
    def test_percent_strips_trailing_zeros(self):
        from decimal import Decimal

        from .templatetags.wiki_extras import percent

        self.assertEqual(percent(Decimal("10.00")), "10%")
        self.assertEqual(percent(Decimal("12.50")), "12.5%")
        self.assertEqual(percent(Decimal("0.25")), "0.25%")
        self.assertEqual(percent(Decimal("100.00")), "100%")
        self.assertEqual(percent(None), "")


class ImportParsingTests(TestCase):
    """The spreadsheet parser used by `manage.py import_items`."""

    def setUp(self):
        from .management.commands import import_items

        self.m = import_items

    def test_plain_enemy_drop(self):
        drops, enemy = self.m.parse_drops("Knuckledragger", "10%")
        self.assertEqual([(d.source, d.source_type, d.chance) for d in drops], [("Knuckledragger", "enemy", 10)])
        self.assertIsNone(enemy)

    def test_mission_with_enemy_after_completion(self):
        drops, _ = self.m.parse_drops(
            "Best Minion Ever\npost quest completion: Captain Flynt", "mission reward\nenemy drop: 33%"
        )
        self.assertEqual(drops[0].source, "Best Minion Ever")
        self.assertEqual((drops[0].source_type, drops[0].note), ("mission", "Quest Reward"))
        self.assertEqual((drops[1].source, drops[1].source_type, drops[1].chance), ("Captain Flynt", "enemy", 33))
        self.assertEqual(drops[1].unlocked_by, "Best Minion Ever")
        self.assertIsNone(drops[0].unlocked_by)

    def test_mission_variants(self):
        drops, _ = self.m.parse_drops("My First Gun (as Axton)", "mission reward")
        self.assertEqual((drops[0].source, drops[0].note), ("My First Gun", "Quest Reward (as Axton)"))
        drops, _ = self.m.parse_drops("Death Race - Tier 3", "mission reward")
        self.assertEqual((drops[0].source, drops[0].note), ("Death Race (Tier 3)", "Quest Reward"))

    def test_custom_enemy(self):
        drops, enemy = self.m.parse_drops("Flynn - custom enemy\nThree Horns - Valley\nshack", "10%")
        self.assertEqual(drops[0].source, "Flynn")
        self.assertEqual(enemy, ("Flynn", ["Three Horns - Valley", "shack"]))

    def test_split_sources_and_variant_chances(self):
        drops, _ = self.m.parse_drops("Warlord Turge/Warlord Grug", "10%")
        self.assertEqual([d.source for d in drops], ["Warlord Turge", "Warlord Grug"])
        drops, _ = self.m.parse_drops("Tropical Varkids", "5% (Tropical Varkid)\n33% (Badass/Elemental Varkid)")
        self.assertEqual(
            [(d.source, d.chance) for d in drops],
            [("Tropical Varkid", 5), ("Badass Varkid", 33), ("Elemental Varkid", 33)],
        )

    def test_chance_with_condition_becomes_note(self):
        drops, _ = self.m.parse_drops("Sacrifice Altar", "50% (on 'rare item' roll)")
        self.assertEqual((drops[0].source_type, drops[0].chance, drops[0].note), ("other", None, "50% (on 'rare item' roll)"))

    def test_doubtful_rows_raise(self):
        for source, chance in [
            ("Muscles", "1"),
            ("Treasure pod hidden chests\n(Note: bugged)", "N/A"),
        ]:
            with self.assertRaises(self.m.Doubt):
                self.m.parse_drops(source, chance)

    def test_vendor_after_mission(self):
        drops, _ = self.m.parse_drops("Long Way To The Top\npost quest completion: Torgue vendor", "mission reward")
        self.assertEqual(
            [(d.source, d.source_type, d.chance, d.note, d.unlocked_by) for d in drops],
            [
                ("Long Way To The Top", "mission", None, "Quest Reward", None),
                ("Torgue vendor", "other", None, "Buyable", "Long Way To The Top"),
            ],
        )

    def test_types_and_content(self):
        self.assertEqual(self.m.parse_type("Nova Shield"), ("shield", ""))
        self.assertEqual(self.m.parse_type("MIRV"), ("grenade_mod", ""))
        self.assertEqual(self.m.parse_type("Elemental Relic"), ("relic", ""))
        self.assertEqual(self.m.parse_type("SMG "), ("weapon", "smg"))
        self.assertEqual(self.m.parse_manufacturer("DAHL"), "dahl")
        self.assertEqual(self.m.format_content("Text: \n- a\n- b"), "Text:\n\n- a\n- b")


class GameOriginNameTests(TestCase):
    def test_sheet_sections_use_short_names(self):
        from .management.commands.import_items import game_origin_for

        GameOrigin.objects.create(name="Sir Hammerlock's Big Game Hunt", slug="sir-hammerlocks-big-game-hunt")
        origin = game_origin_for("Sir Hammerlock's Big Game Hunt")
        self.assertEqual((origin.name, origin.slug), ("Big Game Hunt", "big-game-hunt"))
        self.assertEqual(GameOrigin.objects.count(), 1)  # renamed, not duplicated
        self.assertEqual(game_origin_for("Borderlands 2").name, "Base Game")
        self.assertEqual(game_origin_for("Borderlands 2"), game_origin_for("Borderlands 2"))


class DropOrderAndConditionTests(WikiTestCase):
    def setUp(self):
        self.mission = ItemSource.objects.create(name="Best Minion Ever", source_type="mission")
        self.flynt = ItemSource.objects.create(name="Captain Flynt", source_type="enemy")
        self.survivor = Item.objects.create(name="Survivor", slug="survivor", item_type="weapon", rarity="rare")
        # Created in "wrong" order on purpose: other, enemy, mission.
        ItemSourceDrop.objects.create(item=self.survivor, source=self.chest_source)
        ItemSourceDrop.objects.create(item=self.survivor, source=self.flynt, drop_chance=33, unlocked_by=self.mission)
        ItemSourceDrop.objects.create(item=self.survivor, source=self.mission, drop_note="Quest Reward")

    def test_sources_listed_missions_enemies_others(self):
        response = self.client.get(reverse("arcaniawiki:item_list", args=["new-items", "weapons"]))
        item = next(i for i in response.context["items"] if i.name == "Survivor")
        self.assertEqual(
            [d.source.name for d in item.source_drops.all()],
            ["Best Minion Ever", "Captain Flynt", "Golden Chest"],
        )

    def test_detail_shows_post_quest_completion(self):
        response = self.client.get(self.survivor.get_absolute_url())
        self.assertContains(response, "Post completion of: Best Minion Ever", count=1)
        html = response.content.decode()
        self.assertLess(html.index("Best Minion Ever"), html.index("Captain Flynt"))

    def test_list_has_no_view_details(self):
        response = self.client.get(reverse("arcaniawiki:item_collection", args=["new-items"]))
        self.assertNotContains(response, "View details")


class AppearanceOrderTests(WikiTestCase):
    def setUp(self):
        # Order of appearance differs from alphabetical; Deflector has none and goes last.
        Item.objects.filter(pk=self.seraph_gun.pk).update(appearance_order=1)
        Item.objects.filter(pk=self.blister.pk).update(appearance_order=2)
        Item.objects.filter(pk=self.common_gun.pk).update(appearance_order=3)

    def test_default_sort_is_order_of_appearance(self):
        response = self.client.get(reverse("arcaniawiki:item_collection", args=["new-items"]))
        names = [item.name for item in response.context["items"]]
        self.assertEqual(names, ["Zzz Seraph Gun", "Blister", "Aaa Common Gun", "Deflector"])
        first = response.context["columns"][0]
        self.assertEqual((first["key"], first["label"], first["active"]), ("order", "Order of Appearance", True))
        self.assertContains(response, 'class="data-table__image-heading"')

    def test_order_of_appearance_descending(self):
        url = reverse("arcaniawiki:item_list", args=["new-items", "weapons"])
        names = [item.name for item in self.client.get(url, {"sort": "order", "direction": "desc"}).context["items"]]
        self.assertEqual(names, ["Aaa Common Gun", "Blister", "Zzz Seraph Gun"])

    def test_import_numbers_rows_in_sheet_order(self):
        from .management.commands.import_items import read_sheet
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Loot Sources.xlsx")
        if not os.path.exists(path):
            self.skipTest("spreadsheet not present")
        items, _ = read_sheet(path)
        self.assertEqual([item.order for item in items], list(range(1, len(items) + 1)))


class ElementTests(WikiTestCase):
    def test_parse_elements(self):
        from .management.commands.import_items import Doubt, parse_elements

        self.assertEqual(parse_elements("nicsl"), "nicsl")
        self.assertEqual(parse_elements("isce"), "icse")  # standard order
        self.assertEqual(parse_elements("n"), "n")
        self.assertEqual(parse_elements("N/A"), "")
        self.assertEqual(parse_elements(None), "")
        with self.assertRaises(Doubt):
            parse_elements("x")

    def test_item_page_shows_elements_and_item_effects(self):
        Item.objects.filter(pk=self.blister.pk).update(elements="ics")
        response = self.client.get(self.blister.get_absolute_url())
        self.assertContains(response, "<h2>Item Effects</h2>", html=True)
        self.assertNotContains(response, "<h2>Description</h2>", html=True)
        self.assertContains(response, '<span class="element-badge element-badge--i">Incendiary</span>', html=True)
        self.assertContains(response, '<span class="element-badge element-badge--s">Shock</span>', html=True)
        self.assertNotContains(response, "Non-Elemental")

    def test_items_without_elements_have_no_elements_row(self):
        response = self.client.get(self.shield.get_absolute_url())
        self.assertNotContains(response, "<dt>Elements</dt>", html=True)

    def test_admin_form_stores_codes_in_standard_order(self):
        from .admin import ItemAdminForm

        form = ItemAdminForm(instance=self.blister)
        self.assertEqual(form.initial["elements"], [])
        form = ItemAdminForm(
            data={"item_type": "weapon", "name": "Blister", "slug": "blister", "rarity": "legendary",
                  "elements": ["s", "n", "i"]},
            instance=self.blister,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["elements"], "nis")


class TriviaAndChangesTests(WikiTestCase):
    def test_empty_boxes_show_placeholders(self):
        response = self.client.get(self.blister.get_absolute_url())
        self.assertContains(response, "<h2>Trivia</h2>", html=True)
        self.assertContains(response, "<h2>Changes</h2>", html=True)
        self.assertContains(response, "No trivia has been added yet.")
        self.assertContains(response, "No changes have been recorded yet.")

    def test_markdown_is_rendered(self):
        Item.objects.filter(pk=self.blister.pk).update(trivia="Named after a **blister**.", changes="- 0.5.0: buffed")
        response = self.client.get(self.blister.get_absolute_url())
        self.assertContains(response, "<strong>blister</strong>", html=True)
        self.assertContains(response, "<li>0.5.0: buffed</li>", html=True)
        self.assertNotContains(response, "No trivia has been added yet.")

    def test_change_versions_are_bold_links_to_changelogs(self):
        changelog = Article.objects.create(title="Arcania 0.4.0", slug="arcania-0-4-0", content="x")
        Item.objects.filter(pk=self.blister.pk).update(
            changes="- 0.4.0 - Blister damage reduced.\r\n- 0.1.0 - Added."
        )
        response = self.client.get(self.blister.get_absolute_url())
        self.assertContains(
            response,
            f'<li><a href="{changelog.get_absolute_url()}"><strong>0.4.0</strong></a> - Blister damage reduced.</li>',
            html=True,
        )
        # No changelog for this version: bold only, no link.
        self.assertContains(response, "<li><strong>0.1.0</strong> - Added.</li>", html=True)
        # The stored text stays plain.
        self.blister.refresh_from_db()
        self.assertTrue(self.blister.changes.startswith("- 0.4.0 - "))

    def test_import_keeps_trivia_and_changes(self):
        from .management.commands.import_items import Command, ParsedItem

        Item.objects.filter(pk=self.blister.pk).update(trivia="Keep me", changes="Keep me too")
        parsed = ParsedItem(
            row=1, name="Blister", item_type="weapon", weapon_type="assault_rifle", rarity="legendary",
            manufacturer="torgue", game_origin="Sir Hammerlock's Big Game Hunt", content="New text", order=1,
        )
        Command()._import([parsed], dry_run=False)
        self.blister.refresh_from_db()
        self.assertEqual((self.blister.content, self.blister.trivia, self.blister.changes),
                         ("New text", "Keep me", "Keep me too"))


class ItemImageTests(WikiTestCase):
    def setUp(self):
        import shutil
        import tempfile

        from django.test import override_settings
        from PIL import Image

        self.media = tempfile.mkdtemp()
        self.source = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.source, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        for name in ["blister-look.png", "blister-stats.png", "unknown-look.png", "notes.txt"]:
            path = f"{self.source}/{name}"
            if name.endswith(".png"):
                Image.new("RGBA", (40, 10), (200, 100, 0, 255)).save(path)
            else:
                open(path, "w").close()

    def attach(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("attach_item_images", self.source, *args, stdout=out)
        return out.getvalue()

    def test_attach_matches_files_to_items_by_slug(self):
        output = self.attach()
        self.blister.refresh_from_db()
        self.assertEqual(self.blister.image.name, "items/blister-look.png")
        self.assertEqual(self.blister.stats_image.name, "items/stats/blister-stats.png")
        self.assertIn("unknown-look.png", output)  # reported, not attached

    def test_attach_again_replaces_instead_of_duplicating(self):
        import os

        self.attach()
        self.attach()
        self.blister.refresh_from_db()
        self.assertEqual(self.blister.image.name, "items/blister-look.png")
        self.assertEqual(os.listdir(f"{self.media}/items/stats"), ["blister-stats.png"])

    def test_attach_overwrites_a_leftover_file_instead_of_renaming(self):
        import os

        os.makedirs(f"{self.media}/items", exist_ok=True)
        open(f"{self.media}/items/blister-look.png", "wb").write(b"old")  # not linked to the item
        self.attach()
        self.blister.refresh_from_db()
        self.assertEqual(self.blister.image.name, "items/blister-look.png")
        self.assertEqual(sorted(os.listdir(f"{self.media}/items")), ["blister-look.png", "stats", "thumbs"])

    def test_dry_run_changes_nothing(self):
        self.attach("--dry-run")
        self.blister.refresh_from_db()
        self.assertFalse(self.blister.image)

    def test_pages_show_look_and_stats_card(self):
        self.attach()
        detail = self.client.get(self.blister.get_absolute_url())
        self.assertContains(detail, 'src="/media/items/blister-look.png"')
        self.assertContains(detail, 'src="/media/items/stats/blister-stats.png"')
        listing = self.client.get(reverse("arcaniawiki:item_list", args=["new-items", "weapons"]))
        self.assertContains(listing, 'src="/media/items/thumbs/blister.webp"')
        self.assertNotContains(listing, "blister-look.png")  # list uses the small thumbnail
        self.assertNotContains(listing, "blister-stats.png")  # list shows the item only

    def test_thumbnail_is_made_small_and_replaced_with_the_image(self):
        import os

        from PIL import Image

        big = f"{self.source}/blister-look.png"
        picture = Image.new("RGBA", (2000, 600), (0, 0, 0, 0))  # transparent background
        picture.paste((200, 100, 0, 255), (100, 100, 1900, 500))
        picture.save(big)
        self.attach()
        self.blister.refresh_from_db()
        self.assertEqual(self.blister.thumbnail.name, "items/thumbs/blister.webp")
        with Image.open(self.blister.thumbnail.path) as thumb:
            self.assertLessEqual(thumb.width, 320)
            self.assertLessEqual(thumb.height, 140)
            self.assertEqual(thumb.mode, "RGBA")  # transparency kept
        Image.new("RGBA", (100, 100), (0, 0, 255, 255)).save(big)
        self.attach()
        self.blister.refresh_from_db()
        self.assertEqual(os.listdir(f"{self.media}/items/thumbs"), ["blister.webp"])
        with Image.open(self.blister.thumbnail.path) as thumb:
            self.assertEqual(thumb.size, (100, 100))  # never enlarged

    def test_thumbnail_is_saved_under_a_bare_filename(self):
        # On Windows the generated name uses backslashes; passing it back to save()
        # once doubled the folder (items/thumbs/items/thumbs/...).
        from unittest import mock

        from django.db.models.fields.files import ImageFieldFile

        self.attach()
        self.blister.refresh_from_db()
        field = Item._meta.get_field("thumbnail")
        original = field.generate_filename
        windows_style = lambda instance, name: original(instance, name).replace("/", "\\")
        saved_as = []
        real_save = ImageFieldFile.save

        def spy(file, name, content, save=True):
            saved_as.append(name)
            with mock.patch.object(field, "generate_filename", original):
                return real_save(file, name, content, save)

        with mock.patch.object(field, "generate_filename", side_effect=windows_style), \
                mock.patch.object(ImageFieldFile, "save", spy):
            self.blister.update_thumbnail()
        self.assertEqual(saved_as, ["blister.webp"])
        self.assertEqual(self.blister.thumbnail.name, "items/thumbs/blister.webp")

    def test_make_thumbnails_command_fills_missing_ones(self):
        from io import StringIO

        from django.core.management import call_command

        self.attach()
        Item.objects.filter(pk=self.blister.pk).update(thumbnail="", thumbnail_source="")
        out = StringIO()
        call_command("make_thumbnails", stdout=out)
        self.blister.refresh_from_db()
        self.assertEqual(self.blister.thumbnail.name, "items/thumbs/blister.webp")
        self.assertIn("Made 1 thumbnail", out.getvalue())

    def test_items_without_images_show_placeholders(self):
        response = self.client.get(self.blister.get_absolute_url())
        self.assertContains(response, "No image available")
        self.assertContains(response, "No stats card available")
