"""Azul (Michael Kiesling, 2017) engine - pure logic, no Telegram, no I/O.

Rules verified against the official Azul rulebook (Plan B / Next Move) and
the Board Game Arena rules summary:

- 100 tiles: 20 of each of 5 colours. 5/7/9 factory displays of 4 tiles for
  2/3/4 players, plus the centre (which holds the starting-player marker).
- Factory offer: on your turn take ALL tiles of one colour from one factory
  (the rest of that display slides to the centre) or from the centre. The first
  centre-tile pick of a round also takes the marker; a centre holding only the
  marker is not a legal pick, and the round's first player keeps it if nobody
  picks from the centre. Put the tiles on one pattern line (1-5 spaces, one
  colour each, never a colour already in that row of your wall); overflow goes
  to the 7-space floor line, then to the box lid when full.
- Wall-tiling (automatic at the end of the round): every full pattern line
  moves its rightmost tile to the matching wall space. Score the connected
  horizontal and vertical group sizes (1 if isolated); leftover pattern
  tiles and floor tiles go to the lid. Floor penalties are -1,-1,-2,-2,-2,-3,-3
  (the marker counts as a tile); scores never drop below 0. The marker holder
  is first player next round.
- The game ends after the round in which anyone completes a wall row. Final
  bonuses: +2 per complete row, +7 per complete column, +10 per complete
  colour set. Ties break on completed rows, otherwise the win is shared.

Moves are two-step: `take_tiles` removes a colour from a display and stores
it in `pending`; `place_tiles` commits it to a pattern line (or the floor,
row -1). Both Telegram buttons and the Mini App use the same validation.
"""
import html
import random

MIN_PLAYERS = 2
MAX_PLAYERS = 4
FACTORY_COUNTS = {2: 5, 3: 7, 4: 9}
FACTORY_COUNT = FACTORY_COUNTS[MAX_PLAYERS]
FACTORY_SIZE = 4
TILES_PER_COLOR = 20
COLORS = ("blue", "yellow", "red", "black", "white")
MARKER = "first"
SYMBOLS = {"blue": "🔵", "yellow": "🟡", "red": "🔴", "black": "⚫",
           "white": "⚪", MARKER: "⭐"}
NAMES = {"blue": "blue", "yellow": "yellow", "red": "red", "black": "black",
         "white": "white", MARKER: "first-player marker"}
FLOOR_PENALTIES = (-1, -1, -2, -2, -2, -3, -3)
WALL = [[(c - r) % 5 for c in range(5)] for r in range(5)]


def build_bag():
    bag = []
    for color in COLORS:
        bag.extend([color] * TILES_PER_COLOR)
    assert len(bag) == 100, len(bag)
    return bag


def tile_symbol(tile):
    return SYMBOLS.get(tile, "❔")


def tiles_str(tiles):
    return " ".join(tile_symbol(t) for t in tiles) or "—"


def wall_column(row, color):
    """Column of `color` in wall row `row` (standard Azul board layout)."""
    return (COLORS.index(color) + row) % 5


def new_player(user_id, name):
    return {
        "user_id": int(user_id), "name": name, "npc": False,
        "score": 0, "pattern": [[] for _ in range(5)],
        "wall": [[None] * 5 for _ in range(5)],
        "floor": [], "last_round": None, "winner": False,
    }


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [new_player(creator_id, creator_name)],
        "phase": "lobby",  # lobby|draft|game_end
        "round": 0, "current": 0, "first_player": 0,
        "bag": [], "lid": [], "factories": [], "center": [],
        "marker_center": False, "pending": None,
        "winner_id": None, "winners": [], "board_message_id": None,
    }


def name_of(g, user_id):
    for p in g["players"]:
        if p["user_id"] == user_id:
            return p["name"]
    return "?"


