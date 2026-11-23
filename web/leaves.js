// Leaves Mini App (synced). Loaded by flip7.html router.
const LV={user_id:0,chat_id:null,board:null,timer:null,init:'',sel:[]};
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
function lvCardEl(val, selected, big, disabled, top){
  let b=lvCardBg(val,big);
  let cls='lvcard'+(selected?' sel':'')+(big?' big':'')+(disabled?' dim':'');
  let stack=top==null?'':`position:absolute;left:0;top:${top}px;z-index:${top+1};`;
  return `<div class="${cls}" title="${val}" style="${stack}${b.style}"></div>`;
}
function lvRowStack(s,i){
  let count=Math.max(1,Math.min(3,parseInt(s.count,10)||1));
  let extra=(parseInt(s.count,10)||1)-count;
  let offset=22, height=88+(count-1)*offset, cards='';
  for(let k=0;k<count;k++) cards+=lvCardEl(s.value,false,false,false,k*offset);
  return `<div class="lvrow-item" onclick="lvPassFrom(${i})" title="Tap to pass taking from this stack (pos ${i+1})">`+
    `<div class="lvstack" style="width:56px;height:${height}px">${cards}</div>`+
    `<div class="small">×${s.count}<br>#${i+1}${extra>0?'<br>+'+extra:''}</div></div>`;
}
function lvChatId(raw){let s=String(raw||'');if(s.startsWith('leaves'))s=s.slice(6);
 let n=parseInt(s,10);return isNaN(n)?0:n;}
function lvApi(path,opts){return fetch(path,opts).then(r=>r.json());}
function tgInit(){const tg=window.Telegram&&window.Telegram.WebApp; if(tg)tg.ready(); const p=new URLSearchParams(location.search); let init=tg&&tg.initData?tg.initData:''; let start=p.get('app')||p.get('tgWebAppStartParam')||''; try{let q=new URLSearchParams(init); start=start||q.get('start_param')||'';}catch(e){} return {id:tg&&tg.initDataUnsafe&&tg.initDataUnsafe.user?tg.initDataUnsafe.user.id:0,init:init,start:start,chat_instance:(tg&&tg.initDataUnsafe?String(tg.initDataUnsafe.chat_instance||''):''),tg:tg};}
function escapeHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
async function lvLoad(){
  let tg=tgInit();
  if(!tg.id){document.getElementById('lvBoard').innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot link.</div>';return;}
  LV.user_id=tg.id; LV.init=tg.init;
  let qp=new URLSearchParams(location.search);
  let pref=lvChatId(tg.start)||lvChatId(qp.get('app'))||parseInt(qp.get('chat_id'),10)||0;
  if(!pref && tg.chat_instance) pref=parseInt(tg.chat_instance,10)||0;
  let r=await lvApi('/api/leaves/mygames?init_data='+encodeURIComponent(tg.init));
  let mine=r.games||[];
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
  if(r.game){LV.board=r.game; LV.sel=[]; lvRender();}
}
function lvRender(){
  let b=LV.board; if(!b)return;
  let isMyTurn = b.phase==='playing' && b.current_index>=0 && b.players[b.current_index] && (b.players[b.current_index].user_id===LV.user_id || b.players[b.current_index].npc);
  // row
  let rowHtml = (b.row&&b.row.length) ? '<div class="lvrow">'+b.row.map(lvRowStack).join('')+'</div>' : '<div class="small">Row empty — lead any set</div>';
  // players
  let seats = '<div class="seats reg-row">'+(b.players||[]).map((p,i)=>{
    let turn=(b.phase==='playing'&&i===b.current_index)?' current':'';
    let passed=(b.passed_ids||[]).includes(p.user_id)?' (passed)':'';
    return `<div class="seat${turn}"><div class="seat-head"><span>${escapeHtml(p.name)}${passed}</span><span class="score">${p.hand_count}</span></div></div>`;
  }).join('')+'</div>';
  document.getElementById('lvBoard').innerHTML = '<div class="table"><div class="small">Row (tap a stack to pass taking from it)</div>'+rowHtml+seats+'</div>';
  // my hand
  let hand=b.my_hand||[];
  let picked=LV.sel.length?hand[LV.sel[0]]:null;
  let mh=document.getElementById('lvHand');
  if(!b.is_player){ mh.innerHTML='<div class="small">👁 Spectating</div>'; }
  else {
    let hint=picked===null?'tap cards to select':'only '+picked+' can be selected — deselect to choose another value';
    mh.innerHTML='<b>My hand ('+hand.length+') — '+hint+'</b><div class="pile">'+hand.map((v,i)=>{
      let selected=LV.sel.includes(i);
      let disabled=picked!==null&&v!==picked&&!selected;
      return `<div onclick="${disabled?'':'lvPick('+i+')'}">${lvCardEl(v,selected,false,disabled)}</div>`;
    }).join('')+'</div>';
  }
  let selText=LV.sel.length?(LV.sel.map(i=>hand[i]).join(',')+' selected'):'none';
  let t=document.getElementById('lvTurn');
  if(b.phase==='lobby') t.textContent='🪑 Lobby — tap Start';
  else if(b.phase==='playing') t.textContent=isMyTurn?('👉 Your turn (tap the cards you want to play, then Play). Tap a row stack to Pass. Sel: '+selText):('👉 '+(b.players[b.current_index]?b.players[b.current_index].name:'?')+"'s turn");
  else if(b.phase==='game_end') t.textContent='🏆 Winner: '+(b.winner_name||'?');
  else t.textContent='';
  document.getElementById('lvStart').classList.toggle('hidden',!(b.phase==='lobby'&&b.is_player));
  document.getElementById('lvPlay').classList.toggle('hidden',!(isMyTurn&&b.phase==='playing'));
  document.getElementById('lvPass').classList.toggle('hidden',!(isMyTurn&&b.phase==='playing'&&b.row&&b.row.length>0));
}
window.lvPick=function(i){
  let hand=(LV.board&&LV.board.my_hand)||[];
  if(i<0||i>=hand.length)return;
  let at=LV.sel.indexOf(i);
  if(at>=0){LV.sel.splice(at,1);lvRender();return;}
  if(LV.sel.length&&hand[LV.sel[0]]!==hand[i]){lvLog('one card value at a time — deselect first');return;}
  LV.sel.push(i);
  lvRender();
};
window.lvPassFrom=function(i){ lvMove('pass',{take_index:i}); };
document.getElementById('lvPlay').addEventListener('click',()=>{
  let hand=(LV.board&&LV.board.my_hand)||[];
  if(!LV.sel.length){lvLog('tap the cards you want to play first');return;}
  let values=LV.sel.map(i=>hand[i]);
  if(values.some(v=>v===undefined)){LV.sel=[];lvRender();lvLog('selection expired; tap cards again');return;}
  let value=values[0];
  if(values.some(v=>v!==value)){lvLog('select cards of the same value only');return;}
  lvMove('play',{value:value,count:values.length});
});
document.getElementById('lvPass').addEventListener('click',()=>{ if(!confirm('Pass and take from leftmost stack (pos 1)?')) return; lvMove('pass',{take_index:0}); });
document.getElementById('lvStart').addEventListener('click',()=>lvMove('start'));
if(!document.getElementById('leaves').classList.contains('hidden')) lvLoad();
