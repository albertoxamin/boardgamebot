import os
import re
import unittest

import rumblenation as RN


class FixedRng:
    def __init__(self, dice=None):
        self.dice = list(dice or [])

    def shuffle(self, seq):
        return seq

    def randint(self, a, b):
        return self.dice.pop(0) if self.dice else 3


def game(dice=None):
    g = RN.new_game(7, 1, "Alice", rng=FixedRng(dice))
    g["players"].append(RN.new_player(2, "Bob"))
    ev = []
    assert RN.start_game(g, ev) is None
    return g, ev


def game_n(n, dice=None):
    """A started game with n players (2-4)."""
    g = RN.new_game(7, 1, "Alice", rng=FixedRng(dice))
    for i, name in enumerate(["Bob", "Carol", "Dave"][:n - 1]):
        g["players"].append(RN.new_player(i + 2, name))
    ev = []
    assert RN.start_game(g, ev) is None
    return g, ev


def setup_castles(g, overrides=None):
    mapping = {v: v - 2 for v in RN.CASTLE_VALUES}
    mapping.update(overrides or {})
    g["castle_at"] = {str(v): r for v, r in mapping.items()}


def rotated_castles(g):
    g["castle_at"] = {str(v): (v - 1) % 11 for v in RN.CASTLE_VALUES}


class SetupTests(unittest.TestCase):
    def test_new_game_starts_in_lobby(self):
        g = RN.new_game(7, 1, "Alice")
        self.assertEqual(g["phase"], "lobby")
        self.assertEqual(g["players"][0]["stock"], RN.SOLDIERS)

    def test_start_deals_eleven_castles_and_three_tactics(self):
        g, ev = game()
        self.assertEqual(g["phase"], "action")
        self.assertEqual(sorted(int(v) for v in g["castle_at"]), list(range(2, 13)))
        self.assertEqual(len(set(g["castle_at"].values())), 11)
        self.assertEqual(len(g["tactics"]), 3)
        self.assertEqual(len(set(g["tactics"])), 3)
        self.assertTrue(ev)

    def test_start_rejects_wrong_player_count(self):
        g = RN.new_game(7, 1, "Alice")
        self.assertEqual(RN.start_game(g, []), "Rumble Nation needs 2-4 players")
        for _ in range(4):
            g["players"].append(RN.new_player(len(g["players"]) + 1, "Extra"))
        self.assertEqual(RN.start_game(g, []), "Rumble Nation needs 2-4 players")

    def test_three_and_four_player_starts_deal_more_tactics(self):
        # FB-0066: the display holds players + 1 tactic cards.
        g3, _ = game_n(3)
        self.assertEqual(len(g3["tactics"]), 4)
        self.assertEqual(len(set(g3["tactics"])), 4)
        g4, _ = game_n(4)
        self.assertEqual(len(g4["tactics"]), 5)
        self.assertEqual(len(set(g4["tactics"])), 5)

    def test_finishing_order_awards_swords_for_three_and_four_players(self):
        # FB-0066: first out takes the highest sword chip (3, then 2, then 1).
        g, ev = game_n(3, [1, 1, 1])
        for idx in range(3):
            g["players"][idx]["stock"] = 1
            RN.roll(g, idx)
            g["dice"] = [1, 1, 1]
            RN.deploy(g, idx, 1, 2, ev)
        self.assertEqual([p["sword"] for p in g["players"]], [3, 2, 1])
        self.assertEqual(g["phase"], "game_end")

        g, ev = game_n(4, [1, 1, 1])
        for idx in range(4):
            g["players"][idx]["stock"] = 1
            RN.roll(g, idx)
            g["dice"] = [1, 1, 1]
            RN.deploy(g, idx, 1, 2, ev)
        self.assertEqual([p["sword"] for p in g["players"]], [4, 3, 2, 1])

    def test_lobby_allows_up_to_four_players(self):
        # FB-0066: the registry and the bot's lobby cap must allow 2-4.
        import game_registry as GR
        spec = next(s for s in GR.GAME_SPECS if s.key == "rumblenation")
        self.assertEqual((spec.min_players, spec.max_players), (2, 4))
        self.assertEqual(GR.NPC_MAX["rumblenation"], 4)
        import bot as BOT
        self.assertEqual(BOT.RN_LEN, 4)


