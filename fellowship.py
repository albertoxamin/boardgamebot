"""The Fellowship of the Ring - Trick-Taking Game engine.

Pure logic, no Telegram, no I/O. State is plain JSON-serialisable data and
every move validates phase, turn and ownership. Rules from the Office Dog
rulebook: 37-card main deck (Hills/Mountains/Forests/Shadows 1-8, Rings 1-5),
one face-up lost card, private hands, must-follow trick-taking, Rings cannot be
led until broken, and the 1 of Rings may optionally win any trick. Each chapter
has characters with goals; everyone must succeed for the group to win.
"""
import random

MIN_PLAYERS = 2
MAX_PLAYERS = 4

SUITS = ("Hill", "Mountain", "Forest", "Shadow", "Ring")
LETTERS = {"Hill": "H", "Mountain": "M", "Forest": "F", "Shadow": "S", "Ring": "R"}
BY_LETTER = {v: k for k, v in LETTERS.items()}
MAX_RANK = {"Hill": 8, "Mountain": 8, "Forest": 8, "Shadow": 8, "Ring": 5}
PLURAL = {"Hill": "Hills", "Mountain": "Mountains", "Forest": "Forests",
          "Shadow": "Shadows", "Ring": "Rings"}


def make_deck():
    return [LETTERS[s] + str(n) for s in SUITS for n in range(1, MAX_RANK[s] + 1)]


def suit(card):
    return BY_LETTER[card[0]]


def rank(card):
    return int(card[1:])


def cname(card):
    return f"{rank(card)} of {PLURAL[suit(card)]}"


def cshort(card):
    return f"{rank(card)}{suit(card)[0].upper()}"


