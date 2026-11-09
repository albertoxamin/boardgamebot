"""Regicide engine - pure logic (co-op vs 12 royals, 1-4 players official;
Telegram: 2-4). Rules: official Regicide rulebook (Badgers from Mars).

Castle: 4 Jacks (atk10/hp20) on 4 Queens (15/30) on 4 Kings (20/40), top Jack face-up = enemy.
Tavern: 2-10 (each suit) + 4 Aces (=1) + Jesters by players (1p:0, 2p:0, 3p:1, 4p:2).
Hand limit: 1p:8, 2p:7, 3p:6, 4p:5. Deal to max. Win: defeat last King. Lose: cannot
cover enemy attack discard, or cannot play/yield.
Turn (4 steps): 1) play card/combo/yield, 2) suit power, 3) damage/check defeat,
4) suffer discard. Play: single card; same-number combo sum<=10; Ace (1) alone or
paired with one non-Jester card; Jester alone. Values: J=10 Q=15 K=20 in hand.
Powers (mandatory, immunity blocks own suit): Hearts heal X from discard under Tavern
(shuffle, X facedown under, rest faceup); Diamonds draw X clockwise from active,
skipping full hands; Clubs double this play's damage; Spades shield enemy attack by X
cumulative until enemy falls. Hearts before Diamonds on multi-suit plays.
Defeat: damage>=hp cumulative -> enemy discard (exact ==hp -> facedown on Tavern top),
played cards -> discard, next castle card, killer immediately plays again (no attack).
Jester (0 atk, alone): cancels immunity, no damage, no enemy attack, chooser picks next.
Enemy attack: effective = atk - spade_shield; active player discards cards one at a
time until discard total >= effective (A=1, Jester=0, royal recruited=10/15/20);
cannot cover -> team loses. Yield: skip turn; cannot yield if all others just yielded.
"""
import random

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
ROYAL = {"J": (10, 20), "Q": (15, 30), "K": (20, 40)}
JESTERS = {1: 0, 2: 0, 3: 1, 4: 2}
HAND_LIMIT = {1: 8, 2: 7, 3: 6, 4: 5}


def card_value(c):
    if c["rank"] == "Jester":
        return 0
    return ROYAL[c["rank"]][0] if c["rank"] in ROYAL else (1 if c["rank"] == "A" else int(c["rank"]))


def card_str(c):
    return "Jester" if c["rank"] == "Jester" else f"{c['rank']}{c['suit']}"


def name_of_rg(g, user_id):
    for p in g["players"]:
        if p["user_id"] == user_id:
            return p["name"]
    return "?"


def build_tavern(nplayers):
    deck = [{"suit": s, "rank": r} for s in SUITS for r in RANKS[1:10]]  # 2-10
    deck += [{"suit": s, "rank": "A"} for s in SUITS]
    deck += [{"suit": "Joker", "rank": "Jester"} for _ in range(JESTERS.get(nplayers, 0))]
    random.shuffle(deck)
    return deck


def build_castle():
    castle = []
    for rank in ("K", "Q", "J"):  # kings bottom, jacks top
        pile = [{"suit": s, "rank": rank} for s in SUITS]
        random.shuffle(pile)
        castle = pile + castle if rank == "K" else castle + pile if rank == "J" else castle
    # simpler: kings first (bottom), then queens, then jacks (top)
    kings = [{"suit": s, "rank": "K"} for s in SUITS]
    queens = [{"suit": s, "rank": "Q"} for s in SUITS]
    jacks = [{"suit": s, "rank": "J"} for s in SUITS]
    for p in (kings, queens, jacks):
        random.shuffle(p)
    return kings + queens + jacks  # pop() draws jacks first


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [{"user_id": int(creator_id), "name": creator_name, "hand": []}],
        "phase": "lobby",  # lobby|playing|discard|jester_next|won|lost
        "castle": [], "tavern": [], "discard": [],
        "enemy": None, "enemy_damage": 0, "spade_shield": 0, "immune_off": False,
        "played": [],  # cards played against current enemy (public)
        "current_index": 0, "yields": 0, "kills": 0, "board_message_id": None,
        "chat_type": "private",
    }


