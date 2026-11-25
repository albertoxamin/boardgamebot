const ATG = {user_id: 0, chat_id: null, board: null, timer: null, init: '', mode: null, msgs: [], webVer: null, newVer: false, verAt: 0};

async function atCheckVer() {
  // FB-0026: the Mini App never reloads its own JS while open, and the
  // ?v= cache-buster on altay.js had not been bumped — so a fix could
  // be live on the server while the player still saw the old code with
  // no hint why. Compare the page's ?v= with the server's version
  // (from /healthz) and say so, instead of staying silent.
  if (!ATG.webVer || ATG.newVer) return;
  if (Date.now() - ATG.verAt < 60000) return;
  ATG.verAt = Date.now();
  try {
    const r = await fetch('/healthz').then(r => r.json());
    if (r.version && r.version !== ATG.webVer) {
      ATG.newVer = true;
      atLog('🔄 New version available — close and reopen the Mini App to see the latest fixes.');
    }
  } catch (e) {}
}

function atRenderLog() {
  const e = document.getElementById('ayLog');
  if (!e) return;
  const server = ((ATG.board && ATG.board.log) || []).join('\n');
  const mine = ATG.msgs.join('\n');
  e.textContent = server + (server && mine ? '\n' : '') + mine;
}
function atLog(s) {
  // FB-0022: client-side messages must survive the 3s refresh — atRender
  // used to overwrite ayLog with the server log, wiping every error
  // (e.g. "You cannot afford that card.") within seconds, so the four
  // action buttons looked dead. Keep them in ATG.msgs and re-render.
  ATG.msgs.push(s);
  if (ATG.msgs.length > 8) ATG.msgs.shift();
  atRenderLog();
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
    document.getElementById('ayTurn').textContent = 'Open as Telegram Mini App via the bot link.';
    return;
  }
  ATG.user_id = tg.id;
  ATG.init = tg.init;
  const qp = new URLSearchParams(location.search);
  ATG.webVer = parseInt(qp.get('v'), 10) || null;
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
    document.getElementById('ayTurn').textContent = 'No Altay game yet — send /altay in a chat.';
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
  atCheckVer();
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
  // FB-0023: altay-tokens.webp holds the 4 faction settlement icons in
  // FACTION_ORDER (295px each, 1180px wide) — a 4-column sheet, so
  // background-size is 400% and the positions are 0/33.3/66.7/100%.
  // The old 600% / 20% steps sliced icons in half (Elvenfolk showed
  // half a yellow city + half a green tree; Smallfolk showed the red
  // towers instead of the blue stones).
  const order = ['EARTHFOLK', 'ELVENFOLK', 'FIREFOLK', 'SMALLFOLK'];
  const idx = Math.max(0, order.indexOf(faction));
  return 'background-position:' + (idx * 100 / 3) + '% 0';
}
function atResources(p) {
  const icons = ATG.board.resource_icons || {};
  return Object.entries(p.resources || {}).filter(([, n]) => n)
    .map(([k, n]) => (icons[k] || '') + ' ' + n).join('  ');
}
function atCard(card, clickable, attrs) {
  const sea = !!(ATG.board && ATG.board.seafarers);
  // FB-0056: the Seafarers actions sheet is 11 cols x 19 rows, not
  // 10 x 18 — the old 1000%/1800% background sliced every card across
  // its neighbours, so several pictures showed in one card. The base
  // sheet stays 10 x 15.
  const x = Number((card.sprite || [0, 0])[0]) * 100 / (sea ? 10 : 9);
  const y = Number((card.sprite || [0, 0])[1]) * 100 / (sea ? 18 : 14);
  const cls = 'atcard' + (clickable ? ' atclick' : '');
  const extra = attrs || '';
  return '<div class="' + cls + '" style="background-position:' + x + '% ' + y +
    '%" title="' + escapeHtml(card.name + ' — ' + (card.text || '')) + '" ' + extra + '></div>';
}
// Card + a caption with its name and effect text: title tooltips never
// show on touch, so the effect must be readable on the card itself
// (FB-0013). `who` optionally prefixes the caption with the player.
function atCardCell(card, clickable, attrs, who) {
  const cap = (who ? escapeHtml(who) + ' · ' : '') + '<b>' + escapeHtml(card.name) +
    '</b><br>' + escapeHtml(card.text || '');
  // FB-0022: the tap target is the whole card incl. its caption — the
  // data-* attribute used to sit on the card image only, so tapping the
  // name/effect text under it did nothing.
  return '<div class="atcardwrap" ' + (attrs || '') + '>' + atCard(card, clickable) +
    '<div class="atcap">' + cap + '</div></div>';
}
function atAch(ach, index) {
  const sea = !!(ATG.board && ATG.board.seafarers);
  // FB-0056: the Seafarers achievements sheet is 12 cols x 3 rows —
  // the old 4-row divisor (400% background) sliced each achievement
  // across two rows. Both sheets have 3 rows, so the row divisor is 2.
  const x = Number((ach.sprite || [0, 0])[0]) * 100 / (sea ? 11 : 10);
  const y = Number((ach.sprite || [0, 0])[1]) * 100 / 2;
  const done = ach.done[index];
  const active = ach.active[index];
  const clickable = ATG.board.can_act && !done && (!ach.active[0] || active);
  const cls = 'atach' + (done ? ' atdone' : '') + (active ? ' atactive' : '') + (clickable ? ' atclick' : '');
  const cost = Object.entries(ach.cost).map(([k, n]) => (ATG.board.resource_icons[k] || k) + n).join(' ');
  // FB-0020: description under each achievement card — title tooltips
  // never show on touch, so name, cost, VP and effect must be readable
  // on the card itself (same pattern as atCardCell, FB-0013/FB-0016).
  const cap = '<b>' + escapeHtml(ach.name) + '</b><br>' +
    escapeHtml(cost + ' · ' + ach.vp + ' VP') + '<br>' + escapeHtml(ach.text);
  // FB-0022: data-ach on the whole tile incl. its caption, like the
  // market/hand cards — tapping the description text must work too.
  return '<div class="atachwrap" data-ach="' + escapeHtml(ach.id) + '"><div class="' + cls + '" style="background-position:' + x + '% ' + y +
    '%" title="' + escapeHtml(ach.name + ' (' + cost + ', ' + ach.vp + ' VP) — ' + ach.text) +
    '"></div>' +
    '<div class="atcap">' + cap + '</div></div>';
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
    // FB-0023: settlements are the faction's token icon from
    // altay-tokens.webp (via atFactionStyle), not a plain coloured
    // square — the icon is what identifies the settlement on the map.
    html += '<span class="atsettles">' + region.settlements.map(s =>
      '<span class="atsettle" style="' + atFactionStyle(s.faction) + '"></span>').join('') + '</span>';
  }
  return html + '</div>';
}
function atSeaBadges(g) {
  if (!g.seafarers) return '';
  const me = g.players[g.me] || {};
  return (g.sea_zones || []).map(zone => {
    const pos = (g.sea_anchors || {})[zone] || [50, 50];
    const ships = (me.ships || {})[zone] || 0;
    const crew = (me.ship_crews || {})[zone] || 0;
    return '<span class="atsea" style="top:' + pos[1] + '%;left:' + pos[0] +
      '%">🌊 ' + zone + ' · 🚢' + ships + ' · 👥' + crew + '</span>';
  }).join('');
}
function atHandIndex(id) {
  const me = (ATG.board && ATG.board.players[ATG.board.me]) || {};
  return (me.hand || []).findIndex(c => c.id === id);
}
// FB-0022: why Build/Attack cannot be used right now — the player
// starts every turn with 0 resources, 0 builds and 0 swords (end_turn
// discards them), so these actions only become possible after playing
// hand cards. The Mini App used to stay silent, which read as "the
// buttons do not work".
function atWhy(mode) {
  const g = ATG.board;
  const me = (g && g.players[g.me]) || {};
  const res = me.resources || {};
  if (mode === 'build') {
    if (!(me.builds > 0)) return '🏠 Build needs a build first — play a card like Village from your hand.';
    if ((res.food || 0) < 2) return '🏠 Build costs 2 food — play a card that produces food first.';
    return '🏠 Build: no territory you can build on right now.';
  }
  if (mode === 'attack') {
    if (!(me.swords > 0)) return '⚔️ Attack needs a sword first — play a card like Warrior from your hand.';
    return '⚔️ Attack: no territory in reach right now.';
  }
  return '';
}
function atRender() {
  const g = ATG.board;
  if (!g) return;
  const turn = document.getElementById('ayTurn');
  const players = document.getElementById('ayPlayers');
  const board = document.getElementById('ayBoard');
  const inv = document.getElementById('ayInv');
  const hand = document.getElementById('ayHand');
  const actions = document.getElementById('ayActions');
  const market = document.getElementById('ayMarket');
  const achievements = document.getElementById('ayAch');
  const join = document.getElementById('ayJoin');
  const npc = document.getElementById('ayNpc');
  const sea = document.getElementById('aySea');
  const start = document.getElementById('ayStart');
  const rematch = document.getElementById('ayRematch');
  document.getElementById('altay').classList.toggle('atseaon', !!g.seafarers);
  [join, npc, sea, start, rematch].forEach(el => el.classList.add('hidden'));
  [board, inv, hand, actions, market, achievements].forEach(el => { el.innerHTML = ''; });
  atRenderLog();
  const names = g.players.map(p => escapeHtml(p.name) + (p.npc ? ' 🤖' : '') +
    ' <b style="color:' + p.color + '">' + p.score + ' VP</b>').join(' · ');
  turn.innerHTML = g.phase === 'lobby' ? '🏜️ Altay lobby — ' + g.players.length + '/2 · ' + names :
    g.phase === 'over' ? '🏆 ' + (g.winner === null ? 'Draw' :
      escapeHtml((g.players[g.winner] || {}).name || 'Winner')) + ' wins! · ' + names :
    '🏜️ Turn ' + (g.turn + 1) + ' · ' + names + (g.can_act ? ' · <b>your move</b>' : '');
  if (ATG.newVer) turn.innerHTML += ' · 🔄 <b>New version — reopen the Mini App</b>';
  players.innerHTML = g.players.map((p, i) => '<div class="atplayer' +
    (i === g.current && g.phase !== 'lobby' ? ' atcurrent' : '') + '">' +
    '<span class="atfaction" style="' + atFactionStyle(p.faction) + '"></span>' +
    '<b>' + escapeHtml(p.name) + '</b> · ' + escapeHtml(p.faction_name) + ' · ' + p.score + ' VP<br>' +
    '<span class="atres">' + atResources(p) + '</span> · 🃏 ' + p.hand_count +
    ' · 🏠 ' + p.reserve + ' · ⚔️ ' + p.captured + ' · 🎯 ' + p.markers + '<br>' +
    (g.seafarers ? '<span class="atfleet">🪙 ' + (p.coins || 0) + ' ships ' +
      (g.sea_zones || []).map(z => z + ':' + ((p.ships || {})[z] || 0)).join(' ') +
      ' · supply ' + (p.ship_supply || 0) + ' · crews ' + (p.crews || 0) + '</span><br>' : '') +
    '📜 ' + escapeHtml(p.achievement || 'no active achievement') + '</div>').join('');
  if (g.phase === 'lobby') {
    board.innerHTML = '<div class="atlobby">Join or add an NPC, then start.<br>' +
      'Seafarers: ' + (g.seafarers ? 'on' : 'off') + ' — two sea zones, two islands, ships and crews.<br>' +
      'The board and your cards appear once the game starts.<br>' + names + '</div>';
    if (!g.is_player) join.classList.remove('hidden');
    if (g.players.length < (g.max_players || 2)) npc.classList.remove('hidden');
    if (g.me === 0) {
      sea.textContent = '🌊 Seafarers: ' + (g.seafarers ? 'on' : 'off');
      sea.classList.remove('hidden');
    }
    start.classList.remove('hidden');
    return;
  }
  if (g.phase === 'over') rematch.classList.remove('hidden');
  board.innerHTML = '<div class="atboard">' + g.regions.map(r => atRegion(r, g)).join('') +
    atSeaBadges(g) + '</div>';
  board.querySelectorAll('[data-region]').forEach(el => el.addEventListener('click', () => {
    const region = Number(el.dataset.region);
    if (ATG.mode === 'build' && (g.legal.build || []).map(String).includes(String(region))) {
      atMove('build', {region: region});
    } else if (ATG.mode === 'attack' && (g.legal.attack || []).some(o => o.region === region)) {
      atMove('attack', {region: region});
    } else if (ATG.mode === 'build' || ATG.mode === 'attack') {
      // FB-0022: tapping a territory that is not a legal target used to
      // do nothing at all — say why instead of looking broken.
      atLog(atWhy(ATG.mode));
    }
  }));
  const me = g.players[g.me] || {hand: []};
  // FB-0013: a labelled inventory for the viewer — all resources even
  // when zero, plus reserve, swords, builds and markers — and the cards
  // played this turn, each with its effect text.
  if (g.me !== null && g.me !== undefined && g.players[g.me]) {
    const res = Object.entries(me.resources || {}).map(([k, n]) =>
      (g.resource_icons[k] || k) + ' ' + n).join('  ');
    inv.innerHTML = '<div class="atlabel">🎒 Your inventory</div><div class="atinv">' +
      '<span class="atres">' + res + '</span><br>' +
      '🏠 ' + me.reserve + ' settlements in reserve · ⚔️ ' + me.swords + ' swords · ' +
      '🏠 ' + me.builds + ' builds · 🎯 ' + me.markers + ' conquest markers · ' +
      '🃏 deck ' + me.deck_count + ' · 🗑️ discard ' + me.discard_count +
      (g.seafarers ? '<br><span class="atfleet">🪙 ' + (me.coins || 0) + ' coins · 🚢 supply ' +
        (me.ship_supply || 0) + ' · 👥 crews ' + (me.crews || 0) +
        (g.sea_zones || []).map(z => ' · sea ' + z + ': ' + ((me.ships || {})[z] || 0) +
          '/' + ((me.ship_crews || {})[z] || 0)).join('') + '</span>' : '') + '</div>';
  }
  const played = g.players.filter(p => (p.played || []).length);
  if (played.length) {
    inv.innerHTML += '<div class="atlabel">Played this turn — what each card did</div>' +
      '<div class="atrow">' + played.map(p =>
        p.played.map(c => atCardCell(c, false, '', p.name)).join('')).join('') + '</div>';
  }
  hand.innerHTML = '<div class="atlabel">Your hand</div>' + (me.hand.length
    ? me.hand.map((c, i) => atCardCell(c, g.can_act, 'data-hand="' + i + '"')).join('')
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
    b.addEventListener('click', () => {
      // FB-0022: tapping Build/Attack with nothing available used to do
      // nothing at all — explain what is missing instead.
      if (ATG.mode !== mode) {
        const legal = mode === 'build' ? (g.legal.build || []) : (g.legal.attack || []);
        if (!legal.length) { atLog(atWhy(mode)); return; }
      }
      ATG.mode = ATG.mode === mode ? null : mode; atRender();
    });
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
  // FB-0022: Buy, Build, Attack and Develop all need what hand cards
  // give you — resources, builds, swords — and end_turn discards all
  // of them, so at the start of every turn the four buttons look dead
  // unless you play cards first. Say so right next to the buttons.
  if (g.can_act) {
    const res = Object.values(me.resources || {}).reduce((a, n) => a + n, 0);
    const hint = document.createElement('div');
    hint.className = 'athint';
    hint.textContent = (me.builds > 0 || me.swords > 0 || res > 0)
      ? '💡 Builds ' + (me.builds || 0) + ' · Swords ' + (me.swords || 0) + ' · Resources ' + res + ' — tap Buy, Build, Attack or Develop to use them.'
      : '💡 No resources, builds or swords yet — play cards from your hand first, then Buy, Build, Attack and Develop work.';
    actions.appendChild(hint);
  }
  if (g.seafarers && g.can_act) {
    const seaRow = document.createElement('div');
    seaRow.className = 'atrow';
    const shipwright = atHandIndex('shipwright');
    (g.ship_placements || []).forEach(zone => {
      if (shipwright < 0) return;
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'atbtn'; b.textContent = '🚢 Place ship ' + zone;
      b.addEventListener('click', () => atMove('play', {index: shipwright, params: {zone: zone}}));
      seaRow.appendChild(b);
    });
    const sailor = atHandIndex('sailor');
    if (sailor >= 0) {
      (g.sea_zones || []).forEach(zone => {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'atbtn'; b.textContent = '👥 Crew ' + zone;
        b.addEventListener('click', () => atMove('play', {
          index: sailor, params: {action: 'crew', zone: zone}}));
        seaRow.appendChild(b);
      });
      for (const [from, to] of [['A', 'B'], ['B', 'A']]) {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'atbtn'; b.textContent = '➡️ Ship ' + from + '→' + to;
        b.addEventListener('click', () => atMove('play', {
          index: sailor, params: {action: 'move', from: from, to: to}}));
        seaRow.appendChild(b);
      }
    }
    const explorer = atHandIndex('explorer');
    const islands = (g.regions || []).filter(r => r.id >= 25 && !r.marker && !(r.settlements || []).length);
    if (explorer >= 0 && islands.length) {
      const wrap = document.createElement('span');
      wrap.innerHTML = '<select id="ayResettle">' + islands.map(r =>
        '<option value="' + r.id + '">🏝️ ' + escapeHtml(r.name) + '</option>').join('') + '</select>';
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'atbtn'; b.textContent = '🧭 Resettle';
      b.addEventListener('click', () => atMove('play', {
        index: explorer, params: {action: 'resettle', region: Number(wrap.querySelector('select').value)}}));
      seaRow.appendChild(wrap);
      seaRow.appendChild(b);
    }
    if (seaRow.children.length) actions.appendChild(seaRow);
    const opts = Object.keys(g.resources || {}).map(k =>
      '<option value="' + escapeHtml(k) + '">' + escapeHtml(g.resource_icons[k] || k) + '</option>').join('');
    const trade = document.createElement('div');
    trade.className = 'attrade';
    trade.innerHTML = '🔄 Trade <select id="ayGive1">' + opts + '</select>' +
      '<select id="ayGive2"><option value="">3 of one</option>' + opts + '</select>' +
      ' for <select id="ayReceive">' + opts + '</select>' +
      '<button type="button" id="ayTradeGo"' + (me.traded ? ' disabled' : '') + '>Trade</button>';
    actions.appendChild(trade);
    trade.querySelector('#ayTradeGo').addEventListener('click', () => {
      const first = trade.querySelector('#ayGive1').value;
      const second = trade.querySelector('#ayGive2').value;
      const give = second ? {[first]: 1, [second]: 1} : {[first]: 3};
      atMove('trade', {give: give, receive: trade.querySelector('#ayReceive').value});
    });
  }
  market.innerHTML = '<div class="atlabel">Market — buy once per turn</div>' + (g.market || []).map(c => {
    const affordable = Object.entries(c.cost || {}).every(([k, n]) => (me.resources[k] || 0) >= n);
    const bought = (me.bought || []).includes(c.id);
    const clickable = g.can_act && affordable && !bought;
    return atCardCell(c, clickable, 'data-buy="' + escapeHtml(c.id) + '"');
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
document.getElementById('ayJoin').addEventListener('click', () => atMove('join'));
document.getElementById('ayNpc').addEventListener('click', () => atMove('npc'));
document.getElementById('aySea').addEventListener('click', () =>
  atMove('seafarers', {enabled: !(ATG.board && ATG.board.seafarers)}));
document.getElementById('ayStart').addEventListener('click', () => atMove('start'));
document.getElementById('ayRematch').addEventListener('click', () => atMove('rematch'));
atLoad();
