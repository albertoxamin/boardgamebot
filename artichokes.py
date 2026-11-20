"""Abandon All Artichokes (Gamewright, 2020) pure game engine.

2-4 players. Each starts with a personal deck of 10 Artichokes and a hand
of 5. The shared Garden Stack is 6 copies of each of the 10 vegetables;
the top 5 face-up cards form the Garden Row. On a turn: replenish the
row (4+ matching cards are shuffled back), harvest 1 row card, play any
number of vegetables (each resolves its printed power), discard the rest
of your hand, then draw 5. If that final hand has no Artichokes you win.

Rules verified against the official Gamewright rulebook and the Board
Game Arena rules summary (BGA "Gamehelpabandonallartichokes"). Corn is
played with an Artichoke; both go to the player's discard. Beet's "short
hand" rule is implicit: hands are only refilled at the end of your own
turn. Card powers needing choices are exposed as a `pending` choice with
`apply_choice`, so Telegram buttons and the Mini App share the exact same
server-side validation.
"""
import random
from collections import Counter

MIN_PLAYERS = 2
MAX_PLAYERS = 4
HAND_SIZE = 5
ARTICHOKE = "artichoke"
VEGGIES = ("beet", "broccoli", "carrot", "corn", "eggplant",
           "leek", "onion", "peas", "pepper", "potato")
ICONS = {
    "artichoke": "🥬", "beet": "🍠", "broccoli": "🥦", "carrot": "🥕",
    "corn": "🌽", "eggplant": "🍆", "leek": "🧄", "onion": "🧅",
    "peas": "🫛", "pepper": "🌶️", "potato": "🥔",
}
DESCRIPTIONS = {
    "beet": "You and an opponent each reveal a random card. Compost both if Artichokes, otherwise swap them.",
    "broccoli": "Compost an Artichoke, if your hand has three or more Artichokes.",
    "carrot": "As your only play action, compost exactly two Artichokes along with this card.",
    "corn": "Play this card with an Artichoke. Then put a card from the Garden Row on top of your Deck.",
    "eggplant": "Compost an Artichoke, along with this card. All players pass two cards to the left.",
    "leek": "Reveal the top card of an opponent's Deck. Put it into your hand or on top of their Discard Pile.",
    "onion": "Compost an Artichoke. Put this card on top of another player's Discard Pile.",
    "peas": "Reveal two cards from the Garden Stack. Put one on your Discard pile, the other on an opponent's.",
    "pepper": "Put a card from your Discard Pile on top of your Deck.",
    "potato": "Reveal the top card of your Deck. Compost if Artichoke, otherwise discard it.",
    "artichoke": "Don't break my heart!",
    "rhubarb": "Compost this card to refresh the Garden Row, then harvest a card. (Place old cards under Garden Stack.)",
}


def card_name(card):
    return card["v"].capitalize()


def card_label(card):
    return f"{ICONS.get(card['v'], '🥬')} {card_name(card)}"


def card_desc(card):
    return DESCRIPTIONS.get(card["v"], "")


def new_player(user_id, name):
    return {
        "user_id": int(user_id), "name": name, "deck": [], "hand": [],
        "discard": [], "npc": False,
    }


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [new_player(creator_id, creator_name)],
        "phase": "lobby", "current_index": 0, "round": 0,
        "garden_stack": [], "garden_row": [], "compost": [],
        "pending": None, "play_done": False, "iid": 0,
        "winner_id": None, "board_message_id": None,
    }


def name_of(g, user_id):
    for p in g["players"]:
        if p["user_id"] == user_id:
            return p["name"]
    return "?"


def _mk(g, v):
    g["iid"] += 1
    return {"id": g["iid"], "v": v}


def artichokes(p):
    return sum(1 for c in p["hand"] if c["v"] == ARTICHOKE)


def _take_artichoke(p):
    for i, c in enumerate(p["hand"]):
        if c["v"] == ARTICHOKE:
            return p["hand"].pop(i)
    return None


def _compost(g, card):
    g["compost"].append(card)