class DeploymentTests(unittest.TestCase):
    def test_roll_reroll_and_dice_splits(self):
        g, _ = game([3, 4, 5, 6, 6, 6])
        setup_castles(g, {9: 0, 8: 1, 7: 2})
        self.assertIsNone(RN.roll(g, 0))
        self.assertEqual(g["phase"], "select")
        self.assertEqual(g["dice"], [3, 4, 5])
        self.assertEqual(RN.deploy_options(g, 0), [(3, 9), (4, 8), (5, 7)])
        self.assertIsNone(RN.reroll(g, 0))
        self.assertEqual(g["dice"], [6, 6, 6])
        self.assertEqual(g["rerolls"], 0)
        self.assertIsNotNone(RN.reroll(g, 0))

    def test_deploy_places_ceiling_half_and_passes_turn(self):
        g, ev = game([3, 4, 5])
        setup_castles(g, {9: 0, 8: 1, 7: 2})
        RN.roll(g, 0)
        self.assertIsNone(RN.deploy(g, 0, 5, 7, ev))
        self.assertEqual(g["troops"]["2"]["0"], 3)
        self.assertEqual(g["players"][0]["stock"], RN.SOLDIERS - 3)
        self.assertEqual(g["current"], 1)
        self.assertEqual(g["phase"], "action")
        self.assertTrue(any("sends 3 to castle 7" in e for e in ev))

    def test_illegal_split_is_rejected(self):
        g, _ = game([3, 4, 5])
        RN.roll(g, 0)
        self.assertIsNotNone(RN.deploy(g, 0, 6, 2, []))
        self.assertIsNotNone(RN.deploy(g, 1, 5, 7, []))

    def test_finishing_deployment_awards_swords_and_resolves_war(self):
        g, ev = game([1, 1, 1])
        g["players"][0]["stock"] = 1
        RN.roll(g, 0)
        RN.deploy(g, 0, 1, 2, ev)
        self.assertEqual(g["players"][0]["sword"], 2)
        self.assertEqual(g["finished"], [0])
        self.assertEqual(g["current"], 1)
        g["players"][1]["stock"] = 1
        RN.roll(g, 1)
        g["dice"] = [1, 1, 1]
        RN.deploy(g, 1, 1, 2, ev)
        self.assertEqual(g["players"][1]["sword"], 1)
        self.assertEqual(g["phase"], "game_end")
        self.assertIn(g["winner"], (0, 1))

    def test_last_player_deploys_fewer_than_die_says(self):
        g, ev = game([6, 6, 6])
        setup_castles(g, {12: 0, 2: 1})
        g["players"][0]["stock"] = 2
        RN.roll(g, 0)
        RN.deploy(g, 0, 6, 12, ev)
        self.assertEqual(g["troops"]["0"]["0"], 2)
        self.assertEqual(g["players"][0]["stock"], 0)
        self.assertTrue(any("takes the 2-sword chip" in e for e in ev))


