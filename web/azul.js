// Azul Mini App (synced). Loaded by flip7.html router after leaves.js helpers.
const AZ = {user_id: 0, chat_id: null, board: null, timer: null, init: ''};

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
  const cls = t === 'first' ? 'az-first' : 'az-' + t;
  return '<span class="aztile ' + cls + '" title="' + escapeHtml(t) + '"></span>';
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
  [join, start, rematch].forEach(el => el.classList.add('hidden'));
  opts.innerHTML = '';
  actions.innerHTML = '';
  if (b.phase === 'lobby') {
    turn.textContent = '🔷 Azul lobby — ' + b.players.length + '/4 players';
    board.innerHTML = '<div class="table lobby-note">Join, then anyone taps Start.</div>' +
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
  const facs = b.factories.map(f =>
    '<div class="azfac">' + f.tiles.map(azTile).join('') + '</div>').join('');
  const center = (b.center.marker ? azTile('first') : '') +
    b.center.tiles.map(azTile).join('') || '<span class="small">empty</span>';
  board.innerHTML = '<div class="table"><div class="small">FACTORIES</div><div>' + (facs || '<span class="small">empty</span>') +
    '</div><div class="small" style="margin-top:8px">CENTER</div><div class="azrow">' + center + '</div></div>' +
    b.players.map(p => azPlayer(p, b)).join('');
  if (b.can_act && b.pending) {
    const hint = '<div class="small">Picked: ' + b.pending.tiles.map(azTile).join('') +
      (b.pending.marker ? azTile('first') : '') + ' — choose a line:</div>';
    opts.innerHTML = hint + b.pending.rows.map(r =>
      '<button class="azopt" data-az-act="place" data-az-row="' + r + '">Line ' + (r + 1) + '</button>').join('') +
      '<button class="azopt" data-az-act="place" data-az-row="-1">🧹 Floor</button>';
  } else if (b.can_act) {
    opts.innerHTML = b.options.map(o => {
      const label = (o.source === 'center' ? 'C' : 'F' + (o.index + 1)) + ' ' +
        (o.color === 'first' ? '⭐' : azTile(o.color)) + '×' + o.count;
      return '<button class="azopt" data-az-act="take" data-az-source="' + o.source +
        '" data-az-index="' + o.index + '" data-az-color="' + o.color + '">' + label + '</button>';
    }).join('');
  }
}
(function azStart() {
  if (!document.getElementById('azBoard')) return;
  document.getElementById('azOpts').addEventListener('click', e => {
    const btn = e.target.closest('[data-az-act]');
    if (!btn) return;
    if (btn.dataset.azAct === 'place') azMove('place', {row: parseInt(btn.dataset.azRow, 10)});
    else azMove('take', {source: btn.dataset.azSource, index: parseInt(btn.dataset.azIndex, 10),
                         color: btn.dataset.azColor});
  });
  document.getElementById('azJoin').addEventListener('click', () => azMove('join'));
  document.getElementById('azStart').addEventListener('click', () => azMove('start'));
  document.getElementById('azRematch').addEventListener('click', () => azMove('rematch'));
  if (!document.getElementById('azul').classList.contains('hidden')) azLoad();
})();
