import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch

import bot
import fellowship as FTR
import game_registry as GR
import web_assets
from game_modules.leaves import LEAVES_MODULE


class RegistryTests(unittest.TestCase):
    def test_all_specs_have_required_metadata(self):
        self.assertEqual(len(GR.GAME_KEYS), len(set(GR.GAME_KEYS)))
        for spec in GR.GAME_SPECS:
            self.assertTrue(spec.key)
            self.assertTrue(spec.command.startswith("/"))
            self.assertTrue(spec.join_command.startswith("/"))
            self.assertTrue(spec.web_module)
            self.assertLessEqual(spec.min_players, spec.max_players)

    def test_generated_menus_include_every_game(self):
        help_lines = "\n".join(GR.HELP_LINES)
        catalog = {row[0]: row for row in GR.CATALOG_ROWS}
        for key in GR.GAME_KEYS:
            spec = GR.GAMES_BY_KEY[key]
            self.assertIn(spec.command, help_lines)
            self.assertIn(key, catalog)
            self.assertEqual(GR.keyboard_label(key), spec.web_label)
            self.assertTrue(GR.supports_web_routing(key) or key == "games")

    def test_generated_routes_include_every_web_module(self):
        for spec in GR.GAME_SPECS:
            route = f"/{spec.web_module}.js"
            self.assertIn(route, GR.WEB_JS_ROUTES)
        self.assertEqual(bot.HEALTH_PATHS, ("/healthz", "/health"))

    def test_static_asset_references_exist(self):
        web_dir = web_assets.WEB_DIR
        for asset in sorted(web_assets.referenced_assets()):
            self.assertTrue(os.path.isfile(os.path.join(web_dir, asset)), asset)
            self.assertEqual(web_assets.resolve("/" + asset), os.path.join(web_dir, asset))

    def test_fellowship_art_map_covers_every_character(self):
        with open(os.path.join(web_assets.WEB_DIR, "fellowship.js"), encoding="utf-8") as handle:
            text = handle.read()
        for key in FTR.CHARACTERS:
            self.assertRegex(text, rf"\b{re.escape(key)}:\s*\{{")
        for letter in FTR.LETTERS.values():
            self.assertRegex(text, rf"\b{letter}:\s*\{{name:")

    def test_state_json_accept_sets(self):
        state = {"leaves": {"-1": {"passed": {1, 2}, "nested": {"x": {3}}}}}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(bot, "STATE_FILE", os.path.join(tmp, "state.json")):
                bot.save_state(state)
                with open(bot.STATE_FILE) as handle:
                    saved = json.load(handle)
        self.assertEqual(saved["leaves"]["-1"]["passed"], [1, 2])

    def test_leaves_module_contract(self):
        self.assertTrue(LEAVES_MODULE.validate())
        game = LEAVES_MODULE.new_game(1, 1, "A")
        game["players"].append(LEAVES_MODULE.new_player(2, "B"))
        game["players"].append(LEAVES_MODULE.new_player(3, "C"))
        self.assertEqual(len(game["players"]), 3)
        board = LEAVES_MODULE.board_json(game, 1)
        self.assertTrue(board["is_player"])
        self.assertEqual(board["passed_ids"], [])
        json.dumps(board)

    def test_leaves_module_applies_pass(self):
        game = LEAVES_MODULE.new_game(1, 1, "A")
        for user_id in (2, 3):
            game["players"].append(LEAVES_MODULE.new_player(user_id, str(user_id)))
        game["phase"] = "playing"
        game["row"] = [{"value": 5, "count": 1}]
        game["current_index"] = 0
        events = []
        self.assertIsNone(
            LEAVES_MODULE.apply_action(game, 0, "pass", {"take_index": 0}, events)
        )
        self.assertEqual(game["passed"], [1])
        json.dumps(game)

    def test_player_mention_uses_player_name(self):
        game = {"players": [{"user_id": 42, "name": "A<b>"}]}
        self.assertEqual(
            bot.player_mention(game, 42),
            '<a href="tg://user?id=42">A&lt;b&gt;</a>',
        )

    def test_leaves_render_pings_current_player(self):
        game = LEAVES_MODULE.new_game(1, 42, "A&B")
        for user_id in (43, 44):
            game["players"].append(LEAVES_MODULE.new_player(user_id, str(user_id)))
        game["phase"] = "playing"
        game["row"] = [{"value": 5, "count": 1}]
        game["current_index"] = 0
        for player in game["players"]:
            player["hand"] = [5, 6]
        with patch.object(bot, "send_board", return_value={"ok": True, "result": {"message_id": 1}}) as send:
            bot.leaves_render(game)
        text = send.call_args.args[2]
        self.assertIn('<a href="tg://user?id=42">A&amp;B</a>', text)

    def test_fellowship_render_pings_current_player(self):
        game = FTR.new_game(1, 42, "A&B")
        game["players"].append(FTR.new_player(43, "B"))
        game["phase"] = "choosing"
        game["selection_order"] = [0]
        game["selection_pos"] = 0
        with patch.object(bot, "send_board", return_value={"ok": True, "result": {"message_id": 1}}) as send:
            bot.fotr_render(game)
        text = send.call_args.args[2]
        self.assertIn('<a href="tg://user?id=42">A&amp;B</a>', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
