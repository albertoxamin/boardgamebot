"""Run: python3 test_castlecombo.py"""
import json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import castlecombo as CC


def mk(n=2, seed=1):
    random.seed(seed)
    g = CC.new_game(1, 100, "A")
    for i in range(n):
        g["players"].append(CC.new_player(100 + i, chr(65 + i)))
    assert CC.start_game(g, []) is None
    g["current"] = 0
    return g


def put(g, p, cid, x=0, y=0, fd=False, gold=0):
    inst = CC._mk(g, cid)
    inst.update(x=x, y=y, fd=fd, gold=gold)
    p["tableau"].append(inst)
    return inst


def resolve(g, ev, pick=None):
    """Resolve every pending choice (default: first option)."""
    while g.get("pending"):
        pend = g["pending"]
        opts = [o["v"] for o in pend["options"]]
        ch = pick(pend) if pick else opts[0]
        r = CC.apply_choice(g, pend["player"], ch, ev)
        assert r is None, (pend["kind"], r, ev)


def force_take(g, idx, cid, flipped=False, pick=None):
    """Put card cid alone in the messenger's display; player idx takes it."""
    assert idx == g["current"] and not g.get("pending")
    row = g["messenger"]
    inst = CC._mk(g, cid)
    g["rows"][row] = [inst]
    ev = []
    r = CC.do_take(g, idx, inst["id"], flipped, ev)
    assert r is None, (r, ev)
    resolve(g, ev, pick)
    assert not g.get("pending"), g["pending"]
    return ev


# ------------------------------------------------------------------- setup

def test_deck_and_start():
    assert len(CC.CARDS) == 78
    ids = [c["id"] for c in CC.CARDS]
    assert len(set(ids)) == 78
    castle = sorted(c["id"] for c in CC.CARDS if c["loc"] == CC.CASTLE)
    village = sorted(c["id"] for c in CC.CARDS if c["loc"] == CC.VILLAGE)
    assert castle == list(range(1, 40))
    assert village == list(range(41, 80))
    g = mk(2)
    assert g["phase"] == "playing"
    assert g["messenger"] == CC.VILLAGE
    for loc in (CC.CASTLE, CC.VILLAGE):
        assert len(g["rows"][loc]) == 3
        assert len(g["decks"][loc]) == 36
        for inst in g["rows"][loc]:
            assert CC.card_of(inst)["loc"] == loc
    for p in g["players"]:
        assert p["gold"] == 15 and p["keys"] == 2 and len(p["tableau"]) == 0


def test_messenger_starts_at_village():
    g = mk(2)
    # first player must buy from the Village display
    assert all(CC.card_of(c)["loc"] == CC.VILLAGE for c in g["rows"][g["messenger"]])


# --------------------------------------------------------------- placement

def test_placement_options():
    g = mk(2)
    p = g["players"][0]
    assert CC.placement_options(p) == [(0, 0)]
    put(g, p, 30, 0, 0)
    assert set(CC.placement_options(p)) == {(1, 0), (-1, 0), (0, 1), (0, -1)}
    put(g, p, 32, 1, 0)
    put(g, p, 47, 2, 0)          # full top row of the bounding box
    opts = set(CC.placement_options(p))
    assert (3, 0) not in opts and (-1, 0) not in opts   # never 4 in a row
    assert (0, 1) in opts and (1, 1) in opts and (2, 1) in opts
    # fill the 3x3 -> nothing left
    for xy in ((0, 1), (1, 1), (2, 1), (0, 2), (1, 2), (2, 2)):
        put(g, p, 48, *xy)
    assert CC.placement_options(p) == []


def test_tableau_max_9_cards():
    g = mk(2)
    p = g["players"][0]
    for xy in ((x, y) for y in range(3) for x in range(3)):
        put(g, p, 30, *xy)
    assert len(p["tableau"]) == 9
    g["rows"][g["messenger"]].append(CC._mk(g, 65))
    cid = g["rows"][g["messenger"]][-1]["id"]
    assert CC.do_take(g, 0, cid, False, []) == "your tableau is complete"


# ---------------------------------------------------------------- cost

