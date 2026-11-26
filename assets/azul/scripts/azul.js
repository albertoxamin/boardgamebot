// Azul Mini App (synced). Loaded by flip7.html router after leaves.js helpers.

const AZ_HOW_TO_PLAY_URL = 'https://youtu.be/byHjDCxF5WU?si=aTYP9yfTQMTcqRXY';
const AZ = {user_id: 0, chat_id: null, board: null, timer: null, init: '',
            pick: null, pickKey: ''};
const AZ_TILE_SRC = {
  blue: '/assets/azul/images/azul_assets/img/blue.svg',
  yellow: '/assets/azul/images/azul_assets/img/yellow.svg',
  red: '/assets/azul/images/azul_assets/img/red.svg',
  black: '/assets/azul/images/azul_assets/img/black.svg',
  white: '/assets/azul/images/azul_assets/img/cyan.svg',
  first: '/assets/azul/images/azul_assets/img/first-player.svg'
};

function azLog(s) { const e = document.getElementById('azLog'); if (e) e.textContent += s + '\n'; }
function azApi(path, opts) { return fetch(path, opts).then(r => r.json()); }
function azChatId(raw) {
  let s = String(raw || '');
  if (s.startsWith('azul')) s = s.slice(4);
  const n = parseInt(s, 10);
  return isNaN(n) ? 0 : n;
}
async function azLoad() {
  const tg = tgInit();
  if (!tg.id) {
    document.getElementById('azTurn').textContent = 'Open as Telegram Mini App via the bot link.';
    return;
  }
  AZ.user_id = tg.id;
  AZ.init = tg.init;
  const qp = new URLSearchParams(location.search);
  const pref = azChatId(tg.start) || azChatId(qp.get('app')) ||
               parseInt(qp.get('chat_id'), 10) || azChatId(tg.chat_instance);
  const r = await azApi('/api/azul/mygames?init_data=' + encodeURIComponent(tg.init));
  const mine = r.games || [];
  const pick = mine.find(g => g.chat_id === pref) || mine.find(g => g.phase !== 'game_end') || mine[0];
  if (pick) azSelect(pick.chat_id);
  else if (pref) {
    const cr = await azApi('/api/azul/create', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({init_data: tg.init, chat_id: pref})
    });
    if (cr.game) azSelect(cr.game.chat_id);
    else azLog('⛔ ' + (cr.error || 'create failed'));
  } else {
    document.getElementById('azTurn').textContent = 'No Azul game yet — send /azul in a chat.';
  }
}
async function azSelect(chat_id) {
  AZ.chat_id = chat_id;
  await azRefresh();
  if (AZ.timer) clearInterval(AZ.timer);
  AZ.timer = setInterval(azRefresh, 3000);
}
async function azRefresh() {
  if (!AZ.chat_id) return;
  const q = '?chat_id=' + encodeURIComponent(AZ.chat_id) + '&init_data=' + encodeURIComponent(AZ.init);
  const r = await azApi('/api/azul/game' + q);
  if (r.game) { AZ.board = r.game; azRender(); }
}
async function azMove(action, extra) {
  const body = Object.assign({chat_id: AZ.chat_id, action: action, init_data: AZ.init}, extra || {});
  const r = await azApi('/api/azul/move', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  if (r.events) r.events.forEach(e => azLog(e));
  if (r.error) azLog('⛔ ' + r.error);
  if (r.game) { AZ.board = r.game; azRender(); }
}
function azTile(t) {
  if (!t) return '';
  const src = AZ_TILE_SRC[t] || AZ_TILE_SRC.white;
  return '<img class="aztile" src="' + src + '" alt="' + escapeHtml(t) +
         '" title="' + escapeHtml(t) + '">';
}
function azPickColors(b, source, index) {
  return b.options.filter(o => o.source === source && o.index === index).map(o => o.color);
}
function azPickTile(t, source, index) {
  return '<button class="aztilepick" data-az-color="' + escapeHtml(t) +
         '" data-az-src="' + source + '" data-az-index="' + index +
         '" title="Take ' + escapeHtml(t) + '">' + azTile(t) + '</button>';
}
function azSourceLabel(source, index) {
  return source === 'center' ? 'center' : 'factory ' + (index + 1);
}
// Printed board geometry (playerboard1.webp is 740x484). Cell rects measured
// from the board art: pattern lines and wall share 5 rows, the wall sits
// right of the gold arrows, the floor line is the 7 arched slots below
// (interiors y 400-480 — the old 345-425 band floated tiles above the
// arches, over the penalty numbers).
// Tiles are placed over the printed slots, like BGA does, so they land
// exactly on the art instead of floating over a darkened backdrop.
const AZ_BW = 740, AZ_BH = 484;
const AZ_COLS = [8, 77, 146, 215, 284, 353];
const AZ_WALL_X = [387, 456, 525, 593, 661, 731];
const AZ_ROWS = [5, 76, 143, 213, 282, 351];
const AZ_FLOOR_X = [8, 61, 114, 167, 220, 273, 326, 379];
const AZ_FLOOR_Y = [400, 480];
function azPos(x0, y0, x1, y1, tile, extraCls) {
  const left = ((x0 + 3) / AZ_BW * 100).toFixed(2);
  const top = ((y0 + 3) / AZ_BH * 100).toFixed(2);
  const w = ((x1 - x0 - 6) / AZ_BW * 100).toFixed(2);
  const h = ((y1 - y0 - 6) / AZ_BH * 100).toFixed(2);
  return '<span class="azpos' + (extraCls ? ' ' + extraCls : '') + '" style="left:' + left + '%;top:' + top +
         '%;width:' + w + '%;height:' + h + '%">' + azTile(tile) + '</span>';
}
function azZone(x0, y0, x1, y1, row, label) {
  const left = (x0 / AZ_BW * 100).toFixed(2);
  const top = (y0 / AZ_BH * 100).toFixed(2);
  const w = ((x1 - x0) / AZ_BW * 100).toFixed(2);
  const h = ((y1 - y0) / AZ_BH * 100).toFixed(2);
  return '<span class="azzone" data-az-row="' + row + '" title="' + escapeHtml(label || '') +
         '" style="left:' + left + '%;top:' + top + '%;width:' + w + '%;height:' + h + '%">' +
         (label ? '<span class="azzonelabel">' + escapeHtml(label) + '</span>' : '') + '</span>';
}
function azPlayer(p, b, idx) {
  let tiles = '';
  // Pattern lines: tiles fill each row from the right, against the wall.
  p.pattern.forEach((line, i) => {
    line.forEach((t, j) => {
      const c = 4 - j;
      tiles += azPos(AZ_COLS[c], AZ_ROWS[i], AZ_COLS[c + 1], AZ_ROWS[i + 1], t);
    });
  });
  for (let r = 0; r < 5; r++) for (let c = 0; c < 5; c++) {
    const t = p.wall[r][c];
    if (t) tiles += azPos(AZ_WALL_X[c], AZ_ROWS[r], AZ_WALL_X[c + 1], AZ_ROWS[r + 1], t);
  }
  p.floor.forEach((t, j) => {
    // Floor slots are taller than wide; keep the tile square, centred
    // in the slot instead of stretching it to fill the arch.
    const x0 = AZ_FLOOR_X[j], x1 = AZ_FLOOR_X[j + 1];
    const side = x1 - x0 - 6;
    const y0 = AZ_FLOOR_Y[0] + (AZ_FLOOR_Y[1] - AZ_FLOOR_Y[0] - side) / 2 - 3;
    tiles += azPos(x0, y0, x1, y0 + side + 6, t);
  });
  // Tap-to-place: when this player has just picked tiles, the legal
  // pattern lines and the floor line become tappable on their own
  // board, with ghost tiles showing exactly where the pick would land
  // — no Line/Floor buttons. Other players' boards stay view-only.
  // NB: when the current player is the NPC you play for them (the
  // server sets can_act), so the zones go on the current player's
  // board — not only when its user_id is yours. FB-0161: on the NPC's
  // turn the "tap a highlighted line" hint showed but no line was
  // highlighted, because the NPC's user_id never matches the viewer.
  const placing = b.can_act && b.pending && idx === b.current;
  if (placing) {
    const pend = b.pending;
    const rows = pend.rows || [];
    rows.forEach(r => {
      const line = p.pattern[r];
      const free = (r + 1) - line.length;
      const ghosts = Math.max(0, Math.min(pend.tiles.length, free));
      for (let k = 0; k < ghosts; k++) {
        const c = 4 - line.length - k;
        tiles += azPos(AZ_COLS[c], AZ_ROWS[r], AZ_COLS[c + 1], AZ_ROWS[r + 1],
                       pend.color, 'azghost');
      }
      tiles += azZone(AZ_COLS[0], AZ_ROWS[r], AZ_COLS[5], AZ_ROWS[r + 1], r,
                      'Line ' + (r + 1));
    });
    tiles += azZone(AZ_FLOOR_X[0], AZ_FLOOR_Y[0],
                    AZ_FLOOR_X[AZ_FLOOR_X.length - 1] + 53, AZ_FLOOR_Y[1], -1,
                    '🧹 Floor');
  }
  return '<div class="azplayer' + (p.is_current ? ' azcurrent' : '') + '">' +
    '<div class="azhead"><span>' + escapeHtml(p.name) + (p.npc ? ' 🤖' : '') +
    (p.winner ? ' 🏆' : '') +
    (p.is_current && b.phase === 'draft' ? ' <span class="azturnbadge">👉 TURNO</span>' : '') +
    '</span><span class="azscore">' + p.score + ' pts</span></div>' +
    '<div class="azboard">' + tiles + '</div></div>';
}
function azRender() {
  const b = AZ.board;
  if (!b) return;
  const turn = document.getElementById('azTurn');
  const board = document.getElementById('azBoard');
  const opts = document.getElementById('azOpts');
  const actions = document.getElementById('azActions');
  const join = document.getElementById('azJoin');
  const start = document.getElementById('azStart');
  const rematch = document.getElementById('azRematch');
  const howto = document.getElementById('azHowTo');
  const banner = document.getElementById('azTurnBanner');
  const pickKey = [b.phase, b.round, b.current, b.pending ? 'p' : 'd', b.can_act].join(':');
  if (AZ.pickKey !== pickKey) { AZ.pick = null; AZ.pickKey = pickKey; }
  [join, start, howto, rematch].forEach(el => el.classList.add('hidden'));
  opts.innerHTML = '';
  actions.innerHTML = '';
  if (b.phase === 'lobby') {
    turn.textContent = '🔷 Azul lobby — ' + b.players.length + '/4 players';
    banner.classList.add('hidden');
    board.innerHTML = '<div class="table azlobby lobby-note">Join, then anyone taps Start.</div>' +
      b.players.map(p => '<div class="azplayer"><div class="azhead">' + escapeHtml(p.name) + '</div></div>').join('');
    if (!b.is_player) join.classList.remove('hidden');
    start.classList.remove('hidden');
    howto.classList.remove('hidden');
    return;
  }
  const head = '🔷 Round ' + b.round + ' · bag ' + b.bag + ' · lid ' + b.lid +
    ' · first: ' + escapeHtml(b.players[b.first_player] ? b.players[b.first_player].name : '?');
  if (b.phase === 'game_end') {
    turn.textContent = head;
    const winNames = (b.winners || []).map(i => b.players[i] ? b.players[i].name : '?');
    banner.className = 'azturnbanner azwin';
    banner.textContent = '🏆 ' + winNames.join(' & ') +
      (winNames.length === 1 ? ' wins the game!' : ' win the game!');
    board.innerHTML = b.players.map((p, i) => azPlayer(p, b, i)).join('');
    rematch.classList.remove('hidden');
    return;
  }
  const cur = b.players[b.current];
  // Whose turn it is gets its own big banner — it used to hide at the
  // end of the small info line and was easy to miss.
  turn.textContent = head;
  banner.classList.remove('hidden');
  if (cur && cur.user_id === AZ.user_id) {
    banner.className = 'azturnbanner azmine';
    banner.textContent = '👉 Your turn!';
  } else if (cur) {
    banner.className = 'azturnbanner azwait';
    banner.textContent = '⏳ ' + cur.name + "'s turn" +
      (cur.npc && b.can_act ? ' — you play for them' : '');
  } else {
    banner.className = 'azturnbanner azwait';
    banner.textContent = '⏳ Waiting…';
  }
  const picking = b.can_act && !b.pending;
  const facs = b.factories.map(f => {
    const avail = azPickColors(b, 'factory', f.index);
    const sel = picking && AZ.pick && AZ.pick.source === 'factory' && AZ.pick.index === f.index;
    const cls = 'azfac' + (picking && avail.length ? ' azpick' : '') + (sel ? ' azsel' : '');
    const tiles = f.tiles.map(t => sel && avail.indexOf(t) >= 0
      ? azPickTile(t, 'factory', f.index) : azTile(t)).join('');
    return '<div class="' + cls + '" data-az-src="factory" data-az-index="' + f.index + '">' + tiles + '</div>';
  }).join('');
  const centerAvail = azPickColors(b, 'center', 0);
  const centerSel = picking && AZ.pick && AZ.pick.source === 'center';
  const centerCls = 'azfac azcenter' + (picking && centerAvail.length ? ' azpick' : '') +
    (centerSel ? ' azsel' : '');
  const centerTiles = (b.center.marker ? azTile('first') : '') +
    b.center.tiles.map(t => centerSel && centerAvail.indexOf(t) >= 0
      ? azPickTile(t, 'center', 0) : azTile(t)).join('');
  const centerHtml = '<div class="' + centerCls + '" data-az-src="center" data-az-index="0">' +
    (centerTiles || '<span class="small">empty</span>') + '</div>';
  board.innerHTML = '<div class="table aztable"><div class="small">FACTORIES</div><div>' + (facs || '<span class="small">empty</span>') +
    '</div><div class="small" style="margin-top:8px">CENTER</div>' + centerHtml + '</div>' +
    b.players.map((p, i) => azPlayer(p, b, i)).join('');
  if (b.can_act && b.pending) {
    // No Line/Floor buttons: tap a highlighted line (or the floor line)
    // on your own board — the ghosts show where the tiles land.
    opts.innerHTML = '<div class="small">Picked: ' + b.pending.tiles.map(azTile).join('') +
      (b.pending.marker ? azTile('first') : '') +
      ' — tap a highlighted line on your board, or the floor line.</div>';
  } else if (b.can_act) {
    if (AZ.pick) {
      opts.innerHTML = '<div class="small">Tap a tile in the highlighted ' +
        escapeHtml(azSourceLabel(AZ.pick.source, AZ.pick.index)) +
        ' — or tap it again to cancel.</div>';
    } else {
      opts.innerHTML = '<div class="small">Tap a factory or the center, then tap a tile.</div>';
    }
  }
}
(function azStart() {
  if (!document.getElementById('azBoard')) return;
  document.getElementById('azOpts').addEventListener('click', e => {
    const clear = e.target.closest('[data-az-clear]');
    if (clear) { AZ.pick = null; azRender(); return; }
    const btn = e.target.closest('[data-az-act]');
    if (btn && btn.dataset.azAct === 'place') azMove('place', {row: parseInt(btn.dataset.azRow, 10)});
  });
  document.getElementById('azBoard').addEventListener('click', e => {
    // Tap a highlighted pattern line / floor line on your board to place.
    const row = e.target.closest('[data-az-row]');
    if (row) {
      azMove('place', {row: parseInt(row.dataset.azRow, 10)});
      return;
    }
    const tile = e.target.closest('[data-az-color]');
    if (tile) {
      AZ.pick = null;
      azMove('take', {source: tile.dataset.azSrc, index: parseInt(tile.dataset.azIndex, 10),
                      color: tile.dataset.azColor});
      return;
    }
    const card = e.target.closest('[data-az-src]');
    if (!card || !AZ.board || !AZ.board.can_act || AZ.board.pending) return;
    const source = card.dataset.azSrc;
    const index = parseInt(card.dataset.azIndex, 10);
    if (!azPickColors(AZ.board, source, index).length) return;
    // Tap the selected factory/center again to cancel the pick.
    if (AZ.pick && AZ.pick.source === source && AZ.pick.index === index) {
      AZ.pick = null;
      azRender();
      return;
    }
    AZ.pick = {source: source, index: index};
    azRender();
  });
  document.getElementById('azJoin').addEventListener('click', () => azMove('join'));
  document.getElementById('azStart').addEventListener('click', () => azMove('start'));
document.getElementById('azHowTo').addEventListener('click', () => {
  try {
    if (window.Telegram && Telegram.WebApp && Telegram.WebApp.openLink)
      Telegram.WebApp.openLink(AZ_HOW_TO_PLAY_URL);
    else window.open(AZ_HOW_TO_PLAY_URL, '_blank');
  } catch (e) { window.open(AZ_HOW_TO_PLAY_URL, '_blank'); }
});
  document.getElementById('azRematch').addEventListener('click', () => azMove('rematch'));
  if (!document.getElementById('azul').classList.contains('hidden')) azLoad();
})();