def start_game(g, events):
    n = len(g["players"])
    if n < MIN_PLAYERS or n > MAX_PLAYERS:
        return f"Azul needs {MIN_PLAYERS}-{MAX_PLAYERS} players"
    for p in g["players"]:
        p["score"] = 0
        p["pattern"] = [[] for _ in range(5)]
        p["wall"] = [[None] * 5 for _ in range(5)]
        p["floor"] = []
        p["last_round"] = None
        p["winner"] = False
    g["bag"] = build_bag()
    random.shuffle(g["bag"])
    g["lid"] = []
    g["round"] = 0
    g["first_player"] = 0
    g["winner_id"] = None
    g["winners"] = []
    events.append(f"🔷 Azul started with {n} players. First round is dealt!")
    _start_round(g, events)
    return None


def _draw_tile(g, events):
    if not g["bag"]:
        if not g["lid"]:
            return None
        g["bag"] = g["lid"]
        g["lid"] = []
        random.shuffle(g["bag"])
        events.append("♻️ Empty bag - tiles from the lid are reshuffled back in.")
    return g["bag"].pop()


def _start_round(g, events):
    g["round"] += 1
    g["center"] = []
    g["marker_center"] = True
    g["pending"] = None
    g["factories"] = [[] for _ in range(FACTORY_COUNTS[len(g["players"])])]
    for f in g["factories"]:
        for _ in range(FACTORY_SIZE):
            tile = _draw_tile(g, events)
            if tile is None:
                break
            f.append(tile)
    g["current"] = g["first_player"]
    g["phase"] = "draft"
    events.append(f"🎲 Round {g['round']}: {g['players'][g['first_player']]['name']} has the "
                  "starting-player marker and goes first.")


def take_options(g):
    """Legal picks for the current player: source/color/count descriptors."""
    if g["phase"] != "draft" or g["pending"]:
        return []
    opts = []
    for i, f in enumerate(g["factories"]):
        for color in COLORS:
            n = f.count(color)
            if n:
                opts.append({"source": "factory", "index": i, "color": color, "count": n})
    for color in COLORS:
        n = g["center"].count(color)
        if n:
            opts.append({"source": "center", "index": 0, "color": color, "count": n})
    return opts


def rows_for(g, idx, color):
    """Pattern rows where `color` may be placed (empty rows and same-colour rows)."""
    if color not in COLORS:
        return []
    p = g["players"][idx]
    rows = []
    for r in range(5):
        line = p["pattern"][r]
        if line:
            if line[0] == color:
                rows.append(r)
        elif p["wall"][r][wall_column(r, color)] is None:
            rows.append(r)
    return rows


def take_tiles(g, idx, source, source_index, color, events):
    """Pick all tiles of one colour from a factory or the centre. Sets `pending`."""
    if g["phase"] != "draft":
        return "tiles can only be picked during the factory offer"
    if g["pending"]:
        return "place the tiles you just picked first"
    if idx != g["current"]:
        return "not your turn"
    source_index = int(source_index or 0)
    if not any(o["source"] == source and o["index"] == source_index and o["color"] == color
               for o in take_options(g)):
        return "that colour is not available there"
    marker = False
    if source == "factory":
        f = g["factories"][source_index]
        count = f.count(color)
        tiles = [color] * count
        for _ in range(count):
            f.remove(color)
        g["factories"][source_index] = []
        g["center"].extend(f)
        events.append(f"🎨 {g['players'][idx]['name']} takes {count} {NAMES[color]} "
                      f"from factory {source_index + 1}; the rest slides to the centre.")
    else:
        count = g["center"].count(color)
        tiles = [color] * count
        for _ in range(count):
            g["center"].remove(color)
        events.append(f"🎨 {g['players'][idx]['name']} takes {count} {NAMES[color]} "
                      "from the centre.")
        if g["marker_center"]:
            marker = True
            events.append(f"⭐ {g['players'][idx]['name']} takes the starting-player marker.")
        g["marker_center"] = False
    g["pending"] = {"by": idx, "color": color, "tiles": tiles, "marker": marker,
                    "source": source, "source_index": source_index}
    return None