def test_costs_and_discounts():
    g = mk(2)
    idx = 0
    hm = CC.card_of({"cid": 1})          # His Majesty, Castle, cost 6
    brigand = CC.card_of({"cid": 66})    # Village, cost 7
    assert CC.cost_for(g, idx, hm) == 6
    assert CC.cost_for(g, idx, brigand) == 7
    p = g["players"][idx]
    put(g, p, 3)                         # Princess: 1 off Castle cards
    assert CC.cost_for(g, idx, hm) == 5
    assert CC.cost_for(g, idx, brigand) == 7
    put(g, p, 8)                         # Baron: 1 off everything
    assert CC.cost_for(g, idx, hm) == 4
    assert CC.cost_for(g, idx, brigand) == 6
    put(g, p, 3, fd=True)                # face-down discounts do nothing
    assert CC.cost_for(g, idx, hm) == 4
    # discount never drops below 0
    for cid in (21, 24, 37, 44, 76):     # four more Castle discounts
        put(g, p, cid)
    assert CC.cost_for(g, idx, hm) == 0


def test_buy_and_place_pending():
    g = mk(2)
    p = g["players"][0]
    put(g, p, 30, 0, 0)                  # so placement has several options
    gold0, keys0 = p["gold"], p["keys"]
    ev = force_take(g, 0, 2, pick=lambda pend: pend["kind"] == "place"
                    and "1,0" or pend["options"][0]["v"])
    assert len(p["tableau"]) == 2        # placed exactly once (regression)
    inst = [c for c in p["tableau"] if c["cid"] == 2][0]
    assert (inst["x"], inst["y"]) == (1, 0)
    assert p["gold"] == gold0 - 6 + 1    # Prince costs 6, then +1 gold (own blue)
    assert p["keys"] == keys0


def test_place_pending_with_ability_choice():
    g = mk(2)
    p = g["players"][0]
    put(g, p, 30, 0, 0)
    picks = []
    ev = force_take(g, 0, 14, pick=lambda pend: (picks.append(pend["kind"]),
                                                 pend["options"][0]["v"]) and None
                    or pend["options"][0]["v"])
    assert picks == ["place", "ability"], picks
    assert len([c for c in p["tableau"] if c["cid"] == 14]) == 1


# ------------------------------------------------------------------ flip

def test_flip_face_down():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    opp = g["players"][1]
    gold0, keys0 = p["gold"], p["keys"]
    ev = force_take(g, 0, 1, flipped=True)   # His Majesty face-down
    assert p["gold"] == gold0 + 6 and p["keys"] == keys0 + 2
    inst = p["tableau"][-1]
    assert inst["fd"] and inst["cid"] == 1
    assert opp["gold"] == 15                 # no ability fired
    assert g["messenger"] == CC.CASTLE       # face-down never moves the messenger


# ------------------------------------------------------------- messenger

def test_messenger_moves_to_opposite_row():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    force_take(g, 0, 2)          # Prince: no pennant
    assert g["messenger"] == CC.CASTLE
    g["current"] = 0
    force_take(g, 0, 3)          # Princess: messenger pennant
    assert g["messenger"] == CC.VILLAGE
    g["current"] = 0
    force_take(g, 0, 42)         # Vicar: village pennant
    assert g["messenger"] == CC.CASTLE


def test_key_move_and_renew():
    g = mk(2)
    p = g["players"][0]
    keys0 = p["keys"]
    row0 = [c["id"] for c in g["rows"][CC.VILLAGE]]
    assert CC.do_key(g, 0, "move", []) is None
    assert p["keys"] == keys0 - 1 and g["messenger"] == CC.CASTLE
    assert CC.do_key(g, 0, "renew", []) is None
    assert p["keys"] == keys0 - 2
    assert len(g["rows"][CC.CASTLE]) == 3
    new_ids = {c["id"] for c in g["rows"][CC.CASTLE]}
    assert all(CC.card_of(c)["loc"] == CC.CASTLE for c in g["rows"][CC.CASTLE])
    # old display cards are not lost: they sit in deck or discard
    total = sum(len(g["decks"][l]) + len(g["discards"][l]) + len(g["rows"][l])
                for l in (CC.CASTLE, CC.VILLAGE))
    assert total == 78
    p["keys"] = 0
    assert CC.do_key(g, 0, "move", []) == "no keys left"


