"""Run: python3 -m pytest test_game.py  OR  python3 test_game.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game as G
from collections import Counter


def mk(names=("A", "B", "C"), deck=None):
    g = G.new_game(1, 1, names[0], deck=deck if deck is not None else [])
    for i, n in enumerate(names[1:], 2):
        g["players"].append(G.new_player(i, n))
    g["phase"] = "playing"
    return g


def test_deck_composition():
    c = Counter((x["kind"], x["value"]) for x in G.build_deck())
    assert sum(c.values()) == 94
    assert c[("number", 0)] == 1 and c[("number", 1)] == 1
    assert c[("number", 12)] == 12 and c[("number", 2)] == 2
    for m in ["+2", "+4", "+6", "+8", "+10", "x2"]:
        assert c[("modifier", m)] == 1
    for a in ["Freeze", "Flip Three", "Second Chance"]:
        assert c[("action", a)] == 3


def test_scoring_order_x2_before_plus():
    p = G.new_player(1, "A")
    p["numbers"] = [3, 8, 11]
    p["modifiers"] = ["+4"]
    assert G.score_player(p) == 26
    p["modifiers"] = ["x2"]
    assert G.score_player(p) == 44
    p["modifiers"] = ["x2", "+6"]
    assert G.score_player(p) == 50  # 22*2+6
    p["numbers"] = [1, 2, 3, 4, 5, 6, 7]
    p["modifiers"] = []
    assert G.score_player(p) == 28 + 15  # Flip 7 bonus


def test_bust_and_second_chance_save():
    g = mk()
    g["players"][0]["numbers"] = [5]
    ev = []
    assert G.apply_card(g, 0, {"kind": "number", "value": 5}, ev) == "bust"
    assert g["players"][0]["status"] == "busted"
    assert g["players"][0]["numbers"] == [5, 5]  # both copies visible
    assert G.score_player(g["players"][0]) == 0
    g = mk()
    g["players"][0]["numbers"] = [5]
    g["players"][0]["second_chance"] = True
    ev = []
    assert G.apply_card(g, 0, {"kind": "number", "value": 5}, ev) == "saved"
    assert g["players"][0]["status"] == "active"
    assert g["players"][0]["second_chance"] is False


def test_flip7_ends_round_and_scores():
    g = mk()
    g["players"][0]["numbers"] = [1, 2, 3, 4, 5, 6]
    ev = []
    assert G.apply_card(g, 0, {"kind": "number", "value": 7}, ev) == "flip7"
    G.end_round(g, ev)
    assert g["players"][0]["last_round"] == 28 + 15


def test_freeze_and_second_chance_choice():
    g = mk()
    ev = []
    assert G.apply_card(g, 0, {"kind": "action", "value": "Freeze"}, ev) == "action"
    assert G.eligible_targets(g, "Freeze") == [0, 1, 2]
    assert G.resolve_action(g, 1, ev) == "ok"
    assert g["players"][1]["status"] == "frozen"
    assert G.apply_card(g, 0, {"kind": "action", "value": "Second Chance"}, ev) == "action"
    G.resolve_action(g, 1, ev)  # frozen player is not active - eligible excludes
    # (resolve_action itself doesn't re-check; bot checks eligible before calling)
    g2 = mk()
    ev = []
    G.apply_card(g2, 0, {"kind": "action", "value": "Second Chance"}, ev)
    g2["players"][1]["second_chance"] = True
    assert 1 not in G.eligible_targets(g2, "Second Chance")


def test_flip_three_three_cards_and_deferred():
    deck = [{"kind": "number", "value": 3},
            {"kind": "action", "value": "Freeze"},
            {"kind": "number", "value": 4}]
    g = mk(deck=list(reversed(deck)))  # draw() pops from end
    g["flip3"] = {"target_index": 1, "remaining": 3, "deferred": []}
    ev = []
    assert G.run_flip3_step(g, ev) == "continue"
    assert G.run_flip3_step(g, ev) == "continue"
    assert G.run_flip3_step(g, ev) == "done"
    assert g["players"][1]["numbers"] == [3, 4]
    assert G.finish_flip3(g, ev) == "action"
    assert g["pending_action"]["action"] == "Freeze"
    assert g["pending_action"]["chooser_id"] == 2  # target's id (B=2)


def test_flip_three_marks_forced_cards():
    deck = [{"kind": "number", "value": 3},
            {"kind": "action", "value": "Freeze"},
            {"kind": "number", "value": 4}]
    g = mk(deck=list(reversed(deck)))
    g["flip3"] = {"target_index": 1, "remaining": 3, "deferred": []}
    ev = []
    G.run_flip3_step(g, ev); G.run_flip3_step(g, ev); G.run_flip3_step(g, ev)
    assert g["players"][1]["numbers"] == [3, 4]
    assert g["players"][1]["flip3_cards"] == ["3", "4"]  # Freeze is deferred, not a pile card
    assert g["players"][0]["flip3_cards"] == []
    G.reset_round_player(g["players"][1])
    assert g["players"][1]["flip3_cards"] == []


def test_win_at_200_and_tie_continues():
    g = mk()
    g["players"][0]["total"] = 195
    g["players"][0]["numbers"] = [5]
    ev = []
    G.end_round(g, ev)
    assert g["phase"] == "game_end" and g["winner_id"] == 1
    g = mk()
    g["players"][0]["total"] = 200
    g["players"][1]["total"] = 200
    G.end_round(g, [])
    assert g["phase"] == "dealing" and g["round"] == 2  # tie -> auto next round


def test_next_round_rotates_dealer_and_aside():
    g = mk()
    g["players"][0]["numbers"] = [5]
    g["players"][0]["modifiers"] = ["+2"]
    ev = []
    G.start_next_round(g, ev)
    assert g["dealer_index"] == 1 and g["round"] == 2
    assert len(g["aside"]) == 2 and g["players"][0]["numbers"] == []


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
