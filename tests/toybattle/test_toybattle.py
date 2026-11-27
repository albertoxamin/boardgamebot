import os
import random
import unittest

import toybattle as TB


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def game():
    g = TB.new_game(-7, 1, "Ada")
    g["players"].append(TB.new_player(2, "Bob"))
    ev = []
    assert TB.start_game(g, ev, random.Random(4)) is None
    return g


def clear_hands(g):
    for p in g["players"]:
        p["rack"] = []
        p["reserve"] = [1] * 8


class EngineTests(unittest.TestCase):
    def test_setup(self):
        g = game()
        self.assertEqual(len(g["players"][0]["reserve"]), 17)
        self.assertEqual(len(g["players"][1]["reserve"]), 16)
        self.assertEqual(len(g["players"][0]["rack"]), 3)
        self.assertEqual(len(g["players"][1]["rack"]), 4)
        self.assertEqual([p["hq"] for p in g["players"]], [1, 41])
        self.assertEqual([p["color"] for p in g["players"]], ["blue", "red"])
        self.assertEqual(len(TB.MEDAL_SPOTS), 14)
        self.assertEqual(sum(r[1] for r in TB.REGIONS.values()), 14)

    def test_initial_connection(self):
        g = game()
        g["players"][0]["rack"] = [7]
        self.assertEqual(TB.legal_placements(g, 0)[0], [11, 12])
        g["stacks"]["11"].append({"type": 7, "owner": 0})
        g["stacks"]["12"].append({"type": 7, "owner": 1})
        self.assertIn(13, TB.legal_placements(g, 0)[0])
        self.assertNotIn(14, TB.legal_placements(g, 0)[0])

    def test_hook_and_kwak(self):
        g = game()
        g["players"][0]["rack"] = [4, 8, 1]
        legal = TB.legal_placements(g, 0)
        self.assertIn(23, legal[0])
        self.assertNotIn(23, legal[2])
        for b in (11, 13, 18):
            g["stacks"][str(b)].append({"type": 7, "owner": 0})
        g["stacks"]["23"].append({"type": 7, "owner": 1})
        g["players"][0]["rack"] = [8, 1]
        legal = TB.legal_placements(g, 0)
        self.assertIn(23, legal[0])
        self.assertNotIn(23, legal[1])

    def test_enemy_hq_needs_connection_and_wins(self):
        g = game()
        g["players"][0]["rack"] = [4, 7]
        self.assertNotIn(41, TB.legal_placements(g, 0)[0])
        for b in (11, 13, 15, 17, 20, 22, 24):
            g["stacks"][str(b)].append({"type": 7, "owner": 0})
        self.assertIn(41, TB.legal_placements(g, 0)[1])
        ev = []
        TB.place(g, 0, 1, 41, ev)
        self.assertEqual((g["phase"], g["winner"], g["end_reason"]), ("game_end", 0, "hq"))

    def test_draw_limit(self):
        g = game()
        g["players"][0]["rack"] = [1] * 7
        ev = []
        TB.draw(g, 0, ev, random.Random(2))
        self.assertEqual(len(g["players"][0]["rack"]), 8)
        g["current"] = 0
        err = TB.draw(g, 0, ev)
        self.assertIn("full", err)

    def test_skully_and_star_draw(self):
        g = game()
        g["players"][0]["rack"] = [1]
        g["players"][0]["reserve"] = [6, 6, 6]
        ev = []
        TB.place(g, 0, 0, 11, ev)
        self.assertEqual(len(g["players"][0]["rack"]), 2)
        g["current"] = 0
        g["players"][0]["rack"] = [6]
        TB.place(g, 0, 0, 11, ev)
        self.assertEqual(len(g["players"][0]["rack"]), 1)

    def test_xb42_discards_random_rack_troop(self):
        g = game()
        clear_hands(g)
        g["players"][0]["rack"] = [5]
        g["players"][1]["rack"] = [3, 7]
        ev = []
        TB.place(g, 0, 0, 11, ev, random.Random(0))
        self.assertEqual(len(g["players"][1]["rack"]), 1)
        self.assertEqual(len(g["players"][1]["discard"]), 1)

    def test_jumbo_choice_discards_adjacent_enemy(self):
        g = game()
        clear_hands(g)
        g["stacks"]["13"].append({"type": 7, "owner": 1})
        g["stacks"]["11"].append({"type": 7, "owner": 0})
        g["players"][0]["rack"] = [3]
        ev = []
        TB.place(g, 0, 0, 11, ev)
        self.assertEqual(g["pending"]["kind"], "jumbo")
        opts = TB.pending_options(g, 0)
        self.assertTrue(any(o["value"] == "13" for o in opts))
        TB.choose(g, 0, "13", ev)
        self.assertEqual(g["stacks"]["13"], [])
        self.assertEqual(g["players"][1]["discard"], [7])
        self.assertIsNone(g["pending"])

    def test_captain_extra_placement(self):
        g = game()
        clear_hands(g)
        g["players"][0]["rack"] = [2, 7]
        ev = []
        TB.place(g, 0, 0, 11, ev)
        self.assertEqual(g["pending"]["kind"], "captain")
        opts = TB.pending_options(g, 0)
        self.assertGreaterEqual(len(opts), 2)
        TB.choose(g, 0, [o["value"] for o in opts if o["value"] != "skip"][0], ev)
        self.assertEqual(len(g["players"][0]["rack"]), 0)
        self.assertEqual(sum(len(s) for s in g["stacks"].values()), 2)
        self.assertIsNone(g["pending"])
        self.assertEqual(g["current"], 1)

    def test_special_base_recall(self):
        g = game()
        clear_hands(g)
        g["stacks"]["12"].append({"type": 6, "owner": 0})
        g["stacks"]["11"].append({"type": 7, "owner": 0})
        g["stacks"]["13"].append({"type": 7, "owner": 0})
        g["players"][0]["rack"] = [7]
        ev = []
        TB.place(g, 0, 0, 15, ev)
        self.assertEqual(g["pending"]["kind"], "recall")
        TB.choose(g, 0, "12", ev)
        self.assertEqual(g["stacks"]["12"], [])
        self.assertEqual(g["players"][0]["rack"], [6])
        self.assertEqual(g["current"], 1)

    def test_medals_are_permanent_and_win(self):
        g = game()
        clear_hands(g)
        for b in (13, 15, 17):
            g["stacks"][str(b)].append({"type": 7, "owner": 0})
        g["players"][0]["medals"] = 6
        ev = []
        TB.check_medals(g, ev)
        self.assertEqual(g["players"][0]["medals"], 7)
        self.assertEqual(g["claimed"]["2"], 0)
        g["stacks"]["13"] = []
        TB.check_medals(g, ev)
        self.assertEqual(g["players"][0]["medals"], 7)
        self.assertEqual(g["phase"], "game_end")

    def test_lobby_has_how_to_play_button(self):
        # FB-0082: the Toy Battle lobby has a "🎥 How to play" button that
        # opens the how-to-play video, both on the Telegram board and in the
        # Mini App lobby.
        import bot as BOT

        g = TB.new_game(-1004393094474, 1, "Alice")
        kb = BOT.toybattle_keyboard(g)
        flat = [b for row in kb for b in row]
        howto = [b for b in flat if b.get("text") == "🎥 How to play"]
        self.assertEqual(len(howto), 1)
        self.assertEqual(howto[0].get("url"), BOT.TB_HOW_TO_PLAY_URL)
        self.assertIn("youtube.com/watch?v=O2HjOQUFAio", howto[0]["url"])
        js = open(os.path.join(ROOT, "assets", "toybattle", "scripts", "toybattle.js")).read()
        self.assertIn("TB_HOW_TO_PLAY_URL", js)
        self.assertIn("youtube.com/watch?v=O2HjOQUFAio", js)
        self.assertIn("openLink", js)
        self.assertIn("tbHowTo", js)
        html = open(os.path.join(ROOT, "assets", "shared", "flip7.html")).read()
        self.assertIn('id="tbHowTo"', html)
        self.assertIn("🎥 How to play", html)

    def test_stuck_player_loses(self):
        g = game()
        g["players"][1]["rack"] = []
        g["players"][1]["reserve"] = []
        ev = []
        TB.draw(g, 0, ev)
        self.assertEqual(g["phase"], "game_end")
        self.assertEqual(g["winner"], 0)
        self.assertEqual(g["end_reason"], "stuck")

    def test_board_coordinates_match_board_art(self):
        # FB-0090 follow-up / msg 2411: the old BASES/MEDAL_SPOTS values were
        # measured on a landscape frame, so troops rendered up to a full tile
        # off the printed spaces. Positions are now (top %, left %) of the
        # portrait board art (assets/toybattle/images/toybattle-board.webp, 600x1000), measured
        # off the art and verified with an overlay render.
        seen = set()
        for b, (top, left, adj, special) in TB.BASES.items():
            self.assertTrue(0 <= top <= 100 and 0 <= left <= 100, b)
            self.assertNotIn((round(top, 1), round(left, 1)), seen, b)
            seen.add((round(top, 1), round(left, 1)))
        self.assertLess(TB.BASES[41][0], 15)   # red HQ at the top
        self.assertGreater(TB.BASES[1][0], 85)  # blue HQ at the bottom
        self.assertAlmostEqual(TB.BASES[1][1], 50.2, delta=1)
        self.assertAlmostEqual(TB.BASES[41][1], 50.2, delta=1)
        self.assertEqual({b for b, v in TB.BASES.items() if v[3]},
                         {15, 16, 20, 21})
        self.assertEqual(len(TB.MEDAL_SPOTS), 14)
        per_region = {}
        for m, (top, left, region) in TB.MEDAL_SPOTS.items():
            self.assertTrue(0 <= top <= 100 and 0 <= left <= 100, m)
            per_region[region] = per_region.get(region, 0) + 1
            for b, (bt, bl, _a, _s) in TB.BASES.items():
                dist = ((top - bt) ** 2 + (left - bl) ** 2) ** 0.5
                self.assertGreater(dist, 3, f"medal {m} on base {b}")
        self.assertEqual(per_region, {1: 3, 2: 1, 3: 1, 4: 2, 5: 2, 6: 1, 7: 1, 8: 3})
        # FB-0167: 28px medal tokens still clear every base (token radius
        # 14px + base half-height 29px) and never overlap each other
        # (closest spots are 29px apart) — in real pixels, not mixed %.
        spots = list(TB.MEDAL_SPOTS.items())
        for m, (top, left, _r) in spots:
            for b, (bt, bl, _a, _s) in TB.BASES.items():
                dist = (((top - bt) / 100 * 1000) ** 2 +
                        ((left - bl) / 100 * 600) ** 2) ** 0.5
                self.assertGreaterEqual(dist, 14 + 29, f"medal {m} vs base {b}")
        for i in range(len(spots)):
            for j in range(i + 1, len(spots)):
                (m1, (t1, l1, _)), (m2, (t2, l2, _)) = spots[i], spots[j]
                dist = (((t1 - t2) / 100 * 1000) ** 2 +
                        ((l1 - l2) / 100 * 600) ** 2) ** 0.5
                self.assertGreaterEqual(dist, 28, f"medals {m1}/{m2} overlap")

    def test_troop_abilities_cover_all_troops(self):
        # FB-0091: ability descriptions come from the Toy Battle rules
        # (bot.py TOYBATTLE_RULES), not invented.
        self.assertEqual(set(TB.TROOP_ABILITIES), set(range(1, 9)))
        for t, text in TB.TROOP_ABILITIES.items():
            self.assertTrue(text, t)
        self.assertIn("Draw 2", TB.TROOP_ABILITIES[1])
        self.assertIn("extra", TB.TROOP_ABILITIES[2])
        self.assertIn("adjacent", TB.TROOP_ABILITIES[3])
        self.assertIn("connection", TB.TROOP_ABILITIES[4])
        self.assertIn("random", TB.TROOP_ABILITIES[5])
        self.assertIn("Draw 1", TB.TROOP_ABILITIES[6])
        self.assertIn("No special", TB.TROOP_ABILITIES[7])
        self.assertIn("Joker", TB.TROOP_ABILITIES[8])

    def test_miniapp_tap_to_place_abilities_medals(self):
        # FB-0090: tap a legal base on the board to place the selected troop.
        # FB-0091: ability text under each toy + hover zoom on hand tokens.
        # FB-0092 / msg 2412: medals on the map from toybattle-medals.webp —
        # the sprite's star frame is for any claimed medal (the old code
        # showed the empty-slot frame for red's medals, so they were
        # invisible) with an owner-coloured ring.
        js = open(os.path.join(ROOT, "assets", "toybattle", "scripts", "toybattle.js")).read()
        self.assertIn("querySelectorAll('[data-base]')", js)
        self.assertIn("tbMove('place'", js)
        self.assertIn("tbplaceable", js)
        self.assertIn("TB_ABILITIES", js)
        self.assertIn("tbAbility(type)", js)
        self.assertIn("tbtoyname", js)
        self.assertIn("tbtoyability", js)
        self.assertIn("background-position:0 0", js)
        self.assertIn("tbclaimed", js)
        self.assertIn("troop_abilities", js)
        html = open(os.path.join(ROOT, "assets", "shared", "flip7.html")).read()
        self.assertIn(".tbtoyability", html)
        self.assertIn("scale(1.9)", html)
        self.assertIn(".tbmedal.tbclaimed", html)
        # FB-0167: the 24px slots at 55% opacity were dark discs on green
        # grass — at phone width Annalisa could not see them at all.
        # 28px, full opacity, white ring on unclaimed slots; the script
        # version is bumped so the live app fetches the new CSS.
        self.assertIn(".tbmedal{position:absolute;width:28px;height:28px;", html)
        self.assertIn(".tbmedal.tbunclaimed{box-shadow:0 0 0 2px #f8fafc", html)
        self.assertNotIn(".tbmedal.tbunclaimed{opacity", html)
        self.assertIn("toybattle.js?v=2", html)


    def test_miniapp_turn_banner_npc_log_rack_lock(self):
        # FB-0095: a prominent turn banner + a badge on the current
        # player's row — the old header ("Turn 2 · Annalisa 0/7 vs NPC 0/7
        # · your move") and the thin .tbcurrent border were easy to miss.
        # FB-0096 (b): the NPC's moves surface above the board (last 3 log
        # lines), not only in the small log at the bottom. FB-0096 (c): the
        # viewer's rack is only tappable on their own turn — never while
        # the NPC acts, including during the NPC's pending choice.
        js = open(os.path.join(ROOT, "assets", "toybattle", "scripts", "toybattle.js")).read()
        self.assertIn("tbBanner", js)
        self.assertIn("tbbanner", js)
        self.assertIn("Tocca a te", js)
        self.assertIn("Tocca a NPC", js)
        self.assertIn("tbturnbadge", js)
        self.assertIn("TOCCA A TE", js)
        self.assertIn("TURNO NPC", js)
        self.assertIn("tbRecent", js)
        self.assertIn("Ultime mosse", js)
        self.assertIn("tbwaitnote", js)
        self.assertIn("Aspetta il tuo turno", js)
        self.assertIn("tbIsMyTurn(g)", js)
        self.assertIn("me && myTurn && !g.pending", js)
        self.assertIn("if (TBG.selected === null || g.pending || !myTurn) return;", js)
        self.assertIn("if (!myTurn) TBG.selected = null;", js)
        self.assertIn("NPC\\'s turn", js)
        # The 🎁 Draw button stays available on the NPC's turn: the NPC
        # has no AI, the viewer draws for it.
        self.assertIn("the NPC has no AI", js)

    def test_board_json_can_act_true_on_npc_turn(self):
        # FB-0096 (c): bot.py reports can_act True while the NPC acts
        # (anyone may play for it), so the Mini App must gate the rack on
        # the actor, not on can_act — otherwise the viewer can "select"
        # their own toys on the NPC's turn and the app would try to place
        # the NPC's troop at that rack index.
        import bot as BOT

        g = TB.new_game(-7, 100, "Annalisa")
        assert BOT.add_npc("toybattle", g) is None
        ev = []
        assert TB.start_game(g, ev, random.Random(4)) is None
        g["current"] = 1
        b = BOT.toybattle_board_json(g, 100)
        self.assertTrue(b["can_act"])
        self.assertEqual(b["actor"], 1)
        self.assertTrue(b["players"][1]["npc"])
        self.assertEqual(b["players"][1]["rack"], g["players"][1]["rack"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
