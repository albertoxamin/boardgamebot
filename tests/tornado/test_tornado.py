"""Run: python3 test_tornado.py"""
import os
import random
import sys
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tornado as TS


def mk(n=2, boats=None, seed=1, gp=False):
    """New game with n players; if `boats` given, player i takes boat index
    boats[i] in list order, then the race starts."""
    random.seed(seed)
    g = TS.new_game(1, 1, "A")
    for i in range(2, n + 1):
        g["players"].append(TS.new_player(i, chr(64 + i)))
    ev = []
    assert TS.start_picking(g, ev, gp=gp) is None
    if boats:
        g["picking_order"] = list(range(n))
        g["picking_index"] = 0
        for i, b in enumerate(boats):
            assert TS.pick_boat(g, i, b, ev) is None
    return g


def test_deck_specs():
    weights = sorted(b["weight"] for b in TS.BOATS)
    assert weights == [1, 2, 3, 4, 5, 6]
    for b in TS.BOATS:
        assert sum(b["deck"].values()) == 20
        deck = TS.build_deck(b["deck"])
        assert len(deck) == 20
        for c in deck:
            assert c["kind"] in ("s", "c") and c["spaces"] in (1, 2)
    # speed boats lean straight, control boats lean curve
    speed = TS.BOATS[0]
    control = TS.BOATS[4]
    assert speed["deck"]["s1"] + speed["deck"]["s2"] > control["deck"]["s1"] + control["deck"]["s2"]
    assert control["deck"]["c1"] + control["deck"]["c2"] > speed["deck"]["c1"] + speed["deck"]["c2"]


def test_courses():
    for c in TS.COURSES:
        assert c["checkpoints"], c["name"]
        for cp, d in c["checkpoints"]:
            assert 0 < cp < c["length"] and d in ("L", "R")
    assert TS.course(mk(2, boats=[0, 1]))["name"] == "Tornado Circuit"


def test_picking_flow():
    g1 = TS.new_game(1, 1, "A")
    ev = []
    assert TS.start_picking(g1, ev) == "need at least 2 players"
    g = TS.new_game(1, 1, "A")
    g["players"].append(TS.new_player(2, "B"))
    ev = []
    g["players"].extend(TS.new_player(i, chr(64 + i)) for i in range(3, 8))
    assert TS.start_picking(g, ev).startswith("too many players")
    del g["players"][5:]
    assert TS.start_picking(g, ev) is None
    assert g["phase"] == "picking"
    assert TS.start_picking(g, ev) == "already started"
    assert TS.pick_boat(g, 0, 0, ev) == "not your pick"
    cur = g["picking_order"][g["picking_index"]]
    assert TS.pick_boat(g, cur, 99, ev) == "no such boat"
    assert TS.pick_boat(g, cur, 3, ev) is None
    nxt = g["picking_order"][g["picking_index"]]
    assert TS.pick_boat(g, nxt, 3, ev) == "that boat is already taken"
    assert TS.pick_boat(g, nxt, 1, ev) is None
    # remaining 3 pickers are auto-assigned free boats -> race starts
    assert TS.auto_assign_boats(g, ev) is None
    assert g["phase"] == "playing" and g["race_number"] == 1
    assert all(p["boat"] is not None for p in g["players"])
    assert TS.pick_boat(g, 0, 2, ev) == "not in boat selection"
    assert TS.auto_assign_boats(g, ev) == "not in boat selection"


def test_auto_assign():
    g = mk(3)
    g["picking_order"] = [0, 1, 2]
    g["picking_index"] = 0
    g["phase"] = "picking"
    assert TS.pick_boat(g, 0, 2, []) is None  # Bolt taken
    assert TS.auto_assign_boats(g, []) is None
    assert g["phase"] == "playing"
    taken = {p["boat"] for p in g["players"]}
    assert 2 in taken and len(taken) == 3 and None not in taken
    assert all(p["hand"] for p in g["players"])