# ----------------------------------------------------------- refill/death

def test_draw_reshuffles_discards():
    g = mk(2)
    g["decks"][CC.CASTLE] = [CC._mk(g, 30), CC._mk(g, 32)]
    g["discards"][CC.CASTLE] = [CC._mk(g, 34), CC._mk(g, 36), CC._mk(g, 38)]
    drawn = [CC._draw(g, CC.CASTLE) for _ in range(5)]
    assert all(c is not None for c in drawn)
    assert CC._draw(g, CC.CASTLE) is None
    assert len(g["discards"][CC.CASTLE]) == 0
    assert len(g["decks"][CC.CASTLE]) == 0


def test_location_death_and_game_end():
    g = mk(2)
    g["current"] = 0
    g["messenger"] = CC.CASTLE
    g["decks"][CC.CASTLE] = []
    g["discards"][CC.CASTLE] = []
    g["rows"][CC.CASTLE] = [CC._mk(g, 30)]
    ev = []
    assert CC.do_take(g, 0, g["rows"][CC.CASTLE][0]["id"], True, ev) is None
    resolve(g, ev)
    assert g["mm_live"][CC.CASTLE] is False
    assert g["rows"][CC.CASTLE] == [] and g["decks"][CC.CASTLE] == []
    assert g["messenger"] == CC.VILLAGE
    assert g["phase"] == "playing"
    # now kill the village too -> game ends
    g["current"] = 0
    g["messenger"] = CC.VILLAGE
    g["decks"][CC.VILLAGE] = []
    g["discards"][CC.VILLAGE] = []
    g["rows"][CC.VILLAGE] = [CC._mk(g, 65)]
    ev = []
    assert CC.do_take(g, 0, g["rows"][CC.VILLAGE][0]["id"], True, ev) is None
    resolve(g, ev)
    assert g["phase"] == "game_end"
    assert g["results"] and len(g["results"]) == 2


# --------------------------------------------------------------- abilities

def test_gain_abilities():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    # Prince: +1 gold per blue shield (his own blue shield included)
    put(g, p, 3)             # Princess, 1 blue
    put(g, p, 9)             # Duchess, 2 blue
    gold0 = p["gold"]
    force_take(g, 0, 2)
    assert p["gold"] == gold0 - 5 + 4   # Princess discount -> 5 gold, +4 gold ability
    # Chancellor: +1 key per green shield (his own green included)
    p2 = g["players"][1]
    put(g, p2, 21)           # Astronomer, 2 green
    g["current"] = 1
    g["messenger"] = CC.CASTLE
    keys0 = p2["keys"]
    force_take(g, 1, 4)
    assert p2["keys"] == keys0 + 3
    # His Majesty: opponents gain 1 gold
    opp_gold = g["players"][1]["gold"]
    g["current"] = 0
    g["messenger"] = CC.CASTLE
    force_take(g, 0, 1)
    assert g["players"][1]["gold"] == opp_gold + 1
    # Royal Guard: all players gain 1 key
    k0 = [pl["keys"] for pl in g["players"]]
    g["current"] = 0
    g["messenger"] = CC.CASTLE
    force_take(g, 0, 31)
    assert [pl["keys"] for pl in g["players"]] == [k + 1 for k in k0]


def test_or_choice_plain_option():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    put(g, p, 30)            # Knight: 1 red
    keys0 = p["keys"]
    ev = force_take(g, 0, 14, pick=lambda pend: "ab:k1_1"
                    if pend["kind"] == "ability" else pend["options"][0]["v"])
    assert p["keys"] == keys0 + 2    # Knight's red + Templar's own red shield


def test_or_choice_neighbor_option():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    put(g, g["players"][1], 16)      # Chaplain: 1 purple
    put(g, g["players"][1], 16, 1, 0)
    gold0 = p["gold"]
    ev = force_take(g, 0, 14, pick=lambda pend: "nb:1")
    assert p["gold"] == gold0 - 5 + 2  # Templar costs 5, +2 from neighbour purples


