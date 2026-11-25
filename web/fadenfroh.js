const FF = {chat_id: null, init: '', board: null, timer: null};

function ffLog(s) {
  const e = document.getElementById('ffLog');
  if (e) e.textContent += s + '\n';
}
function ffApi(path, opts) { return fetch(path, opts).then(r => r.json()); }
function ffChatId(raw) {
  let s = String(raw || '');
  if (s.startsWith('fadenfroh')) s = s.slice(9);
  const n = parseInt(s, 10);
  return isNaN(n) ? 0 : n;
}
async function ffLoad() {
  const tg = tgInit();
  if (!tg.id) {
    document.getElementById('ffTurn').textContent = 'Open as Telegram Mini App via the bot link.';
    return;
  }
  FF.init = tg.init;
  const qp = new URLSearchParams(location.search);
  const pref = ffChatId(tg.start) || ffChatId(qp.get('app')) ||
               parseInt(qp.get('chat_id'), 10) || ffChatId(tg.chat_instance);
  const r = await ffApi('/api/fadenfroh/mygames?init_data=' + encodeURIComponent(tg.init));
  const mine = r.games || [];
  const pick = mine.find(g => g.chat_id === pref) || mine.find(g => g.phase !== 'game_end') || mine[0];
  if (pick) ffSelect(pick.chat_id);
  else if (pref) {
    const cr = await ffApi('/api/fadenfroh/create', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({init_data: tg.init, chat_id: pref})
    });
    if (cr.game) ffSelect(cr.game.chat_id);
    else ffLog('⛔ ' + (cr.error || 'create failed'));
  } else {
    document.getElementById('ffTurn').textContent = 'No Fadenfroh game yet — send /fadenfroh in a chat.';
  }
}
async function ffSelect(chat_id) {
  FF.chat_id = chat_id;
  await ffRefresh();
  if (FF.timer) clearInterval(FF.timer);
  FF.timer = setInterval(ffRefresh, 3000);
}
async function ffRefresh() {
  if (!FF.chat_id) return;
  const q = '?chat_id=' + encodeURIComponent(FF.chat_id) + '&init_data=' + encodeURIComponent(FF.init);
  const r = await ffApi('/api/fadenfroh/game' + q);
  if (r.game) { FF.board = r.game; ffRender(); }
}
async function ffMove(action, extra) {
  const body = Object.assign({chat_id: FF.chat_id, action: action, init_data: FF.init}, extra || {});
  const r = await ffApi('/api/fadenfroh/move', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  if (r.events) r.events.forEach(e => ffLog(e));
  if (r.error) ffLog('⛔ ' + r.error);
  if (r.game) { FF.board = r.game; ffRender(); }
}
function ffIcon(c) {
  return (FF.board && FF.board.symbols ? FF.board.symbols.colors[c] : '') +
    (FF.board && FF.board.symbols ? FF.board.symbols.icons[c] : '');
}
function ffCardTitle(cid) {
  return (FF.board.cards && FF.board.cards[cid] ? FF.board.cards[cid].name : 'card ' + cid);
}
function ffCardHtml(cid) {
  const id = Number(cid);
  return '<span class="ffcard" title="' + escapeHtml(ffCardTitle(id)) + '" style="' +
    ffHalfStyle(id, 0) + '"></span><span class="ffcard" title="' +
    escapeHtml(ffCardTitle(id)) + '" style="' + ffHalfStyle(id, 1) + '"></span>';
}
function ffHalfStyle(id, h) {
  const col = id % 9, row = Math.floor(id / 9);
  return 'background-position:' + (-((col * 2 + h) * 44)) + 'px ' + (-(row * 63)) + 'px';
}
function ffScoreStyle(n) {
  const id = Number(n) - 1;
  return 'background-position:' + (-(id % 4) * 78) + 'px ' + (-Math.floor(id / 4) * 56) + 'px';
}
function ffRowHtml(row) {
  if (!row.length) return '<div class="ffrow"></div>';
  const min = Math.min.apply(null, row.map(h => h.col));
  const max = Math.max.apply(null, row.map(h => h.col));
  const items = row.map(h => {
    let cls = 'ffhalf', style = '', label = '';
    if (h.needle) {
      cls = 'ffneedle'; label = 'needle';
    } else if (h.start) {
      cls = 'ffstart';
      style = 'background:' + ({white: '#f8fafc', yellow: '#facc15', purple: '#a855f7'}[h.c] || '#ddd') +
        ';color:#0f172a'; label = h.c;
    } else {
      style = ffHalfStyle(h.id, h.h); label = ffCardTitle(h.id);
    }
    return '<span class="' + cls + '" style="left:' + ((h.col - min) * 46) + 'px;' + style +
      '" title="' + escapeHtml(label + ' @ column ' + h.col) + '">' + escapeHtml(label) + '</span>';
  });
  return '<div class="ffrow" style="width:' + ((max - min + 1) * 46) + 'px">' + items.join('') + '</div>';
}
function ffButton(label, fn) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'primary'; b.textContent = label;
  b.addEventListener('click', fn);
  return b;
}
function ffRender() {
  const g = FF.board;
  if (!g) return;
  const turn = document.getElementById('ffTurn');
  const goals = document.getElementById('ffGoals');
  const market = document.getElementById('ffMarket');
  const players = document.getElementById('ffPlayers');
  const actions = document.getElementById('ffActions');
  const join = document.getElementById('ffJoin');
  const npc = document.getElementById('ffNpc');
  const start = document.getElementById('ffStart');
  const rematch = document.getElementById('ffRematch');
  [join, npc, start, rematch].forEach(el => el.classList.add('hidden'));
  actions.innerHTML = '';
  document.getElementById('ffLog').textContent = (g.log || []).join('\n');
  const names = g.players.map((p, i) => escapeHtml(p.name) + ' <b>' + p.score + '</b> VP' +
    (p.npc ? ' 🤖' : '')).join(' · ');
  turn.innerHTML = g.phase === 'lobby' ? '🪡 Fadenfroh lobby — ' + g.players.length + '/4 · ' + names :
    g.phase === 'game_end' ? '🏆 ' + escapeHtml((g.players[g.winner] || {}).name || 'Winner') +
      ' wins! · ' + names :
    '🪡 Round ' + g.round + '/5 · ' + g.phase + ' · ' + names + (g.can_act ? ' · <b>your move</b>' : '');
  goals.innerHTML = '🎯 ' + ['A', 'B', 'C', 'D'].map(k =>
    '<span class="ffgoal" title="Goal ' + k + ': ' + g.goals[k] + '">' + k +
    '<span class="ffscore" style="' + ffScoreStyle(g.goals[k]) + '"></span></span>').join('');
  const m = g.market;
  market.innerHTML = g.phase === 'lobby' ? '' : '🛒 Market: 🧵' + m.threads + ' 🪡' + m.needles +
    (m.thimble ? ' 🟘' : '') + ' · ' + (m.offers || []).map((o, i) =>
      '<span title="Offer ' + (i + 1) + '">' + o.map(ffCardHtml).join('') + '</span>').join(' ');
  players.innerHTML = g.phase === 'lobby' ? '' : g.players.map((p, i) =>
    '<div class="ffplayer"><b>' + escapeHtml(p.name) + '</b> · ' + p.score + ' VP · 🧵' +
    p.threads + ' 🪡' + p.needles + (p.thimble ? ' 🟘' : '') + ' · hand ' + p.supply_count +
    (i === g.actor ? ' · <b>turn</b>' : '') + '<div>' + p.rows.map(ffRowHtml).join('') +
    '</div></div>').join('');
  if (g.phase === 'lobby') {
    if (g.is_player) join.classList.remove('hidden');
    start.classList.remove('hidden');
    return;
  }
  if (g.phase === 'game_end') { rematch.classList.remove('hidden'); return; }
  if (!g.can_act) return;
  if (g.phase === 'shopping') {
    if (g.market.threads && g.players[g.actor] && Object.keys(g.market).length) {
      actions.appendChild(ffButton('🧵 Take thread', () => ffMove('material', {kind: 'thread'})));
    }
    if (g.market.needles) {
      actions.appendChild(ffButton('🪡 Take needle', () => ffMove('material', {kind: 'needle'})));
    }
    if (g.market.thimble) {
      actions.appendChild(ffButton('🟘 Take thimble', () => ffMove('material', {kind: 'thimble'})));
    }
    (g.market.offers || []).forEach((o, i) => {
      actions.appendChild(ffButton('🙋 Take offer ' + (i + 1) + ' (' + o.length + ')',
        () => ffMove('pass', {offer: i})));
    });
    return;
  }
  (g.options || []).forEach(o => {
    actions.appendChild(ffButton(o.label, () => ffMove('choice', {value: o.value})));
  });
  if (g.pending && g.pending.kind === 'place' && (g.pending.cards || []).length) {
    g.pending.cards.forEach((cid, i) => {
      actions.appendChild(ffButton('🗑 Discard #' + (i + 1),
        () => ffMove('discard', {cards: [i]})));
    });
  }
}
document.getElementById('ffJoin').addEventListener('click', () => ffMove('join'));
document.getElementById('ffNpc').addEventListener('click', () => ffMove('join_npc'));
document.getElementById('ffStart').addEventListener('click', () => ffMove('start'));
document.getElementById('ffRematch').addEventListener('click', () => ffMove('rematch'));
ffLoad();
