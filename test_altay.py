import json
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

    def test_turn_order_and_wrong_player_guard(self):
        game, events = self.new_game()
        self.assertIsNotNone(altay.play_card(game, 1, 0, events))
        self.assertIsNone(altay.end_turn(game, 0, events, random.Random(6)))
        self.assertIsNone(altay.play_card(game, 1, 0, events))


if __name__ == "__main__":
    unittest.main(verbosity=2)
