# TTS mod 3769058526 — "Fliptoons" (Tabletop Simulator Workshop mod)

Extracted 2026-11-26 for FB-0087 (Annalisa's request) — material to eventually use
on the Fliptoons game in boardgamebot. Extraction/inventory only; no game code
was changed.

## Source

- Workshop item: https://steamcommunity.com/sharedfiles/filedetails/?id=3769058526
- Title: **Fliptoons** — "Includes Season 2 and the two Big Button mini expansions.
  No scripts or anything super fancy."
- Creator SteamID: 76561198025388178 · App: Tabletop Simulator (286160)
- Created 2026-07-21, updated 2026-07-28 22:44 UTC · 682 subscriptions · 646 views
- The Workshop page itself requires a Steam login, but the file is public:
  the mod file was fetched straight from the Steam CDN via the public
  `ISteamRemoteStorage/GetPublishedFileDetails` API (no login, no steamcmd
  needed — steamcmd was downloaded but never required).

## Files in this folder

| File | What it is |
|---|---|
| `mod-original.bin` (224,000 bytes) | The mod file exactly as downloaded from the Steam CDN (`file_url` from the API). NOT plain JSON: TTS saves this mod in a binary format — 4-byte little-endian total-size header, then typed key/value entries (`0x01` float64, `0x02` length-prefixed string, `0x03` object, `0x04` array, `0x08` bool, `0x10` int32, `0x12` int64, `0x00` end-of-object). |
| `mod.json` (365,761 bytes) | The same save decoded to readable JSON. |
| `decode_tts.py` | The decoder used (`python3 decode_tts.py` regenerates `mod.json` from `mod-original.bin`; it validates by consuming exactly 224,000 bytes). |
| `assets/` | All 37 unique images/PDFs referenced by the save, downloaded from `steamusercontent-a.akamaihd.net` (see below). |
| `assets-manifest.json` | Machine-readable list: local file, source URL, size, sha256 prefix, roles, description. |

## What the mod contains (from `mod.json`)

- 57 top-level objects: the Season 1 toon deck (53 cards), 7 starting decks
  (6 cards each), 2 rulebook PDFs, 10 tokens, 4 HandTriggers, bags for
  Season 2 / Big Button / Big Button 2, 2 Infinite_Bags (Season 1 + 2
  starting decks), 3 3DText labels, reference/first-player/critic cards.
- LuaScript is only the default TTS template (`onLoad`/`onUpdate` stubs) —
  no custom scripts, as the description says. XmlUI is only the default comment.
- Deck numbers are per-object in TTS: the same number can be a different
  sheet in different bags (e.g. deck 18 is the Axolotl in the Big Button bag,
  the green price-3 card in the Season 2 bag, and the Season 2 starter sheet
  in the Infinite_Bag). The inventory below is by image, not by number.

## Assets (`assets/`, ~152 MB total)

Card sheets (print-quality PNGs):

| File | Size | Contents |
|---|---|---|
| `deck4-face.png` | 3750×5250, 44 MB | Season 1 toon deck, 5×5, ranks 1–25 in reading order: Ostrich, Eagle, Donkey, Butterfly, Dog, Goat, Sheep, Camel, Rabbit, Horse, Snake, Elephant, Rooster, Cat, Alligator, Lion, Monkey, Pig, Peacock, Turkey, Bull, Tiger, Deer, Bear, Cow |
| `deck15-face.png` | 3750×5250, 46 MB | Season 2 toon deck, 5×5, ranks 1–25: Salamander, Groundhog, Rat, Goldfish, Mole, Hen, Starfish, Raccoon, Panther, Opossum, Mongoose, Capybara, Crow, Coyote, Clownfish, Fox, Crab, Swordfish, Gorilla, Vulture, Zebra, Shark, Rhinoceros, Hippopotamus, Sloth |
| `deck13-face.png` | 2250×2100, 8 MB | Season 1 starting deck, 3×2: Bee, Caterpillar, Caterpillar, Skunk, Snail, Dragonfly |
| `deck18-face-15579305.png` | 2250×2100, 8 MB | Season 2 starting deck, 3×2: Spider, Grasshopper, Ladybug, Firefly, Mosquito, Mosquito |
| `deck13-back.png` | 750×1050, 1 MB | Shared card back (megaphone). Also the back of both toon decks, both starter decks, Axolotl, Platypus — and the face of all 10 table tokens |

Single cards (750×1050 each, face/back files where they differ):

- **Prices, Season 1** (orange, face = back): `deck5-back` 3, `deck6-back` 4,
  `deck7-back` 7, `deck8-back` 10, `deck9-back` 15.
- **Prices, Season 2** (green, face = back): `deck18-face-17637095` /
  `deck18-back` 3, `deck19-face` / `deck19-back-14582576` 15;
  `deck10-back` price table ranks 1–20, `deck11-back` ranks 21–40.
- **Reference**: `deck12-face` HOW TO PLAY, `deck12-back` ICONS.
- **Table cards**: `deck16-face` / `deck16-back` Critic's Choice +3 (frog),
  `deck17-face` / `deck17-back` First Player clapperboard.
- **Big Button mini-expansion**: `deck18-face` Axolotl rank 26 (2 copies,
  back = shared card back), `deck19-face-11640540` / `deck19-back` RESET
  button card (6 copies), `deck20-face` / `deck20-back` title + rules card.
- **Big Button 2 mini-expansion**: `deck21-face` Platypus rank 26 (2 copies,
  back = shared card back), `deck22-face` / `deck22-back` title + rules card,
  `deck24-face` / `deck24-back` GRID RESET + rules, `deck25-face` /
  `deck25-back` MARKET RESET + rules, plus 4 more RESET cards
  (`deck19-face-11640540`).

Rulebooks (PDF, text layer intact):

| File | Contents |
|---|---|
| `rulebook-1.pdf` (2.7 MB, 16 pp.) | Fliptoons Season 1 rulebook, v.2 (Sep 2025) |
| `rulebook-2.pdf` (4.0 MB, 20 pp.) | Fliptoons Season 2 rulebook (Dec 2025) |

Also: `preview.png` (832×600) — the Workshop thumbnail.

## Notes for later use on the Fliptoons game

- The Season 1 sheet (`deck4-face.png`) matches the card table already in
  `fliptoons-notes.md` / `fliptoons.py` (ranks 1–25, same names/fame) — the
  repo's existing `assets/fliptoons/images/fliptoons/fl-toon-cards.webp` was already derived from
  this sheet; this folder now preserves the full-resolution original.
- New material vs. what the repo already has: the Season 2 toon sheet
  (25 new toons + Season 2 starters Spider/Grasshopper/Ladybug/Firefly/
  Mosquito), the Season 2 price cards + price tables (ranks 1–40), both
  rulebook PDFs, the Big Button / Big Button 2 cards (Axolotl, Platypus,
  RESET, GRID/MARKET RESET), and the HOW TO PLAY / ICONS reference cards.
- Season 2 starter fame (from the sheet): Spider 1, Grasshopper 1, Ladybug 1,
  Firefly 1, Mosquito 0.
- All Steam CDN URLs are in `assets-manifest.json` if any asset needs
  re-fetching; the CDN links are the mod's own hosted files, not re-hosts.