def test_opening_hands_and_turn_order():
    # boats: Riptide(w1), Tsunami(w4), Waverunner(w6)
    g = mk(3, boats=[3, 2, 0])
    assert g["phase"] == "playing" and g["round"] == 1
    # turn order = weight ascending: players 0, 1, 2
    assert g["turn_order"] == [0, 1, 2]
    assert g["current_index"] == 0
    assert [len(g["players"][i]["hand"]) for i in range(3)] == [4, 5, 6]
    # every player starts at space 0
    assert all(p["pos"] == 0 for p in g["players"])
    assert TS.max_hand(g, 0) == 4 and TS.max_hand(g, 1) == 5 and TS.max_hand(g, 2) == 6


def test_compute_ranks_tiebreak():
    g = mk(3, boats=[3, 2, 0])  # weights 4, 2, 6 -> wait: boat 3=Tsunami w4, 2=Bolt w3, 0=Waverunner w6
    # finished players rank by finish order, then pos desc, ties -> lighter boat
    g["players"][1]["pos"] = 10
    g["players"][2]["pos"] = 10
    # player 1 boat=Bolt w3, player 2 boat=Waverunner w6 -> lighter first
    ranks = TS.compute_ranks(g)
    assert ranks == [1, 2, 0]
    g["players"][0]["pos"] = 25
    assert TS.compute_ranks(g)[0] == 0
    g["players"][0]["finished"] = True
    g["players"][0]["finish_rank"] = 1
    g["finish_order"] = [g["players"][0]["user_id"]]
    assert TS.compute_ranks(g) == [0, 1, 2]
    assert TS.active_ranks(g) == [1, 2]


def test_replenish_limits_and_retrieval():
    p = TS.new_player(1, "A")
    p["deck"] = [{"kind": "s", "spaces": 1} for _ in range(3)]
    p["played"] = [{"kind": "c", "spaces": 1, "tag": "first"},
                   {"kind": "c", "spaces": 2, "tag": "second"}]
    p["hand"] = []
    TS._replenish(p, 5)
    # deck first (3 cards), then played earliest-first
    assert len(p["hand"]) == 5
    assert p["hand"][3]["tag"] == "first" and p["hand"][4]["tag"] == "second"
    assert not p["deck"] and not p["played"]
    # hand already at limit -> nothing drawn
    before = list(p["hand"])
    TS._replenish(p, 4)
    assert p["hand"] == before


def test_do_play_validation():
    g = mk(2, boats=[4, 0])  # Squall(w2) first in turn order, Waverunner(w6) second
    assert g["turn_order"] == [0, 1]
    p0 = g["players"][0]
    p0["hand"] = [{"kind": "s", "spaces": 2}, {"kind": "c", "spaces": 1},
                  {"kind": "s", "spaces": 1}, {"kind": "s", "spaces": 1}]
    ev = []
    # wrong player / wrong phase guards
    assert TS.do_play(g, 1, [0], events=ev) == "not your turn"
    # play 2+1 = 3 spaces (max)
    assert TS.do_play(g, 0, [0, 2], events=ev) is None
    assert p0["pos"] == 3 and len(p0["hand"]) == 2 and len(p0["played"]) == 2
    assert g["current_index"] == 1  # advanced to player 1
    g["current_index"] = 0
    # playing 0 cards
    assert TS.do_play(g, 0, [], events=ev) == "play at least one card (or wait)"
    # too many cards (>3)
    p0["hand"] = [{"kind": "s", "spaces": 1} for _ in range(4)]
    assert TS.do_play(g, 0, [0, 1, 2, 3], events=ev) == "you may play at most 3 card(s) this turn"
    # total over cap
    p0["hand"] = [{"kind": "s", "spaces": 2} for _ in range(3)]
    assert TS.do_play(g, 0, [0, 1], events=ev).endswith("max 3 per turn")
    assert p0["pos"] == 3 and len(p0["hand"]) == 3  # nothing spent
    # bad hand position
    assert TS.do_play(g, 0, [9], events=ev) == "no such card in your hand"
    # boost caps at 4
    p0["hand"] = [{"kind": "s", "spaces": 2}, {"kind": "s", "spaces": 2},
                  {"kind": "s", "spaces": 1}, {"kind": "c", "spaces": 1}]
    assert TS.do_play(g, 0, [0, 1, 2], boost=True, events=ev).endswith("max 4 per turn")
    assert TS.do_play(g, 0, [0, 1], boost=True, events=ev) is None
    assert p0["pos"] == 7 and p0["boost_used"] is True
    # second boost refused
    g["current_index"] = 0
    assert TS.do_play(g, 0, [0], boost=True, events=ev) == "you already used your boost this race"