# Character goals are (kind, parameter). goal_text() turns these into the
# public text shown on the board and in the Mini App.
CHARACTERS = {
    "frodo": {"name": "Frodo", "epithet": "Ring-bearer",
              "goal": ("rings_min", None), "exchange": (), "keep_one": False,
              "setup": "Takes the 1 of Rings and leads the first trick; cannot exchange the One Ring."},
    "bilbo": {"name": "Bilbo", "epithet": "Peculiar",
              "goal": ("tricks_min", 3), "exchange": (), "keep_one": False, "setup": "None."},
    "gandalf": {"name": "Gandalf", "epithet": "Grey Wizard",
                "goal": ("tricks_min", 1), "exchange": ("frodo",), "keep_one": True,
                "setup": "Takes the lost card, then exchanges 1 card with Frodo. Keeps 1 card at the end."},
    "pippin": {"name": "Pippin", "epithet": "Fool",
               "goal": ("fewest", None), "exchange": ("frodo", "sam", "merry"),
               "keep_one": False, "setup": "Exchanges 1 card with Frodo, Sam or Merry."},
    "sam": {"name": "Sam", "epithet": "Gardener",
            "goal": ("threat_hill", None), "exchange": ("frodo", "merry", "pippin"),
            "keep_one": False, "setup": "Draws a Black Rider threat, then exchanges 1 card."},
    "merry": {"name": "Merry", "epithet": "Stout Heart",
              "goal": ("tricks_range", (1, 2)), "exchange": (), "keep_one": False,
              "setup": "None."},
    "gildor": {"name": "Gildor Inglorion", "epithet": "High Elf",
               "goal": ("forest_last", None), "exchange": (), "keep_one": False,
               "setup": "None. Must play a Forest card in the final trick."},
    "maggot": {"name": "Farmer Maggot", "epithet": "Brave",
               "goal": ("threat_rank_two", None), "exchange": (), "keep_one": False,
               "setup": "Draws a threat; must win two cards of that rank."},
    "fatty": {"name": "Fatty Bolger", "epithet": "Cautious",
              "goal": ("last_trick", True), "exchange": ("frodo",), "keep_one": True,
              "setup": "Exchanges with Frodo; stops playing near the end of the round."},
    "tom": {"name": "Tom Bombadil", "epithet": "The Master",
            "goal": ("tricks_min", 2), "exchange": (), "keep_one": True,
            "setup": "Keeps cards left over at the end of the round."},
    "goldberry": {"name": "Goldberry", "epithet": "River's Daughter",
                  "goal": ("tricks_consecutive", 3), "exchange": (), "keep_one": False,
                  "setup": "Must win exactly three consecutive tricks."},
    "barliman": {"name": "Barliman Butterbur", "epithet": "Innkeeper",
                 "goal": ("tricks_last_three", None), "exchange": (), "keep_one": False,
                 "setup": "Must win one of the final three tricks."},
    "underhill": {"name": "Mr. Underhill", "epithet": "Hidden",
                  "goal": ("tricks_min", 1), "exchange": (), "keep_one": False,
                  "setup": "Not considered Frodo for other cards."},
    "strider": {"name": "Strider", "epithet": "Secretive",
                "goal": ("avoid_threat", None), "exchange": (), "keep_one": False,
                "setup": "Draws a threat; must NOT win exactly that many tricks."},
    "aragorn": {"name": "Aragorn", "epithet": "Elessar",
                "goal": ("threat_tricks", None), "exchange": ("gimli",), "keep_one": False,
                "setup": "Draws a threat; must win exactly that many tricks. Exchanges with Gimli."},
    "legolas": {"name": "Legolas", "epithet": "Son of Thranduil",
                "goal": ("suit_cards", ("Forest", 2)), "exchange": ("gimli",),
                "keep_one": False, "setup": "Exchanges with Gimli; wins Forest cards."},
    "gimli": {"name": "Gimli", "epithet": "Durin's Folk",
              "goal": ("suit_cards", ("Mountain", 2)), "exchange": ("legolas",),
              "keep_one": False, "setup": "Exchanges with Legolas; wins Mountain cards."},
    "boromir": {"name": "Boromir", "epithet": "Captain of Gondor",
                "goal": ("last_trick", True), "exchange": (), "keep_one": False,
                "setup": "Must win the final trick and must never take the 1 of Rings."},
    "bill": {"name": "Bill the Pony", "epithet": "Faithful",
             "goal": ("tricks_exact", 1), "exchange": (), "keep_one": False,
             "setup": "Passes a card to Frodo and a card to Sam."},
    "glorfindel": {"name": "Glorfindel", "epithet": "Rider of Rivendell",
                   "goal": ("tricks_min", 2), "exchange": (), "keep_one": True,
                   "setup": "Has one card left at the end of the round."},
    "elrond": {"name": "Elrond", "epithet": "Lord of Rivendell",
               "goal": ("tricks_min", 2), "exchange": ("frodo",), "keep_one": False,
               "setup": "Exchanges with Frodo; his goal is in addition to the others'."},
    "gollum": {"name": "Gollum", "epithet": "Sneaky",
               "goal": ("rings_min", {"2": 4, "3": 4, "4": 2}), "exchange": (),
               "keep_one": False, "setup": "Wants Rings cards."},
    "arwen": {"name": "Arwen", "epithet": "Evenstar",
              "goal": ("suit_most", "Forest"), "exchange": (), "keep_one": False,
              "setup": "Must win more Forest cards than any other character (no ties)."},
    "gloin": {"name": "Glóin", "epithet": "Durin's Folk",
              "goal": ("suit_most", "Mountain"), "exchange": (), "keep_one": False,
              "setup": "Must win more Mountain cards than any other character (no ties)."},
    "shadowfax": {"name": "Shadowfax", "epithet": "Lord of Horses",
                  "goal": ("suit_cards", ("Shadow", 2)), "exchange": (), "keep_one": False,
                  "setup": "Wins tricks containing Shadow cards."},
    "radagast": {"name": "Radagast", "epithet": "The Brown",
                 "goal": ("suit_cards", ("Forest", 2)), "exchange": (), "keep_one": False,
                 "setup": "Wins tricks containing Forest cards."},
    "galadriel": {"name": "Galadriel", "epithet": "Lady of Lórien",
                  "goal": ("rings_min", {"2": 3, "3": 3, "4": 2}), "exchange": (),
                  "keep_one": False, "setup": "Wants Rings cards."},
    "celeborn": {"name": "Celeborn", "epithet": "Lord of Lórien",
                 "goal": ("suit_cards", ("Forest", 3)), "exchange": (), "keep_one": False,
                 "setup": "Wins Forest cards."},
}

# Black Rider / threat ranks used in the early chapters.
THREAT_DECKS = {2: [1, 2, 3, 4], 3: [1, 2, 3, 4], 8: [1, 2, 3, 4],
                9: [1, 2, 3, 4], 13: list(range(1, 8))}

