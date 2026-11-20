import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import artichokes as A


def card(v, i=None):
    return {"id": i if i is not None else random.randrange(1, 10**6), "v": v}


def mk(n=3, seed=7):
    random.seed(seed)
    g = A.new_game(-100, 1, "Ada")
    for i in range(2, n + 1):
        g["players"].append(A.new_player(i, "P" + str(i)))
    ev = []
    assert A.start_game(g, ev) is None
    assert g["phase"] == "harvest"
    return g, ev


def set_hand(g, idx, values):
    g["players"][idx]["hand"] = [card(v, 1000 + idx * 100 + k) for k, v in enumerate(values)]


def ids(values_start, n):
    return list(range(values_start, values_start + n))


def test_setup_counts():
    g, ev = mk(4)
    assert len(g["garden_row"]) == 5
    assert len(g["garden_stack"]) == 55
    assert g["compost"] == []
    assert g["phase"] == "harvest"
    assert 0 <= g["current_index"] < 4
    for p in g["players"]:
        assert len(p["hand"]) == 5
        assert len(p["deck"]) == 5
        assert all(c["v"] == "artichoke" for c in p["hand"] + p["deck"])
        assert p["discard"] == []
    json.dumps(g)


def test_card_descriptions():
    for v in A.VEGGIES + (A.ARTICHOKE,):
        assert A.card_desc({"v": v})


def test_row_reshuffle_four_of_a_kind():
    g, ev = mk(2)
    g["garden_row"] = [card("pepper", i) for i in range(4)] + [card("beet", 90)]
    before = len(g["garden_stack"])
    A.replenish_row(g, ev)
    assert len(g["garden_row"]) == 5
    assert any("reshuffled" in e for e in ev)
    counts = {}
    for c in g["garden_row"]:
        counts[c["v"]] = counts.get(c["v"], 0) + 1
    assert max(counts.values()) < 4
    assert len(g["garden_stack"]) == before


def test_harvest_and_end_turn():
    g, ev = mk()
    idx = g["current_index"]
    nxt = (idx + 1) % len(g["players"])
    assert A.end_turn(g, idx, ev) == "you cannot end your turn now"
    assert A.harvest(g, nxt, 0, ev) == "not your turn"
    assert A.harvest(g, idx, 99, ev) == "pick a garden row card"
    taken = g["garden_row"][2]
    assert A.harvest(g, idx, 2, ev) is None
    assert taken in g["players"][idx]["hand"]
    assert len(g["garden_row"]) == 4
    assert g["phase"] == "play"
    assert A.end_turn(g, nxt, ev) == "not your turn"
    assert A.end_turn(g, idx, ev) is None
    assert len(g["players"][idx]["hand"]) == 5
    assert g["current_index"] == nxt
    assert g["round"] == 2
    assert g["phase"] == "harvest"


def test_broccoli_and_carrot():
    g, ev = mk()
    idx = g["current_index"]
    g["phase"] = "play"
    set_hand(g, idx, ["broccoli"] + ["artichoke"] * 3)
    b = g["players"][idx]["hand"][0]["id"]
    assert A.playable(g, idx) == [b]
    assert A.do_play(g, idx, b, ev) is None
    assert sum(c["v"] == "artichoke" for c in g["compost"]) == 1
    assert any(c["v"] == "broccoli" for c in g["players"][idx]["discard"])

    g["players"][idx]["discard"] = []
    set_hand(g, idx, ["carrot"] + ["artichoke"] * 2)
    carrot = g["players"][idx]["hand"][0]["id"]
    assert A.do_play(g, idx, carrot, ev) is None
    assert g["play_done"] is True
    assert sum(c["v"] == "artichoke" for c in g["compost"]) == 3
    assert any(c["v"] == "carrot" for c in g["compost"])
    other = card("pepper")
    g["players"][idx]["hand"].append(other)
    assert A.do_play(g, idx, other["id"], ev) == "Carrot was your only play action"
    assert A.end_turn(g, idx, ev) is None


def test_corn():
    g, ev = mk()
    idx = g["current_index"]
    g["phase"] = "play"
    set_hand(g, idx, ["corn", "artichoke"])
    corn, art = [c["id"] for c in g["players"][idx]["hand"]]
    assert A.do_play(g, idx, corn, ev) is None
    assert g["pending"]["kind"] == "corn"
    assert A.do_play(g, idx, art, ev) == "finish the current action first"
    assert A.apply_choice(g, (idx + 1) % 3, 0, ev) == "not your choice"
    chosen = g["garden_row"][1]
    assert A.apply_choice(g, idx, 1, ev) is None
    assert g["players"][idx]["deck"][0]["id"] == chosen["id"]
    assert any(c["id"] == art for c in g["players"][idx]["discard"])
    assert any(c["id"] == corn for c in g["players"][idx]["discard"])
    assert g["pending"] is None


