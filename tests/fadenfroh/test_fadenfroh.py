import os
import unittest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import fadenfroh as FD


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def half(color, symbols=()):
    return {"c": color, "s": list(symbols)}


def player(rows=None):
    p = FD.new_player(1, "Alice")
    p["rows"] = rows if rows is not None else [
        {"3": half("yellow"), "4": half("yellow")},
        {"3": half("white"), "4": half("white")},
        {"3": half("purple"), "4": half("purple")},
    ]
    return p


def two_player_game():
    g = FD.new_game(7, 1, "Alice")
    g["players"].append(FD.new_player(2, "Bob"))
    events = []
    assert FD.start_game(g, events, scoring="beginner") is None
    return g, events


def finish(g, take_offer=0, bonus="B"):
    events = []
    for _ in range(5000):
        if g["phase"] == "game_end":
            return events
        idx = FD.current_index(g)
        assert idx is not None, (g["phase"], g.get("pending"))
        pend = g.get("pending")
        if g["phase"] == "shopping":
            err = FD.pass_offer(g, idx, take_offer, events)
        elif pend["kind"] == "keep":
            err = FD.apply_choice(g, idx, 0, events)
        elif pend["kind"] == "place":
            options = FD.pending_options(g, idx)
            assert options
            err = FD.apply_choice(g, idx, options[0]["value"], events)
        elif pend["kind"] == "bonus":
            err = FD.apply_choice(g, idx, bonus, events)
        else:
            raise AssertionError((g["phase"], pend))
        assert err is None, err
    raise AssertionError("game did not finish")


class SetupTests(unittest.TestCase):
    def test_deck_matches_bga_sheet(self):
        self.assertEqual(len(FD.CARDS), 81)
        self.assertEqual(FD.CARDS[0]["h"][0]["c"], "white")
        self.assertEqual(FD.CARDS[0]["h"][1]["c"], "purple")
        self.assertEqual(len({c["id"] for c in FD.CARDS}), 81)

    def test_lobby_to_market(self):
        g, ev = two_player_game()
        self.assertEqual(g["phase"], "shopping")
        self.assertEqual(g["round"], 1)
        self.assertEqual(g["goals"], {"A": 13, "B": 2, "C": 8, "D": 9})
        self.assertEqual(len(g["market"]["offers"]), 2)
        self.assertEqual(g["market"]["threads"], 4)
        self.assertTrue(any("Round 1 market" in e for e in ev))

    def test_starting_rows_use_starting_card_art(self):
        # Starting sheet: 4 columns (starting numbers 1-4) x 3 rows
        # (white, yellow, purple); art = [column, sheet row].
        g, _ = two_player_game()
        for i, p in enumerate(g["players"]):
            self.assertEqual(p["start_no"], i + 1)
            for row, color in enumerate(("yellow", "white", "purple")):
                halves = list(p["rows"][row].values())
                self.assertEqual([h["c"] for h in halves], [color, color])
                sheet_row = {"white": 0, "yellow": 1, "purple": 2}[color]
                self.assertEqual([h["art"] for h in halves],
                                 [[i, sheet_row], [i, sheet_row]])

    def test_start_rejects_bad_player_counts(self):
        g = FD.new_game(7, 1, "Alice")
        self.assertEqual(FD.start_game(g, []), "Fadenfroh needs 2-4 players")
        for _ in range(4):
            g["players"].append(FD.new_player(2, "Bob"))
        self.assertEqual(FD.start_game(g, []), "Fadenfroh needs 2-4 players")


class MarketTests(unittest.TestCase):
    def test_take_material_passes_turn(self):
        g, _ = two_player_game()
        first = FD.current_index(g)
        self.assertIsNone(FD.take_material(g, first, "thread"))
        self.assertEqual(g["players"][first]["threads"], 2)
        self.assertEqual(g["market"]["threads"], 3)
        self.assertNotEqual(g["current"], first)

    def test_last_player_gets_leftovers_and_must_take_offer(self):
        g, _ = two_player_game()
        first = FD.current_index(g)
        FD.pass_offer(g, first, 0)
        last = FD.current_index(g)
        self.assertEqual(len(g["active"]), 1)
        self.assertEqual(FD.take_material(g, last, "thread"),
                         "you must take the last offer now")
        offers = len(g["market"]["offers"])
        FD.pass_offer(g, last, 0)
        self.assertEqual(g["phase"], "embroidery")
        self.assertEqual(len(g["pass_order"]), 2)
        self.assertEqual(offers, 1)

    def test_bad_market_actions_are_rejected(self):
        g, _ = two_player_game()
        actor = FD.current_index(g)
        self.assertEqual(FD.take_material(g, 1 - actor, "thread"), "not your turn in the market")
        self.assertEqual(FD.take_material(g, actor, "thimble"), None)