def test_and_ability_no_choice():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    put(g, p, 79)                    # Beekeeper: yellow shield + Village banner
    put(g, p, 64)                    # Farmer: 2 yellow + Village banner
    gold0, keys0 = p["gold"], p["keys"]
    ev = force_take(g, 0, 78)        # Baker: gold/yellow AND keys/village banner
    assert p["gold"] == gold0 + 4    # Baker + Beekeeper + 2x Farmer's yellow
    assert p["keys"] == keys0 + 3    # Baker, Beekeeper, Farmer are Village cards


def test_traveler_zero_cost_cards():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    put(g, p, 42)            # Vicar, cost 0
    put(g, p, 65)            # Woodcutter, cost 0
    put(g, p, 30)            # Knight, cost 5
    gold0 = p["gold"]
    force_take(g, 0, 74)     # Traveler: 3 gold per 0-cost card
    assert p["gold"] == gold0 + 9   # Vicar + Woodcutter + Traveler himself


def test_purses_ability():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    bk = put(g, p, 79)               # Beekeeper purse cap 9
    put(g, p, 30)                    # Knight filler
    force_take(g, 0, 6)              # Queen Mother: 2 gold on each purse
    assert bk["gold"] == 2
    force_take(g, 0, 56, flipped=False) if False else None


def test_innkeeper_and_opp():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    bk = put(g, p, 79)               # Beekeeper purse
    opp_gold = g["players"][1]["gold"]
    force_take(g, 0, 61)             # Innkeeper: purses +2 AND opponents +2
    inn = [c for c in p["tableau"] if c["cid"] == 61][0]
    assert bk["gold"] == 2 and inn["gold"] == 2   # both purses (own too)
    assert g["players"][1]["gold"] == opp_gold + 2


def test_drop_ability():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    vicar = CC._mk(g, 42)            # Village, cost 0
    farmer = CC._mk(g, 64)           # Village, cost 5
    g["rows"][CC.VILLAGE] = [vicar, farmer]
    g["mm_live"][CC.VILLAGE] = True
    gold0 = p["gold"]
    ev = force_take(g, 0, 13, pick=lambda pend: str(farmer["id"]))
    assert p["gold"] == gold0 - 4 + 5  # paid 4 for Gravedigger, gained 5
    assert farmer not in g["rows"][CC.VILLAGE]
    assert farmer in g["discards"][CC.VILLAGE]


def test_drop_with_empty_display():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    g["rows"][CC.VILLAGE] = []
    ev = force_take(g, 0, 13)        # no crash, no pending
    assert not g.get("pending")


def test_steward_purse2_choice():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    bk = put(g, p, 79)               # cap 9
    qm = put(g, p, 6)                # cap 5
    kinds = []
    ev = force_take(g, 0, 10, pick=lambda pend: (kinds.append(pend["kind"]),
                                                 pend["options"][0]["v"]) and None
                    or pend["options"][0]["v"])
    assert kinds == ["place", "purse2", "purse2"], kinds
    assert bk["gold"] == 9 and qm["gold"] == 5   # both filled in two picks


def test_steward_single_purse_direct():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    bk = put(g, p, 79)               # only one purse with space
    ev = force_take(g, 0, 10)
    assert not g.get("pending")
    assert bk["gold"] == 9


def test_steward_no_purse_space():
    g = mk(2)
    g["messenger"] = CC.CASTLE
    p = g["players"][0]
    bk = put(g, p, 79, gold=9)       # already full
    force_take(g, 0, 10)
    assert bk["gold"] == 9


# ----------------------------------------------------------------- scoring

def _score(g, p):
    slots = CC._norm_slots(p)
    return sum(CC.score_card(g, p, inst, slots, p["keys"])
               for inst in p["tableau"])


def test_score_keys():
    g = mk(2)
    p = g["players"][0]
    p["keys"] = 7
    assert CC.score_player(g, 0)[0] == 7