def hand_limit(g):
    return HAND_LIMIT.get(len(g["players"]), 5)


def start_game(g, events):
    n = len(g["players"])
    if n < 2 or n > 4:
        return "Regicide needs 2-4 players"
    g["castle"] = build_castle()
    g["tavern"] = build_tavern(n)
    g["discard"] = []
    g["enemy"] = g["castle"].pop()
    g["enemy_damage"] = 0
    g["spade_shield"] = 0
    g["immune_off"] = False
    g["played"] = []
    g["yields"] = 0
    g["kills"] = 0
    for p in g["players"]:
        p["hand"] = [g["tavern"].pop() for _ in range(hand_limit(g))]
    g["current_index"] = 0
    g["phase"] = "playing"
    events.append(f"⚔️ Regicide started with {n} players! Enemy: {card_str(g['enemy'])} "
                  f"(atk {ROYAL[g['enemy']['rank']][0]} hp {ROYAL[g['enemy']['rank']][1]}). "
                  f"Hand limit {hand_limit(g)}.")
    return None


def enemy_stats(g):
    return ROYAL[g["enemy"]["rank"]]


def effective_attack(g):
    atk, _ = enemy_stats(g)
    return max(0, atk - g["spade_shield"])


def validate_play(cards):
    """Returns (ok, error). cards: list of card dicts from one hand."""
    if not cards:
        return False, "no card"
    if any(c["rank"] == "Jester" for c in cards):
        return (len(cards) == 1, "Jester must be played alone")
    if len(cards) == 1:
        return True, ""
    if any(c["rank"] == "A" for c in cards):
        return (len(cards) == 2 and sum(1 for c in cards if c["rank"] == "A") == 1,
                "Ace pairs with exactly one other card")
    if len({c["rank"] for c in cards}) == 1:
        total = sum(card_value(c) for c in cards)
        return (total <= 10, f"combo sums to {total} (>10)")
    return False, "combo must be same number (sum<=10) or Ace+one card"


def draw_cards(g, count, start_index, events):
    drawn = 0
    n = len(g["players"])
    i = start_index
    while drawn < count and g["tavern"]:
        if len(g["players"][i]["hand"]) < hand_limit(g):
            g["players"][i]["hand"].append(g["tavern"].pop())
            drawn += 1
        i = (i + 1) % n
        if drawn < count and all(len(p["hand"]) >= hand_limit(g) for p in g["players"]):
            break
    if drawn:
        events.append(f"♦️ {drawn} card(s) drawn.")