# Chapter rosters follow the printed chapter cards where known (1, 2, 13).
# Later chapters use the same core rules with the chapter's character mix.
CHAPTERS = [
    (1, "A Long-expected Party", ("frodo", "bilbo", "gandalf", "pippin"), ("frodo", "bilbo"), "short"),
    (2, "A Little Delay in the Shire", ("frodo", "sam", "merry", "gandalf", "pippin"), ("frodo", "sam", "merry"), "short"),
    (3, "The Ring Sets Out", ("frodo", "gildor", "maggot", "gandalf", "pippin"), ("frodo",), "short"),
    (4, "Conspiracy in Crickhollow", ("frodo", "fatty", "merry", "pippin", "gandalf"), ("frodo", "fatty"), "short"),
    (5, "The Old Forest", ("frodo", "tom", "merry", "pippin"), ("frodo", "tom"), "short"),
    (6, "Fog on the Barrow-downs", ("frodo", "tom", "goldberry", "merry", "pippin"), ("frodo", "goldberry"), "short"),
    (7, "At the Sign of the Prancing Pony", ("underhill", "barliman", "merry", "pippin"), ("barliman",), "short"),
    (8, "Strider", ("frodo", "strider", "merry", "pippin", "gandalf"), ("frodo", "strider"), "short"),
    (9, "Flight to the Ford", ("frodo", "strider", "glorfindel", "merry", "pippin"), ("frodo", "strider"), "long"),
    (10, "Many Meetings", ("frodo", "elrond", "gandalf", "legolas", "gimli"), ("frodo", "elrond"), "short"),
    (11, "The Council of Elrond", ("frodo", "boromir", "aragorn", "legolas", "gimli"), ("frodo", "boromir"), "long"),
    (12, "The Ring Goes South", ("frodo", "gandalf", "aragorn", "boromir"), ("frodo",), "short"),
    (13, "The Ring Goes South", ("frodo", "gandalf", "aragorn", "legolas", "gimli", "boromir", "sam", "merry", "pippin", "bill"), ("frodo",), "long"),
    (14, "The Mines of Moria", ("frodo", "gandalf", "legolas", "gimli", "boromir"), ("frodo",), "long"),
    (15, "The Bridge of Khazad-dûm", ("frodo", "gimli", "legolas", "boromir"), ("frodo", "gimli"), "short"),
    (16, "Lothlórien", ("frodo", "galadriel", "celeborn", "legolas", "gimli"), ("frodo",), "long"),
    (17, "The Forest of Lothlórien", ("frodo", "arwen", "gloin", "legolas", "gimli"), ("frodo",), "long"),
    (18, "The Breaking of the Fellowship", ("frodo", "sam", "merry", "pippin", "aragorn", "boromir", "legolas", "gimli"), ("frodo", "sam"), "long"),
]


def chapter(n):
    for ch in CHAPTERS:
        if ch[0] == n:
            return {"n": ch[0], "title": ch[1], "roster": list(ch[2]),
                    "required": list(ch[3]), "victory": ch[4],
                    "threats": list(THREAT_DECKS.get(n, []))}
    return None


def chapter_name(n):
    ch = chapter(n)
    return f"{n}. {ch['title']}" if ch else str(n)


def new_player(user_id, name):
    return {"user_id": user_id, "name": name, "npc": False, "hand": [],
            "won": [], "trick_wins": [], "character": None, "threat": None}


def new_game(chat_id, creator_id, creator_name, chapter_n=1):
    return {"chat_id": chat_id, "created_by": creator_id, "chat_type": "private",
            "phase": "lobby", "chapter": max(1, min(18, int(chapter_n))),
            "round": 1, "players": [new_player(creator_id, creator_name)],
            "lost": None, "ring_holder": 0, "ring_broken": False,
            "selection_order": [], "selection_pos": 0, "setup_queue": [],
            "pending": None, "leader": 0, "current": 0, "trick": None,
            "trick_no": 0, "last_plays": [], "completed": [], "result": None,
            "board_message_id": None}


def _rng():
    return random.SystemRandom()


def _deal(g, events, chapter_n=None):
    """Shuffle, remove the lost card, deal hands and assign the Ring holder."""
    if chapter_n is not None:
        g["chapter"] = max(1, min(18, int(chapter_n)))
    ch = chapter(g["chapter"])
    deck = make_deck()
    deck.remove("R1")
    _rng().shuffle(deck)
    # The One Ring is never the lost card: reserve it for a hand.
    g["lost"] = deck.pop()
    deck.append("R1")
    _rng().shuffle(deck)
    n = len(g["players"])
    size = 9 if n == 4 else 12
    for p in g["players"]:
        p["hand"] = sorted([deck.pop() for _ in range(size)])
        p["won"] = []
        p["trick_wins"] = []
        p["character"] = None
        p["threat"] = None
    # With only two human players the printed rules add a third "pyramid" hand.
    # Keep the game two-handed: move the Ring into a real hand if it was undealt.
    if not any("R1" in p["hand"] for p in g["players"]):
        holder = _rng().randrange(n)
        dst = _rng().randrange(len(g["players"][holder]["hand"]))
        swapped = g["players"][holder]["hand"][dst]
        g["players"][holder]["hand"][dst] = "R1"
        deck[deck.index("R1")] = swapped
        g["players"][holder]["hand"].sort()
    g["ring_holder"] = next(i for i, p in enumerate(g["players"]) if "R1" in p["hand"])
    g["ring_broken"] = False
    g["trick"] = None
    g["trick_no"] = 0
    g["last_plays"] = []
    g["result"] = None
    g["pending"] = None
    g["leader"] = g["ring_holder"]
    g["current"] = g["ring_holder"]
    g["phase"] = "choosing"
    # Frodo is forced onto whoever holds the One Ring.
    if ch and "frodo" in ch["roster"]:
        g["players"][g["ring_holder"]]["character"] = "frodo"
    g["selection_order"] = [i for i in _order_from(g, g["ring_holder"])
                            if not g["players"][i]["character"]]
    g["selection_pos"] = 0
    g["setup_queue"] = []
    events.append(f"🃏 Chapter {g['chapter']}: <b>{html_safe(ch['title']) if ch else '?'}</b> "
                  f"— lost card: {cname(g['lost'])}.")
    events.append(f"💍 Ring-bearer: <b>{html_safe(g['players'][g['ring_holder']]['name'])}</b> "
                  "(leads the first trick).")
    _auto(g, events)


