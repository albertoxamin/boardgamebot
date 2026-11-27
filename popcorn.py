"""Popcorn engine - pure logic, no Telegram, no I/O (stdlib only).

Rules checked against the official Iello rulebook
(sources/popcorn/rulebook.pdf) and the Board Game Arena rules summary.
Art from the BGA table metadata is stored in sources/popcorn/bga/.
"""
import html
import random

MIN_PLAYERS = 2
MAX_PLAYERS = 4
ROUNDS = 9
COLORS = ("red", "blue", "yellow", "green")
COLOR_ICONS = {"red": "🔴", "blue": "🔵", "yellow": "🟡", "green": "🟢", "white": "⚪"}
ACTION_ICONS = {
    "money": "💵", "popcorn": "🍿", "audience": "📈", "ad": "📣",
    "extra": "🎬", "guest": "🎟️", "reserve": "↩️", "award": "🏆",
    "any": "🎲", "white": "⚪",
}
ACTION_NAMES = {
    "money": "gain ${n}", "popcorn": "gain {n} Popcorn",
    "audience": "increase audience", "ad": "place an Advertising token",
    "extra": "use another Movie action", "guest": "draw a Guest to a seat",
    "reserve": "return a Guest to the reserve", "award": "draw 2 Awards, keep 1",
    "any": "gain a Guest of any color", "white": "give a white Guest to a bag",
}

MOVIE_TITLES = (
    "The Last Reel", "Neon Nights", "Paper Planets", "Midnight Matinee",
    "The Great Escape", "Velvet Riot", "Sunset Boulevard", "Cosmic Comedians",
    "A Tale of Two Cities", "The Hidden Gate", "Static Gold", "Wildflowers",
    "The Long Weekend", "Crystal Canyon", "Five Easy Pieces", "The Single Shadow",
    "Echoes of Summer", "The Glass Orchestra", "Bright Horizon", "Desert Radio",
    "The Quiet Signal", "Silver Harbor", "A Thousand Steps", "The Electric Dream",
    "Fever Dream", "The Tiny Kingdom", "Northern Lights", "The Third Wish",
    "Rocket Boys", "The Paper Tiger", "Blue Hour", "The Secret Garden",
    "Lucky Seven", "The Iron Bird", "Golden Hour", "The Silent Partner",
    "Carnival Road", "The Final Frame", "Ruby Tuesday", "The Open Door",
    "After the Credits", "The Wild Type", "Starlight Cafe", "One More Show",
)

THEATER_COSTS = {1: (3, 4, 6), 2: (6, 8, 9), 3: (9, 12, 15)}

AWARD_KINDS = (
    ("theater1", "Best Single Screen", "theater_size", 1, 4),
    ("theater2", "Best Double Screen", "theater_size", 2, 5),
    ("theater3", "Best Multiplex", "theater_size", 3, 6),
    ("theaters", "Most Theaters", "theaters", None, 4),
    ("audience", "Biggest Audience", "audience", None, 4),
    ("money", "Fullest Wallet", "money", None, 4),
    ("popcorn", "Popcorn Lover", "popcorn", None, 4),
    ("archives", "Clean Archives", "archives", None, 3),
    ("red", "Action Fan", "movies", "red", 4),
    ("blue", "Drama Fan", "movies", "blue", 4),
    ("yellow", "Comedy Fan", "movies", "yellow", 4),
    ("green", "Sci-Fi Fan", "movies", "green", 4),
    ("redguests", "Red Regulars", "guests", "red", 3),
    ("blueguests", "Blue Regulars", "guests", "blue", 3),
    ("yellowguests", "Yellow Regulars", "guests", "yellow", 3),
    ("greenguests", "Green Regulars", "guests", "green", 3),
    ("whiteguests", "White Regulars", "guests", "white", 3),
    ("ads", "Advertising Pro", "ads", None, 3),
    ("action", "Action Movies", "movie_action", "red", 3),
    ("comedy", "Comedy Movies", "movie_action", "yellow", 3),
    ("drama", "Drama Movies", "movie_action", "blue", 3),
    ("scifi", "Sci-Fi Movies", "movie_action", "green", 3),
    ("rich", "Box Office", "money", None, 5),
    ("crowd", "Crowd Pleaser", "guests", None, 3),
    ("classic", "Classic Cinema", "archives", None, 5),
    ("premier", "Premiere Nights", "premiers", None, 4),
)
AWARDS = tuple({"id": i, "code": code, "name": name, "kind": kind,
                "value": value, "points": points}
               for i, (code, name, kind, value, points) in enumerate(AWARD_KINDS))

RULES = """🍿 <b>Popcorn rules</b> (2-4 players, bag-building): run a cinema, show the right movies to the right Guests, and finish with the most Popcorn.
• <b>Round:</b> Buying &amp; Advertising in turn order, then simultaneous Showings, then Theatrical Run / New Lineup. On your Buying turn you may buy 1 movie, buy 1 theater (not on your first turn), and activate Advertising tokens in any order. End with ✅ Done.
• <b>Showings:</b> draw as many Guests as your audience track (starts at 3), place them in theaters showing a movie (seat #1 before #2, etc.; extras go to your exit zone), then activate each Guest in seat order: Seat action, then Movie action if their color matches the movie, then exit. Gray seats work for anyone; colored seats need a matching Guest. Each Movie action is usable once per round; one action is covered each round by the Lobby slider.
• <b>Bag:</b> when you must draw and the bag is empty, shuffle your exit zone into the bag and keep drawing. Movies matching the theater's seat count give an immediate Showing bonus; Premiers cost +$2 and add a Guest of that color.
• <b>Scoring:</b> kept Popcorn + 1 Popcorn per $5 + Theater trophies (highest total cost of 3 theaters: 5/3 Popcorn with 3-4 players, 3 with 2 players) + Award cards. Ties: fewest archived movies, then shared victory.
• Commands: /popcorn (create), /popcorn_join, /popcorn_join_npc, /popcorn_start, /popcorn_move &lt;button-code&gt;, /popcorn_rules, /popcorn_cancel, /popcorn_rematch. Moves use the board buttons or the Mini App; the 🎥 How to play button opens the video tutorial."""

