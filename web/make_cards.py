#!/usr/bin/env python3
"""Generate our own Flip 7-style card images as SVG (no official art copied).
Run: python3 web/make_cards.py  ->  web/cards/*.svg
Colors are distinct per number so piles are readable at a glance."""
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards")
COLORS = {0: "#64748b", 1: "#ef4444", 2: "#f97316", 3: "#eab308", 4: "#84cc16",
          5: "#22c55e", 6: "#14b8a6", 7: "#06b6d4", 8: "#3b82f6", 9: "#6366f1",
          10: "#8b5cf6", 11: "#d946ef", 12: "#ec4899"}


def svg(body, w=64, h=88):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}">{body}</svg>\n')


def number_card(n):
    c = COLORS[n]
    return svg(f'<rect x="2" y="2" width="60" height="84" rx="8" fill="#f8fafc" stroke="{c}" stroke-width="4"/>'
               f'<rect x="2" y="2" width="60" height="22" rx="8" fill="{c}"/>'
               f'<text x="32" y="17" text-anchor="middle" font-family="Arial,sans-serif" font-size="11" font-weight="bold" fill="#fff">FLIP 7</text>'
               f'<text x="32" y="62" text-anchor="middle" font-family="Arial,sans-serif" font-size="38" font-weight="bold" fill="{c}">{n}</text>')


def mod_card(m):
    return svg(f'<rect x="2" y="2" width="60" height="84" rx="8" fill="#ecfdf5" stroke="#059669" stroke-width="4"/>'
               f'<text x="32" y="52" text-anchor="middle" font-family="Arial,sans-serif" font-size="24" font-weight="bold" fill="#065f46">{m}</text>'
               f'<text x="32" y="72" text-anchor="middle" font-family="Arial,sans-serif" font-size="9" fill="#065f46">MODIFIER</text>')


def action_card(name, label):
    return svg(f'<rect x="2" y="2" width="60" height="84" rx="8" fill="#f5f3ff" stroke="#7c3aed" stroke-width="4"/>'
               f'<text x="32" y="40" text-anchor="middle" font-family="Arial,sans-serif" font-size="15" font-weight="bold" fill="#5b21b6">{label}</text>'
               f'<text x="32" y="66" text-anchor="middle" font-family="Arial,sans-serif" font-size="9" fill="#5b21b6">ACTION</text>')


BACK = svg('<defs><pattern id="p" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#5b21b6"/><path d="M0 8L8 0" stroke="#7c3aed" stroke-width="2"/></pattern></defs>'
           '<rect x="2" y="2" width="60" height="84" rx="8" fill="url(#p)" stroke="#f8fafc" stroke-width="3"/>'
           '<text x="32" y="48" text-anchor="middle" font-family="Arial,sans-serif" font-size="13" font-weight="bold" fill="#fff">FLIP 7</text>')


def main():
    os.makedirs(OUT, exist_ok=True)
    for n in range(13):
        open(os.path.join(OUT, f"{n}.svg"), "w").write(number_card(n))
    for m in ["+2", "+4", "+6", "+8", "+10", "x2"]:
        open(os.path.join(OUT, f"mod_{m.replace('+', 'plus')}.svg"), "w").write(mod_card(m))
    open(os.path.join(OUT, "Freeze.svg"), "w").write(action_card("Freeze", "❄ Freeze"))
    open(os.path.join(OUT, "FlipThree.svg"), "w").write(action_card("Flip Three", "🎲 Flip 3"))
    open(os.path.join(OUT, "SecondChance.svg"), "w").write(action_card("Second Chance", "💛 2nd"))
    open(os.path.join(OUT, "back.svg"), "w").write(BACK)
    print(f"wrote {len(os.listdir(OUT))} card images to {OUT}")


if __name__ == "__main__":
    main()
