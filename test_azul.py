"""Engine tests for Azul. Run: python3 test_azul.py (or pytest test_azul.py)."""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import azul as A


def mk(n=2, seed=4):
    random.seed(seed)
    g = A.new_game(-100, 1, "Ada")
    for i in range(2, n + 1):
        g["players"].append(A.new_player(i, "P" + str(i)))
    ev = []
    assert A.start_game(g, ev) is None
    return g, ev


def test_bag_and_setup():
    bag = A.build_bag()
    assert len(bag) == 100
    for c in A.COLORS:
        assert bag.count(c) == 20
    for players, factories, bag in ((2, 5, 80), (3, 7, 72), (4, 9, 64)):
        g, ev = mk(players)
        assert g["phase"] == "draft" and g["round"] == 1
        assert len(g["factories"]) == factories
        assert all(len(f) == 4 for f in g["factories"])
        assert len(g["bag"]) == bag and g["marker_center"] is True
        assert g["current"] == 0 and g["center"] == []
        json.dumps(g)


def test_take_from_factory_slides_rest_to_center():
    g, ev = mk()
    g["factories"][0] = ["red", "red", "blue", "yellow"]
    before = list(g["center"])
    assert A.take_tiles(g, 0, "factory", 0, "red", ev) is None
    assert g["pending"]["tiles"] == ["red", "red"]
    assert g["factories"][0] == []
    assert g["center"] == before + ["blue", "yellow"]
    assert "place the tiles you just picked first" in A.take_tiles(g, 1, "factory", 1, "blue", ev)
    assert A.place_tiles(g, 0, 0, ev) is None
    assert "not your turn" in A.take_tiles(g, 0, "factory", 1, "blue", ev)
    assert g["current"] == 1


def test_pattern_lines_and_overflow():
    g, ev = mk()
    g["pending"] = {"by": 0, "color": "blue", "tiles": ["blue"] * 3,
                    "marker": False, "source": "factory", "source_index": 0}
    assert A.place_tiles(g, 0, 0, ev) is None
    p = g["players"][0]
    assert p["pattern"][0] == ["blue"]
    assert p["floor"] == ["blue", "blue"]
    g["pending"] = {"by": 0, "color": "red", "tiles": ["red"],
                    "marker": False, "source": "factory", "source_index": 0}
    assert "already holds blue" in A.place_tiles(g, 0, 0, ev)
    assert A.place_tiles(g, 0, 1, ev) is None
    assert len(g["players"][0]["pattern"][1]) == 1
    # full floor: extras are discarded to the lid (7 spaces total)
    g["pending"] = {"by": 0, "color": "red", "tiles": ["red"] * 5,
                    "marker": False, "source": "factory", "source_index": 0}
    assert A.place_tiles(g, 0, -1, ev) is None
    assert len(g["players"][0]["floor"]) == 7


def test_marker_counts_toward_floor_limit():
    g, ev = mk()
    p = g["players"][0]
    g["pending"] = {"by": 0, "color": "red", "tiles": ["red"] * 7,
                    "marker": True, "source": "center", "source_index": 0}
    assert A.place_tiles(g, 0, -1, ev) is None
    assert len(p["floor"]) == len(A.FLOOR_PENALTIES)
    assert p["floor"].count(A.MARKER) == 1
    assert p["floor"].count("red") == 6
    assert g["lid"].count("red") == 1


def test_wall_colors_block_pattern_rows():
    g, ev = mk()
    p = g["players"][0]
    c = A.wall_column(2, "yellow")
    p["wall"][2][c] = "yellow"
    assert 2 not in A.rows_for(g, 0, "yellow")
    g["pending"] = {"by": 0, "color": "yellow", "tiles": ["yellow"],
                    "marker": False, "source": "factory", "source_index": 0}
    assert "already on wall row 3" in A.place_tiles(g, 0, 2, ev)


def test_center_marker_rules():
    g, ev = mk()
    g["center"] = []
    g["factories"] = [["red"] if i == 1 else [] for i in range(len(g["factories"]))]
    assert A.take_options(g) == [{"source": "factory", "index": 1,
                                   "color": "red", "count": 1}]
    assert "not available there" in A.take_tiles(g, 0, "center", 0, A.MARKER, ev)
    g["factories"] = [[] for _ in g["factories"]]
    assert A.take_options(g) == []
    # taking a colour from the centre also takes the marker
    g["marker_center"] = True
    g["center"] = ["blue", "blue", "yellow"]
    assert A.take_tiles(g, 0, "center", 0, "blue", ev) is None
    assert g["pending"]["tiles"] == ["blue", "blue"]
    assert g["pending"]["marker"] is True
    assert g["center"] == ["yellow"] and not g["marker_center"]


