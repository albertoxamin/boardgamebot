const FF = {chat_id: null, init: '', board: null, timer: null, me: 0, placeCard: null, placeKey: '', placeMode: 'c1', soloPick: [], soloKey: ''};
const FF_HOW_TO_PLAY_URL = 'https://www.youtube.com/watch?v=ezMd-IwlTyA';

// FB-0126 (Albert): the Mini App is an interactive board, not a wall of
// buttons — "if there are more than 5 buttons maybe you're doing the wrong
// thing". So: shopping taps the market itself (a material pile or an
// offer), embroidery taps a card in hand then the ghost where it goes on
// your own rows, keep taps the drawn card, bonus taps goal B or C. The
// only control row left is one 3-way "how it lands" switch while stitching
// (cover 1 half / cover 2 halves / with a needle); the board is the UI.
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
  let pick = mine.find(g => g.chat_id === pref) || mine.find(g => g.phase !== 'game_end') || mine[0];
  if (!pick && pref) {
    // Spectate the chat's game if one exists (Flip 7 / Odin pattern).
    // Without this a spectator falls through to create — which mid-game
    // accidentally returns the existing game, but after game_end spawns a
    // brand-new game in the group with a "created by <spectator>" message.
    const spec = await ffApi('/api/fadenfroh/game?chat_id=' + encodeURIComponent(pref) +
      '&init_data=' + encodeURIComponent(tg.init));
    if (spec.ok) pick = {chat_id: pref};
  }
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
    // FB-0126: the board is the UI — tappable market piles/offers, a
    // ghost of the card where it would land on your rows, a selected-card
    // lift, one 3-way "how it lands" switch, tappable goal tiles.
    '.ffhint{width:100%;font-size:13px;color:#cbd5e1;margin:2px 0 4px}' +
    '.ffpile{display:inline-flex;flex-direction:column;align-items:center;min-width:56px;' +
    'padding:8px 10px;background:#0f172a;border:1px solid #475569;border-radius:10px;' +
    'color:#e2e8f0;cursor:pointer}' +
    '.ffpile.ffstatic{cursor:default;opacity:.85}' +
    '.ffpile .ffic{font-size:22px}' +
    '.ffpile .ffcnt{font-size:12px;font-weight:800}' +
    '.ffoffer{display:inline-flex;align-items:flex-end;gap:2px;padding:6px;background:#0f172a;' +
    'border:1px solid #475569;border-radius:10px;cursor:pointer}' +
    '.ffoffer.ffstatic{cursor:default;opacity:.85}' +
    '.ffoffer .ffoffcap{font-size:11px;font-weight:800;color:#cbd5e1;margin-left:4px}' +
    '.ffghost{position:absolute;width:44px;height:63px;background-image:url(/assets/fadenfroh/images/fadenfroh-fabric.webp);' +
    'background-size:792px 567px;border:2px dashed #f59e0b;border-radius:3px;opacity:.85;box-sizing:border-box;cursor:pointer}' +
    '.ffcardpick{position:relative}' +
    '.ffcardpick.ffselected{border-color:#f59e0b;box-shadow:0 0 0 2px #f59e0b55,0 0 10px #f59e0b66;transform:translateY(-2px)}' +
    '.ffdiscard{position:absolute;top:-7px;right:-7px;width:22px;height:22px;border-radius:50%;' +
    'background:#7f1d1d;color:#fff;border:1px solid #fca5a5;font-size:12px;line-height:20px;' +
    'text-align:center;cursor:pointer;z-index:2}' +
    '.ffseg{display:flex;gap:6px;width:100%;margin:6px 0}' +
    '.ffseg button{flex:1;background:#1e293b;border:1px solid #475569;border-radius:9px;' +
    'padding:8px 4px;color:#e2e8f0;font-size:13px;font-weight:800;cursor:pointer}' +
    '.ffseg button.on{background:#f59e0b;border-color:#f59e0b;color:#111}' +
    '.ffseg button:disabled{opacity:.35;cursor:default}' +
    '.ffgoal.fftap{cursor:pointer;border-color:#f59e0b;box-shadow:0 0 0 2px #f59e0b55}' +
    '.ffgoal.ffoff{opacity:.45}' +
    // FB-0127: solo passing picks 1-2 adjacent market cards — the
    // picked cards get an amber outline, one ✓ pill confirms the take.
    '.ffsolo-pick{display:inline-flex;border-radius:3px;cursor:pointer}' +
    '.ffsolo-pick.on{outline:2px solid #f59e0b;outline-offset:1px;box-shadow:0 0 0 2px #f59e0b55}' +
    '.fftake{display:inline-block;margin-top:6px;background:#f59e0b;color:#111;' +
    'border-radius:999px;padding:7px 14px;font-size:13px;font-weight:900;cursor:pointer}';
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
// Mirror of the engine's _placement_targets: where the selected card's two
// halves (and a needle, if used) would land on this row, for one mode:
// 'c1' covers 1 half and grows the row, 'c2' covers 2 halves, 'needle'
// sits next to the row with a needle in the gap.
function ffGhostFor(row, side, mode) {
  const cols = row.map(h => h.col).sort((a, b) => a - b);
  if (!cols.length) return null;
  const lo = cols[0], hi = cols[cols.length - 1];
  if (mode === 'needle') {
    const gap = side === 'left' ? lo - 1 : hi + 1;
    const start = side === 'left' ? gap - 2 : gap + 1;
    return {cols: [start, start + 1], gap: gap};
  }
  const start = mode === 'c2'
    ? (side === 'left' ? lo : hi - 1)
    : (side === 'left' ? lo - 1 : hi);
  return {cols: [start, start + 1], gap: null};
}
function ffPlaceValue(i, row, side, mode) {
  if (mode === 'needle') return i + ':' + row + ':' + side + ':0:1';
  return i + ':' + row + ':' + side + ':' + (mode === 'c2' ? 2 : 1) + ':0';
}
function ffRowHtml(row, ghosts) {
  ghosts = ghosts || [];
  const cols = row.map(h => h.col);
  ghosts.forEach(gh => {
    cols.push.apply(cols, gh.cols);
    if (gh.gap !== null && gh.gap !== undefined) cols.push(gh.gap);
  });
  if (!cols.length) return '<div class="ffrow"></div>';
  const min = Math.min.apply(null, cols);
  const max = Math.max.apply(null, cols);
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
  // FB-0126: the ghost is the button — it sits exactly where the card
  // would land, and tapping it stitches the card there.
  ghosts.forEach(gh => {
    gh.cols.forEach((c, k) => {
      items.push('<span class="ffghost" data-place="' + gh.value + '" style="left:' +
        ((c - min) * 46) + 'px;' + ffHalfStyle(gh.cid, k) +
        '" title="Tap to stitch here"></span>');
    });
    if (gh.gap !== null && gh.gap !== undefined) {
      items.push('<span class="ffneedle" data-place="' + gh.value + '" style="left:' +
        ((gh.gap - min) * 46) + 'px" title="Tap to stitch here"></span>');
    }
  });
  return '<div class="ffrow" style="width:' + ((max - min + 1) * 46) + 'px">' + items.join('') + '</div>';
}
function ffButton(label, fn) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'primary'; b.textContent = label;
  b.addEventListener('click', fn);
  return b;
}
// FB-0126: embroidery is tap-the-card, then tap-the-ghost on your board.
// The hand tiles select (tap again to put the card back); the 🗑 badge on
// a tile discards that card; the one switch below picks how the card lands.
function ffRenderPlace(g, actions, pend) {
  const key = pend.cards.join(',');
  if (FF.placeKey !== key) { FF.placeKey = key; FF.placeCard = null; FF.placeMode = 'c1'; }
  const head = document.createElement('div');
  head.className = 'ffhint';
  head.textContent = FF.placeCard === null
    ? '🧵 Tap a card to stitch it:'
    : '🧵 Stitching #' + (Number(pend.cards[FF.placeCard]) + 1) +
      ' — tap the ghost on your board where it goes. Tap the card again to put it back.';
  actions.appendChild(head);
  pend.cards.forEach((cid, i) => {
    const tile = document.createElement('div');
    tile.className = 'ffcardpick' + (FF.placeCard === i ? ' ffselected' : '');
    tile.innerHTML = ffCardHtml(cid) + '<div class="ffpickcap">#' + (Number(cid) + 1) + '</div>' +
      '<span class="ffdiscard" title="Discard this card">🗑</span>';
    tile.addEventListener('click', () => {
      FF.placeCard = FF.placeCard === i ? null : i;
      ffRender();
    });
    tile.querySelector('.ffdiscard').addEventListener('click', (e) => {
      e.stopPropagation();
      ffMove('discard', {cards: [i]});
    });
    actions.appendChild(tile);
  });
  if (FF.placeCard !== null) {
    const actor = g.players[g.actor];
    const modes = [
      ['c1', '1 half', 'Cover one half — the row grows by one'],
      ['c2', '2 halves', 'Cover two halves'],
      ['needle', '🪡 Needle', 'Place with a needle — the card sits next to the row'],
    ];
    const seg = document.createElement('div');
    seg.className = 'ffseg';
    modes.forEach(([mode, label, title]) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      b.title = title;
      if (FF.placeMode === mode) b.classList.add('on');
      const has = (g.options || []).some(o => {
        const p = String(o.value).split(':');
        if (Number(p[0]) !== FF.placeCard) return false;
        if (mode === 'needle') return p[4] === '1';
        return p[4] === '0' && Number(p[3]) === (mode === 'c2' ? 2 : 1);
      });
      if (!has || (mode === 'needle' && (!actor || !actor.needles))) b.disabled = true;
      b.addEventListener('click', () => { FF.placeMode = mode; ffRender(); });
      seg.appendChild(b);
    });
    actions.appendChild(seg);
  }
}
// FB-0126: keep is just tap-the-card — the drawn cards are the UI.
function ffRenderKeep(g, actions, pend) {
  const head = document.createElement('div');
  head.className = 'ffhint';
  head.textContent = '🧶 You traded 3 threads — tap a card to keep it. The others are discarded.';
  actions.appendChild(head);
  pend.cards.forEach((cid, i) => {
    const tile = document.createElement('div');
    tile.className = 'ffcardpick';
    tile.innerHTML = ffCardHtml(cid) + '<div class="ffpickcap">Keep this card</div>';
    tile.addEventListener('click', () => ffMove('choice', {value: String(i)}));
    actions.appendChild(tile);
  });
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
  // Spectating, like the other games: not a player, outside the lobby
  // (in the lobby a non-player is a joiner, not a spectator). The board
  // is view-only for them — no actions, no Start, no Rematch.
  const spectating = !g.is_player && g.phase !== 'lobby';
  const specBar = spectating ?
    '<div class="lobby-note">👁 Spectating — view only (join in Telegram to play)</div>' : '';
  const turnSuffix = myTurn ? ' · <b>your move</b>' : npcTurn ? ' · <b>NPC\'s turn</b>' :
    actorP ? ' · <b>' + escapeHtml(actorP.name) + '\'s turn</b>' : '';
  turn.innerHTML = specBar + ffTurnBanner(g) + (g.phase === 'lobby' ? '🪡 Fadenfroh lobby — ' + g.players.length + '/4 · ' + names :
    g.phase === 'game_end' ? (g.solo ?
      '🏁 Solo: ' + escapeHtml((g.players[0] || {}).name || '') + ' — ' +
      (g.players[0] || {}).score + ' VP · ' + escapeHtml(g.solo_band || '') :
      '🏆 ' + escapeHtml((g.players[g.winner] || {}).name || 'Winner') +
      ' wins! · ' + names) :
    '🪡 Round ' + g.round + '/5 · ' + g.phase + ' · ' + names + turnSuffix);
  // FB-0126: in the bonus phase the B and C goal tiles are the choice —
  // tap one to score it. Other goals dim while choosing.
  const bonusPick = g.phase === 'bonus' && g.can_act;
  // Goals are only dealt at start — in the lobby g.goals is {} and the
  // tiles rendered as "Goal A: undefined" with a NaN sprite position.
  const dealt = ['A', 'B', 'C', 'D'].filter(k => g.goals[k] !== undefined && g.goals[k] !== null);
  goals.innerHTML = dealt.length ? '🎯 ' + dealt.map(k => {
    const tap = bonusPick && (k === 'B' || k === 'C');
    const cls = 'ffgoal' + (tap ? ' fftap' : bonusPick ? ' ffoff' : '');
    return '<span class="' + cls + '"' + (tap ? ' data-goal="' + k + '"' : '') +
      ' title="Goal ' + k + ': ' + g.goals[k] + '">' + k +
      '<span class="ffscore" style="' + ffScoreStyle(g.goals[k]) + '"></span></span>';
  }).join('') : '';
  if (bonusPick) {
    goals.querySelectorAll('[data-goal]').forEach(el =>
      el.addEventListener('click', () => ffMove('choice', {value: el.dataset.goal})));
  }
  // FB-0126: the market is the shopping UI — tap a material pile to take
  // it, or tap an offer to take it and start stitching. No buttons.
  const m = g.market;
  if (g.phase === 'lobby') {
    market.innerHTML = '';
  } else {
    const shopping = g.phase === 'shopping' && g.can_act;
    const soloShop = shopping && !!g.solo;
    // FB-0127: solo passing takes 1-2 adjacent market cards — the
    // selection lives on the market cards themselves, confirmed with
    // one ✓ pill. Reset the selection whenever the market changes.
    const soloKey = g.round + ':' + JSON.stringify(m.offers || []);
    if (FF.soloKey !== soloKey) { FF.soloKey = soloKey; FF.soloPick = []; }
    let mh = '';
    if (soloShop) {
      mh = '<div class="ffhint">👆 Solo: tap 1 or 2 adjacent cards, then ✓ Take them. The rest of the market is cleared.</div>';
    } else if (shopping) {
      mh = '<div class="ffhint">👆 Tap a material to take it, or tap an offer to take it and start stitching.</div>';
    }
    mh += '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">';
    if (m.threads) {
      mh += '<div class="ffpile' + (shopping ? '' : ' ffstatic') + '" data-mat="thread" title="' +
        (shopping ? 'Tap to take a thread' : 'Threads in the market') + '"><span class="ffic">🧵</span><span class="ffcnt">×' + m.threads + '</span></div>';
    }
    if (m.needles) {
      mh += '<div class="ffpile' + (shopping ? '' : ' ffstatic') + '" data-mat="needle" title="' +
        (shopping ? 'Tap to take a needle' : 'Needles in the market') + '"><span class="ffic">🪡</span><span class="ffcnt">×' + m.needles + '</span></div>';
    }
    if (m.thimble) {
      mh += '<div class="ffpile' + (shopping ? '' : ' ffstatic') + '" data-mat="thimble" title="' +
        (shopping ? 'Tap to take the thimble' : 'Thimble in the market') + '"><span class="ffic">🟘</span><span class="ffcnt">Thimble</span></div>';
    }
    let flat = 0;
    (m.offers || []).forEach((o, i) => {
      const cardsHtml = o.map(cid => {
        const idx = flat++;
        if (!soloShop) return ffCardHtml(cid);
        const sel = FF.soloPick.indexOf(idx) !== -1;
        return '<span class="ffsolo-pick' + (sel ? ' on' : '') + '" data-solo-card="' + idx +
          '" title="Tap to pick this card">' + ffCardHtml(cid) + '</span>';
      }).join('');
      mh += '<div class="ffoffer' + (shopping && !soloShop ? '' : ' ffstatic') + '"' +
        (soloShop ? '' : ' data-offer="' + i + '"') +
        ' title="' + (soloShop ? 'Tap the cards to pick them' : shopping ? 'Tap to take this offer' : 'Offer ' + (i + 1)) + '">' +
        cardsHtml + '<span class="ffoffcap">Offer ' + (i + 1) + '</span></div>';
    });
    mh += '</div>';
    if (soloShop) {
      const n = FF.soloPick.length;
      mh += '<div class="fftake" data-take="1" title="Take the selected cards and start stitching">' +
        (n ? '✓ Take selected (' + n + ')' : '✓ Pass — take no cards') + '</div>';
    }
    market.innerHTML = mh;
    if (shopping) {
      market.querySelectorAll('[data-mat]').forEach(el =>
        el.addEventListener('click', () => ffMove('material', {kind: el.dataset.mat})));
      market.querySelectorAll('[data-offer]').forEach(el =>
        el.addEventListener('click', () => ffMove('pass', {offer: Number(el.dataset.offer)})));
      market.querySelectorAll('[data-solo-card]').forEach(el =>
        el.addEventListener('click', () => {
          const idx = Number(el.dataset.soloCard);
          const at = FF.soloPick.indexOf(idx);
          if (at !== -1) { FF.soloPick.splice(at, 1); }
          else if (FF.soloPick.length === 0) { FF.soloPick.push(idx); }
          else if (FF.soloPick.length === 1 && Math.abs(FF.soloPick[0] - idx) === 1) { FF.soloPick.push(idx); }
          ffRender();
        }));
      const take = market.querySelector('[data-take]');
      if (take) take.addEventListener('click', () => ffMove('pass', {cards: FF.soloPick.slice()}));
    }
  }
  players.innerHTML = g.phase === 'lobby' ? '' : g.players.map((p, i) => {
    const active = i === g.actor;
    const badge = active ? ' <span class="ffturnbadge">👉 ' +
      (p.user_id === FF.me ? 'your turn' : 'turn') + '</span>' : '';
    // FB-0126: when a card is selected, the actor's own rows show the
    // ghost where the card would land (only for placements the engine
    // actually allows); tapping the ghost stitches the card there.
    const rowGhosts = [[], [], []];
    if (active && g.can_act && g.pending && g.pending.kind === 'place' && FF.placeCard !== null) {
      const cid = g.pending.cards[FF.placeCard];
      for (let r = 0; r < 3; r++) {
        ['left', 'right'].forEach(side => {
          const gh = ffGhostFor(p.rows[r], side, FF.placeMode);
          if (!gh) return;
          const value = ffPlaceValue(FF.placeCard, r, side, FF.placeMode);
          if ((g.options || []).some(o => o.value === value))
            rowGhosts[r].push({cols: gh.cols, gap: gh.gap, value: value, cid: cid});
        });
      }
    }
    return '<div class="ffplayer' + (active ? ' ffturn' : '') + '"><b>' + escapeHtml(p.name) +
      '</b> · ' + p.score + ' VP · 🧵' + p.threads + ' 🪡' + p.needles +
      (p.thimble ? ' 🟘' : '') + ' · hand ' + p.supply_count + badge +
      '<div>' + p.rows.map((row, ri) => ffRowHtml(row, rowGhosts[ri])).join('') + '</div></div>';
  }).join('');
  players.querySelectorAll('[data-place]').forEach(el =>
    el.addEventListener('click', () => ffMove('choice', {value: el.dataset.place})));
  if (g.phase === 'lobby') {
    // Join is for non-players (it was inverted: shown only to players,
    // who are already seated, so a spectator could never join — and the
    // server-side join accepts any user). Start is for seated players
    // only: the API lets anyone start, so a spectator must not see it.
    if (!g.is_player) join.classList.remove('hidden');
    if (g.is_player) start.classList.remove('hidden');
    howto.classList.remove('hidden');
    return;
  }
  if (g.phase === 'game_end') { if (g.is_player) rematch.classList.remove('hidden'); return; }
  if (!g.can_act) return;
  if (!g.pending || g.pending.kind !== 'place') { FF.placeCard = null; FF.placeKey = ''; }
  if (g.phase === 'shopping') return;
  const pend = g.pending;
  if (pend && pend.kind === 'place' && (pend.cards || []).length) {
    ffRenderPlace(g, actions, pend);
  } else if (pend && pend.kind === 'keep' && (pend.cards || []).length) {
    ffRenderKeep(g, actions, pend);
  } else if (pend && pend.kind === 'bonus') {
    const hint = document.createElement('div');
    hint.className = 'ffhint';
    hint.textContent = '🎯 Tap goal B or C above to score it.';
    actions.appendChild(hint);
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
