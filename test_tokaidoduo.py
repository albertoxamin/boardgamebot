"""Run: python3 -m pytest test_tokaidoduo.py  OR  python3 test_tokaidoduo.py"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tokaidoduo as TD


def mk(rng=None):
    g = TD.new_game(1, 1, "A")
    g["players"].append(TD.new_player(2, "B"))
    ev = []
    assert TD.start_game(g, ev, rng=rng or random.Random(1)) is None
    return g


def _set_dice(g, values):
    g["dice"] = dict(values)
    g["dice_taken"] = []
    g["pick_index"] = 0
    g["pending"] = None
    g["first_picker"] = 0


def _pick(g, pid, char):
    ev = []
    err = TD.pick_die(g, pid, char, ev)
    assert err is None, (err, ev)
    return ev


def test_station_counts():
    from collections import Counter
    c = Counter(TD.STATIONS)
    assert len(TD.STATIONS) == 37
    assert c["coastal"] == 8 and c["temple"] == 13 and c["garden"] == 7
    assert c["hotspring"] == 5 and c["seashore"] == 4
    assert TD.COASTAL_STATIONS == [0, 4, 9, 13, 18, 23, 27, 31]


def test_pilgrim_stations_are_measured_off_the_board():
    # FB-0042: the Pilgrim pawn was not clearly on the stations — the
    # Mini App placed it on a guessed ellipse, which missed the drawn
    # medallions by up to ~15% of the board. Every station now has a
    # position measured off tokaidoduo-board.webp (centre of its drawn
    # medallion), served as station_pos in the board JSON, and the JS
    # uses it instead of the ellipse. Coastal stations sit on the same
    # town icon as TOWN_POS, so the Merchant and the Pilgrim agree.
    import math
    assert len(TD.STATION_POS) == len(TD.STATIONS) == 37
    seen = set()
    for i, (x, y) in enumerate(TD.STATION_POS):
        assert 0 <= x <= 100 and 0 <= y <= 100, (i, x, y)
        assert (x, y) not in seen, (i, x, y)  # no two stations share a spot
        seen.add((x, y))
        assert isinstance(x, (int, float)) and isinstance(y, (int, float)), (i, x, y)
    for s in TD.COASTAL_STATIONS:
        assert TD.STATION_POS[s] == TD.TOWN_POS["c_%d" % s], s
    # the ring order is right: consecutive stations (incl. 36 -> 0) are
    # neighbours on the board, never a jump across it.
    for i in range(37):
        x1, y1 = TD.STATION_POS[i]
        x2, y2 = TD.STATION_POS[(i + 1) % 37]
        assert math.hypot(x2 - x1, y2 - y1) < 16, (i, (i + 1) % 37)
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    assert "g.station_pos" in js
    assert "tdStationPos(g, p.pilgrim_pos)" in js
    assert "tdStationPos(g, o.station)" in js
    bot = open(os.path.join(os.path.dirname(__file__), "bot.py"),
               encoding="utf-8").read()
    assert '"station_pos": TD.STATION_POS' in bot


def test_merchant_mountain_towns_are_measured_off_the_board():
    # FB-0043: the Merchant pawns did not sit exactly on their arrival
    # town — the four Mountain towns were still guessed (rotated)
    # positions, off by up to ~13% of the board (m_cl and m_w landed
    # in empty space, m_w even on the wrong town's cluster). Each is
    # now the centre of its drawn gold circle on tokaidoduo-board.webp
    # (badge = MOUNTAIN_DRAW value: 2 for m_e, 3 for m_c and m_cl,
    # 4 for m_w), and the JS puts the Merchant meeple — and the
    # merchant_dest tap highlight — exactly there via town_pos.
    import math
    # measured gold-circle centres (% of the 789x1600 portrait board)
    measured = {"m_e": (41.8, 30.5), "m_c": (56.8, 46.3),
                "m_cl": (50.8, 65.5), "m_w": (49.7, 80.0)}
    guessed = {"m_w": (50, 68), "m_cl": (50, 53), "m_c": (55, 40),
               "m_e": (48, 27)}
    for town, (mx, my) in measured.items():
        x, y = TD.TOWN_POS[town]
        assert math.hypot(x - mx, y - my) < 0.6, (town, (x, y), (mx, my))
        # regression guard: the old guessed spot was far from the town
        assert math.hypot(x - guessed[town][0],
                          y - guessed[town][1]) > 3, town
    # mountain towns are distinct spots, and none collides with a
    # coastal town or a Pilgrim-ring station centre.
    spots = list(TD.TOWN_POS.values())
    assert len(set(spots)) == len(spots) == 12
    for town in measured:
        for s in TD.STATION_POS:
            assert math.hypot(TD.TOWN_POS[town][0] - s[0],
                              TD.TOWN_POS[town][1] - s[1]) > 8, (town, s)
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    assert "(g.town_pos || {})[p.merchant_pos]" in js
    assert "(g.town_pos || {})[String(o.value).slice(5)]" in js
    bot = open(os.path.join(os.path.dirname(__file__), "bot.py"),
               encoding="utf-8").read()
    assert '"town_pos": TD.TOWN_POS' in bot


def test_commerce_tokens_use_bga_art():
    # FB-0044: the commerce tokens (dolls, vases, ...) were emoji —
    # Annalisa asked for the real BGA art from spriteJetonCommerce.jpg.
    # The webp is the 6-panel strip (one panel per boutique offer) and
    # the JS picks the panel by (ware, price) wherever a Ware appears,
    # so the emoji are gone from the Mini App (Telegram text keeps them).
    import os
    webp = os.path.join(os.path.dirname(__file__), "web",
                        "tokaidoduo-commerce.webp")
    assert os.path.isfile(webp) and os.path.getsize(webp) > 10000
    src = os.path.join(os.path.dirname(__file__), "sources", "tokaidoduo",
                       "bga", "spriteJetonCommerce.jpg")
    assert os.path.isfile(src)
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    assert "ware_emoji" not in js
    assert "TD_WARE_TOKEN = {pottery: {4: 0, 3: 1}, fan: {3: 2, 2: 3}, doll: {3: 4}, kimono: {4: 5}}" in js
    assert "function tdWare(ware, price)" in js
    assert "tdWare(b.ware, b.price)" in js
    assert "tdWare(w)" in js
    # every distinct boutique offer has a panel, and no panel is unused
    panels = set()
    for ware, price in set(TD.BOUTIQUE_TOKENS):
        assert ware in ("pottery", "fan", "doll", "kimono")
        panels.add((ware, price))
    assert len(panels) == 6
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert "tokaidoduo-commerce.webp" in html


def test_painting_tokens_use_bga_art():
    # FB-0045: the painting tokens (dipinto) were emoji — Annalisa
    # asked for the real BGA art from spriteOeuvres.jpg. The webp is
    # the 10-panel strip (brush back + 4 icons per player colour) and
    # tdPaintSlot() picks the panel by (colour, icon, revealed) for the
    # printed painting slots on the player board, so the emoji and the
    # '?'/'✓' text are gone from the Mini App (Telegram text keeps the
    # emoji). FB-0049: the slots are the numbered boxes on the Artist
    # track (3-4-3: 2/4/7, 10/14/18/23, 28/34/40), not a 5x2 grid in
    # the middle of the board — and a gifted painting leaves the board
    # on BGA, so gifted tiles are not drawn at all.
    import re
    from PIL import Image
    webp = os.path.join(os.path.dirname(__file__), "web",
                        "tokaidoduo-paintings.webp")
    assert os.path.isfile(webp) and os.path.getsize(webp) > 10000
    assert Image.open(webp).size == (2480, 307)
    src = os.path.join(os.path.dirname(__file__), "sources", "tokaidoduo",
                       "bga", "spriteOeuvres.jpg")
    assert os.path.isfile(src)
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    assert "zone_icon_emoji" not in js
    assert "function tdPaintSlot(col, t, sx, sy)" in js
    assert "tdPaintSlot(col, t, slot[0], slot[1])" in js
    assert "if (idx >= 10 || t.gifted) return;" in js
    assert "tdgift" not in js and "gifted ?" not in js
    # the slots are the culture positions in reading order
    m = re.search(r"const TD_PAINT_SLOT = \[([^\]]*)\]\s*\n\s*\.map\(v => TD_CULTURE_POS\[v\]\);", js)
    assert m, "painting slot order"
    assert [int(v) for v in m.group(1).split(",")] == [2, 4, 7, 10, 14, 18, 23, 28, 34, 40]
    # every painting icon has a panel in each player's colour, the
    # brush back is a different panel per colour, and no panel is unused
    assert "purple: {bamboo: 1, moon: 2, mountain: 3, waterfall: 4}" in js
    assert "green: {bamboo: 6, moon: 7, mountain: 8, waterfall: 9}" in js
    assert "purple: 0, green: 5" in js
    # the deck's icons are exactly the mapped ones
    for col in ("purple", "green"):
        assert sorted(set(TD.PAINTING_TILES[col])) == [
            "bamboo", "moon", "mountain", "waterfall"]
    m = re.search(r"const TD_PAINT_IDX = (\{.*?\});", js, re.S)
    assert m
    back = re.search(r"const TD_PAINT_BACK = (\{[^}]*\});", js)
    assert back
    panels = sorted(int(n) for n in
                    re.findall(r"\d+", m.group(1) + back.group(1)))
    assert panels == list(range(10))
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert "tokaidoduo-paintings.webp" in html
    assert "background-size:600% 100%" in html
    assert ".tdware{" in html
    # FB-0039: a referenced webp that is not in bot.py's static
    # allowlist answers 404 and renders invisible.
    bot = open(os.path.join(os.path.dirname(__file__), "bot.py"),
               encoding="utf-8").read()
    assert '"/tokaidoduo-commerce.webp"' in bot


def test_two_artists_same_zone_both_visible():
    # FB-0047: when both Artists moved into the same zone, one meeple
    # vanished — both markers landed on the exact same zone spot and
    # the second covered the first. The engine allows sharing a zone
    # (artist_destinations has no exclusion, unlike Pilgrim/Merchant),
    # so the Mini App must split the two markers sideways.
    g = mk()
    for pid in (0, 1):
        g["players"][pid]["artist_zone"] = 7
    _set_dice(g, {"pilgrim": 1, "merchant": 2, "artist": 1})
    _pick(g, 0, "artist")
    assert g["pending"]["kind"] == "artist_dest"
    ev = []
    assert TD.choose(g, 0, "dest:0", ev) is None
    while g["pending"]:
        assert TD.choose(g, 0, TD.pending_options(g, 0)[0]["value"], ev) is None
    assert g["players"][0]["artist_zone"] == 0
    # player 1 may move into the SAME zone — no exclusion
    assert 0 in TD.artist_destinations(g, 1, 1)
    g["round"] = 2
    _set_dice(g, {"pilgrim": 1, "merchant": 2, "artist": 1})
    g["first_picker"] = 1  # _set_dice resets it to 0; player 1 rolls first
    _pick(g, 1, "artist")
    assert g["pending"]["kind"] == "artist_dest"
    assert TD.choose(g, 1, "dest:0", ev) is None
    while g["pending"]:
        assert TD.choose(g, 1, TD.pending_options(g, 1)[0]["value"], ev) is None
    assert g["players"][1]["artist_zone"] == 0
    # the Mini App offsets the two artist markers sideways (±2 board-%,
    # ~17px apart on a 420px board for 24px meeples) so both stay
    # visible in the shared zone instead of one covering the other.
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    start = js.index("g.players.forEach((p, i) => {")
    end = js.index("});", start)
    loop = js[start:end]
    assert "sameZone" in loop
    assert "g.players[1 - i].artist_zone === p.artist_zone" in loop
    assert "zp[0] + (sameZone ? (i === 0 ? -2 : 2) : 0)" in loop


def test_zone_graph_and_spaces():
    assert len(TD.ZONES) == 8
    # adjacency is symmetric, 11 trade routes
    edges = set()
    for z, nbs in TD.ZONE_ADJ.items():
        for n in nbs:
            assert z in TD.ZONE_ADJ[n]
            edges.add(tuple(sorted((z, n))))
    assert len(edges) == 11
    # every town / coastal station belongs to at least one zone's spaces
    towns = set()
    stations = set()
    for spec in TD.ZONE_SPACES:
        towns.update(spec["towns"])
        stations.update(spec["stations"])
    assert towns == set(TD.TOWN_ADJ)
    assert stations == set(range(37)) - set(TD.COASTAL_STATIONS)


def test_bga_verified_constants():
    # Dice faces from BGA spriteDes.jpg + live log (release 261120-2009)
    assert sorted(TD.DICE_FACES["pilgrim"]) == [1, 2, 2, 3, 3, 4]
    assert sorted(TD.DICE_FACES["merchant"]) == [1, 1, 2, 2, 3, 3]
    assert sorted(TD.DICE_FACES["artist"]) == [1, 1, 1, 2, 2, 3]
    # Culture table from BGA Artist board + live panels
    assert TD.CULTURE_POINTS == [0, 2, 4, 7, 10, 14, 18, 23, 28, 34, 40]
    # Boutique set read face-up on a live BGA table
    from collections import Counter
    assert Counter(TD.BOUTIQUE_TOKENS) == Counter(
        [("pottery", 3), ("pottery", 4), ("fan", 3), ("fan", 2),
         ("doll", 3), ("doll", 3), ("kimono", 4), ("kimono", 4)])


def test_start_game():
    g = mk()
    assert g["phase"] == "play" and g["round"] == 1
    assert len(g["players"]) == 2
    assert g["players"][0]["color"] == "purple"
    assert g["players"][1]["color"] == "green"
    assert len(g["players"][0]["paintings"]) == 10
    assert len(g["boutiques"]) == 8 and len(g["waves_board"]) == 3
    assert len(g["ware_bag"]) == 26
    assert set(g["dice"]) == {"pilgrim", "merchant", "artist"}
    # BGA dice faces: pilgrim 1-4, merchant/artist 1-3 only
    assert 1 <= g["dice"]["pilgrim"] <= 4
    assert 1 <= g["dice"]["merchant"] <= 3
    assert 1 <= g["dice"]["artist"] <= 3
    # opposite starts
    assert g["players"][0]["pilgrim_pos"] == 1
    assert g["players"][1]["pilgrim_pos"] == 22
    assert g["players"][0]["merchant_pos"] == "c_0"
    assert g["players"][1]["merchant_pos"] == "c_18"


def test_pilgrim_temple_garden_and_occupied_jump():
    g = mk()
    _set_dice(g, {"pilgrim": 1, "merchant": 2, "artist": 2})
    # A pilgrim at 1, move 1 -> station 2 (garden)
    _pick(g, 0, "pilgrim")
    assert g["players"][0]["pilgrim_pos"] == 2
    assert g["players"][0]["garden"] == 2
    # occupied landing jumps to next empty station: put B's pilgrim on 3
    # (Hot Spring), move A 1 from 2 -> would land 3, jumps to 4 (Coastal)
    g["players"][1]["pilgrim_pos"] = 3
    g["pick_index"] = 2  # A picks again (third pick of the round)
    g["dice_taken"] = ["merchant", "artist"]
    g["dice"] = {"pilgrim": 1, "merchant": 2, "artist": 2}
    coins_before = g["players"][0]["coins"]
    _pick(g, 0, "pilgrim")
    assert g["players"][0]["pilgrim_pos"] == 4
    assert g["players"][0]["coins"] > coins_before  # Coastal town pays out


def test_merchant_mountain_draw_and_cap():
    g = mk()
    p = g["players"][0]
    p["merchant_pos"] = "m_w"
    p["wares"] = ["kimono"] * 4
    _set_dice(g, {"pilgrim": 1, "merchant": 1, "artist": 1})
    # merchant 1 step from m_w: destinations m_cl, c_18, c_13 - pick m_cl
    ev = []
    err = TD.pick_die(g, 0, "merchant", ev)
    assert err is None
    assert g["pending"] and g["pending"]["kind"] == "merchant_dest"
    err = TD.choose(g, 0, "dest:m_cl", ev)
    assert err is None, err
    # m_cl draws 3, total 7 > cap 5 -> keep_wares pending
    assert g["pending"] and g["pending"]["kind"] == "keep_wares"
    assert len(p["wares"]) == 7
    for _ in range(2):
        err = TD.choose(g, 0, "discard:0", ev)
        assert err is None, err
    assert len(p["wares"]) == 5
    assert not g["pending"]


def test_merchant_coastal_sell_and_gold():
    g = mk()
    p = g["players"][0]
    p["merchant_pos"] = "m_e"
    p["wares"] = ["fan", "fan", "fan", "kimono"]
    # force boutique at c_0 to fan/4
    g["boutiques"]["c_0"] = {"ware": "fan", "price": 4}
    _set_dice(g, {"pilgrim": 1, "merchant": 1, "artist": 1})
    ev = []
    assert TD.pick_die(g, 0, "merchant", ev) is None
    assert g["pending"]["kind"] == "merchant_dest"
    assert TD.choose(g, 0, "dest:c_0", ev) is None
    assert g["pending"]["kind"] == "sell"
    # sell 3 fans at 4 coins = 12 -> 1 gold slab, 2 coins left.
    # Selling the last matching Ware auto-closes the sell pending.
    for _ in range(3):
        assert TD.choose(g, 0, "sell:0", ev) is None
    assert p["gold"] == 1 and p["coins"] == 2
    assert not g["pending"]


def test_artist_paint_and_gift():
    g = mk()
    p = g["players"][0]
    # put other meeples in zone 0 (moon_nw): B pilgrim on station 19,
    # B merchant on c_18, A merchant on m_w -> 3 other meeples
    g["players"][1]["pilgrim_pos"] = 19
    g["players"][1]["merchant_pos"] = "c_18"
    p["merchant_pos"] = "m_w"
    p["artist_zone"] = 7  # waterfall_w, adjacent to zone 0
    # reveal the top tile so gift can be tested: force its icon to moon
    p["paintings"][0] = {"icon": "moon", "revealed": True, "gifted": False}
    _set_dice(g, {"pilgrim": 1, "merchant": 1, "artist": 1})
    ev = []
    assert TD.pick_die(g, 0, "artist", ev) is None
    # artist 1 step from zone 7: destinations 6 and 0 - pick 0
    assert g["pending"]["kind"] == "artist_dest"
    assert TD.choose(g, 0, "dest:0", ev) is None
    assert g["pending"]["kind"] == "artist_action"
    opts = {o["value"] for o in TD.pending_options(g, 0)}
    assert "gift" in opts  # top tile is moon, arrival zone is moon
    assert TD.choose(g, 0, "gift", ev) is None
    assert p["gifted"] == 1 and TD.culture_score(p) == 2  # BGA table: 1 gift = 2


def test_artist_paint_reveals_by_meeple_count():
    g = mk()
    p = g["players"][0]
    g["players"][1]["pilgrim_pos"] = 19
    g["players"][1]["merchant_pos"] = "c_18"
    p["artist_zone"] = 7
    _set_dice(g, {"pilgrim": 1, "merchant": 1, "artist": 1})
    ev = []
    assert TD.pick_die(g, 0, "artist", ev) is None
    assert TD.choose(g, 0, "dest:0", ev) is None
    assert TD.choose(g, 0, "paint", ev) is None
    revealed = [t for t in p["paintings"] if t["revealed"]]
    # 2 other meeples in zone 0 (B pilgrim + B merchant; A merchant is
    # on m_w, also in zone 0's towns -> 3 total)
    assert len(revealed) == 3


def test_draft_1_2_1_and_round_alternates():
    g = mk()
    _set_dice(g, {"pilgrim": 2, "merchant": 2, "artist": 2})
    # pick order: A, B, A. Pilgrim 2 from 1 -> station 3 (hotspring, takes token)
    _pick(g, 0, "pilgrim")
    assert g["pick_index"] == 1
    # B picks merchant: from c_18, 2 steps -> e.g. m_w (via c_13? no, 2 steps:
    # c_18-m_w-m_cl etc.) - just take first pending option if any
    ev = []
    assert TD.pick_die(g, 1, "merchant", ev) is None
    if g["pending"]:
        opt = TD.pending_options(g, 1)[0]["value"]
        assert TD.choose(g, 1, opt, ev) is None
    assert g["pick_index"] == 2
    # A picks artist (last die)
    assert TD.pick_die(g, 0, "artist", ev) is None
    if g["pending"]:
        # artist_action or artist_dest: resolve generically
        while g["pending"]:
            opt = TD.pending_options(g, 0)[0]["value"]
            assert TD.choose(g, 0, opt, ev) is None
    # round 2 starts, B is first picker
    assert g["round"] == 2 and g["first_picker"] == 1
    assert g["pick_index"] == 0


def test_scoring():
    g = mk()
    p = g["players"][0]
    p["temple"] = 7
    p["garden"] = 6
    p["gold"] = 5
    p["gifted"] = 6
    sc = TD.scores(g)[0]
    assert sc["faith"] == 42 and sc["commerce"] == 35 and sc["culture"] == 18
    assert sc["total"] == 95


def test_end_on_garden_finishes_round_then_scores():
    g = mk()
    p = g["players"][0]
    p["garden"] = 5
    p["temple"] = 3
    _set_dice(g, {"pilgrim": 1, "merchant": 2, "artist": 2})
    # A pilgrim at 1, move 1 -> station 2 garden -> 6, end triggered
    _pick(g, 0, "pilgrim")
    assert g["end_triggered"] and g["phase"] == "play"
    # finish the round (B merchant, A artist) with generic choices
    ev = []
    assert TD.pick_die(g, 1, "merchant", ev) is None
    while g["pending"]:
        assert TD.choose(g, 1, TD.pending_options(g, 1)[0]["value"], ev) is None
    assert TD.pick_die(g, 0, "artist", ev) is None
    while g["pending"]:
        assert TD.choose(g, 0, TD.pending_options(g, 0)[0]["value"], ev) is None
    assert g["phase"] == "game_end"
    assert g["winner"] == 0  # A: 3*6=18 faith vs B: 1*1=1


def test_hot_spring_take_and_repeat():
    g = mk()
    p = g["players"][0]
    p["pilgrim_pos"] = 2  # move 1 -> station 3 hotspring
    _set_dice(g, {"pilgrim": 1, "merchant": 2, "artist": 2})
    _pick(g, 0, "pilgrim")
    assert g["hot_spring"] == 0
    # cannot use it on the same pick (no pending hotspring offered)
    assert not g["pending"] or g["pending"]["kind"] != "hotspring"
    # next round, A picks pilgrim again and uses the token after moving
    g["round"] = 2
    g["first_picker"] = 0
    _set_dice(g, {"pilgrim": 1, "merchant": 2, "artist": 2})
    p["pilgrim_pos"] = 4  # move 1 -> station 5 coastal
    _pick(g, 0, "pilgrim")
    assert g["pending"] and g["pending"]["kind"] == "hotspring"
    ev = []
    assert TD.choose(g, 0, "use", ev) is None
    # repeat move 1 -> station 6 seashore, which sets a wave_take pending
    # (or, if no waves left, advances) - token is consumed either way
    assert g["hot_spring"] is None
    assert p["pilgrim_pos"] == 6


def test_seashore_takes_wave():
    g = mk()
    p = g["players"][0]
    p["pilgrim_pos"] = 5  # move 1 -> station 6 seashore
    _set_dice(g, {"pilgrim": 1, "merchant": 2, "artist": 2})
    ev = []
    assert TD.pick_die(g, 0, "pilgrim", ev) is None
    assert g["pending"] and g["pending"]["kind"] == "wave_take"
    opt = TD.pending_options(g, 0)[0]["value"]
    assert TD.choose(g, 0, opt, ev) is None
    assert sum(1 for v in p["waves"].values() if v) == 1


def test_merchant_no_path():
    g = mk()
    p = g["players"][0]
    # merchant on c_0 (SE): neighbours only m_e; a 4-step simple path
    # exists, so use a value with no exact path by blocking: put the
    # merchant on a coastal town and use value 1 where the only neighbour
    # is occupied by a pilgrim on the coastal station + merchant there.
    # Simpler: value 1 from m_e with both neighbours blocked.
    p["merchant_pos"] = "m_e"
    g["players"][1]["merchant_pos"] = "c_31"
    g["players"][1]["pilgrim_pos"] = 0  # blocks c_0
    _set_dice(g, {"pilgrim": 1, "merchant": 1, "artist": 1})
    ev = []
    assert TD.pick_die(g, 0, "merchant", ev) is None
    # no destination: pick advances without a pending choice
    assert not g["pending"]
    assert g["pick_index"] == 1


def test_miniapp_shows_boutiques_and_waves_on_board():
    # FB-0010/FB-0011: ware+price at each coastal town and the face-up
    # Wave tiles must be rendered ON the board (.tdboard), not only in
    # the card underneath it.
    import os
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    start = js.index("let html = '<div class=\"tdboard\">'")
    end = js.index("html += '</div>';", start)
    board_html = js[start:end]
    assert "tdbout" in board_html and "package_pos" in board_html, board_html
    assert "tdwave" in board_html and "waves_board" in board_html, board_html
    assert "boutiques" in board_html


def test_boutique_pills_sit_over_package_symbols():
    # FB-0014: one package position per coastal town, each further from
    # the board centre than its town (the packages are at the board
    # edge), and the Mini App serves them in the board JSON.
    import math
    coastal = [t for t in TD.TOWN_POS if t.startswith("c_")]
    assert len(coastal) == 8
    assert set(TD.PACKAGE_POS) == set(coastal)
    for town in coastal:
        px, py = TD.PACKAGE_POS[town]
        assert 0 <= px <= 100 and 0 <= py <= 100, (town, px, py)
        tx, ty = TD.TOWN_POS[town]
        assert math.hypot(px - 50, py - 50) > math.hypot(tx - 50, ty - 50), town


def test_miniapp_notices_a_new_version():
    # FB-0026 (Altay, same cause): the Mini App never reloads its own
    # JS while open, and the ?v= cache-buster on tokaidoduo.js had not
    # been bumped — a fix could be live on the server while the player
    # still saw the old code with no hint why. The script tag must be
    # bumped when the file changes, and the Mini App must compare the
    # page's ?v= with the server version (/healthz) and tell the player
    # to close and reopen when a new version is out.
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    assert "tdCheckVer" in js
    assert "fetch('/healthz')" in js
    assert "TDG.webVer" in js
    assert "New version — reopen the Mini App" in js
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert 'src="tokaidoduo.js?v=7"' in html


def test_character_markers_use_bga_meeples_on_boutique_symbols():
    # FB-0024: when a Merchant or a Pilgrim is at a boutique, its marker
    # must sit on the boutique symbol (TOWN_POS), not drift towards the
    # wrapped-package symbol at the board edge (PACKAGE_POS, where the
    # boutique pill already sits). FB-0031: the markers are the BGA
    # character meeples from sources/tokaidoduo/bga/spriteMeeples.png
    # (pilgrim / merchant / artist down the columns, purple row on top,
    # green row below), served as web/tokaidoduo-meeples.webp — they
    # replace the FB-0025 character icons. The meeple already is the
    # player's colour (FB-0027); the ring and halo make it unmissable.
    from PIL import Image
    meeples = Image.open(os.path.join(os.path.dirname(__file__), "web",
                                      "tokaidoduo-meeples.webp"))
    assert meeples.size == (147, 119), meeples.size  # 3 meeples x 2 colours
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    start = js.index("let html = '<div class=\"tdboard\">'")
    end = js.index("html += '</div>';", start)
    board_html = js[start:end]
    # Markers are the character meeples, not emoji letters.
    assert "tdMeeple(sx" in board_html and "'pilgrim'" in board_html
    assert "tdMeeple(mTown[0]" in board_html and "'merchant'" in board_html
    assert "tdMeeple(zp[0]" in board_html and "'artist'" in board_html
    assert "'⛩'" not in board_html and "'$'" not in board_html
    # Merchant sits exactly on the town (boutique) symbol; pilgrim on a
    # coastal station sits on that town's boutique symbol too — the
    # meeple block must use town_pos, never package_pos.
    assert "const mTown = (g.town_pos || {})[p.merchant_pos]" in board_html
    assert "const pTownName = 'c_' + p.pilgrim_pos" in board_html
    meeples_js = board_html[board_html.index("g.players.forEach((p, i) => {"):
                            board_html.index("const zp = (g.zone_pos || [])[p.artist_zone];")]
    assert "town_pos" in meeples_js and "package_pos" not in meeples_js, meeples_js
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert ".tdmeeple{position:absolute;width:24px;height:30px;" in html
    assert "background-image:url(tokaidoduo-meeples.webp);background-size:300% 200%;" in html
    assert ".tdmeeple.tdpilgrim{background-position-x:0%}" in html
    assert ".tdmeeple.tdmerchant{background-position-x:50%}" in html
    assert ".tdmeeple.tdartist{background-position-x:100%}" in html
    assert ".tdmeeple.tdpurple{background-position-y:0%}" in html
    assert ".tdmeeple.tdgreen{background-position-y:100%}" in html
    # FB-0027: the player colour must be unmissable on the token — the
    # meeple itself is that colour, plus a coloured ring and halo.
    assert ".tdmeeple.tdpurple{border-color:#7c3aed;box-shadow:0 0 0 2px #7c3aedcc" in html
    assert ".tdmeeple.tdgreen{border-color:#059669;box-shadow:0 0 0 2px #059669cc" in html
    assert "border:3px solid #fff" in html
    # The old icon sprite is no longer the marker art.
    assert "tokaidoduo-icons.webp" not in html.split(".tdmeeple")[1].split("}")[0]
    assert "background-color:#7c3aed" not in html.split(".tdmeeple.tdpurple")[1].split("\n")[0]


def test_lobby_shows_bga_cover_art():
    # FB-0032: when the lobby is opened (/tokaidoduo), show the BGA
    # cover art from sources/tokaidoduo/bga/bg.jpg — as the Telegram
    # lobby photo (the bot's established cover mechanism: lobbies show
    # the game's box art as a photo with the board text as caption)
    # and as the Mini App lobby background.
    import bot as BOT
    import game_registry as GR
    from PIL import Image
    cover = Image.open(os.path.join(os.path.dirname(__file__), "web",
                                    "covers", "tokaidoduo.jpg"))
    src = Image.open(os.path.join(os.path.dirname(__file__), "sources",
                                  "tokaidoduo", "bga", "bg.jpg"))
    assert cover.size == src.size == (559, 488), (cover.size, src.size)
    assert GR.GAMES_BY_KEY["tokaidoduo"].cover == "tokaidoduo.jpg"
    path = BOT.cover_path("tokaidoduo")
    assert path and os.path.isfile(path), path
    bg = Image.open(os.path.join(os.path.dirname(__file__), "web",
                                 "tokaidoduo-bg.webp"))
    assert bg.size == (559, 488), bg.size
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert "url(tokaidoduo-bg.webp?v=1)" in html
    assert ".tdlobby{" in html and "tokaidoduo-bg.webp" in html.split(".tdlobby{")[1].split("}")[0]


def test_die_choice_buttons_show_die_faces():
    # FB-0033: when the player must choose the movement die, the button
    # shows the die face from sources/tokaidoduo/bga/spriteDes.jpg
    # next to e.g. "merchant (2)" — not just the text. The sprite is
    # 6 faces x 3 dice: Merchant (1/2/3/1/2/3) orange row, Artist
    # (1/2/3/1/1/2) gold row, Pilgrim (1/2/3/4/2/3) pink row.
    import ast
    import re
    from PIL import Image
    dice = Image.open(os.path.join(os.path.dirname(__file__), "web",
                                   "tokaidoduo-dice.webp"))
    assert dice.size == (240, 120), dice.size  # 6 faces of 40px x 3 dice
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    row = dict(re.findall(r"(\w+): (\d+)", js[js.index("const TD_DIE_ROW = "):
                                              js.index(";", js.index("const TD_DIE_ROW = "))]))
    row = {k: int(v) for k, v in row.items()}
    assert row == {"merchant": 0, "artist": 1, "pilgrim": 2}, row
    col = ast.literal_eval(js[js.index("const TD_DIE_COL = ") + len("const TD_DIE_COL = "):
                             js.index(";", js.index("const TD_DIE_COL = "))])
    assert col == {1: 0, 2: 1, 3: 2, 4: 3}, col
    # every face value of every die maps to a face in its row
    assert set(TD.DICE_FACES["pilgrim"]) == {1, 2, 3, 4}
    assert set(TD.DICE_FACES["merchant"]) == {1, 2, 3}
    assert set(TD.DICE_FACES["artist"]) == {1, 2, 3}
    for ch, faces in TD.DICE_FACES.items():
        for v in set(faces):
            assert v in col, (ch, v)
    # the pick-die buttons carry the face span before the text
    assert "tdDieFace(ch, g.dice[ch])" in js
    assert "b.innerHTML = tdDieFace(ch, g.dice[ch])" in js
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert ".tddie{display:inline-block;width:22px;height:22px;" in html
    assert "background-image:url(tokaidoduo-dice.webp);background-size:600% 300%;" in html


def test_miniapp_assets_are_served():
    # FB-0039: the Hot Spring token (and the Wave tiles) were invisible
    # on the board even though the art and the Mini App code were right:
    # bot.py's static allowlist never included
    # tokaidoduo-hotspring.webp / tokaidoduo-waves.webp, so the server
    # answered 404 and the token span rendered as an empty, near
    # invisible ring. Every tokaidoduo-*.webp the Mini App references
    # must be in the allowlist and exist on disk.
    import re
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    referenced = set(re.findall(r"tokaidoduo-[a-z]+\.webp", html + js))
    assert referenced, referenced
    src = open(os.path.join(os.path.dirname(__file__), "bot.py"),
               encoding="utf-8").read()
    served = set(re.findall(r'"/(tokaidoduo-[a-z]+\.webp)"', src))
    missing = referenced - served
    assert not missing, missing
    for name in sorted(referenced):
        path = os.path.join(os.path.dirname(__file__), "web", name)
        assert os.path.isfile(path), path


def test_player_seats_use_bga_player_boards():
    # FB-0034: the player boards are the BGA boards from
    # sources/tokaidoduo/bga/spritePlateauxJoueurs.png (two 862x213
    # boards: top half = first seat, bottom half = second), served as
    # web/tokaidoduo-pboards.webp, with the player's markers on the
    # printed tracks — culture dots, commerce on the gold row, temple
    # lanterns, garden circles, paintings in the printed slots.
    import ast
    import re
    from PIL import Image
    boards = Image.open(os.path.join(os.path.dirname(__file__), "web",
                                     "tokaidoduo-pboards.webp"))
    assert boards.size == (862, 426), boards.size
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()

    def _map(name):
        m = re.search(r"(?:const |, )" + name + r" = (\{[^}]*\}|\[[^\]]*\])", js)
        assert m, name
        return ast.literal_eval(m.group(1))
    assert sorted(_map("TD_CULTURE_POS")) == [0, 2, 4, 7, 10, 14, 18, 23, 28, 34, 40]
    assert sorted(_map("TD_GOLD_POS")) == [0, 5, 11, 18, 26, 35, 45]
    for name in ("TD_CULTURE_POS", "TD_GOLD_POS"):
        for x, y in _map(name).values():
            assert 0 <= x <= 862 and 0 <= y <= 213, (name, x, y)
    assert _map("TD_LANTERN_X") == [602, 645, 687]
    assert _map("TD_LANTERN_Y") == [58, 118, 178]
    assert _map("TD_GARDEN_Y") == [28, 60, 92, 123, 155, 185]
    # FB-0049: the 10 painting slots are the numbered boxes on the
    # Artist track (culture positions, reading order) — not the 5x2
    # grid in the middle of the board.
    culture = _map("TD_CULTURE_POS")
    m = re.search(r"const TD_PAINT_SLOT = \[([^\]]*)\]", js)
    assert m, "painting slot order"
    order = [int(v) for v in m.group(1).split(",")]
    assert order == [2, 4, 7, 10, 14, 18, 23, 28, 34, 40], order
    assert [culture[v] for v in order] == [
        [62, 58], [112, 58], [165, 58], [30, 118], [80, 118],
        [135, 118], [185, 118], [55, 180], [110, 180], [160, 180]]
    assert "TD_GARDEN_X = 735" in js
    # 10 painting slots, one per painting tile in the deck
    assert len(TD.PAINTING_TILES["purple"]) == 10
    assert len(TD.PAINTING_TILES["green"]) == 10
    # seats render the board strip (pb1 = bottom half for the 2nd seat)
    # with the markers on it, and the paintings live in the slots —
    # the old tdpaints strip under the seat is gone.
    assert "'<div class=\"tdpboard' + (i === 1 ? ' pb1' : '') + '\">' + tdSeatBoard(g, p, col)" in js
    assert "tdSeatBoard(g, p, col)" in js
    assert "'<div class=\"tdpaints\">' + p.paintings.map(tdPaintTile)" not in js
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert ".tdpboard{position:relative;aspect-ratio:862/213;" in html
    assert "background-image:url(tokaidoduo-pboards.webp);background-size:100% 200%;" in html
    assert ".tdpboard.pb1{background-position-y:100%}" in html
    assert ".tdmark{position:absolute;width:14px;height:14px;" in html
    assert ".tdpaintslot{position:absolute;width:4.6%;height:23.5%;transform:translate(-50%,-50%);background-image:url(tokaidoduo-paintings.webp);background-size:1000% 100%;" in html


def test_player_board_shows_coin_tokens():
    # FB-0048: the player's own board (plancia del singolo giocatore)
    # must show the coin tokens too — the real BGA 1-coin art from
    # spritePieces.png (tokaidoduo-pieces.webp, panel 1), in a single
    # row in the free band between the Merchant's ware slots (their
    # row 2 ends at y~118) and the printed "10 coin -> gold"
    # conversion (starts at y~148). The gold slabs are NOT in this
    # pile: per FB-0051 a slab marks the commerce tracker instead.
    # The board JSON already carries coins/gold per player.
    import re
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    assert '"coins": p["coins"], "gold": p["gold"]' in open(
        os.path.join(os.path.dirname(__file__), "bot.py"),
        encoding="utf-8").read()
    assert "const coins = Math.max(0, p.coins || 0);" in js
    assert "tdBoardCoin(1, TD_COIN_X0" in js  # 1-coin art, panel 1
    assert "tdBoardCoin(2, TD_COIN_X0" not in js  # no slabs in the pile
    assert "background-position-x:' + (idx * 50)" in js
    m = re.search(r"const TD_COIN_X0 = (\d+), TD_COIN_Y0 = (\d+), "
                  r"TD_COIN_D = (\d+), TD_COIN_PER_ROW = (\d+);", js)
    assert m, "coin grid constants"
    x0, y0, d, per_row = (int(v) for v in m.groups())
    # worst case on the board: 9 coins (10 auto-convert to a slab),
    # all in one row — every token centre stays on the 862x213 board
    # with its 10px half-size inside. The row starts right of the
    # Artist's robe (right edge x~263 at y~140, measured off the board
    # art) so no token sits on the character, it clears the ware
    # slots above (row 2 ends y~118) and the printed coin icons
    # below (start y~148), and it ends above the gold row (y=196).
    assert per_row >= 9, per_row
    for i in range(9):
        x = x0 + (i % per_row) * d
        y = y0 + (i // per_row) * d
        assert 10 <= x <= 862 - 10 and 10 <= y <= 213 - 10, (i, x, y)
    assert x0 - 10 > 263, x0  # clears the Artist's robe
    assert y0 - 10 > 118, y0  # below the ware slots
    assert y0 + 10 < 148, y0  # above the printed coin icons
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert ".tdboardcoin{position:absolute;width:20px;height:20px;" in html
    assert "background-image:url(tokaidoduo-pieces.webp);background-size:300% 100%;" in html


def test_player_board_shows_ware_tokens():
    # FB-0050: the Merchant section of each player's own board must
    # show the Ware tokens the player holds in inventory — the real
    # BGA merchandise tokens from spriteJetonsMarchandise.jpg
    # (tokaidoduo-marchandise.webp: 4 panels — pottery, doll, fan,
    # kimono). Verified against live BGA tables: they sit in the
    # Merchant's 6 printed ware slots — the light-grey octagonal
    # squares with the bundle icon at the top-left of the Merchant
    # section (3 columns x 2 rows), in inventory order, top row
    # first — not in a row above the Merchant character.
    import re
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    m = re.search(r"const TD_MARCH_IDX = \{([^}]*)\};", js)
    assert m, "merchandise panel index"
    idx = dict((k.strip(), int(v)) for k, v in
               (kv.split(":") for kv in m.group(1).split(",")))
    assert sorted(idx) == sorted(TD.WARE_TYPES), idx
    assert len(set(idx.values())) == 4
    assert "(p.wares || []).forEach((w, idx) => {" in js
    assert "if (idx >= 6) return;" in js
    assert "TD_MARCH_IDX[w]" in js
    assert '"tdwareslot"' in js
    assert '"tdwaretok"' not in js  # the row above the Merchant is gone
    assert "TD_WARE_SLOT_X[idx % 3]" in js
    assert "TD_WARE_SLOT_Y[Math.floor(idx / 3)]" in js
    m = re.search(r"const TD_WARE_SLOT_X = \[([^\]]*)\], "
                  r"TD_WARE_SLOT_Y = \[([^\]]*)\];", js)
    assert m, "ware slot constants"
    xs = [int(v) for v in m.group(1).split(",")]
    ys = [int(v) for v in m.group(2).split(",")]
    assert len(xs) == 3 and len(ys) == 2, (xs, ys)
    # every slot centre stays on the 862x213 board with the 20px
    # half-size of the 40x40 token inside; the slots are the printed
    # grey squares (bundle icons measured at x~328/383/437, y~45/98).
    for x in xs:
        for y in ys:
            assert 20 <= x <= 862 - 20 and 20 <= y <= 213 - 20, (x, y)
    assert xs == [329, 384, 439] and ys == [45, 98], (xs, ys)
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert ".tdwareslot{position:absolute;width:40px;height:40px;" in html
    assert "background-image:url(tokaidoduo-marchandise.webp);background-size:400% 100%;" in html
    bot = open(os.path.join(os.path.dirname(__file__), "bot.py"),
               encoding="utf-8").read()
    assert '"/tokaidoduo-marchandise.webp"' in bot


def test_gold_slab_marks_commerce_tracker():
    # FB-0051: the 10-coin token (gold slab) must sit at the Merchant's
    # score tracker — the gold row. The commerce score is exactly the
    # gold-slab count mapped to points, so the slab token replaces the
    # plain dot as the marker on the gold row.
    import ast
    import re
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    assert "s += tdBoardCoin(2, go[0], go[1], 'Commerce ' + p.commerce" in js
    assert "tdMark(go[0], go[1]" not in js  # the dot is gone here
    m = re.search(r"const TD_GOLD_POS = (\{[^}]*\})", js)
    assert m, "gold row positions"
    assert sorted(ast.literal_eval(m.group(1))) == [0, 5, 11, 18, 26, 35, 45]
    assert sorted(TD.GOLD_POINTS) == [0, 5, 11, 18, 26, 35, 45]
    # the positions are the measured centres of the printed numerals
    # on the gold row (FB-0034's 55px pitch drifted up to 52px right
    # of the numeral — the slab at commerce 18 floated between 11
    # and 18); 0 is one ~47px pitch left of 5.
    assert ast.literal_eval(m.group(1)) == {
        0: [266, 196], 5: [313, 196], 11: [361, 196], 18: [406, 196],
        26: [453, 196], 35: [501, 196], 45: [546, 196]}


def test_hot_spring_token_shows_on_board():
    # FB-0028 / FB-0040 / FB-0041: the Hot Spring token must be visible
    # ON the board always — not only while a player holds it. It sits
    # on its drawn place: the large dashed hot-spring circle at the
    # bottom-left of the board art (board 789x1600, centre ~x=105,
    # y=1303), with the holder's colour ring, like the character
    # tokens; while nobody holds it (every fresh game) it shows with
    # a grey ring, so it never looks missing.
    # FB-0046: the token art is the real BGA art from
    # sources/tokaidoduo/bga/spritePieces.png (panel 0 of
    # tokaidoduo-pieces.webp), not the hotspring.jpg art used before.
    from PIL import Image
    tok = Image.open(os.path.join(os.path.dirname(__file__), "web",
                                  "tokaidoduo-pieces.webp"))
    assert tok.size == (216, 91), tok.size  # 3 panels: hot spring, coin, gold
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    start = js.index("let html = '<div class=\"tdboard\">'")
    end = js.index("html += '</div>';", start)
    board_html = js[start:end]
    assert "tdhotspring" in board_html and "hot_spring" in board_html, board_html
    assert "top:81.4%;left:13.3%" in board_html
    assert "g.players[g.hot_spring]" in board_html
    assert "' td' + (hp.color" in board_html  # held: 'td' + colour class
    assert "'purple' ? 'purple' : 'green'" in board_html
    # The token is rendered unconditionally now: the span is added
    # outside any hot_spring if-gate, with an unclaimed branch.
    assert "if (g.hot_spring" not in board_html
    assert "nobody holds it yet" in board_html
    # Unclaimed it gets a grey ring (tdnone) so it reads on the light
    # board instead of relying on the plain white border.
    assert "' tdnone'" in board_html
    # The card under the board also always names the token's state.
    assert "Hot Spring: ' + (g.hot_spring !== null" in js
    assert "nobody holds it yet" in js
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert ".tdhotspring{position:absolute;width:40px;height:40px;" in html
    assert "background-image:url(tokaidoduo-pieces.webp);background-size:300% 100%;" in html
    assert ".tdhotspring.tdpurple{border-color:#7c3aed" in html
    assert ".tdhotspring.tdgreen{border-color:#059669" in html
    # Unclaimed it gets a grey ring (tdnone) so it reads on the light
    # board instead of relying on the plain white border.
    assert ".tdhotspring.tdnone{border-color:#64748b" in html


def test_pending_move_options_carry_board_positions():
    # FB-0015: tap the board to move — every move option must map to a
    # spot on the board: pilgrim options carry their landing station,
    # merchant/artist options name a town/zone with a known position.
    g = mk()
    g["pending"] = {"kind": "pilgrim_wave", "by": 0, "options": [2, 3]}
    opts = TD.pending_options(g, 0)
    assert len(opts) == 2
    for o in opts:
        d = int(o["value"][5:])
        assert o["station"] == TD.pilgrim_destinations(g, 0, d)
        assert 0 <= o["station"] < len(TD.STATIONS)
    g["pending"] = {"kind": "merchant_dest", "by": 0, "options": ["c_0", "c_4"]}
    for o in TD.pending_options(g, 0):
        assert o["value"][5:] in TD.TOWN_POS
    g["pending"] = {"kind": "artist_dest", "by": 0, "options": [1, 3]}
    for o in TD.pending_options(g, 0):
        assert 0 <= int(o["value"][5:]) < len(TD.ZONE_POS)
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    start = js.index("let html = '<div class=\"tdboard\">'")
    end = js.index("html += '</div>';", start)
    assert "tdtap" in js[start:end] and "data-tap" in js[start:end]


def test_wave_tokens_show_on_board_slots():
    # FB-0029: the face-up Wave tiles must sit ON the board as real
    # tokens (BGA art from sources/tokaidoduo/bga/spriteVagues.jpg),
    # one per character in the three dashed slots at the top of the
    # board — not as a text strip. A tile leaves its slot once taken.
    from PIL import Image
    waves = Image.open(os.path.join(os.path.dirname(__file__), "web",
                                    "tokaidoduo-waves.webp"))
    assert waves.size == (1464, 328), waves.size  # 6 tiles of 244x328
    assert set(TD.WAVE_POS) == {"pilgrim", "merchant", "artist"}
    xs = [TD.WAVE_POS[ch][0] for ch in ("pilgrim", "merchant", "artist")]
    assert xs == sorted(xs)  # slots left to right, one per character
    for ch, (x, y) in TD.WAVE_POS.items():
        assert 0 <= x <= 100 and 0 <= y <= 100, (ch, x, y)
    # every Wave side maps to exactly one sprite tile, 0..5
    assert set(TD.WAVE_SPRITE) == {"pilgrim", "merchant", "artist"}
    idxs = [i for sides in TD.WAVE_SPRITE.values() for i in sides.values()]
    assert sorted(idxs) == list(range(6))
    for ch, sides in TD.WAVES.items():
        assert {name for name, _ in sides} == set(TD.WAVE_SPRITE[ch])
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    start = js.index("let html = '<div class=\"tdboard\">'")
    end = js.index("html += '</div>';", start)
    board_html = js[start:end]
    assert "tdwavetok" in board_html and "waves_board" in board_html
    assert "wave_pos" in board_html and "TD_WAVE_IDX" in board_html
    assert '<div class="tdwaves">' not in js  # text strip replaced
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert ".tdwavetok{position:absolute;width:36px;height:48px;" in html
    assert "background-image:url(tokaidoduo-waves.webp);background-size:600% 100%;" in html
    assert ".tdwave0{background-position:0% 0}" in html
    assert ".tdwave5{background-position:100% 0}" in html
    # a taken Wave leaves the board: no tile of that character remains
    g = mk()
    assert len(g["waves_board"]) == 3
    g["waves_board"] = [w for w in g["waves_board"] if w["char"] != "pilgrim"]
    assert all(w["char"] != "pilgrim" for w in g["waves_board"])


def test_cancel_pick_returns_die_to_pool():
    # FB-0030: after choosing a die, while the move is still a pending
    # destination choice (meeple not moved yet), the player can cancel
    # the pick — the die goes back in the pool and they pick again.
    g = mk()
    _set_dice(g, {"pilgrim": 1, "merchant": 2, "artist": 2})
    _pick(g, 0, "merchant")
    assert g["pending"] and g["pending"]["kind"] == "merchant_dest"
    assert g["dice_taken"] == ["merchant"]
    ev = []
    assert TD.cancel_pick(g, 0, ev) is None
    assert g["pending"] is None
    assert g["dice_taken"] == []
    assert g["pick_char"] is None and g["pick_value"] == 0
    assert g["pick_index"] == 0
    assert "merchant" in TD.available_dice(g)
    assert "back in the pool" in ev[-1]
    # re-picking the same die works and reaches the same choice
    _pick(g, 0, "merchant")
    assert g["pending"] and g["pending"]["kind"] == "merchant_dest"


def test_cancel_pick_rejected_once_move_is_done():
    # FB-0030: once the move has executed (single-option pick moves at
    # once, no pending choice), the pick is committed — no cancelling.
    g = mk()
    _set_dice(g, {"pilgrim": 1, "merchant": 2, "artist": 2})
    _pick(g, 0, "pilgrim")
    assert not g["pending"]
    assert g["pick_index"] == 1
    ev = []
    err = TD.cancel_pick(g, 0, ev)
    assert err and "Nothing to cancel" in err
    assert g["dice_taken"] == ["pilgrim"]
    assert g["pick_index"] == 1
    # a pending choice that comes AFTER the move (here: taking a Wave
    # on the seashore) is committed too — cancelling must not undo it.
    g2 = mk()
    g2["players"][0]["pilgrim_pos"] = 5  # move 1 -> station 6 seashore
    _set_dice(g2, {"pilgrim": 1, "merchant": 2, "artist": 2})
    _pick(g2, 0, "pilgrim")
    assert g2["pending"] and g2["pending"]["kind"] == "wave_take"
    err = TD.cancel_pick(g2, 0, [])
    assert err and "already done" in err
    assert g2["pending"] and g2["pending"]["kind"] == "wave_take"
    assert g2["dice_taken"] == ["pilgrim"]


def test_cancel_pick_restores_hot_spring_token():
    # FB-0030: cancelling a Hot Spring repeat gives the token back —
    # the player must not lose it for changing their mind mid-repeat.
    g = mk()
    p = g["players"][0]
    g["hot_spring"] = 0
    g["hot_spring_gained"] = (1, 99)  # gained on an earlier pick
    _set_dice(g, {"pilgrim": 1, "merchant": 2, "artist": 2})
    _pick(g, 0, "merchant")  # c_0 -> m_c (mountain draw), then offer
    assert g["pending"] and g["pending"]["kind"] == "merchant_dest"
    ev = []
    assert TD.choose(g, 0, "dest:m_c", ev) is None
    assert g["pending"] and g["pending"]["kind"] == "hotspring"
    assert TD.choose(g, 0, "use", ev) is None
    assert g["hot_spring"] is None
    assert g["pending"] and g["pending"]["kind"] == "merchant_dest"
    assert TD.cancel_pick(g, 0, ev) is None
    assert g["hot_spring"] == 0  # token back
    assert g["dice_taken"] == []
    assert g["pending"] is None
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    assert "↩️ Cancel move" in js and "tdMove('cancel'" in js
    assert "TD_CANCELLABLE" in js


def test_board_lines_show_boutiques_and_wave_abilities():
    g = mk()
    lines = TD.board_lines(g)
    assert any("🏘️ Sell:" in ln for ln in lines), lines
    assert any("🌊 Waves on board:" in ln for ln in lines), lines
    # every Wave side has ability text (surfaced in the Mini App)
    assert len(TD.WAVES) == 3
    assert all(len(v) == 2 and all(t for _, t in v) for v in TD.WAVES.values())


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