class EmbroideryTests(unittest.TestCase):
    def begin_place(self):
        g, _ = two_player_game()
        first = FD.current_index(g)
        FD.pass_offer(g, first, 0)
        idx = FD.current_index(g)
        FD.pass_offer(g, idx, 0)
        self.assertEqual(g["phase"], "embroidery")
        pend = g["pending"]
        self.assertEqual(pend["kind"], "place")
        return g, pend["by"]

    def test_cover_one_cover_two_and_needle_placements(self):
        g, idx = self.begin_place()
        cid = g["pending"]["cards"][0]
        opts = FD.pending_options(g, idx)
        values = {o["value"] for o in opts}
        self.assertIn(f"0:0:left:1:0", values)
        self.assertIn(f"0:0:left:2:0", values)
        self.assertIn(f"0:0:right:0:1", values)
        self.assertIsNone(FD.apply_choice(g, idx, f"0:0:left:1:0"))
        row = g["players"][idx]["rows"][0]
        self.assertIn("2", row)
        self.assertEqual(row["3"]["id"], cid)

    def test_needle_places_without_covering(self):
        g, idx = self.begin_place()
        cid = g["pending"]["cards"][0]
        self.assertIsNone(FD.apply_choice(g, idx, f"0:0:right:0:1"))
        row = g["players"][idx]["rows"][0]
        self.assertTrue(row["5"].get("needle"))
        self.assertEqual(row["6"]["id"], cid)
        self.assertEqual(row["7"]["id"], cid)
        self.assertEqual(g["players"][idx]["needles"], 0)

    def test_keep_draw_discards_other_cards(self):
        g, _ = two_player_game()
        g["players"][0]["threads"] = 3
        FD.pass_offer(g, 0, 0)
        FD.pass_offer(g, FD.current_index(g), 0)
        self.assertEqual(g["pending"]["kind"], "keep")
        drawn = list(g["pending"]["cards"])
        before = len(g["discard"])
        FD.apply_choice(g, g["pending"]["by"], 0)
        self.assertEqual(len(g["discard"]), before + len(drawn) - 1)
        by = g["pending"]["by"]
        self.assertIn(drawn[0], g["pending"]["cards"] +
                      g["players"][by]["supply"] +
                      [h["id"] for row in g["players"][by]["rows"]
                       for h in row.values()])


