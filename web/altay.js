const ATG = {user_id: 0, chat_id: null, board: null, timer: null, init: '', mode: null};

function atLog(s) {
  const e = document.getElementById('atLog');
  if (e) e.textContent += s + '\n';
}
function atApi(path, opts) { return fetch(path, opts).then(r => r.json()); }
function atChatId(raw) {
  let s = String(raw || '');
  if (s.startsWith('altay')) s = s.slice(5);
  const n = parseInt(s, 10);
  return isNaN(n) ? 0 : n;
}
async function atLoad() {
  const tg = tgInit();
  if (!tg.id) {
    document.getElementById('atTurn').textContent = 'Open as Telegram Mini App via the bot link.';
    return;
  }
  ATG.user_id = tg.id;
  ATG.init = tg.init;
  const qp = new URLSearchParams(location.search);
  const pref = atChatId(tg.start) || atChatId(qp.get('app')) ||
               parseInt(qp.get('chat_id'), 10) || atChatId(tg.chat_instance);
  const r = await atApi('/api/altay/mygames?init_data=' + encodeURIComponent(tg.init));
  const mine = r.games || [];
  const pick = mine.find(g => g.chat_id === pref) || mine.find(g => g.phase !== 'over') || mine[0];
  if (pick) atSelect(pick.chat_id);
  else if (pref) {
    const cr = await atApi('/api/altay/create', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({init_data: tg.init, chat_id: pref})
    });
    if (cr.game) atSelect(cr.game.chat_id);
    else atLog('⛔ ' + (cr.error || 'create failed'));
  } else {
    document.getElementById('atTurn').textContent = 'No Altay game yet — send /altay in a chat.';
  }
}
async function atSelect(chat_id) {
  ATG.chat_id = chat_id;
  await atRefresh();
  if (ATG.timer) clearInterval(ATG.timer);
  ATG.timer = setInterval(atRefresh, 3000);
}
async function atRefresh() {
  if (!ATG.chat_id) return;
  const q = '?chat_id=' + encodeURIComponent(ATG.chat_id) + '&init_data=' + encodeURIComponent(ATG.init);
  const r = await atApi('/api/altay/game' + q);
  if (r.game) { ATG.board = r.game; atRender(); }
}
async function atMove(action, extra) {
  const body = Object.assign({chat_id: ATG.chat_id, action: action, init_data: ATG.init}, extra || {});
  const r = await atApi('/api/altay/move', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  if (r.events) r.events.forEach(e => atLog(e));
  if (r.error) atLog('⛔ ' + r.error);
  if (r.game) { ATG.board = r.game; ATG.mode = null; atRender(); }
}
function atFactionStyle(faction) {
  const order = ['EARTHFOLK', 'ELVENFOLK', 'FIREFOLK', 'SMALLFOLK'];
  const idx = Math.max(0, order.indexOf(faction));
  return 'background-position:' + (idx * 20) + '% 0';
}
function atResources(p) {
  const icons = ATG.board.resource_icons || {};
  return Object.entries(p.resources || {}).filter(([, n]) => n)
    .map(([k, n]) => (icons[k] || '') + ' ' + n).join('  ');
}
function atCard(card, clickable, attrs) {
  const x = Number((card.sprite || [0, 0])[0]) * 100 / 9;
  const y = Number((card.sprite || [0, 0])[1]) * 100 / 14;
  const cls = 'atcard' + (clickable ? ' atclick' : '');
  const extra = attrs || '';
  return '<div class="' + cls + '" style="background-position:' + x + '% ' + y +
    '%" title="' + escapeHtml(card.name + ' — ' + (card.text || '')) + '" ' + extra + '></div>';
}
function atAch(ach, index) {
  const x = Number((ach.sprite || [0, 0])[0]) * 10;
  const y = Number((ach.sprite || [0, 0])[1]) * 50;
  const done = ach.done[index];
  const active = ach.active[index];
  const clickable = ATG.board.can_act && !done && (!ach.active[0] || active);
  const cls = 'atach' + (done ? ' atdone' : '') + (active ? ' atactive' : '') + (clickable ? ' atclick' : '');
  const cost = Object.entries(ach.cost).map(([k, n]) => (ATG.board.resource_icons[k] || k) + n).join(' ');
  return '<div class="' + cls + '" style="background-position:' + x + '% ' + y +
    '%" title="' + escapeHtml(ach.name + ' (' + cost + ', ' + ach.vp + ' VP) — ' + ach.text) +
    '" data-ach="' + escapeHtml(ach.id) + '"></div>';
}
function atRegion(region, g) {
  const builds = (g.legal.build || []).map(String).includes(String(region.id));
  const attacks = (g.legal.attack || []).some(o => String(o.region) === String(region.id));
  const canBuild = g.can_act && ATG.mode === 'build' && builds;
  const canAttack = g.can_act && ATG.mode === 'attack' && attacks;
  const cls = 'atregion' + (canBuild ? ' atbuild' : '') + (canAttack ? ' atattack' : '');
  let html = '<div class="' + cls + '" style="top:' + region.pos[1] + '%;left:' + region.pos[0] +
    '%" data-region="' + region.id + '" title="' + escapeHtml(region.name + ' — ' + region.type) + '">';
  if (region.marker) {
    const col = Math.min(5, Math.max(0, region.marker.value - 1));
    html += '<span class="atmarkerchip" style="background-position:' + (col * 100 / 6) +
      '% 0">' + region.marker.value + '</span>';
  }
  if (region.vp) html += '<span class="atvp" style="top:-9px;left:70%">★' + region.vp + '</span>';
  if (region.settlements.length) {
    html += '<span class="atsettles">' + region.settlements.map(s =>
      '<span class="atsettle" style="background:' + s.color + '"></span>').join('') + '</span>';
  }
  return html + '</div>';
}
function atRender() {
  const g = ATG.board;
  if (!g) return;
  const turn = document.getElementById('atTurn');
  const players = document.getElementById('atPlayers');
  const board = document.getElementById('atBoard');
  const hand = document.getElementById('atHand');
  const actions = document.getElementById('atActions');
  const market = document.getElementById('atMarket');
  const achievements = document.getElementById('atAch');
  const join = document.getElementById('atJoin');
  const npc = document.getElementById('atNpc');
  const start = document.getElementById('atStart');
  const rematch = document.getElementById('atRematch');
  [join, npc, start, rematch].forEach(el => el.classList.add('hidden'));
  [board, hand, actions, market, achievements].forEach(el => { el.innerHTML = ''; });
  document.getElementById('atLog').textContent = (g.log || []).join('\n');
  const names = g.players.map(p => escapeHtml(p.name) + (p.npc ? ' 🤖' : '') +
    ' <b style="color:' + p.color + '">' + p.score + ' VP</b>').join(' · ');
  turn.innerHTML = g.phase === 'lobby' ? '🏜️ Altay lobby — ' + g.players.length + '/2 · ' + names :
    g.phase === 'over' ? '🏆 ' + (g.winner === null ? 'Draw' :
      escapeHtml((g.players[g.winner] || {}).name || 'Winner')) + ' wins! · ' + names :
    '🏜️ Turn ' + (g.turn + 1) + ' · ' + names + (g.can_act ? ' · <b>your move</b>' : '');
  players.innerHTML = g.players.map((p, i) => '<div class="atplayer' +
    (i === g.current && g.phase !== 'lobby' ? ' atcurrent' : '') + '">' +
    '<span class="atfaction" style="' + atFactionStyle(p.faction) + '"></span>' +
    '<b>' + escapeHtml(p.name) + '</b> · ' + escapeHtml(p.faction_name) + ' · ' + p.score + ' VP<br>' +
    '<span class="atres">' + atResources(p) + '</span> · 🃏 ' + p.hand_count +
    ' · 🏠 ' + p.reserve + ' · ⚔️ ' + p.captured + ' · 🎯 ' + p.markers + '<br>' +
    '📜 ' + escapeHtml(p.achievement || 'no active achievement') + '</div>').join('');
  if (g.phase === 'lobby') {
    board.innerHTML = '<div class="atlobby">Join or add an NPC, then start.<br>' +
      'The board and your cards appear once the game starts.<br>' + names + '</div>';
    if (!g.is_player) join.classList.remove('hidden');
    if (g.players.length < (g.max_players || 2)) npc.classList.remove('hidden');
    start.classList.remove('hidden');
    return;
  }
  if (g.phase === 'over') rematch.classList.remove('hidden');
  board.innerHTML = '<div class="atboard">' + g.regions.map(r => atRegion(r, g)).join('') + '</div>';
  board.querySelectorAll('[data-region]').forEach(el => el.addEventListener('click', () => {
    const region = Number(el.dataset.region);
    if (ATG.mode === 'build' && (g.legal.build || []).map(String).includes(String(region))) {
      atMove('build', {region: region});
    } else if (ATG.mode === 'attack' && (g.legal.attack || []).some(o => o.region === region)) {
      atMove('attack', {region: region});
    }
  }));
  const me = g.players[g.me] || {hand: []};
  hand.innerHTML = '<div class="atlabel">Your hand</div>' + (me.hand.length
    ? me.hand.map((c, i) => atCard(c, g.can_act, 'data-hand="' + i + '"')).join('')
    : '<span class="atcardback"></span>'.repeat(Math.max(1, me.hand_count)));
  hand.querySelectorAll('[data-hand]').forEach(el => el.addEventListener('click', () => {
    atMove('play', {index: Number(el.dataset.hand)});
  }));
  const mkBtn = (label, mode) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'atbtn';
    b.textContent = label;
    b.disabled = !g.can_act;
    b.addEventListener('click', () => { ATG.mode = ATG.mode === mode ? null : mode; atRender(); });
    return b;
  };
  actions.appendChild(mkBtn('🏠 Build', 'build'));
  actions.appendChild(mkBtn('⚔️ Attack', 'attack'));
  const end = document.createElement('button');
  end.type = 'button';
  end.className = 'atbtn';
  end.textContent = '✅ End turn';
  end.disabled = !g.can_act;
  end.addEventListener('click', () => atMove('end'));
  actions.appendChild(end);
  market.innerHTML = '<div class="atlabel">Market — buy once per turn</div>' + (g.market || []).map(c => {
    const affordable = Object.entries(c.cost || {}).every(([k, n]) => (me.resources[k] || 0) >= n);
    const bought = (me.bought || []).includes(c.id);
    const clickable = g.can_act && affordable && !bought;
    return atCard(c, clickable, 'data-buy="' + escapeHtml(c.id) + '"');
  }).join('');
  market.querySelectorAll('[data-buy]').forEach(el => el.addEventListener('click', () => {
    if (!g.can_act) return;
    atMove('buy', {card: el.dataset.buy});
  }));
  achievements.innerHTML = '<div class="atlabel">Achievements — click to invest one resource</div>' +
    (g.achievements || []).map(a => atAch(a, g.me === null ? 0 : g.me)).join('');
  achievements.querySelectorAll('[data-ach]').forEach(el => el.addEventListener('click', () => {
    if (!g.can_act) return;
    atMove('develop', {achievement: el.dataset.ach});
  }));
}
document.getElementById('atJoin').addEventListener('click', () => atMove('join'));
document.getElementById('atNpc').addEventListener('click', () => atMove('npc'));
document.getElementById('atStart').addEventListener('click', () => atMove('start'));
document.getElementById('atRematch').addEventListener('click', () => atMove('rematch'));
atLoad();