def test_checkpoint_curve_rule():
    g = mk(2, boats=[4, 0])
    g["players"][0]["pos"] = 8  # Tornado Circuit checkpoint at 9
    g["players"][0]["hand"] = [{"kind": "s", "spaces": 2}, {"kind": "c", "spaces": 1}]
    ev = []
    # crossing cp 9 with only straights -> refused
    assert TS.do_play(g, 0, [0], events=ev).startswith("you are passing checkpoint 9")
    assert g["players"][0]["pos"] == 8 and len(g["players"][0]["hand"]) == 2
    # stop exactly ON the checkpoint needs no curve (8 + 1 = 9)
    assert TS.do_play(g, 0, [1], events=ev) is None  # c1: 1 space, stops on 9
    assert g["players"][0]["pos"] == 9
    g["current_index"] = 0
    g["players"][0]["hand"] = [{"kind": "s", "spaces": 2}, {"kind": "c", "spaces": 2}]
    # crossing with a curve in the mix -> allowed (9 + 2 = 11, passes cp 9)
    assert TS.do_play(g, 0, [1], events=ev) is None
    assert g["players"][0]["pos"] == 11


def test_finish_and_race_end():
    g = mk(2, boats=[4, 0])
    p0, p1 = g["players"]
    p0["pos"] = 23
    p0["hand"] = [{"kind": "s", "spaces": 2}]
    ev = []
    assert TS.do_play(g, 0, [0], events=ev) is None
    assert p0["finished"] and p0["finish_rank"] == 1
    # 2 players: first finisher ends the race immediately
    assert g["phase"] == "race_end"
    assert g["winners"] == [p0["user_id"]] and g["winner_id"] == p0["user_id"]
    assert p1["finish_rank"] == 2 and p1["finished"] and p1["pos"] == TS.course(g)["length"]
    assert TS.do_play(g, 0, [0], events=ev) == "not in playing phase"
    assert TS.do_wait(g, 0, events=ev) == "not in playing phase"


def test_race_continues_until_one_left():
    g = mk(3, boats=[4, 0, 2])  # weights 2,6,3 -> turn order [0, 2, 1]
    ev = []
    # player 0 finishes first; race must NOT end (3 players)
    p0 = g["players"][0]
    p0["pos"] = TS.course(g)["length"] - 2
    p0["hand"] = [{"kind": "s", "spaces": 2}]
    assert TS.do_play(g, 0, [0], events=ev) is None
    assert p0["finished"] and g["phase"] == "playing"
    assert g["turn_order"] == [0, 2, 1]
    # next in turn order (player 2) finishes -> one unfinished left -> race ends
    idx = g["turn_order"][g["current_index"]]
    assert idx == 2
    p2 = g["players"][2]
    p2["pos"] = TS.course(g)["length"] - 1
    p2["hand"] = [{"kind": "s", "spaces": 2}]  # overshoots -> finish
    assert TS.do_play(g, 2, [0], events=ev) is None
    assert g["phase"] == "race_end"
    assert [p["finish_rank"] for p in g["players"]] == [1, 3, 2]
    # single race: no GP points
    assert all(p["points"] == 0 for p in g["players"])
    # next_race is for GP only
    assert TS.next_race(g, p0["user_id"], ev) == "no race to continue"
    # rematch goes back to boat selection
    TS.rematch_reset(g, ev)
    assert g["phase"] == "lobby" and g["gp"] is False
    assert all(p["boat"] is None for p in g["players"])


def test_wait_and_discard():
    g = mk(2, boats=[4, 0])
    g["players"][0]["hand"] = [{"kind": "s", "spaces": 2}, {"kind": "s", "spaces": 1}]
    ev = []
    # bad discard position
    assert TS.do_wait(g, 0, discard=[5], events=ev) == "no such card in your hand"
    assert TS.do_wait(g, 0, discard=[1], events=ev) is None
    p0 = g["players"][0]
    assert len(p0["hand"]) == 1 and len(p0["played"]) == 1
    assert any("waits" in e for e in ev)
    assert g["current_index"] == 1


