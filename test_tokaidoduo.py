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
    assert _map("TD_PAINT_X") == [278, 333, 388, 443, 498]
    assert _map("TD_PAINT_Y") == [32, 88]
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
    assert ".tdpaintslot{position:absolute;width:6.4%;height:19%;" in html


def test_hot_spring_token_shows_on_board():
    # FB-0028 / FB-0040 / FB-0041: the Hot Spring token (BGA art from
    # sources/tokaidoduo/bga/hotspring.jpg) must be visible ON the board
    # always — not only while a player holds it. It sits on its drawn
    # place: the large dashed hot-spring circle at the bottom-left of
    # the board art (board 789x1600, centre ~x=105, y=1303), with the
    # holder's colour ring, like the character tokens; while nobody
    # holds it (every fresh game) it shows with a grey ring, so it
    # never looks missing.
    from PIL import Image
    tok = Image.open(os.path.join(os.path.dirname(__file__), "web",
                                  "tokaidoduo-hotspring.webp"))
    assert tok.size == (288, 288), tok.size  # tight crop of the round token
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
    assert "background:url(tokaidoduo-hotspring.webp) center/cover;" in html
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
