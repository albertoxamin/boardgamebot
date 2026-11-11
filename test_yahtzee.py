"""Run: python3 test_yahtzee.py"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yahtzee as Y


def mk(n=2, seed=1):
    random.seed(seed)
    g = Y.new_game(1, 1, "A")
    for i in range(2, n + 1):
        g["players"].append(Y.new_player(i, chr(64 + i)))
    assert Y.start_game(g, []) is None
    return g


def set_dice(g, dice, rolls=1):
    g["turn"]["dice"] = list(dice)
    g["turn"]["rolls"] = rolls


def test_score_table():
    assert Y.score_for("ones", [1, 1, 1, 4, 6]) == 3
    assert Y.score_for("sixes", [6, 6, 6, 2, 1]) == 18
    assert Y.score_for("three_kind", [3, 3, 3, 2, 6]) == 17
    assert Y.score_for("three_kind", [3, 3, 2, 2, 6]) == 0
    assert Y.score_for("four_kind", [4, 4, 4, 4, 2]) == 18
    assert Y.score_for("four_kind", [4, 4, 4, 2, 2]) == 0
    assert Y.score_for("full_house", [3, 3, 3, 2, 2]) == 25
    assert Y.score_for("full_house", [3, 3, 3, 3, 2]) == 0
    assert Y.score_for("small_straight", [1, 2, 3, 4, 6]) == 30
    assert Y.score_for("small_straight", [1, 2, 3, 5, 6]) == 0
    assert Y.score_for("large_straight", [1, 2, 3, 4, 5]) == 40
    assert Y.score_for("large_straight", [2, 2, 3, 4, 5]) == 0
    assert Y.score_for("yahtzee", [5, 5, 5, 5, 5]) == 50
    assert Y.score_for("yahtzee", [5, 5, 5, 5, 6]) == 0
    assert Y.score_for("chance", [1, 2, 3, 4, 5]) == 15


def test_roll_and_keep():
    g = mk(2)
    random.seed(7)
    assert Y.roll_dice(g, 0, events=[]) is None
    first = list(g["turn"]["dice"])
    assert g["turn"]["rolls"] == 1 and len(first) == 5
    # Keep positions 0,2 and reroll the rest.
    assert Y.roll_dice(g, 0, keep=[True, False, True, False, False], events=[]) is None
    assert g["turn"]["dice"][0] == first[0] and g["turn"]["dice"][2] == first[2]
    assert g["turn"]["rolls"] == 2
    # Third roll then no more.
    assert Y.roll_dice(g, 0, events=[]) is None
    assert g["turn"]["rolls"] == 3
    assert Y.roll_dice(g, 0, events=[]).startswith("no rolls")
    # Wrong player cannot roll.
    assert Y.roll_dice(g, 1, events=[]) == "not your turn"


def test_score_advances_and_ends_turn():
    g = mk(3)
    set_dice(g, [1, 1, 1, 4, 6])
    ev = []
    assert Y.score_category(g, 0, "ones", ev) is None
    assert g["players"][0]["scores"]["ones"] == 3
    assert g["current_index"] == 1 and g["turn"]["rolls"] == 0
    # Already-filled box rejected (same player, fresh turn).
    g["current_index"] = 0
    Y.begin_turn(g)
    set_dice(g, [1, 1, 1, 1, 1])
    assert "already filled" in (Y.score_category(g, 0, "ones", ev) or "")
    # Scoring requires at least one roll.
    g["current_index"] = 1
    Y.begin_turn(g)
    assert Y.score_category(g, 1, "twos", ev) == "roll the dice first"


def test_upper_bonus_and_total():
    p = Y.new_player(1, "A")
    for key, face in Y.UPPER_FACE.items():
        p["scores"][key] = face * 3  # 63 exactly
    assert Y.upper_subtotal(p) == 63 and Y.has_upper_bonus(p)
    assert Y.total_score(p) == 63 + 35
    p["scores"]["ones"] = 1  # drop below threshold
    assert not Y.has_upper_bonus(p)
    assert Y.total_score(p) == 61


def test_yahtzee_bonus():
    g = mk(2)
    set_dice(g, [4, 4, 4, 4, 4])
    ev = []
    assert Y.score_category(g, 0, "yahtzee", ev) is None
    assert g["players"][0]["scores"]["yahtzee"] == 50
    assert g["players"][0]["yahtzee_bonus"] == 0
    # Later extra Yahtzee placed in chance earns the +100 bonus.
    set_dice(g, [2, 2, 2, 2, 2])
    assert Y.score_category(g, 1, "chance", ev) is None
    assert g["players"][1]["scores"]["chance"] == 10  # player 1 has no Yahtzee yet
    set_dice(g, [6, 6, 6, 6, 6])
    assert Y.score_category(g, 0, "chance", ev) is None
    assert g["players"][0]["scores"]["chance"] == 30
    assert g["players"][0]["yahtzee_bonus"] == 100


def test_full_game_to_end():
    g = mk(2)
    random.seed(3)
    guard = 0
    while g["phase"] != "game_end":
        guard += 1
        assert guard < 200
        idx = g["current_index"]
        p = g["players"][idx]
        open_cats = [k for k, v in p["scores"].items() if v is None]
        # Always roll once; occasionally reroll; then score the first open box.
        Y.roll_dice(g, idx, events=[])
        Y.score_category(g, idx, open_cats[0], events=[])
    assert g["phase"] == "game_end"
    assert g["winner_id"] is not None or len(g["winners"]) > 1
    assert all(Y.filled_count(p) == len(Y.CATEGORIES) for p in g["players"])
    totals = sorted((Y.total_score(p) for p in g["players"]), reverse=True)
    assert totals[0] == max(totals)
    assert len(g["winners"]) == sum(1 for t in totals if t == totals[0])


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all yahtzee tests passed")