import json
import os
import tempfile
import unittest
from unittest.mock import patch

import bot
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
