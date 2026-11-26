import json
import os
import random
import unittest

import altay


class AltayEngineTests(unittest.TestCase):
    def new_game(self, seed=1):
        game = altay.new_game(7, 42, "Ada")
        self.assertIsNone(altay.join_game(game, 43, "Ben"))
        events = []
        self.assertIsNone(altay.start_game(game, events, random.Random(seed)))
        return game, events

    def new_seafarers_game(self, seed=1):
        game = altay.new_game(7, 42, "Ada")
        self.assertIsNone(altay.set_seafarers(game, True))
        self.assertIsNone(altay.join_game(game, 43, "Ben"))
        events = []
        self.assertIsNone(altay.start_game(game, events, random.Random(seed)))
        return game, events

    def test_module_contract_and_start(self):
        self.assertTrue(altay.validate())
        game, events = self.new_game()
        self.assertEqual(game["phase"], "playing")
        self.assertEqual(len(game["players"]), 2)
        self.assertEqual([p["faction"] for p in game["players"]], ["EARTHFOLK", "ELVENFOLK"])
        self.assertEqual(len(game["players"][0]["hand"]), altay.HAND_SIZE)
        self.assertIsNone(game["board"]["0"]["marker"])
        self.assertIsNone(game["board"]["3"]["marker"])
        self.assertEqual(game["board"]["0"]["settlements"], [0])
        self.assertEqual(game["board"]["3"]["settlements"], [1])
        self.assertTrue(events)

    def test_board_json_is_serializable_and_private(self):
        game, events = self.new_game()
        board = altay.board_json(game, 42)
        json.dumps(board)
        self.assertEqual(len(board["regions"]), 25)
        self.assertEqual(board["regions"][0]["pos"], altay.REGION_POS[0])
        self.assertEqual(len(board["players"][0]["hand"]), 5)
        self.assertEqual(board["players"][1]["hand"], [])
        self.assertEqual(board["players"][1]["hand_count"], 5)
        game["players"][1]["npc"] = True
        board = altay.board_json(game, 42)
        self.assertEqual(len(board["players"][1]["hand"]), 5)

    def test_play_produces_and_expire_at_end_of_turn(self):
        game, events = self.new_game()
        game["players"][0]["hand"] = ["hunter", "digger", "warrior", "village", "colonist"]
        self.assertIsNone(altay.play_card(game, 0, 0, events))
        self.assertEqual(game["players"][0]["resources"]["food"], 1)
        self.assertIsNone(altay.play_card(game, 0, 0, events))
        self.assertEqual(game["players"][0]["resources"]["stone"], 1)
        self.assertIsNone(altay.play_card(game, 0, 0, events))
        self.assertEqual(game["players"][0]["swords"], 1)
        self.assertIsNone(altay.end_turn(game, 0, events, random.Random(2)))
        self.assertEqual(game["current"], 1)
        self.assertEqual(game["players"][0]["resources"]["food"], 0)
        self.assertEqual(game["players"][0]["swords"], 0)

    def test_village_enforces_building_rules(self):
        game, events = self.new_game()
        player = game["players"][0]
        player["hand"] = ["village", "hunter", "hunter", "hunter", "hunter"]
        player["resources"]["food"] = 4
        self.assertIsNone(altay.play_card(game, 0, 0, events))
        self.assertEqual(player["builds"], 1)
        self.assertEqual(altay.legal_build(game, 0), [0])
        self.assertIsNotNone(altay.build_settlement(game, 0, 6, events))
        self.assertIsNone(altay.build_settlement(game, 0, 0, events))
        self.assertEqual(player["reserve"], altay.START_SETTLEMENTS - 1)
        self.assertEqual(game["board"]["0"]["settlements"], [0, 0])
        self.assertEqual(player["resources"]["food"], 2)
        self.assertIsNotNone(altay.build_settlement(game, 0, 0, events))

    def test_neutral_conquest_removes_marker_and_draws(self):
        game, events = self.new_game()
        player = game["players"][0]
        player["hand"] = ["warrior", "hunter", "hunter", "hunter", "hunter"]
        player["discard"] = []
        self.assertIsNone(altay.play_card(game, 0, 0, events))
        option = next(o for o in altay.attack_options(game, 0) if o["kind"] == "neutral")
        self.assertEqual(option["region"], 6)
        self.assertIsNone(altay.attack(game, 0, option["from"], option["region"], events, random.Random(3)))
        self.assertIsNone(game["board"]["6"]["marker"])
        self.assertEqual(player["markers"], 1)
        self.assertEqual(player["resources"]["wood"], 1)
        self.assertEqual(player["swords"], 0)
        json.dumps(game)

    def test_player_attack_captures_settlement(self):
        game, events = self.new_game()
        game["board"]["6"]["settlements"].append(1)
        game["board"]["6"]["marker"] = None
        player = game["players"][0]
        player["hand"] = ["warrior", "warrior", "hunter", "hunter", "hunter"]
        self.assertIsNone(altay.play_card(game, 0, 0, events))
        self.assertIsNone(altay.play_card(game, 0, 0, events))
        option = next(o for o in altay.attack_options(game, 0) if o["kind"] == "player")
        self.assertIsNone(altay.attack(game, 0, option["from"], 6, events, random.Random(4)))
        self.assertNotIn(1, game["board"]["6"]["settlements"])
        self.assertEqual(player["captured"], 1)

    def test_achievements_and_scoring(self):
        game, events = self.new_game()
        player = game["players"][0]
        player["resources"]["food"] = 3
        self.assertIsNone(altay.develop(game, 0, "irrigation", events))
        self.assertEqual(player["achievement"], "irrigation")
        self.assertIsNotNone(altay.develop(game, 0, "mining", events))
        self.assertIsNone(altay.develop(game, 0, "irrigation", events))
        self.assertEqual(player["achievements"], ["irrigation"])
        breakdown = altay.score_breakdown(game, 0)
        self.assertEqual(breakdown["achievements"], 1)
        self.assertEqual(breakdown["total"], breakdown["achievements"] + breakdown["cards"]
                         + breakdown["territories"] + breakdown["victory_markers"]
                         + breakdown["captured"] + breakdown["conquest_markers"])

    def test_market_limits_and_costs(self):
        game, events = self.new_game()
        player = game["players"][0]
        player["resources"]["wood"] = 2
        self.assertIsNone(altay.buy_card(game, 0, "worker", events))
        self.assertEqual(player["resources"]["wood"], 1)
        self.assertIsNotNone(altay.buy_card(game, 0, "worker", events))
        self.assertIsNotNone(altay.buy_card(game, 0, "chariot", events))

    def test_last_settlement_ends_game_after_equal_turns(self):
        game, events = self.new_game()
        player = game["players"][0]
        player["reserve"] = 1
        player["hand"] = ["village", "hunter", "hunter", "hunter", "hunter"]
        player["resources"]["food"] = 2
        self.assertIsNone(altay.play_card(game, 0, 0, events))
        self.assertIsNone(altay.build_settlement(game, 0, 0, events))
        self.assertIsNotNone(game["end_at"])
        self.assertIsNone(altay.end_turn(game, 0, events, random.Random(5)))
        self.assertEqual(game["phase"], "over")
        self.assertIn(game["winner"], (0, 1))
        self.assertEqual(len(game["scores"]), 2)
        json.dumps(game)

    def test_play_event_names_card_effect_and_board_json_exposes_played(self):
        # FB-0013: the effect of a played card must be visible — in the
        # event log line and in board_json's played list (Mini App shows
        # "Played this turn" with each card's effect text).
        game, events = self.new_game()
        game["players"][0]["hand"] = ["hunter", "warrior", "hunter", "hunter", "hunter"]
        self.assertIsNone(altay.play_card(game, 0, 0, events))
        self.assertTrue(any("Hunter" in e and "Produce 1 food" in e for e in events), events)
        board = altay.board_json(game, 42)
        played = board["players"][0]["played"]
        self.assertEqual([c["id"] for c in played], ["hunter"])
        self.assertEqual(played[0]["name"], "Hunter")
        self.assertIn("Produce 1 food", played[0]["text"])
        self.assertEqual(board["players"][1]["played"], [])

    def test_card_sprites_match_faction_decks_and_market_art(self):
        # FB-0018: the picture of a card must match its description. The
        # BGA sprite sheet lists each faction's starter deck in order
        # along its row, so a starter card's sprite column is its
        # position in its faction's deck; market cards use fixed coords
        # into the action-card rows (cols 1-8; cols 0 and 9 are backs).
        game, _ = self.new_game()
        for faction, info in altay.FACTIONS.items():
            game["players"][0]["faction"] = faction
            for index, card_id in enumerate(info["deck"]):
                sprite = altay._card_sprite(game, 0, card_id)
                # Duplicates share identical art, so the sprite column is
                # the card's first deck position; the cell there must be
                # this card.
                self.assertEqual(sprite, [info["deck"].index(card_id), info["row"]],
                                 f"{faction} {card_id} should be at deck position {index}")
                self.assertEqual(info["deck"][sprite[0]], card_id)
        expected_market = {
            "worker": [4, 12], "stonecutter": [4, 7], "farmer": [4, 4],
            "scholar": [4, 8], "chariot": [4, 13], "cavalry": [4, 10],
            "architect": [4, 11], "champion": [4, 10], "merchant": [4, 9],
            "city": [4, 14],
        }
        self.assertEqual(list(altay.MARKET), list(expected_market))
        board = altay.board_json(game, 42)
        for card in board["market"]:
            self.assertEqual(card["sprite"], expected_market[card["id"]],
                             f"market {card['id']} shows the wrong picture")
            col, row = card["sprite"]
            self.assertTrue(1 <= col <= 8 and 4 <= row <= 14,
                            f"market {card['id']} sprite {card['sprite']} is a card back or out of range")
        # Legacy ids from games saved before the rename still resolve.
        self.assertEqual(altay.CARDS["miner"]["name"], "Stonecutter")
        self.assertEqual(altay.CARDS["herbalist"]["name"], "Farmer")

    def test_seafarers_card_sprites_match_seafarers_sheets(self):
        # FB-0056: in Seafarers games every card showed slices of
        # several pictures at once. The Seafarers actions sheet is
        # 11 cols x 19 rows (not 10 x 18): the market rows sit one row
        # lower than on the base sheet and the sea cards are rows
        # 16-18. The Seafarers achievements sheet is 12 cols x 3 rows
        # (not 12 x 4). Every sprite below was checked against the
        # real sheets: the old coords showed a Town for Explorer, a
        # Town for Sailor, a Hunter for Shipwright, a blank cell for
        # Astronomy and the Triumphal Arch for Lighthouse.
        game, _ = self.new_seafarers_game()
        board = altay.board_json(game, 42)
        self.assertTrue(board["seafarers"])
        expected_market = {
            "worker": [4, 13], "stonecutter": [4, 8], "farmer": [4, 5],
            "scholar": [4, 9], "chariot": [4, 14], "cavalry": [4, 11],
            "architect": [4, 12], "champion": [4, 11], "merchant": [4, 10],
            "city": [4, 15], "explorer": [4, 16], "sailor": [4, 17],
            "shipwright": [4, 18],
        }
        self.assertEqual(list(altay.SEA_MARKET), list(expected_market))
        self.assertEqual(len(board["market"]), 13)
        for card in board["market"]:
            self.assertEqual(card["sprite"], expected_market[card["id"]],
                             f"seafarers market {card['id']} shows the wrong picture")
            col, row = card["sprite"]
            self.assertTrue(1 <= col <= 8 and 5 <= row <= 18,
                            f"seafarers market {card['id']} sprite {card['sprite']} "
                            "is a card back or out of range")
        # Starter cards keep their base coords: rows 0-3 are identical
        # in both sheets.
        for faction, info in altay.FACTIONS.items():
            game["players"][0]["faction"] = faction
            for card_id in info["deck"]:
                self.assertEqual(altay._card_sprite(game, 0, card_id),
                                 [info["deck"].index(card_id), info["row"]])
        expected_achievements = {"astronomy": [6, 0], "lighthouse": [11, 2]}
        for ach in board["achievements"]:
            col, row = ach["sprite"]
            self.assertTrue(0 <= col <= 11 and 0 <= row <= 2,
                            f"seafarers achievement {ach['id']} sprite {ach['sprite']} "
                            "is out of range")
            if ach["id"] in expected_achievements:
                self.assertEqual(ach["sprite"], expected_achievements[ach["id"]],
                                 f"seafarers achievement {ach['id']} shows the wrong picture")

    def test_seafarers_sprite_sheet_geometry_matches_files(self):
        # FB-0056: the Mini App sliced the Seafarers sheets with the
        # wrong grid (10x18 actions, 12x4 achievements). The CSS
        # background-size and the JS position divisors must match the
        # real sheets: 11 cols x 19 rows for actions, 12 cols x 3 rows
        # for achievements — verified here against the files on disk.
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "web", "flip7.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn("#altay.atseaon .atcard{background-image:url(altay-seafarers-actions.webp);"
                      "background-size:1100% 1900%}", html)
        self.assertIn("#altay.atseaon .atach{background-image:url(altay-seafarers-achievements.webp);"
                      "background-size:1200% 300%}", html)
        with open(os.path.join(base, "web", "altay.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("* 100 / (sea ? 10 : 9)", js)
        self.assertIn("* 100 / (sea ? 18 : 14)", js)
        self.assertIn("* 100 / (sea ? 11 : 10)", js)
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL not installed")

        def _size(name):
            with Image.open(os.path.join(base, "web", name)) as im:
                return im.size

        base_w, base_h = _size("altay-actions.webp")
        sea_w, sea_h = _size("altay-seafarers-actions.webp")
        cell_w, cell_h = base_w / 10, base_h / 15
        self.assertEqual(sea_w, 11 * cell_w)
        self.assertAlmostEqual(sea_h, 19 * cell_h, delta=1)
        base_aw, base_ah = _size("altay-achievements.webp")
        sea_aw, sea_ah = _size("altay-seafarers-achievements.webp")
        self.assertEqual(sea_aw, 12 * (base_aw / 11))
        self.assertEqual(sea_ah, base_ah)  # same height: still 3 rows

    def test_turn_order_and_wrong_player_guard(self):
        game, events = self.new_game()
        self.assertIsNotNone(altay.play_card(game, 1, 0, events))
        self.assertIsNone(altay.end_turn(game, 0, events, random.Random(6)))
        self.assertIsNone(altay.play_card(game, 1, 0, events))

    def test_achievements_show_description_under_each_card(self):
        """FB-0020: 'on altay, add the description under the achievements
        cards' — each achievement tile must be wrapped with a caption
        showing its name, cost, VP and effect text, not just a hover
        tooltip."""
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "web", "altay.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("atachwrap", js)
        self.assertIn("ach.text", js)
        self.assertIn("ach.vp + ' VP'", js)
        with open(os.path.join(base, "web", "flip7.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn(".atachwrap{flex:none;width:88px", html)

    def test_board_tokens_are_big_enough_to_see(self):
        """FB-0021: 'on altay, make the token on the board bigger, so
        they are easier to see' — the settlement tokens on the board
        were 10px squares inside a 34px region circle; both the region
        circle and the tokens (plus the conquest marker chips) must be
        substantially larger. FB-0023 replaced the plain squares with
        the faction token icons from altay-tokens.webp (20x26px)."""
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "web", "flip7.html"), encoding="utf-8") as f:
            html = f.read()
        # FB-0060: fixed 44px circles overlapped on the small territories
        # at phone width, so the circle is now min(44px, 10.5%) of the
        # board width — still 44px on a wide board, ~38px on a phone,
        # never below the 34px FB-0021 complained about.
        self.assertIn(".atregion{position:absolute;transform:translate(-50%,-50%);width:min(44px,10.5%);aspect-ratio:1/1;", html)
        self.assertIn(".atsettle{width:20px;height:26px;background-image:url(altay-tokens.webp);background-size:400% 100%;", html)
        self.assertIn(".atmarkerchip{position:absolute;transform:translate(-50%,-50%);width:42px;height:28px;", html)

    def test_settlements_use_faction_token_icons(self):
        """FB-0023: 'su altay, cambia i simboli delle icone che
        indicano gli insediamenti sulla plancia della mappa e usa come
        icone quelle disponibili su web/altay-tokens.webp' — settlements
        on the map must be drawn with the faction's token icon from
        altay-tokens.webp, not a plain coloured square. The sheet holds
        the 4 faction icons in FACTION_ORDER (4 columns), so the sprite
        grid is 400% with 0/33.3/66.7/100% positions — the old 600% /
        20% steps sliced icons in half. board_json must expose each
        settlement's faction for the Mini App to pick the icon."""
        game, _ = self.new_game()
        board = altay.board_json(game, 42)
        start = next(r for r in board["regions"]
                     if r["settlements"])
        self.assertEqual(start["settlements"][0]["faction"], "EARTHFOLK")
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "web", "altay.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("(idx * 100 / 3)", js)
        self.assertIn("atFactionStyle(s.faction)", js)
        self.assertNotIn("background:' + s.color", js)
        with open(os.path.join(base, "web", "flip7.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn(".atfaction{display:inline-block;width:26px;height:26px;background-image:url(altay-tokens.webp);background-size:400% 100%;", html)


    def test_action_buttons_explain_why_they_cannot_be_used(self):
        """FB-0022: 'on altay, the buttons buy, build, attack and develop
        do not work' — the engine was fine: every turn starts with 0
        resources, 0 builds and 0 swords (end_turn discards them), so
        all four actions are correctly impossible until hand cards are
        played. The Mini App gave no feedback: Build/Attack taps were
        silently ignored, and server errors were written to the log only
        to be wiped by the 3s refresh. The Mini App must now explain
        what is missing, keep its messages across refreshes, show a
        hint next to the buttons, and let the whole card (incl. its
        caption) be tapped."""
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "web", "altay.js"), encoding="utf-8") as f:
            js = f.read()
        # Client messages survive the 3s refresh instead of being wiped.
        self.assertIn("ATG.msgs", js)
        self.assertIn("atRenderLog()", js)
        # Tapping Build/Attack (or a territory) with nothing available
        # explains what is missing instead of doing nothing.
        self.assertIn("atWhy(mode)", js)
        self.assertIn("play a card like Village", js)
        self.assertIn("play a card like Warrior", js)
        # Hint next to the buttons about playing hand cards first.
        self.assertIn("play cards from your hand first", js)
        # Tap target is the whole card incl. its caption.
        self.assertIn('<div class="atcardwrap" \' + (attrs || \'\') + \'>', js)
        self.assertIn('<div class="atachwrap" data-ach="', js)
        with open(os.path.join(base, "web", "flip7.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn(".athint{width:100%;font-size:12px;color:#94a3b8}", html)

    def test_miniapp_notices_a_new_version(self):
        """FB-0026: 'su altay, gli insediamenti sulla mappa sono come
        prima e non sono stati modificati come richiesto' — the FB-0023
        settlement icons were live on the server, but the player still
        saw the old ones: the Mini App never reloads its own JS while
        open, and the ?v= cache-buster on altay.js had not been bumped
        for any of the day's fixes. The script tag must be bumped when
        the file changes, and the Mini App must compare the page's ?v=
        with the server version (/healthz) and tell the player to close
        and reopen when a new version is out. FB-0059: the same trap bit
        again — FB-0057 changed altay.js and replaced altay-markers.webp
        under the same name, but neither ?v= was bumped, so the Mini App
        kept the old JS and the old markers sheet (served max-age=86400)
        while the screenshot render, reading the files from disk, looked
        fixed. The markers sheet must carry a ?v= too, bumped whenever
        its bytes change."""
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "web", "flip7.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn('src="altay.js?v=6"', html)
        self.assertIn("url(altay-markers.webp?v=", html)
        with open(os.path.join(base, "web", "altay.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("atCheckVer", js)
        self.assertIn("fetch('/healthz')", js)
        self.assertIn("ATG.webVer", js)
        self.assertIn("New version — reopen the Mini App", js)

    def test_seafarers_setup_and_board_json(self):
        game, events = self.new_seafarers_game()
        self.assertEqual(len(game["board"]), 27)
        self.assertEqual(sorted(game["board"][str(r)]["marker"]["value"]
                                for r in altay.SEAFARERS_REGIONS), [2, 3])
        for player in game["players"]:
            self.assertEqual(player["ship_supply"], 3)
            self.assertEqual(player["crews"], 3)
            self.assertEqual(player["ships"], {"A": 0, "B": 0})
        self.assertTrue(altay.ship_placements(game, 0))
        self.assertTrue(altay.ship_placements(game, 1))
        self.assertIn("Seafarers", " ".join(events))
        board = altay.board_json(game, 42)
        json.dumps(board)
        self.assertTrue(board["seafarers"])
        self.assertEqual(len(board["regions"]), 27)
        self.assertEqual(len(board["market"]), 13)
        self.assertIn("lighthouse", [a["id"] for a in board["achievements"]])
        astronomy = next(a for a in board["achievements"] if a["id"] == "astronomy")
        self.assertEqual(astronomy["level"], 1)
        self.assertEqual(board["sea_anchors"]["A"], altay.SEA_ANCHORS["A"])

    def test_seafarers_islands_do_not_overlap(self):
        """FB-0057: 'now the cards work but the board is weird' — in a
        Seafarers game each island holds two territories, and the old
        positions stacked each pair on top of the other (23 over 25, 24
        next to 26), so the board showed a doubled blob on both islands.
        With the expansion on, 23/24 move to the far end of their island
        so both circles fit; the base game keeps its positions."""
        game, _ = self.new_seafarers_game()
        board = altay.board_json(game, 42)
        pos = {r["id"]: r["pos"] for r in board["regions"]}
        # Region circles are min(44px, 10.5%) of the board width
        # (FB-0060). Distances are in % of width, with the vertical
        # component scaled by the board aspect (1451/2048).
        aspect = 1451 / 2048

        def dist(a, b):
            dx = pos[a][0] - pos[b][0]
            dy = (pos[a][1] - pos[b][1]) * aspect
            return (dx * dx + dy * dy) ** 0.5

        self.assertGreaterEqual(dist(23, 25), 12)
        self.assertGreaterEqual(dist(24, 26), 12)
        self.assertNotEqual(pos[23], altay.REGION_POS[23])
        self.assertNotEqual(pos[24], altay.REGION_POS[24])
        base_game, _ = self.new_game()
        base = altay.board_json(base_game, 42)
        base_pos = {r["id"]: r["pos"] for r in base["regions"]}
        self.assertEqual(base_pos[23], altay.REGION_POS[23])
        self.assertEqual(base_pos[24], altay.REGION_POS[24])

    def test_region_circles_never_overlap_or_clip(self):
        """FB-0060: 'on altay, the map on the mini app still looks
        weird' — after the FB-0057 island fix, the map still showed
        territories merged into blobs and circles cut off by the board
        edge: 2 sat on 14 and 11 on 17 in every game, and 0/2/7 were
        clipped at the top, 11/16 at the bottom, 12/8 at the sides.
        Every pair of circles must clear each other (centre distance
        above the circle diameter plus its 2px border) and every circle
        must fit fully inside the board, in base and Seafarers games,
        at phone widths (360/390px) and on a wide board."""
        aspect = 1451 / 2048
        for make in (self.new_game, self.new_seafarers_game):
            game, _ = make()
            board = altay.board_json(game, 42)
            regions = board["regions"]
            for width in (360, 390, 700):
                height = width * aspect
                # the CSS circle is min(44px, 10.5%) of the board width
                diam = min(44.0, 0.105 * width)
                need = diam + 4  # +2px border on each side
                pts = {r["id"]: (r["pos"][0] / 100 * width,
                                  r["pos"][1] / 100 * height)
                       for r in regions}
                for a in pts:
                    for b in pts:
                        if b <= a:
                            continue
                        dist = ((pts[a][0] - pts[b][0]) ** 2 +
                                (pts[a][1] - pts[b][1]) ** 2) ** 0.5
                        self.assertGreaterEqual(
                            dist, need,
                            f"regions {a} and {b} overlap at {width}px")
                for rid, (cx, cy) in pts.items():
                    self.assertGreaterEqual(cx - diam / 2 - 2, 0,
                                           f"region {rid} clipped left")
                    self.assertLessEqual(cx + diam / 2 + 2, width,
                                        f"region {rid} clipped right")
                    self.assertGreaterEqual(cy - diam / 2 - 2, 0,
                                           f"region {rid} clipped top")
                    self.assertLessEqual(cy + diam / 2 + 2, height,
                                        f"region {rid} clipped bottom")

    def test_sea_badges_do_not_cover_region_circles(self):
        """FB-0057: the sea-zone badges sat on top of region circles (A
        over 6/13, B over 20) and next to the VP stars. Both badges now
        sit in the central lake, clear of every region circle, VP star
        and each other, in base and Seafarers games."""
        aspect = 1451 / 2048
        for make in (self.new_game, self.new_seafarers_game):
            game, _ = make()
            board = altay.board_json(game, 42)
            regions = {r["id"]: r["pos"] for r in board["regions"]}
            anchors = list(board["sea_anchors"].values())
            # badge half-size in % of board width: ~55px wide, ~17px tall
            hw, hh = 8.0, 2.2
            for ax, ay in anchors:
                ay_w = ay * aspect
                for rid, p in regions.items():
                    dx = abs(p[0] - ax)
                    dy = abs(p[1] * aspect - ay_w)
                    self.assertFalse(dx < hw + 5.7 and dy < hh + 5.7,
                                     f"sea badge covers region {rid}")
                    if altay.VICTORY_MARKERS.get(rid):
                        # the VP star sits up-right of its circle
                        vx, vy = p[0] + 2.3, p[1] * aspect - 5.8
                        self.assertFalse(abs(vx - ax) < hw + 3.9
                                         and abs(vy - ay_w) < hh + 2.2,
                                         f"sea badge covers the VP star of {rid}")
            ax0, ay0 = anchors[0]
            ax1, ay1 = anchors[1]
            self.assertFalse(abs(ax0 - ax1) < 2 * hw
                             and abs(ay0 - ay1) * aspect < 2 * hh,
                             "sea badges overlap each other")

    def test_marker_chips_show_one_shield_per_value(self):
        # FB-0057: the conquest marker chips showed two half-tokens
        # mashed together — the old sheet was sliced as 6 equal columns
        # (col * 100 / 6) although it is a strip of assorted tokens. The
        # rebuilt sheet is one red shield per value (3 cells of 120x80),
        # so the CSS is 300% and the JS column is (value-1) * 100 / 2,
        # and the number is printed on the shield, not overlaid as text.
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "web", "flip7.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn("background-image:url(altay-markers.webp?v=1);background-size:300% 100%;", html)
        with open(os.path.join(base, "web", "altay.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("(col * 100 / 2)", js)
        self.assertNotIn("col * 100 / 6", js)
        self.assertNotIn("region.marker.value + '</span>'", js)
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL not installed")
        with Image.open(os.path.join(base, "web", "altay-markers.webp")) as im:
            self.assertEqual(im.size, (360, 80))

    def test_seafarers_shipwright_and_sea_attack(self):
        game, events = self.new_seafarers_game()
        player = game["players"][0]
        player["hand"].append("shipwright")
        self.assertIsNone(altay.play_card(game, 0, len(player["hand"]) - 1, events,
                                          None, {"zone": "A"}))
        self.assertEqual(player["ships"]["A"], 1)
        self.assertEqual(player["ship_supply"], 2)
        option = next((o for o in altay.attack_options(game, 0)
                       if o["region"] in altay.SEAFARERS_REGIONS), None)
        self.assertIsNotNone(option)
        self.assertEqual(option["via"], ["A"])
        player["swords"] = 4
        reserve = player["reserve"]
        self.assertIsNone(altay.attack(game, 0, option["from"], option["region"], events))
        self.assertIsNone(game["board"][str(option["region"])]["marker"])
        self.assertIn(0, game["board"][str(option["region"])]["settlements"])
        self.assertEqual(player["reserve"], reserve - 1)
        self.assertEqual(player["ship_supply"], 3)
        self.assertEqual(player["ships"]["A"], 0)

    def test_seafarers_sailor_explorer_and_trade(self):
        game, events = self.new_seafarers_game()
        player = game["players"][0]
        player["ships"]["A"] = 1
        player["hand"].extend(["sailor", "explorer"])
        self.assertIsNone(altay.play_card(game, 0, len(player["hand"]) - 2, events,
                                          None, {"action": "crew", "zone": "A"}))
        self.assertEqual(player["ship_crews"]["A"], 1)
        self.assertEqual(player["crews"], 2)
        self.assertIsNone(altay.play_card(game, 0, len(player["hand"]) - 1, events))
        self.assertEqual(player["coins"], 3)
        player["resources"]["food"] = 3
        self.assertIsNone(altay.trade(game, 0, {"food": 3}, "wood", events))
        self.assertEqual(player["resources"]["wood"], 1)
        self.assertIsNotNone(altay.trade(game, 0, {"food": 3}, "wood", events))
        self.assertIsNone(altay.end_turn(game, 0, events))
        self.assertFalse(game["players"][0]["traded"])

    def test_seafarers_miniapp_assets_and_controls(self):
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "web", "flip7.html"), encoding="utf-8") as f:
            html = f.read()
        for asset in ("altay-seafarers-actions.webp", "altay-seafarers-achievements.webp"):
            self.assertIn(asset, html)
        with open(os.path.join(base, "game_registry.py"), encoding="utf-8") as f:
            registry = f.read()
        for asset in ("altay-seafarers-actions.webp", "altay-seafarers-achievements.webp",
                      "altay-seafarers-tokens.webp", "altay-seafarers-ships.webp"):
            self.assertIn(asset, registry)
        self.assertIn('id="aySea"', html)
        with open(os.path.join(base, "web", "altay.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("atSeaBadges", js)
        self.assertIn("atMove('seafarers'", js)
        self.assertIn("atMove('trade'", js)
        self.assertIn("index: shipwright", js)
        self.assertIn("action: 'resettle'", js)

    def test_lobby_has_how_to_play_buttons(self):
        # FB-0084: the Altay lobby has two "🎥 How to play" buttons — one
        # for the base game and one for the Seafarers expansion — both on
        # the Telegram board and in the Mini App lobby.
        import bot as BOT

        game = altay.new_game(7, 42, "Ada")
        self.assertEqual(game["phase"], "lobby")
        kb = BOT.altay_keyboard(game)
        flat = [b for row in kb for b in row]
        howto = [b for b in flat if b.get("text") == "🎥 How to play ALTAY"]
        self.assertEqual(len(howto), 1)
        self.assertEqual(howto[0].get("url"), BOT.AL_HOW_TO_PLAY_URL)
        self.assertIn("youtube.com/watch?v=siN2PgEhtGA", howto[0]["url"])
        sea = [b for b in flat
               if b.get("text") == "🎥 How to play ALTAY SEAFARERS EXPANSION"]
        self.assertEqual(len(sea), 1)
        self.assertEqual(sea[0].get("url"), BOT.AL_HOW_TO_PLAY_SEAFARERS_URL)
        self.assertIn("youtu.be/uc2jhm9Bx8s", sea[0]["url"])
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "web", "altay.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("AL_HOW_TO_PLAY_URL", js)
        self.assertIn("AL_HOW_TO_PLAY_SEAFARERS_URL", js)
        self.assertIn("youtube.com/watch?v=siN2PgEhtGA", js)
        self.assertIn("youtu.be/uc2jhm9Bx8s", js)
        self.assertIn("openLink", js)
        self.assertIn("ayHowTo", js)
        self.assertIn("ayHowToSea", js)
        with open(os.path.join(base, "web", "flip7.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="ayHowTo"', html)
        self.assertIn('id="ayHowToSea"', html)
        self.assertIn("🎥 How to play ALTAY", html)
        self.assertIn("🎥 How to play ALTAY SEAFARERS EXPANSION", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