def place_tiles(g, idx, row, events):
    """Commit the pending pick to a pattern line (`row` 0-4) or the floor (-1)."""
    pend = g.get("pending")
    if not pend or pend["by"] != idx:
        return "pick tiles first"
    row = int(row)
    if row != -1 and not 0 <= row < 5:
        return "choose a pattern line 1-5 or the floor"
    p = g["players"][idx]
    color = pend["color"]
    tiles = list(pend["tiles"])
    count = 0
    if row != -1:
        if not tiles:
            return "the marker alone must go on the floor line"
        line = p["pattern"][row]
        if line and line[0] != color:
            return f"line {row + 1} already holds {NAMES[line[0]]}"
        if not line and p["wall"][row][wall_column(row, color)] is not None:
            return f"{NAMES[color]} is already on wall row {row + 1}"
        fit = max(0, row + 1 - len(line))
        count = min(len(tiles), fit)
        p["pattern"][row].extend([color] * count)
        msg = f"🧱 {p['name']} places {count} {NAMES[color]} on line {row + 1}"
        if len(tiles) > count:
            msg += f" ({len(tiles) - count} spill to the floor)"
        events.append(msg + ".")
    if pend["marker"]:
        p["floor"].append(MARKER)
    for tile in tiles[count:]:
        if len(p["floor"]) < len(FLOOR_PENALTIES):
            p["floor"].append(tile)
        else:
            g["lid"].append(tile)
    if row == -1 and tiles:
        events.append(f"🧱 {p['name']} drops {len(tiles)} tiles on the floor.")
    if not tiles and not pend["marker"]:
        return "nothing to place"
    g["pending"] = None
    g["current"] = (idx + 1) % len(g["players"])
    if not any(g["factories"]) and not g["center"]:
        _resolve_round(g, events)
    return None


def do_move(g, idx, move, events):
    """One-call convenience used by the APIs: pick + place in a single request."""
    err = take_tiles(g, idx, move.get("source"), move.get("index"),
                     move.get("color"), events)
    if err:
        return err
    return place_tiles(g, idx, move.get("row", -1), events)


def _connected(wall, r, c):
    color = wall[r][c]
    left = right = up = down = 0
    for cc in range(c - 1, -1, -1):
        if wall[r][cc] != color:
            break
        left += 1
    for cc in range(c + 1, 5):
        if wall[r][cc] != color:
            break
        right += 1
    for rr in range(r - 1, -1, -1):
        if wall[rr][c] != color:
            break
        up += 1
    for rr in range(r + 1, 5):
        if wall[rr][c] != color:
            break
        down += 1
    return left + right + 1, up + down + 1


def complete_rows(p):
    return sum(1 for row in p["wall"] if all(cell is not None for cell in row))


def complete_columns(p):
    return sum(1 for c in range(5) if all(p["wall"][r][c] is not None for r in range(5)))


def complete_colors(p):
    return sum(1 for color in COLORS
               if all(color in p["wall"][r] for r in range(5)))


def _resolve_round(g, events):
    """Wall-tiling, floor penalties, marker rotation and end-of-game scoring."""
    for idx, p in enumerate(g["players"]):
        gained = 0
        for r in range(5):
            line = p["pattern"][r]
            if len(line) != r + 1:
                continue
            color = line[0]
            c = wall_column(r, color)
            p["wall"][r][c] = color
            h, v = _connected(p["wall"], r, c)
            pts = (h if h > 1 else 0) + (v if v > 1 else 0) or 1
            p["score"] += pts
            gained += pts
            events.append(f"⬜ {p['name']} places {NAMES[color]} at wall row {r + 1}, "
                          f"column {c + 1}: +{pts} ({h} across, {v} down)")
            g["lid"].extend(line[1:])
            p["pattern"][r] = []
        penalty = -sum(FLOOR_PENALTIES[i] for i in range(min(len(p["floor"]), 7)))
        if penalty:
            loss = min(penalty, p["score"])
            p["score"] -= loss
            gained -= loss
            events.append(f"💥 {p['name']} loses {loss} points for {len(p['floor'])} "
                          "tile(s) on the floor line.")
        if MARKER in p["floor"]:
            g["first_player"] = idx
            events.append(f"⭐ {p['name']} will start the next round.")
        g["lid"].extend(t for t in p["floor"] if t != MARKER)
        p["floor"] = []
        p["last_round"] = gained
    if any(complete_rows(p) for p in g["players"]):
        _end_game(g, events)
    else:
        events.append(f"Round {g['round']} scored. Next round incoming…")
        _start_round(g, events)