class TacticTests(unittest.TestCase):
    def test_scout_moves_one_soldier_to_adjacent_area(self):
        g, ev = game()
        g["tactics"] = [1]
        g["troops"]["1"]["0"] = 2
        opts = RN.tactic_options(g, 0, 1)
        self.assertTrue(opts)
        self.assertIsNone(RN.play_tactic(g, 0, opts[0]["value"], ev))
        self.assertEqual(g["troops"]["1"]["0"], 1)
        self.assertEqual(g["used"][0], 1)
        self.assertEqual(g["current"], 1)

    def test_tactics_close_when_anyone_is_out_of_soldiers(self):
        g, _ = game()
        g["tactics"] = [7]
        g["troops"]["0"]["0"] = 1
        g["finished"] = [1]
        self.assertEqual(RN.tactic_options(g, 0, 7), [])

    def test_rebel_replaces_enemy_soldier(self):
        g, ev = game()
        g["tactics"] = [8]
        g["troops"]["3"]["0"] = 1
        g["troops"]["3"]["1"] = 1
        opt = RN.tactic_options(g, 0, 8)[0]
        self.assertIsNone(RN.play_tactic(g, 0, opt["value"], ev))
        self.assertEqual((g["troops"]["3"]["0"], g["troops"]["3"]["1"]), (2, 0))
        self.assertEqual(g["players"][0]["stock"], RN.SOLDIERS - 1)
        self.assertEqual(g["players"][1]["stock"], RN.SOLDIERS + 1)

    def test_rebel_targets_the_chosen_foe_in_three_player_game(self):
        # FB-0066: in 3-4 player games an enemy-targeting card must let the
        # player pick which opponent it hits.
        g, ev = game_n(3)
        g["tactics"] = [8]
        g["troops"]["3"]["0"] = 1
        g["troops"]["3"]["1"] = 1
        g["troops"]["3"]["2"] = 1
        opts = RN.tactic_options(g, 0, 8)
        foes = sorted(int(o["value"].split("|")[3]) for o in opts)
        self.assertEqual(foes, [1, 2])
        self.assertTrue(all("vs " in o["label"] for o in opts))
        vs_carol = next(o for o in opts if o["value"].endswith("|2"))
        self.assertIsNone(RN.play_tactic(g, 0, vs_carol["value"], ev))
        self.assertEqual((g["troops"]["3"]["0"], g["troops"]["3"]["1"],
                          g["troops"]["3"]["2"]), (2, 1, 0))
        self.assertEqual(g["players"][1]["stock"], RN.SOLDIERS)
        self.assertEqual(g["players"][2]["stock"], RN.SOLDIERS + 1)

    def test_retreat_returns_three_soldiers(self):
        g, ev = game()
        g["tactics"] = [12]
        g["troops"]["4"]["0"] = 4
        g["players"][0]["stock"] = 5
        opt = RN.tactic_options(g, 0, 12)[0]
        self.assertIsNone(RN.play_tactic(g, 0, opt["value"], ev))
        self.assertEqual(g["troops"]["4"]["0"], 1)
        self.assertEqual(g["players"][0]["stock"], 8)

    def test_every_tactic_has_working_target_generation(self):
        for cid in RN.TACTICS:
            g, _ = game()
            g["tactics"] = [cid]
            g["troops"] = {str(r): {"0": 4, "1": 4} for r in range(len(RN.REGIONS))}
            g["troops"]["0"] = {"0": 0, "1": 0}
            opts = RN.tactic_options(g, 0, cid)
            self.assertTrue(opts, cid)
            ev = []
            self.assertIsNone(RN.play_tactic(g, 0, opts[0]["value"], ev), cid)