def _legal(g, idx, combo, boost):
    p = g["players"][idx]
    cap = TS.max_move(g, idx, boost)
    cards = [p["hand"][h] for h in combo]
    total = sum(c["spaces"] for c in cards)
    if total == 0 or total > cap:
        return False
    c = TS.course(g)
    new_pos = min(p["pos"] + total, c["length"])
    crossed = any(p["pos"] <= cp < new_pos for cp, _ in c["checkpoints"])
    if crossed and not any(x["kind"] == "c" for x in cards):
        return False
    return True


def drive_race(g, ev):
    """Naive pilot: play the best legal move (saving boost when possible),
    else wait/discard until a curve shows up."""
    while g["phase"] == "playing":
        idx = g["turn_order"][g["current_index"]]
        p = g["players"][idx]
        move = None
        for boost in (False, True):
            if boost and p["boost_used"]:
                continue
            cap = TS.max_move(g, idx, boost)
            best = None
            for k in range(min(cap, len(p["hand"])), 0, -1):
                for combo in combinations(range(len(p["hand"])), k):
                    if not _legal(g, idx, combo, boost):
                        continue
                    total = sum(p["hand"][h]["spaces"] for h in combo)
                    if best is None or total > best[0]:
                        best = (total, combo)
                if best:
                    break  # biggest k with any legal combo wins
            if best:
                move = (best[1], boost)
                break
        if move:
            combo, boost = move
            assert TS.do_play(g, idx, list(combo), boost=boost, events=ev) is None
        else:
            # stuck: discard a straight to cycle toward curves
            disc = [h for h, c in enumerate(p["hand"]) if c["kind"] == "s"][:1]
            assert TS.do_wait(g, idx, discard=disc, events=ev) is None


def test_grand_prix_three_races():
    g = mk(3, boats=[4, 0, 2], seed=5, gp=True)
    ev = []
    assert g["gp"] is True
    for race in range(1, 4):
        drive_race(g, ev)
        assert g["phase"] == ("race_end" if race < 3 else "game_end"), \
            f"race {race}: {g['phase']}"
        if race < 3:
            # only players may continue
            assert TS.next_race(g, 999, ev) == "only players can continue the Grand Prix"
            assert TS.next_race(g, g["players"][0]["user_id"], ev) is None
            assert g["phase"] == "playing"
            assert g["race_number"] == race + 1
            assert all(not p["finished"] for p in g["players"])
            assert all(p["pos"] == 0 for p in g["players"])
            assert all(p["boost_used"] is False for p in g["players"])
    assert g["phase"] == "game_end"
    # 3 players -> points 5/3/0 per race, total 8/race
    assert sum(p["points"] for p in g["players"]) == 3 * 8
    valid = {a + b + c2 for a in (0, 3, 5) for b in (0, 3, 5) for c2 in (0, 3, 5)}
    for p in g["players"]:
        assert p["points"] in valid
    top = max(p["points"] for p in g["players"])
    assert g["winners"] == [p["user_id"] for p in g["players"] if p["points"] == top]
    assert TS.next_race(g, g["players"][0]["user_id"], ev) == "no race to continue"


def test_points_table():
    assert TS.points_for(2, 1) == 5 and TS.points_for(2, 2) == 0
    assert TS.points_for(3, 2) == 3 and TS.points_for(3, 3) == 0
    assert TS.points_for(4, 3) == 2 and TS.points_for(4, 4) == 0
    assert TS.points_for(5, 3) == 2 and TS.points_for(5, 4) == 0 and TS.points_for(5, 5) == 0
    assert TS.points_for(2, 3) == 0  # out of table


def test_race_end_awards_leftovers():
    g = mk(3, boats=[4, 0, 2], gp=True)
    ev = []
    g["players"][0]["pos"] = TS.course(g)["length"]  # pretend finished via direct call
    g["players"][0]["finished"] = True
    g["players"][0]["finish_rank"] = 1
    g["finish_order"] = [g["players"][0]["user_id"]]
    TS._end_race(g, ev)
    assert [p["finish_rank"] for p in g["players"]] == [1, 2, 3]
    assert [p["points"] for p in g["players"]] == [5, 3, 0]
    assert g["phase"] == "race_end" and g["gp"] is True


