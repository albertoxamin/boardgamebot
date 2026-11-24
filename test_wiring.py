import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch

import bot
import blackflag as BF
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

    def test_guide_payload_covers_every_game(self):
        for key in GR.GAME_KEYS:
            payload = bot.guide_payload(key)
            self.assertIsNotNone(payload, key)
            self.assertEqual(payload["key"], key)
            self.assertEqual(payload["name"], GR.GAMES_BY_KEY[key].name)
            self.assertTrue(payload["guide"].strip(), key)
        self.assertIsNone(bot.guide_payload("missing"))

    def test_web_guide_controls_present(self):
        with open(os.path.join(web_assets.WEB_DIR, "flip7.html"), encoding="utf-8") as handle:
            html = handle.read()
        self.assertIn('id="guideBtn"', html)
        self.assertIn('id="guideOverlay"', html)
        with open(os.path.join(web_assets.WEB_DIR, "flip7.js"), encoding="utf-8") as handle:
            js = handle.read()
        self.assertIn("/api/guide?key=", js)

    def test_open_lobbies_filters_chat_and_phase(self):
        state = {key: {} for key in GR.GAME_KEYS}
        state["leaves"]["7"] = {"phase": "lobby", "players": [{}, {}]}
        state["fellowship"]["7"] = {"phase": "playing", "players": [{}]}
        state["regicide"]["8"] = {"phase": "lobby", "players": [{}]}
        rows = bot.open_lobbies(state, 7)
        self.assertEqual([(r["key"], r["players"]) for r in rows], [("leaves", 2)])
        self.assertEqual(rows[0]["join"], "/leaves_join")

    def test_games_rich_message_uses_scorecard_table_style(self):
        state = {key: {} for key in GR.GAME_KEYS}
        state["leaves"]["7"] = {"phase": "lobby", "players": [{}, {}]}
        rich = bot.games_rich_message(state, 7)
        tables = [b for b in rich["blocks"] if b["type"] == "table"]
        self.assertEqual(len(tables), 2)
        self.assertTrue(all(t["is_bordered"] and t["is_striped"] and t["is_compact"]
                            for t in tables))
        cells = tables[0]["cells"]
        self.assertEqual([c["text"] for c in cells[0]],
                         ["Game", "Start", "In this chat"])
        row = next(r for r in cells if r[0]["text"] == "🍃 13 Leaves")
        self.assertEqual([c["text"] for c in row],
                         ["🍃 13 Leaves", "/leaves", "lobby (2 in) - /leaves_join"])
        lobby_rows = [[c["text"] for c in r] for r in tables[1]["cells"]]
        self.assertIn(["🍃 13 Leaves", "2", "/leaves_join"], lobby_rows)

    def test_games_spectate_keyboard_only_in_progress(self):
        state = {key: {} for key in GR.GAME_KEYS}
        state["leaves"]["7"] = {"phase": "lobby", "players": [{}]}
        state["fellowship"]["7"] = {"phase": "playing", "players": [{}]}
        state["regicide"]["8"] = {"phase": "playing", "players": [{}]}
        with patch.object(bot, "WEB_URL", "https://example.test/app"):
            kb = bot.games_spectate_keyboard(state, 7, "private")
        self.assertEqual(len(kb), 1)
        btn = kb[0][0]
        self.assertEqual(btn["text"], "👁 Spectate 💍 Fellowship of the Ring")
        self.assertIn("app=fellowship", btn["web_app"]["url"])
        self.assertIn("chat_id=7", btn["web_app"]["url"])

    def test_games_command_sends_rich_with_text_fallback(self):
        state = {key: {} for key in GR.GAME_KEYS}
        state["leaves"]["7"] = {"phase": "lobby", "players": [{}, {}]}
        state["fellowship"]["7"] = {"phase": "playing", "players": [{}]}
        msg = {"chat": {"id": 7, "type": "private"},
               "from": {"id": 42, "first_name": "A"}, "text": "/games"}
        with patch.object(bot, "WEB_URL", "https://example.test/app"), \
                patch.object(bot, "send_rich", return_value={"ok": True}) as rich, \
                patch.object(bot, "send") as send:
            bot.handle_command(state, msg)
        rich.assert_called_once()
        send.assert_not_called()
        self.assertEqual(rich.call_args.args[2][0][0]["text"],
                         "👁 Spectate 💍 Fellowship of the Ring")
        with patch.object(bot, "WEB_URL", "https://example.test/app"), \
                patch.object(bot, "send_rich", return_value={"ok": False}), \
                patch.object(bot, "send") as send:
            bot.handle_command(state, msg)
        text = send.call_args.args[1]
        self.assertIn("Open lobbies in this chat", text)
        self.assertIn("🍃 13 Leaves — 2 in · /leaves_join", text)

    def test_unknown_command_stays_silent(self):
        # FB-0004: unrecognised /commands (e.g. meant for another bot in a
        # shared group) must not make the bot reply and spam the chat.
        for with_game in (False, True):
            state = {key: {} for key in GR.GAME_KEYS}
            if with_game:
                state["games"]["7"] = {"phase": "lobby", "players": []}
            msg = {"chat": {"id": 7, "type": "group"},
                   "from": {"id": 42, "first_name": "A"}, "text": "/roll"}
            with patch.object(bot, "send") as send, \
                    patch.object(bot, "send_rich") as rich:
                bot.handle_command(state, msg)
            send.assert_not_called()
            rich.assert_not_called()

    def test_known_flip7_command_still_hints_when_no_game(self):
        state = {key: {} for key in GR.GAME_KEYS}
        msg = {"chat": {"id": 7, "type": "private"},
               "from": {"id": 42, "first_name": "A"}, "text": "/flip7_join"}
        with patch.object(bot, "send") as send:
            bot.handle_command(state, msg)
        send.assert_called_once()
        self.assertIn("No Flip 7 game here yet", send.call_args.args[1])

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

    def test_azul_npc_can_be_controlled_by_any_player(self):
        game = bot.AZ.new_game(7, 42, "Ada")
        self.assertIsNone(bot.add_npc("azul", game))
        self.assertTrue(game["players"][1]["npc"])
        events = []
        self.assertIsNone(bot.AZ.start_game(game, events))
        game["current"] = 1
        self.assertEqual(bot.azul_actor_idx(game, 42), 1)
        board = bot.azul_board_json(game, 42)
        self.assertTrue(board["can_act"])
        self.assertTrue(board["players"][1]["npc"])
        self.assertTrue(board["options"])
        game["players"][1]["npc"] = False
        self.assertEqual(bot.azul_actor_idx(game, 42), 1)
        self.assertTrue(bot.azul_board_json(game, 42)["can_act"])
        state = {"azul": {"7": game}}
        opt = bot.AZ.take_options(game)[0]
        with patch.object(bot, "send_board", return_value={"ok": False}):
            _, err = bot.azul_api_move(state, 7, 42, {
                "action": "take", "source": opt["source"],
                "index": opt["index"], "color": opt["color"],
            })
            self.assertIsNone(err)
            self.assertEqual(game["pending"]["by"], 1)
            _, err = bot.azul_api_move(state, 7, 42, {"action": "place", "row": -1})
            self.assertIsNone(err)

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
    def test_toybattle_npc_can_be_controlled_and_racks_are_private(self):
        game = bot.TB.new_game(7, 42, "Ada")
        self.assertIsNone(bot.add_npc("toybattle", game))
        self.assertTrue(game["players"][1]["npc"])
        events = []
        self.assertIsNone(bot.TB.start_game(game, events))
        game["current"] = 1
        self.assertEqual(bot.toybattle_actor_idx(game, 42), 1)
        board = bot.toybattle_board_json(game, 42)
        self.assertTrue(board["can_act"])
        self.assertTrue(board["players"][1]["rack"])
        state = {"toybattle": {"7": game}}
        with patch.object(bot, "send_board", return_value={"ok": False}):
            _, err = bot.toybattle_api_move(state, 7, 42, {"action": "draw"})
            self.assertIsNone(err)
        game["players"][1]["npc"] = False
        game["players"][1]["user_id"] = 43
        board = bot.toybattle_board_json(game, 42)
        self.assertTrue(board["can_act"])
        self.assertFalse(board["players"][1]["rack"])
        self.assertEqual(bot.toybattle_actor_idx(game, 999), None)
    def test_altay_npc_can_be_controlled_and_hands_are_private(self):
        game = bot.AL.new_game(7, 42, "Ada")
        self.assertIsNone(bot.add_npc("altay", game))
        self.assertTrue(game["players"][1]["npc"])
        events = []
        self.assertIsNone(bot.AL.start_game(game, events))
        board = bot.altay_board_json(game, 42)
        self.assertTrue(board["can_act"])
        self.assertEqual(len(board["players"][1]["hand"]), 5)
        self.assertEqual(len(board["market"]), 10)
        game["players"][1]["npc"] = False
        game["players"][1]["user_id"] = 43
        game["current"] = 1
        board = bot.altay_board_json(game, 42)
        self.assertEqual(board["players"][1]["hand"], [])
        self.assertFalse(board["can_act"])
        state = {"altay": {"7": game}}
        with patch.object(bot, "send_board", return_value={"ok": False}):
            _, err = bot.altay_api_move(state, 7, 43, {"action": "end"})
            self.assertIsNone(err)
        self.assertEqual(game["current"], 0)

    def test_altay_api_can_add_npc_from_lobby(self):
        game = bot.AL.new_game(7, 42, "Ada")
        state = {"altay": {"7": game}}
        with patch.object(bot, "send_board", return_value={"ok": False}):
            events, err = bot.altay_api_move(state, 7, 42, {"action": "npc"})
        self.assertIsNone(err)
        self.assertTrue(game["players"][1]["npc"])
        self.assertTrue(events)


