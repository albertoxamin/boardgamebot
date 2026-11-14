// Tornado Splash Mini App (synced, initData auto-login). Loaded by flip7.html router.
const TSV={user_id:0,chat_id:null,board:null,timer:null,init:'',sel:new Set(),boost:false,prevKey:''};
function tsLog(s){let e=document.getElementById('tsLog');if(e)e.textContent+=s+'\n';}
function tsApi(path,opts){return fetch(path,opts).then(r=>r.json());}
// The scanned running-card faces have no printed values, so this mapping of the
// engine's four card types onto four of the five faces is arbitrary (and the
// printed value is shown as a badge on top of the art).
const TS_CARD_ART={s1:'running_1_wide.png',s2:'running_2_wide.png',c1:'running_3_wide.png',c2:'running_4_wide.png'};
function tsCard(c){
 let key=(c.kind==='c'?'c':'s')+c.spaces;
 let src='tornado_cards/'+(TS_CARD_ART[key]||'running_5_wide.png');
 return '<img src="'+src+'" alt=""><span class="tscardbadge">'+(c.kind==='c'?'🌊':'➡️')+c.spaces+'</span>';
}
function tsBoatStars(n){let s='';for(let i=0;i<n;i++)s+='⭐';return s;}
async function tsLoad(){
 let tg=tgInit();
 if(!tg.id){document.getElementById('tsBoard').innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot\'s Tornado Splash link.</div>';return;}
 TSV.user_id=tg.id; TSV.init=tg.init;
 let r=await tsApi('/api/tornado/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 let pref=parseInt(tg.start,10)||0; if(!pref && tg.chat_instance) pref=parseInt(tg.chat_instance,10)||0;
 if(tg.start && String(tg.start).startsWith('tornado')) pref=parseInt(String(tg.start).slice(7),10)||pref;
 let pick=mine.find(g=>g.chat_id===pref);
 if(!pick && pref){let spec=await tsApi('/api/tornado/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
  if(spec.ok) pick={chat_id:pref};}
 if(!pick) pick=mine.find(g=>g.phase!=='game_end'&&g.phase!=='race_end') || mine[0];
 if(pick) tsSelect(pick.chat_id);
 else if(pref){let cr=await tsApi('/api/tornado/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});
  if(cr.game) tsSelect(cr.game.chat_id); else tsLog('⛔ '+(cr.error||'create failed'));}
 else document.getElementById('tsBoard').innerHTML='<div class="table lobby-note">No Tornado Splash game for you yet — send /tornado in a chat, then open its Mini App link.</div>';
}
async function tsSelect(chat_id){TSV.chat_id=chat_id; await tsRefresh();
 if(TSV.timer)clearInterval(TSV.timer); TSV.timer=setInterval(tsRefresh,3000);}
async function tsRefresh(){ if(!TSV.chat_id)return;
 let r=await tsApi('/api/tornado/game?chat_id='+encodeURIComponent(TSV.chat_id)+'&init_data='+encodeURIComponent(TSV.init));
 if(r.ok){TSV.board=r.game; tsCleanSel(); tsRender();}}
async function tsMove(action,extra){
 let body=Object.assign({chat_id:TSV.chat_id,action:action,init_data:TSV.init},extra||{});
 let r=await tsApi('/api/tornado/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.events)r.events.forEach(e=>tsLog(e)); if(r.error)tsLog('⛔ '+r.error);
 if(r.game){TSV.board=r.game; TSV.sel=new Set(); tsCleanSel(); tsRender();}}
function tsCleanSel(){
 let b=TSV.board; if(!b)return;
 let n=(b.my_hand||[]).length;
 [...TSV.sel].forEach(i=>{if(i<0||i>=n)TSV.sel.delete(i);});
 if(!b.my_boost_available)TSV.boost=false;
}
function tsMyTurn(b){
 let cur=b.current_index!=null?b.players[b.current_index]:null;
 return b.phase==='playing'&&cur&&(cur.user_id===TSV.user_id||cur.npc);
}
function tsRender(){
 let b=TSV.board; if(!b)return;
 let me=b.my_index!=null?b.players[b.my_index]:null;
 let cur=b.current_index!=null?b.players[b.current_index]:null;
 let myTurn=tsMyTurn(b);
 let sel=[...TSV.sel];
 let total=sel.reduce((a,i)=>a+((b.my_hand[i]||{}).spaces||0),0);
 let cap=(b.my_max_move||3)+(TSV.boost?1:0);
 let spect=b.is_player===false;
 let specBar=spect?'<div class="lobby-note">👁 Spectating — view only (join in Telegram to play)</div>':'';
 // ---- turn line ----
 let turn=document.getElementById('tsTurn');
 if(b.phase==='lobby') turn.textContent='🪑 Lobby — '+b.players.length+'/'+b.max_players+' racers';
 else if(b.phase==='picking'){
  let picker=b.picker_index!=null?b.players[b.picking_order[b.picker_index]]:null;
  turn.textContent='🛥️ '+(picker?picker.name+' is picking a boat':'Boat selection');
 } else if(b.phase==='playing'){
  turn.textContent=(myTurn?'👉 Your turn':'👉 '+(cur?cur.name:'?')+"'s turn")
   +' · round '+b.round+(b.gp?' · race '+b.race_number+'/'+b.total_races:'');
 } else if(b.phase==='race_end'){
  turn.textContent=b.gp?'🏁 Race '+b.race_number+' done':'🏁 Race over!';
 } else if(b.phase==='game_end'){
  let wn=(b.winners||[]).map(u=>{let p=b.players.find(x=>x.user_id===u);return p?p.name:'?';}).join(' & ');
  turn.textContent='🏆 Grand Prix over — '+wn;
 } else turn.textContent='';
 // ---- track + racers ----
 let order=b.phase==='playing'?b.rank_order:b.players.map((_,i)=>i);
 let rows=order.map(i=>{
  let p=b.players[i];
  let pct=Math.min(100,Math.round(100*p.pos/b.course.length));
  let cps=b.course.checkpoints.map(cp=>'<span class="tscp" style="left:'+Math.round(100*cp.space/b.course.length)+'%"></span>').join('');
  let cls='tsracer'+(i===b.current_index&&b.phase==='playing'?' current':'')+(i===b.my_index?' me':'');
  let right=(p.finished?'🏁 '+p.finish_rank+'/'+b.players.length:'')+(b.gp?' · '+p.points+' pts':'')+' · 🃏'+p.hand_count;
  return '<div class="'+cls+'"><div class="tsrhead"><span>'+escapeHtml(p.name)+(p.npc?' 🤖':'')+(p.boost_used?'':' ⚡')+'</span><span>'+right+'</span></div>'
   +'<div class="tstrack"><div class="tsfill" style="width:'+pct+'%"></div>'+cps+'</div>'
   +'<div class="small">'+(p.boat_name||'no boat yet')+' · space '+p.pos+'/'+b.course.length+' · checkpoints '+b.course.checkpoints.map(c=>c.space+c.dir[0]).join(' ')+'</div></div>';
 }).join('');
 let head='<div class="tsbar"><b>🌊 '+escapeHtml(b.course.name)+'</b> <span class="small">'+b.course.length+' spaces</span></div>';
 document.getElementById('tsBoard').innerHTML=specBar+head+rows;
 // ---- hand ----
 let handHtml='';
 if(b.phase==='playing'&&me){
  handHtml='<div class="tshand">'+(b.my_hand.length?b.my_hand.map((c,i)=>
   '<div class="tscard'+(TSV.sel.has(i)?' sel':'')+'" data-i="'+i+'">'+tsCard(c)+'</div>').join(''):'<span class="small">Empty hand</span>')+'</div>'
   +'<div class="small" style="text-align:center">Selected '+total+' / max '+cap+' spaces'+(TSV.boost?' · ⚡ boost':'')+' · tap cards to choose</div>';
 }
 document.getElementById('tsHand').innerHTML=handHtml;
 // ---- boat picker ----
 let pickHtml='';
 if(b.phase==='picking'){
  let taken=new Set(b.players.filter(p=>p.boat!=null).map(p=>p.boat));
  let picker=b.picker_index!=null?b.players[b.picking_order[b.picker_index]]:null;
  let canPick=me&&picker&&(picker.user_id===TSV.user_id||picker.npc);
  pickHtml='<div class="tsboats">'+b.boats.map(x=>{
   let dis=taken.has(x.index)||!canPick;
   return '<button class="tsboat'+(taken.has(x.index)?' taken':'')+'" data-boat="'+x.index+'"'+(dis?' disabled':'')+'>'
    +'<img class="tsboatimg" src="tornado_cards/number_'+(x.index+1)+'.png" alt="">'
    +x.name
    +'<span class="small">'+tsBoatStars(x.speed)+'/'+tsBoatStars(x.handling)+'</span><span class="small">weight '+x.weight+'</span></button>';
  }).join('')+'</div>';
 }
 document.getElementById('tsActions').innerHTML=pickHtml;
 // ---- buttons ----
 let $=id=>document.getElementById(id);
 $('tsJoin').classList.toggle('hidden',!(b.phase==='lobby'&&!b.is_player));
 $('tsStart').classList.toggle('hidden',!(b.phase==='lobby'&&b.is_player&&b.players.length>=2));
 $('tsGp').classList.toggle('hidden',!(b.phase==='lobby'&&b.is_player&&b.players.length>=2));
 $('tsAuto').classList.toggle('hidden',!(b.phase==='picking'&&b.is_player));
 $('tsPlay').classList.toggle('hidden',!(myTurn&&b.is_player));
 $('tsPlay').disabled=!(sel.length>0&&sel.length<=cap&&total>0&&total<=cap);
 $('tsPlay').textContent='🛥️ Play '+sel.length+' card'+(sel.length===1?'':'s')+' ('+total+')';
 $('tsBoost').classList.toggle('hidden',!(myTurn&&b.is_player&&b.my_boost_available));
 $('tsBoost').textContent=TSV.boost?'⚡ Boost ON':'⚡ Boost';
 $('tsWait').classList.toggle('hidden',!(myTurn&&b.is_player));
 $('tsDiscard').classList.toggle('hidden',!(myTurn&&b.is_player&&sel.length>0));
 $('tsDiscard').textContent='🗑 Discard '+sel.length+' & wait';
 $('tsNext').classList.toggle('hidden',!(b.phase==='race_end'&&b.gp&&b.is_player));
 $('tsRematch').classList.toggle('hidden',!((b.phase==='game_end'||(b.phase==='race_end'&&!b.gp))&&b.is_player));
 // ---- taps ----
 if(myTurn&&me){
  document.querySelectorAll('#tsHand .tscard').forEach(el=>el.addEventListener('click',()=>{
   let i=parseInt(el.dataset.i); if(TSV.sel.has(i))TSV.sel.delete(i); else TSV.sel.add(i); tsRender();}));
 }
 if(b.phase==='picking'){
  document.querySelectorAll('#tsActions .tsboat').forEach(el=>el.addEventListener('click',()=>{
   if(el.disabled)return; tsMove('pick',{boat:parseInt(el.dataset.boat)});}));
 }
}
document.getElementById('tsJoin').addEventListener('click',()=>tsMove('join'));
document.getElementById('tsStart').addEventListener('click',()=>tsMove('start',{gp:false}));
document.getElementById('tsGp').addEventListener('click',()=>tsMove('start',{gp:true}));
document.getElementById('tsAuto').addEventListener('click',()=>tsMove('auto'));
document.getElementById('tsPlay').addEventListener('click',()=>tsMove('play',{cards:[...TSV.sel],boost:TSV.boost}));
document.getElementById('tsBoost').addEventListener('click',()=>{TSV.boost=!TSV.boost; tsRender();});
document.getElementById('tsWait').addEventListener('click',()=>tsMove('wait'));
document.getElementById('tsDiscard').addEventListener('click',()=>tsMove('wait',{discard:[...TSV.sel]}));
document.getElementById('tsNext').addEventListener('click',()=>tsMove('next'));
document.getElementById('tsRematch').addEventListener('click',()=>tsMove('rematch'));
// Self-start when router (flip7.js) selected Tornado Splash mode.
if(!document.getElementById('tornado').classList.contains('hidden')) tsLoad();
