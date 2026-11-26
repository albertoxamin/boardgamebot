const RNG = {chat_id: null, init: '', board: null, timer: null, card: null};

const RN_HOW_TO_PLAY_URL = 'https://youtu.be/l89gewMT6uQ?si=W345viv6T7_pu5rg';

const RN_TACTIC_POS = {1: [737, 2], 2: [737, 280], 3: [942, 2], 4: [942, 280],
  5: [2, 722], 6: [412, 722], 7: [207, 722], 8: [617, 722], 9: [822, 722],
  10: [1147, 2], 11: [1147, 280], 12: [1147, 558]};
const RN_CASTLE_POS = {2: [2, 383], 3: [110, 383], 4: [218, 383], 5: [326, 383],
  6: [494, 2], 7: [218, 489], 8: [494, 320], 9: [110, 489], 10: [494, 108],
  11: [2, 489], 12: [494, 214]};
const RN_SOLDIER_POS = [399, 489, 387, 289, 387, 200, 472, 489];
// Player colours, in seat order: red, blue, orange, white. Each pair is the
// top-left of the small soldier meeple in rumblenation-tokens.webp (104px
// cells), measured off the sheet: red (399,489), blue (387,289),
// orange (387,200), white (472,489). FB-0066: the old array had only
// red/blue and the first entry (472,489) was actually the white meeple,
// so player 0's icon was white.
const RN_COLORS = ['red', 'blue', 'orange', 'white'];
const RN_DIE_POS = {1: [1, 1], 2: [78, 1], 3: [1, 78], 4: [78, 78], 5: [155, 1], 6: [155, 78]};

