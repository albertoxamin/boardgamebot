// Fellowship Mini App (synced). Loaded by flip7.html router.
const FTR = {user_id: 0, chat_id: null, board: null, timer: null, init: '', target: null, sig: ''};
const FTR_CARD_SHEET = 'fellowship_cards/cards.jpg';
const FTR_CHAR_SHEETS = {
  early: 'fellowship_cards/characters-early.jpg',
  late: 'fellowship_cards/characters-late.jpg',
  legolas: 'fellowship_cards/characters-legolas.jpg'
};
const FTR_CHAR_GRIDS = {early: {w: 5, h: 5}, late: {w: 10, h: 4}, legolas: {w: 10, h: 4}};
const FTR_CARD_SUITS = {
  H: {name: 'Hill', row: 1}, M: {name: 'Mountain', row: 0},
  F: {name: 'Forest', row: 2}, S: {name: 'Shadow', row: 3}, R: {name: 'Ring', row: 4}
};
const FTR_CHAR_ART = {
  frodo: {sheet: 'early', id: 900, name: 'Frodo'},
  bilbo: {sheet: 'early', id: 901, name: 'Bilbo'},
  gandalf: {sheet: 'early', id: 905, name: 'Gandalf'},
  pippin: {sheet: 'early', id: 906, name: 'Pippin'},
  sam: {sheet: 'early', id: 907, name: 'Sam'},
  merry: {sheet: 'early', id: 902, name: 'Merry'},
  gildor: {sheet: 'late', id: 17903, name: 'Gildor Inglorion'},
  maggot: {sheet: 'early', id: 908, name: 'Farmer Maggot'},
  fatty: {sheet: 'early', id: 904, name: 'Fatty Bolger'},
  tom: {sheet: 'late', id: 17909, name: 'Tom Bombadil'},
  goldberry: {sheet: 'early', id: 911, name: 'Goldberry'},
  underhill: {sheet: 'early', id: 913, name: 'Mr. Underhill'},
  barliman: {sheet: 'early', id: 912, name: 'Barliman Butterbur'},
  strider: {sheet: 'early', id: 910, name: 'Strider'},
  aragorn: {sheet: 'early', id: 919, name: 'Aragorn'},
  legolas: {sheet: 'legolas', id: 2826, name: 'Legolas'},
  gimli: {sheet: 'late', id: 4438, name: 'Gimli son of Glóin'},
  boromir: {sheet: 'early', id: 921, name: 'Boromir'},
  bill: {sheet: 'late', id: 17915, name: 'Bill the Pony'},
  glorfindel: {sheet: 'late', id: 17914, name: 'Glorfindel'},
  elrond: {sheet: 'late', id: 17918, name: 'Elrond'},
  gollum: {name: 'Gollum'},
  arwen: {sheet: 'late', id: 17917, name: 'Arwen'},
  gloin: {sheet: 'late', id: 17916, name: 'Glóin'},
  shadowfax: {sheet: 'early', id: 923, name: 'Shadowfax'},
  radagast: {sheet: 'late', id: 17922, name: 'Radagast'},
  galadriel: {sheet: 'late', id: 17931, name: 'Galadriel'},
  celeborn: {sheet: 'late', id: 17930, name: 'Celeborn'}
};

