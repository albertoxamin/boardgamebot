const FF = {chat_id: null, init: '', board: null, timer: null, me: 0};
const FF_HOW_TO_PLAY_URL = 'https://www.youtube.com/watch?v=ezMd-IwlTyA';

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
  FF.me = tg.id;
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
// FB-0123: like Rumble Nation, make the current player unmissable: a big
// banner above the header plus an amber highlight + badge on the current
// player's box. can_act is also true while the NPC acts (anyone may play
// for it), so "your move" must mean the actor is the viewer, not can_act.
// flip7.html is shared, so this CSS is injected by fadenfroh.js itself.
function ffTurnStyle() {
  if (document.getElementById('ffTurnStyle')) return;
  const s = document.createElement('style');
  s.id = 'ffTurnStyle';
  s.textContent = '.ffturnbanner{display:flex;align-items:center;justify-content:center;' +
    'gap:6px;background:#1e293b;border:2px solid #f59e0b;border-radius:10px;' +
    'padding:8px 12px;margin:6px 0;font-size:18px;font-weight:900;text-align:center;' +
    'box-shadow:0 0 0 2px #f59e0b33,0 2px 10px #0008}' +
    '.ffturnbanner .ffturnname{font-size:20px}' +
    '.ffplayer.ffturn{border:2px solid #f59e0b;' +
    'box-shadow:0 0 0 2px #f59e0b55,0 0 12px #f59e0b66;background:#1e293b}' +
    '.ffturnbadge{display:inline-block;background:#f59e0b;color:#111;' +
    'border-radius:999px;padding:1px 8px;font-size:11px;font-weight:900}';
  if (document.head) document.head.appendChild(s);
}
function ffIsMyTurn(g) {
  return g.actor !== null && g.actor !== undefined &&
    !!g.players[g.actor] && g.players[g.actor].user_id === FF.me;
}
function ffTurnBanner(g) {
  if (g.actor === null || g.actor === undefined) return '';
  const p = g.players[g.actor];
  if (!p) return '';
  const mine = p.user_id === FF.me;
  return '<div class="ffturnbanner">👉 <span class="ffturnname">' + escapeHtml(p.name) +
    '</span>' + (mine ? ' — your move' : '') + '</div>';
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
// Starting-card sheet (fadenfroh-starting.webp): 4 columns (starting
// numbers 1-4) x 3 rows (white, yellow, purple); each card is two 44px
// halves. Column comes from the player's starting number, row from the
// half's colour, so live games dealt before this fix render right too.
const FF_START_ROW = {white: 0, yellow: 1, purple: 2};
function ffStartStyle(h) {
  const col = Math.max(0, Math.min(3, ((h.start_no || 1) - 1)));
  const row = FF_START_ROW[h.c] || 0;
  return 'background-position:' + (-(col * 88 + (h.h || 0) * 44)) + 'px ' + (-(row * 63)) + 'px';
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
      style = ffStartStyle(h); label = 'starting card';
    } else {
      style = ffHalfStyle(h.id, h.h); label = ffCardTitle(h.id);
    }
    return '<span class="' + cls + '" style="left:' + ((h.col - min) * 46) + 'px;' + style +
      '" title="' + escapeHtml(label + ' @ column ' + h.col) + '"></span>';
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
  ffTurnStyle();
  const turn = document.getElementById('ffTurn');
  const goals = document.getElementById('ffGoals');
  const market = document.getElementById('ffMarket');
  const players = document.getElementById('ffPlayers');
  const actions = document.getElementById('ffActions');
  const join = document.getElementById('ffJoin');
  const npc = document.getElementById('ffNpc');
  const start = document.getElementById('ffStart');
  const howto = document.getElementById('ffHowTo');
  const rematch = document.getElementById('ffRematch');
  [join, npc, start, howto, rematch].forEach(el => el.classList.add('hidden'));
  actions.innerHTML = '';
  document.getElementById('ffLog').textContent = (g.log || []).join('\n');
  const names = g.players.map((p, i) => escapeHtml(p.name) + ' <b>' + p.score + '</b> VP' +
    (p.npc ? ' 🤖' : '')).join(' · ');
  const actorP = (g.actor !== null && g.actor !== undefined) ? g.players[g.actor] : null;
  const myTurn = ffIsMyTurn(g);
  const npcTurn = !!(actorP && actorP.npc);
  const turnSuffix = myTurn ? ' · <b>your move</b>' : npcTurn ? ' · <b>NPC\'s turn</b>' :
    actorP ? ' · <b>' + escapeHtml(actorP.name) + '\'s turn</b>' : '';
  turn.innerHTML = ffTurnBanner(g) + (g.phase === 'lobby' ? '🪡 Fadenfroh lobby — ' + g.players.length + '/4 · ' + names :
    g.phase === 'game_end' ? '🏆 ' + escapeHtml((g.players[g.winner] || {}).name || 'Winner') +
      ' wins! · ' + names :
    '🪡 Round ' + g.round + '/5 · ' + g.phase + ' · ' + names + turnSuffix);
  goals.innerHTML = '🎯 ' + ['A', 'B', 'C', 'D'].map(k =>
    '<span class="ffgoal" title="Goal ' + k + ': ' + g.goals[k] + '">' + k +
    '<span class="ffscore" style="' + ffScoreStyle(g.goals[k]) + '"></span></span>').join('');
  const m = g.market;
  market.innerHTML = g.phase === 'lobby' ? '' : '🛒 Market: 🧵' + m.threads + ' 🪡' + m.needles +
    (m.thimble ? ' 🟘' : '') + ' · ' + (m.offers || []).map((o, i) =>
      '<span title="Offer ' + (i + 1) + '">' + o.map(ffCardHtml).join('') + '</span>').join(' ');
  players.innerHTML = g.phase === 'lobby' ? '' : g.players.map((p, i) => {
    const active = i === g.actor;
    const badge = active ? ' <span class="ffturnbadge">👉 ' +
      (p.user_id === FF.me ? 'your turn' : 'turn') + '</span>' : '';
    return '<div class="ffplayer' + (active ? ' ffturn' : '') + '"><b>' + escapeHtml(p.name) +
      '</b> · ' + p.score + ' VP · 🧵' + p.threads + ' 🪡' + p.needles +
      (p.thimble ? ' 🟘' : '') + ' · hand ' + p.supply_count + badge +
      '<div>' + p.rows.map(ffRowHtml).join('') + '</div></div>';
  }).join('');
  if (g.phase === 'lobby') {
    if (g.is_player) join.classList.remove('hidden');
    start.classList.remove('hidden');
    howto.classList.remove('hidden');
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
document.getElementById('ffHowTo').addEventListener('click', () => {
  try {
    if (window.Telegram && Telegram.WebApp && Telegram.WebApp.openLink)
      Telegram.WebApp.openLink(FF_HOW_TO_PLAY_URL);
    else window.open(FF_HOW_TO_PLAY_URL, '_blank');
  } catch (e) { window.open(FF_HOW_TO_PLAY_URL, '_blank'); }
});
document.getElementById('ffRematch').addEventListener('click', () => ffMove('rematch'));
ffLoad();
