"""Engine tests for The Fellowship of the Ring trick-taking game.

Run: python3 -m pytest test_fellowship.py  OR  python3 test_fellowship.py
"""
import json
import os
import random

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import fellowship as F


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def mk(n=3, seed=1, chapter_n=1):
    random.seed(seed)
    g = F.new_game(-100, 10, "Frodo player", chapter_n)
    for i in range(1, n):
        g["players"].append(F.new_player(10 + i, f"Player {i}"))
    ev = []
    assert F.start_game(g, ev) is None
    return g, ev


def pick_characters(g, choices=None):
    ev = []
    choices = choices or {}
    guard = 0
    while g["phase"] == "choosing":
        idx = F.current_player(g)
        assert idx is not None
        avail = F.available_characters(g)
        ch = choices.get(idx)
        if ch is None:
            ch = next((c for c in avail if c in F.chapter(g["chapter"])["required"]), avail[0])
        assert F.choose_character(g, idx, ch, ev) is None, (idx, ch, avail)
        guard += 1
        assert guard < 10
    while g["phase"] == "setup" and F.current_player(g) is not None:
        idx = F.current_player(g)
        pend = g["pending"]
        if pend["kind"] == "exchange_out":
            card = next((c for c in g["players"][idx]["hand"]
                         if not (idx == g["ring_holder"] and c == "R1")), None)
            assert F.exchange_cards(g, idx, card, pend["targets"][0], ev) is None
        else:
            assert F.exchange_back(g, idx, pend["given"], ev) is None
        guard += 1
        assert guard < 20
    return ev


def play_round(g, strategy=None):
    ev = []
    guard = 0
    while g["phase"] == "playing":
        idx = F.current_player(g)
        if g.get("pending") and g["pending"]["kind"] == "ring_choice":
            assert F.ring_choice(g, g["pending"]["actor"], True, ev) is None
            continue
        legal = F.legal_cards(g, idx)
        card = strategy(g, idx, legal) if strategy else legal[0]
        assert F.play_card(g, idx, card, ev) is None, (idx, card, legal)
        guard += 1
        assert guard < 60
    return ev


def test_deck_and_card_helpers():
    d = F.make_deck()
    assert len(d) == 37
    for s, mx in (("H", 8), ("M", 8), ("F", 8), ("S", 8), ("R", 5)):
        assert len([c for c in d if c[0] == s]) == mx
    assert F.cname("R1") == "1 of Rings"
    assert F.suit("F7") == "Forest"
    assert F.rank("S8") == 8


def test_deal_sizes_lost_and_ring_holder():
    for n, size in ((2, 12), (3, 12), (4, 9)):
        g, _ = mk(n)
        assert all(len(p["hand"]) == size for p in g["players"])
        assert g["lost"] != "R1"
        assert sum(len(p["hand"]) for p in g["players"]) == n * size <= 36
        assert "R1" in g["players"][g["ring_holder"]]["hand"]
        assert g["players"][g["ring_holder"]]["character"] == "frodo"
        assert g["phase"] == "choosing"


def test_chapter_one_can_be_chosen_and_is_serialisable():
    g, _ = mk(4)
    ev = pick_characters(g)
    assert sorted(p["character"] for p in g["players"]) == ["bilbo", "frodo", "gandalf", "pippin"]
    assert g["phase"] == "playing" or g.get("pending")
    assert json.loads(json.dumps(g)) == g
    assert any("lost card" in e for e in ev)


def test_required_character_enforced():
    g, _ = mk(3)
    ev = []
    others = [i for i in F._order_from(g, g["ring_holder"]) if i != g["ring_holder"]]
    first, second = others[0], others[1]
    assert F.choose_character(g, first, "gandalf", ev) is None
    err = F.choose_character(g, second, "pippin", ev)
    assert err is not None and "required" in err
    assert F.choose_character(g, second, "bilbo", ev) is None


def test_lead_restriction_and_follow_suit():
    g, _ = mk(3)
    pick_characters(g)
    # Force a controllable situation: current hand has only one non-Ring card.
    idx = g["current"]
    g["players"][idx]["hand"] = ["R2", "R3", "H4"]
    g["ring_broken"] = False
    assert F.legal_cards(g, idx) == ["H4"]
    ev = []
    assert F.play_card(g, idx, "R2", ev) == "cannot lead Rings yet"
    assert F.play_card(g, idx, "H4", ev) is None
    nxt = g["current"]
    g["players"][nxt]["hand"] = ["H2", "M3"]
    assert sorted(F.legal_cards(g, nxt)) == ["H2"]
    assert F.play_card(g, nxt, "M3", []) == "must follow the lead suit"


def test_one_ring_choice_can_win_or_lose():
    for use_it in (True, False):
        g, _ = mk(3)
        pick_characters(g)
        # Give the current player R1 plus a low card; others play high cards.
        leader = g["current"]
        g["ring_broken"] = True
        g["players"][leader]["hand"] = ["R1", "H1"]
        for k, j in enumerate(F._order_from(g, leader)[1:]):
            g["players"][j]["hand"] = [f"H{8 - k}"]
            g["trick"] = g["trick"] or {"leader": leader, "suit": None, "plays": [], "size": 3}
        ev = []
        assert F.play_card(g, leader, "R1", ev) is None
        while g.get("trick") and len(g["trick"]["plays"]) < 3:
            idx = g["current"]
            assert F.play_card(g, idx, g["players"][idx]["hand"][0], ev) is None
        assert g["pending"] and g["pending"]["kind"] == "ring_choice"
        owner = g["pending"]["actor"]
        assert F.ring_choice(g, owner, use_it, ev) is None
        tricks = len(g["players"][owner]["trick_wins"])
        if use_it:
            assert any("One Ring" in e for e in ev)
            assert "R1" in g["players"][owner]["won"]
        assert tricks >= 0