def play_cards(g, idx, cards, events):
    """Play cards (already removed from hand by caller validation of ownership).
    Appends to g['played'], resolves powers/damage/attack. Returns error or None."""
    ok, err = validate_play(cards)
    if not ok:
        return err
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    enemy = g["enemy"]
    # Jester
    if cards[0]["rank"] == "Jester":
        g["played"].append(cards[0])
        g["immune_off"] = True
        g["jester_player"] = idx
        g["yields"] = 0
        events.append("🃏 Jester: immunity cancelled, no enemy attack. Jester player picks who goes next.")
        g["phase"] = "jester_next"
        return None
    total_val = sum(card_value(c) for c in cards)
    suits_present = []
    for c in cards:
        if c["suit"] not in suits_present:
            suits_present.append(c["suit"])
    immune = (enemy["suit"] in suits_present) and not g["immune_off"]
    # Powers, Hearts before Diamonds; Spades/Clubs modify later steps.
    for suit in ("♥", "♦"):
        if suit not in suits_present or (immune and suit == enemy["suit"]):
            continue
        if suit == "♥":
            random.shuffle(g["discard"])
            n_back = min(total_val, len(g["discard"]))
            under = [g["discard"].pop() for _ in range(n_back)]
            g["tavern"] = g["tavern"] + under  # face-down under tavern (bottom)
            events.append(f"♥️ Heal: {n_back} card(s) back under Tavern.")
        if suit == "♦":
            draw_cards(g, total_val, idx, events)
    # Spades shield (cumulative, immune blocks)
    if "♠" in suits_present and not (immune and "♠" == enemy["suit"]):
        g["spade_shield"] += total_val
        events.append(f"♠ Shield +{total_val} (total shield {g['spade_shield']}).")
    # Damage (clubs double, immune blocks)
    dmg = total_val * 2 if ("♣" in suits_present and not (immune and "♣" == enemy["suit"])) else total_val
    g["played"].extend(cards)
    g["enemy_damage"] += dmg
    _, hp = enemy_stats(g)
    events.append(f"⚔️ {g['players'][idx]['name']} plays {'+'.join(card_str(c) for c in cards)} "
                  f"for {dmg} damage (enemy {g['enemy_damage']}/{hp}).")
    g["yields"] = 0
    if g["enemy_damage"] >= hp:
        exact = g["enemy_damage"] == hp
        if exact:
            g["tavern"].append(enemy)  # facedown on top of tavern (pop end)
            events.append(f"💛 Exact kill! {card_str(enemy)} goes on top of Tavern as an ally.")
        else:
            g["discard"].append(enemy)
            events.append(f"☠️ {card_str(enemy)} defeated (discarded).")
        g["discard"].extend(g["played"])
        g["played"] = []
        g["kills"] += 1
        if not g["castle"]:
            g["phase"] = "won"
            g["enemy"] = None
            events.append("🏆 All 12 royals defeated - the team wins!")
            return None
        g["enemy"] = g["castle"].pop()
        g["enemy_damage"] = 0
        g["spade_shield"] = 0
        g["immune_off"] = False
        events.append(f"👑 Next enemy: {card_str(g['enemy'])} - {g['players'][idx]['name']} plays again.")
        return None  # same player, no enemy attack
    # Enemy attacks: active player must discard, unless shield covers it fully
    eff = effective_attack(g)
    if eff == 0:
        g["discard_needed"] = 0
        g["discard_total"] = 0
        g["current_index"] = (idx + 1) % len(g["players"])
        g["phase"] = "playing"
        events.append(f"🛡️ Shield covers the attack from {card_str(enemy)} (0) - no discard. "
                      f"Turn passes to {g['players'][g['current_index']]['name']}.")
        return None
    g["phase"] = "discard"
    g["discard_needed"] = eff
    g["discard_total"] = 0
    events.append(f"💥 {card_str(enemy)} attacks for {g['discard_needed']} - "
                  f"{g['players'][idx]['name']} must discard card(s) worth ≥{g['discard_needed']}.")
    return None


def discard_cards(g, idx, cards, events):
    """Discard one or more cards at once during enemy attack. Returns error or None."""
    if g["phase"] != "discard":
        return "not in discard phase"
    if idx != g["current_index"]:
        return "only the attacked player discards"
    if not cards:
        return "select at least one card to discard"
    g["discard_total"] += sum(card_value(c) for c in cards)
    g["discard"].extend(cards)
    events.append(f"🗑 {g['players'][idx]['name']} discards "
                  f"{', '.join(card_str(c) for c in cards)} "
                  f"({g['discard_total']}/{g['discard_needed']}).")
    if g["discard_total"] >= g["discard_needed"]:
        g["current_index"] = (idx + 1) % len(g["players"])
        g["phase"] = "playing"
    elif not g["players"][idx]["hand"]:
        g["phase"] = "lost"
        events.append("💀 Cannot cover the attack - the team loses.")
    return None


def discard_card(g, idx, card, events):
    """One discard step during enemy attack. Returns error or None."""
    return discard_cards(g, idx, [card], events)


def yield_turn(g, idx, events):
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    if g["yields"] >= len(g["players"]):
        return "cannot yield - everyone already yielded"
    g["yields"] += 1
    events.append(f"⏭ {g['players'][idx]['name']} yields.")
    g["current_index"] = (idx + 1) % len(g["players"])
    return None


def jester_next(g, idx, events):
    if g["phase"] != "jester_next":
        return "not after a Jester"
    # idx is the newly chosen current player (any player, incl. jester player)
    g["current_index"] = idx
    g["phase"] = "playing"
    events.append(f"🎯 {g['players'][idx]['name']} goes next.")
    return None