class BlackFlagTests(unittest.TestCase):
    def test_deck_and_role_metadata_are_consistent(self):
        self.assertEqual(set(BF.CARD_DECK), set(BF.CARD_INFO))
        self.assertTrue(all(copies > 0 for copies in BF.CARD_DECK.values()))
        self.assertEqual(set(BF.CAPTAIN_SHIP), set(BF.CAPTAINS))
        self.assertTrue(all(ship in BF.SHIPS for ship in BF.CAPTAIN_SHIP.values()))
        for count in range(BF.MIN_PLAYERS, BF.MAX_PLAYERS + 1):
            roles = BF.ROLE_DECKS[count]
            self.assertEqual(len(roles), count)
            self.assertIn(905, roles)

    def test_setup_deals_cards_and_hides_info(self):
        game = BF.new_game(7, 42, "Ada")
        for uid, name in ((43, "Ben"), (44, "Cy"), (45, "Dee")):
            self.assertIsNone(BF.join_game(game, uid, name))
        events = []
        self.assertIsNone(BF.start_game(game, events))
        total = sum(len(p["hand"]) for p in game["players"]) + len(game["deck"]) + len(game["discard"])
        self.assertEqual(total, sum(BF.CARD_DECK.values()))
        self.assertEqual(len(game["ship_row"]), 3)
        self.assertEqual(game["hourglass"], 7)
        self.assertEqual(len({p["role"] for p in game["players"]}), 4)
        self.assertTrue(events)
        outsider = BF.board_json(game, 999)
        self.assertTrue(all(p["hand"] == [] for p in outsider["players"]))
        own = BF.board_json(game, 42)
        self.assertEqual(len(own["players"][0]["hand"]), len(game["players"][0]["hand"]))

    def test_shot_can_be_passed_and_damages_target(self):
        game = BF.new_game(7, 42, "Ada")
        for uid, name in ((43, "Ben"), (44, "Cy"), (45, "Dee")):
            BF.join_game(game, uid, name)
        BF.start_game(game, [])
        current = game["current"]
        game["players"][current]["ship"] = 400
        targets = BF._target_options(game, current, attack=True)
        self.assertTrue(targets)
        target = targets[0]
        game["players"][current]["hand"] = [929]
        before = game["players"][target]["barrels"]
        events = []
        self.assertIsNone(BF.play_card(game, current, 0, target, events))
        self.assertEqual(game["pending"]["target"], target)
        self.assertIsNone(BF.pass_defense(game, target, events))
        self.assertIsNone(game["pending"])
        self.assertEqual(game["players"][target]["barrels"], before - 2)
        self.assertTrue(events)

    def test_npc_can_be_controlled_and_hands_are_private(self):
        game = bot.BF.new_game(7, 42, "Ada")
        BF.join_game(game, 43, "Ben")
        BF.join_game(game, 44, "Cy")
        self.assertIsNone(bot.add_npc("blackflag", game))
        events = []
        self.assertIsNone(bot.BF.start_game(game, events))
        npc_index = len(game["players"]) - 1
        game["current"] = npc_index
        self.assertEqual(bot.blackflag_actor_idx(game, 42), npc_index)
        board = bot.blackflag_board_json(game, 42)
        self.assertTrue(board["can_act"])
        self.assertTrue(board["players"][npc_index]["hand"])
        game["players"][npc_index]["npc"] = False
        game["players"][npc_index]["user_id"] = 99
        board = bot.blackflag_board_json(game, 42)
        self.assertEqual(board["players"][npc_index]["hand"], [])
        self.assertFalse(board["can_act"])
        state = {"blackflag": {"7": game}}
        with patch.object(bot, "send_board", return_value={"ok": False}):
            _, err = bot.blackflag_api_move(state, 7, 99, {"action": "end"})
        self.assertIsNone(err)

    def test_api_can_add_npc_from_lobby(self):
        game = bot.BF.new_game(7, 42, "Ada")
        state = {"blackflag": {"7": game}}
        with patch.object(bot, "send_board", return_value={"ok": False}):
            events, err = bot.blackflag_api_move(state, 7, 42, {"action": "npc"})
        self.assertIsNone(err)
        self.assertTrue(game["players"][1]["npc"])
        self.assertTrue(events)


if __name__ == "__main__":
    unittest.main(verbosity=2)
