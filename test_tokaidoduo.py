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
    assert 'src="tokaidoduo.js?v=4"' in html


def test_character_markers_use_bga_icons_on_boutique_symbols():
    # FB-0024: when a Merchant or a Pilgrim is at a boutique, its marker
    # must sit on the boutique symbol (TOWN_POS), not drift towards the
    # wrapped-package symbol at the board edge (PACKAGE_POS, where the
    # boutique pill already sits). FB-0025: the markers are the BGA
    # character tokens from sources/tokaidoduo/bga/spriteIcons.png
    # (parasol / merchant grid / paintbrush), served as
    # web/tokaidoduo-icons.webp, with the player colour as the ring.
    from PIL import Image
    icons = Image.open(os.path.join(os.path.dirname(__file__), "web",
                                    "tokaidoduo-icons.webp"))
    assert icons.size == (141, 47), icons.size  # 3 icons of 47px
    js = open(os.path.join(os.path.dirname(__file__), "web", "tokaidoduo.js"),
              encoding="utf-8").read()
    start = js.index("let html = '<div class=\"tdboard\">'")
    end = js.index("html += '</div>';", start)
    board_html = js[start:end]
    # Markers are the character icons, not emoji letters.
    assert "tdMeeple(sx" in board_html and "'pilgrim'" in board_html
    assert "tdMeeple(mTown[0]" in board_html and "'merchant'" in board_html
    assert "tdMeeple(zp[0]" in board_html and "'artist'" in board_html
    assert "'⛩'" not in board_html and "'$'" not in board_html
    # Merchant sits exactly on the town (boutique) symbol; pilgrim on a
    # coastal station sits on that town's boutique symbol too — the
    # meeple block must use town_pos, never package_pos.
    assert "const mTown = (g.town_pos || {})[p.merchant_pos]" in board_html
    assert "const pTownName = 'c_' + p.pilgrim_pos" in board_html
    meeples = board_html[board_html.index("g.players.forEach((p, i) => {"):
                         board_html.index("const zp = (g.zone_pos || [])[p.artist_zone];")]
    assert "town_pos" in meeples and "package_pos" not in meeples, meeples
    html = open(os.path.join(os.path.dirname(__file__), "web", "flip7.html"),
                encoding="utf-8").read()
    assert ".tdmeeple{position:absolute;width:26px;height:26px;" in html
    assert "background-image:url(tokaidoduo-icons.webp);background-size:300% 100%;" in html
    assert ".tdmeeple.tdpilgrim{background-position:0% 0}" in html
    assert ".tdmeeple.tdmerchant{background-position:50% 0}" in html
    assert ".tdmeeple.tdartist{background-position:100% 0}" in html
    assert ".tdmeeple.tdpurple{border-color:#7c3aed}" in html
    assert ".tdmeeple.tdgreen{border-color:#059669}" in html
    # FB-0027: the player colour must be unmissable on the token — the
    # whole disc is filled with it (the icon has transparent parts) and
    # it gets a coloured halo, not just a thin ring.
    assert ".tdmeeple.tdpurple{background-color:#7c3aed;box-shadow:0 0 0 2px #7c3aedcc" in html
    assert ".tdmeeple.tdgreen{background-color:#059669;box-shadow:0 0 0 2px #059669cc" in html
    assert "border:4px solid #fff" in html


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
