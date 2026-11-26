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
        self.assertEqual(RN.start_game(g, []), "Rumble Nation needs exactly 2 players")


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
        js = open(os.path.dirname(__file__) + "/web/rumblenation.js").read()
        m = re.search(r"rnSprite\('token', RN_CASTLE_POS\[castle\], (\d+), (\d+),", js)
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)), 46)
        css = open(os.path.dirname(__file__) + "/web/flip7.html").read()
        m = re.search(r"\.rncastle\{[^}]*width:(\d+)px", css)
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)), 46)

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
