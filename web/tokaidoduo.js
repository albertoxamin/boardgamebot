const TDG = {user_id: 0, chat_id: null, board: null, timer: null, init: ''};

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
function tdStationPos(i) {
  // Ring stations, clockwise from the SE Coastal town (station 0).
  // Board is displayed rotated -90deg (portrait, like BGA), so the
  // landscape ellipse (x = 50+36cos, y = 52+40sin) maps to
  // new_x = old_y, new_y = 100 - old_x.
  const a = (45 + i * (360 / 37)) * Math.PI / 180;
  return [52 + 40 * Math.sin(a), 50 - 36 * Math.cos(a)];
}
function tdMeeple(x, y, color, label, title) {
  return '<span class="tdmeeple td' + color + '" style="top:' + y.toFixed(1) +
         '%;left:' + x.toFixed(1) + '%;" title="' + escapeHtml(title) + '">' +
         escapeHtml(label) + '</span>';
}
function tdPaintTile(t, idx) {
  if (t.gifted) return '<span class="tdpaint gifted" title="Gifted">✓</span>';
  if (!t.revealed) return '<span class="tdpaint back" title="Face-down Painting">?</span>';
  const em = (TDG.board.zone_icon_emoji || {})[t.icon] || t.icon;
  return '<span class="tdpaint" title="' + escapeHtml(t.icon) + '">' + em + '</span>';
}
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
        return t + ' ' + per + '🪙' + (p.merchant_pos === t ? ' ★ here' : '');
      });
    return (g.ware_emoji[w] || '') + w + (n > 1 ? ' ×' + n : '') + ' → ' + offers.join(' / ');
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
  if (g.phase === 'game_end') rematch.classList.remove('hidden');
  let html = '<div class="tdboard">';
  // meeples: pilgrim on the ring, merchant on towns, artist in zones
  g.players.forEach((p, i) => {
    const col = p.color === 'purple' ? 'purple' : 'green';
    const [sx, sy] = tdStationPos(p.pilgrim_pos);
    html += tdMeeple(sx - 2.5, sy - 3, col, '⛩', p.name + ' Pilgrim @ station ' + p.pilgrim_pos + ' (' + (g.stations[p.pilgrim_pos] || '') + ')');
    const tp = (g.town_pos || {})[p.merchant_pos];
    if (tp) html += tdMeeple(tp[0] + 2.5, tp[1] - 3, col, '$', p.name + ' Merchant @ ' + p.merchant_pos);
    const zp = (g.zone_pos || [])[p.artist_zone];
    if (zp) html += tdMeeple(zp[0], zp[1] + 3, col, '🎨', p.name + ' Artist @ ' + ((g.zones[p.artist_zone] || {}).name || ''));
  });
  // FB-0010/FB-0011: boutiques and waves ON the board itself, not just
  // in the card underneath it. Boutique pills sit just inside each
  // coastal town (ware + price); the face-up Wave tiles sit in a strip
  // across the top of the board (icon + side, full ability in the title).
  html += '<div class="tdwaves">' + (g.waves_board || []).map(w =>
    '<span class="tdwave" title="' + escapeHtml(tdWaveText(g, w.char, w.side)) + '">' +
    (g.char_emoji[w.char] || '') + ' ' + w.side.charAt(0).toUpperCase() + w.side.slice(1) +
    '</span>').join('') + '</div>';
  Object.entries(g.boutiques || {}).forEach(([t, b]) => {
    const tp = (g.town_pos || {})[t];
    if (!tp) return;
    const bx = tp[0] + (50 - tp[0]) * 0.18, by = tp[1] + (50 - tp[1]) * 0.18;
    html += '<span class="tdbout" style="top:' + by.toFixed(1) + '%;left:' + bx.toFixed(1) +
      '%;" title="Boutique ' + t + ': ' + b.ware + ' · ' + b.price + ' coins">' +
      (g.ware_emoji[b.ware] || '') + ' ' + b.price + '🪙</span>';
  });
  html += '</div>';
  // boutiques + waves on board, right under the board (not buried below
  // the seats): what each town buys, where it is, whose Merchant is there,
  // and what each face-up Wave tile does.
  const bouts = Object.entries(g.boutiques || {}).map(([t, b]) => {
    const here = g.players.filter(pp => pp.merchant_pos === t).map(pp => pp.name);
    return '<b>' + t + '</b> (' + (TD_TOWN_WHERE[t] || t) + ') ' +
      (g.ware_emoji[b.ware] || '') + b.ware + ' · ' + b.price + '🪙' +
      (here.length ? ' — ' + here.map(escapeHtml).join(', ') + ' here' : '');
  }).join('<br>');
  const wavesOnBoard = (g.waves_board || []).map(w =>
    w.char + ': ' + tdWaveText(g, w.char, w.side)).join('<br>');
  html += '<div class="card small">🏘️ <b>Boutiques</b> — sell a Ware at its town:<br>' + bouts +
    '<br>🌊 <b>Waves on board</b>:<br>' + (wavesOnBoard || 'none') +
    (g.hot_spring !== null && g.hot_spring !== undefined ? '<br>♨️ Hot Spring held by ' + escapeHtml((g.players[g.hot_spring] || {}).name || '') : '') +
    (g.end_triggered ? '<br>🏁 End triggered: ' + escapeHtml(g.end_reason || '') + ' — finish this round.' : '') + '</div>';
  // player seats
  html += '<div class="seats">';
  g.players.forEach((p, i) => {
    const me = p.user_id === TDG.user_id;
    const counts = {};
    p.wares.forEach(w => { counts[w] = (counts[w] || 0) + 1; });
    const waresTxt = Object.entries(counts).map(([w, n]) =>
      (g.ware_emoji[w] || '') + w + (n > 1 ? ' ×' + n : '')).join(', ') || 'no Wares';
    const sellTxt = tdSellLines(g, p).join('<br>') || '—';
    html += '<div class="seat' + (p.is_current ? ' current' : '') + '"><div class="seat-head"><span>' +
      (p.color === 'purple' ? '🟣 ' : '🟢 ') + escapeHtml(p.name) + (p.npc ? ' 🤖' : '') +
      (me ? ' (you)' : '') + '</span><span class="score">' +
      (p.faith + p.commerce + p.culture) + ' pts</span></div>' +
      '<div class="small">⛩️ ' + p.temple + '×🌳 ' + p.garden + ' = ' + p.faith +
      ' · 💰 ' + p.gold + ' slabs = ' + p.commerce +
      ' · 🎨 ' + p.gifted + '/10 = ' + p.culture +
      ' · 🪙 ' + p.coins + '</div>' +
      '<div class="small">🎒 ' + waresTxt + '</div>' +
      '<div class="small">🛍️ Sell:<br>' + sellTxt + '</div>' +
      '<div class="small">🌊 Waves: ' + ['pilgrim', 'merchant', 'artist'].map(ch =>
        ch + ': ' + tdWaveText(g, ch, p.waves[ch])).join(' · ') + '</div>' +
      '<div class="tdpaints">' + p.paintings.map(tdPaintTile).join('') + '</div></div>';
  });
  html += '</div>';
  board.innerHTML = html;
  // actions
  if (g.phase === 'game_end') return;
  if (g.pending) {
    (g.options || []).forEach(o => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'primary';
      b.textContent = o.label;
      b.addEventListener('click', () => tdMove('choose', {value: o.value}));
      actions.appendChild(b);
    });
  } else if (g.can_act) {
    (g.legal.dice || []).forEach(ch => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'hit';
      b.textContent = (g.char_emoji[ch] || '') + ' ' + ch + ' (' + g.dice[ch] + ')';
      b.addEventListener('click', () => tdMove('pick', {char: ch}));
      actions.appendChild(b);
    });
  }
}
document.getElementById('tdJoin').addEventListener('click', () => tdMove('join'));
document.getElementById('tdStart').addEventListener('click', () => tdMove('start'));
document.getElementById('tdRematch').addEventListener('click', () => tdMove('rematch'));
tdLoad();
