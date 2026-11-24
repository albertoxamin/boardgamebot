// Azul Mini App (synced). Loaded by flip7.html router after leaves.js helpers.
const AZ = {user_id: 0, chat_id: null, board: null, timer: null, init: '',
            pick: null, pickKey: ''};
const AZ_TILE_SRC = {
  blue: 'azul_assets/img/blue.svg',
  yellow: 'azul_assets/img/yellow.svg',
  red: 'azul_assets/img/red.svg',
  black: 'azul_assets/img/black.svg',
  white: 'azul_assets/img/cyan.svg',
  first: 'azul_assets/img/first-player.svg'
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
function azSlots(tiles, size) {
  let html = '';
  const n = Math.max(size || tiles.length, tiles.length);
  for (let i = 0; i < n; i++) html += i < tiles.length ? azTile(tiles[i]) : '<span class="azempty"></span>';
  return html;
}
function azWall(p, colors) {
  let html = '<div class="azwall">';
  for (let r = 0; r < 5; r++) for (let c = 0; c < 5; c++) {
    const tile = p.wall[r][c];
    html += '<div class="azcell" title="row ' + (r + 1) + ', col ' + (c + 1) + '">' +
            (tile ? azTile(tile) : '') + '</div>';
  }
  return html + '</div>';
}
function azPlayer(p, b) {
  const lines = p.pattern.map((line, i) =>
    '<div class="azline"><span class="azlabel">' + (i + 1) + '</span>' +
    azSlots(line, i + 1) + '</div>').join('');
  const penalty = [-1, -1, -2, -2, -2, -3, -3].slice(0, p.floor.length).reduce((a, x) => a + x, 0);
  return '<div class="azplayer' + (p.is_current ? ' azcurrent' : '') + '">' +
    '<div class="azhead"><span>' + escapeHtml(p.name) + (p.npc ? ' 🤖' : '') +
    (p.winner ? ' 🏆' : '') + '</span><span class="azscore">' + p.score + ' pts</span></div>' +
    '<div class="azrow">' + azWall(p, b.colors) +
    '<div style="margin-left:10px">' + lines +
    '<div class="azline"><span class="azlabel">🧹</span>' + azSlots(p.floor, 7) +
    '<span class="azlabel">-' + (-penalty) + '</span></div></div></div></div>';
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
  const pickKey = [b.phase, b.round, b.current, b.pending ? 'p' : 'd', b.can_act].join(':');
  if (AZ.pickKey !== pickKey) { AZ.pick = null; AZ.pickKey = pickKey; }
  [join, start, rematch].forEach(el => el.classList.add('hidden'));
  opts.innerHTML = '';
  actions.innerHTML = '';
  if (b.phase === 'lobby') {
    turn.textContent = '🔷 Azul lobby — ' + b.players.length + '/4 players';
    board.innerHTML = '<div class="table azlobby lobby-note">Join, then anyone taps Start.</div>' +
      b.players.map(p => '<div class="azplayer"><div class="azhead">' + escapeHtml(p.name) + '</div></div>').join('');
    if (!b.is_player) join.classList.remove('hidden');
    start.classList.remove('hidden');
    return;
  }
  const head = '🔷 Round ' + b.round + ' · bag ' + b.bag + ' · lid ' + b.lid +
    ' · first: ' + escapeHtml(b.players[b.first_player] ? b.players[b.first_player].name : '?');
  if (b.phase === 'game_end') {
    turn.textContent = head + ' · 🏆 ' + (b.winners || []).map(i => escapeHtml(b.players[i].name)).join(' & ');
    board.innerHTML = b.players.map(p => azPlayer(p, b)).join('');
    rematch.classList.remove('hidden');
    return;
  }
  const cur = b.players[b.current];
  turn.textContent = head + ' · ' + (cur ? escapeHtml(cur.name) : '?') + "'s turn" +
    (b.can_act ? ' (you)' : '');
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
    b.players.map(p => azPlayer(p, b)).join('');
  if (b.can_act && b.pending) {
    const hint = '<div class="small">Picked: ' + b.pending.tiles.map(azTile).join('') +
      (b.pending.marker ? azTile('first') : '') + ' — choose a line:</div>';
    opts.innerHTML = hint + b.pending.rows.map(r =>
      '<button class="azopt" data-az-act="place" data-az-row="' + r + '">Line ' + (r + 1) + '</button>').join('') +
      '<button class="azopt" data-az-act="place" data-az-row="-1">🧹 Floor</button>';
  } else if (b.can_act) {
    if (AZ.pick) {
      opts.innerHTML = '<div class="small">Tap a tile in the highlighted ' +
        escapeHtml(azSourceLabel(AZ.pick.source, AZ.pick.index)) +
        '.</div><button class="azopt" data-az-clear="1">Cancel</button>';
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
    AZ.pick = {source: source, index: index};
    azRender();
  });
  document.getElementById('azJoin').addEventListener('click', () => azMove('join'));
  document.getElementById('azStart').addEventListener('click', () => azMove('start'));
  document.getElementById('azRematch').addEventListener('click', () => azMove('rematch'));
  if (!document.getElementById('azul').classList.contains('hidden')) azLoad();
})();
