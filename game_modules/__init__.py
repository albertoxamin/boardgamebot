class GameModule:
    key = ""

    def new_game(self, chat_id, creator_id, creator_name):
        raise NotImplementedError

    def new_player(self, user_id, name):
        raise NotImplementedError

    def npc_player(self):
        raise NotImplementedError

    def board_json(self, game, viewer_id=None):
        raise NotImplementedError

    def apply_action(self, game, actor_index, action, payload, events):
        raise NotImplementedError

    def rules(self):
        raise NotImplementedError

    def validate(self):
        return self.key and callable(self.new_game) and callable(self.board_json)