def test_state_json_serializable():
    import json
    g = mk(3, boats=[4, 0, 2], gp=True)
    ev = []
    drive_race(g, ev)
    assert TS.next_race(g, g["players"][0]["user_id"], ev) is None
    drive_race(g, ev)
    json.dumps(g)  # must not raise


def test_lobby_has_how_to_play_button():
    # FB-0078: the Tornado Splash lobby has a "🎥 How to play" button that
    # opens the how-to-play video, both on the Telegram board and in the
    # Mini App lobby.
    import bot as BOT

    g = TS.new_game(-1004393094474, 1, "Alice")
    kb = BOT.tornado_keyboard(g)
    flat = [b for row in kb for b in row]
    howto = [b for b in flat if b.get("text") == "🎥 How to play"]
    assert len(howto) == 1
    assert howto[0].get("url") == BOT.TS_HOW_TO_PLAY_URL
    assert "youtu.be/7iSZihL0nWw" in howto[0]["url"]
    js = open(os.path.join(ROOT, "assets", "tornado", "scripts", "tornado.js")).read()
    assert "TS_HOW_TO_PLAY_URL" in js
    assert "youtu.be/7iSZihL0nWw" in js
    assert "openLink" in js
    assert "tsHowTo" in js
    html = open(os.path.join(ROOT, "assets", "shared", "flip7.html")).read()
    assert 'id="tsHowTo"' in html
    assert "🎥 How to play" in html


def _solo_game(seed=3):
    """Annalisa + NPC, ready to pick boats."""
    import bot as BOT

    random.seed(seed)
    g = TS.new_game(-1004393094474, 1, "Annalisa")
    assert BOT.add_npc("tornado", g) is None
    assert g["players"][1].get("npc")
    return g


def test_npc_autoplay_picks_boat():
    # FB-0169: the NPC picks its own boat — nobody has to pick for it.
    g = _solo_game()
    ev = []
    assert TS.start_picking(g, ev) is None
    TS.autoplay_npcs(g, ev)
    while g["phase"] == "picking":
        idx = g["picking_order"][g["picking_index"]]
        assert not g["players"][idx].get("npc"), "autoplay must pick for the NPC"
        free = next(i for i in range(len(TS.BOATS))
                    if not any(p["boat"] == i for p in g["players"]))
        assert TS.pick_boat(g, idx, free, ev) is None
        TS.autoplay_npcs(g, ev)
    assert g["phase"] == "playing"
    assert all(p["boat"] is not None for p in g["players"])
    assert len({p["boat"] for p in g["players"]}) == 2


def test_npc_best_play_prefers_finish_and_curve():
    # A subset that finishes beats a longer one that does not; crossing a
    # checkpoint needs a curve card in the subset.
    g = mk(2, boats=[0, 1])
    p = g["players"][1]
    p["pos"] = 22  # Tornado Circuit is 24 long
    p["hand"] = [TS._card("s", 1), TS._card("s", 2), TS._card("c", 2)]
    assert TS._npc_best_play(g, 1) is not None
    chosen = TS._npc_best_play(g, 1)
    total = sum(p["hand"][i]["spaces"] for i in chosen)
    assert p["pos"] + total >= TS.course(g)["length"]
    p["pos"] = 8  # checkpoint at 9: s2 alone would cross it without a curve
    p["hand"] = [TS._card("s", 2), TS._card("c", 1)]
    assert TS._npc_best_play(g, 1) == [0, 1]
    p["hand"] = [TS._card("s", 2)]
    assert TS._npc_best_play(g, 1) is None


def test_npc_autoplay_plays_its_turn():
    # FB-0169: on the NPC's turn the race moves on by itself.
    g = mk(2, boats=[0, 1])  # turn order [1, 0]: Bolt (w3) goes first
    g["players"][1]["npc"] = True
    assert g["turn_order"][g["current_index"]] == 1
    ev = []
    before = g["players"][1]["pos"]
    TS.autoplay_npcs(g, ev)
    assert g["players"][1]["pos"] > before
    assert g["turn_order"][g["current_index"]] == 0
    assert not any("NPC error" in e for e in ev)