function rnLog(s) { const e = document.getElementById('rnLog'); if (e) e.textContent += s + '\n'; }
function rnApi(path, opts) { return fetch(path, opts).then(r => r.json()); }
function rnChatId(raw) {
  let s = String(raw || '');
  if (s.startsWith('rumblenation')) s = s.slice(12);
  const n = parseInt(s, 10);
  return isNaN(n) ? 0 : n;
}
async function rnLoad() {
  const tg = tgInit();
  if (!tg.id) {
    document.getElementById('rnTurn').textContent = 'Open as Telegram Mini App via the bot link.';
    return;
  }
  RNG.init = tg.init;
  const qp = new URLSearchParams(location.search);
  const pref = rnChatId(tg.start) || rnChatId(qp.get('app')) ||
               parseInt(qp.get('chat_id'), 10) || rnChatId(tg.chat_instance);
  const r = await rnApi('/api/rumblenation/mygames?init_data=' + encodeURIComponent(tg.init));
  const mine = r.games || [];
  const pick = mine.find(g => g.chat_id === pref) || mine.find(g => g.phase !== 'game_end') || mine[0];
  if (pick) rnSelect(pick.chat_id);
  else if (pref) {
    const cr = await rnApi('/api/rumblenation/create', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({init_data: tg.init, chat_id: pref})
    });
    if (cr.game) rnSelect(cr.game.chat_id);
    else rnLog('⛔ ' + (cr.error || 'create failed'));
  } else {
    document.getElementById('rnTurn').textContent = 'No Rumble Nation game yet — send /rumblenation in a chat.';
  }
}
async function rnSelect(chat_id) {
  RNG.chat_id = chat_id;
  await rnRefresh();
  if (RNG.timer) clearInterval(RNG.timer);
  RNG.timer = setInterval(rnRefresh, 3000);
}
async function rnRefresh() {
  if (!RNG.chat_id) return;
  const q = '?chat_id=' + encodeURIComponent(RNG.chat_id) + '&init_data=' + encodeURIComponent(RNG.init);
  const r = await rnApi('/api/rumblenation/game' + q);
  if (r.game) { RNG.board = r.game; rnRender(); }
}
async function rnMove(action, extra) {
  const body = Object.assign({chat_id: RNG.chat_id, action: action, init_data: RNG.init}, extra || {});
  const r = await rnApi('/api/rumblenation/move', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  if (r.events) r.events.forEach(e => rnLog(e));
  if (r.error) rnLog('⛔ ' + r.error);
  if (r.game) { RNG.board = r.game; RNG.card = null; rnRender(); }
}
function rnSprite(sheet, pos, w, h, sheetW, sheetH) {
  return 'width:' + w + 'px;height:' + h + 'px;background-image:url(rumblenation-' +
    (sheet === 'card' ? 'cards' : sheet === 'token' ? 'tokens' : 'dice') +
    '.webp);background-size:' + Math.round(sheetW * (w / (sheet === 'card' ? 201 : sheet === 'token' ? 104 : 75))) +
    'px ' + Math.round(sheetH * (w / (sheet === 'card' ? 201 : sheet === 'token' ? 104 : 75))) +
    'px;background-position:' + (-pos[0] * (w / (sheet === 'card' ? 201 : sheet === 'token' ? 104 : 75))) +
    'px ' + (-pos[1] * (w / (sheet === 'card' ? 201 : sheet === 'token' ? 104 : 75))) + 'px';
}
function rnCard(c) {
  const pos = RN_TACTIC_POS[c.id] || [2, 722];
  return '<div class="rncardwrap"><button type="button" class="rncard btn' +
    (c.used_by !== null ? ' rnused' : '') + (RNG.card === c.id ? ' rnselected' : '') +
    '" data-card="' + c.id + '" style="' + rnSprite('card', pos, 64, 87, 1350, 998) +
    '" title="' + escapeHtml(c.name + ': ' + c.text) + '"></button>' +
    '<div class="rncardcap"><b>' + escapeHtml(c.name) + '</b><br>' +
    escapeHtml(c.text) + '</div></div>';
}
function rnReserve(g) {
  return '<div class="rnreserves">' + g.players.map((p, i) => {
    const pos = [RN_SOLDIER_POS[i * 2], RN_SOLDIER_POS[i * 2 + 1]];
    return '<span class="rnreserve"><span class="rnmeeple" style="' +
      rnSprite('token', pos, 22, 22, 687, 593) + '"></span> <span class="rn' +
      RN_COLORS[i] + '">' + escapeHtml(p.name) + '</span>: <b>' + p.stock +
      '</b> soldier' + (p.stock === 1 ? '' : 's') + ' in reserve</span>';
  }).join('') + '</div>';
}
function rnRegion(r, g) {
  const castle = r.castle;
  const tok = castle && RN_CASTLE_POS[castle]
    ? '<span class="rncastle" style="' + rnSprite('token', RN_CASTLE_POS[castle], 44, 43, 687, 593) + '"></span>'
    : '<span class="rncastle rnempty"></span>';
  let troops = '';
  for (let p = 0; p < g.players.length; p++) {
    const n = r.troops[p] + r.reinforce[p];
    if (!n) continue;
    const pos = [RN_SOLDIER_POS[p * 2], RN_SOLDIER_POS[p * 2 + 1]];
    troops += '<span class="rnmeeples" title="' + escapeHtml(g.players[p].name + ': ' + n) + '">' +
      '<span class="rnmeeple" style="' + rnSprite('token', pos, 22, 22, 687, 593) + '"></span>' +
      '<b class="rncount rn' + RN_COLORS[p] + '">' + n + '</b></span>';
  }
  return '<div class="rnregion" style="left:' + r.x + '%;top:' + r.y + '%" title="' +
    escapeHtml(r.name + ' (' + r.title + ') · castle ' + (castle || '—')) + '">' +
    tok + '<span class="rntroops">' + troops + '</span></div>';
}
function rnRender() {
  const g = RNG.board;
  if (!g) return;
  const turn = document.getElementById('rnTurn');
  const board = document.getElementById('rnBoard');
  const actions = document.getElementById('rnActions');
  const join = document.getElementById('rnJoin');
  const start = document.getElementById('rnStart');
  const howto = document.getElementById('rnHowTo');
  const rematch = document.getElementById('rnRematch');
  const roll = document.getElementById('rnRoll');
  const reroll = document.getElementById('rnReroll');
  [join, start, howto, rematch, roll, reroll].forEach(el => el.classList.add('hidden'));
  actions.innerHTML = '';
  document.getElementById('rnLog').textContent = (g.log || []).join('\n');
  const names = g.players.map((p, i) => '<span class="rn' + RN_COLORS[i] + '">' +
    escapeHtml(p.name) + '</span> ' + p.score + ' pts · ' + p.stock + ' left · ⚔️' + p.sword).join(' vs ');
  turn.innerHTML = g.phase === 'lobby' ? '⚔️ Rumble Nation lobby — ' + g.players.length + '/4 · ' + names :
    g.phase === 'game_end' ? '🏆 ' + (g.winner === null ? 'Draw' :
      escapeHtml((g.players[g.winner] || {}).name || 'Winner')) + ' wins! · ' + names :
    '⚔️ Turn ' + g.turn + ' · ' + names + (g.can_act ? ' · <b>your move</b>' : '');
  if (g.phase === 'lobby') {
    board.innerHTML = '<div class="rnlobby">Join, then anyone taps Start.</div>';
    if (!g.is_player) join.classList.remove('hidden');
    start.classList.remove('hidden');
    howto.classList.remove('hidden');
    return;
  }
  if (g.phase === 'game_end') rematch.classList.remove('hidden');
  let html = '';
  if (g.phase === 'action' || g.phase === 'select') html += rnReserve(g);
  html += '<div class="rnboard">';
  Object.values(g.regions).forEach(r => { html += rnRegion(r, g); });
  html += '</div>';
  if (g.dice.length) {
    html += '<div class="rndice">' + g.dice.map(d => {
      return '<span style="' + rnSprite('dice', RN_DIE_POS[d], 42, 42, 385, 385) + '"></span>';
    }).join('') + '</div>';
  }
  html += '<div class="rncards">' + g.tactics.map(rnCard).join('') + '</div>';
  html += '<div class="rnlegend">🎲 The single die decides the soldiers: ' +
    '1–2 → 1 soldier · 3–4 → 2 soldiers · 5–6 → 3 soldiers</div>';
  board.innerHTML = html;
  board.querySelectorAll('[data-card]').forEach(el => el.addEventListener('click', () => {
    RNG.card = Number(el.dataset.card);
    rnRender();
  }));
  if (!g.can_act) return;
  if (g.phase === 'action') {
    roll.classList.remove('hidden');
    const cards = RNG.card === null ? [] : g.options.filter(o => o.card === RNG.card);
    if (RNG.card !== null && !cards.length) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'primary'; b.textContent = '↩️ Pick another card';
      b.addEventListener('click', () => { RNG.card = null; rnRender(); });
      actions.appendChild(b);
    }
    cards.forEach(o => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'primary'; b.textContent = o.label;
      b.addEventListener('click', () => rnMove('tactic', {value: o.value}));
      actions.appendChild(b);
    });
  } else if (g.phase === 'select') {
    if (g.rerolls) reroll.classList.remove('hidden');
    g.deploy.forEach(o => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'primary';
      b.textContent = '🪖 ' + o.soldiers + ' → castle ' + o.castle;
      b.addEventListener('click', () => rnMove('deploy', {die: o.die, castle: o.castle}));
      actions.appendChild(b);
    });
  }
}
document.getElementById('rnJoin').addEventListener('click', () => rnMove('join'));
document.getElementById('rnStart').addEventListener('click', () => rnMove('start'));
document.getElementById('rnHowTo').addEventListener('click', () => {
  try {
    if (window.Telegram && Telegram.WebApp && Telegram.WebApp.openLink)
      Telegram.WebApp.openLink(RN_HOW_TO_PLAY_URL);
    else window.open(RN_HOW_TO_PLAY_URL, '_blank');
  } catch (e) { window.open(RN_HOW_TO_PLAY_URL, '_blank'); }
});
document.getElementById('rnRematch').addEventListener('click', () => rnMove('rematch'));
document.getElementById('rnRoll').addEventListener('click', () => rnMove('roll'));
document.getElementById('rnReroll').addEventListener('click', () => rnMove('reroll'));
rnLoad();
