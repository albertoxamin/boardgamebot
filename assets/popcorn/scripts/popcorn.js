const PC={chat_id:null,init:'',board:null,timer:null};
const PC_HOW_TO_PLAY_URL='https://www.youtube.com/watch?v=XxEKn0NgP8E';

function pcLog(s){const e=document.getElementById('pcLog');if(e)e.textContent+=s+'\n';}
function pcApi(path,opts){return fetch(path,opts).then(r=>r.json());}
function pcChatId(raw){let s=String(raw||'');if(s.startsWith('popcorn'))s=s.slice(7);const n=parseInt(s,10);return isNaN(n)?0:n;}
async function pcLoad(){
 const tg=tgInit();
 if(!tg.id){document.getElementById('pcTurn').textContent='Open as Telegram Mini App via the bot link.';return;}
 PC.init=tg.init;
 const qp=new URLSearchParams(location.search);
 const pref=pcChatId(tg.start)||pcChatId(qp.get('app'))||parseInt(qp.get('chat_id'),10)||pcChatId(tg.chat_instance);
 let r;
 try{r=await pcApi('/api/popcorn/mygames?init_data='+encodeURIComponent(tg.init));}
 catch(e){pcLoadFail('mygames');return;}
 const mine=r.games||[];
 const pick=mine.find(g=>g.chat_id===pref)||mine.find(g=>g.phase!=='game_end')||mine[0];
 // FB-0166: pick.chat_id must exist (the board JSON carries it since the
 // server fix); fall back to pref so a missing id can never silently
 // select an undefined game and leave a blank board.
 if(pick)pcSelect(pick.chat_id||pref);
 else if(pref){
  let cr;
  try{cr=await pcApi('/api/popcorn/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});}
  catch(e){pcLoadFail('create');return;}
  if(cr.game)pcSelect(cr.game.chat_id||pref);else pcLog('⛔ '+(cr.error||'create failed'));
 }else document.getElementById('pcTurn').textContent='No Popcorn game yet — send /popcorn in a chat.';
}
function pcLoadFail(what){
 // FB-0165: a failed first load used to die silently and leave a blank
 // board. Say so on the board and retry — a transient server/tunnel
 // hiccup must not look like a dead Mini App.
 document.getElementById('pcTurn').textContent='⚠️ Couldn\'t load the Popcorn game — retrying…';
 pcLog('⛔ load failed ('+what+'), retrying in 5s');
 if(PC.retry)clearTimeout(PC.retry);
 PC.retry=setTimeout(pcLoad,5000);
}
async function pcSelect(chat_id){
 // FB-0166: without a chat id the refresh below used to ask the server
 // for chat_id=undefined, get no game and render nothing — silently.
 // Say so instead of installing a timer that can never show a board.
 if(!chat_id){document.getElementById('pcTurn').textContent='⚠️ Couldn\'t open the Popcorn game — reopen it from the chat.';return;}
 PC.chat_id=chat_id;
 // Install the refresh timer before the first refresh, so a failed first
 // load keeps retrying instead of dying silently with a blank board.
 if(PC.timer)clearInterval(PC.timer);PC.timer=setInterval(pcRefresh,3000);
 await pcRefresh();
}
async function pcRefresh(){
 if(!PC.chat_id)return;
 const q='?chat_id='+encodeURIComponent(PC.chat_id)+'&init_data='+encodeURIComponent(PC.init);
 let r;
 try{r=await pcApi('/api/popcorn/game'+q);}
 catch(e){pcLoadFail('game');return;}
 if(r.game){PC.board=r.game;pcRender();}
 else pcLoadFail('game');
}
async function pcMove(action,extra){
 const body=Object.assign({chat_id:PC.chat_id,action:action,init_data:PC.init},extra||{});
 let r;
 try{r=await pcApi('/api/popcorn/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
 catch(e){pcLog('⛔ move failed — check your connection and try again');return;}
 if(r.events)r.events.forEach(e=>pcLog(e));
 if(r.error)pcLog('⛔ '+r.error);
 if(r.game){PC.board=r.game;pcRender();}
}
function pcColor(c){return ({red:'🔴',blue:'🔵',yellow:'🟡',green:'🟢',white:'⚪'}[c]||'·');}
function pcCard(c){
 const extra=(c.row==='premiers'?2:0),cost=(c.cost||0)+extra;
 return '<span class="pccard" style="border-color:'+({red:'#f87171',blue:'#60a5fa',yellow:'#facc15',green:'#4ade80'}[c.color]||'#94a3b8')+'" title="'+escapeHtml(c.title||'')+'">'+
  '<b>'+pcColor(c.color)+'</b> '+escapeHtml(c.title||'')+'<small>$'+cost+' · '+c.seats+'-seat</small></span>';
}
function pcTheater(t,i){
 const seats=(t.seats||[]).map(s=>'<span class="pcseat" style="color:'+(s.c==='gray'?'#94a3b8':'')+'">'+(s.guest?pcColor(s.guest):'·')+'</span>').join('');
 return '<div class="pctheater"><b>T'+(i+1)+'</b> '+t.size+' seats · '+escapeHtml(t.movie||'Empty')+' '+seats+'</div>';
}
function pcButton(label,fn){
 const b=document.createElement('button');b.type='button';b.className='primary';b.textContent=label;
 b.addEventListener('click',fn);return b;
}
function pcRender(){
 const g=PC.board;if(!g)return;
 const turn=document.getElementById('pcTurn'),market=document.getElementById('pcMarket'),
  players=document.getElementById('pcPlayers'),actions=document.getElementById('pcActions'),
  join=document.getElementById('pcJoin'),npc=document.getElementById('pcNpc'),
  start=document.getElementById('pcStart'),rematch=document.getElementById('pcRematch'),
  howto=document.getElementById('pcHowTo');
 [join,npc,start,rematch,howto].forEach(el=>el.classList.add('hidden'));
 actions.innerHTML='';
 document.getElementById('pcLog').textContent=(g.log||[]).join('\n');
 const names=g.players.map((p,i)=>escapeHtml(p.name)+' <b>'+p.popcorn+'🍿</b> $'+p.money+
  ' 📈'+p.audience+(i===g.actor?' · <b>turn</b>':'')).join(' · ');
 if(g.phase==='lobby')turn.innerHTML='🍿 Popcorn lobby — '+g.players.length+'/4 · '+names;
 else if(g.phase==='game_end')turn.innerHTML='🏆 '+escapeHtml((g.players[g.winner]||{}).name||'Winner')+' wins! · '+names;
 else turn.innerHTML='🍿 Round '+g.round+(g.final?' (FINAL)':'')+' · '+g.phase+' · '+names+(g.can_act?' · <b>your move</b>':'');
 market.innerHTML=g.phase==='lobby'?'':'<div class="pclabel">🎞️ Features</div>'+
  (g.market.features||[]).map(c=>pcCard(Object.assign({row:'features'},c))).join('')+
  '<div class="pclabel">🌟 Premiers (+$2)</div>'+
  (g.market.premiers||[]).map(c=>pcCard(Object.assign({row:'premiers'},c))).join('');
 players.innerHTML=g.phase==='lobby'?'':g.players.map(p=>
  '<div class="pcplayer"><b>'+escapeHtml(p.name)+'</b> · 🍿'+p.popcorn+' 💵'+p.money+
  ' 📈'+p.audience+' 🎟️'+p.bag_count+' 🚪'+p.exit.length+' 📣'+(p.ads_board||[]).length+
  ' 🏆'+(p.awards||[]).map(escapeHtml).join(', ')+
  '<div>'+(p.theaters||[]).map(pcTheater).join('')+'</div></div>').join('');
 if(g.phase==='lobby'){
  // Join is for non-players (a player is already in); showing it only to
  // players was inverted — same fix as Fadenfroh's Join button.
  if(!g.is_player)join.classList.remove('hidden');
  npc.classList.remove('hidden');start.classList.remove('hidden');howto.classList.remove('hidden');return;
 }
 if(g.phase==='game_end'){rematch.classList.remove('hidden');return;}
 if(!g.can_act)return;
 (g.options||[]).forEach(o=>actions.appendChild(pcButton(o.label,()=>pcMove('move',{code:o.code}))));
}
document.getElementById('pcJoin').addEventListener('click',()=>pcMove('join'));
document.getElementById('pcNpc').addEventListener('click',()=>pcMove('join_npc'));
document.getElementById('pcStart').addEventListener('click',()=>pcMove('start'));
document.getElementById('pcHowTo').addEventListener('click',()=>{
 try{
  if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.openLink)
   Telegram.WebApp.openLink(PC_HOW_TO_PLAY_URL);
  else window.open(PC_HOW_TO_PLAY_URL,'_blank');
 }catch(e){window.open(PC_HOW_TO_PLAY_URL,'_blank');}
});
document.getElementById('pcRematch').addEventListener('click',()=>pcMove('rematch'));
pcLoad();