def _discard(p, card):
    p["discard"].append(card)


def _find_card(p, card_id):
    for i, c in enumerate(p["hand"]):
        if c["id"] == card_id:
            return i
    return None


def replenish_row(g, events):
    for _ in range(8):
        while len(g["garden_row"]) < 5 and g["garden_stack"]:
            g["garden_row"].append(g["garden_stack"].pop())
        counts = Counter(c["v"] for c in g["garden_row"])
        if counts and max(counts.values()) >= 4 and g["garden_stack"]:
            g["garden_stack"].extend(g["garden_row"])
            g["garden_row"] = []
            random.shuffle(g["garden_stack"])
            events.append("🌱 Four or more matching vegetables in the garden row - reshuffled!")
            continue
        return


def _draw_to(p, n):
    while len(p["hand"]) < n:
        if p["deck"]:
            p["hand"].append(p["deck"].pop())
        elif p["discard"]:
            p["deck"] = p["discard"]
            p["discard"] = []
            random.shuffle(p["deck"])
        else:
            break


def _ensure_deck(p):
    if not p["deck"] and p["discard"]:
        p["deck"] = p["discard"]
        p["discard"] = []
        random.shuffle(p["deck"])
    return bool(p["deck"])


def _opponents(g, idx, need="hand"):
    out = []
    for i, p in enumerate(g["players"]):
        if i == idx:
            continue
        if need == "any" or (need == "hand" and p["hand"]) or (need == "deck" and (p["deck"] or p["discard"])):
            out.append(i)
    return out


def _remove_id(p, card_id):
    for i, c in enumerate(p["hand"]):
        if c["id"] == card_id:
            return p["hand"].pop(i)
    return None


def _opts(g, indexes):
    return [{"v": i, "label": g["players"][i]["name"]} for i in indexes]


def start_game(g, events):
    if len(g["players"]) < MIN_PLAYERS:
        return f"need at least {MIN_PLAYERS} players"
    if len(g["players"]) > MAX_PLAYERS:
        return f"too many players (max {MAX_PLAYERS})"
    g["iid"] = 0
    g["garden_stack"] = []
    g["garden_row"] = []
    g["compost"] = []
    for _ in range(6):
        for v in VEGGIES:
            g["garden_stack"].append(_mk(g, v))
    random.shuffle(g["garden_stack"])
    for p in g["players"]:
        p["deck"] = [_mk(g, ARTICHOKE) for _ in range(10)]
        p["hand"] = []
        p["discard"] = []
        random.shuffle(p["deck"])
    for p in g["players"]:
        _draw_to(p, HAND_SIZE)
    g["current_index"] = random.randrange(len(g["players"]))
    g["round"] = 1
    g["phase"] = "harvest"
    g["pending"] = None
    g["play_done"] = False
    g["winner_id"] = None
    replenish_row(g, events)
    events.append(f"🥬 Round 1 - {g['players'][g['current_index']]['name']} goes first. Harvest a vegetable!")
    return None


def harvest(g, idx, row_pos, events):
    if g["phase"] != "harvest":
        return "you cannot harvest right now"
    if idx != g["current_index"]:
        return "not your turn"
    if not isinstance(row_pos, int) or not 0 <= row_pos < len(g["garden_row"]):
        return "pick a garden row card"
    p = g["players"][idx]
    card = g["garden_row"].pop(row_pos)
    p["hand"].append(card)
    g["phase"] = "play"
    events.append(f"{p['name']} harvested {card_label(card)}.")
    return None


def skip_harvest(g, idx, events):
    if g["phase"] != "harvest":
        return "you cannot skip harvesting now"
    if idx != g["current_index"]:
        return "not your turn"
    if g["garden_row"]:
        return "you must harvest a garden row card"
    g["phase"] = "play"
    events.append("🌱 The garden row is empty - nothing to harvest.")
    return None


