"""Run: python3 test_leaves.py"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import leaves as L


def mk(n=3, seed=1):
    random.seed(seed)
    g = L.new_game(1, 1, "A")
    for i in range(2, n + 1):
        g["players"].append(L.new_player(i, chr(64 + i)))
    assert L.start_game(g, []) is None
    return g


def test_deck_and_deal():
    g = mk(3)
    assert all(len(p["hand"]) == 12 for p in g["players"])
    g2 = mk(4)
    assert all(len(p["hand"]) == 11 for p in g2["players"])
    g3 = mk(6)
    assert all(len(p["hand"]) == 9 for p in g3["players"])


def test_lead_and_play():
    g = mk(3)
    g["players"][0]["hand"] = [5, 5, 9]
    g["players"][1]["hand"] = [6, 6, 1]
    g["players"][2]["hand"] = [1, 2, 3]
    g["deck"] = []
    g["phase"] = "playing"
    g["row"] = []
    g["passed"] = []
    g["current_index"] = 0
    ev = []
    assert L.play(g, 0, 5, 2, ev) is None
    assert g["row"][0]["value"] == 5 and g["row"][0]["count"] == 2


def test_play_stack_and_extend():
    g = mk(3)
    g["players"][0]["hand"] = [5, 5, 5, 5]
    g["players"][1]["hand"] = [4, 6]
    g["players"][2]["hand"] = [7]
    g["deck"] = []
    g["phase"] = "playing"
    g["row"] = [{"value": 5, "count": 2}]
    g["passed"] = []
    g["current_index"] = 0
    ev = []
    # stack onto end value 5: must play >= 2
    assert L.play(g, 0, 5, 2, ev) is None
    assert g["row"][0]["value"] == 5 and g["row"][0]["count"] == 4


def test_extend_left_right():
    g = mk(3)
    g["players"][0]["hand"] = [4, 7]
    g["players"][1]["hand"] = [5]
    g["players"][2]["hand"] = [6]
    g["deck"] = []
    g["phase"] = "playing"
    g["row"] = [{"value": 5, "count": 1}, {"value": 6, "count": 1}]
    g["passed"] = []
    g["current_index"] = 0
    ev = []
    # extend left with 4 (needs >= left stack count 1)
    assert L.play(g, 0, 4, 1, ev) is None
    assert g["row"][0]["value"] == 4


def test_cannot_pass_on_empty_row():
    g = mk(3)
    g["phase"] = "playing"
    g["row"] = []
    g["current_index"] = 0
    ev = []
    assert L.pass_turn(g, 0, ev) is not None


def test_win_on_empty_hand():
    g = mk(3)
    g["players"][0]["hand"] = [5]
    g["players"][1]["hand"] = [6, 7]
    g["players"][2]["hand"] = [8, 9]
    g["deck"] = []
    g["phase"] = "playing"
    g["row"] = []
    g["passed"] = []
    g["current_index"] = 0
    ev = []
    assert L.play(g, 0, 5, 1, ev) is None
    assert g["phase"] == "game_end"
    assert g["winner_id"] == g["players"][0]["user_id"]


def test_pass_and_serialize():
    g = mk(3)
    g["phase"] = "playing"
    g["row"] = [{"value": 5, "count": 1}]
    g["current_index"] = 0
    ev = []
    assert L.pass_turn(g, 0, ev) is None
    json.dumps({"leaves": {str(g["chat_id"]): g}})


if __name__ == "__main__":
    test_deck_and_deal()
    print("PASS test_deck_and_deal")
    test_lead_and_play()
    print("PASS test_lead_and_play")
    test_play_stack_and_extend()
    print("PASS test_play_stack_and_extend")
    test_extend_left_right()
    print("PASS test_extend_left_right")
    test_cannot_pass_on_empty_row()
    print("PASS test_cannot_pass_on_empty_row")
    test_win_on_empty_hand()
    print("PASS test_win_on_empty_hand")
    test_pass_and_serialize()
    print("PASS test_pass_and_serialize")
    print("all leaves tests passed")


def test_lobby_has_how_to_play_button():
    # FB-0074: the 13 Leaves lobby has a "🎥 How to play" button that opens the
    # how-to-play video, both on the Telegram board and in the Mini App lobby.
    import bot as BOT

    g = L.new_game(-1004393094474, 1, "Alice")
    kb = BOT.leaves_keyboard(g)
    flat = [b for row in kb for b in row]
    howto = [b for b in flat if b.get("text") == "🎥 How to play"]
    assert len(howto) == 1
    assert howto[0].get("url") == BOT.LEAVES_HOW_TO_PLAY_URL
    assert "youtu.be/s_pJ2p1Zjew" in howto[0]["url"]
    js = open(os.path.join(ROOT, "assets", "leaves", "scripts", "leaves.js")).read()
    assert "LV_HOW_TO_PLAY_URL" in js
    assert "youtu.be/s_pJ2p1Zjew" in js
    assert "openLink" in js
    assert "lvHowTo" in js
    html = open(os.path.join(ROOT, "assets", "shared", "flip7.html")).read()
    assert 'id="lvHowTo"' in html
    assert "🎥 How to play" in html


def _mk_npc_game():
    # 3 players: human A, NPC, human C.
    g = mk(3)
    g["players"][1]["npc"] = True
    g["players"][1]["name"] = "🤖 NPC"
    return g


def test_npc_autoplay_plays_its_own_cards():
    # FB-0160: the NPC must play from ITS hand, never the human's.
    g = _mk_npc_game()
    human_hand = [5, 5, 9]
    g["players"][0]["hand"] = list(human_hand)
    g["players"][1]["hand"] = [6, 6, 6, 2]
    g["players"][2]["hand"] = [1, 2, 3]
    g["row"] = []
    g["passed"] = []
    g["current_index"] = 1
    ev = []
    assert L.autoplay_npcs(g, ev) is None
    # NPC leads with its three 6s (sheds the most); the human hand is untouched.
    assert g["players"][1]["hand"] == [2]
    assert g["players"][0]["hand"] == human_hand
    assert g["row"] == [{"value": 6, "count": 3}]
    # Turn moved on to the next human.
    assert g["current_index"] == 2


def test_npc_autoplay_passes_when_stuck():
    g = _mk_npc_game()
    g["players"][0]["hand"] = [5, 5, 9]
    g["players"][1]["hand"] = [13, 13]
    g["players"][2]["hand"] = [1, 2, 3]
    g["row"] = [{"value": 5, "count": 3}]
    g["passed"] = []
    g["current_index"] = 1
    ev = []
    assert L.autoplay_npcs(g, ev) is None
    # NPC cannot play (needs 3 of a value, has only two 13s): passes,
    # takes a 5 from the row, and is marked passed. Human hand untouched.
    assert 5 in g["players"][1]["hand"]
    assert g["players"][1]["user_id"] in g["passed"]
    assert g["players"][0]["hand"] == [5, 5, 9]
    assert g["current_index"] == 2


def test_npc_autoplay_stops_at_human():
    g = _mk_npc_game()
    g["current_index"] = 0
    before = [list(p["hand"]) for p in g["players"]]
    ev = []
    assert L.autoplay_npcs(g, ev) is None
    assert [list(p["hand"]) for p in g["players"]] == before
    assert g["current_index"] == 0
    assert ev == []


def test_lobby_has_start_button():
    # FB-0159: the 13 Leaves lobby keyboard was missing the Start button
    # (the lv:start callback existed, but no button ever sent it).
    import bot as BOT

    g = L.new_game(-1004393094474, 1, "Alice")
    kb = BOT.leaves_keyboard(g)
    flat = [b for row in kb for b in row]
    start = [b for b in flat if b.get("callback_data") == "lv:start"]
    assert len(start) == 1
    assert start[0].get("text") == "▶️ Start game"