def test_npc_waits_when_no_legal_play():
    # Hand of straights just before a checkpoint: every card would cross
    # it without a curve, so the NPC waits and fresh cards come next round.
    g = mk(2, boats=[0, 1])
    g["players"][1]["npc"] = True
    g["players"][1]["pos"] = 8
    g["players"][1]["hand"] = [TS._card("s", 2)]
    ev = []
    TS.autoplay_npcs(g, ev)
    assert g["players"][1]["pos"] == 8
    assert g["turn_order"][g["current_index"]] == 0
    assert any("waits" in e for e in ev)
    # It discarded its hand to cycle fresh cards in — waiting alone
    # would leave it stuck before the checkpoint forever.
    assert g["players"][1]["hand"] == []


def test_npc_autoplay_finishes_solo_race():
    # FB-0169: a whole race, human waiting every turn, NPC driving itself.
    g = _solo_game(seed=11)
    ev = []
    assert TS.start_picking(g, ev) is None
    TS.autoplay_npcs(g, ev)
    while g["phase"] == "picking":
        idx = g["picking_order"][g["picking_index"]]
        free = next(i for i in range(len(TS.BOATS))
                    if not any(p["boat"] == i for p in g["players"]))
        assert TS.pick_boat(g, idx, free, ev) is None
        TS.autoplay_npcs(g, ev)
    assert g["phase"] == "playing"
    turns = 0
    while g["phase"] == "playing" and turns < 500:
        turns += 1
        cur = g["turn_order"][g["current_index"]]
        if g["players"][cur].get("npc"):
            TS.autoplay_npcs(g, ev)
        else:
            assert TS.do_wait(g, cur, events=ev) is None
            TS.autoplay_npcs(g, ev)
    assert g["phase"] == "race_end", f"stuck in {g['phase']} after {turns} turns"
    assert g["players"][1]["finished"]
    assert not any("NPC error" in e for e in ev)


def test_api_join_npc_and_miniapp_button():
    # FB-0168: 🤖 Add NPC from the Mini App lobby (and the chat lobby
    # button, which answered "Unknown button" — no ts:npc branch existed).
    import bot as BOT
    from unittest.mock import patch

    state = {"tornado": {}}
    g = TS.new_game(-1004393094474, 1, "Annalisa")
    state["tornado"]["-1004393094474"] = g
    with patch.object(BOT, "send_board", return_value={"ok": False}):
        ev, err = BOT.tornado_api_move(state, -1004393094474, 1,
                                       {"action": "join_npc"})
    assert err is None
    assert len(g["players"]) == 2 and g["players"][1].get("npc")
    assert any("NPC joined" in e for e in ev)
    assert BOT.tornado_board_json(g, 1)["can_add_npc"] is True
    for _ in range(3):
        assert BOT.add_npc("tornado", g) is None
    assert BOT.tornado_board_json(g, 1)["can_add_npc"] is False
    with patch.object(BOT, "send_board", return_value={"ok": False}):
        _, err = BOT.tornado_api_move(state, -1004393094474, 1,
                                      {"action": "join_npc"})
    assert err is not None
    js = open(os.path.join(ROOT, "assets", "tornado", "scripts", "tornado.js")).read()
    assert "tsNpc" in js
    assert "join_npc" in js
    assert "can_add_npc" in js
    html = open(os.path.join(ROOT, "assets", "shared", "flip7.html")).read()
    assert 'id="tsNpc"' in html
    assert "🤖 Add NPC" in html
    assert "tornado.js?v=4" in html
    bot_src = open(os.path.join(ROOT, "bot.py")).read()
    assert '["ts", "npc"]' in bot_src
    assert "TS.autoplay_npcs(g, ev)" in bot_src
    assert "TS.autoplay_npcs(ts, ev)" in bot_src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok - {fn.__name__}")
    print(f"All {len(fns)} tornado tests passed.")