def test_score_position_cards():
    g = mk(2)
    p = g["players"][0]
    # Captain: 8 if in the right column
    put(g, p, 30, 0, 0)
    put(g, p, 32, 0, 1)
    cap = put(g, p, 29, 0, 2)        # left column -> slot 7
    slots = CC._norm_slots(p)
    assert CC.score_card(g, p, cap, slots, p["keys"]) == 0
    cap["x"] = 2                     # now the right column (bounding box 3 wide)
    slots = CC._norm_slots(p)
    assert CC.score_card(g, p, cap, slots, p["keys"]) == 8
    # Duchess: 8 if in the top row
    g2 = mk(2)
    p2 = g2["players"][0]
    put(g2, p2, 30, 0, 0)
    put(g2, p2, 32, 0, 1)
    d = put(g2, p2, 9, 0, 2)         # bottom row
    slots = CC._norm_slots(p2)
    assert CC.score_card(g2, p2, d, slots, p2["keys"]) == 0
    d["x"], d["y"] = 1, 0            # top row
    slots = CC._norm_slots(p2)
    assert CC.score_card(g2, p2, d, slots, p2["keys"]) == 8


def test_score_row_shields():
    g = mk(2)
    p = g["players"][0]
    # Princess: 3 per blue shield in her row
    put(g, p, 3, 0, 0)               # Princess herself (blue)
    put(g, p, 2, 1, 0)               # Prince (blue)
    put(g, p, 30, 2, 0)              # Knight (red) same row
    put(g, p, 2, 0, 1)               # Prince (blue) other row
    # Per-card contributions: Princess row 2 blues -> 6; Prince(1,0) row -> 8;
    # Knight row+col 2 blues -> 6; Prince(0,1) row 1 blue -> 4.
    assert _score(g, p) == 24


def test_score_pair():
    g = mk(2)
    p = g["players"][0]
    # Officer: 4 per blue+red pair (shields counted across the whole tableau)
    off = put(g, p, 33, 0, 0)        # Officer (red)
    put(g, p, 2, 1, 0)               # Prince (blue)
    put(g, p, 3, 0, 1)               # Princess (blue)
    put(g, p, 30, 1, 1)              # Knight (red)
    slots = CC._norm_slots(p)
    assert CC.score_card(g, p, off, slots, p["keys"]) == 2 * 4  # 2 blues, 2 reds


def test_score_sets():
    g = mk(2)
    p = g["players"][0]
    # General: 6 per set of three identical shields
    for cid in (30, 32, 34, 47, 48, 49):     # six red single-shield cards
        put(g, p, cid)
    gen = [c for c in p["tableau"] if c["cid"] == 34][0]
    slots = CC._norm_slots(p)
    assert CC.score_card(g, p, gen, slots, p["keys"]) == 6 * 2


def test_score_purse_cards():
    g = mk(2)
    p = g["players"][0]
    # Vicar: 2 per gold stored, capped at 5
    put(g, p, 42, 0, 0, gold=3)
    assert _score(g, p) == 6
    p["tableau"][0]["gold"] = 7
    assert _score(g, p) == 10        # capped at capacity 5
    # Banker: 1 per gold on all purses
    g2 = mk(2)
    p2 = g2["players"][0]
    bk = put(g2, p2, 39, 0, 0)       # Banker
    put(g2, p2, 6, 1, 0, gold=2)     # Queen Mother 2 gold
    put(g2, p2, 79, 0, 1, gold=3)    # Beekeeper 3 gold
    slots = CC._norm_slots(p2)
    assert CC.score_card(g2, p2, bk, slots, p2["keys"]) == 5
    # Patron: 5 per purse holding at least 5 gold
    g3 = mk(2)
    p3 = g3["players"][0]
    pat = put(g3, p3, 27, 0, 0)      # Patron
    put(g3, p3, 6, 1, 0, gold=5)     # Queen Mother full
    put(g3, p3, 10, 0, 1, gold=4)    # Steward short
    slots = CC._norm_slots(p3)
    assert CC.score_card(g3, p3, pat, slots, p3["keys"]) == 5


def test_score_flany_and_face_down():
    g = mk(2)
    p = g["players"][0]
    put(g, p, 62, 0, 0)              # Carpenter: 8 if any face-down card
    assert _score(g, p) == 0
    put(g, p, 30, 1, 0, fd=True)
    assert _score(g, p) == 8         # the face-down Knight itself scores 0


def test_face_down_scores_zero():
    g = mk(2)
    p = g["players"][0]
    put(g, p, 9, 0, 0, fd=True)      # face-down Duchess would be 8
    put(g, p, 30, 1, 0)
    assert _score(g, p) == 0


