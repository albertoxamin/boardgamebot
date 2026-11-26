const FF = {chat_id: null, init: '', board: null, timer: null, me: 0, placeCard: null, placeKey: ''};
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
    'border-radius:999px;padding:1px 8px;font-size:11px;font-weight:900}' +
    // FB-0125: styles for the visual embroidery picker — the card the
    // player is stitching is ghosted (dashed amber) where it would land.
    '.ffghost{position:absolute;width:44px;height:63px;background-image:url(/assets/fadenfroh/images/fadenfroh-fabric.webp);' +
    'background-size:792px 567px;border:2px dashed #f59e0b;border-radius:3px;opacity:.85;box-sizing:border-box}' +
    '.ffplace{display:block;width:100%;text-align:left;background:#0f172a;border:1px solid #475569;' +
    'border-radius:10px;padding:8px;margin:6px 0;color:#e2e8f0;cursor:pointer}' +
    '.ffplace:active,.ffplace:focus-visible{border-color:#f59e0b}' +
    '.ffplacelabel{font-size:13px;font-weight:700;margin-bottom:4px}' +
    '.ffcardpick{display:inline-block;vertical-align:top;margin:4px;padding:6px;border:2px solid #475569;' +
    'border-radius:10px;background:#0f172a;color:#e2e8f0;cursor:pointer;text-align:center}' +
    '.ffcardpick:active,.ffcardpick:focus-visible{border-color:#f59e0b}' +
    '.ffpickcap{font-size:12px;font-weight:700;margin-top:4px}' +
    '.ffrowhead{width:100%;font-weight:800;margin:8px 0 2px}';
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
function ffHtmlButton(html, cls, fn) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = cls; b.innerHTML = html;
  b.addEventListener('click', fn);
  return b;
}
// FB-0125: the embroidery phase used to dump every possible placement
// (card x row x end x cover x needle, up to ~45) as cryptic text buttons
// like "#69 ... -> row 1 L 1". Now it is a two-step visual picker: first
// pick the card to stitch (shown with its real BGA fabric art), then tap
// where it goes on a preview of the row, with the card ghosted where it
// would land. Discard shows the card too, so every option is recognisable.
function ffRenderPlace(g, actions, pend) {
  const key = pend.cards.join(',');
  if (FF.placeKey !== key) { FF.placeKey = key; FF.placeCard = null; }
  const head = document.createElement('div');
  head.style.cssText = 'width:100%;font-weight:700;margin:2px 0 4px';
  if (FF.placeCard === null) {
    head.textContent = '🧵 Choose a card to stitch:';
    actions.appendChild(head);
    pend.cards.forEach((cid, i) => {
      actions.appendChild(ffHtmlButton(
        ffCardHtml(cid) + '<div class="ffpickcap">#' + (Number(cid) + 1) + '</div>',
        'ffcardpick', () => { FF.placeCard = i; ffRender(); }));
    });
  } else {
    const cid = pend.cards[FF.placeCard];
    head.textContent = '🧵 Stitching #' + (Number(cid) + 1) + ' — tap where it goes:';
    actions.appendChild(head);
    actions.appendChild(ffButton('← Another card', () => { FF.placeCard = null; ffRender(); }));
    const mine = (g.options || []).filter(o =>
      Number(String(o.value).split(':')[0]) === FF.placeCard);
    for (let row = 0; row < 3; row++) {
      const rowOpts = mine.filter(o => Number(String(o.value).split(':')[1]) === row);
      if (!rowOpts.length) continue;
      const rh = document.createElement('div');
      rh.className = 'ffrowhead';
      rh.textContent = 'Row ' + (row + 1);
      actions.appendChild(rh);
      rowOpts.forEach(o => {
        const parts = String(o.value).split(':');
        const side = parts[2], cover = Number(parts[3]), needle = parts[4] === '1';
        const how = needle ? 'with a needle' :
          cover === 1 ? 'covers 1 half' : 'covers 2 halves';
        const label = (side === 'left' ? 'Left' : 'Right') + ' end · ' + how;
        actions.appendChild(ffHtmlButton(
          '<div class="ffplacelabel">' + escapeHtml(label) + '</div>' +
          ffPlacePreview(g, cid, row, side, cover, needle),
          'ffplace', () => ffMove('choice', {value: o.value})));
      });
    }
  }
  pend.cards.forEach((cid, i) => {
    actions.appendChild(ffHtmlButton(
      ffCardHtml(cid) + '<div class="ffpickcap">🗑 Discard</div>',
      'ffcardpick', () => ffMove('discard', {cards: [i]})));
  });
}
// Mirror of the engine's _placement_targets: where the card's two halves
// (and a needle, if used) would land on this row.
function ffPlacePreview(g, cid, row, side, cover, needle) {
  const halves = (g.players[g.actor] && g.players[g.actor].rows[row]) || [];
  const cols = halves.map(h => h.col).sort((a, b) => a - b);
  const lo = cols[0], hi = cols[cols.length - 1];
  let start, gap = null;
  if (needle) {
    gap = side === 'left' ? lo - 1 : hi + 1;
    start = side === 'left' ? gap - 2 : gap + 1;
  } else if (cover === 1) {
    start = side === 'left' ? lo - 1 : hi;
  } else {
    start = side === 'left' ? lo : hi - 1;
  }
  const span = cols.concat([start, start + 1]);
  if (gap !== null) span.push(gap);
  const min = Math.min.apply(null, span), max = Math.max.apply(null, span);
  let html = '<div class="ffrow" style="width:' + ((max - min + 1) * 46) + 'px">';
  halves.forEach(h => {
    const left = ((h.col - min) * 46) + 'px';
    if (h.needle) {
      html += '<span class="ffneedle" style="left:' + left + '"></span>';
    } else if (h.start) {
      html += '<span class="ffstart" style="left:' + left + ';' + ffStartStyle(h) + '"></span>';
    } else {
      html += '<span class="ffhalf" style="left:' + left + ';' + ffHalfStyle(h.id, h.h) + '"></span>';
    }
  });
  for (let k = 0; k < 2; k++) {
    html += '<span class="ffghost" style="left:' + ((start + k - min) * 46) + 'px;' +
      ffHalfStyle(cid, k) + '"></span>';
  }
  if (gap !== null) {
    html += '<span class="ffneedle" style="left:' + ((gap - min) * 46) + 'px"></span>';
  }
  return html + '</div>';
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
  if (!g.pending || g.pending.kind !== 'place') { FF.placeCard = null; FF.placeKey = ''; }
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
  const pend = g.pending;
  if (pend && pend.kind === 'place' && (pend.cards || []).length) {
    ffRenderPlace(g, actions, pend);
  } else if (pend && pend.kind === 'keep' && (pend.cards || []).length) {
    // FB-0125: show the actual cards, not "Keep card 1/2/3".
    pend.cards.forEach((cid, i) => {
      actions.appendChild(ffHtmlButton(
        ffCardHtml(cid) + '<div class="ffpickcap">Keep this card</div>',
        'ffcardpick', () => ffMove('choice', {value: String(i)})));
    });
  } else {
    (g.options || []).forEach(o => {
      actions.appendChild(ffButton(o.label, () => ffMove('choice', {value: o.value})));
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