function ftrEsc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function ftrLog(s) { let e = document.getElementById('ftrLog'); if (e) e.textContent += s + '\n'; }
function ftrChatFrom(s) { let m = String(s || '').match(/(-?\d+)/); return m ? parseInt(m[1], 10) : 0; }
function ftrInit() {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) tg.ready();
  const q = new URLSearchParams(location.search);
  let start = q.get('app') || '';
  try {
    const p = new URLSearchParams(tg && tg.initData || '');
    start = start || p.get('start_param') || '';
  } catch (e) {}
  return {
    id: tg && tg.initDataUnsafe && tg.initDataUnsafe.user ? tg.initDataUnsafe.user.id : 0,
    init: tg && tg.initData ? tg.initData : '',
    start: start,
    chat_instance: tg && tg.initDataUnsafe ? String(tg.initDataUnsafe.chat_instance || '') : ''
  };
}
function ftrSpriteStyle(sheet, w, h, index) {
  let col = index % w;
  let row = Math.floor(index / w);
  let x = w > 1 ? col * 100 / (w - 1) : 0;
  let y = h > 1 ? row * 100 / (h - 1) : 0;
  return `background-image:url(${sheet});background-size:${w * 100}% ${h * 100}%;` +
    `background-position:${x}% ${y}%`;
}
function ftrCardName(code) {
  let text = String(code || '');
  let info = FTR_CARD_SUITS[text[0]];
  return info ? `${text.slice(1)} - ${info.name}` : text;
}
function ftrCard(code, dim, click) {
  let text = String(code || '');
  let info = FTR_CARD_SUITS[text[0]];
  let label = ftrCardName(code);
  let style = info ? ftrSpriteStyle(FTR_CARD_SHEET, 8, 5, info.row * 8 + parseInt(text.slice(1), 10) - 1) : '';
  let cls = 'ftr-card' + (dim ? ' dim' : '') + (click ? ' click' : '');
  return `<span class="${cls}" style="${style}" title="${ftrEsc(label)}" aria-label="${ftrEsc(label)}" ${click || ''}></span>`;
}
function ftrCharArt(key) {
  return FTR_CHAR_ART[key] || {name: key ? String(key) : '?'};
}
function ftrCharName(key) {
  return ftrCharArt(key).name;
}
function ftrChar(key, cls, click) {
  let art = ftrCharArt(key);
  let extra = cls ? ' ' + cls : '';
  let attr = click ? ` onclick="${click}"` : '';
  if (!art.sheet) {
    return `<span class="ftr-char fallback${extra}" title="${ftrEsc(art.name)}"${attr}>${ftrEsc(art.name)}</span>`;
  }
  let grid = FTR_CHAR_GRIDS[art.sheet];
  let style = ftrSpriteStyle(FTR_CHAR_SHEETS[art.sheet], grid.w, grid.h, art.id % 100);
  return `<span class="ftr-char${extra}" style="${style}" title="${ftrEsc(art.name)}" aria-label="${ftrEsc(art.name)}"${attr}></span>`;
}
async function ftrLoad() {
  let tg = ftrInit();
  if (!tg.id) {
    document.getElementById('ftrBoard').innerHTML = '<div class="table lobby-note">Open as Telegram Mini App via the bot link.</div>';
    return;
  }
  FTR.user_id = tg.id; FTR.init = tg.init;
  let r = await fetch('/api/fellowship/mygames?init_data=' + encodeURIComponent(tg.init)).then(x => x.json());
  let mine = r.games || [];
  let pref = ftrChatFrom(tg.start) || ftrChatFrom(tg.chat_instance);
  let pick = mine.find(g => String(g.chat_id) === String(pref)) ||
    mine.find(g => g.phase !== 'game_end' && g.phase !== 'chapter_end') || mine[0];
  if (pick) ftrSelect(pick.chat_id);
  else if (pref) {
    let cr = await fetch('/api/fellowship/create', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({init_data: tg.init, chat_id: pref})
    }).then(x => x.json());
    if (cr.game) ftrSelect(cr.game.chat_id);
    else ftrLog('⛔ ' + (cr.error || 'create failed'));
  } else {
    document.getElementById('ftrBoard').innerHTML = '<div class="table lobby-note">No Fellowship game yet — send /fotr in a chat.</div>';
  }
}
async function ftrSelect(chat_id) {
  FTR.chat_id = chat_id;
  FTR.sig = '';
  await ftrRefresh();
  if (FTR.timer) clearInterval(FTR.timer);
  FTR.timer = setInterval(ftrRefresh, 3000);
}
async function ftrRefresh() {
  if (!FTR.chat_id) return;
  let r = await fetch('/api/fellowship/game?chat_id=' + encodeURIComponent(FTR.chat_id) +
    '&init_data=' + encodeURIComponent(FTR.init)).then(x => x.json());
  if (r.ok) {
    let sig = JSON.stringify(r.game);
    if (sig === FTR.sig) return;
    FTR.sig = sig;
    FTR.board = r.game;
    ftrRender();
  }
}
async function ftrMove(action, extra) {
  let body = Object.assign({chat_id: FTR.chat_id, action: action, init_data: FTR.init}, extra || {});
  let r = await fetch('/api/fellowship/move', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  }).then(x => x.json());
  if (r.events) r.events.forEach(e => ftrLog(e.replace(/<[^>]+>/g, '')));
  if (r.error) ftrLog('⛔ ' + r.error);
  if (r.game) {
    FTR.sig = JSON.stringify(r.game);
    FTR.board = r.game;
    FTR.target = null;
    ftrRender();
  }
}
function ftrRender() {
  let b = FTR.board;
  if (!b) return;
  let me = (b.players || []).find(p => p.user_id === FTR.user_id);
  let myIdx = b.viewer_index;
  let pendingActor = b.pending && b.players[b.pending.actor];
  let isPendingMine = !!pendingActor && (pendingActor.npc || pendingActor.user_id === FTR.user_id);
  let isTurnMine = b.phase === 'playing' && b.current != null && b.players[b.current] &&
    (b.players[b.current].npc || b.players[b.current].user_id === FTR.user_id);
  let turnText = '';
  if (b.phase === 'lobby') turnText = '🪑 Lobby — join, then start';
  else if (b.phase === 'choosing') turnText = b.current != null && b.players[b.current] ?
    '🎭 ' + (b.players[b.current].npc ? '🤖 NPC' : ftrEsc(b.players[b.current].name)) + ' chooses a character' : '🎭 Choosing';
  else if (b.phase === 'setup') turnText = pendingActor ? '🔨 Setup: ' + (pendingActor.npc ? '🤖 NPC' : ftrEsc(pendingActor.name)) : '🔨 Setup';
  else if (b.phase === 'playing') turnText = b.current != null && b.players[b.current] ?
    '👉 ' + (b.players[b.current].npc ? '🤖 NPC' : ftrEsc(b.players[b.current].name)) + "'s turn" : '🃏 Playing';
  else turnText = '🏁 ' + ftrEsc(b.result || b.phase);
  document.getElementById('ftrTurn').innerHTML = turnText;

  let head = `<b>Chapter ${b.chapter}: ${ftrEsc(b.chapter_title)}</b> · round ${b.round} · ${ftrEsc(b.victory)}` +
    `<div class="small">Lost: ${ftrEsc(b.lost || 'taken')} · Rings: ${b.ring_broken ? 'BROKEN' : 'sealed'}</div>`;
  let seats = '<div class="seats ftr-seats">' + (b.players || []).map((p, i) => {
    let cls = 'seat' + (b.current === i || (b.pending && b.pending.actor === i) ? ' current' : '');
    let g = (b.goals || []).find(x => x.player === i);
    let goal = g ? (g.ok ? '✅' : '❌') : '';
    let portrait = p.character ? ftrChar(p.character, 'small tap', `ftrShowArt('${p.character}')`) : '';
    return `<div class="${cls}"><div class="seat-head"><span>${p.npc ? '🤖 ' : ''}${ftrEsc(p.name)}${i === b.ring_holder ? ' 💍' : ''}</span><span class="score">${p.hand_count}</span></div>` +
      `<div class="ftr-seat-body">${portrait}<div class="small">${p.tricks} tricks<br>${p.won_count} cards ${goal}</div></div></div>`;
  }).join('') + '</div>';
  let trickHtml = '';
  if (b.trick && b.trick.plays && b.trick.plays.length) {
    trickHtml = '<div class="table"><div class="small">Trick ' + b.trick_no + ' · lead ' +
      ftrEsc(b.trick.suit || '?') + '</div><div>' + b.trick.plays.map(pl =>
        ftrEsc((b.players[pl.player] || {}).name || '?') + ': ' + ftrCard(pl.card)).join(' ') + '</div></div>';
  }
  document.getElementById('ftrBoard').innerHTML = '<div class="card">' + head + seats + trickHtml + '</div>';

  let actions = '';
  if (b.phase === 'choosing' && b.current != null && (b.current === myIdx || b.players[b.current].npc)) {
    actions += '<div class="small">Choose a character:</div><div class="ftr-choices">' + (b.available || []).map(c =>
      `<button class="primary ftr-choice" onclick="ftrMove('choose',{character:'${c}'})">${ftrChar(c, 'small')}</button>`).join('') + '</div>';
  }
  if (b.phase === 'setup' && isPendingMine && b.pending) {
    if (b.pending.kind === 'exchange_out') {
      actions += '<div class="small">Exchange target: ' + (b.pending.targets || []).map(t =>
        `<button class="${FTR.target === t ? 'hit' : 'stay'}" onclick="ftrTarget(${t})">${ftrEsc((b.players[t] || {}).name || t)}</button>`).join('') + '</div>';
    } else if (b.pending.kind === 'exchange_in') {
      actions += '<div class="small">Tap a card to pass back.</div>';
    }
  }
  if (b.phase === 'playing' && b.pending && b.pending.kind === 'ring_choice' && isPendingMine) {
    actions += '<button class="hit" onclick="ftrMove(\'ring\',{use:true})">💍 Claim with R1</button>' +
      '<button class="stay" onclick="ftrMove(\'ring\',{use:false})">⏭ Let it lose</button>';
  }
  if (b.phase === 'lobby' || b.phase === 'round_end' || b.phase === 'chapter_end' || b.phase === 'game_end') {
    actions += '<button class="primary hidden" id="ftrJoinBtn">🙋 Join</button>';
  }
  document.getElementById('ftrActions').innerHTML = actions;

  let handHtml = '';
  if (myIdx != null && (b.players[myIdx] || {}).hand && b.players[myIdx].hand.length) {
    let hand = b.players[myIdx].hand;
    let legal = b.my_legal || [];
    let canPlay = isTurnMine && !(b.pending && b.pending.kind === 'ring_choice');
    let canExchangeOut = b.phase === 'setup' && b.pending && b.pending.kind === 'exchange_out' && isPendingMine && FTR.target != null;
    let canExchangeBack = b.phase === 'setup' && b.pending && b.pending.kind === 'exchange_in' && isPendingMine;
    handHtml = '<b>My hand (' + hand.length + ')</b><div class="pile">' + hand.map(c => {
      let clickable = (canPlay && legal.includes(c)) || canExchangeOut || canExchangeBack;
      let attr = clickable ? `onclick="ftrCardClick('${c}')"` : '';
      return ftrCard(c, !clickable, attr);
    }).join('') + '</div>';
  } else if (b.current_is_npc && (b.current_legal || []).length) {
    handHtml = '<div class="small">🤖 NPC legal cards (anyone may tap):</div><div class="pile">' +
      (b.current_legal || []).map(c => ftrCard(c, false, `onclick="ftrMove('play',{card:'${c}'})"`)).join('') + '</div>';
  } else if (b.pending_hand && b.pending_hand.length) {
    handHtml = '<div class="small">🤖 NPC exchange hand (anyone may tap):</div><div class="pile">' +
      b.pending_hand.map(c => ftrCard(c, false, `onclick="ftrNpcExchange('${c}')"`)).join('') + '</div>';
  }
  document.getElementById('ftrHand').innerHTML = handHtml;

  let show = (id, on) => { let e = document.getElementById(id); if (e) e.classList.toggle('hidden', !on); };
  show('ftrJoin', b.phase === 'lobby' && b.is_player === false);
  show('ftrStart', b.phase === 'lobby' && b.is_player);
  show('ftrRingYes', b.phase === 'playing' && b.pending && b.pending.kind === 'ring_choice' && isPendingMine);
  show('ftrRingNo', b.phase === 'playing' && b.pending && b.pending.kind === 'ring_choice' && isPendingMine);
  show('ftrRetry', b.phase === 'round_end' || b.phase === 'chapter_end');
  show('ftrRestart', b.phase === 'round_end' || b.phase === 'chapter_end');
  show('ftrNext', b.phase === 'chapter_end');
}
window.ftrTarget = function (t) { FTR.target = t; ftrRender(); };
window.ftrShowArt = function (key) {
  let box = document.getElementById('ftrLightbox');
  let card = document.getElementById('ftrLightboxCard');
  if (!box || !card) return;
  card.innerHTML = ftrChar(key, 'full');
  box.classList.remove('hidden');
};
window.ftrCloseArt = function () {
  let box = document.getElementById('ftrLightbox');
  if (box) box.classList.add('hidden');
};
window.ftrMove = ftrMove;
window.ftrCardClick = function (c) {
  let b = FTR.board;
  if (!b) return;
  if (b.phase === 'setup' && b.pending && b.pending.kind === 'exchange_out') {
    ftrMove('out', {card: c, target: FTR.target});
  } else if (b.phase === 'setup' && b.pending && b.pending.kind === 'exchange_in') {
    ftrMove('back', {card: c});
  } else if (b.phase === 'playing') {
    ftrMove('play', {card: c});
  }
};
window.ftrNpcExchange = function (c) {
  let b = FTR.board;
  if (!b || !b.pending) return;
  if (b.pending.kind === 'exchange_out') ftrMove('out', {card: c, target: FTR.target != null ? FTR.target : b.pending.targets[0]});
  else if (b.pending.kind === 'exchange_in') ftrMove('back', {card: c});
};
document.getElementById('ftrJoin').addEventListener('click', () => ftrMove('join'));
document.getElementById('ftrStart').addEventListener('click', () => ftrMove('start'));
document.getElementById('ftrRingYes').addEventListener('click', () => ftrMove('ring', {use: true}));
document.getElementById('ftrRingNo').addEventListener('click', () => ftrMove('ring', {use: false}));
document.getElementById('ftrRetry').addEventListener('click', () => ftrMove('retry'));
document.getElementById('ftrRestart').addEventListener('click', () => ftrMove('restart'));
document.getElementById('ftrNext').addEventListener('click', () => ftrMove('next'));
if (!document.getElementById('fellowship').classList.contains('hidden')) ftrLoad();
