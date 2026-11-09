"""Run: python3 test_spots.py"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spots as S


def mk(n=2, seed=1):
    random.seed(seed)
    g = S.new_game(1, 1, "A")
    for i in range(2, n + 1):
        g["players"].append({"user_id": i, "name": chr(64 + i), "dogs": [],
                             "scored": [], "yard": [], "treats": 1})
    assert S.start_game(g, []) is None
    return g


def test_setup():
    g = mk(2)
    assert all(len(p["dogs"]) == 2 and len(p["yard"]) == 1 and p["treats"] == 1 for p in g["players"])
    assert g["dice_supply"] == 40 - 2 and g["treat_supply"] == 20 - 2
    assert [t["slug"] for t in g["tiles"]] == S.BEGINNER_TILES
    assert all(t["faceup"] for t in g["tiles"])
    assert g["phase"] == "playing"


def test_walk_place_and_bust():
    g = mk(2)
    idx = g["current_index"]
    # Force a known dog: Pebble spots [1,3,4]
    peb = next(d for d in g["dog_deck"] if d["slug"] == "pebble")
    g["dog_deck"].remove(peb)
    p = g["players"][idx]
    p["dogs"][0] = peb
    p["yard"] = [1]
    assert S.choose_trick(g, idx, "walk", []) is None
    assert g["pending"] and g["pending"]["kind"] == "place"
    g["trick"]["dice"] = [1, 1]  # pin dice: no bust in the placement part
    dice = g["trick"]["dice"]
    assert len(dice) == 2
    # Place first die on matching Pebble spot if possible, else bury
    spot = next((i for i, s in enumerate(peb["spots"]) if s == dice[0]), None)
    if spot is not None:
        assert S.do_place(g, idx, 0, ("dog", peb["iid"], spot), []) is None
    else:
        assert S.do_place(g, idx, 0, ("yard",), []) is None
    if g["pending"] and g["pending"]["kind"] == "place":
        assert S.do_place(g, idx, 0, ("yard",), []) is None  # bury second die
    # optional THEN roll pending (auto-bury may have finished the pool)
    assert g["pending"] and g["pending"]["kind"] == "optional_roll"
    assert S.apply_choice(g, idx, "done", []) is None
    assert g["trick"] is None and g["current_index"] == 1 - idx
    # Bust: bury a huge die
    idx2 = g["current_index"]
    p2 = g["players"][idx2]
    p2["yard"] = [7]
    assert S.choose_trick(g, idx2, "run", []) is None
    g["trick"]["dice"] = [2, 2, 2]
    g["pending"] = {"kind": "place", "player": idx2, "only_num": None,
                    "hunt_limit": None, "search": False, "placed_sum": 0}
    assert S.do_place(g, idx2, 0, ("yard",), []) is None
    assert yard_total_check(p2) == 0 and all(not d["placed"] for d in p2["dogs"])


def yard_total_check(p):
    return sum(p["yard"])


def test_score_action_and_autoscore():
    g = mk(2)
    idx = g["current_index"]
    p = g["players"][idx]
    peb = next(d for d in g["dog_deck"] if d["slug"] == "pebble")
    g["dog_deck"].remove(peb)
    peb["placed"] = {0: 1, 1: 3, 2: 4}
    p["dogs"][0] = peb
    assert S.score_action(g, idx, []) is None
    assert peb in p["scored"] and len(p["scored"]) == 1
    assert len(p["dogs"]) == 2  # drew a replacement (cap 6 not hit)
    # Auto-score: complete all dogs during a trick -> scored instantly
    p["dogs"] = []
    burt = next(d for d in g["dog_deck"] if d["slug"] == "burt")
    g["dog_deck"].remove(burt)
    burt["placed"] = {0: 1}
    p["dogs"].append(burt)
    p["scored"] = [peb]
    g["current_index"] = idx
    g["trick"] = S._fresh_trick("walk", idx)
    g["trick"]["rolled_steps"] = {0}  # pretend the Walk roll already happened
    g["trick"]["dice"] = [1]
    g["pending"] = {"kind": "place", "player": idx, "only_num": None,
                    "hunt_limit": None, "search": False, "placed_sum": 0}
    # Burt is already complete before the placement; placing on a *new*
    # drawn dog is not possible, so use a fresh incomplete dog instead:
    gum = next(d for d in g["dog_deck"] if d["slug"] == "gumbo")
    gum["placed"] = {0: 2, 1: 6}
    p["dogs"] = [gum]
    assert S.do_place(g, idx, 0, ("dog", gum["iid"], 2), []) is None
    assert gum not in p["scored"] and S.dog_complete(gum)  # manual scoring only
    # finish the trick, then score it as its own action
    while g["trick"] and g["pending"] and g["pending"]["kind"] == "place":
        assert S.do_place(g, idx, 0, ("yard",), []) is None
    if g["pending"]:
        assert S.apply_choice(g, idx, "done", []) is None
    assert g["trick"] is None and g["current_index"] == 1 - idx
    g["current_index"] = idx
    assert S.score_action(g, idx, []) is None
    assert gum in p["scored"] and len(p["scored"]) == 2


def test_reroll_and_win():
    g = mk(2)
    idx = g["current_index"]
    p = g["players"][idx]
    p["treats"] = 2
    assert S.choose_trick(g, idx, "walk", []) is None
    assert g["pending"]["kind"] == "place"
    before = list(g["trick"]["dice"])
    assert S.do_reroll(g, idx, None, []) is None
    assert p["treats"] == 1
    assert len(g["trick"]["dice"]) == 2
    # Finish trick
    while g["trick"] and g["pending"] and g["pending"]["kind"] == "place":
        assert S.do_place(g, idx, 0, ("yard",), []) is None
    if g["pending"]:
        assert S.apply_choice(g, idx, "done", []) is None
    assert g["trick"] is None
    # Win: 5 scored + complete one more via score action
    p["scored"] = p["scored"] + [dict(p["dogs"][0]) for _ in range(5)]
    for d in p["dogs"]:
        d["placed"] = {i: s for i, s in enumerate(d["spots"])}
    g["players"][idx]["treats"] = 1
    # force turn back to idx
    g["current_index"] = idx
    assert S.score_action(g, idx, []) is None
    assert g["phase"] == "game_end" and g["winner"] == p["user_id"]



def test_scavenge_and_search_finish():
    g = mk(2)
    idx = g["current_index"]
    p = g["players"][idx]
    p["yard"] = [5, 5]  # buried total 10: any die < 10 may be discarded
    g["tiles"].append({"slug": "scavenge", "faceup": True, "treat_on": False})
    g["tiles"].append({"slug": "search", "faceup": True, "treat_on": False})
    assert S.choose_trick(g, idx, "scavenge", []) is None
    assert g["pending"]["kind"] == "scavenge"
    # discard one die, then done -> placement pending with the rest
    assert S.apply_choice(g, idx, g["pending"]["options"][0], []) is None
    assert S.apply_choice(g, idx, "done", []) is None
    assert g["pending"]["kind"] == "place"
    while g["trick"] and g["pending"] and g["pending"]["kind"] == "place":
        assert S.do_place(g, idx, 0, ("yard",), []) is None
    assert g["trick"] is None  # trick completed, turn advanced
    # Search: place to 8 then Done via choice
    idx2 = g["current_index"]
    # Onto a dog (burying 8 would bust): Lil Beth spots [5,3]
    lb = next(d for d in g["dog_deck"] if 3 in d["spots"] and 5 in d["spots"])
    g["dog_deck"].remove(lb)
    lb["placed"] = {}
    g["players"][idx2]["dogs"] = [lb]
    assert S.choose_trick(g, idx2, "search", []) is None
    g["trick"]["dice"] = [3, 5, 2]
    # place 3 + 5 = 8 exactly on the dog, then Done
    i3 = lb["spots"].index(3); i5 = lb["spots"].index(5)
    assert S.do_place(g, idx2, 0, ("dog", lb["iid"], i3), []) is None  # 3
    assert S.do_place(g, idx2, 0, ("dog", lb["iid"], i5), []) is None  # 5
    assert S.apply_choice(g, idx2, "done", []) is None
    assert g["trick"] is None


def test_autoscore_mid_pool_continues():
    g = mk(2)
    idx = g["current_index"]
    p = g["players"][idx]
    p["yard"] = [1]
    peb = next(d for d in g["dog_deck"] if d["slug"] == "pebble")
    g["dog_deck"].remove(peb)
    peb["placed"] = {0: 1, 1: 3}  # pebble [1,3,4]
    p["dogs"] = [peb]
    assert S.choose_trick(g, idx, "walk", []) is None
    g["trick"]["dice"] = [4, 3, 3]  # 3 dice pool (patched for the test)
    p["treats"] = 0  # no reroll window: remaining dice auto-bury if unplaceable
    g["pending"]["dice"] = None
    # Place the 4 on Pebble -> completes the only dog; scoring is manual now,
    # so the dog stays complete in the pack and the trick continues.
    assert S.do_place(g, idx, 0, ("dog", peb["iid"], 2), []) is None
    assert peb not in p["scored"] and S.dog_complete(peb)
    assert g["trick"] is not None and g["pending"] is not None
    while g["trick"] and g["pending"] and g["pending"]["kind"] == "place":
        assert S.do_place(g, idx, 0, ("yard",), []) is None
    if g["pending"]:
        assert S.apply_choice(g, idx, "done", []) is None
    assert g["trick"] is None


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all spots tests passed")


def test_auto_place():
    g = mk(2)
    idx = g["current_index"]
    p = g["players"][idx]
    p["treats"] = 0
    peb = next(d for d in g["dog_deck"] if d["slug"] == "pebble")
    g["dog_deck"].remove(peb)
    peb["placed"] = {0: 1}
    p["dogs"] = [peb]
    assert S.choose_trick(g, idx, "walk", []) is None
    g["trick"]["dice"] = [3, 4, 2, 6]
    assert S.auto_place(g, idx, []) is None
    assert peb["placed"] == {0: 1, 1: 3, 2: 4}
    assert g["trick"]["dice"] == [2, 6]  # unplaceable dice stay in the pool
    # Hunt/Search-style pools are excluded from auto-place
    g["trick"]["dice"] = [3]
    g["pending"]["hunt_limit"] = 2
    assert S.auto_place(g, idx, []) == "auto-place is not available for this trick's dice"


def test_autobury_single_die_only():
    g = mk(2)
    idx = g["current_index"]
    p = g["players"][idx]
    p["treats"] = 0
    peb = next(d for d in g["dog_deck"] if d["slug"] == "pebble")
    g["dog_deck"].remove(peb)
    p["dogs"] = [peb]
    assert S.choose_trick(g, idx, "walk", []) is None
    g["trick"]["dice"] = [6, 5]  # pebble spots are [1,3,4]: both unplaceable
    g["pending"] = {"kind": "place", "player": idx, "only_num": None,
                    "hunt_limit": None, "search": False, "placed_sum": 0}
    # multi-die pool: nothing auto-buries, both dice stay for manual play
    assert S.do_place(g, idx, 0, ("yard",), []) is None
    assert g["trick"]["dice"] == [5] and p["yard"][-1] == 6
    # last die unplaceable with no treats: next placement attempt is moot,
    # it auto-buries instead (pool empties, trick advances)
    g["players"][idx]["treats"] = 0
    # simulate by calling autobury through a fresh single-die situation:
    g2 = mk(2)
    i2 = g2["current_index"]
    i2p = g2["players"][i2]
    i2p["treats"] = 0
    peb2 = next(d for d in g2["dog_deck"] if d["slug"] == "pebble")
    g2["dog_deck"].remove(peb2)
    i2p["dogs"] = [peb2]
    assert S.choose_trick(g2, i2, "walk", []) is None
    g2["trick"]["dice"] = [6]
    g2["trick"]["placed_roll"] = 1
    assert S._autobury(g2, []) is True
    assert g2["trick"]["dice"] == [] and 6 in i2p["yard"]
