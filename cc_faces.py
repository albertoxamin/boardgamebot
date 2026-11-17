#!/usr/bin/env python3
"""Generate web/castlecombo-faces.js from the engine's CARDS table.

Each card face is a list of segment lines for the ability area and the
scoring area, in the spirit of BGA's HTML faces (icons + short text):
  {"i": "<icon>", ...}   icon segment
  {"t": "..."}           text segment

Icon keys and params:
  gold q=0..3       coin icon (gold-icons.png, 4 cols)
  key               key icon (key-icons.png)
  sh c=0..6         single shield, BGA colour row (0 = double-shield mark)
  dir k=line|col|lc c=1..6   direction shield (direction-shield-icons.png)
  pos t=0|123|456|789|147|258|369|1379|2468  position icon
  pt q=-1|1..10|12  point icon (point-icons.png, 12 cols)
  ban t=1|2|12      castle/village banner (card-type-icons.png)
  disc t=1|2|12     discount icon (discount-icons.png)
  purse             purse icon (card-icons.png col 0)
  flip              face-down icon (card-icons.png col 7)
  shset t=0|246|135|14|25|36  shield-combo icon (shields-icons.png)

BGA shield colour rows (from direction-shield-icons.png + BGA HTML):
  0 special/double, 1 blue, 2 purple, 3 green, 4 red, 5 orange, 6 yellow.
The engine uses 1=red 2=orange 3=blue 4=purple 5=green 6=yellow, so:
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import castlecombo as CC  # noqa: E402

# engine colour -> BGA icon row
BGA_SH = {CC.RED: 4, CC.ORANGE: 5, CC.BLUE: 1, CC.PURPLE: 2,
          CC.GREEN: 3, CC.YELLOW: 6}

# position icon types
_POS_KEYS = {(1, 2, 3): "123", (4, 5, 6): "456", (7, 8, 9): "789",
             (1, 4, 7): "147", (2, 5, 8): "258", (3, 6, 9): "369",
             (1, 3, 7, 9): "1379", (2, 4, 6, 8): "2468"}

_SH_NAME = {CC.RED: "red", CC.ORANGE: "orange", CC.BLUE: "blue",
            CC.PURPLE: "purple", CC.GREEN: "green", CC.YELLOW: "yellow"}


def _gold(n):
    return {"i": "gold", "q": max(0, min(3, n))}


def seg_t(s):
    return {"t": s}


def _sh(cond):
    return {"i": "sh", "c": BGA_SH[cond]}


def cond_segs(cond):
    """Icon/text segments for a scoring/ability condition."""
    if isinstance(cond, int):
        return [_sh(cond)]
    if isinstance(cond, str):
        if cond == "diff":
            return [{"i": "shset", "t": 0}]
        if cond == "pmiss":
            return [{"i": "shset", "t": 0}]
        return [seg_t(cond)]
    head = cond[0]
    if head == "b":
        return [{"i": "ban", "t": cond[1]}]
    if head == "single":
        return [seg_t("cards with 1 shield")]
    if head == "double":
        return [{"i": "shset", "t": 0}]
    if head == "cost":
        v = cond[1]
        if v in (0, 4, 5, -1):
            return [{"i": "card", "t": "cost", "v": v}]
        return [seg_t(f"costing {v} gold")]
    if head == "purse":
        return [{"i": "purse"}]
    if head == "disc":
        return [{"i": "disc", "t": 12}]
    if head == "empty":
        return [seg_t("empty"), {"i": "pos", "t": 0}]
    if head == "full":
        return [seg_t("full"), {"i": "pos", "t": 0}]
    if head == "flip":
        return [{"i": "flip"}]
    return [seg_t(str(cond))]


def _reward(res, n):
    if res == "gold":
        return [_gold(n)]
    if res == "keys":
        return [{"i": "key"} for _ in range(min(n, 4))]
    return [_gold(n)]


def ab_line(ab):
    """One ability line: list of segments."""
    kind = ab[0]
    if kind == "g":
        return _reward("gold", ab[2]) + [seg_t("per")] + cond_segs(ab[1])
    if kind == "k":
        return _reward("keys", ab[2]) + [seg_t("per")] + cond_segs(ab[1])
    if kind == "gsum":
        segs = _reward("gold", ab[2]) + [seg_t("per")]
        for i, c in enumerate(ab[1]):
            if i:
                segs.append(seg_t("+"))
            segs += cond_segs(c)
        return segs
    if kind == "gain":
        return [seg_t("gain")] + _reward(ab[1], ab[2])
    if kind == "opp":
        return [seg_t("opponents gain")] + _reward(ab[1], ab[2])
    if kind == "allk":
        return [seg_t("all players gain")] + _reward("keys", ab[1])
    if kind == "purses":
        return [{"i": "purse"}, seg_t("gets"), _gold(ab[1])]
    if kind == "purse2":
        return [seg_t("fill purses with"), _gold(2)]
    if kind == "drop":
        return [seg_t("discard a"), {"i": "ban", "t": ab[1]},
                seg_t("card, gain its cost")]
    if kind == "nb":
        cond, res, n = ab[1], ab[2], ab[3]
        return (_reward(res, n) + [seg_t("per")] + cond_segs(cond) +
                [seg_t("of a neighbour")])
    return [seg_t(str(ab))]


def ab_lines(ab):
    if not ab:
        return []
    if ab[0] == "and":
        return [ab_line(a) for a in ab[1]]
    if ab[0] == "or":
        lines = [ab_line(a) for a in ab[1]]
        for ln in lines[1:]:
            ln.insert(0, seg_t("or"))
        return lines
    return [ab_line(ab)]


def _pt(n):
    return {"i": "pt", "q": n}


def _dir(where):
    return {"row": "line", "col": "col", "rc": "lc"}.get(where)


def sc_line(sc):
    kind = sc[0]
    if kind == "sh":
        where, c, n = sc[1], sc[2], sc[3]
        d = _dir(where)
        icon = {"i": "dir", "k": d, "c": BGA_SH[c]} if d else _sh(c)
        return [_pt(n), seg_t("per"), icon]
    if kind == "pos":
        slots, n = tuple(sc[1]), sc[2]
        t = _POS_KEYS.get(slots, "1379" if len(slots) > 2 else "123")
        return [_pt(n), seg_t("in"), {"i": "pos", "t": t}]
    if kind == "purse":
        cap, n = sc[1], sc[2]
        return [_pt(n), seg_t(f"per gold on purse (max {cap})")]
    if kind == "cnt":
        return [_pt(sc[2]), seg_t("per")] + cond_segs(sc[1])
    if kind == "miss":
        return [_pt(sc[2]), seg_t("if no"), _sh(sc[1])]
    if kind == "pmiss":
        return [_pt(sc[1]), seg_t("per missing shield type")]
    if kind == "diff":
        where, n = sc[1], sc[2]
        where_t = {"row": "in a row", "col": "in a column", "all": ""}[where]
        segs = [_pt(n), seg_t("per different shield type")]
        if where_t:
            segs.append(seg_t(where_t))
        return segs
    if kind == "pair":
        return [_pt(sc[3]), seg_t("per"), _sh(sc[1]), _sh(sc[2]), seg_t("pair")]
    if kind == "pair_b":
        return [_pt(sc[1]), seg_t("per"), {"i": "ban", "t": 1},
                {"i": "ban", "t": 2}, seg_t("pair")]
    if kind == "tri":
        return [_pt(sc[4]), seg_t("per"), _sh(sc[1]), _sh(sc[2]), _sh(sc[3]),
                seg_t("set")]
    if kind == "sets":
        return [_pt(sc[1]), seg_t("per set of 3 matching shields")]
    if kind == "bset":
        return [_pt(sc[2]), seg_t("per set of 3"),
                {"i": "ban", "t": sc[1]}, seg_t("banners")]
    if kind == "keys":
        return [_pt(sc[1]), seg_t("per"), {"i": "key"}]
    if kind == "flany":
        return [_pt(sc[1]), seg_t("if you have a"), {"i": "flip"},
                seg_t("card")]
    if kind == "pall":
        return [_pt(sc[1]), seg_t("per stored gold")]
    if kind == "prich":
        return [_pt(sc[1]), seg_t(f"per purse holding {sc[1]}+ gold")]
    return [_pt(1), seg_t(str(sc))]


def sc_lines(sc):
    if not sc:
        return []
    if isinstance(sc[0], list):
        return [sc_line(s) for s in sc]
    return [sc_line(sc)]


def main():
    faces = {}
    for c in CC.CARDS:
        faces[str(c["id"])] = {
            "n": c["name"], "mm": 1 if c["mm"] else 0,
            "loc": c["loc"], "cost": c["cost"], "purse": c["purse"],
            "ab": ab_lines(c["ab"]), "sc": sc_lines(c["sc"]),
        }
    js = "const CC_FACES=" + json.dumps(faces, ensure_ascii=False,
                                        separators=(",", ":")) + ";\n"
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "web", "castlecombo-faces.js")
    with open(path, "w") as f:
        f.write(js)
    print("wrote", path, len(js), "bytes,", len(faces), "cards")


if __name__ == "__main__":
    main()
