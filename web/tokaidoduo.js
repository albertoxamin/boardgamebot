const TDG = {user_id: 0, chat_id: null, board: null, timer: null, init: '', webVer: null, newVer: false, verAt: 0};

async function tdCheckVer() {
  // FB-0026 (Altay, same cause): the Mini App never reloads its own JS
  // while open, and the ?v= cache-buster on tokaidoduo.js had not been
  // bumped — so a fix could be live on the server while the player
  // still saw the old code with no hint why. Compare the page's ?v=
  // with the server's version (from /healthz) and say so.
  if (!TDG.webVer || TDG.newVer) return;
  if (Date.now() - TDG.verAt < 60000) return;
  TDG.verAt = Date.now();
  try {
    const r = await fetch('/healthz').then(r => r.json());
    if (r.version && r.version !== TDG.webVer) {
      TDG.newVer = true;
      tdLog('🔄 New version available — close and reopen the Mini App to see the latest fixes.');
    }
  } catch (e) {}
}

function tdLog(s) {
  const e = document.getElementById('tdLog');
  if (e) e.textContent += s + '\n';
}
function tdApi(path, opts) { return fetch(path, opts).then(r => r.json()); }
function tdChatId(raw) {
  let s = String(raw || '');
  if (s.startsWith('tokaidoduo')) s = s.slice(10);
  const n = parseInt(s, 10);
  return isNaN(n) ? 0 : n;
}
async function tdLoad() {
  const tg = tgInit();
  if (!tg.id) {
    document.getElementById('tdTurn').textContent = 'Open as Telegram Mini App via the bot link.';
    return;
  }
  TDG.user_id = tg.id;
  TDG.init = tg.init;
  const qp = new URLSearchParams(location.search);
  TDG.webVer = parseInt(qp.get('v'), 10) || null;
  const pref = tdChatId(tg.start) || tdChatId(qp.get('app')) ||
               parseInt(qp.get('chat_id'), 10) || tdChatId(tg.chat_instance);
  const r = await tdApi('/api/tokaidoduo/mygames?init_data=' + encodeURIComponent(tg.init));
  const mine = r.games || [];
  const pick = mine.find(g => g.chat_id === pref) || mine.find(g => g.phase !== 'game_end') || mine[0];
  if (pick) tdSelect(pick.chat_id);
  else if (pref) {
    const cr = await tdApi('/api/tokaidoduo/create', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({init_data: tg.init, chat_id: pref})
    });
    if (cr.game) tdSelect(cr.game.chat_id);
    else tdLog('⛔ ' + (cr.error || 'create failed'));
  } else {
    document.getElementById('tdTurn').textContent = 'No Tokaido Duo game yet — send /tokaidoduo in a chat.';
  }
}
async function tdSelect(chat_id) {
  TDG.chat_id = chat_id;
  await tdRefresh();
  if (TDG.timer) clearInterval(TDG.timer);
  TDG.timer = setInterval(tdRefresh, 3000);
}
async function tdRefresh() {
  if (!TDG.chat_id) return;
  tdCheckVer();
  const q = '?chat_id=' + encodeURIComponent(TDG.chat_id) + '&init_data=' + encodeURIComponent(TDG.init);
  const r = await tdApi('/api/tokaidoduo/game' + q);
  if (r.game) { TDG.board = r.game; tdRender(); }
}
async function tdMove(action, extra) {
  const body = Object.assign({chat_id: TDG.chat_id, action: action, init_data: TDG.init}, extra || {});
  const r = await tdApi('/api/tokaidoduo/move', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  if (r.events) r.events.forEach(e => tdLog(e));
  if (r.error) tdLog('⛔ ' + r.error);
  if (r.game) { TDG.board = r.game; tdRender(); }
}
function tdStationPos(g, i) {
  // FB-0042: the Pilgrim meeple must sit exactly on the drawn station
  // it stands on. The ellipse below was a guess and missed the drawn
  // medallions by up to ~15% of the board — the ring is not an ellipse,
  // it bulges around the four villages and dips to the big Hot Spring
  // circle — so the pawn floated off the stations. Positions are now
  // measured off tokaidoduo-board.webp and served as station_pos (see
  // STATION_POS in tokaidoduo.py); the ellipse stays only as a fallback
  // for a board JSON that predates it.
  const sp = (g && g.station_pos) || null;
  if (sp && sp[i]) return sp[i];
  const a = (45 + i * (360 / 37)) * Math.PI / 180;
  return [52 + 40 * Math.sin(a), 50 - 36 * Math.cos(a)];
}
function tdMeeple(x, y, color, char, title) {
  // FB-0031: the marker is the BGA character meeple from
  // tokaidoduo-meeples.webp (spriteMeeples.png: pilgrim / merchant /
  // artist down the columns, purple row on top, green row below), so
  // the marker already is the player's colour (FB-0027) — the ring
  // and halo just make it unmissable (see .tdmeeple in flip7.html).
  return '<span class="tdmeeple td' + color + ' td' + char + '" style="top:' + y.toFixed(1) +
         '%;left:' + x.toFixed(1) + '%;" title="' + escapeHtml(title) + '"></span>';
}
// FB-0033: spriteDes.jpg is 6 die faces x 3 dice (40px each): the
// Merchant die (1/2/3/1/2/3) on the orange row, the Artist die
// (1/2/3/1/1/2) on the gold row, the Pilgrim die (1/2/3/4/2/3) on the
// pink row. Show the rolled face on the pick-die button, next to
// e.g. "merchant (2)".
const TD_DIE_ROW = {merchant: 0, artist: 1, pilgrim: 2};
const TD_DIE_COL = {1: 0, 2: 1, 3: 2, 4: 3};
function tdDieFace(ch, value) {
  const col = TD_DIE_COL[value] || 0;
  const row = TD_DIE_ROW[ch] || 0;
  return '<span class="tddie" style="background-position:' + (col * 20) + '% ' + (row * 50) +
    '%;" title="' + escapeHtml(ch + ' ' + value) + '"></span>';
}
// FB-0034: the player boards (spritePlateauxJoueurs.png, 862x213 each:
// top half = first seat, bottom half = second). Marker positions are
// image pixels on the half-board, measured off the BGA art:
// culture dots on the Artist track, commerce on the gold row, temple
// lanterns (3x3), garden circles (x1-x6), painting slots (5x2).
const TD_CULTURE_POS = {0: [35, 58], 2: [62, 58], 4: [112, 58], 7: [165, 58],
  10: [30, 118], 14: [80, 118], 18: [135, 118], 23: [185, 118],
  28: [55, 180], 34: [110, 180], 40: [160, 180]};
const TD_GOLD_POS = {0: [223, 168], 5: [278, 168], 11: [333, 168], 18: [388, 168],
  26: [443, 168], 35: [498, 168], 45: [553, 168]};
const TD_LANTERN_X = [602, 645, 687], TD_LANTERN_Y = [58, 118, 178];
const TD_GARDEN_X = 735, TD_GARDEN_Y = [28, 60, 92, 123, 155, 185];
const TD_PAINT_X = [278, 333, 388, 443, 498], TD_PAINT_Y = [32, 88];
function tdMark(x, y, col, title) {
  return '<span class="tdmark td' + col + '" style="left:' + (x / 862 * 100).toFixed(1) +
    '%;top:' + (y / 213 * 100).toFixed(1) + '%;" title="' + escapeHtml(title) + '"></span>';
}
// FB-0048: the coin tokens on the player's own board — the real BGA
// 1-coin and gold-slab art from spritePieces.png (tokaidoduo-pieces.webp,
// panels 1 and 2, as tdCoin()/tdGold() use inline), laid out in the free
// band of the Merchant section, above the printed "10 coin -> gold"
// conversion (painting slots end at y~113, the printed icons start at
// y~148): coins first, then gold slabs, up to 8 per row. The pile starts
// at x=278, not at the band's left edge, so the second row clears the
// Artist's robe (measured off the board art: its right edge reaches
// x~263 at y~140) instead of sitting on the character.
const TD_COIN_X0 = 278, TD_COIN_Y0 = 118, TD_COIN_D = 22, TD_COIN_PER_ROW = 8;
function tdBoardCoin(idx, x, y, title) {
  return '<span class="tdboardcoin" style="left:' + (x / 862 * 100).toFixed(1) +
    '%;top:' + (y / 213 * 100).toFixed(1) +
    '%;background-position-x:' + (idx * 50) +
    '%;" title="' + escapeHtml(title) + '"></span>';
}
function tdSeatBoard(g, p, col) {
  let s = '';
  const cu = TD_CULTURE_POS[p.culture];
  if (cu) s += tdMark(cu[0], cu[1], col, 'Culture ' + p.culture);
  const go = TD_GOLD_POS[p.commerce];
  if (go) s += tdMark(go[0], go[1], col, 'Commerce ' + p.commerce);
  for (let t = 1; t <= Math.min(p.temple, 9); t++) {
    s += tdMark(TD_LANTERN_X[(t - 1) % 3], TD_LANTERN_Y[Math.floor((t - 1) / 3)],
      col, 'Temple ' + t + '/9');
  }
  for (let gd = 1; gd <= Math.min(p.garden, 6); gd++) {
    s += tdMark(TD_GARDEN_X, TD_GARDEN_Y[gd - 1], col, 'Garden x' + gd);
  }
  p.paintings.forEach((t, idx) => {
    if (idx >= 10) return;
    s += tdPaintSlot(col, t, TD_PAINT_X[idx % 5], TD_PAINT_Y[Math.floor(idx / 5)]);
  });
  let ci = 0;
  const coins = Math.max(0, p.coins || 0), slabs = Math.max(0, p.gold || 0);
  for (let k = 0; k < coins; k++, ci++) {
    s += tdBoardCoin(1, TD_COIN_X0 + (ci % TD_COIN_PER_ROW) * TD_COIN_D,
      TD_COIN_Y0 + Math.floor(ci / TD_COIN_PER_ROW) * TD_COIN_D,
      'Coin ' + (k + 1) + ' of ' + coins);
  }
  for (let k = 0; k < slabs; k++, ci++) {
    s += tdBoardCoin(2, TD_COIN_X0 + (ci % TD_COIN_PER_ROW) * TD_COIN_D,
      TD_COIN_Y0 + Math.floor(ci / TD_COIN_PER_ROW) * TD_COIN_D,
      'Gold slab ' + (k + 1) + ' of ' + slabs + ' (10 coins each)');
  }
  return s;
}
// FB-0045: the painting tokens are the real BGA art from
// spriteOeuvres.jpg (tokaidoduo-paintings.webp): 10 panels, one per
// player colour x (brush back + 4 icons), left to right — purple brush,
// bamboo, moon, mountain, waterfall, then the same five in green.
// A revealed tile shows its icon in the player's colour, an unrevealed
// one shows the brush back, a gifted one keeps the art with a ✓ badge.
const TD_PAINT_IDX = {purple: {bamboo: 1, moon: 2, mountain: 3, waterfall: 4},
  green: {bamboo: 6, moon: 7, mountain: 8, waterfall: 9}};
const TD_PAINT_BACK = {purple: 0, green: 5};
function tdPaintSlot(col, t, sx, sy) {
  const idx = (t.revealed || t.gifted) ? (TD_PAINT_IDX[col] || {})[t.icon]
    : TD_PAINT_BACK[col];
  if (idx === undefined) return '';
  const title = t.gifted ? 'gifted ' + (t.icon || '')
    : (t.revealed ? t.icon : 'painting (face down)');
  return '<span class="tdpaintslot' + (t.gifted ? ' gifted' : '') +
    '" style="left:' + (sx / 862 * 100).toFixed(1) + '%;top:' + (sy / 213 * 100).toFixed(1) +
    '%;background-position-x:' + (idx * 100 / 9).toFixed(2) +
    '%;" title="' + escapeHtml(title) + '">' + (t.gifted ? '<b class="tdgift">✓</b>' : '') + '</span>';
}
// Index of each Wave side in the tokaidoduo-waves.webp sprite strip
// (spriteVagues.jpg, left to right): pilgrim hasty/tranquil, merchant
// crafty/robust, artist proficient/inspired.
// FB-0044: the commerce tokens are the real BGA art from
// spriteJetonCommerce.jpg (tokaidoduo-commerce.webp): 6 panels, one
// per boutique offer, left to right — pottery 4, pottery 3, fan 3,
// fan 2, doll 3, kimono 4 — replacing the ware emoji wherever a Ware
// appears. A held Ware has no price, so it uses its ware's first
// panel (the coins on it are decorative there).
const TD_WARE_TOKEN = {pottery: {4: 0, 3: 1}, fan: {3: 2, 2: 3}, doll: {3: 4}, kimono: {4: 5}};
const TD_WARE_FIRST = {pottery: 0, fan: 2, doll: 4, kimono: 5};
function tdWare(ware, price) {
  const idx = price === undefined ? TD_WARE_FIRST[ware]
    : ((TD_WARE_TOKEN[ware] || {})[price]);
  if (idx === undefined) return escapeHtml(ware || '');
  return '<span class="tdware" style="background-position-x:' + (idx * 20) +
    '%;" title="' + escapeHtml(ware) + '"></span>';
}
const TD_WAVE_IDX = {pilgrim: {hasty: 0, tranquil: 1}, merchant: {crafty: 2, robust: 3},
  artist: {proficient: 4, inspired: 5}};
// FB-0046: the Hot Spring token, the 1 coin and the 10-coin gold slab
// are the real BGA art from spritePieces.png (tokaidoduo-pieces.webp):
// 3 panels, left to right — hot spring, 1 coin, gold slab. tdCoin()
// replaces the coin emoji wherever a coin amount appears in the Mini
// App, tdGold() the money-bag emoji for gold slabs (10 coins each); the Hot Spring
// token on the board uses panel 0 via .tdhotspring in flip7.html.
// Telegram text keeps the emoji.
function tdPiece(idx, title) {
  return '<span class="tdpiece" style="background-position-x:' + (idx * 50) +
    '%;" title="' + escapeHtml(title || '') + '"></span>';
}
function tdCoin() { return tdPiece(1, 'coin'); }
function tdGold() { return tdPiece(2, 'gold slab (10 coins)'); }
// Pending kinds where the meeple has not moved yet, so the die pick
// can still be cancelled (FB-0030).
const TD_CANCELLABLE = ['pilgrim_wave', 'merchant_dest', 'artist_dest'];
// Coastal town locations on the portrait board, so the boutique list
// is readable without memorising town codes.
const TD_TOWN_WHERE = {c_0: 'top right', c_4: 'right', c_9: 'lower right',
  c_13: 'bottom right', c_18: 'bottom left', c_23: 'lower left',
  c_27: 'left', c_31: 'top left'};
function tdWaveText(g, ch, side) {
  if (!side) return '—';
  return ((g.wave_info || {})[ch] || {})[side] || side;
}
function tdSellLines(g, p) {
  const counts = {};
  p.wares.forEach(w => { counts[w] = (counts[w] || 0) + 1; });
  return Object.entries(counts).map(([w, n]) => {
    const offers = Object.entries(g.boutiques || {}).filter(([, b]) => b.ware === w)
      .map(([t, b]) => {
        let per = b.price + (p.waves.merchant === 'crafty' ? 1 : 0);
        return t + ' ' + per + ' ' + tdCoin() + (p.merchant_pos === t ? ' ★ here' : '');
      });
    return tdWare(w) + w + (n > 1 ? ' ×' + n : '') + ' → ' + offers.join(' / ');
  });
}
function tdRender() {
  const g = TDG.board;
  if (!g) return;
  const turn = document.getElementById('tdTurn');
  const board = document.getElementById('tdBoard');
  const actions = document.getElementById('tdActions');
  const join = document.getElementById('tdJoin');
  const start = document.getElementById('tdStart');
  const rematch = document.getElementById('tdRematch');
  [join, start, rematch].forEach(el => el.classList.add('hidden'));
  actions.innerHTML = '';
  document.getElementById('tdLog').textContent = (g.log || []).join('\n');
  const names = g.players.map(p => escapeHtml(p.name) + (p.npc ? ' 🤖' : '') +
    ' <b>' + (p.faith + p.commerce + p.culture) + ' pts</b>').join(' vs ');
  if (g.phase === 'lobby') {
    turn.innerHTML = '🗾 Tokaido Duo lobby — ' + g.players.length + '/2 · ' + names;
    board.innerHTML = '<div class="tdlobby">Join, then anyone taps Start.<br>Each player controls a Pilgrim, a Merchant and an Artist.</div>';
    if (!g.is_player) join.classList.remove('hidden');
    start.classList.remove('hidden');
    return;
  }
  const dice = ['pilgrim', 'merchant', 'artist'].map(ch =>
    (g.char_emoji[ch] || '') + ' ' + (g.dice[ch] !== undefined ? g.dice[ch] : '?') +
    (g.dice_taken.includes(ch) ? ' ✓' : '')).join(' · ');
  turn.innerHTML = g.phase === 'game_end'
    ? '🏆 ' + (g.winner === null ? 'Shared victory!' :
        escapeHtml((g.players[g.winner] || {}).name || 'Winner')) + ' wins! · ' + names
    : '🗾 Round ' + g.round + ' · 🎲 ' + dice + ' · ' + names +
      (g.can_act ? ' · <b>your move</b>' : '');
  if (TDG.newVer) turn.innerHTML += ' · 🔄 <b>New version — reopen the Mini App</b>';
  if (g.phase === 'game_end') rematch.classList.remove('hidden');
  let html = '<div class="tdboard">';
  // meeples: pilgrim on the ring, merchant on towns, artist in zones.
  // FB-0024: when a Merchant or a Pilgrim is at a boutique, its marker
  // sits exactly on the boutique symbol (TOWN_POS) — not offset towards
  // the wrapped-package symbol at the board edge (PACKAGE_POS, where
  // the boutique pill already sits). A Pilgrim on a coastal station is
  // at that town's boutique, so it uses the same symbol. If one
  // player's Merchant and Pilgrim share a boutique, split them sideways
  // so both markers stay visible on the boutique symbol.
  // FB-0047: two Artists may share a zone (artist_destinations has no
  // exclusion, unlike Pilgrim/Merchant) — without an offset the second
  // meeple lands exactly on the first and one artist disappears.
  // Split them sideways too, so both stay visible in the zone.
  g.players.forEach((p, i) => {
    const col = p.color === 'purple' ? 'purple' : 'green';
    const mTown = (g.town_pos || {})[p.merchant_pos];
    const pTownName = 'c_' + p.pilgrim_pos;
    const pTown = (g.town_pos || {})[pTownName];
    const together = !!(mTown && pTown && p.merchant_pos === pTownName);
    const sameZone = g.players.length > 1 && g.players[1 - i] &&
      g.players[1 - i].artist_zone === p.artist_zone;
    const [sx, sy] = pTown || tdStationPos(g, p.pilgrim_pos);
    html += tdMeeple(sx + (together ? 3 : 0), sy, col, 'pilgrim', p.name + ' Pilgrim @ station ' + p.pilgrim_pos + ' (' + (g.stations[p.pilgrim_pos] || '') + ')');
    if (mTown) html += tdMeeple(mTown[0] - (together ? 3 : 0), mTown[1], col, 'merchant', p.name + ' Merchant @ ' + p.merchant_pos);
    const zp = (g.zone_pos || [])[p.artist_zone];
    if (zp) html += tdMeeple(zp[0] + (sameZone ? (i === 0 ? -2 : 2) : 0), zp[1] + 3, col, 'artist', p.name + ' Artist @ ' + ((g.zones[p.artist_zone] || {}).name || ''));
  });
  // FB-0028 / FB-0040 / FB-0041: the Hot Spring token itself, on the
  // board — always. It sits on its drawn place: the large dashed
  // hot-spring circle at the bottom-left of the board art
  // (board 789x1600: centre ~x=105, y=1303 -> 13.3%, 81.4%), not in
  // the middle of the board — Annalisa asked for it exactly there.
  // FB-0046: the token is the real BGA art from spritePieces.png
  // (tokaidoduo-pieces.webp, panel 0) via .tdhotspring in flip7.html,
  // not the hotspring.jpg art used before.
  // Grey ring while unclaimed ('nobody holds it yet'), holder's
  // colour ring once a Pilgrim visits a Hot Spring and takes it.
  const hp = (g.hot_spring !== null && g.hot_spring !== undefined)
    ? g.players[g.hot_spring] : null;
  html += '<span class="tdhotspring' + (hp ? ' td' + (hp.color === 'purple' ? 'purple' : 'green') : ' tdnone') +
    '" style="top:81.4%;left:13.3%;" title="♨️ Hot Spring token — ' + (hp
      ? 'held by ' + escapeHtml(hp.name) + ' (the other player does not have it)'
      : 'nobody holds it yet — visit a Hot Spring to take it') + '"></span>';
  // FB-0029: the face-up Wave tiles as real tokens on the board, in
  // the three dashed slots at the top (one per character, wave_pos),
  // using the BGA art from spriteVagues.jpg (tokaidoduo-waves.webp).
  // A tile leaves its slot when a player takes it. The full ability
  // text stays in the card under the board (and in the title tooltip).
  (g.waves_board || []).forEach(w => {
    const pos = (g.wave_pos || {})[w.char];
    const idx = (TD_WAVE_IDX[w.char] || {})[w.side];
    if (!pos || idx === undefined) return;
    html += '<span class="tdwavetok tdwave' + idx + '" style="top:' + pos[1].toFixed(1) +
      '%;left:' + pos[0].toFixed(1) + '%;" title="' +
      escapeHtml(w.char + ': ' + tdWaveText(g, w.char, w.side)) + '"></span>';
  });
  // FB-0014: each boutique pill sits exactly over its town's wrapped
  // package symbol at the board edge (package_pos), not offset inwards.
  Object.entries(g.boutiques || {}).forEach(([t, b]) => {
    const pp = (g.package_pos || {})[t] || (g.town_pos || {})[t];
    if (!pp) return;
    html += '<span class="tdbout" style="top:' + pp[1].toFixed(1) + '%;left:' + pp[0].toFixed(1) +
      '%;" title="Boutique ' + t + ': ' + b.ware + ' · ' + b.price + ' coins">' +
      tdWare(b.ware, b.price) + b.price + ' ' + tdCoin() + '</span>';
  });
  // FB-0015: tap the board to move — when a move choice is pending,
  // highlight every legal destination on the board (station, town or
  // zone) so the player can tap it instead of hunting for the button.
  if (g.pending && g.can_act) {
    (g.options || []).forEach(o => {
      let pos = null;
      if (g.pending.kind === 'pilgrim_wave' && o.station !== undefined && o.station !== null) pos = tdStationPos(g, o.station);
      else if (g.pending.kind === 'merchant_dest' && String(o.value).indexOf('dest:') === 0) pos = (g.town_pos || {})[String(o.value).slice(5)];
      else if (g.pending.kind === 'artist_dest' && String(o.value).indexOf('dest:') === 0) pos = (g.zone_pos || [])[Number(String(o.value).slice(5))];
      if (!pos) return;
      html += '<span class="tdtap" style="top:' + pos[1].toFixed(1) + '%;left:' + pos[0].toFixed(1) +
        '%;" data-tap="' + escapeHtml(o.value) + '" title="' + escapeHtml(o.label) + '"></span>';
    });
  }
  html += '</div>';
  // boutiques + waves on board, right under the board (not buried below
  // the seats): what each town buys, where it is, whose Merchant is there,
  // and what each face-up Wave tile does.
  const bouts = Object.entries(g.boutiques || {}).map(([t, b]) => {
    const here = g.players.filter(pp => pp.merchant_pos === t).map(pp => pp.name);
    return '<b>' + t + '</b> (' + (TD_TOWN_WHERE[t] || t) + ') ' +
      tdWare(b.ware, b.price) + b.ware + ' · ' + b.price + ' ' + tdCoin() +
      (here.length ? ' — ' + here.map(escapeHtml).join(', ') + ' here' : '');
  }).join('<br>');
  const wavesOnBoard = (g.waves_board || []).map(w =>
    w.char + ': ' + tdWaveText(g, w.char, w.side)).join('<br>');
  html += '<div class="card small">🏘️ <b>Boutiques</b> — sell a Ware at its town:<br>' + bouts +
    '<br>🌊 <b>Waves on board</b>:<br>' + (wavesOnBoard || 'none') +
    '<br>♨️ Hot Spring: ' + (g.hot_spring !== null && g.hot_spring !== undefined ? 'held by ' + escapeHtml((g.players[g.hot_spring] || {}).name || '') : 'nobody holds it yet') +
    (g.end_triggered ? '<br>🏁 End triggered: ' + escapeHtml(g.end_reason || '') + ' — finish this round.' : '') + '</div>';
  // player seats
  // player seats: each seat IS the BGA player board (FB-0034) — the
  // top half of spritePlateauxJoueurs.png for the first seat, the
  // bottom half for the second — with the player's markers on its
  // printed tracks (culture, commerce, temple lanterns, garden
  // circles, painting slots). Wares, sell lines and Waves stay as
  // text under the board, with the exact numbers in the summary line.
  html += '<div class="seats">';
  g.players.forEach((p, i) => {
    const me = p.user_id === TDG.user_id;
    const col = p.color === 'purple' ? 'purple' : 'green';
    const counts = {};
    p.wares.forEach(w => { counts[w] = (counts[w] || 0) + 1; });
    const waresTxt = Object.entries(counts).map(([w, n]) =>
      tdWare(w) + w + (n > 1 ? ' ×' + n : '')).join(', ') || 'no Wares';
    const sellTxt = tdSellLines(g, p).join('<br>') || '—';
    html += '<div class="seat' + (p.is_current ? ' current' : '') + '"><div class="seat-head"><span>' +
      (p.color === 'purple' ? '🟣 ' : '🟢 ') + escapeHtml(p.name) + (p.npc ? ' 🤖' : '') +
      (me ? ' (you)' : '') + '</span><span class="score">' +
      (p.faith + p.commerce + p.culture) + ' pts</span></div>' +
      '<div class="tdpboard' + (i === 1 ? ' pb1' : '') + '">' + tdSeatBoard(g, p, col) + '</div>' +
      '<div class="small">⛩️ ' + p.temple + '×🌳 ' + p.garden + ' = ' + p.faith +
      ' · ' + tdGold() + ' ' + p.gold + ' slabs = ' + p.commerce +
      ' · 🎨 ' + p.gifted + '/10 = ' + p.culture +
      ' · ' + tdCoin() + ' ' + p.coins + '</div>' +
      '<div class="small">🎒 ' + waresTxt + '</div>' +
      '<div class="small">🛍️ Sell:<br>' + sellTxt + '</div>' +
      '<div class="small">🌊 Waves: ' + ['pilgrim', 'merchant', 'artist'].map(ch =>
        ch + ': ' + tdWaveText(g, ch, p.waves[ch])).join(' · ') + '</div></div>';
  });
  html += '</div>';
  board.innerHTML = html;
  board.querySelectorAll('[data-tap]').forEach(el => el.addEventListener('click', () => {
    tdMove('choose', {value: el.dataset.tap});
  }));
  // actions
  if (g.phase === 'game_end') return;
  if (g.pending) {
    if (g.can_act && board.querySelector('[data-tap]')) {
      const hint = document.createElement('div');
      hint.className = 'small';
      hint.textContent = '👆 Tap a glowing spot on the board — or use a button below.';
      actions.appendChild(hint);
    }
    (g.options || []).forEach(o => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'primary';
      b.textContent = o.label;
      b.addEventListener('click', () => tdMove('choose', {value: o.value}));
      actions.appendChild(b);
    });
    // FB-0030: while the meeple has not moved yet, offer to cancel the
    // die pick — the die goes back in the pool and the player picks again.
    if (g.can_act && TD_CANCELLABLE.includes(g.pending.kind)) {
      const c = document.createElement('button');
      c.type = 'button';
      c.className = 'stay';
      c.textContent = '↩️ Cancel move';
      c.addEventListener('click', () => tdMove('cancel', {}));
      actions.appendChild(c);
    }
  } else if (g.can_act) {
    (g.legal.dice || []).forEach(ch => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'hit';
      b.innerHTML = tdDieFace(ch, g.dice[ch]) +
        escapeHtml((g.char_emoji[ch] || '') + ' ' + ch + ' (' + g.dice[ch] + ')');
      b.addEventListener('click', () => tdMove('pick', {char: ch}));
      actions.appendChild(b);
    });
  }
}
document.getElementById('tdJoin').addEventListener('click', () => tdMove('join'));
document.getElementById('tdStart').addEventListener('click', () => tdMove('start'));
document.getElementById('tdRematch').addEventListener('click', () => tdMove('rematch'));
tdLoad();