def _play_error(g, idx, card):
    if g["phase"] != "play":
        return "you cannot play cards right now"
    if idx != g["current_index"]:
        return "not your turn"
    if g["pending"] is not None:
        return "finish the current action first"
    if g["play_done"]:
        return "Carrot was your only play action"
    v = card["v"]
    if v == ARTICHOKE:
        return "you cannot play an Artichoke"
    p = g["players"][idx]
    if v == "broccoli" and artichokes(p) < 3:
        return "Broccoli needs 3 Artichokes in your hand"
    if v == "carrot" and artichokes(p) < 2:
        return "Carrot needs 2 Artichokes in your hand"
    if v == "corn":
        if artichokes(p) < 1:
            return "Corn needs an Artichoke in your hand"
        if not g["garden_row"]:
            return "Corn needs a card in the garden row"
    if v in ("eggplant", "onion") and artichokes(p) < 1:
        return f"{card_name(card)} needs an Artichoke in your hand"
    if v == "beet" and not _opponents(g, idx):
        return "Beet needs an opponent with cards"
    if v == "leek" and not _opponents(g, idx, "deck"):
        return "Leek needs an opponent with a deck or discard"
    if v == "pepper" and not p["discard"]:
        return "Pepper needs a card in your discard pile"
    if v == "peas" and not g["garden_stack"]:
        return "Peas needs cards in the garden stack"
    if v == "potato" and not (p["deck"] or p["discard"]):
        return "Potato needs a deck or discard pile"
    return None


def playable(g, idx):
    if g["phase"] != "play" or idx != g["current_index"] or g["pending"] or g["play_done"]:
        return []
    return [c["id"] for c in g["players"][idx]["hand"] if not _play_error(g, idx, c)]


def _pending(g, kind, idx, card, options, prompt, **data):
    pend = {"kind": kind, "by": idx, "card": card,
            "options": options, "prompt": prompt}
    pend.update(data)
    g["pending"] = pend


def do_play(g, idx, card_id, events):
    err = None
    pos = None
    if g["phase"] != "play" or idx != g["current_index"]:
        return "not your turn"
    if g["pending"] is not None:
        return "finish the current action first"
    if g["play_done"]:
        return "Carrot was your only play action"
    pos = _find_card(g["players"][idx], card_id)
    if pos is None:
        return "card not in your hand"
    card = g["players"][idx]["hand"][pos]
    err = _play_error(g, idx, card)
    if err:
        return err
    g["players"][idx]["hand"].pop(pos)
    v = card["v"]
    p = g["players"][idx]
    if v == "beet":
        _pending(g, "beet", idx, card, _opts(g, _opponents(g, idx)),
                 "Beet: choose an opponent to compare a random card with.")
    elif v == "broccoli":
        _compost(g, _take_artichoke(p))
        _discard(p, card)
        events.append(f"{p['name']} composted an Artichoke with Broccoli.")
    elif v == "carrot":
        _compost(g, _take_artichoke(p))
        _compost(g, _take_artichoke(p))
        _compost(g, card)
        g["play_done"] = True
        events.append(f"🥕 {p['name']} composted two Artichokes and the Carrot - last action!")
    elif v == "corn":
        _discard(p, _take_artichoke(p))
        _pending(g, "corn", idx, card,
                 [{"v": i, "label": card_label(c)} for i, c in enumerate(g["garden_row"])],
                 "Corn: choose a garden row card to put on top of your deck.")
    elif v == "eggplant":
        _compost(g, _take_artichoke(p))
        _compost(g, card)
        order = list(range(len(g["players"])))
        g["pending"] = {"kind": "eggplant", "order": order, "pos": 0,
                        "answers": {}, "prompt": "Eggplant: everyone passes up to two cards to the left."}
        events.append(f"🍆 {p['name']} composted an Artichoke with Eggplant - everyone passes two cards left!")
        _eggplant_next(g, events)
    elif v == "leek":
        _pending(g, "leek", idx, card, _opts(g, _opponents(g, idx, "deck")),
                 "Leek: choose an opponent's deck to reveal.")
    elif v == "onion":
        _compost(g, _take_artichoke(p))
        _pending(g, "onion", idx, card, _opts(g, _opponents(g, idx, "any")),
                 "Onion: choose an opponent to receive this Onion.")
    elif v == "pepper":
        _pending(g, "pepper", idx, card,
                 [{"v": c["id"], "label": card_label(c)} for c in p["discard"]],
                 "Pepper: choose a card from your discard to put on top of your deck.")
    elif v == "peas":
        revealed = [g["garden_stack"].pop() for _ in range(min(2, len(g["garden_stack"])))]
        _pending(g, "peas", idx, card, _opts(g, _opponents(g, idx, "any")),
                 "Peas: choose an opponent to send one of the revealed cards to.",
                 revealed=revealed)
        events.append(f"🫛 {p['name']} revealed " + " and ".join(card_label(c) for c in revealed) + ".")
    elif v == "potato":
        if not _ensure_deck(p):
            return "Potato needs a deck or discard pile"
        top = p["deck"].pop()
        if top["v"] == ARTICHOKE:
            _compost(g, top)
            events.append(f"🥔 {p['name']} composted an Artichoke with Potato.")
        else:
            p["discard"].append(top)
            events.append(f"🥔 {p['name']} turned up {card_label(top)} and discarded it.")
        _discard(p, card)
    return None


