# Fliptoons (Season 1) — resolved rules data

All data verified against: the official Season 1 rulebook PDF (text layer, from the TTS mod),
BGA gamepanel FAQ (Spanish), kuribodo (BGA player's Japanese card table), GeekDad 53-fame
worked example, and the print-quality TTS deck sheet (`c00..c24.png` cells = ranks 1..25 in order).

## Deck composition (53 cards)

Starters — every player starts with the same 5 starting cards + 1 duplicate caterpillar
(6 cards total: 2x caterpillar, 1 each skunk/dragonfly/bee/snail). All rank 0, gray cards.
Toon deck (ranks 1-25, 47 cards total): see counts below. Counts sum to 47: 3+2+2+3+4+2+2+5+4+2+2+2+2+2+2+2+2+1+2+2+1+1+1+1+1 = 47.

## Card table

| Rank | Name        | Count | Fame | Ability |
|------|-------------|-------|------|---------|
| 0    | Caterpillar | 2     | 0    | Dismiss cost 3 (paid action) |
| 0    | Skunk       | 1     | 0    | At start of this player's Market phase, if the skunk is face-up in their grid and no other player (incl. own grid/market) has equal-or-fewer fame, that player MUST free-dismiss one face-up grid card (may dismiss the skunk itself); tie in least fame = nobody |
| 0    | Dragonfly   | 1     | 0    | +1 per adjacent card (every card in adjacent stacks counts individually, incl. face-down cards) |
| 0    | Bee         | 1     | 1    | - |
| 0    | Snail       | 1     | 2    | - |
| 1    | Ostrich     | 3     | 1    | The next revealed card stacks on it; if the ostrich fills the last empty slot, stop revealing market refill cards |
| 2    | Eagle       | 2     | 4    | CANNOT BE FLIPPED; flips the NEXT placed card face-down unless that card cannot be flipped (its ability does not activate) |
| 3    | Donkey      | 2     | 1    | Lower row: +5 AND dismissed after the Market phase; upper row: neither |
| 4    | Butterfly   | 3     | 2    | When hired, may dismiss a face-up caterpillar (any caterpillar, incl. stacked) |
| 5    | Dog         | 4     | 0    | +5 if at least one DOG is in the market or any other player's grid (evaluated at Check Fame) |
| 6    | Goat         | 2     | 1    | Upper row: +3 (still counts if monkey row above) |
| 7    | Sheep       | 2     | 1    | Middle column: +4 |
| 8    | Camel       | 5     | 2    | +2 if no other player or the market has more CAMELS than you (strictly more; ties keep the bonus -> 4) |
| 9    | Rabbit      | 4     | 3    | CANNOT BE FLIPPED; stacks on the first RABBIT or face-down card in the grid if possible |
| 10   | Horse       | 2     | 4    | When hired: discard any number of market cards, reveal equal number from toon deck, re-sort market |
| 11   | Snake       | 2     | 1    | Dismiss the top card of your own deck AND stack the top card of the toon deck on this card (independent effects) |
| 12   | Elephant    | 2     | 7    | CANNOT BE FLIPPED; flips the previously placed card face-down unless it cannot be flipped; ignored if first placed card; works even if the target has moved (incl. from monkey row) |
| 13   | Rooster     | 2     | 0    | +1 per card rank 13 or lower in your grid (including this card; starters rank 0 count) |
| 14   | Cat         | 2     | 1    | CANNOT BE DISMISSED; +1 per starting card in your dismissed cards |
| 15   | Alligator   | 2     | 6    | After the Market phase, dismiss one card adjacent to the right of this card (stack -> any one card in it; cancelled if the alligator itself gets dismissed; the dismissed card still generated fame this round) |
| 16   | Lion        | 2     | 3    | +4 if all adjacent cards are rank 16 or lower (vacuously true if none adjacent) |
| 17   | Monkey      | 2     | 3    | Placed in the upper row: moves above the grid creating an extra row; the next revealed card goes into the monkey's old slot; the extra row is part of the grid (adjacent to top row) but not one of the 6 slots and not "the upper row" |
| 18   | Pig         | 1     | -1   | When hired or dismissed: place it in any deck (your own, any other player's, or the toon deck -> shuffle) |
| 19   | Peacock     | 2     | 5    | When hired: +2 fame immediately AND take a bonus Market action |
| 20   | Turkey      | 2     | 5    | Stacks on the previously placed card (even if it moved); ignored if first placed card |
| 21   | Bull        | 1     | 3    | CANNOT BE FLIPPED; +7 if one or more cards in your grid are face down |
| 22   | Tiger       | 1     | 3    | CANNOT BE DISMISSED; +1 per card in your dismissed cards |
| 23   | Deer        | 1     | 3    | +5 if each face-up card in your grid is unique (by name) |
| 24   | Bear        | 1     | 1    | +1 per face-up card in your grid (including itself; stacked face-up cards each count) |
| 25   | Cow         | 1     | 0    | NO printed fame: card shows "=" and "Copy the fame of one adjacent card" (up/down/left/right arrows -> orthogonal adjacency); adjacent stack -> copy any one card in it |

## Verified rulings / edge cases

- Flipping: when placed face-down, card is flipped and CANNOT-BE-FLIPPED cards stay face-up.
- Stacking: a stack shows only the top card face-up; cards below are face-down but still cards
  (no name/ability while face-down; a face-down card still counts as a card for dragonfly adjacency,
  bear face-up counting excludes them, bull sees them, rabbit stacks on them).
- Rabbit placement priority: own rabbit stack / face-down card first, else normal slot.
- Turkey stacks on the last placed card wherever it ended up (incl. monkey row); if that cell is
  occupied by a stack, turkey goes on top.
- Ostrich: next revealed card (market refill) goes onto the ostrich; if the ostrich was in the last
  empty slot, stop revealing refill cards.
- Snake: dismiss own deck top is optional?? — NO: both effects happen (dismiss own top + stack toon
  deck top on snake). If own deck is empty, only the stacking happens. If the toon deck top cannot
  be dismissed-placed (cat/tiger), place it to the right of the snake or return it to the deck.
  When-hired of the stacked card resolves AFTER the Flip phase; peacock grants +2 fame + bonus
  action; rabbit/turkey just sit stacked.
- Monkey: creates a row above the grid (cell 6), adjacent to cells 0,1,2.
- Elephant: flips the previously placed card (the card placed just before the elephant), wherever
  it is now, face-down (unless it cannot be flipped: eagle/rabbit/elephant/bull — then nothing).
- Eagle: flips the next placed card face-down (unless it cannot be flipped — then the eagle's
  effect does nothing more).
- Pig: when hired OR dismissed, its owner places it (face-up) in any deck: own deck top/bottom
  (choice), any other player's deck, or the toon deck (then shuffle). A pig in a deck is drawn
  and hired like any card; its when-hired may fire again.
- Alligator: after the Market phase (in cell order), dismisses one card adjacent to its right;
  if that cell holds a stack, dismiss any one card from the stack; if the alligator was dismissed
  during cleanup/ordering, nothing; a dismissed caterpillar does NOT count as "starting card
  dismissed" for the cat until it's actually in the dismissed pile (it is).
- Skunk: checked at the START of the skunk owner's Market phase (their turn): if skunk face-up
  and owner is the UNIQUE least-fame player (strictly less than everyone else incl. market fame),
  owner MUST free-dismiss one face-up card from their grid (may be the skunk). Equal least -> no one.
- Cat: +1 per starting card (caterpillar/skunk/dragonfly/bee/snail) in the dismissed pile.
  Caterpillars dismissed by butterfly/alligator/etc. count.
- Rooster: rank <= 13 cards in grid incl. itself; starters (rank 0) count.
- Camel: +2 if no other player's grid AND the market contain strictly more camels than this
  player's grid+market camels? — rulebook: "if no other player or the market has more camels than you".
  Compare per-location: your camels vs each other player's grid camels and vs market camels;
  bonus if nobody strictly exceeds you. Ties keep the bonus. Stacked camels all count.
- Dog: +5 if >= 1 dog in the market or any OTHER player's grid (not your own). Stacked dogs in
  other grids/market count. Evaluated at Check Fame (end of round).
- Deer: all face-up cards in grid unique by name (duplicates allowed if one of them is face-down).
- Bear: +1 per face-up card in your grid including itself (stacked face-up cards each count).
- Cow: copies the fame of one adjacent card (orthogonal up/down/left/right; adjacent stack ->
  any one card in that stack). Copies the card's TOTAL computed fame. No printed fame of its own.
- Dismiss (paid action): cost 3 fame? — no: paid dismissal costs fame equal to... the
  caterpillar's "dismiss cost 3" is the caterpillar-specific printed cost. General paid dismiss:
  dismiss any face-up card from your grid for the printed dismiss cost (only caterpillar has one,
  cost 3). Cannot dismiss if you have fewer than 4 total cards (deck+grid).
- Cleanup: grid cards go back on TOP of your deck (face-up, original order: leftmost first? -> top).
  Then market refills. With 2 players: after the last player's refill, discard the leftmost and
  rightmost market cards, then refill, then re-sort by price.
- End: any player reaches >= 30 fame at Check Fame -> critic's choice: +3 fame to the single player
  with the most fame (nobody if tied); finish the current round so everyone played equally, then
  the Final Flip. Also ends when the toon deck AND market are both empty after a round -> Final Flip.
- Final Flip: each player's total fame = grid fame at that moment; ties -> players re-flip
  (reveal top of deck? no: flip their top grid... — per rulebook: tied players flip one more card
  into their grid? implement as: highest total fame wins; on tie, tied players flip their top deck
  card face-up adding it to grid and recompute; cap at ~10 iterations, then draw).

## Implementation decisions (documented approximations)

- Cards are instances: {"id": n, "r": rank, "s": starter index 0-4 or None, "fd": face_down}.
  Starters are rank 0 (caterpillar=0/skunk=1/dragonfly=2/bee=3/snail=4); toons 1..25 = rank.
  Starting deck per player: caterpillar x2, skunk, dragonfly, bee, snail (no pig).
- deck = list, deck[-1] = top. Grid = 6 slots (0-2 top row, 3-5 bottom) + cell 6 = monkey row
  (adjacent to 0,1,2). Adjacency orthogonal.
- Market prices [3,4,7,10,15] by sorted position; < 5 cards -> right-aligned (use last n prices).
- Dismiss restriction: total cards (deck + grid) < 4 -> cannot dismiss (paid action only).
- Cow: auto-copy the max computed fame among orthogonal adjacent cards (NPC + default;
  documented approximation vs free choice).
- Snake-stacked card's when-hired: only peacock (grants +2 fame + bonus action), rabbit/turkey
  sit stacked; horse/butterfly/pig when-hired skipped (approximation).
- Alligator stack target: dismiss the TOP card of the stack (approximation).
- Pig dismissed by card abilities (alligator/donkey/snake): returns to its owner's deck top.
- Butterfly (NPC): auto-dismiss a face-up caterpillar if present.
- Fame computation order: all non-cow cards first, then cow (only 1 cow in deck, no recursion).
- NPC auto-play: greedy — hire the most expensive affordable non-pig card; resolve pendings inline.

## Engine API (implemented in fliptoons.py)

- new_game(chat_id, creator_id, creator_name) / start_game(g, events) (2-4 players) /
  advance(g, events) / apply_choice(g, idx, choice, events) / do_market(g, idx, act, arg, events).
- Pendings: dict {"kind", "player", "options": [{"v","label"}], "prompt"} in g["pending"];
  overflow via g["pending_q"] (apply_choice promotes the queue head and returns without
  advancing). Kinds: skunk (mandatory dismissal), butterfly (dismiss caterpillar/skip),
  pig (own/toon/p<i> deck placement), horse (incremental market discard, "done").
- Instances {"id","r","s","fd"}; grid_fame(g, p), card_name(inst), _label(inst) helpers.
- Fame target 30; prices [3,4,7,10,15]; dismiss cost 5 (starters 3); tie cap 10 -> draw.
- 2-player cleanup: after the last player's market phase, discard the leftmost+rightmost market
  cards (1 remaining card counts as both -> discard it), refill, re-sort. 3+ players: no discard.
- End triggers: fame >= 30 at Check Fame; toon deck AND market both empty; degenerate-state
  stall breaker (engine house rule): toon deck empty and no market hire for 8 consecutive
  rounds -> Final Flip (prevents rules-legal deadlocks like empty decks + unaffordable market).
- Skunk check: owner's fame strictly the least among all players (tie -> nobody), mandatory
  free dismissal at the start of the owner's Market phase, no action cost.
- End triggers as above; critic's choice +3 to unique most-fame player at first 30+ check.

## Assets

- BGA sprite: rank N -> row (N-1)//6, col (N-1)%6 of fl-toon-cards.jpg (6x5 grid; cells 25-29 of
  the sheet = the 5 starter card arts, order unverified). Card ratio 148x206.6.
- TTS print sheet: 5x5 grid of 750x1050 cells, ranks 1-25 in row-major order (verified by OCR).