def html_safe(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _order_from(g, idx):
    n = len(g["players"])
    return [(idx + k) % n for k in range(n)]


def start_game(g, events, chapter_n=None):
    if g.get("phase") != "lobby":
        return "game already started"
    if not MIN_PLAYERS <= len(g["players"]) <= MAX_PLAYERS:
        return f"need {MIN_PLAYERS}-{MAX_PLAYERS} players"
    if chapter_n is not None:
        try:
            n = int(chapter_n)
        except (TypeError, ValueError):
            return "bad chapter number"
        if chapter(n) is None:
            return "no such chapter (1-18)"
    _deal(g, events, chapter_n)
    return None


def retry_round(g, events):
    if g.get("phase") not in ("round_end", "chapter_end"):
        return "round is not over"
    _deal(g, events)
    return None


def restart_chapter(g, events):
    if g.get("phase") not in ("round_end", "chapter_end"):
        return "round is not over"
    g["completed"] = []
    events.append(f"🔁 Chapter {g['chapter']} restarted.")
    _deal(g, events)
    return None


def next_chapter(g, events):
    if g.get("phase") != "chapter_end":
        return "chapter is not complete"
    if g["chapter"] >= len(CHAPTERS):
        g["phase"] = "game_end"
        events.append("🏆 The Fellowship is complete! Play on with /fotr_chapter for any chapter.")
        return None
    g["chapter"] += 1
    g["completed"] = []
    g["phase"] = "lobby"
    events.append(f"📖 Next chapter: {chapter_name(g['chapter'])}. Anyone may start.")
    return None


def set_chapter(g, n, events):
    if g.get("phase") not in ("lobby", "round_end", "chapter_end", "game_end"):
        return "finish the current round first"
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "bad chapter number"
    if chapter(n) is None:
        return "no such chapter (1-18)"
    g["chapter"] = n
    g["completed"] = []
    g["result"] = None
    g["phase"] = "lobby"
    events.append(f"📖 Chapter set to {chapter_name(n)}. Start when ready.")
    return None


# ---------- character selection and setup ----------
def selection_actor(g):
    if g.get("phase") != "choosing":
        return None
    order = g.get("selection_order") or []
    if g.get("selection_pos", 0) >= len(order):
        return None
    return order[g["selection_pos"]]


def available_characters(g):
    ch = chapter(g["chapter"])
    if not ch:
        return []
    used = {p["character"] for p in g["players"] if p["character"]}
    return [c for c in ch["roster"] if c not in used]


def choose_character(g, idx, key, events):
    if selection_actor(g) != idx:
        return "not your turn to choose"
    ch = chapter(g["chapter"])
    if key not in available_characters(g):
        return "character not available"
    left = len(g["selection_order"]) - g["selection_pos"] - 1
    # A required character still unchosen must be picked by a remaining seat.
    unchosen_required = [r for r in ch["required"]
                         if r not in {p["character"] for p in g["players"]} and r != key]
    if len(unchosen_required) > left:
        return f"a required character must still be chosen ({', '.join(CHARACTERS[r]['name'] for r in unchosen_required)})"
    g["players"][idx]["character"] = key
    g["selection_pos"] += 1
    events.append(f"🎭 {html_safe(g['players'][idx]['name'])} is <b>{CHARACTERS[key]['name']}</b> "
                  f"({CHARACTERS[key]['epithet']}).")
    if selection_actor(g) is None:
        _begin_setup(g, events)
    _auto(g, events)
    return None


def _begin_setup(g, events):
    ch = chapter(g["chapter"])
    missing = [r for r in ch["required"] if r not in {p["character"] for p in g["players"]}]
    if missing:
        # Should not happen thanks to validation, but never leave a broken round.
        free = [i for i, p in enumerate(g["players"]) if not p["character"]]
        for i, r in zip(free, missing):
            g["players"][i]["character"] = r
            events.append(f"🎭 {html_safe(g['players'][i]['name'])} takes required <b>{CHARACTERS[r]['name']}</b>.")
    g["phase"] = "setup"
    start = (g["ring_holder"] + 1) % len(g["players"]) if "frodo" in ch["roster"] else g["ring_holder"]
    g["setup_queue"] = _order_from(g, start)
    g["setup_pos"] = 0
    events.append("🔨 Setup actions, starting to the Ring-bearer's left.")
    _auto(g, events)


def _setup_actor(g):
    if g.get("phase") != "setup" or g.get("pending"):
        return None
    q = g.get("setup_queue") or []
    pos = g.get("setup_pos", 0)
    if pos >= len(q):
        return None
    return q[pos]


def _threat_deck(g):
    return list(chapter(g["chapter"])["threats"])


def _setup_step(g, idx, events):
    p = g["players"][idx]
    c = CHARACTERS.get(p["character"])
    if not c:
        return
    kind = p["character"]
    if kind == "gandalf" and g.get("lost"):
        p["hand"].append(g["lost"])
        p["hand"].sort()
        events.append(f"🧙 {html_safe(p['name'])} (Gandalf) takes the lost card {cname(g['lost'])}.")
        g["lost"] = None
    if c["setup"].startswith("Draws a") or kind in ("sam", "maggot", "strider", "aragorn"):
        deck = _threat_deck(g)
        if deck:
            p["threat"] = _rng().choice(deck)
            events.append(f"👁 {html_safe(p['name'])} draws threat <b>{p['threat']}</b>.")
    if kind == "bill":
        for target_name in ("frodo", "sam"):
            t = next((j for j, q in enumerate(g["players"])
                      if q["character"] == target_name and j != idx), None)
            if t is not None and len(p["hand"]) > 1:
                card = _rng().choice([x for x in p["hand"] if x != "R1"] or p["hand"])
                p["hand"].remove(card)
                g["players"][t]["hand"].append(card)
                g["players"][t]["hand"].sort()
        events.append(f"🐴 {html_safe(p['name'])} (Bill) passes cards to Frodo and Sam.")
    targets = _exchange_targets(g, idx)
    if targets:
        g["pending"] = {"kind": "exchange_out", "actor": idx, "targets": targets}
    else:
        g["setup_pos"] += 1


def _exchange_targets(g, idx):
    me = g["players"][idx]
    c = CHARACTERS.get(me["character"])
    if not c or not c["exchange"]:
        return []
    return [j for j, p in enumerate(g["players"])
            if j != idx and p["character"] in c["exchange"]]


def pending_actor(g):
    p = g.get("pending")
    return p.get("actor") if p else None


def exchange_cards(g, idx, card, target=None, events=None):
    """Exchange stage 1: actor gives a card to the chosen target."""
    events = events if events is not None else []
    pend = g.get("pending") or {}
    if g.get("phase") != "setup" or pend.get("kind") != "exchange_out" or pend.get("actor") != idx:
        return "no exchange pending for you"
    if card not in g["players"][idx]["hand"]:
        return "card not in your hand"
    if idx == g["ring_holder"] and card == "R1":
        return "the One Ring cannot be exchanged"
    if target not in pend["targets"]:
        return "invalid exchange target"
    g["players"][idx]["hand"].remove(card)
    g["players"][target]["hand"].append(card)
    g["players"][target]["hand"].sort()
    g["pending"] = {"kind": "exchange_in", "actor": target, "other": idx, "given": card}
    return None


def exchange_back(g, idx, card, events=None):
    """Exchange stage 2: receiver passes any card back (may be the same one)."""
    events = events if events is not None else []
    pend = g.get("pending") or {}
    if g.get("phase") != "setup" or pend.get("kind") != "exchange_in" or pend.get("actor") != idx:
        return "no reply pending for you"
    if card not in g["players"][idx]["hand"]:
        return "card not in your hand"
    if idx == g["ring_holder"] and card == "R1":
        return "the One Ring cannot be exchanged"
    other = pend["other"]
    g["players"][idx]["hand"].remove(card)
    g["players"][other]["hand"].append(card)
    g["players"][other]["hand"].sort()
    events.append(f"🔄 {html_safe(g['players'][other]['name'])} and "
                  f"{html_safe(g['players'][idx]['name'])} exchanged a card.")
    g["pending"] = None
    g["setup_pos"] += 1
    _auto(g, events)
    return None


# ---------- trick taking ----------
def is_done(p):
    c = CHARACTERS.get(p["character"])
    return not p["hand"] or (bool(c and c["keep_one"]) and len(p["hand"]) <= 1)


def active_players(g):
    return [i for i, p in enumerate(g["players"]) if not is_done(p)]


def legal_cards(g, idx, trick=None):
    """Cards this player may play right now."""
    if idx != g.get("current") or g.get("phase") != "playing" or g.get("pending"):
        return []
    hand = g["players"][idx]["hand"]
    trick = trick if trick is not None else g.get("trick")
    if not trick or not trick["plays"]:
        if not g["ring_broken"] and any(suit(c) != "Ring" for c in hand):
            return [c for c in hand if suit(c) != "Ring"]
        return list(hand)
    lead = trick["suit"]
    following = [c for c in hand if suit(c) == lead]
    return following or list(hand)


def current_player(g):
    if g.get("phase") == "choosing":
        return selection_actor(g)
    if g.get("phase") == "setup":
        return pending_actor(g) if g.get("pending") else _setup_actor(g)
    if g.get("phase") == "playing":
        return g.get("current")
    return None


def play_card(g, idx, card, events=None):
    """Play one card into the current trick. May raise a One Ring choice."""
    events = events if events is not None else []
    if g.get("phase") != "playing" or g.get("pending"):
        return "no play is pending"
    if idx != g.get("current"):
        return "not your turn"
    if card not in g["players"][idx]["hand"]:
        return "card not in your hand"
    if card not in legal_cards(g, idx):
        return "must follow the lead suit" if g["trick"]["plays"] else "cannot lead Rings yet"
    g["players"][idx]["hand"].remove(card)
    trick = g["trick"]
    if not trick["plays"]:
        trick["suit"] = suit(card)
    trick["plays"].append({"player": idx, "card": card})
    events.append(f"🃏 {html_safe(g['players'][idx]['name'])} plays <b>{cname(card)}</b>.")
    if suit(card) == "Ring" and trick["suit"] != "Ring" and not g["ring_broken"]:
        g["ring_broken"] = True
        events.append("💍 The Rings suit is broken — it may now be led.")
    if len(trick["plays"]) == trick["size"]:
        ring_play = next((pl for pl in trick["plays"] if pl["card"] == "R1"), None)
        if ring_play:
            g["pending"] = {"kind": "ring_choice", "actor": ring_play["player"]}
        else:
            _finish_trick(g, events)
    else:
        g["current"] = _next_active(g, idx)
    _auto(g, events)
    return None


def ring_choice(g, idx, use_it, events=None):
    events = events if events is not None else []
    pend = g.get("pending") or {}
    if g.get("phase") != "playing" or pend.get("kind") != "ring_choice" or pend.get("actor") != idx:
        return "no One Ring choice pending for you"
    g["pending"] = None
    if use_it:
        events.append(f"💍 {html_safe(g['players'][idx]['name'])} claims the trick with the One Ring!")
    _finish_trick(g, bool(use_it), events)
    return None


def _next_active(g, idx):
    act = set(active_players(g))
    for off in range(1, len(g["players"]) + 1):
        j = (idx + off) % len(g["players"])
        if j in act:
            return j
    return idx


def _finish_trick(g, use_ring=False, events=None):
    events = events if events is not None else []
    trick = g["trick"] or {"plays": [], "suit": None}
    plays = trick["plays"]
    lead = trick["suit"]
    winner = None
    if use_ring:
        winner = next((pl["player"] for pl in plays if pl["card"] == "R1"), None)
    if winner is None and lead:
        best = -1
        for pl in plays:
            if suit(pl["card"]) == lead and rank(pl["card"]) > best:
                best, winner = rank(pl["card"]), pl["player"]
    if winner is None:
        winner = plays[0]["player"] if plays else g["leader"]
    cards = [pl["card"] for pl in plays]
    g["players"][winner]["won"].extend(cards)
    g["players"][winner]["trick_wins"].append(g["trick_no"])
    g["last_plays"] = list(plays)
    events.append(f"🏆 {html_safe(g['players'][winner]['name'])} wins trick {g['trick_no']} "
                  f"({', '.join(cname(c) for c in cards)}).")
    g["trick_no"] += 1
    g["trick"] = None
    if len(active_players(g)) < 2 or all(is_done(p) for p in g["players"]):
        # No further trick is possible once fewer than two players hold cards.
        _end_round(g, events)
        return
    act = [i for i in _order_from(g, winner) if i in set(active_players(g))]
    if not act:
        _end_round(g, events)
        return
    _start_trick(g, act[0])


def _start_trick(g, leader):
    """Open a fresh trick with a frozen player count (hands can empty mid-trick)."""
    g["leader"] = leader
    g["current"] = leader
    g["trick"] = {"leader": leader, "suit": None, "plays": [],
                  "size": len(active_players(g)) or len(g["players"])}


# ---------- goals ----------
def _goals(g):
    """Return {character_key: achieved_bool} for the current round."""
    res = {}
    n = len(g["players"])
    counts = {i: len(p["trick_wins"]) for i, p in enumerate(g["players"])}
    last = g["trick_no"] - 1
    for i, p in enumerate(g["players"]):
        key = p["character"]
        if not key or key in res:
            continue
        kind, param = CHARACTERS[key]["goal"]
        won = p["won"]
        w = counts[i]
        if kind == "rings_min":
            need = param.get(str(n), param.get(str(3), 2)) if isinstance(param, dict) else (4 if n <= 3 else 2)
            ok = sum(1 for c in won if suit(c) == "Ring") >= need
        elif kind == "tricks_min":
            ok = w >= param
        elif kind == "tricks_exact":
            ok = w == param
        elif kind == "tricks_range":
            ok = param[0] <= w <= param[1]
        elif kind == "fewest":
            ok = w == 0 or all(w <= counts[j] for j in range(n) if j != i)
        elif kind == "threat_hill":
            ok = f"H{p['threat']}" in won if p["threat"] else False
        elif kind == "threat_rank_two":
            ok = p["threat"] is not None and sum(1 for c in won if rank(c) == p["threat"]) >= 2
        elif kind == "forest_last":
            ok = any(pl["player"] == i and suit(pl["card"]) == "Forest" for pl in g["last_plays"])
        elif kind == "tricks_consecutive":
            seq = sorted(p["trick_wins"])
            ok = w == param and bool(seq) and all(b == a + 1 for a, b in zip(seq, seq[1:]))
        elif kind == "tricks_last_three":
            ok = any(t >= last - 2 for t in p["trick_wins"])
        elif kind == "avoid_threat":
            ok = p["threat"] is not None and w != p["threat"]
        elif kind == "threat_tricks":
            ok = p["threat"] is not None and w == p["threat"]
        elif kind == "suit_cards":
            s, need = param
            ok = sum(1 for c in won if suit(c) == s) >= need
        elif kind == "suit_most":
            mine = sum(1 for c in won if suit(c) == param)
            others = [sum(1 for c in g["players"][j]["won"] if suit(c) == param)
                      for j in range(n) if j != i]
            ok = mine > 0 and all(mine > x for x in others)
        elif kind == "last_trick":
            ok = (any(pl["player"] == i for pl in g["last_plays"]) and
                  (not param or "R1" not in won))
        else:
            ok = False
        res[key] = ok
    return res


def goal_text(g, key, idx=None):
    c = CHARACTERS.get(key)
    if not c:
        return "?"
    kind, param = c["goal"]
    n = len(g["players"])
    if kind == "rings_min":
        need = param.get(str(n), param.get(str(3), 2)) if isinstance(param, dict) else (4 if n <= 3 else 2)
        return f"Win {need}+ Rings cards"
    if kind == "tricks_min":
        return f"Win {param}+ tricks"
    if kind == "tricks_exact":
        return f"Win exactly {param} trick(s)"
    if kind == "tricks_range":
        return f"Win exactly {param[0]} or {param[1]} tricks"
    if kind == "fewest":
        return "Win the fewest tricks (a tie counts)"
    if kind == "threat_hill":
        t = g["players"][idx]["threat"] if idx is not None else None
        return f"Win the {t} of Hills" if t else "Win the threat's Hills card"
    if kind == "threat_rank_two":
        t = g["players"][idx]["threat"] if idx is not None else None
        return f"Win two {t}s (any suit)" if t else "Win two cards of the threat rank"
    if kind == "forest_last":
        return "Play a Forest card in the final trick"
    if kind == "tricks_consecutive":
        return f"Win exactly {param} tricks in a row"
    if kind == "tricks_last_three":
        return "Win one of the last three tricks"
    if kind == "avoid_threat":
        t = g["players"][idx]["threat"] if idx is not None else None
        return f"Do NOT win exactly {t} tricks" if t else "Avoid the threat number of tricks"
    if kind == "threat_tricks":
        t = g["players"][idx]["threat"] if idx is not None else None
        return f"Win exactly {t} tricks" if t else "Win the threat number of tricks"
    if kind == "suit_cards":
        return f"Win {param[1]}+ {PLURAL[param[0]]} cards"
    if kind == "suit_most":
        return f"Win more {PLURAL[param]} than anyone else"
    if kind == "last_trick":
        return "Win the final trick, never take the 1 of Rings" if param else "Win the final trick"
    return c["setup"]


def goal_status(g):
    """Public progress for each seat: (character, name, goal text, achieved)."""
    goals = _goals(g)
    out = []
    for i, p in enumerate(g["players"]):
        if p["character"]:
            out.append({"player": i, "name": p["name"], "character": p["character"],
                        "goal": goal_text(g, p["character"], i),
                        "ok": goals.get(p["character"], False),
                        "tricks": len(p["trick_wins"]), "cards": len(p["won"])})
    return out


def _end_round(g, events):
    ch = chapter(g["chapter"])
    goals = _goals(g)
    chosen = [p["character"] for p in g["players"] if p["character"]]
    ok = all(goals.get(k, False) for k in chosen)
    failed = [k for k in chosen if not goals.get(k, False)]
    g["phase"] = "round_end"
    g["pending"] = None
    if ok:
        for k in chosen:
            if k not in g["completed"]:
                g["completed"].append(k)
        need = ch["required"] if ch else []
        done = all(k in g["completed"] for k in need)
        if ch and ch["victory"] == "long":
            done = all(k in g["completed"] for k in ch["roster"])
        if done:
            g["phase"] = "chapter_end"
            g["result"] = "won"
            events.append(f"🎉 Chapter {g['chapter']} complete! All goals achieved.")
        else:
            g["result"] = "round_won"
            remaining = [CHARACTERS[k]["name"] for k in (ch["roster"] if ch else [])
                         if k not in g["completed"]]
            events.append(f"⭐ Round won! Still to finish: {', '.join(remaining) or '?'}. Next round deals now.")
            g["round"] += 1
            _deal(g, events)
    else:
        g["result"] = "lost"
        events.append("💔 Round failed: " + ", ".join(
            f"{CHARACTERS[k]['name']} ({goal_text(g, k, next((i for i, p in enumerate(g['players']) if p['character'] == k), None))})"
            for k in failed) + ". Retry the round.")
    return goals


# ---------- automatic resolution (NPC turns and no-decision phases) ----------
def _auto(g, events, limit=40):
    for _ in range(limit):
        if g.get("phase") == "choosing":
            idx = selection_actor(g)
            if idx is None:
                _begin_setup(g, events)
                continue
            if not g["players"][idx].get("npc"):
                return
            ch = chapter(g["chapter"])
            avail = available_characters(g)
            req = [c for c in avail if c in ch["required"]]
            pick = (req or avail or ["frodo"])[0]
            choose_character(g, idx, pick, events)
            continue
        if g.get("phase") == "setup":
            idx = pending_actor(g)
            if idx is None:
                idx = _setup_actor(g)
                if idx is None:
                    g["phase"] = "playing"
                    g["trick_no"] = 1
                    act = active_players(g) or list(range(len(g["players"])))
                    _start_trick(g, act[0])
                    events.append("▶️ Play begins. Lead any suit (Rings only if broken).")
                    continue
                _setup_step(g, idx, events)
                continue
            if not g["players"][idx].get("npc"):
                return
            pend = g["pending"]
            if pend["kind"] == "exchange_out":
                hand = [c for c in g["players"][idx]["hand"]
                        if not (idx == g["ring_holder"] and c == "R1")]
                card = _rng().choice(hand) if hand else None
                target = _rng().choice(pend["targets"])
                if card:
                    exchange_cards(g, idx, card, target, events)
                else:
                    g["pending"] = None
                    g["setup_pos"] += 1
            elif pend["kind"] == "exchange_in":
                hand = [c for c in g["players"][idx]["hand"]
                        if not (idx == g["ring_holder"] and c == "R1")]
                exchange_back(g, idx, _rng().choice(hand), events) if hand else exchange_back(g, idx, pend["given"], events)
            continue
        if g.get("phase") == "playing":
            idx = g.get("current")
            pend = g.get("pending")
            if pend and pend.get("kind") == "ring_choice":
                if not g["players"][pend["actor"]].get("npc"):
                    return
                ring_choice(g, pend["actor"], True, events)
                continue
            if idx is None:
                return
            if not g["players"][idx].get("npc"):
                return
            legal = legal_cards(g, idx)
            if not legal:
                return
            play_card(g, idx, _rng().choice(legal), events)
            continue
        return


def advance(g, events=None):
    """Public wrapper used by the bot after any mutation."""
    _auto(g, events if events is not None else [])
    return g


def public_board(g, viewer_id=None):
    """Viewer-filtered state for the Mini App: private hands stay private."""
    me = next((p for p in g["players"] if p["user_id"] == viewer_id), None)
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == viewer_id), None)
    pend = g.get("pending")
    out = {
        "chat_id": g["chat_id"], "phase": g["phase"], "chapter": g["chapter"],
        "chapter_title": chapter(g["chapter"])["title"] if chapter(g["chapter"]) else "?",
        "round": g["round"], "result": g.get("result"), "lost": g["lost"],
        "ring_holder": g["ring_holder"], "ring_broken": g["ring_broken"],
        "leader": g["leader"], "current": current_player(g), "trick_no": g["trick_no"],
        "is_player": me is not None, "viewer_index": idx,
        "completed": list(g.get("completed") or []),
        "victory": (chapter(g["chapter"]) or {"victory": "short"})["victory"],
        "trick": ({"leader": g["trick"]["leader"], "suit": g["trick"]["suit"],
                   "plays": [{"player": pl["player"], "card": pl["card"]}
                             for pl in g["trick"]["plays"]]} if g.get("trick") else None),
        "last_plays": list(g.get("last_plays") or []),
        "pending": ({"kind": pend["kind"], "actor": pend["actor"],
                     "targets": pend.get("targets", []), "given": pend.get("given")}
                    if pend else None),
        "available": available_characters(g) if g["phase"] == "choosing" else [],
        "players": [{"user_id": p["user_id"], "name": p["name"], "npc": bool(p.get("npc")),
                     "hand_count": len(p["hand"]), "character": p["character"],
                     "threat": p["threat"], "tricks": len(p["trick_wins"]),
                     "won_count": len(p["won"]), "won_cards": list(p["won"]),
                     "hand": sorted(p["hand"]) if me is not None and i == idx else []}
                    for i, p in enumerate(g["players"])],
        "goals": goal_status(g),
        "my_legal": legal_cards(g, idx) if idx is not None and g["phase"] == "playing" else [],
        "current_legal": (legal_cards(g, g.get("current")) if g.get("phase") == "playing" else []),
        "current_is_npc": (bool(g["players"][g["current"]].get("npc"))
                           if g.get("phase") == "playing" and g.get("current") is not None else False),
        "pending_hand": (sorted(g["players"][pend["actor"]]["hand"])
                         if pend and pend.get("actor") is not None
                         and g["players"][pend["actor"]].get("npc") else []),
    }
    return out


def set_lead(g, card):
    """Internal: record the lead card of a fresh trick (used by play_card)."""
    if not g.get("trick"):
        g["trick"] = {"leader": g["current"], "suit": None, "plays": []}
    if not g["trick"]["plays"]:
        g["trick"]["suit"] = suit(card)