def test_beet_swap_and_double_compost():
    g, ev = mk()
    idx = g["current_index"]
    target = (idx + 1) % 3
    g["phase"] = "play"
    set_hand(g, idx, ["beet", "artichoke", "pepper"])
    set_hand(g, target, ["artichoke", "artichoke", "corn"])
    beet = g["players"][idx]["hand"][0]["id"]
    assert A.do_play(g, idx, beet, ev) is None
    assert g["pending"]["kind"] == "beet"
    g["players"][idx]["hand"] = [card("artichoke", 500)]
    g["players"][target]["hand"] = [card("artichoke", 501)]
    assert A.apply_choice(g, idx, target, ev) is None
    assert g["pending"] is None
    assert len(g["compost"]) == 2
    assert g["players"][idx]["hand"] == []
    assert g["players"][target]["hand"] == []


def test_eggplant_passing():
    g, ev = mk(4)
    idx = g["current_index"]
    g["phase"] = "play"
    set_hand(g, idx, ["eggplant", "artichoke", "pepper", "corn"])
    for j in range(4):
        if j != idx:
            set_hand(g, j, ["artichoke", "peas", "potato"])
    eg = g["players"][idx]["hand"][0]["id"]
    assert A.do_play(g, idx, eg, ev) is None
    before = [len(p["hand"]) for p in g["players"]]
    pend = g["pending"]
    assert pend["kind"] == "eggplant"
    assert sum(c["v"] == "artichoke" for c in g["compost"]) == 1
    for _ in range(4):
        who = g["pending"]["by"]
        choose = [c["id"] for c in g["players"][who]["hand"]][:2]
        assert A.apply_choice(g, who, choose, ev) is None
    assert g["pending"] is None
    after = [len(p["hand"]) for p in g["players"]]
    assert after == [before[j] - min(2, before[j]) + min(2, before[(j - 1) % 4]) for j in range(4)]


def test_leek():
    g, ev = mk()
    idx = g["current_index"]
    target = (idx + 1) % 3
    g["phase"] = "play"
    set_hand(g, idx, ["leek", "artichoke"])
    top = card("pepper", 777)
    g["players"][target]["deck"] = [card("artichoke"), top]
    leek = g["players"][idx]["hand"][0]["id"]
    assert A.do_play(g, idx, leek, ev) is None
    assert A.apply_choice(g, idx, target, ev) is None
    assert g["pending"]["kind"] == "leek"
    assert g["pending"]["revealed"]["id"] == top["id"]
    assert A.apply_choice(g, idx, "hand", ev) is None
    assert top in g["players"][idx]["hand"]
    assert g["pending"] is None


def test_leek_discard_and_reshuffle():
    g, ev = mk()
    idx = g["current_index"]
    target = (idx + 1) % 3
    g["phase"] = "play"
    set_hand(g, idx, ["leek"])
    g["players"][target]["deck"] = []
    g["players"][target]["discard"] = [card("potato")]
    lk = g["players"][idx]["hand"][0]["id"]
    assert A.do_play(g, idx, lk, ev) is None
    assert A.apply_choice(g, idx, target, ev) is None
    assert g["pending"]["revealed"] is not None
    assert A.apply_choice(g, idx, "discard", ev) is None
    assert g["pending"] is None


def test_onion():
    g, ev = mk()
    idx = g["current_index"]
    target = (idx + 2) % 3
    g["phase"] = "play"
    set_hand(g, idx, ["onion", "artichoke"])
    onion = g["players"][idx]["hand"][0]["id"]
    assert A.do_play(g, idx, onion, ev) is None
    assert sum(c["v"] == "artichoke" for c in g["compost"]) == 1
    assert A.apply_choice(g, idx, target, ev) is None
    assert any(c["id"] == onion for c in g["players"][target]["discard"])
    assert g["pending"] is None


def test_pepper():
    g, ev = mk()
    idx = g["current_index"]
    g["phase"] = "play"
    set_hand(g, idx, ["pepper"])
    old = card("beet", 812)
    g["players"][idx]["discard"] = [old]
    pp = g["players"][idx]["hand"][0]["id"]
    assert A.do_play(g, idx, pp, ev) is None
    assert A.apply_choice(g, idx, 999, ev) == "invalid choice"
    assert A.apply_choice(g, idx, old["id"], ev) is None
    assert g["players"][idx]["deck"][0]["id"] == old["id"]
    assert g["pending"] is None


