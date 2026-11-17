# TODO

## Castle Combo — Mini App score sheet (game end)
When the game ends, render the score sheet like BGA does instead of the plain
results list:

- Background image: `end-score.jpg`
  (https://x.boardgamearena.net/data/themereleases/current/games/castlecombo/260709-1118/img/end-score.jpg —
  a copy exists at /tmp/cc/end-score.jpg). Serve it from the bot web server and
  put the `.castle-combo-score-sheet-background` styling behind a table
  (563x750 on BGA; scale to fit mobile).
- Table structure (BGA `#result #score-sheet`):
  - header row: corner cell + one `<th class="bga-score-sheet_player-name">`
    per player (colour-tinted).
  - entries 1..9: one row per round; each cell = the score of the card placed
    that round. **Engine work needed:** compute a per-card score breakdown
    (round-by-round, keys entry, total) — currently only the final total
    exists (`preview_score` / `_score`). BGA evaluates each placed card's
    scoring in the final tableau; add a `score_breakdown(g)` that returns
    9 card entries + `keys` (1 pt per leftover key) + `total` per player,
    and expose it in `castlecombo_board_json` (e.g. `results` gains
    `entries`), then render the table in `ccRender()`'s `game_end` branch.
  - `keys` row, then `total` row with the `.total` highlight; winner styling.
- Keep the tiebreak (leftover gold) note below the sheet.
