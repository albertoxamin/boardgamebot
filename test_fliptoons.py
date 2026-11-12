"""Run: python3 test_fliptoons.py"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fliptoons as F


def mk(n=3, seed=1):
    random.seed(seed)
    g = F.new_game(1, 1, "A")
    for i in range(2, n + 1):
        g["players"].append({"user_id": i, "name": chr(64 + i), "deck": [], "grid": [],
                             "extra": [], "discarded": [], "fame": 0, "fame_bonus": 0,
                             "bonus_actions": 0, "actions": 0, "last_placed": None,
                             "ostrich_queue": [], "eagle_pending": False,
                             "after_flip": [], "in_flip": False})
    assert F.start_game(g, []) is None
    g["active"] = list(range(n))
    return g


def T(g, p, r):
    return F._mk(g, r)


def FDD(g, r):
    c = F._mk(g, r)
    c["fd"] = True
    return c


def FD(g, p, r):
    return F._mk(g, r, None, True)


def ST(g, s):
    def f(g2=None, p=None, r=None):
        return F._mk(g2, 0, s)
    return f


def put(g, p, slot, insts):
    p["grid"][slot] = insts


def _all_grid(p):
    return [c for st in p["grid"] for c in st]


def force_flip(g, decks):
    """Stage a clean flip phase with fixed deck orders (last item flips first)."""
    g["stage"] = "flip"
    g["flip_list"] = list(range(len(g["players"])))
    g["flip_pos"] = 0
    g["pending"] = None
    g["pending_q"] = []
    g["market"] = [None] * 5          # deterministic camel/dog conditions
    g["toon_deck"] = list(g["toon_deck"])
    for i, p in enumerate(g["players"]):
        p["deck"] = decks[i] if i < len(decks) else []
        p["grid"] = [[] for _ in range(6)]
        p["extra"] = []
        p["discarded"] = []
        p["fame_bonus"] = 0
        p["bonus_actions"] = 0
        p["ostrich_queue"] = []
        p["eagle_pending"] = False
        p["after_flip"] = []
        p["last_placed"] = None
        p["in_flip"] = i < len(decks)   # only scripted players flip


def drain_flip(g):
    """Run advance() until the market phase or a pending needs input."""
    ev = []
    while g["phase"] == "playing" and g["stage"] == "flip":
        if g.get("pending"):
            return g["pending"]
        F.advance(g, ev)
    return None


def test_setup():
    g = mk(3)
    assert len(g["toon_deck"]) == 53 - 5        # 5 toons dealt to the market
    start = F.STARTER_NAMES
    for p in g["players"]:
        names = sorted(F.STARTER_NAMES[c["s"]] for c in _all_grid(p) if c["s"] is not None)
        assert names == ["Bee", "Caterpillar", "Caterpillar", "Dragonfly", "Skunk", "Snail"], names
    assert len(g["market"]) == 5 and all(g["market"])
    ranks = [c["r"] for c in g["market"]]
    assert ranks == sorted(ranks)
    assert g["phase"] == "playing" and g["round"] == 1


def test_lobby_board():
    random.seed(0)
    g = F.new_game(1, 1, "A")
    p = g["players"][0]
    assert p["grid"] == [[] for _ in range(6)]
    assert F.grid_fame(g, p) == 0
    p["grid"] = []                    # legacy saved lobby state: no grid yet
    assert F.grid_fame(g, p) == 0


def test_stall_breaker():
    g = mk(3)
    g["stage"] = "cleanup"
    g["toon_deck"] = [F._mk(g, 1)]     # deck not empty: covered by "no progress"
    for _ in range(7):
        g["acted"] = False
        F._cleanup(g, [])
        assert not g["end_triggered"]
    g["acted"] = False
    F._cleanup(g, [])
    assert g["end_triggered"]
    F._cleanup(g, [])                 # the triggered Final Flip starts next cleanup
    assert g["stage"] == "final_flip"
    # a round with a market action keeps resetting the counter
    g2 = mk(3)
    g2["stage"] = "cleanup"; g2["toon_deck"] = [F._mk(g2, 1)]
    for _ in range(20):
        g2["acted"] = True
        F._cleanup(g2, [])
        assert not g2["end_triggered"] and g2["stall"] == 0


def test_renato_12_fame():
    g = mk(2)
    # Rulebook example: cat | sheep(top-mid) | cat / dragonfly | bee | camel = 12
    g["market"] = [T(g, g["players"][0], 7), T(g, g["players"][0], 13),
                   T(g, g["players"][0], 19), T(g, g["players"][0], 21),
                   T(g, g["players"][0], 24)]  # no camels anywhere
    p = g["players"][0]
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [F._mk(g, 0, F.CATERPILLAR)])
    put(g, p, 1, [T(g, p, 7)])
    put(g, p, 2, [F._mk(g, 0, F.CATERPILLAR)])
    put(g, p, 3, [F._mk(g, 0, F.DRAGONFLY)])
    put(g, p, 4, [F._mk(g, 0, F.BEE)])
    put(g, p, 5, [T(g, p, 8)])  # camel
    assert F.grid_fame(g, p) == 12, F.grid_fame(g, p)


def test_positional_fames():
    g = mk(2)
    g["market"] = [T(g, g["players"][0], 7), T(g, g["players"][0], 13),
                   T(g, g["players"][0], 19), T(g, g["players"][0], 21),
                   T(g, g["players"][0], 24)]
    p = g["players"][0]
    p["grid"] = [[] for _ in range(6)]
    # donkey: 1 + 5 in bottom row (slot 3)
    put(g, p, 3, [T(g, p, 3)])
    assert F.grid_fame(g, p) == 6
    put(g, p, 3, [T(g, p, 6)]); assert F.grid_fame(g, p) == 1   # goat bottom row -> no +3
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [T(g, p, 6)]); assert F.grid_fame(g, p) == 4   # goat top row +3
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 1, [T(g, p, 7)]); assert F.grid_fame(g, p) == 5   # sheep center column
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [T(g, p, 7)]); assert F.grid_fame(g, p) == 1   # sheep off-column
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 2, [T(g, p, 8)]); assert F.grid_fame(g, p) == 4   # camel 2+2 (none elsewhere)
    put(g, p, 2, [T(g, p, 15)]); assert F.grid_fame(g, p) == 6   # alligator
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [T(g, p, 24), FDD(g, 5)])
    assert F.grid_fame(g, p) == 2                               # bear 1+1 (itself); face-down dog 0
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [T(g, p, 23)])
    assert F.grid_fame(g, p) == 8                               # deer 3+5 (single unique name)


def test_bear_rooster_cat_tiger():
    g = mk(2)
    g["market"] = [None] * 5
    p = g["players"][0]
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [T(g, p, 24), T(g, p, 13)])    # bear + rooster
    assert F.grid_fame(g, p) == 4               # bear 3 (1+2 face-ups), rooster 1 (only itself <=13)
    p["discarded"] = [F._mk(g, 0, F.BEE), F._mk(g, 0, F.SNAIL), T(g, p, 8)]
    assert F.grid_fame(g, p) == 4               # cat/tiger absent -> discarded list irrelevant
    # tiger alone: 3 + dismissed count (starters count as any dismissed card)
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [T(g, p, 22)])
    assert F.grid_fame(g, p) == 6
    # cat: 1 + dismissed starters (2)
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [T(g, p, 14)])
    assert F.grid_fame(g, p) == 3
    # rooster: +1 per rank<=13 face-up incl itself
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [T(g, p, 13)])                 # rooster + camel(2)
    put(g, p, 1, [T(g, p, 19)])                 # peacock rank 19 not counted
    assert F.grid_fame(g, p) == 1 + 5           # rooster (only itself <=13), peacock 5
    # lion: 3 (+4 if ALL adjacent face-up rank<=16)
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 1, [T(g, p, 16)])
    put(g, p, 0, [T(g, p, 8)]), put(g, p, 2, [T(g, p, 13)])
    assert F.grid_fame(g, p) == 4 + 2 + 7      # lion 3+4, camel 2, rooster 2... rooster 7? recount below
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [T(g, p, 16)])                 # lion with peacock adjacent (19>16) -> no bonus
    put(g, p, 1, [T(g, p, 19)])
    assert F.grid_fame(g, p) == 3 + 5
    # cow copies max adjacent computed fame
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 1, [T(g, p, 7)])                  # sheep center col = 5
    put(g, p, 4, [T(g, p, 25)])                 # cow adjacent to slot 1
    assert F.grid_fame(g, p) == 10
    # skunk 0, snail 2
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [F._mk(g, 0, F.SKUNK)])
    put(g, p, 1, [F._mk(g, 0, F.SNAIL)])
    assert F.grid_fame(g, p) == 2


def test_ostrich_stack():
    g = mk(3)
    p = g["players"][0]
    force_flip(g, [[T(g, p, 13), T(g, p, 1), T(g, p, 8)]])
    assert drain_flip(g) is None                # flip completes, no pending
    assert [c["r"] for c in p["grid"][0]] == [8]
    assert [c["r"] for c in p["grid"][1]] == [1, 13], p["grid"][1]  # camel stacks on ostrich
    assert p["fame"] == 1 + 4 + 3               # ostrich 1, camel 2+2, rooster counts 3 (<=13)


def test_rabbit_turkey_eagle_elephant():
    g = mk(3)
    p = g["players"][0]
    # eagle (rank 2) flips the NEXT placed card face-down
    force_flip(g, [[T(g, p, 8), T(g, p, 2)]])
    drain_flip(g)
    assert [c["r"] for c in p["grid"][0]] == [2] and not p["grid"][0][0]["fd"]
    assert [c["r"] for c in p["grid"][1]] == [8] and p["grid"][1][0]["fd"]
    # elephant flips the last placed card
    force_flip(g, [[T(g, p, 12), T(g, p, 7)]])
    drain_flip(g)
    assert [c["r"] for c in p["grid"][0]] == [7] and p["grid"][0][0]["fd"]
    assert [c["r"] for c in p["grid"][1]] == [12]
    # turkey stacks on the last placed card
    force_flip(g, [[T(g, p, 20), T(g, p, 7), T(g, p, 8)]])
    drain_flip(g)
    assert [c["r"] for c in p["grid"][0]] == [8]
    assert [c["r"] for c in p["grid"][1]] == [7, 20], p["grid"]


def test_monkey_row():
    g = mk(3)
    p = g["players"][0]
    force_flip(g, [[T(g, p, 8), T(g, p, 17)]])   # monkey flips first, climbs from slot 0
    drain_flip(g)
    assert [c["r"] for c in p["grid"][0]] == [8]
    assert len(p["grid"][0]) == 1 and p["grid"][1] == []
    assert len(p["extra"]) == 1 and [c["r"] for c in p["extra"][0]["cards"]] == [17]
    assert p["extra"][0]["below"] == 0


def test_snake():
    g = mk(3)
    p = g["players"][0]
    g["toon_deck"] = list(g["toon_deck"]) + [T(g, p, 19)]   # snake stacks deck top
    force_flip(g, [[T(g, p, 1), T(g, p, 11), T(g, p, 8)]])
    assert drain_flip(g) is None
    # snake dismissed the deck top (ostrich) and stacked peacock on itself
    snakes = [st for st in p["grid"] if any(c["r"] == 11 for c in st)]
    assert snakes and [c["r"] for c in snakes[0]] == [11, 19]
    assert p["fame_bonus"] == 2 and p["bonus_actions"] == 1


def test_market_hire_and_pendings():
    g = mk(2)
    ev = []
    p = g["players"][0]
    for q in g["players"]:
        q["grid"] = [[] for _ in range(6)]
        q["extra"] = []
        q["pending_q"] = []
    g["pending"] = None
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [F._mk(g, 0, F.CATERPILLAR)])
    put(g, p, 1, [F._mk(g, 0, F.BEE)])
    put(g, p, 2, [F._mk(g, 0, F.BEE)])
    put(g, p, 3, [F._mk(g, 0, F.CATERPILLAR)])
    put(g, p, 4, [F._mk(g, 0, F.SNAIL)])
    put(g, p, 5, [F._mk(g, 0, F.SKUNK)])
    p["fame"] = 20      # rich: no skunk trigger, enough for all hires
    g["players"][1]["fame"] = 0
    g["market"] = [T(g, p, 19), T(g, p, 4), T(g, p, 10), T(g, p, 18), T(g, p, 25)]
    g["toon_deck"] = [T(g, p, 8), T(g, p, 8), T(g, p, 8), T(g, p, 8), T(g, p, 8)] + g["toon_deck"]
    g["stage"] = "market"; g["market_idx"] = 0
    g["flip_list"] = []; g["flip_pos"] = 0
    F._start_market_player(g, ev)
    assert p["actions"] == 2
    # hire peacock (price 3): +2 fame, +1 bonus action
    assert F.do_market(g, 0, "hire", "0", ev) is None
    assert p["fame_bonus"] == 2 and p["bonus_actions"] == 1 and p["actions"] == 2
    assert g["pending"] is None
    # hire butterfly (price 4): pending to dismiss a caterpillar
    assert F.do_market(g, 0, "hire", "1", ev) is None
    assert g["pending"] and g["pending"]["kind"] == "butterfly"
    cid = str(next(c["id"] for st in p["grid"] for c in st if c["s"] == F.CATERPILLAR))
    before = sum(len(s) for s in p["grid"])
    assert F.apply_choice(g, 0, cid, ev) is None
    assert sum(len(s) for s in p["grid"]) == before - 1
    assert g["pending"] is None or g["pending"]["kind"] != "butterfly"
    # hire horse (price 7): pending discard market cards
    p["actions"] = 2; p["fame"] = 30
    g["market_idx"] = 0
    assert F.do_market(g, 0, "hire", "2", ev) is None
    assert g["pending"] and g["pending"]["kind"] == "horse"
    assert F.apply_choice(g, 0, "done", ev) is None
    # hire pig (price 10): pending deck choice; pig must not duplicate
    p["actions"] = 2
    p["fame"] = 30
    tot0 = sum(len(pp["deck"]) + len(F._all_grid_cards(pp)) for pp in g["players"]) + \
        len(g["toon_deck"]) + len(g["toon_discard"]) + sum(1 for c in g["market"] if c)
    assert F.do_market(g, 0, "hire", "3", ev) is None
    assert g["pending"] and g["pending"]["kind"] == "pig"
    assert F.apply_choice(g, 0, "own", ev) is None
    tot1 = sum(len(pp["deck"]) + len(F._all_grid_cards(pp)) for pp in g["players"]) + \
        len(g["toon_deck"]) + len(g["toon_discard"]) + sum(1 for c in g["market"] if c)
    assert tot1 == tot0
    assert p["deck"][-1]["r"] == 18 and sum(1 for d in p["deck"] if d["r"] == 18) == 1
    # hire cow (price 15)
    p["actions"] = 2; p["fame"] = 30; g["market_idx"] = 0
    assert F.do_market(g, 0, "hire", "4", ev) is None
    assert p["fame"] == 15 and g["pending"] is None     # cow costs 15


def test_market_poor_and_skip():
    g = mk(2)
    ev = []
    p = g["players"][0]
    p["fame"] = 1
    g["market"] = [T(g, p, 8), None, None, None, None]
    g["stage"] = "market"; g["market_idx"] = 0
    assert F.do_market(g, 0, "hire", "0", ev) == "not enough fame (costs 3)"
    assert F.do_market(g, 0, "skip", None, ev) is None


def test_2p_discard_and_depletion():
    g = mk(2, seed=5)
    ev = []
    td0 = len(g["toon_deck"])
    g["market"] = [T(g, g["players"][0], r) for r in (8, 7, 3, 6, 1)]
    g["toon_deck"] = [T(g, g["players"][0], r) for r in (13, 13)]
    g["stage"] = "market"; g["market_idx"] = 1
    g["players"][1]["actions"] = 0
    F._finish_market_player(g, ev)
    # leftmost + rightmost discarded, refilled from the 2-card deck
    assert len(g["toon_discard"]) == 2
    assert len(g["market"]) == 5 and all(g["market"])
    ranks = [c["r"] for c in g["market"]]
    assert ranks == sorted(ranks)
    assert len(g["toon_deck"]) == 0
    # now market drains on further 2p discards -> depletion trigger
    g["market_idx"] = 1; g["players"][1]["actions"] = 0
    F._finish_market_player(g, ev)
    assert [c["r"] if c else None for c in g["market"]] == [None, None, 6, 7, 13]
    for _ in range(2):
        g["market_idx"] = 1; g["players"][1]["actions"] = 0
        F._finish_market_player(g, ev)
    assert g["end_triggered"]
    assert not any(g["market"])


def test_depletion_and_final_flip():
    g = mk(3, seed=7)
    ev = []
    for p in g["players"]:
        p["deck"] = []
        p["grid"] = [[] for _ in range(6)]
        p["extra"] = []
    g["market"] = [None] * 5
    g["toon_deck"] = []
    g["end_triggered"] = True
    g["stage"] = "cleanup"
    F._cleanup(g, ev)
    assert g["stage"] == "final_flip"
    F.advance(g, ev)
    assert g["phase"] == "game_end"   # everyone empty: fame 0 tie x10 -> draw
    assert g["winner"] is None


def test_fame_30_triggers_end():
    g = mk(3, seed=9)
    ev = []
    p = g["players"][0]
    g["market"] = [None] * 5
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [T(g, p, 21)]); put(g, p, 1, [T(g, p, 8)])
    put(g, p, 2, [T(g, p, 12)]); put(g, p, 3, [T(g, p, 15)])
    put(g, p, 4, [T(g, p, 15)]); put(g, p, 5, [T(g, p, 10)])
    assert F.grid_fame(g, p) == 3 + 4 + 7 + 6 + 6 + 4   # bull camel elephant gator gator horse
    F._check_fame(g, ev)
    assert g["end_triggered"] and g["critic_holder"] == 0
    g["stage"] = "cleanup"
    F._cleanup(g, ev)
    assert g["stage"] == "final_flip"
    while g["phase"] == "playing":
        F.advance(g, ev)
        if g.get("pending"):
            F.apply_choice(g, g["pending"]["player"], g["pending"]["options"][0]["v"], ev)
    assert g["phase"] == "game_end" and g["winner"] is not None


def test_skunk_pending():
    g = mk(2, seed=3)
    ev = []
    p = g["players"][0]
    p["grid"] = [[] for _ in range(6)]
    put(g, p, 0, [F._mk(g, 0, F.SKUNK)])
    put(g, p, 1, [F._mk(g, 0, F.BEE)])
    put(g, p, 2, [F._mk(g, 0, F.CATERPILLAR)])
    p["fame"] = F.grid_fame(g, p)
    o = g["players"][1]
    o["grid"] = [[] for _ in range(6)]
    put(g, o, 0, [T(g, o, 8)]); put(g, o, 1, [T(g, o, 21)])
    o["fame"] = F.grid_fame(g, o)
    assert p["fame"] < o["fame"]
    g["stage"] = "market"; g["market_idx"] = 0
    F._start_market_player(g, ev)
    assert g["pending"] and g["pending"]["kind"] == "skunk"
    n0 = sum(len(s) for s in p["grid"])
    assert F.apply_choice(g, 0, g["pending"]["options"][0]["v"], ev) is None
    assert sum(len(s) for s in p["grid"]) == n0 - 1
    assert p["actions"] == 2     # skunk dismissal is free
    # tie in least fame -> nobody
    g["pending"] = None; g["pending_q"] = []
    o["fame"] = p["fame"]
    F._start_market_player(g, ev)
    assert g["pending"] is None or g["pending"]["kind"] != "skunk"


def test_full_random_games():
    for npl in (2, 3, 4):
        for seed in (0, 1, 2):
            random.seed(seed)
            ev = []
            g = F.new_game(1, 11, "A")
            for k in range(npl - 1):
                g["players"].append({"user_id": 100 + k, "name": f"P{k+2}", "deck": [],
                                     "grid": [], "extra": [], "discarded": [], "fame": 0,
                                     "fame_bonus": 0, "bonus_actions": 0, "actions": 0,
                                     "last_placed": None, "ostrich_queue": [],
                                     "eagle_pending": False, "after_flip": [], "in_flip": False})
            assert F.start_game(g, ev) is None
            iters = 0
            while g["phase"] == "playing" and iters < 30000:
                iters += 1
                assert F.advance(g, ev)
                if g.get("pending"):
                    opts = g["pending"]["options"]
                    assert F.apply_choice(g, g["pending"]["player"],
                                          random.choice(opts)["v"], ev) is None
                    continue
                assert g["stage"] == "market", g["stage"]
                idx = g["market_idx"]; p = g["players"][idx]
                acts = []
                for slot, c in enumerate(g["market"]):
                    if c and F.PRICES[slot] <= p["fame"] + p["fame_bonus"]:
                        acts.append(("hire", str(slot)))
                tot = len(p["deck"]) + len(F._all_grid_cards(p))
                for cell in F._reading_cells(p):
                    for c in F._stack_at(p, cell):
                        cost = 3 if c["s"] == F.CATERPILLAR else 5
                        if not c["fd"] and c["r"] not in F.UNDISMISSABLE and tot >= 4 \
                           and cost <= p["fame"] + p["fame_bonus"]:
                            acts.append(("dismiss", str(c["id"])))
                if acts and random.random() < 0.3:
                    assert F.do_market(g, idx, *random.choice(acts), ev) is None
                else:
                    assert F.do_market(g, idx, "skip", None, ev) is None
            assert g["phase"] == "game_end", (npl, seed, g["round"], g["stage"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all ok")
