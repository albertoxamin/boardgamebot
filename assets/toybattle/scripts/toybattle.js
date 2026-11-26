const TBG = {user_id: 0, chat_id: null, board: null, timer: null, init: '', selected: null};
const TB_HOW_TO_PLAY_URL = 'https://www.youtube.com/watch?v=O2HjOQUFAio';
// Troop special abilities, worded from the Toy Battle rules (same strings
// as TROOP_ABILITIES in toybattle.py). Used until the board JSON serves
// troop_abilities (see tbAbility); keep the two in sync.
const TB_ABILITIES = {
  1: 'Draw 2 troops', 2: 'Place 1 extra troop', 3: 'Discard an adjacent enemy troop',
  4: 'Ignores connection', 5: 'Discard a random enemy rack troop', 6: 'Draw 1 troop',
  7: 'No special ability', 8: 'Joker: covers any enemy troop, can be covered by any troop'
};
function tbAbility(type) {
  const m = (TBG.board && TBG.board.troop_abilities) || TB_ABILITIES;
  return m[type] || m[String(type)] || '';
}

function tbLog(s) {
  const e = document.getElementById('tbLog');
  if (e) e.textContent += s + '\n';
}
// FB-0095/FB-0096: styling lives here, not in flip7.html (shared file).
// Turn banner, current-player badge, recent-moves box, wait note.
function tbInjectStyle() {
  if (document.getElementById('tbStyle')) return;
  const st = document.createElement('style');
  st.id = 'tbStyle';
  st.textContent = '.tbbanner{font-size:18px;font-weight:800;border-radius:10px;padding:9px 12px;' +
    'margin-bottom:8px;text-align:center}.tbbanner.tbmyturn{background:#14532d;color:#dcfce7;' +
    'border:2px solid #22c55e}.tbbanner.tbnpc{background:#3b0764;color:#f3e8ff;border:2px solid #a855f7}' +
    '.tbbanner.tbwait{background:#1e293b;color:#cbd5e1;border:2px solid #475569}' +
    '.tbturnbadge{display:inline-block;font-size:11px;font-weight:800;border-radius:999px;' +
    'padding:1px 8px;margin-left:6px;background:#f59e0b;color:#111;vertical-align:middle}' +
    '.tbturnbadge.tbmine{background:#22c55e;color:#052e16}' +
    '.tbrecent{background:#0f172a99;border:1px solid #334155;border-radius:10px;padding:7px 10px;' +
    'margin-bottom:8px;font-size:13px;line-height:1.45}.tbrecent b{display:block;font-size:12px;' +
    'color:#94a3b8;margin-bottom:2px}.tbackrow.tbnotmine .tbrack{opacity:.55}' +
    '.tbwaitnote{font-size:12px;font-weight:700;color:#fbbf24;margin-top:5px}';
  document.head.appendChild(st);
}
// The viewer is the actor only when the current/pending player is them.
// NOTE: bot.py sets can_act true while the NPC acts too (anyone may play
// for the NPC), so can_act alone must NOT gate the viewer's rack —
// otherwise during the NPC's turn the viewer can "select" their own toys
// and the app tries to place the NPC's troop at that index (FB-0096c).
function tbIsMyTurn(g) {
  const a = g.actor;
  return a !== null && a !== undefined && g.players[a] &&
         g.players[a].user_id === TBG.user_id;
}
function tbApi(path, opts) { return fetch(path, opts).then(r => r.json()); }
function tbChatId(raw) {
  let s = String(raw || '');
  if (s.startsWith('toybattle')) s = s.slice(9);
  const n = parseInt(s, 10);
  return isNaN(n) ? 0 : n;
}
async function tbLoad() {
  const tg = tgInit();
  if (!tg.id) {
    document.getElementById('tbTurn').textContent = 'Open as Telegram Mini App via the bot link.';
    return;
  }
  TBG.user_id = tg.id;
  TBG.init = tg.init;
  const qp = new URLSearchParams(location.search);
  const pref = tbChatId(tg.start) || tbChatId(qp.get('app')) ||
               parseInt(qp.get('chat_id'), 10) || tbChatId(tg.chat_instance);
  const r = await tbApi('/api/toybattle/mygames?init_data=' + encodeURIComponent(tg.init));
  const mine = r.games || [];
  const pick = mine.find(g => g.chat_id === pref) || mine.find(g => g.phase !== 'game_end') || mine[0];
  if (pick) tbSelect(pick.chat_id);
  else if (pref) {
    const cr = await tbApi('/api/toybattle/create', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({init_data: tg.init, chat_id: pref})
    });
    if (cr.game) tbSelect(cr.game.chat_id);
    else tbLog('⛔ ' + (cr.error || 'create failed'));
  } else {
    document.getElementById('tbTurn').textContent = 'No Toy Battle game yet — send /toybattle in a chat.';
  }
}
async function tbSelect(chat_id) {
  TBG.chat_id = chat_id;
  await tbRefresh();
  if (TBG.timer) clearInterval(TBG.timer);
  TBG.timer = setInterval(tbRefresh, 3000);
}
async function tbRefresh() {
  if (!TBG.chat_id) return;
  const q = '?chat_id=' + encodeURIComponent(TBG.chat_id) + '&init_data=' + encodeURIComponent(TBG.init);
  const r = await tbApi('/api/toybattle/game' + q);
  if (r.game) { TBG.board = r.game; tbRender(); }
}
async function tbMove(action, extra) {
  const body = Object.assign({chat_id: TBG.chat_id, action: action, init_data: TBG.init}, extra || {});
  const r = await tbApi('/api/toybattle/move', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  if (r.events) r.events.forEach(e => tbLog(e));
  if (r.error) tbLog('⛔ ' + r.error);
  if (r.game) { TBG.board = r.game; TBG.selected = null; tbRender(); }
}
function tbTile(type, owner, extraClass) {
  const col = ((Number(type) || 1) - 1) % 12;
  const row = Number(owner) === 1 ? 100 : 0;
  const name = escapeHtml(TBG.board.troop_names[type] || type);
  const ab = escapeHtml(tbAbility(type));
  return '<span class="tbtile ' + (extraClass || '') + '" style="background-position:' +
         (col / 11 * 100) + '% ' + row + '%" title="' + name + (ab ? ' — ' + ab : '') +
         '"></span>';
}
function tbBase(b, data, g) {
  const top = data.top;
  const legal = g.legal && Object.values(g.legal).some(list => list.map(String).includes(String(b)));
  const placeable = TBG.selected !== null &&
    (g.legal[String(TBG.selected)] || []).map(String).includes(String(b));
  const cls = 'tbbase' + (legal ? ' tblegal' : '') + (data.special ? ' tbspecial' : '') +
              (placeable ? ' tbplaceable' : '');
  let inner = '';
  if (top) inner = tbTile(top.type, top.owner, 'tbonboard') +
    (data.height > 1 ? '<span class="tbheight">' + data.height + '</span>' : '');
  else inner = '<span class="tbemptybase">' + (data.special ? '★' : '') + '</span>';
  if (String(b) === '1' || String(b) === '41') inner += '<span class="tbhq">HQ</span>';
  const sel = placeable ? ' tbselected' : '';
  return '<div class="' + cls + sel + '" style="top:' + data.top_pos + '%;left:' + data.left_pos +
         '%" data-base="' + b + '" title="Base ' + b + (placeable ? ' — tap to place here' : '') + '">' + inner + '</div>';
}
function tbMedal(m, data) {
  // assets/toybattle/images/toybattle-medals.webp has two frames: gold star (claimed medal)
  // and an empty slot. Any claimed medal shows the star; the owner's
  // colour ring tells whose it is. Unclaimed spots show the empty slot.
  const owner = data.owner;
  const claimed = owner !== null && owner !== undefined;
  const bg = claimed ? 'background-position:0 0' : 'background-position:100% 0';
  const cls = 'tbmedal' + (claimed ? ' tbclaimed tb' + (Number(owner) === 0 ? 'blue' : 'red')
                                   : ' tbunclaimed');
  return '<span class="' + cls + '" style="top:' + data.top + '%;left:' + data.left + '%;' + bg +
         '" title="Medal ' + m + ': ' + (claimed ? 'claimed by ' +
         escapeHtml((TBG.board.players[owner] || {}).name || '') : 'unclaimed') + '"></span>';
}
function tbRack(p, me, g, idx) {
  const tiles = [];
  const n = Math.max(8, p.rack_count);
  const myTurn = tbIsMyTurn(g);
  for (let i = 0; i < n; i++) {
    const type = p.rack[i];
    // FB-0096 (c): only the viewer's own turn makes their toys tappable.
    // During the NPC's turn (incl. its pending choice) the rack is plain
    // display — no buttons, no tap-to-place.
    const can = me && myTurn && !g.pending && (g.legal[String(i)] || []).length;
    if (type === undefined) tiles.push('<span class="tback"></span>');
    else if (!me) tiles.push('<span class="track"><span class="tback"></span></span>');
    else {
      const sel = TBG.selected === i ? ' tbselected' : '';
      const inner = can
        ? '<button type="button" class="track" data-index="' + i + '" title="' +
          escapeHtml(g.troop_names[type] || type) + ' — ' + escapeHtml(tbAbility(type)) + '">' +
          tbTile(type, idx) + '</button>'
        : '<span class="track">' + tbTile(type, idx) + '</span>';
      tiles.push('<span class="tbtoy' + sel + '">' + inner +
        '<span class="tbtoyname">' + escapeHtml(g.troop_names[type] || type) + '</span>' +
        '<span class="tbtoyability">' + escapeHtml(tbAbility(type)) + '</span></span>');
    }
  }
  return tiles.join('');
}
function tbRender() {
  const g = TBG.board;
  if (!g) return;
  tbInjectStyle();
  const turn = document.getElementById('tbTurn');
  const board = document.getElementById('tbBoard');
  const actions = document.getElementById('tbActions');
  const join = document.getElementById('tbJoin');
  const start = document.getElementById('tbStart');
  const howto = document.getElementById('tbHowTo');
  const rematch = document.getElementById('tbRematch');
  const draw = document.getElementById('tbDraw');
  [join, start, howto, rematch, draw].forEach(el => el.classList.add('hidden'));
  actions.innerHTML = '';
  document.getElementById('tbLog').textContent = (g.log || []).join('\n');
  // FB-0095: who is to move, stated plainly. can_act is also true while
  // the NPC acts (anyone may play for it), so the old header said
  // "your move" on the NPC's turn too — that was the confusion.
  const actorP = (g.actor !== null && g.actor !== undefined) ? g.players[g.actor] : null;
  const myTurn = tbIsMyTurn(g);
  const npcTurn = !!(actorP && actorP.npc);
  const actorName = actorP ? actorP.name : '';
  // A selection made on my turn must not survive into someone else's
  // turn (the poll refreshes every 3s): it would offer 📍 Base buttons
  // for the other player's legal spots.
  if (!myTurn) TBG.selected = null;
  const names = g.players.map(p => escapeHtml(p.name) + (p.npc ? ' 🤖' : '') +
    ' <b class="tb' + (p.color === 'red' ? 'red' : 'blue') + '">' + p.medals + '/' + g.medal_target + ' 🏅</b>').join(' vs ');
  const turnSuffix = g.phase === 'play'
    ? (myTurn ? ' · <b>your move</b>' : npcTurn ? ' · <b>NPC\'s turn</b>' :
       ' · <b>' + escapeHtml(actorName) + '\'s turn</b>')
    : '';
  turn.innerHTML = g.phase === 'lobby' ? '🎯 Toy Battle lobby — ' + g.players.length + '/2 · ' + names :
                   g.phase === 'game_end' ? '🏆 ' + (g.winner === null ? 'Draw' :
                     escapeHtml((g.players[g.winner] || {}).name || 'Winner')) + ' wins! · ' + names :
                   '🎯 Turn ' + g.turn + ' · ' + names + turnSuffix;
  // Prominent turn banner + recent moves (FB-0095, FB-0096 b): the log at
  // the bottom is easy to miss, so the last moves and whose turn it is
  // sit above the board instead.
  let banner = document.getElementById('tbBanner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'tbBanner';
    turn.parentNode.insertBefore(banner, turn.nextSibling);
  }
  let recent = document.getElementById('tbRecent');
  if (!recent) {
    recent = document.createElement('div');
    recent.id = 'tbRecent';
    banner.parentNode.insertBefore(recent, banner.nextSibling);
  }
  if (g.phase === 'play') {
    if (myTurn) {
      banner.className = 'tbbanner tbmyturn';
      banner.textContent = '👉 Tocca a te — your move!';
    } else if (npcTurn) {
      banner.className = 'tbbanner tbnpc';
      banner.textContent = g.pending
        ? '🤖 Tocca a NPC — scegli per lui qui sotto 👇'
        : '🤖 Tocca a NPC — gioca per lui: 🎁 pesca o piazza un suo giocattolo';
    } else {
      banner.className = 'tbbanner tbwait';
      banner.textContent = '⏳ Tocca a ' + actorName + ' — aspetta il tuo turno';
    }
    banner.classList.remove('hidden');
    const last = (g.log || []).slice(-3);
    recent.className = 'tbrecent';
    recent.innerHTML = last.length
      ? '<b>📜 Ultime mosse</b>' + last.map(e => '<div>' + escapeHtml(e) + '</div>').join('')
      : '';
    recent.classList.toggle('hidden', !last.length);
  } else {
    banner.classList.add('hidden');
    recent.classList.add('hidden');
  }
  if (g.phase === 'lobby') {
    board.innerHTML = '<div class="tblobby">Join, then anyone taps Start.</div>';
    if (!g.is_player) join.classList.remove('hidden');
    start.classList.remove('hidden');
    howto.classList.remove('hidden');
    return;
  }
  if (g.phase === 'game_end') rematch.classList.remove('hidden');
  {
    let html = '<div class="tbboard">';
    Object.entries(g.bases).forEach(([b, d]) => { html += tbBase(b, d, g); });
    Object.entries(g.medal_spots).forEach(([m, d]) => { html += tbMedal(m, d); });
    html += '</div><div class="tbracks">';
    g.players.forEach((p, i) => {
      const isMe = p.user_id === TBG.user_id;
      // FB-0095: a badge on the current player's row, not just the thin
      // amber border (.tbcurrent) that was easy to miss.
      const badge = p.is_current
        ? '<span class="tbturnbadge' + (isMe && myTurn ? ' tbmine' : '') + '">' +
          (isMe && myTurn ? '👉 TOCCA A TE' : npcTurn && p.npc ? '🤖 TURNO NPC' : '▶️ DI TURNO') + '</span>'
        : '';
      const rowCls = 'tbackrow' + (p.is_current ? ' tbcurrent' : '') +
                     (isMe && !myTurn && g.phase === 'play' ? ' tbnotmine' : '');
      html += '<div class="' + rowCls + '">' +
              '<div class="tbhead">' + (i === 0 ? '🔵 ' : '🔴 ') + escapeHtml(p.name) +
              (p.npc ? ' 🤖' : '') + ' · 🎒' + p.rack_count + ' · 📦' + p.reserve +
              ' · 🗑' + p.discard + badge + '</div><div class="tbrack">' + tbRack(p, isMe, g, i) + '</div>' +
              // FB-0096 (c): say so on the viewer's own row while waiting,
              // including during the NPC's pending choice.
              (isMe && !myTurn && g.phase === 'play'
                ? '<div class="tbwaitnote">⏳ Aspetta il tuo turno — i tuoi giocattoli non si possono selezionare ora</div>'
                : '') +
              '</div>';
    });
    html += '</div>';
    board.innerHTML = html;
    board.querySelectorAll('[data-index]').forEach(el => el.addEventListener('click', () => {
      TBG.selected = Number(el.dataset.index); tbRender();
    }));
    // Tap-to-place (FB-0090): with a troop selected, tapping a legal base
    // on the board places it there. The 📍 Base buttons below stay as-is.
    board.querySelectorAll('[data-base]').forEach(el => el.addEventListener('click', () => {
      if (TBG.selected === null || g.pending || !myTurn) return;
      const base = Number(el.dataset.base);
      if ((g.legal[String(TBG.selected)] || []).map(Number).includes(base))
        tbMove('place', {index: TBG.selected, base: base});
    }));
    if (g.pending) {
      g.options.forEach(o => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'primary';
        b.textContent = o.label;
        b.addEventListener('click', () => tbMove('choose', {value: o.value}));
        actions.appendChild(b);
      });
    } else if (g.can_act) {
      // 🎁 Draw stays available on the NPC's turn: the NPC has no AI, the
      // viewer draws for it. Only the rack-selection buttons below need
      // myTurn — a selection cannot exist off-turn any more.
      draw.classList.remove('hidden');
      if (myTurn && TBG.selected !== null && (g.legal[String(TBG.selected)] || []).length) {
        const back = document.createElement('button');
        back.type = 'button';
        back.className = 'tbopt';
        back.textContent = '↩️ Pick another troop';
        back.addEventListener('click', () => { TBG.selected = null; tbRender(); });
        actions.appendChild(back);
        g.legal[String(TBG.selected)].forEach(base => {
          const b = document.createElement('button');
          b.type = 'button';
          b.className = 'tbopt';
          b.textContent = '📍 Base ' + base;
          b.addEventListener('click', () => tbMove('place', {index: TBG.selected, base: base}));
          actions.appendChild(b);
        });
      }
    }
  }
}
document.getElementById('tbJoin').addEventListener('click', () => tbMove('join'));
document.getElementById('tbStart').addEventListener('click', () => tbMove('start'));
document.getElementById('tbHowTo').addEventListener('click', () => {
  try {
    if (window.Telegram && Telegram.WebApp && Telegram.WebApp.openLink)
      Telegram.WebApp.openLink(TB_HOW_TO_PLAY_URL);
    else window.open(TB_HOW_TO_PLAY_URL, '_blank');
  } catch (e) { window.open(TB_HOW_TO_PLAY_URL, '_blank'); }
});
document.getElementById('tbRematch').addEventListener('click', () => tbMove('rematch'));
document.getElementById('tbDraw').addEventListener('click', () => tbMove('draw'));
tbLoad();
