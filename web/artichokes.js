const ATAPP={user_id:0,chat_id:null,board:null,timer:null,init:'',err:'',sel:[],pass:new Set()};
const AT_VER=2;
const AT_SPRITE={beet:0,broccoli:1,carrot:2,corn:3,eggplant:4,leek:5,onion:6,peas:7,
 pepper:8,potato:9,artichoke:10,rhubarb:15,back:16};
function atChatId(raw){let s=String(raw||'');if(s.startsWith('artichokes'))s=s.slice(10);
 let n=parseInt(s,10);return isNaN(n)?0:n;}
function atApi(path,opts){return fetch(path,opts).then(r=>r.json());}
function atLog(s){let e=document.getElementById('atLog');if(e)e.textContent+=s+'\n';}
async function atLoad(){
 let tg=tgInit(); let board=document.getElementById('atBoard');
 if(!tg.id){board.innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot\'s Abandon All Artichokes link.</div>';return;}
 ATAPP.user_id=tg.id; ATAPP.init=tg.init;
 let qp=new URLSearchParams(location.search);
 let pref=atChatId(tg.start)||atChatId(qp.get('app'))||parseInt(qp.get('chat_id'),10)||0;
 if(!pref&&tg.chat_instance)pref=parseInt(tg.chat_instance,10)||0;
 let r=await atApi('/api/artichokes/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 if(pref){
  let pick=mine.find(g=>g.chat_id===pref);
  if(!pick){let spec=await atApi('/api/artichokes/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
   if(spec.ok&&spec.game)pick={chat_id:pref};}
  if(pick){atSelect(pick.chat_id);return;}
  let cr=await atApi('/api/artichokes/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});
  if(cr.game){atSelect(cr.game.chat_id);return;}
  ATAPP.err=cr.error||'could not create the game';
  board.innerHTML='<div class="table lobby-note">⛔ '+escapeHtml(ATAPP.err)+'</div>';return;
 }
 let cands=mine.slice().sort((a,b)=>((a.phase==='game_end')-(b.phase==='game_end'))||
  ((b.players?b.players.length:0)-(a.players?a.players.length:0)));
 if(cands.length){atSelect(cands[0].chat_id);return;}
 board.innerHTML='<div class="table lobby-note">No Abandon All Artichokes game for you yet — send /artichokes in a chat, then open its Mini App link.</div>';
}
async function atSelect(chat_id){ATAPP.chat_id=chat_id;ATAPP.err='';ATAPP.sel=[];ATAPP.pass.clear();await atRefresh();
 if(ATAPP.timer)clearInterval(ATAPP.timer);ATAPP.timer=setInterval(atRefresh,3000);}
async function atRefresh(){if(!ATAPP.chat_id)return;
 let r=await atApi('/api/artichokes/game?chat_id='+encodeURIComponent(ATAPP.chat_id)+'&init_data='+encodeURIComponent(ATAPP.init));
 if(r.ok){ATAPP.board=r.game;ATAPP.err='';atRender();atAutoLog();}
 else if(ATAPP.board){ATAPP.err=r.error||'game not found';atRender();}}
function atAutoLog(){let b=ATAPP.board;if(!b||!b.events)return;b.events.forEach(e=>atLog(e));delete b.events;}
async function atMove(action,extra){
 let body=Object.assign({chat_id:ATAPP.chat_id,action:action,init_data:ATAPP.init},extra||{});
 let r=await atApi('/api/artichokes/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.events)r.events.forEach(e=>atLog(e));
 ATAPP.err=r.error||'';if(r.error)atLog('⛔ '+r.error);
 if(!r.error){ATAPP.sel=[];ATAPP.pass.clear();}
 if(r.game)ATAPP.board=r.game;
 if(ATAPP.board)atRender();}
function atCard(c,cls,extra){
 let num=AT_SPRITE[c.v];if(num===undefined)num=AT_SPRITE.back;
 let cap=escapeHtml(c.name||c.label||'Card');
 return '<div class="atcard '+cls+'" title="'+cap+'"'+(extra||'')+'>'+
  '<img class="atart" src="/artichokes_cards/'+num+'.jpg?v='+AT_VER+'" alt="'+cap+'">'+
  '<div class="atcap">'+cap+'</div></div>';}
function atPlayer(p,i,b){
 let bits=[];
 if(b.phase!=='lobby'&&i===b.actor)bits.push('👉');
 if(p.npc)bits.push('🤖');
 return '<div class="atseat'+(i===b.actor?' atcurrent':'')+'">'+
  '<div class="atseatname">'+bits.join(' ')+' '+escapeHtml(p.name)+'</div>'+
  '<div class="small">🥬 '+p.artichokes+' · ✋ '+p.hand_count+
  ' · 🎴 '+p.deck+' · ♻️ '+p.discard+'</div></div>';}
function atToggle(list,v){let i=list.indexOf(v);if(i<0)list.push(v);else list.splice(i,1);}
function atRender(){
 let b=ATAPP.board;if(!b)return;
 let turn=document.getElementById('atTurn'),board=document.getElementById('atBoard'),
  actions=document.getElementById('atActions'),hand=document.getElementById('atHand'),
  choice=document.getElementById('atChoice');
 let winner=b.players.find(p=>p.user_id===b.winner_id);
 if(b.phase==='lobby')turn.textContent='🥬 Lobby — '+b.players.length+'/4 players';
 else if(b.phase==='game_end')turn.textContent='🏆 '+(winner?escapeHtml(winner.name):'Someone')+' abandoned all artichokes!';
 else if(b.phase==='harvest')turn.textContent='🌱 '+(b.can_act?'Your turn':'Waiting for '+escapeHtml((b.players[b.actor]||{}).name||'player'))+' — harvest one card';
 else if(b.pending)turn.textContent='⚡ '+(b.can_act?'Choose':'Waiting for '+escapeHtml((b.players[b.pending.by]||{}).name||'player'))+' — '+b.pending.prompt;
 else turn.textContent='🎴 '+(b.can_act?'Your turn':'Waiting for '+escapeHtml((b.players[b.actor]||{}).name||'player'))+' — play vegetables, then end turn';
 let h='<div class="table"><div class="small">Round '+b.round+' · 🌳 Stack '+b.garden_stack+' · ♻️ Compost '+b.compost+'</div>'+
  '<div class="atrow"><b>Garden Row</b><div class="atrowcards">';
 b.garden_row.forEach(c=>{
  let click=b.can_act&&b.phase==='harvest'&&!b.pending;
  h+=atCard(c,'atrowcard clickable',click?' data-at-h="'+c.pos+'"':'');
 });
 h+='</div></div><div class="atseats">'+b.players.map((p,i)=>atPlayer(p,i,b)).join('')+'</div></div>';
 board.innerHTML=h;
 hand.innerHTML='';
 let me=b.players.find(p=>p.my_hand);
 if(me&&me.my_hand.length){
  hand.innerHTML='<div class="table"><b>Your hand</b><div class="athand">'+
   me.my_hand.map(c=>{
    let playable=b.playable.indexOf(c.id)>=0;
    let sel=ATAPP.sel.indexOf(c.id)>=0;
    return atCard(c,'athandcard'+(sel?' atsel':'')+(playable&&b.can_act&&!b.pending?' clickable':''),
     playable&&b.can_act&&!b.pending?' data-at-p="'+c.id+'"':'');
   }).join('')+'</div></div>';
 }
 choice.innerHTML='';
 if(b.pending){
  let pend=b.pending,opts=pend.options||[];
  if(pend.kind==='eggplant'){
   choice.innerHTML='<div class="table"><b>'+escapeHtml(pend.prompt)+'</b><div class="atchoices">'+
    opts.map(o=>{
     let on=ATAPP.pass.has(String(o.v));
     return '<button class="atchoice'+(on?' atsel':'')+'" data-at-pass="'+escapeHtml(String(o.v))+'">'+escapeHtml(o.label)+'</button>';
    }).join('')+'</div>'+(b.can_act?'<button class="hit" id="atPassGo">✅ Pass selected</button>':'')+'</div>';
  }else{
   choice.innerHTML='<div class="table"><b>'+escapeHtml(pend.prompt)+'</b><div class="atchoices">'+
    opts.map(o=>'<button class="atchoice" data-at-ch="'+escapeHtml(String(o.v))+'">'+escapeHtml(o.label)+'</button>').join('')+'</div></div>';
  }
 }
 let a='';
 if(b.phase==='lobby'){
  if(!b.is_player)a+='<button class="primary" id="atJoin">🙋 Join</button>';
  if(b.players.length>=2)a+='<button class="primary" id="atStart">🎮 Start game</button>';
 }else if(b.phase==='game_end'){
  a+='<button class="primary" id="atRematch">🔄 Rematch!</button>';
 }else if(b.can_act&&!b.pending){
  if(b.phase==='harvest')a+='<button class="stay" id="atSkip">⏭ Skip harvest</button>';
  else{a+='<button class="hit" id="atPlay">🃏 Play selected ('+ATAPP.sel.length+')</button>'+
        '<button class="stay" id="atEnd">🏁 End turn</button>';}
 }
 actions.innerHTML=a;
 if(ATAPP.err)choice.innerHTML+='<div class="lobby-note">⛔ '+escapeHtml(ATAPP.err)+'</div>';
}
(function atEvents(){
 document.addEventListener('click',e=>{
  let t=e.target.closest('[data-at-h],[data-at-p],[data-at-ch],[data-at-pass]');
  if(!t)return;
  if(t.hasAttribute('data-at-h'))return atMove('harvest',{pos:parseInt(t.dataset.atH,10)});
  if(t.hasAttribute('data-at-p')){atToggle(ATAPP.sel,parseInt(t.dataset.atP,10));atRender();return;}
  if(t.hasAttribute('data-at-ch'))return atMove('choose',{choice:/^-?\d+$/.test(t.dataset.atCh)?parseInt(t.dataset.atCh,10):t.dataset.atCh});
  if(t.hasAttribute('data-at-pass')){let v=t.dataset.atPass;if(ATAPP.pass.has(v))ATAPP.pass.delete(v);else ATAPP.pass.add(v);atRender();return;}
 });
 document.addEventListener('click',e=>{
  let id=e.target.id;
  if(id==='atJoin')return atMove('join');
  if(id==='atStart')return atMove('start');
  if(id==='atRematch')return atMove('rematch');
  if(id==='atSkip')return atMove('skip');
  if(id==='atPlay'){if(!ATAPP.sel.length){ATAPP.err='Select a card first.';atRender();return;}
   return atMove('play',{iid:ATAPP.sel[0]});}
  if(id==='atEnd')return atMove('end');
  if(id==='atPassGo')return atMove('pass',{ids:Array.from(ATAPP.pass)});
 });
})();
(function atStart(){if(document.getElementById('atBoard'))atLoad();})();