def _end_game(g, events):
    g["phase"] = "game_end"
    for p in g["players"]:
        rows, cols, colors = complete_rows(p), complete_columns(p), complete_colors(p)
        bonus = rows * 2 + cols * 7 + colors * 10
        p["score"] += bonus
        if bonus:
            if p["last_round"] is None:
                p["last_round"] = 0
            p["last_round"] += bonus
            events.append(f"🏅 {p['name']} final bonuses: {rows} rows (+{rows * 2}), "
                          f"{cols} columns (+{cols * 7}), {colors} colour sets "
                          f"(+{colors * 10}) = +{bonus}")
    top = max(p["score"] for p in g["players"])
    leaders = [i for i, p in enumerate(g["players"]) if p["score"] == top]
    if len(leaders) > 1:
        best_rows = max(complete_rows(g["players"][i]) for i in leaders)
        leaders = [i for i in leaders if complete_rows(g["players"][i]) == best_rows]
    g["winners"] = leaders
    g["winner_id"] = g["players"][leaders[0]]["user_id"] if len(leaders) == 1 else None
    for i in leaders:
        g["players"][i]["winner"] = True
    names = " & ".join(g["players"][i]["name"] for i in leaders)
    events.append(f"🏆 Game over! {'Winner' if len(leaders) == 1 else 'Winners'}: "
                  f"{names} with {top} points!")


def board_lines(g):
    """Compact HTML board text for Telegram (names are escaped here)."""
    lines = [f"🔷 <b>Azul</b> - Round {g['round']} | First: "
             f"{html.escape(g['players'][g['first_player']]['name'])} | "
             f"Bag {len(g['bag'])} | Lid {len(g['lid'])}"]
    if g["phase"] == "game_end":
        lines.append("🏆 " + " & ".join(html.escape(g["players"][i]["name"])
                                       for i in g["winners"]) + " win!")
    else:
        facs = [f"{i + 1}:{tiles_str(f)}" for i, f in enumerate(g["factories"]) if f]
        lines.append("🏭 " + "  ".join(facs))
        center = (tile_symbol(MARKER) + " " if g["marker_center"] else "") + tiles_str(g["center"])
        lines.append("🎯 Center: " + center)
        cur = g["players"][g["current"]]
        if g["pending"]:
            pend = g["pending"]
            tiles = tiles_str(pend["tiles"] + ([MARKER] if pend["marker"] else []))
            lines.append(f"👉 <b>{html.escape(cur['name'])}</b> picked {tiles} - choose a line or the floor.")
        else:
            lines.append(f"👉 <b>{html.escape(cur['name'])}</b>'s turn - pick a colour.")
    for p in g["players"]:
        wall = " ".join("".join(tile_symbol(c) if c else "·" for c in row)
                        for row in p["wall"])
        lines.append(f"\n<b>{html.escape(p['name'])}</b> — <b>{p['score']}</b> pts "
                     f"(rows {complete_rows(p)}, cols {complete_columns(p)}, "
                     f"sets {complete_colors(p)})")
        lines.append("🟫 " + wall)
        lines.append("📏 " + " ".join(f"{r + 1}:{tiles_str(line)}" for r, line in
                                     enumerate(p["pattern"]) if line))
        lines.append("🧹 " + tiles_str(p["floor"]))
    return "\n".join(lines)
