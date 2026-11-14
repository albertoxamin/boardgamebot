# Tornado Splash card art (extracted from the TTS workshop save)

Source: <https://cdn.steamusercontent.com/ugc/63712806320358425/D3208D2E495325AC2B30DB1DCF9B97FB0442FBEB/>

That link is **not** an image — it is a Tabletop Simulator save file (118,860 bytes,
version `v13.3`) for the Steam Workshop mod
[**Tornado Splash 2 / トーネードスプラッシュ2**](https://steamcommunity.com/sharedfiles/filedetails/?id=3229903430)
(workshop item now hidden/removed by Steam). The card pictures are referenced inside
the save as three `CustomDeck` image atlases hosted on Steam's CDN:

| deck | atlas | grid | what it is |
|---|---|---|---|
| 15 | `ugc/2523780000427749871/3428826011818BA9D254BD42DAACBB1F081AF967/` | 3×2, 712×1422 | 5 running cards + shared back (100×35 mm cards) |
| 16 | `ugc/2523780000427753203/3CD91C0E430B18E4595D1B1D4A1D314EBFBD20B7/` | 4×2, 1992×594 | 6 numbered cards + blank cell + shared back (88×63 mm cards) |
| 17 | `ugc/2523780000427758558/E2671A13CD1ECA6314DB91153EA8C59FB66F9E14/` | 1×1, 498×297 | summary/player-aid card |

Each atlas is a grid of faces. `DeckIDs` in the save give the card counts:
running deck = 15 + 15 + 15 + 10 + 5 = 60 cards (faces 1–5), and the second deck
is 6 numbered cards (faces 1–6) in six colours — the six boat/player cards. The
save has no text labels for the card values, so which running face is a
1/2/3-space straight or a curve still has to be identified visually. Likewise the
numbered cards carry a large stylised digit (1–6) but no boat name or stats.

## Files

* `running_1..5.png` – the five running-card faces, exactly as stored in the atlas
  (portrait, 3:1).
* `running_1..5_wide.png` – same art rotated 90° for the physical 100×35 mm
  landscape card shape.
* `running_back.png`, `number_back.png` – the two shared card backs.
* `number_1..6.png` – the six numbered (boat/player) cards, 88×63 mm landscape.
* `summary.png` – the player-aid card ("after moving the boat, refill 1–3 cards
  from your deck up to a 6-card hand").
* `contact_sheet.png` – all of the above in one labelled image.
* `banner_logo.jpg`, `banner_strip.jpg` – the two 549×55 workshop decals.
* `rules.pdf` – the 4-page scanned rules included with the mod.

Regenerated from the save; no colour/detail was altered, only the atlas grid was
cut apart.

## Use in the Mini App

`web/tornado.js` uses these files:

* hand tiles use `running_1..4_wide.png` (the fifth face is the fallback) plus a
  small badge with the engine's card value — the scanned faces carry no printed
  values, so the mapping of `s1/s2/c1/c2` onto four of the five faces is
  arbitrary;
* the boat picker uses `number_1..6.png` as the six boat portraits, matching
  `TS.BOATS` index 0–5.

## Rights

Artwork © Adisawa Games / Arclight Games (illustration: yamamori). These files are
the scans shipped inside the Tabletop Simulator mod. They are included here at the
repository owner's request for personal/reference use with this bot. Do not
redistribute them separately.