class WarTests(unittest.TestCase):
    def test_war_awards_castle_and_tie_goes_to_higher_sword(self):
        g, ev = game()
        g["players"][0]["sword"] = 1
        g["players"][1]["sword"] = 2
        g["troops"]["0"]["0"] = 2
        g["troops"]["0"]["1"] = 2
        RN.resolve_war(g, ev)
        self.assertEqual(g["phase"], "game_end")
        self.assertEqual(g["players"][1]["castles"], [2])
        self.assertTrue(any("wins" in e for e in ev))

    def test_reinforcements_go_to_adjacent_unresolved_areas_with_own_troops(self):
        g, ev = game()
        rotated_castles(g)
        g["troops"]["1"]["0"] = 3
        g["troops"]["2"]["0"] = 1
        RN.resolve_war(g, ev)
        self.assertEqual(g["reinforce"]["2"]["0"], 1)
        self.assertIn(2, g["players"][0]["castles"])

    def test_uncontested_castle_gives_no_reinforcement_without_presence(self):
        g, ev = game()
        rotated_castles(g)
        g["troops"]["1"]["0"] = 3
        RN.resolve_war(g, ev)
        self.assertEqual(g["reinforce"]["2"]["0"], 0)

    def test_three_player_war_gives_runner_up_small_token(self):
        # FB-0066: in 3-4 player games the runner-up takes a small castle
        # token worth half the value, rounded down.
        g, ev = game_n(3)
        g["troops"]["0"]["0"] = 3
        g["troops"]["0"]["1"] = 2
        g["troops"]["0"]["2"] = 1
        RN.resolve_war(g, ev)
        self.assertEqual(g["players"][0]["castles"], [2])
        self.assertEqual(g["players"][1]["small_castles"], [2])
        self.assertEqual(g["players"][0]["score"], 2)
        self.assertEqual(g["players"][1]["score"], 1)
        self.assertEqual(g["players"][2]["score"], 0)
        self.assertEqual(g["winner"], 0)

    def test_three_player_war_places_two_reinforcements(self):
        # FB-0066: 3-4 player games place 2 reinforcements per adjacent area.
        g, ev = game_n(3)
        g["troops"]["0"]["0"] = 3
        g["troops"]["1"]["0"] = 1  # region 1 is adjacent to region 0
        RN.resolve_war(g, ev)
        self.assertEqual(g["reinforce"]["1"]["0"], 2)

    def test_empty_areas_are_skipped(self):
        g, ev = game()
        RN.resolve_war(g, ev)
        self.assertEqual(g["players"][0]["score"], 0)
        self.assertTrue(any("nobody deployed" in e for e in ev))

    def test_final_tie_broken_by_sword(self):
        g, ev = game()
        g["players"][0]["score"] = 3
        g["players"][1]["score"] = 3
        g["players"][1]["sword"] = 2
        RN.resolve_war(g, ev)
        self.assertEqual(g["winner"], 1)
        self.assertTrue(any("wins" in e for e in ev))


