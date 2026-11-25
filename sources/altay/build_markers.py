"""Rebuild web/altay-markers.webp as 3 clean cells (values 1/2/3).

Run from the repo root: python3 sources/altay/build_markers.py

The old sheet was a strip of assorted BGA tokens; the Mini App sliced it
as 6 equal columns, so every chip showed two half-tokens mashed together.
The new sheet has one red shield per value (the number printed on it),
each centred in a 120x80 cell, so background-size 300% shows exactly one.
The value-3 shield on BGA is white-on-parchment, which cannot be keyed
out, so the 3 is taken from that shield and put on a red shield like 1/2.
"""
from PIL import Image
from collections import Counter, deque
import math

import os
# original BGA token strip (assorted tokens); this script rebuilds
# web/altay-markers.webp from it. Run from the repo root.
SRC = os.path.join('sources', 'altay', 'markers-strip.webp')
src = Image.open(SRC).convert('RGBA')
spx = src.load()

PARCH = (230, 222, 202)
def dist(c1, c2):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))
def is_red(r, g, b):
    return r > 60 and r - g > 40 and r - b > 40
def is_pale(r, g, b):
    return dist((r, g, b), PARCH) < 45

def shield_alpha(crop):
    """Keep the shield + its numeral; drop everything reachable from the
    border without crossing dark red (parchment and the token shape behind
    the shield are both reachable, the cream numeral inside is not)."""
    w, h = crop.size
    px = crop.load()
    keep = [[False] * w for _ in range(h)]
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not is_red(*px[x, y][:3]):
                q.append((x, y)); keep[y][x] = True
    for y in range(h):
        for x in (0, w - 1):
            if not is_red(*px[x, y][:3]) and not keep[y][x]:
                q.append((x, y)); keep[y][x] = True
    while q:
        x, y = q.popleft()
        for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
            if 0 <= nx < w and 0 <= ny < h and not keep[ny][nx] and not is_red(*px[nx, ny][:3]):
                keep[ny][nx] = True
                q.append((nx, ny))
    out = crop.copy()
    opx = out.load()
    for y in range(h):
        for x in range(w):
            if keep[y][x]:
                opx[x, y] = (0, 0, 0, 0)
    return out

def shield_crop(x0, y0, x1, y1):
    return shield_alpha(src.crop((x0, y0, x1, y1)))

# red shields, measured off the sheet (tight bbox + small margin)
s1 = shield_crop(31, 19, 80, 69)     # red '1'
s2 = shield_crop(141, 10, 189, 59)   # red '2'

# shield red: most common dark-red in s2
reds = Counter()
px2 = s2.load()
for y in range(s2.height):
    for x in range(s2.width):
        r, g, b, a = px2[x, y]
        if a and is_red(r, g, b):
            reds[(r, g, b)] += 1
shield_red = reds.most_common(1)[0][0]
print('shield red:', shield_red)

# --- build the red '3': flat shield-red silhouette of the red '2'
# (painting the cream '2' away leaves a pink halo from its anti-aliased
# edges), then the white '3' on top.
s3 = Image.new('RGBA', s2.size, (0, 0, 0, 0))
px3 = s3.load()
for y in range(s2.height):
    for x in range(s2.width):
        if px2[x, y][3]:
            px3[x, y] = shield_red + (255,)

# extract the '3' numeral: dark connected component inside the white shield
bx0, by0, bx1, by1 = 542, 10, 591, 61
dark = set()
for x in range(bx0, bx1):
    for y in range(by0, by1):
        r, g, b, a = spx[x, y]
        if a and r < 150 and g < 130 and b < 120:
            dark.add((x, y))
seen, comps = set(), []
for p in dark:
    if p in seen:
        continue
    stack, comp = [p], []
    seen.add(p)
    while stack:
        q = stack.pop()
        comp.append(q)
        for nb in ((q[0]+1, q[1]), (q[0]-1, q[1]), (q[0], q[1]+1), (q[0], q[1]-1)):
            if nb in dark and nb not in seen:
                seen.add(nb); stack.append(nb)
    comps.append(comp)
three = [c for c in comps
         if all(bx0 < x < bx1 - 1 and by0 < y < by1 - 1 for x, y in c)]
assert len(three) == 1, f'expected 1 central component, got {len(three)}'
three = three[0]
tx0, tx1 = min(x for x, y in three), max(x for x, y in three)
ty0, ty1 = min(y for x, y in three), max(y for x, y in three)
print('three bbox:', tx0, tx1, ty0, ty1)
tcx, tcy = (tx0 + tx1) // 2, (ty0 + ty1) // 2
ccx, ccy = s3.width // 2, s3.height // 2
for (x, y) in three:
    nx, ny = x - tcx + ccx, y - tcy + ccy
    if 0 <= nx < s3.width and 0 <= ny < s3.height:
        px3[nx, ny] = (255, 255, 255, 255)

# --- assemble: 3 cells of 120x80, shield fitted to height 80
CELL_W, CELL_H = 120, 80
sheet = Image.new('RGBA', (CELL_W * 3, CELL_H), (0, 0, 0, 0))
for i, sh in enumerate([s1, s2, s3]):
    scale = CELL_H / sh.height
    w = max(1, int(sh.width * scale))
    sh2 = sh.resize((w, CELL_H), Image.LANCZOS)
    sheet.paste(sh2, (i * CELL_W + (CELL_W - w) // 2, 0), sh2)
sheet.save('web/altay-markers.webp')
print('saved web/altay-markers.webp', sheet.size)
bg = Image.new('RGBA', sheet.size, (15, 23, 42, 255))
bg.paste(sheet, (0, 0), sheet)
bg.resize((720, 160), Image.NEAREST).convert('RGB').save('/tmp/markers_sheet_big.png')
prev = Image.new('RGBA', (42 * 3 + 8, 28), (15, 23, 42, 255))
for i in range(3):
    cell = sheet.crop((i * CELL_W, 0, (i + 1) * CELL_W, CELL_H)).resize((42, 28), Image.LANCZOS)
    prev.paste(cell, (i * 46, 0), cell)
prev.convert('RGB').save('/tmp/markers_preview.png')
print('previews saved')
