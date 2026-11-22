// Leaves Mini App (synced). Loaded by flip7.html router.
const LV={user_id:0,chat_id:null,board:null,timer:null,init:'',sel:null};
const LV_COLS=7, LV_ROWS=2;
const LV_TILE_W=330, LV_TILE_H=518;
function lvLog(s){let e=document.getElementById('lvLog');if(e)e.textContent+=s+'\n';}
function lvCardBg(val, big){
  let w=big?80:56, h=big?126:88;
  let scaleX=w/LV_TILE_W, scaleY=h/LV_TILE_H;
  let bgW=LV_COLS*LV_TILE_W*scaleX, bgH=LV_ROWS*LV_TILE_H*scaleY;
  let col, row;
  if(val==='back'){ row=1; col=6; }
  else {
    let v=parseInt(val);
    if(v>=1&&v<=7){ row=0; col=v-1; }
    else if(v>=8&&v<=13){ row=1; col=v-8; }
    else { row=1; col=6; }
  }
  let px=-(col*LV_TILE_W*scaleX), py=-(row*LV_TILE_H*scaleY);
  return {style:`width:${w}px;height:${h}px;background-image:url(13leaves.png);background-size:${bgW}px ${bgH}px;background-position:${px}px ${py}px;border-radius:6px;box-shadow:1px 2px 3px #0008;flex:none;cursor:pointer`};
}
function lvCardEl(val, selected, big){
  let b=lvCardBg(val,big);
  let cls='lvcard'+(selected?' sel':'')+(big?' big':'');
  return `<div class="${cls}" title="${val}" style="${b.style}"></div>`;
}
function lvApi(path,opts){return fetch(path,opts).then(r=>r.json());}
function tgInit(){const tg=window.Telegram&&window.Telegram.WebApp; if(tg)tg.ready(); const p=new URLSearchParams(location.search); return {id:tg&&tg.initDataUnsafe&&tg.initDataUnsafe.user?tg.initDataUnsafe.user.id:0,init:tg&&tg.initData?tg.initData:'',start:(p.get('tgWebAppStartParam')||''),chat_instance:(tg&&tg.initDataUnsafe?String(tg.initDataUnsafe.chat_instance||''):''),tg:tg};}
function escapeHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
async function lvLoad(){
  let tg=tgInit();
  if(!tg.id){document.getElementById('lvBoard').innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot link.</div>';return;}
  LV.user_id=tg.id; LV.init=tg.init;
  let r=await lvApi('/api/leaves/mygames?init_data='+encodeURIComponent(tg.init));
  let mine=r.games||[];
  let pref=parseInt(tg.start,10)||0;
  if(!pref && tg.chat_instance) pref=parseInt(tg.chat_instance,10)||0;
  let pick=mine.find(g=>g.chat_id===pref)||mine.find(g=>g.phase!=='game_end')||mine[0];
  if(pick) lvSelect(pick.chat_id);
  else if(pref){let cr=await lvApi('/api/leaves/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})}); if(cr.game) lvSelect(cr.game.chat_id); else lvLog('⛔ '+(cr.error||'create failed'));}
  else document.getElementById('lvBoard').innerHTML='<div class="table lobby-note">No Leaves game for you yet — send /leaves in a chat.</div>';
}
async function lvSelect(chat_id){LV.chat_id=chat_id; await lvRefresh(); if(LV.timer)clearInterval(LV.timer); LV.timer=setInterval(lvRefresh,3000);}
async function lvRefresh(){if(!LV.chat_id)return; let r=await lvApi('/api/leaves/game?chat_id='+encodeURIComponent(LV.chat_id)+'&init_data='+encodeURIComponent(LV.init)); if(r.ok){LV.board=r.game; lvRender();}}
async function lvMove(action,extra){
  let body=Object.assign({chat_id:LV.chat_id,action:action,init_data:LV.init},extra||{});
  let r=await lvApi('/api/leaves/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r.events)r.events.forEach(e=>lvLog(e)); if(r.error)lvLog('⛔ '+r.error);
  if(r.game){LV.board=r.game; LV.sel=null; lvRender();}
}
function lvRender(){
  let b=LV.board; if(!b)return;
  let isMyTurn = b.phase==='playing' && b.current_index>=0 && b.players[b.current_index] && (b.players[b.current_index].user_id===LV.user_id || b.players[b.current_index].npc);
  // row
  let rowHtml = (b.row&&b.row.length) ? '<div class="lvrow">'+b.row.map((s,i)=>`<div style="display:inline-block;text-align:center;margin:2px;cursor:pointer" onclick="lvPassFrom(${i})" title="Tap to pass taking from this stack (pos ${i+1})">${lvCardEl(s.value,true)}<div class="small">×${s.count}<br>#${i+1}</div></div>`).join('')+'</div>' : '<div class="small">Row empty — lead any set</div>';
  // players
  let seats = '<div class="seats reg-row">'+(b.players||[]).map((p,i)=>{
    let turn=(b.phase==='playing'&&i===b.current_index)?' current':'';
    let passed=(b.passed_ids||[]).includes(p.user_id)?' (passed)':'';
    return `<div class="seat${turn}"><div class="seat-head"><span>${escapeHtml(p.name)}${passed}</span><span class="score">${p.hand_count}</span></div></div>`;
  }).join('')+'</div>';
  document.getElementById('lvBoard').innerHTML = '<div class="table"><div class="small">Row (tap a stack to pass taking from it)</div>'+rowHtml+seats+'</div>';
  // my hand
  let hand=b.my_hand||[];
  let mh=document.getElementById('lvHand');
  if(!b.is_player){ mh.innerHTML='<div class="small">👁 Spectating</div>'; }
  else {
    mh.innerHTML='<b>My hand ('+hand.length+')</b><div class="pile">'+hand.map(v=>`<div onclick="lvPick(${v})">${lvCardEl(v,false)}</div>`).join('')+'</div>';
  }
  let t=document.getElementById('lvTurn');
  if(b.phase==='lobby') t.textContent='🪑 Lobby — tap Start';
  else if(b.phase==='playing') t.textContent=isMyTurn?('👉 Your turn (tap a card, set count, Play). Or tap a row stack to Pass taking it. Sel: '+(LV.sel?LV.sel:'none')):('👉 '+(b.players[b.current_index]?b.players[b.current_index].name:'?')+"'s turn");
  else if(b.phase==='game_end') t.textContent='🏆 Winner: '+(b.winner_name||'?');
  else t.textContent='';
  document.getElementById('lvStart').classList.toggle('hidden',!(b.phase==='lobby'&&b.is_player));
  document.getElementById('lvPlay').classList.toggle('hidden',!(isMyTurn&&b.phase==='playing'));
  document.getElementById('lvPass').classList.toggle('hidden',!(isMyTurn&&b.phase==='playing'&&b.row&&b.row.length>0));
}
window.lvPick=function(v){ LV.sel=v; lvRender(); };
window.lvPassFrom=function(i){ lvMove('pass',{take_index:i}); };
document.getElementById('lvPlay').addEventListener('click',()=>{
  if(!LV.sel){lvLog('tap a card in your hand first');return;}
  let countStr = prompt('How many of '+LV.sel+' to play? (1..n)');
  if(!countStr)return; let count=parseInt(countStr); if(!count||count<1){lvLog('bad count');return;}
  lvMove('play',{value:LV.sel,count:count});
});
document.getElementById('lvPass').addEventListener('click',()=>{ if(!confirm('Pass and take from leftmost stack (pos 1)?')) return; lvMove('pass',{take_index:0}); });
document.getElementById('lvStart').addEventListener('click',()=>lvMove('start'));
if(!document.getElementById('leaves').classList.contains('hidden')) lvLoad();