class ViewTests(unittest.TestCase):
    def test_board_lines_and_json(self):
        g, _ = game([2, 2, 2])
        RN.roll(g, 0)
        self.assertTrue(any("Rumble Nation" in line for line in RN.board_lines(g)))
        own = RN.board_json(g, 1)
        other = RN.board_json(g, 2)
        self.assertTrue(own["can_act"])
        self.assertFalse(other["can_act"])
        self.assertEqual(len(own["regions"]), 11)
        self.assertEqual(len(own["dice"]), 3)

    def test_lobby_board_lines(self):
        g = RN.new_game(7, 1, "Alice")
        self.assertTrue(any("lobby" in line for line in RN.board_lines(g)))

    def test_region_positions_are_on_the_printed_hexes(self):
        # FB-0061: the old coordinates were a guessed diagonal - the tokens
        # floated in the sea and bunched up in the middle instead of sitting
        # on the white hexagons printed on the board art.  Positions must
        # stay inside the map area and well apart from each other.
        for r in RN.REGIONS:
            self.assertGreater(r["x"], 5, r["name"])
            self.assertLess(r["x"], 95, r["name"])
            self.assertGreater(r["y"], 5, r["y"])
            self.assertLess(r["y"], 95, r["name"])
        for i, a in enumerate(RN.REGIONS):
            for b in RN.REGIONS[i + 1:]:
                dist = ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
                self.assertGreaterEqual(dist, 10, (a["name"], b["name"]))

    def test_card_description_under_card_and_zoom(self):
        # FB-0062: each tactic card shows its name + description underneath,
        # and hovering (or tapping, which selects it) zooms the card.
        js = open(os.path.dirname(__file__) + "/web/rumblenation.js").read()
        self.assertIn("rncardcap", js)
        self.assertIn("c.name", js)
        self.assertIn("c.text", js)
        self.assertIn("rnselected", js)
        css = open(os.path.dirname(__file__) + "/web/flip7.html").read()
        m = re.search(r"\.rncardwrap\{([^}]+)\}", css)
        self.assertIsNotNone(m)
        m = re.search(r"\.rncardcap\{([^}]+)\}", css)
        self.assertIsNotNone(m)
        zoom = re.search(
            r"\.rncard:hover[^{]*\{[^}]*transform:scale\(([\d.]+)\)", css)
        self.assertIsNotNone(zoom)
        self.assertGreaterEqual(float(zoom.group(1)), 1.5)
        self.assertIn(".rncard.rnselected", css)

    def test_number_tokens_are_small(self):
        # FB-0063: the castle number tokens were too big in the Mini App.
        # FB-0061 follow-up: they are now sized in JS from the board
        # width (rnCastleDiam, 8% capped at 44px) instead of fixed 44px,
        # so they shrink at phone width; the CSS 44px is only a fallback.
        js = open(os.path.dirname(__file__) + "/web/rumblenation.js").read()
        self.assertIn("rnCastleDiam", js)
        self.assertIn("Math.min(44", js)
        self.assertIn("* 0.08", js)
        self.assertIn("rnSprite('token', RN_CASTLE_POS[castle], d, h, 687, 593)", js)
        css = open(os.path.dirname(__file__) + "/web/flip7.html").read()
        m = re.search(r"\.rncastle\{[^}]*width:(\d+)px", css)
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)), 46)

    def test_castle_tokens_never_overlap_at_phone_width(self):
        # FB-0061 follow-up: fixed 44px tokens overlapped at phone width
        # — Odawara-Inabayama are 32.8px apart at 360px, Kyo-Yoshida
        # 39.5px, both under 44px. With rnCastleDiam (8% of the board,
        # capped at 44px) every pair must clear each other and every
        # token must fit fully inside the board, at 360/390/700px.
        aspect = 1480 / 2000  # rumblenation-board.webp
        for width in (360, 390, 700):
            board_w = min(width, 680)  # .rnboard is min(100%, 680px)
            height = board_w * aspect
            diam = min(44, int(board_w * 0.08))
            need = diam + 2
            pts = {r["name"]: (r["x"] / 100 * board_w,
                                r["y"] / 100 * height)
                   for r in RN.REGIONS}
            for a in pts:
                for b in pts:
                    if b <= a:
                        continue
                    dist = ((pts[a][0] - pts[b][0]) ** 2 +
                            (pts[a][1] - pts[b][1]) ** 2) ** 0.5
                    self.assertGreaterEqual(
                        dist, need, f"{a} and {b} overlap at {width}px")
            for name, (cx, cy) in pts.items():
                self.assertGreaterEqual(cx - diam / 2, 0, f"{name} clipped left")
                self.assertLessEqual(cx + diam / 2, board_w, f"{name} clipped right")
                self.assertGreaterEqual(cy - diam / 2, 0, f"{name} clipped top")
                self.assertLessEqual(cy + diam / 2, height, f"{name} clipped bottom")

    def test_dice_legend_at_bottom(self):
        # FB-0064: a legend under the board explains the dice -> soldiers
        # symbols from the printed chart (1-2 = 1, 3-4 = 2, 5-6 = 3).
        js = open(os.path.dirname(__file__) + "/web/rumblenation.js").read()
        self.assertIn("rnlegend", js)
        self.assertIn("1–2 → 1 soldier", js)
        self.assertIn("3–4 → 2 soldiers", js)
        self.assertIn("5–6 → 3 soldiers", js)
        css = open(os.path.dirname(__file__) + "/web/flip7.html").read()
        self.assertIn(".rnlegend{", css)

    def test_lobby_has_how_to_play_button(self):
        # FB-0065: the Rumble Nation lobby has a "How to play" button that
        # opens the how-to-play video, both on the Telegram board and in
        # the Mini App lobby.
        import bot as BOT
        import json

        g = RN.new_game(-1004393094474, 1, "Alice")
        g["chat_type"] = "supergroup"
        kb = BOT.rumblenation_keyboard(g)
        flat = [b for row in kb for b in row]
        howto = [b for b in flat if b.get("text") == "🎥 How to play"]
        self.assertEqual(len(howto), 1)
        self.assertEqual(howto[0].get("url"), BOT.RN_HOW_TO_PLAY_URL)
        self.assertIn("youtu.be/l89gewMT6uQ", howto[0]["url"])
        self.assertNotIn("rn:howto", json.dumps(kb))
        js = open(os.path.dirname(__file__) + "/web/rumblenation.js").read()
        self.assertIn("RN_HOW_TO_PLAY_URL", js)
        self.assertIn("youtu.be/l89gewMT6uQ", js)
        self.assertIn("howto.classList.remove('hidden')", js)
        self.assertIn("openLink", js)
        html = open(os.path.dirname(__file__) + "/web/flip7.html").read()
        self.assertIn('id="rnHowTo"', html)
        self.assertIn("🎥 How to play", html)

    def test_mini_app_supports_four_players_and_four_colours(self):
        # FB-0066: the Mini App lobby allows 4 players, and each seat has
        # its own meeple colour (red, blue, orange, white).
        js = open(os.path.dirname(__file__) + "/web/rumblenation.js").read()
        m = re.search(r"RN_SOLDIER_POS = \[([0-9, ]+)\]", js)
        self.assertIsNotNone(m)
        pos = [int(v) for v in m.group(1).split(",")]
        self.assertEqual(len(pos), 8)  # 4 meeples x 2 coords
        self.assertEqual(len({tuple(pos[i:i + 2]) for i in range(0, 8, 2)}), 4)
        m = re.search(r"RN_COLORS = \[([^\]]+)\]", js)
        self.assertIsNotNone(m)
        self.assertEqual([c.strip().strip("'\"") for c in m.group(1).split(",")],
                         ["red", "blue", "orange", "white"])
        self.assertIn("'/4 · '", js)
        self.assertNotIn("p < 2", js)
        self.assertNotIn("'/2 · '", js)
        css = open(os.path.dirname(__file__) + "/web/flip7.html").read()
        for colour in ("red", "blue", "orange", "white"):
            self.assertIn(f".rn{colour}{{", css)
        g, _ = game_n(4)
        board = RN.board_json(g, 1)
        self.assertEqual(len(board["players"]), 4)
        self.assertEqual([len(r["troops"]) for r in board["regions"].values()],
                         [4] * 11)
        self.assertTrue(any("/4" in line for line in
                            RN.board_lines(RN.new_game(7, 1, "Alice"))))

    def test_reserve_row_shows_soldiers_left(self):
        # FB-0067: each player must see how many soldiers they still have
        # in reserve, not just the small "N left" buried in the header
        # line. The Mini App shows a reserve row with the soldier meeple,
        # the player's name and the remaining count; the board JSON that
        # feeds it carries each player's stock.
        g, _ = game([2, 2, 2])
        RN.roll(g, 0)
        board = RN.board_json(g, 1)
        self.assertEqual([p["stock"] for p in board["players"]],
                         [RN.SOLDIERS, RN.SOLDIERS])
        self.assertTrue(any("left" in line for line in RN.board_lines(g)))
        js = open(os.path.dirname(__file__) + "/web/rumblenation.js").read()
        self.assertIn("rnReserve", js)
        self.assertIn("in reserve", js)
        self.assertIn("p.stock", js)
        self.assertIn("rnReserve(g)", js)
        css = open(os.path.dirname(__file__) + "/web/flip7.html").read()
        self.assertIn(".rnreserves{", css)
        self.assertIn(".rnreserve{", css)

    def test_current_player_is_unmissable_in_mini_app(self):
        # FB-0094: Annalisa could not tell whose turn it was from the
        # Mini App — the header is one dense line and the player rows
        # carry no turn marker. The Mini App now shows a big banner with
        # the current player's name in their colour above the header,
        # and the current player's reserve row gets an amber border +
        # glow plus a turn badge. The board JSON already carries the
        # actor index, so no bot change is needed.
        g, _ = game([2, 2, 2])
        RN.roll(g, 0)
        board = RN.board_json(g, 1)
        self.assertEqual(board["phase"], "select")
        self.assertEqual(board["actor"], 0)
        js = open(os.path.dirname(__file__) + "/web/rumblenation.js").read()
        self.assertIn("rnTurnBanner", js)
        self.assertIn("g.actor", js)
        self.assertIn(".rnturnbanner{", js)
        self.assertIn(".rnreserve.rnturn{", js)
        self.assertIn("rnturnbadge", js)
        self.assertIn("your turn", js)
        self.assertIn("rnTurnBanner(g)", js)
        self.assertIn("rnTurnStyle()", js)

    def test_no_header_line_below_turn_banner_during_play(self):
        # FB-0098: Annalisa asked to remove the dense header line below
        # the turn banner during play (the banner already says whose
        # turn it is). The play-phase branch of the turn element must
        # render nothing after the banner; lobby and game-end headers
        # stay, since there is no banner there.
        js = open(os.path.dirname(__file__) + "/web/rumblenation.js").read()
        self.assertNotIn("'⚔️ Turn ' + g.turn", js)
        self.assertIn("Rumble Nation lobby", js)
        self.assertIn("wins! · ' + names", js)

    def test_shared_map_is_labelled(self):
        # FB-0101: Annalisa read the one shared map as a map per player and
        # wondered why the current player's soldiers also appeared on the
        # other player's map. She confirmed a shared map is fine — the
        # Mini App now labels it above the board, and the Telegram board
        # lines say so too. Deploying still only adds the acting player's
        # soldiers to that castle.
        g, ev = game([3, 4, 5])
        setup_castles(g, {9: 0, 8: 1, 7: 2})
        RN.roll(g, 0)
        self.assertIsNone(RN.deploy(g, 0, 5, 7, ev))
        # Deploying adds soldiers only for the acting player — the other
        # player's count in that castle stays 0.
        self.assertEqual(g["troops"]["2"]["0"], 3)
        self.assertEqual(g["troops"]["2"]["1"], 0)
        lines = RN.board_lines(g)
        self.assertTrue(any("One shared map" in l for l in lines))
        js = open(os.path.dirname(__file__) + "/web/rumblenation.js").read()
        self.assertIn("rnsharednote", js)
        self.assertIn("One shared map", js)

    def test_castle_token_sprites_match_their_numbers(self):
        # FB-0061: castle 7 and 11 were swapped in web/rumblenation.js, so
        # the token face did not match the castle value in the rules.
        js = (os.path.dirname(__file__) + "/web/rumblenation.js")
        with open(js) as f:
            src = f.read()
        m = re.search(r"RN_CASTLE_POS = \{([^}]+)\}", src)
        self.assertIsNotNone(m)
        found = {int(k): [int(v) for v in vals.split(",")]
                 for k, vals in re.findall(r"(\d+): \[([0-9, ]+)\]", m.group(1))}
        self.assertEqual(set(found), set(range(2, 13)))
        self.assertEqual(len({tuple(v) for v in found.values()}), 11)
        self.assertEqual(found[7], [218, 489])
        self.assertEqual(found[11], [2, 489])


if __name__ == "__main__":
    unittest.main()