def _eggplant_next(g, events):
    pend = g["pending"]
    while pend["pos"] < len(pend["order"]) and not g["players"][pend["order"][pend["pos"]]]["hand"]:
        pend["pos"] += 1
    if pend["pos"] >= len(pend["order"]):
        for i, ids in pend["answers"].items():
            taken = []
            for c in g["players"][i]["hand"][:]:
                if c["id"] in ids:
                    taken.append(c)
                    g["players"][i]["hand"].remove(c)
            left = (i + 1) % len(g["players"])
            g["players"][left]["hand"].extend(taken)
        events.append("🍆 Cards were passed to the player on the left.")
        g["pending"] = None
        return
    who = pend["order"][pend["pos"]]
    pend["options"] = [{"v": c["id"], "label": card_label(c)} for c in g["players"][who]["hand"]]
    pend["by"] = who
    need = min(2, len(g["players"][who]["hand"]))
    word = "one card" if need == 1 else "two cards"
    pend["prompt"] = f"Pass {word} to {g['players'][(who + 1) % len(g['players'])]['name']}."


def apply_choice(g, idx, choice, events):
    pend = g["pending"]
    if pend is None:
        return "nothing to choose"
    kind = pend["kind"]
    if kind == "eggplant":
        if idx != pend.get("by"):
            return "not your choice"
        need = min(2, len(g["players"][idx]["hand"]))
        picks = choice if isinstance(choice, list) else [choice]
        if len(picks) != need:
            return "choose the right number of cards"
        if len(set(picks)) != len(picks):
            return "duplicate card"
        hand_ids = [c["id"] for c in g["players"][idx]["hand"]]
        if any(c not in hand_ids for c in picks):
            return "card not in your hand"
        pend["answers"][idx] = picks
        pend["pos"] += 1
        _eggplant_next(g, events)
        return None
    if idx != pend["by"]:
        return "not your choice"
    valid = [o["v"] for o in pend["options"]]
    if choice not in valid:
        return "invalid choice"
    p = g["players"][idx]
    card = pend["card"]
    if kind == "beet":
        target = g["players"][choice]
        if not p["hand"] or not target["hand"]:
            events.append("🍠 Not enough cards to swap - the Beet fizzles.")
            _discard(p, card)
            g["pending"] = None
            return None
        mine = random.randrange(len(p["hand"]))
        theirs = random.randrange(len(target["hand"]))
        a = p["hand"][mine]
        b = target["hand"][theirs]
        p["hand"][mine] = b
        target["hand"][theirs] = a
        if a["v"] == ARTICHOKE and b["v"] == ARTICHOKE:
            _remove_id(p, b["id"])
            _remove_id(target, a["id"])
            _compost(g, a)
            _compost(g, b)
            events.append(f"🍠 {p['name']} and {target['name']} both drew Artichokes - both composted!")
        else:
            events.append(f"🍠 {p['name']} drew {card_label(b)}, {target['name']} drew {card_label(a)} - swapped.")
        _discard(p, card)
        g["pending"] = None
    elif kind == "corn":
        row = g["garden_row"].pop(choice)
        p["deck"].insert(0, row)
        _discard(p, card)
        events.append(f"🌽 {p['name']} put {card_label(row)} on top of their deck.")
        g["pending"] = None
    elif kind == "leek":
        if "revealed" not in pend:
            target = g["players"][choice]
            if not _ensure_deck(target):
                return "that player has no deck or discard"
            revealed = target["deck"].pop()
            pend["revealed"] = revealed
            pend["target"] = choice
            pend["options"] = [{"v": "hand", "label": "Take it into your hand"},
                               {"v": "discard", "label": "Put it on their discard pile"}]
            pend["prompt"] = f"Leek revealed {card_label(revealed)}. Where does it go?"
            events.append(f"🧅 {p['name']} revealed {card_label(revealed)} from {target['name']}'s deck.")
            return None
        revealed = pend["revealed"]
        target = g["players"][pend["target"]]
        if choice == "hand":
            p["hand"].append(revealed)
            events.append(f"{p['name']} took the revealed card into their hand.")
        else:
            target["discard"].append(revealed)
            events.append(f"{p['name']} put the revealed card on {target['name']}'s discard pile.")
        _discard(p, card)
        g["pending"] = None
    elif kind == "onion":
        target = g["players"][choice]
        target["discard"].append(card)
        events.append(f"🧅 {p['name']} sent the Onion to {target['name']}'s discard pile.")
        g["pending"] = None
    elif kind == "pepper":
        for i, c in enumerate(p["discard"]):
            if c["id"] == choice:
                got = p["discard"].pop(i)
                p["deck"].insert(0, got)
                break
        _discard(p, card)
        events.append(f"🌶️ {p['name']} put {card_label(got)} on top of their deck.")
        g["pending"] = None
    elif kind == "peas":
        if "target" not in pend:
            pend["target"] = choice
            if len(pend["revealed"]) == 1:
                g["players"][choice]["discard"].append(pend["revealed"][0])
                _discard(p, card)
                events.append(f"🫛 The revealed card went to {g['players'][choice]['name']}'s discard pile.")
                g["pending"] = None
                return None
            pend["options"] = [{"v": c["id"], "label": card_label(c)} for c in pend["revealed"]]
            pend["prompt"] = "Peas: which card goes on your discard pile?"
            return None
        got = None
        for c in pend["revealed"]:
            if c["id"] == choice:
                got = c
        other = next(c for c in pend["revealed"] if c["id"] != choice)
        p["discard"].append(got)
        g["players"][pend["target"]]["discard"].append(other)
        _discard(p, card)
        events.append(f"🫛 {p['name']} kept {card_label(got)}; {card_label(other)} went to {g['players'][pend['target']]['name']}.")
        g["pending"] = None
    return None


def end_turn(g, idx, events):
    if g["phase"] != "play":
        return "you cannot end your turn now"
    if idx != g["current_index"]:
        return "not your turn"
    if g["pending"] is not None:
        return "finish the current action first"
    p = g["players"][idx]
    p["discard"].extend(p["hand"])
    p["hand"] = []
    _draw_to(p, HAND_SIZE)
    names = ", ".join(card_label(c) for c in p["hand"]) or "an empty hand"
    if not any(c["v"] == ARTICHOKE for c in p["hand"]):
        g["phase"] = "game_end"
        g["winner_id"] = p["user_id"]
        events.append(f"🏆 {p['name']} draws {names} and shouts ABANDON ALL ARTICHOKES!")
        return None
    events.append(f"{p['name']} refreshed to {names}.")
    g["round"] += 1
    g["current_index"] = (idx + 1) % len(g["players"])
    g["play_done"] = False
    g["phase"] = "harvest"
    replenish_row(g, events)
    events.append(f"🌱 Round {g['round']} - {g['players'][g['current_index']]['name']} harvests a vegetable.")
    return None
