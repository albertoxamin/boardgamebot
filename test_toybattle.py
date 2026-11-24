import random
import unittest

import toybattle as TB


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

    def test_stuck_player_loses(self):
        g = game()
        g["players"][1]["rack"] = []
        g["players"][1]["reserve"] = []
        ev = []
        TB.draw(g, 0, ev)
        self.assertEqual(g["phase"], "game_end")
        self.assertEqual(g["winner"], 0)
        self.assertEqual(g["end_reason"], "stuck")


if __name__ == "__main__":
    unittest.main(verbosity=2)