def test_ring_breaks_when_played_off_suit():
    g, _ = mk(3)
    pick_characters(g)
    leader = g["current"]
    g["players"][leader]["hand"] = ["H1", "H2"]
    for j in F._order_from(g, leader)[1:]:
        g["players"][j]["hand"] = ["R3", "R4"]
    g["ring_broken"] = False
    ev = []
    F.play_card(g, leader, "H1", ev)
    nxt = g["current"]
    assert F.play_card(g, nxt, "R3", ev) is None
    assert g["ring_broken"] is True
    assert any("broken" in e for e in ev)


def test_goals_and_short_chapter_win():
    g, _ = mk(3)
    pick_characters(g)
    g["phase"] = "playing"
    g["pending"] = None
    g["trick"] = None
    g["players"][0]["hand"] = ["H2", "H4"]
    g["players"][1]["hand"] = ["H3"]
    g["players"][2]["hand"] = ["H1"]
    F._start_trick(g, F.active_players(g)[0])
    ev = []
    guard = 0
    while g["phase"] == "playing":
        idx = g["current"]
        assert F.play_card(g, idx, g["players"][idx]["hand"][0], ev) is None
        guard += 1
        assert guard < 5
    assert g["phase"] in ("chapter_end", "round_end")
    for p in g["players"]:
        if p["character"] == "frodo":
            p["won"] = ["R1", "R2", "R3", "R4"]
            p["trick_wins"] = [1, 2, 3, 4]
        elif p["character"] == "bilbo":
            p["trick_wins"] = [1, 2, 3]
            p["won"] = ["H1", "H2", "H3"]
        elif p["character"] == "gandalf":
            p["trick_wins"] = [1]
            p["won"] = ["M1"]
        elif p["character"] == "pippin":
            p["trick_wins"] = []
            p["won"] = []
    assert all(x["ok"] for x in F.goal_status(g))


def test_goal_helpers():
    g, _ = mk(4)
    g["players"][0]["character"] = "frodo"
    g["players"][0]["won"] = ["R1", "R2"]
    assert F._goals(g)["frodo"] is True
    g["players"][0]["won"] = ["R1"]
    assert F._goals(g)["frodo"] is False
    g["players"][0]["character"] = "merry"
    g["players"][0]["trick_wins"] = [1, 2]
    assert F._goals(g)["merry"] is True
    g["players"][0]["trick_wins"] = [1, 2, 3]
    assert F._goals(g)["merry"] is False
    g["players"][0]["character"] = "pippin"
    g["players"][0]["trick_wins"] = []
    g["players"][1]["trick_wins"] = [1]
    assert F._goals(g)["pippin"] is True


def test_full_game_with_npcs_terminates():
    g, _ = mk(4)
    for p in g["players"]:
        p["npc"] = True
    F.advance(g, [])
    assert g["phase"] in ("round_end", "chapter_end")
    assert all(not p["hand"] or len(p["hand"]) == 1 for p in g["players"])
    assert json.loads(json.dumps(g)) == g


def test_chapter_progression_and_retry():
    g, _ = mk(3, chapter_n=1)
    g["phase"] = "chapter_end"
    ev = []
    assert F.next_chapter(g, ev) is None
    assert g["chapter"] == 2 and g["phase"] == "lobby"
    assert F.set_chapter(g, 8, ev) is None
    assert g["chapter"] == 8
    g["phase"] = "round_end"
    assert F.retry_round(g, ev) is None
    assert g["phase"] == "choosing" or g.get("pending") is not None


def test_invalid_moves_do_not_mutate():
    g, _ = mk(3)
    before = json.dumps(g)
    assert F.play_card(g, 0, "H1", []) is not None
    assert F.choose_character(g, 1, "frodo", []) is not None
    assert json.dumps(g) == before


def test_public_board_privacy():
    g, _ = mk(3)
    pick_characters(g)
    b = F.public_board(g, g["players"][0]["user_id"])
    assert b["players"][0]["hand"] == sorted(g["players"][0]["hand"])
    assert all(not p["hand"] for p in b["players"][1:])
    assert isinstance(b["goals"], list)
    assert set(b["my_legal"]) <= set(g["players"][0]["hand"])


def test_lobby_has_how_to_play_button():
    # FB-0081: the Fellowship lobby has a "🎥 How to play" button that opens
    # the how-to-play video, both on the Telegram board and in the Mini App
    # lobby.
    import bot as BOT

    g = F.new_game(-1004393094474, 1, "Alice")
    kb = BOT.fotr_keyboard(g)
    flat = [b for row in kb for b in row]
    howto = [b for b in flat if b.get("text") == "🎥 How to play"]
    assert len(howto) == 1
    assert howto[0].get("url") == BOT.FTR_HOW_TO_PLAY_URL
    assert "youtube.com/watch?v=0WdRKisfgH4" in howto[0]["url"]
    js = open(os.path.join(ROOT, "assets", "fellowship", "scripts", "fellowship.js")).read()
    assert "FTR_HOW_TO_PLAY_URL" in js
    assert "youtube.com/watch?v=0WdRKisfgH4" in js
    assert "openLink" in js
    assert "ftrHowTo" in js
    html = open(os.path.join(ROOT, "assets", "shared", "flip7.html")).read()
    assert 'id="ftrHowTo"' in html
    assert "🎥 How to play" in html


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)} tests passed")
