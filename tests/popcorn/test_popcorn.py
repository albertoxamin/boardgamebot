import random
import unittest

import popcorn as PC


def two_player_game(seed=4):
    g = PC.new_game(7, 1, "Alice")
    g["players"].append(PC.new_player(2, "Bob"))
    events = []
    err = PC.start_game(g, events, rng=random.Random(seed))
    assert err is None, err
    return g, events


def end_buying(g, events=None):
    ev = events if events is not None else []
    for _ in g["players"]:
        idx = PC.current_index(g)
        assert PC.act(g, idx, "done", {}, ev) is None
    return ev


class SetupTests(unittest.TestCase):
    def test_rejects_bad_player_counts(self):
        g = PC.new_game(7, 1, "Alice")
        self.assertEqual(PC.start_game(g, []), "Popcorn needs 2-4 players")
        for _ in range(4):
            g["players"].append(PC.new_player(2, "Bob"))
        self.assertEqual(PC.start_game(g, []), "Popcorn needs 2-4 players")

    def test_starting_cinemas(self):
        g, _ = two_player_game()
        self.assertEqual(g["phase"], "buy")
        self.assertEqual(g["round"], 1)
        self.assertEqual([p["money"] for p in g["players"]], [5, 6])
        self.assertEqual([p["audience"] for p in g["players"]], [3, 3])
        for p in g["players"]:
            self.assertEqual(len(p["bag"]), 10)
            self.assertEqual(p["bag"].count("white"), 5)
            self.assertEqual(len(p["exit"]), 4)
            self.assertEqual(len(p["theaters"]), 1)
            self.assertEqual(p["theaters"][0]["size"], 1)
            self.assertEqual(p["ads"], 3)
            self.assertEqual(len(p["awards"]), 1)
        self.assertEqual(len(g["market"]["features"]), 3)
        self.assertEqual(len(g["market"]["premiers"]), 3)
        self.assertTrue(all(len(g["market"]["tiles"][s]) == 3 for s in (1, 2, 3)))

    def test_start_is_idempotent(self):
        g, _ = two_player_game()
        self.assertEqual(PC.start_game(g, []), "game already started")


class BuyingTests(unittest.TestCase):
    def test_buy_movie_with_showing_bonus(self):
        g, ev = two_player_game()
        g["players"][0]["money"] = 99
        mid = g["market"]["features"][0]
        err = PC.act(g, 0, "movie", {"movie": mid, "slot": 0}, ev)
        self.assertIsNone(err)
        self.assertEqual(g["players"][0]["theaters"][0]["movie"]["id"], mid)
        self.assertTrue(g["players"][0]["bought_movie"])
        self.assertTrue(any("shows" in e for e in ev))
        self.assertEqual(PC.act(g, 0, "movie", {"movie": mid, "slot": 0}, []),
                         "you already bought a movie this turn")

    def test_buy_theater_requires_second_turn(self):
        g, _ = two_player_game()
        g["players"][0]["money"] = 99
        tile = g["market"]["tiles"][2][0]
        self.assertEqual(PC.act(g, 0, "theater", {"tile": tile["id"], "slot": 0}, []),
                         "you cannot buy a theater on your first turn")
        g["players"][0]["turns"] = 1
        before = g["players"][0]["audience"]
        self.assertIsNone(PC.act(g, 0, "theater", {"tile": tile["id"], "slot": 2}, []))
        self.assertEqual(g["players"][0]["theaters"][2]["size"], 2)
        self.assertEqual(g["players"][0]["audience"], min(7, before + 1))

    def test_advertising_token_effects(self):
        g, ev = two_player_game()
        g["players"][0]["turns"] = 1
        g["players"][0]["ads_board"] = [{"kind": "color", "color": "red"}]
        before = len(g["players"][0]["bag"])
        self.assertIsNone(PC.act(g, 0, "ad", {"index": 0}, ev))
        self.assertEqual(g["players"][0]["ads"], 4)
        self.assertEqual(g["players"][0]["ads_board"], [])
        self.assertGreaterEqual(len(g["players"][0]["bag"]), before)

    def test_wrong_actor_is_rejected(self):
        g, _ = two_player_game()
        self.assertEqual(PC.act(g, 1, "done", {}, []), "not your turn")


class ShowingTests(unittest.TestCase):
    def test_auto_seat_finishes_showing(self):
        g, ev = two_player_game()
        end_buying(g, ev)
        self.assertEqual(g["phase"], "show")
        self.assertEqual(g["pending"]["kind"], "place")
        opts = PC.pending_options(g, g["pending"]["by"])
        self.assertTrue(opts)
        while g["phase"] == "show":
            actor = g["pending"]["by"]
            self.assertIsNone(PC.act(g, actor, "auto", {}, ev))
        self.assertIsNone(g["pending"])
        self.assertEqual(g["phase"], "buy")
        self.assertEqual(g["round"], 2)
        self.assertTrue(any("showing is over" in e for e in ev))

    def test_manual_placement_uses_seat_order(self):
        g, ev = two_player_game()
        end_buying(g, ev)
        actor = g["pending"]["by"]
        color = g["pending"]["guests"][0]
        before = g["pending"]["guests"].count(color)
        self.assertIsNone(PC.act(g, actor, "place", {"color": color, "slot": 0}, ev))
        self.assertEqual(g["players"][actor]["theaters"][0]["seats"][0]["guest"], color)
        after = g["pending"]["guests"].count(color) if g["pending"] else 0
        self.assertEqual(after, before - 1)

    def test_board_json_hides_bag(self):
        g, _ = two_player_game()
        mine = PC.board_json(g, 1)
        theirs = PC.board_json(g, 2)
        self.assertEqual(mine["players"][0]["bag_count"], 10)
        self.assertEqual(len(mine["players"][0]["bag"]), 10)
        self.assertEqual(theirs["players"][0]["bag"], [])
        self.assertEqual(theirs["players"][0]["bag_count"], 10)
        self.assertEqual(len(mine["options"]), len(PC.action_options(g, 1)))

    def test_board_json_includes_chat_id(self):
        # FB-0166: the Mini App picks the game with pick.chat_id, so the
        # board JSON must carry it — without it the app fetched
        # /api/popcorn/game?chat_id=undefined, got no game and rendered
        # a blank board.
        g, _ = two_player_game()
        self.assertEqual(PC.board_json(g, 1)["chat_id"], g["chat_id"])