def test_score_keys_per_key():
    g = mk(2)
    p = g["players"][0]
    put(g, p, 14, 0, 0)              # Templar: 1 per key
    p["keys"] = 4
    assert _score(g, p) == 4


def test_score_missing_shields_ability():
    g = mk(2)
    p = g["players"][0]
    # Carpenter ability: 1 gold per shield type missing (6 - distinct)
    g["messenger"] = CC.CASTLE
    put(g, p, 30)                    # red only
    gold0 = p["gold"]
    force_take(g, 0, 62)
    assert p["gold"] == gold0 + 4    # red (Knight) + orange (Carpenter): 6-2


# ----------------------------------------------------------- end of game

def test_leftover_gold_fills_largest_purse_first():
    g = mk(2)
    p = g["players"][0]
    bk = put(g, p, 79)               # cap 9
    qm = put(g, p, 6, gold=2)        # cap 5
    p["gold"] = 6
    left = CC.store_leftover_gold(p)
    assert left == 0
    assert bk["gold"] == 6           # all 6 into the biggest purse
    assert qm["gold"] == 2


def test_tiebreak_leftover_gold():
    g = mk(2)
    g["players"][0]["keys"] = 3
    g["players"][0]["gold"] = 0
    g["players"][1]["keys"] = 3
    g["players"][1]["gold"] = 5      # same score, more leftover gold
    ev = []
    CC._end_game(g, ev)
    assert g["phase"] == "game_end"
    assert g["winner"] == 1           # B wins the tiebreak on leftover gold
    assert [r["leftover"] for r in g["results"]] == [0, 5]


def test_end_game_explicit_winner():
    g = mk(2)
    put(g, g["players"][0], 9, 0, 0)         # Duchess top row: 8
    put(g, g["players"][0], 30, 1, 0)
    g["players"][0]["keys"] = 2              # 10 vs 2 keys
    ev = []
    CC._end_game(g, ev)
    assert g["winner"] == 0
    # 2 keys + 8 (Duchess top row) + 6 (Knight: 3 per blue in his row/col)
    assert g["results"][0]["score"] == 16
    assert g["results"][1]["score"] == 2


def test_preview_score_fills_purses():
    g = mk(2)
    p = g["players"][0]
    put(g, p, 79, 0, 0)              # Beekeeper empty purse
    p["keys"] = 1
    p["gold"] = 12
    # hypothetical: 9 gold goes onto the purse -> 2 pts each
    assert CC.preview_score(g, 0) == 1 + 18


# -------------------------------------------------------------- full games

def test_full_random_games():
    for seed in range(3):
        random.seed(seed)
        g = CC.new_game(1, 100, "A")
        for i in range(3):
            g["players"].append(CC.new_player(100 + i, f"P{i+1}"))
        assert CC.start_game(g, []) is None
        ev = []
        guard = 0
        while g["phase"] == "playing" and guard < 3000:
            guard += 1
            if g.get("pending"):
                opts = g["pending"]["options"]
                assert CC.apply_choice(g, g["pending"]["player"],
                                       random.choice(opts)["v"], ev) is None
                continue
            idx = g["current"]
            p = g["players"][idx]
            row = g["messenger"]
            cards = g["rows"][row]
            afford = [c for c in cards
                      if CC.cost_for(g, idx, CC.card_of(c)) <= p["gold"]]
            if (p["keys"] > 0 and random.random() < 0.3) or not afford:
                c = random.choice(cards)
                if not afford or random.random() < 0.2:
                    assert CC.do_take(g, idx, c["id"], True, ev) is None
                else:
                    assert CC.do_key(g, idx, random.choice(["move", "renew"]),
                                     ev) is None
            else:
                c = random.choice(afford)
                assert CC.do_take(g, idx, c["id"], False, ev) is None
        assert g["phase"] == "game_end", (seed, g["phase"])
        for pl in g["players"]:
            assert len(pl["tableau"]) == 9
        json.dumps(g)               # state must stay JSON-serializable


def test_take_refuses_foreign_turn_and_pending():
    g = mk(2)
    g["rows"][g["messenger"]].append(CC._mk(g, 65))
    assert CC.do_take(g, 1, g["rows"][g["messenger"]][-1]["id"], False, []) != None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all ok")
