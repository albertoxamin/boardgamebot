// Fliptoons Mini App (synced, initData auto-login). Loaded by flip7.html router.
const FLP={user_id:0,chat_id:null,board:null,timer:null,init:''};
function ftLog(s){let e=document.getElementById('ftLog');if(e)e.textContent+=s+'\n';}
function ftApi(path,opts){return fetch(path,opts).then(r=>r.json());}
async function ftLoad(){
 let tg=tgInit();
 if(!tg.id){document.getElementById('ftBoard').innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot\'s Fliptoons link.</div>';return;}
 FLP.user_id=tg.id; FLP.init=tg.init;
 let r=await ftApi('/api/fliptoons/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 let pref=parseInt(tg.start,10)||0; if(!pref && tg.chat_instance) pref=parseInt(tg.chat_instance,10)||0;
 if(tg.start && String(tg.start).startsWith('fliptoons')) pref=parseInt(String(tg.start).slice(9),10)||pref;
 let pick=mine.find(g=>g.chat_id===pref);
 if(!pick && pref){let spec=await ftApi('/api/fliptoons/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
  if(spec.ok) pick={chat_id:pref};}
 if(!pick) pick=mine.find(g=>g.phase!=='game_end') || mine[0];
 if(pick) ftSelect(pick.chat_id);
 else if(pref){let cr=await ftApi('/api/fliptoons/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});
  if(cr.game) ftSelect(cr.game.chat_id); else ftLog('⛔ '+(cr.error||'create failed'));}
 else document.getElementById('ftBoard').innerHTML='<div class="table lobby-note">No Fliptoons game for you yet — send /fliptoons in a chat, then open its Mini App link.</div>';
}
async function ftSelect(chat_id){FLP.chat_id=chat_id; await ftRefresh();
 if(FLP.timer)clearInterval(FLP.timer); FLP.timer=setInterval(ftRefresh,3000);}
async function ftRefresh(){ if(!FLP.chat_id)return;
 let r=await ftApi('/api/fliptoons/game?chat_id='+encodeURIComponent(FLP.chat_id)+'&init_data='+encodeURIComponent(FLP.init));
 if(r.ok){FLP.board=r.game; ftRender();}}
async function ftMove(action,extra){
 let body=Object.assign({chat_id:FLP.chat_id,action:action,init_data:FLP.init},extra||{});
 let r=await ftApi('/api/fliptoons/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.events)r.events.forEach(e=>ftLog(e)); if(r.error)ftLog('⛔ '+r.error);
 if(r.game){FLP.board=r.game; ftRender();}}
function ftCell(st){
 if(!st||!st.length)return '<div class="ftcell empty">·</div>';
 let top=st[st.length-1], cls='ftcell'+(top.fd?' fd':''), stack=st.length>1?' ×'+st.length:'';
 let fame=top.fd?'':'<span class="fm">'+top.fame+'</span>';
 return '<div class="'+cls+'"><span class="nm">'+escapeHtml(top.name)+stack+'</span>'+fame+'</div>';
}
function ftGrid(p){
 let cells=p.grid.map(ftCell);
 while(cells.length<6)cells.push('<div class="ftcell empty">·</div>');
 let h='<div class="ftgrid">'+cells.join('')+'</div>';
 (p.extra||[]).forEach(e=>{h+='<div class="ftrow-extra">+ '+e.cards.map(c=>escapeHtml(c.fd?'?':c.name)+(c.fd?'':' ('+c.fame+')')).join(' · ')+'</div>';});
 return h;
}
function ftDismissButtons(p){
 let out=[];
 let add=c=>{if(c.dismissable)out.push('<button class="ftdismiss" data-dismiss="'+c.id+'">🗑 '+escapeHtml(c.name)+' ('+c.dismiss_cost+')</button>');};
 p.grid.forEach(st=>st.forEach(add));
 (p.extra||[]).forEach(e=>e.cards.forEach(add));
 return out.length?'<div class="ftopts">'+out.join('')+'</div>':'';
}
function ftRender(){
 let b=FLP.board; if(!b)return;
 let t=document.getElementById('ftTurn'), board=document.getElementById('ftBoard');
 let cur=b.actor!=null?b.players[b.actor]:null;
 let isActor=b.actor!=null&&(cur.user_id===FLP.user_id||cur.npc);
 let myMarket=b.can_act&&b.stage==='market'&&!b.pending;
 let parts=[];
 if(b.phase==='lobby'){
  t.textContent='🪑 Lobby - '+b.players.length+'/4 players';
  parts.push('<div class="table"><div class="small">Players</div>'+b.players.map(p=>'<div>'+escapeHtml(p.name)+(p.npc?' 🤖':'')+(p.user_id===FLP.user_id?' (you)':'')+'</div>').join('')+
   '<div class="lobby-note">Friends join in Telegram, then anyone taps Start.</div></div>');
 } else if(b.phase==='game_end'){
  t.textContent='🏆 Game over!';
  if(b.winner!=null){let w=b.players[b.winner]; parts.push('<div class="table lobby-note">Winner: <b>'+escapeHtml(w.name)+'</b> with '+w.fame+' fame!</div>');}
  else parts.push('<div class="table lobby-note">It\'s a draw!</div>');
 } else {
  t.textContent=isActor?(b.pending?'👉 Your choice':(b.stage==='market'?'👉 Your market turn':'⏳ Resolving flips…')):(cur?'👉 '+escapeHtml(cur.name)+'\'s turn':'⏳ Resolving flips…');
  if(b.pending){
   let pp=b.players[b.pending.player];
   let mine=b.pending.player!=null&&pp&&(pp.user_id===FLP.user_id||pp.npc);
   parts.push('<div class="table"><div class="lobby-note">'+escapeHtml(b.pending.prompt)+
    (!mine&&pp?' <i>(waiting for '+escapeHtml(pp.name)+')</i>':'')+'</div>'+
    (mine?'<div class="ftopts">'+b.pending.options.map(o=>'<button class="hit" data-choose="'+escapeHtml(String(o.v))+'">'+escapeHtml(o.label)+'</button>').join('')+'</div>':'')+
    '</div>');
  }
  parts.push('<div class="table"><div class="small">🛒 Market (cost = slot) · round '+b.round+' · target '+b.target+' fame</div><div class="ftmarket">'+
   b.market.map(m=>'<div class="ftmcard"><div class="price">'+m.price+'💰</div><div>'+(m.card?escapeHtml(m.card.name):'—')+'</div>'+
    (m.card&&myMarket?'<button class="hit" data-hire="'+m.slot+'">Hire</button>':'')+'</div>').join('')+'</div></div>');
  let ph='<div class="table"><div class="ftplayers">';
  b.players.forEach((p,i)=>{
   ph+='<div class="ftpc'+(p.is_current?' current':'')+'"><div style="display:flex;justify-content:space-between"><b>'+escapeHtml(p.name)+(p.npc?' 🤖':'')+'</b><span class="score">'+p.fame+'</span></div>'+
    '<div class="small">deck '+p.deck+' · discarded '+p.discarded+(p.is_current&&b.stage==='market'?' · budget '+p.budget:'')+'</div>'+ftGrid(p)+
    (i===b.actor&&myMarket?ftDismissButtons(p):'')+'</div>';
  });
  ph+='</div></div>'; parts.push(ph);
 }
 board.innerHTML=parts.join('');
 document.getElementById('ftJoin').classList.toggle('hidden',!(b.phase==='lobby'&&!b.is_player));
 document.getElementById('ftStart').classList.toggle('hidden',!(b.phase==='lobby'&&b.is_player));
 document.getElementById('ftSkip').classList.toggle('hidden',!myMarket);
 document.getElementById('ftRematch').classList.toggle('hidden',!(b.phase==='game_end'&&b.is_player));
 board.querySelectorAll('[data-hire]').forEach(el=>el.addEventListener('click',()=>ftMove('hire',{slot:parseInt(el.dataset.hire)})));
 board.querySelectorAll('[data-choose]').forEach(el=>el.addEventListener('click',()=>ftMove('choose',{choice:el.dataset.choose})));
 board.querySelectorAll('[data-dismiss]').forEach(el=>el.addEventListener('click',()=>ftMove('dismiss',{iid:parseInt(el.dataset.dismiss)})));
}
document.getElementById('ftJoin').addEventListener('click',()=>ftMove('join'));
document.getElementById('ftStart').addEventListener('click',()=>ftMove('start'));
document.getElementById('ftSkip').addEventListener('click',()=>ftMove('skip'));
document.getElementById('ftRematch').addEventListener('click',()=>ftMove('rematch'));
if(!document.getElementById('fliptoons').classList.contains('hidden')) ftLoad();