def test_peas():
    g, ev = mk()
    idx = g["current_index"]
    target = (idx + 1) % 3
    g["phase"] = "play"
    set_hand(g, idx, ["peas"])
    g["garden_stack"] = [card("beet", 601), card("corn", 602)]
    ps = g["players"][idx]["hand"][0]["id"]
    assert A.do_play(g, idx, ps, ev) is None
    assert g["pending"]["kind"] == "peas"
    assert len(g["pending"]["revealed"]) == 2
    assert A.apply_choice(g, idx, target, ev) is None
    assert A.apply_choice(g, idx, 601, ev) is None
    assert 601 in [c["id"] for c in g["players"][idx]["discard"]]
    assert 602 in [c["id"] for c in g["players"][target]["discard"]]
    assert g["pending"] is None
    assert g["garden_stack"] == []


def test_potato():
    g, ev = mk()
    idx = g["current_index"]
    g["phase"] = "play"
    set_hand(g, idx, ["potato"])
    potato = g["players"][idx]["hand"][0]["id"]
    g["players"][idx]["deck"] = [card("artichoke", 701)]
    assert A.do_play(g, idx, potato, ev) is None
    assert any(c["id"] == 701 for c in g["compost"])
    assert any(c["id"] == potato for c in g["players"][idx]["discard"])

    g["players"][idx]["deck"] = []
    g["players"][idx]["discard"] = [card("beet", 702)]
    set_hand(g, idx, ["potato"])
    potato2 = g["players"][idx]["hand"][0]["id"]
    assert A.do_play(g, idx, potato2, ev) is None
    assert any(c["id"] == 702 for c in g["players"][idx]["discard"])


def test_requirements_and_playable():
    g, ev = mk()
    idx = g["current_index"]
    g["phase"] = "play"
    set_hand(g, idx, ["artichoke", "broccoli", "carrot", "corn", "pepper", "potato", "peas"])
    g["garden_stack"] = []
    g["garden_row"] = []
    g["players"][idx]["deck"] = []
    g["players"][idx]["discard"] = []
    assert A.playable(g, idx) == []
    assert A.do_play(g, idx, g["players"][idx]["hand"][0]["id"], ev) == "you cannot play an Artichoke"
    g["garden_stack"] = [card("beet")]
    g["garden_row"] = [card("peas")]
    g["players"][idx]["discard"] = [card("beet")]
    assert set(A.playable(g, idx)) == {c["id"] for c in g["players"][idx]["hand"] if c["v"] in ("corn", "pepper", "potato", "peas")}


def test_win_only_at_refill():
    g, ev = mk()
    idx = g["current_index"]
    g["phase"] = "play"
    set_hand(g, idx, ["beet", "corn", "peas"])
    assert any(c["v"] != "artichoke" for c in g["players"][idx]["hand"])
    assert A.end_turn(g, idx, ev) is None
    assert g["phase"] == "harvest"
    g["current_index"] = idx
    g["phase"] = "play"
    g["players"][idx]["hand"] = [card("potato")]
    g["players"][idx]["deck"] = [card("pepper")]
    assert A.end_turn(g, idx, ev) is None
    assert g["phase"] == "game_end"
    assert g["winner_id"] == g["players"][idx]["user_id"]
    assert any("ABANDON ALL ARTICHOKES" in e for e in ev)


def resolve_pending(g, ev):
    pend = g["pending"]
    who = pend.get("by")
    if pend["kind"] == "eggplant":
        who = pend["order"][pend["pos"]]
        choice = [c["id"] for c in g["players"][who]["hand"]][:2]
    elif pend["kind"] in ("leek", "peas") and ("revealed" in pend or "target" in pend):
        choice = "hand" if pend["kind"] == "leek" else pend["options"][0]["v"]
    else:
        choice = pend["options"][0]["v"]
    err = A.apply_choice(g, who, choice, ev)
    assert err is None, err


def test_full_random_games():
    for n in (2, 3, 4):
        for seed in range(6):
            random.seed(1000 + seed * 10 + n)
            g = A.new_game(-100, 1, "A")
            for i in range(2, n + 1):
                g["players"].append(A.new_player(i, "P" + str(i)))
            ev = []
            assert A.start_game(g, ev) is None
            turns = 0
            while g["phase"] != "game_end" and turns < 500:
                turns += 1
                idx = g["current_index"]
                if g["phase"] == "harvest":
                    if g["garden_row"]:
                        assert A.harvest(g, idx, random.randrange(len(g["garden_row"])), ev) is None
                    else:
                        assert A.skip_harvest(g, idx, ev) is None
                while g["pending"] is not None:
                    resolve_pending(g, ev)
                if g["phase"] == "play":
                    for _ in range(8):
                        opts = A.playable(g, idx)
                        if not opts:
                            break
                        assert A.do_play(g, idx, random.choice(opts), ev) is None
                        while g["pending"] is not None:
                            resolve_pending(g, ev)
                        if g["play_done"]:
                            break
                    assert A.end_turn(g, idx, ev) is None
            assert g["phase"] == "game_end", (n, seed, turns)
            assert g["winner_id"] is not None
            json.dumps(g)


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print("All", len(tests), "tests passed")
