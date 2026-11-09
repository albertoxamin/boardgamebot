"""Run: python3 test_lsd.py"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lsd as L


def mk(n=2, seed=1):
    random.seed(seed)
    g = L.new_game(1, 1, "A")
    for i in range(2, n + 1):
        g["players"].append({"user_id": i, "name": chr(64 + i), "souls": 5,
                             "candle": None, "in_play": [], "demons": [], "demon_hand": []})
    assert L.start_game(g, []) is None
    return g


def card(g, slug):
    for c in g["block_deck"] + g["market"] + g["discard"]:
        if c["slug"] == slug:
            return c
    raise KeyError(slug)


def test_setup():
    g = mk(2)
    assert all(p["souls"] == 5 and p["candle"] and len(p["demon_hand"]) == 3 for p in g["players"])
    assert len(g["market"]) == 5 and len(g["block_deck"]) == 95
    assert len(g["demon_deck"]) == 20 - 6
    assert g["supply"] == 40 - 10
    assert g["phase"] == "playing" and g["current_index"] == 0


def test_roll_activates_everyone():
    g = mk(2)
    # Give player 0 Adam (8, +1 soul) and player 1 Eve (6, +1) in play
    a = card(g, "adam"); g["block_deck"].remove(a); g["players"][0]["in_play"].append(a)
    e = card(g, "eve"); g["block_deck"].remove(e); g["players"][1]["in_play"].append(e)
    g["players"][0]["candle"] = L._mk(g, L._card("beginners-candle", "Beginner's Candle", "candle", None, None, None, [6, 8], "candle"))
    g["players"][1]["candle"] = L._mk(g, L._card("good-candle", "Good Candle", "candle", None, None, None, [3, 4, 5], "candle"))
    s0, s1 = g["players"][0]["souls"], g["players"][1]["souls"]
    g["dice"] = [3, 3]  # total 6: Eve (6) + Beginner's (6,8) activate; Adam (8) and Good (3,4,5) don't
    L._finalize_roll(g, 0, [])
    assert g["players"][0]["souls"] == s0 + 1, g["players"][0]["souls"]
    assert g["players"][1]["souls"] == s1 + 1
    assert g["turn"]["rolled"]


def test_buy_and_summon():
    g = mk(2)
    p = g["players"][0]
    first = g["market"][0]
    ev = []
    assert L.buy_card(g, 0, first["iid"], ev) is None
    assert first in p["in_play"] and p["souls"] == 2 and g["turn"]["bought"]
    assert L.buy_card(g, 0, g["market"][0]["iid"], ev) == "you already bought this turn"
    # summon: sacrifice 3 block cards (need 3 in play)
    extra = [g["block_deck"].pop() for _ in range(2)]
    p["in_play"].extend(extra)
    demon = p["demon_hand"][0]
    assert L.summon(g, 0, [c["iid"] for c in p["in_play"][:3]], demon["iid"], ev) is None
    assert demon in p["demons"] and len(p["in_play"]) == 0 + (3 - 3)
    assert g["turn"]["summoned"]


def test_win_check():
    g = mk(2)
    p = g["players"][0]
    p["demons"] = [dict(p["demon_hand"][0]), dict(p["demon_hand"][1]), dict(p["demon_hand"][2])]
    p["souls"] = 10
    assert L.check_win(g, [])
    assert g["phase"] == "game_end" and g["winner"] == p["user_id"]


def test_optional_and_pending():
    g = mk(2)
    p = g["players"][0]
    al = card(g, "alligator")
    g["block_deck"].remove(al)
    p["in_play"].append(al)
    # opponent has a boy to discard
    boyk = card(g, "adam")
    g["block_deck"].remove(boyk)
    g["players"][1]["in_play"].append(boyk)
    g["dice"] = [3, 4]  # total 7 = Alligator
    L._finalize_roll(g, 0, [])
    assert g["pending"] and g["pending"]["kind"] == "optional"
    # skip the optional discard
    assert L.apply_choice(g, 0, "skip", []) is None
    assert g["pending"] is None and al in p["in_play"]
    # again, this time do it and discard the opponent's boy
    g["act_queue"] = [[0, al["iid"]]]
    g["activated"] = []
    L.drain(g, [])
    assert g["pending"] and g["pending"]["kind"] == "optional"
    assert L.apply_choice(g, 0, "do", []) is None
    assert g["pending"] and g["pending"]["kind"] == "alligator"
    opt = g["pending"]["options"][0]
    assert L.apply_choice(g, 0, {"player": opt["player"], "iid": opt["iid"]}, []) is None
    assert boyk in g["discard"] and g["pending"] is None


def test_steal_souls_choice():
    g = mk(2)
    p = g["players"][0]
    di = card(g, "rotten-dillinger")
    g["block_deck"].remove(di)
    p["in_play"].append(di)
    g["players"][1]["souls"] = 4
    g["dice"] = [5, 5]  # total 10 = Dillinger
    L._finalize_roll(g, 0, [])
    assert g["pending"] and g["pending"]["kind"] == "steal_souls"
    s1 = g["players"][1]["souls"]
    assert L.apply_choice(g, 0, 1, []) is None
    assert g["players"][0]["souls"] == 6 and g["players"][1]["souls"] == s1 - 1


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all lsd tests passed")