class ScoringTests(unittest.TestCase):
    def test_final_scoring_awards_money_trophy_and_winner(self):
        g, _ = two_player_game()
        g["phase"] = "show"
        g["round"] = 7
        g["final_round"] = 7
        g["players"][0].update(money=10, popcorn=2, archived=[])
        g["players"][1].update(money=0, popcorn=0, archived=["x", "y"])
        for p in g["players"]:
            p["theaters"] = [{"size": 1, "cost": 8, "seats": [], "movie": {}, "slider": 0, "used": []},
                             {"size": 2, "cost": 6, "seats": [], "movie": {}, "slider": 0, "used": []},
                             {"size": 3, "cost": 5, "seats": [], "movie": {}, "slider": 0, "used": []}]
        ev = []
        PC._finish_game(g, ev)
        self.assertEqual(g["phase"], "game_end")
        self.assertEqual(g["players"][0]["theater_cost"], 19)
        self.assertGreaterEqual(g["players"][0]["popcorn"], 2 + 2)
        self.assertIn(g["winner"], (0, 1))

    def test_award_score_helpers(self):
        g, _ = two_player_game()
        p = g["players"][0]
        p.update(money=12, audience=5, popcorn=3, archived=["a"])
        self.assertEqual(PC._award_score(g, {"kind": "money"}, p), 12)
        self.assertEqual(PC._award_score(g, {"kind": "audience"}, p), 5)
        self.assertEqual(PC._award_score(g, {"kind": "archives"}, p), -1)


class FlowTests(unittest.TestCase):
    def test_full_game_finishes(self):
        for seed in (0, 3, 11):
            g, _ = two_player_game(seed)
            for _ in range(800):
                if g["phase"] == "game_end":
                    break
                idx = PC.current_index(g)
                opts = PC.action_options(g, g["players"][idx]["user_id"])
                self.assertTrue(opts, (g["phase"], g["round"]))
                pick = opts[-1]
                err = PC.act(g, idx, pick["action"], pick["params"], [])
                self.assertIsNone(err, err)
            self.assertEqual(g["phase"], "game_end")
            self.assertIn(g["winner"], (0, 1))
            self.assertTrue(all(p["popcorn"] >= 0 for p in g["players"]))
            self.assertGreaterEqual(g["round"], 6)

    def test_code_round_trip(self):
        self.assertEqual(PC.parse_code("d"), ("done", {}))
        self.assertEqual(PC.parse_code("auto"), ("auto", {}))
        self.assertEqual(PC.parse_code("a2"), ("ad", {"index": 2}))
        action, params = PC.parse_code("m12:1")
        self.assertEqual((action, params["movie"], params["slot"]), ("movie", "12", "1"))
        action, params = PC.parse_code("pred:2")
        self.assertEqual((action, params), ("place", {"color": "red", "slot": "2"}))


class BgaAssetsTests(unittest.TestCase):
    # FB-0170: the 13 BGA sprite sheets (release 260810-1806) stored in
    # sources/popcorn/bga/ — movie cards, awards, guests, theater tiles
    # and boards, lobby sliders, advertising, tokens, background,
    # score pad and help sheet. Dimensions verified off the files.
    SHEETS = {
        "POP_Movies.jpg": (1644, 2466),
        "POP_Awards.jpg": (741, 1548),
        "POP_Guests.png": (1128, 200),
        "POP_Theaters.png": (672, 1344),
        "POP_CinemaBoards.png": (3776, 1296),
        "POP_Lobbies.png": (420, 506),
        "POP_AdvertisingBoard.png": (289, 745),
        "POP_AdvertisingTokensMoney.png": (360, 71),
        "POP_OtherResources.png": (600, 200),
        "POP_FeatureTiles.png": (388, 272),
        "POP_Background.jpg": (722, 1000),
        "POP_Scorepad.jpg": (1294, 505),
        "POP_Help.png": (1202, 1695),
    }

    def test_bga_sprite_sheets_present(self):
        import os

        from PIL import Image

        base = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))),
            "sources", "popcorn", "bga")
        for name, size in self.SHEETS.items():
            path = os.path.join(base, name)
            self.assertTrue(os.path.isfile(path), name)
            with Image.open(path) as im:
                self.assertEqual(im.size, size, name)


if __name__ == "__main__":
    unittest.main()
