const BFG = {user_id: 0, chat_id: null, board: null, timer: null, init: '', mode: null};

function bfLog(s) {
  const el = document.getElementById('bfLog');
  if (el) el.textContent += s + '\n';
}
function bfApi(path, opts) { return fetch(path, opts).then(r => r.json()); }
function bfChatId(raw) {
  let s = String(raw || '');
  if (s.startsWith('blackflag')) s = s.slice(9);
  const n = parseInt(s, 10);
  return isNaN(n) ? 0 : n;
}
async function bfLoad() {
  if (document.getElementById('blackflag').classList.contains('hidden')) return;
  const tg = tgInit();
  if (!tg.id) {
    document.getElementById('bfTurn').textContent = 'Open as Telegram Mini App via the bot link.';
    return;
  }
  BFG.user_id = tg.id;
  BFG.init = tg.init;
  const qp = new URLSearchParams(location.search);
  const pref = bfChatId(tg.start) || bfChatId(qp.get('app')) ||
    parseInt(qp.get('chat_id'), 10) || bfChatId(tg.chat_instance);
  const r = await bfApi('/api/blackflag/mygames?init_data=' + encodeURIComponent(tg.init));
  const mine = r.games || [];
  const pick = mine.find(g => g.chat_id === pref) || mine.find(g => g.phase !== 'game_end') || mine[0];
  if (pick) bfSelect(pick.chat_id);
  else if (pref) {
    const cr = await bfApi('/api/blackflag/create', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({init_data: tg.init, chat_id: pref})
    });
    if (cr.game) bfSelect(cr.game.chat_id);
    else bfLog('⛔ ' + (cr.error || 'create failed'));
  } else {
    document.getElementById('bfTurn').textContent = 'No Black Flag game yet — send /blackflag in a chat.';
  }
}
async function bfSelect(chatId) {
  BFG.chat_id = chatId;
  await bfRefresh();
  if (BFG.timer) clearInterval(BFG.timer);
  BFG.timer = setInterval(bfRefresh, 3000);
}
async function bfRefresh() {
  if (!BFG.chat_id) return;
  const q = '?chat_id=' + encodeURIComponent(BFG.chat_id) + '&init_data=' + encodeURIComponent(BFG.init);
  const r = await bfApi('/api/blackflag/game' + q);
  if (r.game) { BFG.board = r.game; bfRender(); }
}
async function bfMove(action, extra) {
  const body = Object.assign({chat_id: BFG.chat_id, action: action, init_data: BFG.init}, extra || {});
  const r = await bfApi('/api/blackflag/move', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  if (r.events) r.events.forEach(e => bfLog(e));
  if (r.error) bfLog('⛔ ' + r.error);
  if (r.game) { BFG.board = r.game; BFG.mode = null; bfRender(); }
}
function bfCard(card, clickable, attrs) {
  const sprite = card.sprite || [9, 9];
  const cls = 'bfcard' + (clickable ? ' bfclick' : '');
  return '<div class="' + cls + '" style="background-position:' + (sprite[0] * 100 / 5) + '% ' +
    (sprite[1] * 100 / 8) + '%" title="' + escapeHtml(card.name + ' — ' + (card.text || '')) + '" ' +
    (attrs || '') + '></div>';
}
function bfShip(ship, clickable, attrs) {
  const sprite = ship.sprite || [9, 9];
  const cls = 'bfship' + (clickable ? ' bfclick' : '');
  return '<div class="' + cls + '" style="background-position:' + (sprite[0] * 100 / 4) + '% ' +
    (sprite[1] * 100 / 4) + '%" title="' + escapeHtml(ship.name + ' Range ' + ship.range +
      ' · Cannons ' + ship.ammo + ' · Barrels ' + ship.barrels) + '" ' + (attrs || '') + '></div>';
}
function bfRender() {
  const g = BFG.board;
  if (!g) return;
  const turn = document.getElementById('bfTurn');
  const players = document.getElementById('bfPlayers');
  const board = document.getElementById('bfBoard');
  const hand = document.getElementById('bfHand');
  const actions = document.getElementById('bfActions');
  const join = document.getElementById('bfJoin');
  const npc = document.getElementById('bfNpc');
  const start = document.getElementById('bfStart');
  const rematch = document.getElementById('bfRematch');
  [join, npc, start, rematch].forEach(el => el.classList.add('hidden'));
  [board, hand, actions, players].forEach(el => { el.innerHTML = ''; });
  document.getElementById('bfLog').textContent = (g.log || []).join('\n');
  const names = g.players.map(p => escapeHtml(p.name) + (p.npc ? ' 🤖' : '') +
    ' <span class="bfpill">' + p.barrels + '/' + p.max_barrels + '</span>').join(' · ');
  turn.innerHTML = g.phase === 'lobby' ? '🏴‍☠️ Black Flag lobby — ' + g.players.length + '/8 · ' + names :
    g.phase === 'game_end' ? '🏆 ' + escapeHtml((g.winner_names || []).join(', ') || 'Draw') + ' · ' + names :
    '🏴‍☠️ Turn ' + (g.turn + 1) + ' · Chest ' + g.chest + ' · Flags ±' + g.flags +
    ' · Hourglass ' + g.hourglass + ' · ' + names + (g.can_act ? ' · <b>your move</b>' : '');
  players.innerHTML = g.players.map((p, i) => '<div class="bfplayer' +
    (i === g.actor && g.phase !== 'lobby' ? ' bfcurrent' : '') + '">' +
    '<b>' + escapeHtml(p.name) + '</b>' + (p.npc ? ' 🤖' : '') +
    '<span class="bfrole">' + escapeHtml((p.role && p.role.name) || 'Hidden') + '</span><br>' +
    escapeHtml((p.captain && p.captain.name) || '?') + ' / ' +
    escapeHtml((p.ship && p.ship.name) || 'adrift') + '<br>' +
    '🛡 ' + p.barrels + '/' + p.max_barrels + ' · 💰 ' + p.doubloons + ' · 🃏 ' + p.hand_count +
    ' · ⚙️ ' + p.equipment.map(c => escapeHtml(c.name)).join(', ') + '</div>').join('');
  if (g.phase === 'lobby') {
    board.innerHTML = '<div class="bflobby">Join or add an NPC, then start. ' + names + '</div>';
    if (!g.is_player) join.classList.remove('hidden');
    if (!g.players.some(p => p.npc)) npc.classList.remove('hidden');
    start.classList.remove('hidden');
    return;
  }
  if (g.phase === 'game_end') {
    board.innerHTML = '<div class="bflobby">🏁 ' + escapeHtml(g.end_reason || 'Game over') + '<br>' +
      'Winner: ' + escapeHtml((g.winner_names || []).join(', ') || 'nobody') + '</div>';
    rematch.classList.remove('hidden');
    return;
  }
  const legal = g.legal || {};
  let html = '<div class="bfrow"><span class="bfpill">🚢 Ship row</span>';
  if (!g.players[legal.actor].ship) {
    html += (g.ship_row || []).map((s, i) => bfShip(s, g.can_act, 'data-ship="' + i + '"')).join('') +
      (legal.ships && legal.ships.includes('deck') ? '<button class="atbtn" data-ship="deck">Blind deck</button>' : '');
  } else {
    html += (g.ship_row || []).map(s => bfShip(s, false)).join('');
  }
  html += '<span class="bfpill">🃏 Deck ' + g.deck_count + '</span>';
  html += '<span class="bfpill">🚢 Fleet ' + g.ship_deck_count + '</span></div>';
  if (g.pending) {
    const target = g.players[g.pending.target];
    html += '<div class="bfpending">⚔️ ' + escapeHtml(g.players[g.pending.attacker].name) + ' → ' +
      escapeHtml(target.name) + ' · ' + (g.pending.kind === 'boarding' ? 'Boarding' : 'Shot') + '</div>';
  }
  board.innerHTML = html;
  board.querySelectorAll('[data-ship]').forEach(el => el.addEventListener('click', () => {
    if (!g.can_act) return;
    bfMove('ship', {choice: el.dataset.ship});
  }));
  const me = g.players[g.me] || g.players[legal.actor];
  const handCards = g.players[legal.actor].hand;
  const visible = (g.me === legal.actor || g.players[legal.actor].npc) ? handCards : (me.hand || []);
  if (!g.players[legal.actor].ship) {
    hand.innerHTML = '<div class="bflabel">Choose a Ship first</div><div class="bfcardback"></div>';
  } else if (visible.length) {
    const targets = legal.defend || [];
    hand.innerHTML = '<div class="bflabel">' + (g.pending ? 'Choose a defense' : 'Your hand') + '</div>' +
      visible.map((c, i) => bfCard(c, g.can_act && (!g.pending || targets.includes(i)),
        g.pending ? 'data-defend="' + i + '"' : 'data-hand="' + i + '"')).join('');
  } else {
    hand.innerHTML = '<div class="bflabel">Hidden hand</div>' +
      '<div class="bfcardback"></div>'.repeat(Math.max(1, g.players[legal.actor].hand_count));
  }
  hand.querySelectorAll('[data-hand]').forEach(el => el.addEventListener('click', () => {
    if (!g.can_act) return;
    const index = Number(el.dataset.hand);
    if ((g.target_cards || []).includes(handCards[index].id)) {
      BFG.mode = index;
      bfRender();
    } else {
      bfMove('play', {index: index});
    }
  }));
  hand.querySelectorAll('[data-defend]').forEach(el => el.addEventListener('click', () => {
    bfMove('defend', {index: Number(el.dataset.defend)});
  }));
  const mk = (label, fn, disabled) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'atbtn';
    b.textContent = label;
    b.disabled = !!disabled;
    b.addEventListener('click', fn);
    return b;
  };
  if (BFG.mode !== null && legal.targets) {
    actions.appendChild(mk('🎯 Choose target', () => {}, true));
    legal.targets.forEach(target => actions.appendChild(mk(g.players[target].name,
      () => bfMove('play', {index: BFG.mode, target: target}), !g.can_act)));
    actions.appendChild(mk('↩️ Back', () => { BFG.mode = null; bfRender(); }));
  } else {
    if (legal.pass) actions.appendChild(mk('⏭ Pass', () => bfMove('pass'), !g.can_act));
    if (legal.ability) actions.appendChild(mk('🔥 Extra Shot', () => bfMove('ability'), !g.can_act));
    if (legal.end) actions.appendChild(mk('✅ End turn', () => bfMove('end'), !g.can_act));
  }
}
document.getElementById('bfJoin').addEventListener('click', () => bfMove('join'));
document.getElementById('bfNpc').addEventListener('click', () => bfMove('npc'));
document.getElementById('bfStart').addEventListener('click', () => bfMove('start'));
document.getElementById('bfRematch').addEventListener('click', () => bfMove('rematch'));
bfLoad();