class ScoringTests(unittest.TestCase):
    def score(self, n, rows):
        return FD.score_details(player(rows), n)

    def test_all_sixteen_scoring_cards(self):
        flower_rows = [
            {"3": half("yellow", ["daisy"]), "4": half("yellow", ["thistle"]),
             "5": half("yellow", ["crocus"]), "6": half("yellow")},
            {"3": half("yellow", ["daisy"]), "4": half("yellow")},
            {"3": half("yellow"), "4": half("yellow")},
        ]
        animal_rows = [
            {"3": half("white", ["bunny"] * 5), "4": half("white", ["cat"])},
            {"3": half("white"), "4": half("white")},
            {"3": half("white"), "4": half("white")},
        ]
        expectations = [
            ([{"3": half("white", ["blueberry", "blueberry"]),
               "4": half("white", ["strawberry"])}, {}, {}], 3),
            ([{"3": half("white", ["blueberry"]), "4": half("white", ["strawberry"])},
              {}, {}], 4),
            ([{"3": half("white", ["blueberry"]),
               "4": half("white", ["strawberry", "strawberry"])}, {}, {}], 6),
            ([{"3": half("white", ["strawberry"]), "4": half("white", ["strawberry"]),
               "5": half("white", ["strawberry"])},
              {"3": half("white", ["blueberry"]), "4": half("white", ["blueberry"]),
               "5": half("white", ["blueberry"]), "6": half("white", ["blueberry"])}, {}], 15),
            ([{"3": half("white", ["bunny"])}, {}, {}], 3),
            ([{"3": half("white", ["bunny"]), "4": half("white", ["cat", "cat"]),
               "5": half("white", ["squirrel"] * 3)}, {}, {}], 18),
            (animal_rows, 19),
            ([{"3": half("white", ["bunny", "cat", "squirrel"])}, {}, {}], 9),
            (flower_rows, 9),
            ([{"3": half("white", ["daisy"]), "4": half("white")},
              {"3": half("white", ["daisy"]), "4": half("white")}, {}], 7),
            ([{"3": half("white", ["daisy"]), "4": half("white", ["daisy"]),
               "5": half("white", ["daisy"])}, {}, {}], 11),
            ([{"3": half("white", ["daisy"]), "4": half("white", ["daisy"])},
              {"3": half("white", ["daisy"]), "4": half("white", ["daisy"])},
              {"3": half("white", ["daisy"]), "4": half("white", ["daisy"])}], 24),
            ([{"3": half("white"), "4": half("white"), "5": half("white")}, {}, {}], 6),
            ([{"3": half("white"), "4": half("white"), "5": half("white"),
               "6": half("white")}, {}, {}], 5),
            ([{"3": half("white")}, {"5": half("white")}, {}], 2),
            ([{"3": half("purple"), "4": half("purple")},
              {"3": half("white")}, {}], 2),
        ]
        for card_no, (rows, expected) in enumerate(expectations, 1):
            with self.subTest(card=card_no):
                self.assertEqual(self.score(card_no, rows), expected)

    def test_feathers_count_for_every_scored_goal(self):
        p = player([{"3": half("white", ["feather"]), "4": half("white")}, {}, {}])
        self.assertEqual(FD._score_card(1, p), 0)
        self.assertEqual(FD._score_round, FD._score_round)


class FlowTests(unittest.TestCase):
    def test_full_game_finishes_and_awards_bonus(self):
        g, _ = two_player_game()
        finish(g)
        self.assertEqual(g["phase"], "game_end")
        self.assertEqual(g["round"], 5)
        self.assertIn(g["winner"], (0, 1))
        self.assertTrue(all(p["bonus"] == "B" for p in g["players"]))
        self.assertTrue(all(p["score"] > 0 for p in g["players"]))

    def test_lobby_has_how_to_play_button(self):
        # FB-0086: the Fadenfroh lobby has a "🎥 How to play" button that
        # opens the how-to-play video, both on the Telegram board and in the
        # Mini App lobby.
        import bot as BOT

        g = FD.new_game(-1004393094474, 1, "Alice")
        kb = BOT.fadenfroh_keyboard(g)
        flat = [b for row in kb for b in row]
        howto = [b for b in flat if b.get("text") == "🎥 How to play"]
        self.assertEqual(len(howto), 1)
        self.assertEqual(howto[0].get("url"), BOT.FF_HOW_TO_PLAY_URL)
        self.assertIn("youtube.com/watch?v=ezMd-IwlTyA", howto[0]["url"])
        js = open(os.path.join(ROOT, "assets", "fadenfroh", "scripts", "fadenfroh.js")).read()
        self.assertIn("FF_HOW_TO_PLAY_URL", js)
        self.assertIn("youtube.com/watch?v=ezMd-IwlTyA", js)
        self.assertIn("openLink", js)
        self.assertIn("ffHowTo", js)
        html = open(os.path.join(ROOT, "assets", "shared", "flip7.html")).read()
        self.assertIn('id="ffHowTo"', html)
        self.assertIn("🎥 How to play", html)

    def test_board_json_filters_opponent_hand(self):
        g, _ = two_player_game()
        g["players"][0]["supply"] = [4, 5]
        g["players"][1]["supply"] = [6, 7]
        mine = FD.board_json(g, 1)
        theirs = FD.board_json(g, 2)
        self.assertEqual(mine["players"][0]["supply"], [4, 5])
        self.assertEqual(mine["players"][1]["supply"], [])
        self.assertEqual(theirs["players"][0]["supply"], [])
        self.assertEqual(theirs["players"][1]["supply"], [6, 7])
        self.assertEqual(len(mine["cards"]), 81)


if __name__ == "__main__":
    unittest.main()
