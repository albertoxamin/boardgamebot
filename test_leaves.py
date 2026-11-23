"""Run: python3 test_leaves.py"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
    g["passed"] = set()
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
    g["passed"] = set()
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
    g["passed"] = set()
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
    g["passed"] = set()
    g["current_index"] = 0
    ev = []
    assert L.play(g, 0, 5, 1, ev) is None
    assert g["phase"] == "game_end"
    assert g["winner_id"] == g["players"][0]["user_id"]


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
    print("all leaves tests passed")
