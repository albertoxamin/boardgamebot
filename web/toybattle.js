const TBG = {user_id: 0, chat_id: null, board: null, timer: null, init: '', selected: null};
const TB_HOW_TO_PLAY_URL = 'https://www.youtube.com/watch?v=O2HjOQUFAio';

function tbLog(s) {
  const e = document.getElementById('tbLog');
  if (e) e.textContent += s + '\n';
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
  return '<span class="tbtile ' + (extraClass || '') + '" style="background-position:' +
         (col / 11 * 100) + '% ' + row + '%" title="' + escapeHtml(TBG.board.troop_names[type] || type) +
         '"></span>';
}
function tbBase(b, data, g) {
  const top = data.top;
  const legal = g.legal && Object.values(g.legal).some(list => list.map(String).includes(String(b)));
  const cls = 'tbbase' + (legal ? ' tblegal' : '') + (data.special ? ' tbspecial' : '');
  let inner = '';
  if (top) inner = tbTile(top.type, top.owner, 'tbonboard') +
    (data.height > 1 ? '<span class="tbheight">' + data.height + '</span>' : '');
  else inner = '<span class="tbemptybase">' + (data.special ? '★' : '') + '</span>';
  if (String(b) === '1' || String(b) === '41') inner += '<span class="tbhq">HQ</span>';
  const sel = TBG.selected !== null && String(g.legal && Object.keys(g.legal).find(k => (g.legal[k] || []).map(String).includes(String(b))) || '-1') === String(TBG.selected) ? ' tbselected' : '';
  return '<div class="' + cls + sel + '" style="top:' + data.top_pos + '%;left:' + data.left_pos +
         '%" data-base="' + b + '" title="Base ' + b + '">' + inner + '</div>';
}
function tbMedal(m, data) {
  const owner = data.owner;
  const bg = owner === null || owner === undefined ? 'background-position:100% 0;opacity:.45' :
             'background-position:' + (Number(owner) === 0 ? '0' : '100%') + ' 0';
  return '<span class="tbmedal" style="top:' + data.top + '%;left:' + data.left + '%;' + bg +
         '" title="Medal ' + m + ': ' + (owner === null ? 'unclaimed' : escapeHtml((TBG.board.players[owner] || {}).name || '')) + '"></span>';
}
function tbRack(p, me, g, idx) {
  const tiles = [];
  const n = Math.max(8, p.rack_count);
  for (let i = 0; i < n; i++) {
    const type = p.rack[i];
    const can = me && g.can_act && !g.pending && (g.legal[String(i)] || []).length;
    if (type === undefined) tiles.push('<span class="tback"></span>');
    else if (can) tiles.push('<button type="button" class="track" data-index="' + i + '" title="' +
      escapeHtml(g.troop_names[type] || type) + '">' + tbTile(type, idx) + '</button>');
    else tiles.push('<span class="track">' + (type === undefined ? '' :
      (me ? tbTile(type, idx) : '<span class="tback"></span>')) + '</span>');
  }
  return tiles.join('');
}
function tbRender() {
  const g = TBG.board;
  if (!g) return;
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
  const names = g.players.map(p => escapeHtml(p.name) + (p.npc ? ' 🤖' : '') +
    ' <b class="tb' + (p.color === 'red' ? 'red' : 'blue') + '">' + p.medals + '/' + g.medal_target + ' 🏅</b>').join(' vs ');
  turn.innerHTML = g.phase === 'lobby' ? '🎯 Toy Battle lobby — ' + g.players.length + '/2 · ' + names :
                   g.phase === 'game_end' ? '🏆 ' + (g.winner === null ? 'Draw' :
                     escapeHtml((g.players[g.winner] || {}).name || 'Winner')) + ' wins! · ' + names :
                   '🎯 Turn ' + g.turn + ' · ' + names + (g.can_act ? ' · <b>your move</b>' : '');
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
      html += '<div class="tbackrow' + (p.is_current ? ' tbcurrent' : '') + '">' +
              '<div class="tbhead">' + (i === 0 ? '🔵 ' : '🔴 ') + escapeHtml(p.name) +
              (p.npc ? ' 🤖' : '') + ' · 🎒' + p.rack_count + ' · 📦' + p.reserve +
              ' · 🗑' + p.discard + '</div><div class="tbrack">' + tbRack(p, p.user_id === TBG.user_id, g, i) + '</div></div>';
    });
    html += '</div>';
    board.innerHTML = html;
    board.querySelectorAll('[data-index]').forEach(el => el.addEventListener('click', () => {
      TBG.selected = Number(el.dataset.index); tbRender();
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
      draw.classList.remove('hidden');
      if (TBG.selected !== null && (g.legal[String(TBG.selected)] || []).length) {
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
