import leaves as rules

from . import GameModule

NPC_ID = -1
MIN_PLAYERS = rules.MIN_PLAYERS
MAX_PLAYERS = rules.MAX_PLAYERS

RULES_TEXT = """🍃 <b>13 Leaves rules</b> (short): shed your hand by playing sets onto the row ends.
• 3–6 players (dealt 12/11/10/9). First lead plays any set of same value.
• After that, play onto left/right end: play >= count of that end stack, and value is <= lowest (left) or >= highest (right), or stack equal to that end value.
• If you can’t/won’t play: Pass (and you’re out for this round in many variants) — see buttons. First to empty hand wins the game.
Use the Mini App for easier play, or commands like <code>/leaves_play 5 2</code> (play two 5s)."""


class LeavesGame(GameModule):
    key = "leaves"

    def normalize(self, game):
        passed = game.get("passed")
        if isinstance(passed, set):
            game["passed"] = list(passed)
        elif passed is None:
            game["passed"] = []
        return game

    def new_game(self, chat_id, creator_id, creator_name):
        return self.normalize(rules.new_game(chat_id, creator_id, creator_name))

    def new_player(self, user_id, name):
        return rules.new_player(user_id, name)

    def npc_player(self):
        return {**self.new_player(NPC_ID, "🤖 NPC"), "npc": True}

    def start_game(self, game, events):
        self.normalize(game)
        return rules.start_game(game, events)

    def play(self, game, actor_index, value, count, events):
        self.normalize(game)
        return rules.play(game, actor_index, value, count, events)

    def pass_turn(self, game, actor_index, events, take_index=None):
        self.normalize(game)
        return rules.pass_turn(game, actor_index, events, take_index=take_index)

    def apply_action(self, game, actor_index, action, payload, events):
        self.normalize(game)
        if action == "play":
            try:
                value = int(payload.get("value"))
                count = int(payload.get("count"))
            except (TypeError, ValueError):
                return "bad value/count"
            return rules.play(game, actor_index, value, count, events)
        if action == "pass":
            take_index = payload.get("take_index")
            if take_index is not None:
                try:
                    take_index = int(take_index)
                except (TypeError, ValueError):
                    return "bad take_index"
            return rules.pass_turn(game, actor_index, events, take_index=take_index)
        return "unknown action"

    def board_json(self, game, viewer_id=None):
        self.normalize(game)
        me = next((p for p in game["players"] if p["user_id"] == viewer_id), None)
        return {
            "chat_id": game["chat_id"],
            "phase": game["phase"],
            "created_by": game["created_by"],
            "current_index": game.get("current_index", 0),
            "leader_index": game.get("leader_index", 0),
            "winner_id": game.get("winner_id"),
            "is_player": me is not None,
            "row": game.get("row", []),
            "passed_ids": list(game.get("passed", [])),
            "players": [
                {
                    "user_id": p["user_id"],
                    "name": p["name"],
                    "npc": bool(p.get("npc")),
                    "hand_count": len(p["hand"]),
                }
                for p in game["players"]
            ],
            "my_hand": sorted(me["hand"]) if me else [],
        }

    def rules(self):
        return RULES_TEXT


LEAVES_MODULE = LeavesGame()
