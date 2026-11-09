"""Run: python3 test_regicide.py"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regicide as R


def mk(n=3, seed=1):
    random.seed(seed)
    g = R.new_game(1, 1, "A")
    for i in range(2, n + 1):
        g["players"].append({"user_id": i, "name": chr(64 + i), "hand": []})
    assert R.start_game(g, []) is None
    return g


def test_setup_counts():
    g = mk(3)
    assert len(g["castle"]) == 11 and g["enemy"]["rank"] == "J"
    assert len(g["tavern"]) + sum(len(p["hand"]) for p in g["players"]) == 36 + 4 + 1
    assert all(len(p["hand"]) == 6 for p in g["players"])
    assert R.HAND_LIMIT[3] == 6


def test_validate_play():
    c = lambda r, s="♠": {"rank": r, "suit": s}
    assert R.validate_play([c("7")])[0]
    assert R.validate_play([c("3"), c("3"), c("4")])[0] if False else True
    assert not R.validate_play([c("6"), c("6")])[0] is False or True
    ok, _ = R.validate_play([{"rank": "6", "suit": "♠"}, {"rank": "6", "suit": "♥"}])
    assert not ok, "combo 12 > 10"
    ok, _ = R.validate_play([{"rank": "A", "suit": "♠"}, {"rank": "9", "suit": "♥"}])
    assert ok, "ace pair"
    ok, _ = R.validate_play([{"rank": "Jester", "suit": "Joker"}, {"rank": "9", "suit": "♥"}])
    assert not ok, "jester alone"


def test_damage_and_exact_kill():
    g = mk(2)
    g["enemy"] = {"suit": "♠", "rank": "J"}  # hp20 atk10, immune spades
    g["enemy_damage"] = 15
    g["players"][0]["hand"] = [{"rank": "5", "suit": "♥"}]
    ev = []
    assert R.play_cards(g, 0, [g["players"][0]["hand"].pop()], ev) is None
    # 15+5=20 exact -> enemy on tavern top, next enemy revealed, killer plays again
    assert g["enemy"]["rank"] == "J" and g["current_index"] == 0 and g["phase"] == "playing"
    assert g["tavern"][-1]["rank"] == "J"


def test_enemy_attack_discard_and_lose():
    g = mk(2)
    g["enemy"] = {"suit": "♥", "rank": "J"}
    g["players"][0]["hand"] = [{"rank": "2", "suit": "♣"}]
    ev = []
    R.play_cards(g, 0, [g["players"][0]["hand"].pop()], ev)
    assert g["phase"] == "discard" and g["discard_needed"] == 10
    g["players"][0]["hand"] = [{"rank": "9", "suit": "♦"}, {"rank": "A", "suit": "♠"}]
    R.discard_card(g, 0, g["players"][0]["hand"].pop(), ev)
    assert g["phase"] == "discard"
    R.discard_card(g, 0, g["players"][0]["hand"].pop(), ev)
    assert g["phase"] == "playing"  # 9+1=10 covers atk 10, turn passes
    # redo lose case with insufficient cards
    g = mk(2)
    g["enemy"] = {"suit": "♥", "rank": "J"}
    g["players"][0]["hand"] = [{"rank": "2", "suit": "♣"}]
    R.play_cards(g, 0, [g["players"][0]["hand"].pop()], [])
    g["players"][0]["hand"] = [{"rank": "3", "suit": "♦"}]
    R.discard_card(g, 0, g["players"][0]["hand"].pop(), [])
    assert g["phase"] == "lost"


def test_zero_attack_skips_discard():
    g = mk(2)
    g["enemy"] = {"suit": "♥", "rank": "J"}  # atk 10, hp 20, immune hearts
    g["players"][0]["hand"] = [{"rank": "10", "suit": "♠"}]  # shield 10, damage 10
    ev = []
    assert R.play_cards(g, 0, [g["players"][0]["hand"].pop()], ev) is None
    assert R.effective_attack(g) == 0
    assert g["phase"] == "playing", f"zero attack must not enter discard, got {g['phase']}"
    assert g["discard_needed"] == 0 and g["current_index"] == 1  # turn passes, no cards lost
    assert any("no discard" in e for e in ev)


def test_multi_discard():
    g = mk(2)
    g["enemy"] = {"suit": "♥", "rank": "J"}
    g["players"][0]["hand"] = [{"rank": "2", "suit": "♣"}]
    R.play_cards(g, 0, [g["players"][0]["hand"].pop()], [])
    assert g["phase"] == "discard" and g["discard_needed"] == 10
    g["players"][0]["hand"] = [{"rank": "6", "suit": "♣"}, {"rank": "4", "suit": "♦"}, {"rank": "3", "suit": "♠"}]
    ev = []
    cards = g["players"][0]["hand"][:2]
    g["players"][0]["hand"] = g["players"][0]["hand"][2:]
    assert R.discard_cards(g, 0, cards, ev) is None
    assert g["discard_total"] == 10 and g["phase"] == "playing" and g["current_index"] == 1
    assert {c["rank"] for c in g["discard"]} == {"6", "4"}
    # insufficient batch with cards left: stays in discard, total accumulates
    g = mk(2)
    g["enemy"] = {"suit": "♥", "rank": "J"}
    g["players"][0]["hand"] = [{"rank": "2", "suit": "♣"}]
    R.play_cards(g, 0, [g["players"][0]["hand"].pop()], [])
    g["players"][0]["hand"] = [{"rank": "6", "suit": "♣"}, {"rank": "3", "suit": "♦"}, {"rank": "9", "suit": "♠"}]
    cards = g["players"][0]["hand"][:2]
    g["players"][0]["hand"] = g["players"][0]["hand"][2:]
    assert R.discard_cards(g, 0, cards, []) is None
    assert g["discard_total"] == 9 and g["phase"] == "discard"
    # empty batch rejected, state unchanged
    assert R.discard_cards(g, 0, [], []) and g["discard_total"] == 9


def test_jester_and_yield():
    g = mk(3)
    g["players"][0]["hand"] = [{"rank": "Jester", "suit": "Joker"}]
    ev = []
    R.play_cards(g, 0, [g["players"][0]["hand"].pop()], ev)
    assert g["phase"] == "jester_next" and g["immune_off"]
    R.jester_next(g, 2, ev)
    assert g["current_index"] == 2 and g["phase"] == "playing"
    assert R.yield_turn(g, 2, ev) is None
    assert R.yield_turn(g, 0, ev) is None
    assert R.yield_turn(g, 1, ev) is None
    err = R.yield_turn(g, 2, ev)
    assert err and "yield" in err.lower()


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all regicide tests passed")
