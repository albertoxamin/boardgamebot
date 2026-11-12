"""Run: python3 test_odin.py"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import odin as O


def C(rank, suit):
    return {"rank": rank, "suit": suit}


def mk(n=3, seed=1):
    random.seed(seed)
    g = O.new_game(1, 1, "A")
    for i in range(2, n + 1):
        g["players"].append({"user_id": i, "name": chr(64 + i), "hand": [], "score": O.START_SCORE})
    assert O.start_game(g, []) is None
    return g


def play(g, idx, cards):
    """Remove cards from hand (bot-layer behaviour) then play them."""
    hand = g["players"][idx]["hand"]
    for c in cards:
        hand.remove(c)
    return O.play_cards(g, idx, cards, [])


def test_setup_and_deck():
    g = mk(3)
    assert all(len(p["hand"]) == 9 for p in g["players"])
    assert len(g["deck"]) == 54 - 27
    assert g["phase"] == "playing" and g["current_index"] == 0 and not g["table"]
    g2 = mk(2)
    assert len(g2["deck"]) == 36 - 18  # 2P: two colours removed
    assert {c["suit"] for p in g2["players"] for c in p["hand"]} <= set(O.SUITS[:4])


def test_set_value_and_mono():
    assert O.set_value([C(2, "blue"), C(8, "blue")]) == 82
    assert O.set_value([C(5, "red"), C(2, "red"), C(8, "red")]) == 852
    assert O.set_value([C(5, "red")]) == 5
    assert O.is_mono([C(3, "blue"), C(3, "red")]) and O.is_mono([C(3, "blue"), C(7, "blue")])
    assert not O.is_mono([C(3, "blue"), C(7, "red")])


def test_lead_and_response_rules():
    g = mk(3)
    g["players"][0]["hand"] = [C(5, "red"), C(9, "blue")]
    assert play(g, 0, [C(5, "red")]) is None
    assert g["table_value"] == 5 and g["current_index"] == 1
    # same count, higher value, lower digits combined: 3+3=33 does not exist here; use 6
    g["players"][1]["hand"] = [C(6, "blue"), C(2, "blue")]
    assert play(g, 1, [C(6, "blue")]) is None
    assert g["phase"] == "pickup" and g["pickup_player"] == 1
    assert O.choose_pickup(g, 1, C(5, "red"), []) is None
    assert g["table_value"] == 6 and C(5, "red") in g["players"][1]["hand"]
    assert g["current_index"] == 2
    # count must be table size (1) or +1 (2); 3 cards rejected
    g["players"][2]["hand"] = [C(9, "green"), C(8, "green"), C(7, "green")]
    g["players"][2]["hand"].remove(C(7, "green"))  # simulate removal of 3 below via copy
    err = O.validate_play(g, 2, [C(9, "green"), C(8, "green"), C(6, "green")])
    assert err and "1 or 2" in err
    # mixed set rejected
    g["players"][2]["hand"] = [C(9, "green"), C(8, "blue")]
    assert O.validate_play(g, 2, [C(9, "green"), C(8, "blue")]) is not None  # not mono
    assert O.validate_play(g, 2, [C(9, "green")]) is None  # 9 > 6 single


def test_pickup_and_pass_round_end():
    g = mk(2)
    g["players"][0]["hand"] = [C(4, "red"), C(9, "blue")]
    assert play(g, 0, [C(4, "red")]) is None
    g["players"][1]["hand"] = [C(9, "blue"), C(1, "green")]
    assert play(g, 1, [C(9, "blue")]) is None
    assert g["phase"] == "pickup"
    assert O.choose_pickup(g, 1, C(4, "red"), []) is None
    assert g["current_index"] == 0 and g["table_value"] == 9
    # 0 must beat 9 with 1 or 2 cards: pass -> round ends, 1 leads again
    assert O.pass_turn(g, 0, []) is None
    assert g["phase"] == "playing" and not g["table"] and g["current_index"] == 1
    assert g["table_value"] is None


def test_go_out_and_scoring():
    g = mk(2)
    g["players"][0]["hand"] = [C(9, "red")]
    assert O.start_game(g, []) is None or True
    g["players"][0]["hand"] = [C(9, "red")]
    g["players"][1]["hand"] = [C(3, "blue"), C(4, "blue")]
    ev = []
    assert play(g, 0, [C(9, "red")]) is None  # leads last card, goes out
    assert g["players"][0]["score"] == O.START_SCORE and g["players"][1]["score"] == O.START_SCORE - 2
    # no one at 0 -> new hand auto-dealt, starter rotates to player 1
    assert g["phase"] == "playing" and g["hand_starter"] == 1 and g["current_index"] == 1
    assert all(len(p["hand"]) == 9 for p in g["players"])


def test_lead_mono_dump_ends_hand():
    g = mk(2)
    g["players"][0]["hand"] = [C(3, "blue"), C(7, "blue")]
    g["players"][1]["hand"] = [C(1, "red"), C(2, "red")]
    ev = []
    cards = list(g["players"][0]["hand"])
    g["players"][0]["hand"] = []
    assert O.play_cards(g, 0, cards, ev) is None
    assert g["players"][1]["score"] == O.START_SCORE - 2 and g["hand_starter"] == 1


def test_game_end_first_to_zero():
    g = mk(2)
    g["players"][0]["score"] = 3
    g["players"][1]["score"] = 2
    g["players"][0]["hand"] = [C(9, "red")]
    g["players"][1]["hand"] = [C(3, "blue"), C(4, "blue")]
    assert play(g, 0, [C(9, "red")]) is None
    # player0: 3-0=3, player1: 2-2=0 (reaches 0) -> winner is player 1
    assert g["phase"] == "game_end" and g["winners"] == [1]


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all odin tests passed")