def test_marker_left_in_center_keeps_first_player():
    g, ev = mk()
    g["factories"] = [[] for _ in g["factories"]]
    g["center"] = []
    g["pending"] = {"by": 0, "color": "blue", "tiles": ["blue"],
                    "marker": False, "source": "factory", "source_index": 0}
    assert A.place_tiles(g, 0, 0, ev) is None
    assert g["round"] == 2 and g["marker_center"] is True
    assert g["first_player"] == 0 and g["current"] == 0


def test_wall_tiling_scoring():
    g, ev = mk()
    p = g["players"][0]
    # row 0: place blue next to an existing blue -> horizontal group of 2
    p["wall"][0][1] = "blue"
    p["pattern"][0] = ["blue"]
    # row 1: isolated yellow -> 1 point
    p["pattern"][1] = ["yellow"] * 2
    # row 2: red with a red above it in column 3 -> vertical group of 2
    p["wall"][1][4] = "red"
    p["pattern"][2] = ["red"] * 3
    g["factories"] = [[] for _ in range(9)]
    g["center"] = []
    g["marker_center"] = False
    A._resolve_round(g, ev)
    assert p["score"] == 2 + 1 + 2, (p["score"], ev)
    assert p["pattern"] == [[] for _ in range(5)]
    assert p["wall"][0][0] == "blue"
    assert p["wall"][1][A.wall_column(1, "yellow")] == "yellow"
    assert p["wall"][2][4] == "red"
    assert p["last_round"] == 5
    assert g["phase"] == "draft" and g["round"] == 2


def test_floor_penalty_and_clamp():
    g, ev = mk()
    p = g["players"][0]
    g["factories"] = [[] for _ in range(9)]
    g["center"] = []
    g["marker_center"] = False
    p["floor"] = [A.MARKER] + ["red"] * 6  # -14 total
    p["score"] = 5
    A._resolve_round(g, ev)
    assert p["score"] == 0 and p["floor"] == []
    assert g["first_player"] == 0
    p2 = g["players"][1]
    p2["floor"] = ["blue"]
    p2["score"] = 10
    A._resolve_round(g, ev)
    assert p2["score"] == 9 and g["first_player"] == 0


def test_end_game_bonuses_and_tiebreak():
    g, ev = mk()
    for p in g["players"]:
        p["wall"] = [[A.COLORS[A.WALL[r][c]] for c in range(5)] for r in range(5)]
    g["players"][1]["wall"][2][2] = None  # fewer sets, still full rows? no -> fewer rows
    A._end_game(g, ev)
    assert g["phase"] == "game_end"
    assert g["players"][0]["score"] == 5 * 2 + 5 * 7 + 5 * 10
    assert g["winners"] == [0] and g["winner_id"] == 1, (g["winners"], ev)
    # tie -> shared win (remove same tile from both)
    g2, ev2 = mk()
    for p in g2["players"]:
        p["wall"] = [[A.COLORS[A.WALL[r][c]] for c in range(5)] for r in range(5)]
        p["wall"][0][0] = None
    A._end_game(g2, ev2)
    assert g2["winner_id"] is None and len(g2["winners"]) == 2


def test_full_game_simulation():
    g, ev = mk(3, seed=13)
    turns = 0
    while g["phase"] == "draft" and turns < 2000:
        idx = g["current"]
        opts = A.take_options(g)
        assert opts, (g["round"], ev[-5:])
        best = max(opts, key=lambda o: (o["color"] != A.MARKER,
                                        o["count"] * len(A.rows_for(g, idx, o["color"]))))
        assert A.take_tiles(g, idx, best["source"], best["index"], best["color"], ev) is None
        color = best["color"]
        rows = A.rows_for(g, idx, color) if color in A.COLORS else []
        row = rows[-1] if rows else -1
        assert A.place_tiles(g, idx, row, ev) is None
        turns += 1
    assert g["phase"] == "game_end", (turns, ev[-10:])
    assert g["winners"] and 2 <= g["round"] <= 20
    assert len(set(g["winners"])) == len(g["winners"])
    assert any(p["score"] > 0 for p in g["players"])
    assert "🔷" in A.board_lines(g)
    json.dumps(g)


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print("All", len(tests), "tests passed")