_COLOR_POOL = {
    "red": ("money", "popcorn", "ad", "extra", "guest", "reserve", "award", "money", "popcorn"),
    "blue": ("money", "award", "ad", "any", "guest", "reserve", "money", "popcorn", "audience"),
    "yellow": ("audience", "money", "guest", "ad", "extra", "popcorn", "audience", "guest", "any"),
    "green": ("guest", "reserve", "white", "ad", "audience", "money", "guest", "popcorn", "award"),
}


def _action(kind, n=0):
    return {"k": kind, "n": int(n)}


def _build_movies(rnd):
    cards = []
    colors = list(COLORS)
    rnd.shuffle(colors)
    for i, title in enumerate(MOVIE_TITLES):
        color = colors[i % 4]
        pool = _COLOR_POOL[color]
        actions = [_action(pool[(i + j * 3 + j // 3) % len(pool)],
                           (i + j) % 3 + 1 if pool[(i + j * 3 + j // 3) % len(pool)]
                           in ("money", "popcorn") else 0)
                   for j in range(3)]
        bonus = _action(pool[(i * 2) % len(pool)],
                        1 if pool[(i * 2) % len(pool)] not in ("reserve", "white") else 0)
        cards.append({"id": i, "title": title, "color": color,
                      "cost": 1 + (i * 5) % 9, "seats": 1 + (i // 5) % 3,
                      "actions": actions, "bonus": bonus})
    rnd.shuffle(cards)
    return cards


def _build_starting_movies():
    out = {}
    for i, color in enumerate(COLORS):
        out[color] = {"id": f"start_{color}", "title": "Starting Movie", "color": color,
                      "cost": 0, "seats": 1,
                      "actions": [_action(_COLOR_POOL[color][i % len(_COLOR_POOL[color])], 1)],
                      "bonus": _action("popcorn", 1), "starting": True}
    return out


STARTING_MOVIES = _build_starting_movies()


def _build_theater_tiles(rnd):
    tiles = {}
    kinds = ("money", "popcorn", "ad", "guest", "reserve", "audience", "extra", "award")
    for size in (1, 2, 3):
        group = []
        for i in range(10):
            seats = []
            for seat in range(size):
                kind = kinds[(i * 3 + seat * 5 + size) % len(kinds)]
                n = (i + seat) % 3 + 1 if kind in ("money", "popcorn") else 0
                color = "gray" if (i + seat) % 3 else COLORS[(i + seat) % 4]
                seats.append({"c": color, "a": _action(kind, n)})
            group.append({"id": f"t{size}_{i}", "size": size,
                          "cost": THEATER_COSTS[size][i % 3], "seats": seats})
        rnd.shuffle(group)
        tiles[size] = group
    return tiles


def _build_deck(rnd):
    awards = list(AWARDS)
    rnd.shuffle(awards)
    return awards


def name_of(g, user_id):
    return next((p["name"] for p in g["players"] if p["user_id"] == user_id), "player")


def new_player(user_id, name):
    return {"user_id": int(user_id), "name": name, "npc": False, "money": 0,
            "popcorn": 0, "audience": 3, "bag": [], "exit": [],
            "theaters": [], "archived": [], "awards": [], "premiers": 0,
            "ads": 3, "ads_board": [], "turns": 0, "color": "red"}


def new_game(chat_id, creator_id, creator_name, rng=None):
    return {"chat_id": int(chat_id), "created_by": int(creator_id),
            "players": [new_player(creator_id, creator_name)],
            "phase": "lobby", "round": 0, "current": 0, "buy_pos": 0,
            "first_player": 0, "market": {}, "deck": [], "awards": [],
            "tile_deck": [], "reserve": {}, "pending": None, "final_round": None,
            "winner": None, "log": [], "board_message_id": None,
            "chat_type": "private"}


def _rng(g):
    return g.get("_rng") or random


def _remember(g, events, before):
    g.setdefault("log", []).extend(events[before:])
    g["log"] = g["log"][-40:]


def _draw_movie(g, events, rnd=None):
    rnd = rnd or _rng(g)
    if not g["movie_deck"]:
        g["movie_deck"] = list(g["movie_discard"])
        g["movie_discard"] = []
        rnd.shuffle(g["movie_deck"])
        if not g["movie_deck"]:
            g["movie_deck"] = [c["id"] for c in _build_movies(rnd)]
            rnd.shuffle(g["movie_deck"])
    cid = g["movie_deck"].pop()
    if cid == g.get("final_card") and not g.get("final_round"):
        g["final_round"] = g["round"] + 1
        events.append("🎬 Final Showing revealed - this is the last round!")
    return cid


def _card(g, cid):
    if cid is None:
        return {"id": None, "title": "Empty", "color": "", "cost": 0,
                "seats": 0, "actions": [], "bonus": _action("money", 0)}
    if isinstance(cid, dict):
        return cid
    card = g.get("movie_by_id", {}).get(cid)
    if isinstance(card, dict):
        return card
    return {"id": cid, "title": "Movie", "color": "red", "cost": 1,
            "seats": 1, "actions": [_action("money", 1)], "bonus": _action("popcorn", 1)}


def _refill_market(g, events, rnd=None):
    rnd = rnd or _rng(g)
    for row in ("features", "premiers"):
        while len(g["market"][row]) < 3:
            cid = _draw_movie(g, events, rnd)
            card = g.get("movie_by_id", {}).get(cid)
            if card is None:
                g["movie_discard"].append(cid)
                continue
            g["market"][row].append(cid)
    for size in (1, 2, 3):
        while len(g["market"]["tiles"][size]) < 3 and g["tile_deck"][size]:
            g["market"]["tiles"][size].append(g["tile_deck"][size].pop())


def _draw_award(g):
    if not g["awards"]:
        return None
    return g["awards"].pop()


def _award_score(g, award, p):
    kind = award["kind"]
    if kind == "theater_size":
        return sum(1 for t in p["theaters"] if t["size"] == award["value"])
    if kind == "theaters":
        return len(p["theaters"])
    if kind == "audience":
        return p["audience"]
    if kind == "money":
        return p["money"]
    if kind == "popcorn":
        return p["popcorn"]
    if kind == "archives":
        return -len(p["archived"])
    if kind == "movies":
        return sum(1 for t in p["theaters"] if _card(g, t["movie"]).get("color") == award["value"])
    if kind == "guests":
        colors = [award["value"]] if award["value"] else COLORS
        return sum(p["bag"].count(c) + p["exit"].count(c) for c in colors)
    if kind == "ads":
        return p["ads"] + len(p["ads_board"])
    if kind == "movie_action":
        return sum(1 for t in p["theaters"] for a in _card(g, t["movie"]).get("actions", [])
                   if a["k"] == award["value"])
    if kind == "premiers":
        return p["premiers"]
    return 0


def _give_award(g, p, events):
    a = _draw_award(g)
    b = _draw_award(g)
    choices = [x for x in (a, b) if x]
    if not choices:
        return
    best = max(choices, key=lambda x: _award_score(g, x, p))
    p["awards"].append(best["id"])
    for x in choices:
        if x["id"] != best["id"]:
            g.setdefault("award_discard", []).append(x["id"])
    events.append(f"🏆 {p['name']} kept {best['name']}.")


def _take_guest(g, color, events, actor=None):
    if g["reserve"].get(color, 0) > 0:
        g["reserve"][color] -= 1
        return color
    order = list(range(len(g["players"])))
    if actor is not None:
        order = [i for i in order if i != actor] + [actor]
    for i in order:
        if color in g["players"][i]["exit"]:
            g["players"][i]["exit"].remove(color)
            events.append(f"🎟️ {g['players'][i]['name']} gave a {COLOR_ICONS.get(color, '')} Guest to {g['players'][actor]['name'] if actor is not None else 'the cinema'}.")
            return color
    return None


def _start_game_setup(g, events, rnd):
    n = len(g["players"])
    cards = _build_movies(rnd)
    g["movie_by_id"] = {c["id"]: c for c in cards}
    g["movie_by_id"].update({m["id"]: m for m in STARTING_MOVIES.values()})
    g["movie_deck"] = [c["id"] for c in cards]
    rnd.shuffle(g["movie_deck"])
    under = 10 if n == 2 else 5
    g["final_card"] = g["movie_deck"][under]
    g["movie_discard"] = []
    g["tile_deck"] = _build_theater_tiles(rnd)
    g["awards"] = _build_deck(rnd)
    g["award_discard"] = []
    g["reserve"] = {c: 2 for c in COLORS}
    g["market"] = {"features": [], "premiers": [],
                   "tiles": {1: [], 2: [], 3: []}}
    g["round"] = 1
    g["first_player"] = 0
    g["final_round"] = None
    g["winner"] = None
    g["log"] = []
    g["pending"] = None
    for i, p in enumerate(g["players"]):
        start_color = COLORS[i % 4]
        p.update(money=5 + i, popcorn=0, audience=3, archived=[], awards=[],
                 premiers=0, ads=3, ads_board=[], turns=0, color=start_color)
        bag = ["white"] * 5 + list(COLORS) + [start_color]
        rnd.shuffle(bag)
        p["bag"] = bag
        p["exit"] = list(COLORS)
        p["theaters"] = [{"size": 1, "seats": [{"c": "gray", "a": _action("money", 1)}],
                          "movie": STARTING_MOVIES[start_color], "slider": 0,
                          "used": []}]
        _give_award(g, p, events)
    _refill_market(g, events, rnd)
    events.append(f"🍿 Popcorn started! {n} cinemas open with $5-$8 and 10 Guests each.")
    _start_buy(g, events)


def start_game(g, events=None, rng=None):
    if g["phase"] != "lobby":
        return "game already started"
    n = len(g["players"])
    if not MIN_PLAYERS <= n <= MAX_PLAYERS:
        return f"Popcorn needs {MIN_PLAYERS}-{MAX_PLAYERS} players"
    ev = events if events is not None else []
    before = len(ev)
    rnd = rng or _rng(g)
    _start_game_setup(g, ev, rnd)
    _remember(g, ev, before)
    return None


def _order(g):
    n = len(g["players"])
    return [(g["first_player"] + i) % n for i in range(n)]


def _start_buy(g, events):
    g["phase"] = "buy"
    g["buy_pos"] = 0
    g["current"] = _order(g)[0]
    g["pending"] = None
    for p in g["players"]:
        p["bought_movie"] = False
        p["bought_theater"] = False
    events.append(f"🛒 Round {g['round']} buying: {g['players'][g['current']]['name']} starts.")


def current_index(g):
    if g["phase"] == "buy":
        return g["current"]
    if g["phase"] == "show":
        if g.get("pending") and g["pending"].get("kind") == "place":
            return g["pending"]["by"]
        order = _order(g)
        pos = g.get("show_pos", 0)
        return order[pos] if pos < len(order) else None
    return None


def _movie_in_market(g, mid):
    for row in ("features", "premiers"):
        if mid in g["market"][row]:
            return row
    return None


def _draw_from_bag(g, p, count, events):
    out = []
    while len(out) < count:
        if p["bag"]:
            out.append(p["bag"].pop())
            continue
        if p["exit"]:
            p["bag"] = list(p["exit"])
            p["exit"] = []
            _rng(g).shuffle(p["bag"])
            events.append(f"🔄 {p['name']} refilled the bag from the exit zone.")
            continue
        break
    return out


def _start_show(g, events):
    g["phase"] = "show"
    g["show_pos"] = 0
    g["show_order"] = _order(g)
    g["current"] = g["show_order"][0]
    events.append("🎬 Showings begin - draw and seat your Guests.")
    _next_show(g, events)


def _next_show(g, events):
    order = g.get("show_order") or _order(g)
    while g["show_pos"] < len(order):
        idx = order[g["show_pos"]]
        p = g["players"][idx]
        guests = _draw_from_bag(g, p, p["audience"], events)
        if not guests:
            events.append(f"🎟️ {p['name']} has no Guests to show.")
            g["show_pos"] += 1
            continue
        g["pending"] = {"kind": "place", "by": idx, "guests": guests}
        g["current"] = idx
        events.append(f"🎟️ {p['name']} draws {len(guests)} Guests: " +
                      " ".join(COLOR_ICONS.get(c, "⚪") for c in guests))
        return
    _end_round(g, events)


def _free_seat(t, start=0):
    for i in range(start, len(t["seats"])):
        if t["seats"][i]["c"] not in COLORS and t["seats"][i]["c"] != "gray":
            continue
        if t["seats"][i].get("guest") is None:
            return i
    return None


def pending_options(g, idx=None):
    pend = g.get("pending")
    if not pend or pend.get("kind") != "place":
        return []
    if idx is not None and pend.get("by") != idx:
        return []
    out = []
    for color in dict.fromkeys(pend["guests"]):
        for s, t in enumerate(g["players"][pend["by"]]["theaters"]):
            if not isinstance(t["movie"], dict):
                continue
            seat = _free_seat(t)
            if seat is None:
                continue
            out.append({"label": f"{COLOR_ICONS.get(color, '⚪')} → Theater {s + 1}, seat {seat + 1}",
                        "value": f"{color}:{s}", "color": color, "slot": s})
    return out


def _available_movie_actions(t):
    movie = t["movie"]
    count = max(0, 3 - min(3, t.get("slider", 0)))
    return [(i, a) for i, a in enumerate(movie.get("actions", [])[:count])
            if i not in t.get("used", [])]


def _apply_action(g, actor, action, n, t, events, depth=0):
    if depth > 8:
        return
    p = g["players"][actor]
    kind = action.get("k")
    if kind == "money":
        amount = max(1, action.get("n") or 1)
        p["money"] += amount
        events.append(f"💵 {p['name']} gains ${amount}.")
    elif kind == "popcorn":
        amount = max(1, action.get("n") or 1)
        p["popcorn"] += amount
        events.append(f"🍿 {p['name']} gains {amount} Popcorn.")
    elif kind == "audience":
        p["audience"] = min(7, p["audience"] + 1)
        events.append(f"📈 {p['name']}'s audience grows to {p['audience']}.")
    elif kind == "ad":
        if p["ads"] > 0:
            p["ads"] -= 1
            color = _card(g, t["movie"])["color"]
            p["ads_board"].append({"kind": "color", "color": color})
            events.append(f"📣 {p['name']} places an Advertising token.")
    elif kind == "guest":
        guests = _draw_from_bag(g, p, 1, events)
        if guests:
            seat = _free_seat(t, 1) if t.get("current_seat", 0) >= 0 else None
            if seat is None:
                p["exit"].append(guests[0])
                events.append(f"🎟️ Extra Guest goes to {p['name']}'s exit zone.")
            else:
                t["seats"][seat]["guest"] = guests[0]
                events.append(f"🎟️ {p['name']} seats a new Guest.")
    elif kind == "reserve":
        victim = p["exit"][0] if p["exit"] else None
        if victim is None:
            for tt in p["theaters"]:
                for seat in tt["seats"]:
                    if seat.get("guest"):
                        victim = seat.pop("guest")
                        break
                if victim:
                    break
        if victim:
            g["reserve"][victim] = g["reserve"].get(victim, 0) + 1
            events.append(f"↩️ {p['name']} returns a Guest to the reserve.")
    elif kind == "award":
        _give_award(g, p, events)
    elif kind == "any":
        color = _card(g, t["movie"])["color"]
        got = _take_guest(g, color, events, actor)
        if got:
            p["bag"].append(got)
            events.append(f"🎟️ {p['name']} adds a {COLOR_ICONS.get(got, '')} Guest to the bag.")
    elif kind == "white":
        white = None
        if g["reserve"].get("white", 0) > 0:
            g["reserve"]["white"] -= 1
            white = "white"
        elif "white" in p["exit"]:
            p["exit"].remove("white")
            white = "white"
        else:
            for tt in p["theaters"]:
                for seat in tt["seats"]:
                    if seat.get("guest") == "white":
                        seat["guest"] = None
                        white = "white"
                        break
                if white:
                    break
        if white:
            others = [i for i in range(len(g["players"])) if i != actor]
            target = min(others, key=lambda i: len(g["players"][i]["bag"])) if others else actor
            g["players"][target]["bag"].append("white")
            events.append(f"⚪ {p['name']} gives a white Guest to {g['players'][target]['name']}'s bag.")
    elif kind == "extra":
        avail = _available_movie_actions(t)
        if avail:
            i, nxt = max(avail, key=lambda item: (item[1]["k"] == "popcorn",
                                                  item[1]["k"] == "audience",
                                                  item[1]["k"] == "money",
                                                  item[1].get("n", 0)))
            t["used"].append(i)
            _apply_action(g, actor, nxt, n, t, events, depth + 1)


def _resolve_show(g, idx, events):
    p = g["players"][idx]
    for ti, t in enumerate(p["theaters"]):
        if not isinstance(t["movie"], dict):
            continue
        movie = t["movie"]
        for si in range(len(t["seats"])):
            if si >= len(t["seats"]):
                break
            seat = t["seats"][si]
            guest = seat.get("guest")
            if not guest:
                continue
            t["current_seat"] = si
            if seat["c"] == "gray" or seat["c"] == guest:
                _apply_action(g, idx, seat["a"], seat["a"].get("n", 0), t, events)
            if guest == movie["color"]:
                avail = _available_movie_actions(t)
                if avail:
                    i, action = max(avail, key=lambda item: (
                        item[1]["k"] == "popcorn", item[1]["k"] == "audience",
                        item[1]["k"] == "money", item[1].get("n", 0)))
                    t["used"].append(i)
                    _apply_action(g, idx, action, action.get("n", 0), t, events)
            seat["guest"] = None
        t.pop("current_seat", None)
    events.append(f"🎬 {p['name']}'s showing is over.")


def _end_round(g, events):
    for p in g["players"]:
        for t in p["theaters"]:
            if isinstance(t["movie"], dict):
                t["slider"] = min(3, t.get("slider", 0) + 1)
                t["used"] = []
    if g.get("final_round") == g["round"]:
        _finish_game(g, events)
        return
    g["market"]["features"] = list(g["market"]["premiers"])
    g["market"]["premiers"] = []
    for row in ("features", "premiers"):
        while len(g["market"][row]) < 3:
            mid = _draw_movie(g, events)
            if g.get("movie_by_id", {}).get(mid) is not None:
                g["market"][row].append(mid)
            else:
                g["movie_discard"].append(mid)
    for size in (1, 2, 3):
        while len(g["market"]["tiles"][size]) < 3 and g["tile_deck"][size]:
            g["market"]["tiles"][size].append(g["tile_deck"][size].pop())
    g["round"] += 1
    g["first_player"] = (g["first_player"] + 1) % len(g["players"])
    events.append(f"🔁 Round {g['round']} begins.")
    _start_buy(g, events)


def _finish_game(g, events):
    for p in g["players"]:
        p["popcorn"] += p["money"] // 5
        costs = sorted((t.get("cost", 0) for t in p["theaters"]), reverse=True)
        p["theater_cost"] = sum(costs[:3])
    costs = [p["theater_cost"] for p in g["players"]]
    top = max(costs)
    leaders = [i for i, c in enumerate(costs) if c == top]
    trophy = 5 if len(g["players"]) >= 3 else 3
    if len(leaders) == 1:
        g["players"][leaders[0]]["popcorn"] += trophy
        events.append(f"🏅 {g['players'][leaders[0]]['name']} wins the Theater trophy (+{trophy}).")
    elif len(g["players"]) >= 3:
        rest = sorted((c for c in costs if c != top), reverse=True)
        if rest and rest[0] < top:
            second = [i for i, c in enumerate(costs) if c == rest[0]]
            if len(second) == 1:
                g["players"][second[0]]["popcorn"] += 3
                events.append(f"🏅 {g['players'][second[0]]['name']} wins the second Theater trophy (+3).")
    for aid in sorted({a for p in g["players"] for a in p["awards"] if a < len(AWARDS)}):
        award = AWARDS[aid]
        scores = [_award_score(g, award, p) for p in g["players"]]
        best = max(scores)
        if best <= 0:
            continue
        for i, sc in enumerate(scores):
            if sc == best:
                g["players"][i]["popcorn"] += award["points"]
                events.append(f"🏆 {g['players'][i]['name']} scores {award['points']} from {award['name']}.")
    best = max(p["popcorn"] for p in g["players"])
    tied = [i for i, p in enumerate(g["players"]) if p["popcorn"] == best]
    if len(tied) > 1:
        tied.sort(key=lambda i: len(g["players"][i]["archived"]))
        best = g["players"][tied[0]]["popcorn"]
        tied = [i for i in tied if g["players"][i]["popcorn"] == best]
    g["winner"] = tied[0]
    g["shared"] = tied
    g["phase"] = "game_end"
    g["pending"] = None
    events.append(f"🏆 Final scores: " + ", ".join(
        f"{p['name']} {p['popcorn']}🍿" for p in g["players"]))


def _buy_movie(g, actor, params, events):
    p = g["players"][actor]
    if p.get("bought_movie"):
        return "you already bought a movie this turn"
    mid = params.get("movie")
    available = g["market"]["features"] + g["market"]["premiers"]
    if mid not in available and str(mid) not in [str(x) for x in available]:
        return "that movie is not available"
    if mid not in available:
        mid = next(x for x in available if str(x) == str(mid))
    try:
        slot = int(params.get("slot"))
    except (TypeError, ValueError):
        return "bad theater slot"
    if not 0 <= slot < len(p["theaters"]) or not p["theaters"][slot].get("size"):
        return "bad theater slot"
    card = _card(g, mid)
    row = _movie_in_market(g, mid)
    if not row:
        return "that movie is not available"
    cost = card["cost"] + (2 if row == "premiers" else 0)
    if p["money"] < cost:
        return f"need ${cost}"
    p["money"] -= cost
    g["market"][row].remove(mid)
    g["movie_discard"].append(mid)
    t = p["theaters"][slot]
    if isinstance(t["movie"], dict) and not t["movie"].get("starting"):
        p["archived"].append(t["movie"]["id"])
    t["movie"] = card
    t["slider"] = 0
    t["used"] = []
    p["bought_movie"] = True
    if row == "premiers":
        p["premiers"] += 1
        got = _take_guest(g, card["color"], events, actor)
        if got:
            p["bag"].append(got)
    if t["size"] == card["seats"]:
        _apply_action(g, actor, card["bonus"], card["bonus"].get("n", 0), t, events)
    events.append(f"🎬 {p['name']} shows {card['title']} in Theater {slot + 1} for ${cost}.")
    return None


def _buy_theater(g, actor, params, events):
    p = g["players"][actor]
    if p.get("bought_theater"):
        return "you already bought a theater this turn"
    if p["turns"] == 0 and g["round"] == 1:
        return "you cannot buy a theater on your first turn"
    tid = params.get("tile")
    slot = params.get("slot")
    try:
        slot = int(slot)
    except (TypeError, ValueError):
        return "bad theater slot"
    tile = None
    size = None
    for s in (1, 2, 3):
        for candidate in g["market"]["tiles"][s]:
            if str(candidate["id"]) == str(tid):
                tile = candidate
                size = s
                break
        if tile:
            break
    if tile is None:
        return "that theater is not available"
    if not 0 <= slot < 3:
        return "bad theater slot"
    if p["money"] < tile["cost"]:
        return f"need ${tile['cost']}"
    p["money"] -= tile["cost"]
    g["market"]["tiles"][size].remove(tile)
    first_right = slot == 2 and len(p["theaters"]) <= 2
    while len(p["theaters"]) <= slot:
        p["theaters"].append({"size": 0, "cost": 0, "seats": [], "movie": None,
                              "slider": 0, "used": []})
    old = p["theaters"][slot]
    movie = old["movie"] if old else None
    slider = old["slider"] if old else 0
    used = list(old.get("used", [])) if old else []
    if isinstance(movie, dict) and not movie.get("starting"):
        p["archived"].append(movie["id"])
    seats = [{"c": seat["c"], "a": seat["a"], "guest": None} for seat in tile["seats"]]
    theater = {"size": tile["size"], "cost": tile["cost"], "seats": seats,
               "movie": movie, "slider": slider, "used": used}
    if old:
        p["theaters"][slot] = theater
    else:
        p["theaters"].append(theater)
    p["bought_theater"] = True
    if first_right:
        p["audience"] = min(7, p["audience"] + 1)
        events.append(f"📈 {p['name']}'s audience grows to {p['audience']}.")
    events.append(f"🏛️ {p['name']} buys a {tile['size']}-seat theater for ${tile['cost']}.")
    return None


def _activate_ad(g, actor, params, events):
    p = g["players"][actor]
    if g["round"] == 1 and p["turns"] == 0:
        return "you cannot activate Advertising on your first turn"
    if not p["ads_board"]:
        return "no Advertising tokens on the board"
    idx = params.get("index", 0)
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        return "bad Advertising token"
    if not 0 <= idx < len(p["ads_board"]):
        return "bad Advertising token"
    token = p["ads_board"].pop(idx)
    p["ads"] += 1
    if token["kind"] == "color":
        got = _take_guest(g, token["color"], events, actor)
        if got:
            p["bag"].append(got)
            events.append(f"📣 {p['name']} adds a {COLOR_ICONS.get(got, '')} Guest from Advertising.")
    else:
        white = None
        if g["reserve"].get("white", 0) > 0:
            g["reserve"]["white"] -= 1
            white = "white"
        if white:
            p["bag"].append(white)
            events.append("📣 Advertising adds a white Guest.")
    return None


def _place_guest(g, actor, params, events):
    pend = g.get("pending")
    if not pend or pend.get("kind") != "place" or pend.get("by") != actor:
        return "you have no Guests to place"
    color = params.get("color")
    if color not in pend["guests"]:
        return "that Guest was not drawn"
    try:
        slot = int(params.get("slot"))
    except (TypeError, ValueError):
        return "bad theater slot"
    if not 0 <= slot < len(g["players"][actor]["theaters"]):
        return "bad theater slot"
    t = g["players"][actor]["theaters"][slot]
    if not isinstance(t["movie"], dict):
        return "that theater has no movie"
    seat = _free_seat(t)
    if seat is None:
        return "that theater is full"
    t["seats"][seat]["guest"] = color
    pend["guests"].remove(color)
    if not pend["guests"]:
        g["pending"] = None
        _resolve_show(g, actor, events)
        g["show_pos"] += 1
        _next_show(g, events)
    return None


def _auto_place(g, actor, events):
    pend = g.get("pending")
    if not pend or pend.get("kind") != "place" or pend.get("by") != actor:
        return "you have no Guests to place"
    while pend["guests"]:
        color = pend["guests"][0]
        options = [o for o in pending_options(g, actor) if o["color"] == color]
        if not options:
            p = g["players"][actor]
            p["exit"].append(color)
            pend["guests"].remove(color)
            if not pend["guests"]:
                g["pending"] = None
                _resolve_show(g, actor, events)
                g["show_pos"] += 1
                _next_show(g, events)
            break
        movie_colors = [_card(g, t["movie"])["color"] if isinstance(t["movie"], dict) else ""
                        for t in g["players"][actor]["theaters"]]
        best = max(options, key=lambda o: (
            movie_colors[o["slot"]] == color,
            g["players"][actor]["theaters"][o["slot"]]["seats"][_free_seat(g["players"][actor]["theaters"][o["slot"]])]["c"] in ("gray", color)))
        err = _place_guest(g, actor, {"color": color, "slot": best["slot"]}, events)
        if err:
            return err
        pend = g.get("pending")
        if not pend or pend.get("kind") != "place":
            break
    return None


def act(g, actor, action, params=None, events=None):
    params = params or {}
    ev = events if events is not None else []
    before = len(ev)

    def finish(err):
        if err is None:
            _remember(g, ev, before)
        return err

    if not 0 <= actor < len(g["players"]):
        return "not in this game"
    if current_index(g) != actor:
        return "not your turn"
    if action == "done" and g["phase"] == "buy":
        p = g["players"][actor]
        p["turns"] += 1
        g["buy_pos"] += 1
        if g["buy_pos"] >= len(g["players"]):
            _start_show(g, ev)
        else:
            g["current"] = _order(g)[g["buy_pos"]]
        return finish(None)
    if g["phase"] == "buy":
        if action == "movie":
            return finish(_buy_movie(g, actor, params, ev))
        if action == "theater":
            return finish(_buy_theater(g, actor, params, ev))
        if action == "ad":
            return finish(_activate_ad(g, actor, params, ev))
    if g["phase"] == "show":
        if action == "place":
            return finish(_place_guest(g, actor, params, ev))
        if action == "auto":
            return finish(_auto_place(g, actor, ev))
    return "unknown action"


def apply_choice(g, actor, value, events=None):
    pend = g.get("pending")
    if not pend or pend.get("kind") != "place":
        return "no pending choice"
    try:
        color, slot = str(value).split(":", 1)
    except ValueError:
        return "bad choice"
    return act(g, actor, "place", {"color": color, "slot": slot}, events)


def _code_parts(code):
    body = code[1:]
    if body.startswith(":"):
        body = body[1:]
    parts = body.split(":", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", "")


def parse_code(code):
    code = str(code)
    if code == "d":
        return "done", {}
    if code == "auto":
        return "auto", {}
    if code.startswith("m") and ":" in code:
        mid, slot = _code_parts(code)
        return "movie", {"movie": mid, "slot": slot}
    if code.startswith("t") and ":" in code:
        tid, slot = _code_parts(code)
        return "theater", {"tile": tid, "slot": slot}
    if code.startswith("a") and code[1:].isdigit():
        return "ad", {"index": int(code[1:])}
    if code.startswith("p") and ":" in code:
        color, slot = _code_parts(code)
        color = {"r": "red", "b": "blue", "y": "yellow",
                 "g": "green", "w": "white"}.get(color, color)
        return "place", {"color": color, "slot": slot}
    return "", {}


def action_options(g, viewer_id=None):
    actor = current_index(g)
    me = next((i for i, p in enumerate(g["players"]) if p["user_id"] == viewer_id), None)
    if actor is None or (me is not None and me != actor and not g["players"][actor].get("npc")):
        return []
    out = []
    if g["phase"] == "buy":
        p = g["players"][actor]
        if not p.get("bought_movie"):
            for row in ("features", "premiers"):
                for mid in g["market"][row]:
                    card = _card(g, mid)
                    cost = card["cost"] + (2 if row == "premiers" else 0)
                    for slot, t in enumerate(p["theaters"]):
                        if not t.get("size"):
                            continue
                        label = f"🎬 {card['title']} {COLOR_ICONS.get(card['color'], '')} ${cost} → T{slot + 1}"
                        out.append({"label": label, "action": "movie",
                                    "params": {"movie": mid, "slot": slot},
                                    "code": f"m{mid}:{slot}"})
        if not p.get("bought_theater") and not (g["round"] == 1 and p["turns"] == 0):
            for size in (1, 2, 3):
                for tile in g["market"]["tiles"][size]:
                    for slot in range(min(3, len(p["theaters"]) + 1)):
                        label = f"🏛️ {tile['size']}-seat ${tile['cost']} → T{slot + 1}"
                        out.append({"label": label, "action": "theater",
                                    "params": {"tile": tile["id"], "slot": slot},
                                    "code": f"t{tile['id']}:{slot}"})
        for i, token in enumerate(p["ads_board"]):
            label = "📣 Activate "
            label += (COLOR_ICONS.get(token.get("color"), "") + " Guest"
                      if token.get("kind") == "color" else "white Guest token")
            out.append({"label": label, "action": "ad", "params": {"index": i},
                        "code": f"a{i}"})
        out.append({"label": "✅ Done", "action": "done", "params": {}, "code": "d"})
    elif g["phase"] == "show":
        for opt in pending_options(g, actor):
            out.append({"label": opt["label"], "action": "place",
                        "params": {"color": opt["color"], "slot": opt["slot"]},
                        "code": f"p:{opt['color'][0]}:{opt['slot']}"})
        out.append({"label": "⚡ Auto-seat remaining Guests", "action": "auto",
                    "params": {}, "code": "auto"})
    return out


def _action_text(a):
    if not isinstance(a, dict):
        return "?"
    name = ACTION_NAMES.get(a.get("k"), a.get("k", "?"))
    return name.format(n=a.get("n", 0))


def board_lines(g):
    if g["phase"] == "lobby":
        names = ", ".join(p["name"] for p in g["players"])
        return [f"🍿 Popcorn lobby · {len(g['players'])}/4 players: {names}",
                "Send /popcorn_start when everyone has joined."]
    lines = [f"🍿 Round {g['round']}{' (FINAL)' if g.get('final_round') == g['round'] else ''} · "
             f"{g['phase']} · ${sum(p['money'] for p in g['players'])} in play"]
    if g["phase"] == "buy" or g["phase"] == "show":
        lines.append(f"👉 {g['players'][current_index(g)]['name']}'s move")
    features = ", ".join(
        f"{_card(g, m)['title']} ({COLOR_ICONS.get(_card(g, m)['color'], '')} ${_card(g, m)['cost']})"
        for m in g["market"]["features"])
    premiers = ", ".join(
        f"{_card(g, m)['title']} ({COLOR_ICONS.get(_card(g, m)['color'], '')} ${_card(g, m)['cost'] + 2})"
        for m in g["market"]["premiers"])
    lines.append("🎞️ Features: " + (features or "-"))
    lines.append("🌟 Premiers: " + (premiers or "-"))
    for p in g["players"]:
        theathers = " | ".join(
            f"T{i + 1}: {t['size']} seats, {_card(g, t['movie'])['title']}, "
            f"{''.join(COLOR_ICONS.get(s.get('guest'), '·') for s in t['seats'])}"
            for i, t in enumerate(p["theaters"])) or "-"
        lines.append(f"🏛️ {p['name']}: 🍿{p['popcorn']} 💵{p['money']} 📈{p['audience']} "
                     f"🎟️{p['bag_count'] if 'bag_count' in p else len(p['bag'])} "
                     f"📣{len(p['ads_board'])} · {theathers}")
    if g["phase"] == "show" and g.get("pending"):
        pend = g["pending"]
        lines.append("🎟️ Place: " + " ".join(COLOR_ICONS.get(c, "⚪") for c in pend["guests"]))
    if g["phase"] == "game_end":
        lines.append("🏆 " + ", ".join(
            f"{p['name']} {p['popcorn']}🍿" for p in g["players"]))
    if g.get("log"):
        lines.extend("· " + x for x in g["log"][-4:])
    return lines


def board_json(g, viewer_id=None):
    viewer = next((i for i, p in enumerate(g["players"]) if p["user_id"] == viewer_id), None)
    actor = current_index(g)
    players = []
    for i, p in enumerate(g["players"]):
        show_bag = viewer == i or p.get("npc")
        players.append({
            "name": html.escape(p["name"]), "npc": bool(p.get("npc")),
            "money": p["money"], "popcorn": p["popcorn"], "audience": p["audience"],
            "bag_count": len(p["bag"]), "exit": list(p["exit"]),
            "bag": list(p["bag"]) if show_bag else [],
            "ads": p["ads"], "ads_board": list(p["ads_board"]),
            "awards": [AWARDS[a]["name"] for a in p["awards"] if a < len(AWARDS)],
            "archived": len(p["archived"]),
            "theaters": [{
                "size": t["size"], "cost": t.get("cost", 0),
                "movie": _card(g, t["movie"])["title"],
                "color": _card(g, t["movie"])["color"],
                "slider": t.get("slider", 0),
                "actions": [_action_text(a) for a in _card(g, t["movie"]).get("actions", [])],
                "seats": [{"c": s["c"], "guest": s.get("guest")} for s in t["seats"]],
            } for t in p["theaters"]],
        })
    board = {
        "key": "popcorn", "chat_id": g["chat_id"], "phase": g["phase"], "round": g["round"],
        "final": g.get("final_round") == g["round"],
        "actor": actor, "winner": g["winner"], "shared": g.get("shared", []),
        "players": players,
        "market": {
            "features": [{"id": m, **_card(g, m)} for m in g["market"].get("features", [])],
            "premiers": [{"id": m, **_card(g, m)} for m in g["market"].get("premiers", [])],
            "tiles": {str(s): [{"id": t["id"], "size": t["size"], "cost": t["cost"]}
                               for t in g["market"].get("tiles", {}).get(s, [])]
                      for s in (1, 2, 3)},
        },
        "pending": g.get("pending"),
        "options": action_options(g, viewer_id),
        "log": list(g.get("log", [])[-12:]),
        "can_act": actor is not None and (viewer == actor or
                                          (viewer is not None and g["players"][actor].get("npc"))),
        "is_player": viewer is not None,
    }
    return board
