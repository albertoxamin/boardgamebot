// Regicide Mini App (synced, initData auto-login). Loaded by flip7.html router.
const RG={user_id:0,chat_id:null,board:null,timer:null,init:'',selected:[],prevPlayed:[],prevHand:[],prevEnemyKey:'',prevDamage:0,prevCounts:{}};
const SUIT_COLOR={'♥':'#dc2626','♦':'#dc2626','♠':'#111827','♣':'#111827'};
function rgLog(s){let e=document.getElementById('rgLog');if(e)e.textContent+=s+'\n';}
const RG_COL={Jester:0,A:1,'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,J:11,Q:12,K:13};
const RG_ROW={'♠':0,'♥':1,'♣':2,'♦':3};
function rgSprite(c,big,extra){
 let col=RG_COL[c.rank]||0, row=c.rank==='Jester'?0:(RG_ROW[c.suit]||0);
 let w=big?72:48, h=big?101:67;
 return '<div class="rcimg'+(big?' big':'')+(extra?' '+extra:'')+'" data-suit="'+c.suit+'" data-rank="'+c.rank+'" title="'+escapeHtml(c.rank+c.suit)+'" style="background-position:-'+(col*w)+'px -'+(row*h)+'px"></div>';}
function rgCard(c,selected,extra){
 return rgSprite(c,false,((extra?extra+' ':'')+(selected?'sel':''))||undefined);}
function rgNew(prev,keys){let pool=[...prev],out=new Set();keys.forEach((k,i)=>{let j=pool.indexOf(k);if(j>=0)pool.splice(j,1);else out.add(i);});return out;}
function rgApi(path,opts){return fetch(path,opts).then(r=>r.json());}
async function rgLoad(){
 let tg=tgInit();
 if(!tg.id){document.getElementById('rgBoard').innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot\'s Regicide link.</div>';return;}
 RG.user_id=tg.id; RG.init=tg.init;
 let r=await rgApi('/api/regicide/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 let pref=parseInt(tg.start,10)||0; if(!pref && tg.chat_instance) pref=parseInt(tg.chat_instance,10)||0;
 if(tg.start && String(tg.start).startsWith('regicide')) pref=parseInt(String(tg.start).slice(8),10)||pref;
 let pick=mine.find(g=>g.chat_id===pref);
 if(!pick && pref){ // spectate the chat's game if one exists
  let spec=await rgApi('/api/regicide/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
  if(spec.ok) pick={chat_id:pref};}
 if(!pick) pick=mine.find(g=>!['won','lost'].includes(g.phase)) || mine[0];
 if(pick) rgSelect(pick.chat_id);
 else if(pref){let cr=await rgApi('/api/regicide/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});
  if(cr.game) rgSelect(cr.game.chat_id); else rgLog('⛔ '+(cr.error||'create failed'));}
 else document.getElementById('rgBoard').innerHTML='<div class="table lobby-note">No Regicide game for you yet — send /regicide in a chat, then open its Mini App link.</div>';
}
async function rgSelect(chat_id){RG.chat_id=chat_id; await rgRefresh();
 if(RG.timer)clearInterval(RG.timer); RG.timer=setInterval(rgRefresh,3000);}
async function rgRefresh(){ if(!RG.chat_id)return;
 let r=await rgApi('/api/regicide/game?chat_id='+encodeURIComponent(RG.chat_id)+'&init_data='+encodeURIComponent(RG.init));
 if(r.ok){RG.board=r.game; rgRender();}}
async function rgMove(action,extra){
 let body=Object.assign({chat_id:RG.chat_id,action:action,init_data:RG.init},extra||{});
 let r=await rgApi('/api/regicide/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.events)r.events.forEach(e=>rgLog(e)); if(r.error)rgLog('⛔ '+r.error);
 if(r.game){RG.board=r.game; RG.selected=[]; rgRender();}}
function rgRender(){let b=RG.board; if(!b)return;
 RG.spectating=b.is_player===false&&!((b.players[b.current_index]||{}).npc);
 let e=b.enemy, atk=e?(e.rank==='K'?20:e.rank==='Q'?15:10):0, hp=e?(e.rank==='K'?40:e.rank==='Q'?30:20):0;
 let enemyKey=e?e.rank+e.suit:'';
 let enemyAnim=enemyKey!==RG.prevEnemyKey?'card-in':(e&&b.enemy_damage>RG.prevDamage?'hit-shake':'');
 let head=e? '<div class="deckpile" style="justify-content:flex-start;align-items:flex-start">'+rgSprite(e,true,enemyAnim)+'<div class="vstack" style="font-size:18px"><b>'+e.rank+e.suit+'</b><span>⚔️ '+b.effective_attack+'</span><span>❤️ '+(hp-b.enemy_damage)+'</span></div></div>'
  : (b.phase==='won'?'<div class="lobby-note">🏆 Team wins!</div>':b.phase==='lost'?'<div class="lobby-note">💀 Team loses.</div>':'');
 let castleBack='<div class="castle-tr"><div class="vstack"><b>Castle ('+(b.castle||[]).length+')</b>'+((b.castle||[]).length?'<span>Next: <b>'+b.castle[0]+'</b> '+(b.next_suits||[]).join('')+'</span>':'')+'<span class="small">Tavern '+b.tavern_count+'</span><span class="small">Discard '+b.discard_count+'</span><span class="small">Kills '+b.kills+'/12</span></div><div class="rcimg small" title="castle" style="background-position:0 -101px"></div></div>';
 let seats='<div class="seats reg-row">'+b.players.map((p,i)=>{
   let isTurn=['playing','discard'].includes(b.phase)&&i===b.current_index;
   let grew=p.hand_count>(RG.prevCounts[p.name]||0); let backs='<div class="handbacks">'+Array.from({length:Math.min(p.hand_count,10)},(_,bi)=>'<div class="rcimg'+(grew&&bi===Math.min(p.hand_count,10)-1?' card-in':'')+'" title="hand" style="background-position:0 -67px"></div>').join('')+'</div>';
   return '<div class="seat'+(isTurn?' current':'')+'"><div class="seat-head"><span><span class="avatar">'+escapeHtml(p.name.slice(0,1).toUpperCase())+'</span>'+escapeHtml(p.name)+'</span><span class="score">'+p.hand_count+'</span></div>'+backs+(isTurn?'<div class="small"><b>▶ Turn</b></div>':'')+'</div>';}).join('')+'</div>';
 let playedKeys=(b.played||[]).map(c=>c.rank+c.suit), newPlayed=rgNew(RG.prevPlayed,playedKeys);
 document.getElementById('rgBoard').innerHTML='<div class="table" style="position:relative">'+(RG.spectating?'<div class="lobby-note">👁 Spectating — view only (join in Telegram to play)</div>':'')+head
  +castleBack
  +((b.played||[]).length?'<div class="small">Played:</div><div class="pile">'+b.played.map((c,i)=>rgSprite(c,false,newPlayed.has(i)?'card-in':'')).join('')+'</div>':'')+seats+'</div>';
 RG.prevPlayed=playedKeys; RG.prevEnemyKey=enemyKey; RG.prevDamage=b.enemy_damage||0; RG.prevCounts=Object.fromEntries(b.players.map(p=>[p.name,p.hand_count]));
 // Hand (only mine, private)
 let hand=b.my_hand||[];
 let mh=document.getElementById('rgHand');
 let handKeys=hand.map(c=>c.rank+c.suit), newHand=rgNew(RG.prevHand,handKeys); RG.prevHand=handKeys;
 mh.innerHTML=RG.spectating?'<div class="small">👁 Spectating — hands are private</div>'
  : '<b>My hand ('+hand.length+'/'+b.hand_limit+')</b><div class="pile">'
  + hand.map((c,i)=>rgCard(c, RG.selected.includes(i), newHand.has(i)?'card-in':'')).join('') + '</div>';
 mh.querySelectorAll('.rcimg').forEach(el=>el.addEventListener('click',()=>{
   let i=hand.findIndex(c=>c.suit===el.dataset.suit&&c.rank===el.dataset.rank);
   if(RG.selected.includes(i)) RG.selected=RG.selected.filter(x=>x!==i); else RG.selected.push(i); rgRenderHandOnly();}));
 rgPreview();
 let cur=b.players[b.current_index]; let myTurn=(b.phase==='playing'&&cur&&(cur.user_id===RG.user_id||cur.npc));
 let myDiscard=(b.phase==='discard'&&b.players[b.current_index]&&(b.players[b.current_index].user_id===RG.user_id||b.players[b.current_index].npc));
 document.getElementById('rgPlay').classList.toggle('hidden',!myTurn);
 document.getElementById('rgYield').classList.toggle('hidden',!myTurn);
 document.getElementById('rgDiscard').classList.toggle('hidden',!myDiscard);
 document.getElementById('rgStart').classList.toggle('hidden',!(b.phase==='lobby'&&b.players.some(p=>p.user_id===RG.user_id)));
 document.getElementById('rgRematch').classList.toggle('hidden',!((b.phase==='won'||b.phase==='lost')&&b.is_player));
 let t=document.getElementById('rgTurn'),ab=document.getElementById('rgActions'); ab.innerHTML='';
 if(b.phase==='playing') t.textContent=myTurn?'👉 Your turn - select card(s) and Play, or Yield':'👉 '+b.players[b.current_index].name+"'s turn";
 else if(b.phase==='discard') t.textContent=myDiscard? '💥 Discard ≥'+b.discard_needed+' (done '+b.discard_total+') - select card(s), then Discard' : '💥 '+b.players[b.current_index].name+' is discarding';
 else if(b.phase==='jester_next'){t.textContent='🎯 Pick who goes next:';
   b.players.forEach((p,i)=>{let btn=document.createElement('button');btn.className='targetbtn';btn.textContent='➡️ '+p.name;btn.addEventListener('click',()=>rgMove('jester_next',{target_index:i}));ab.appendChild(btn);});}
 else if(b.phase==='lobby') t.textContent='🪑 Lobby - anyone taps Start';
 else t.textContent='';
}
function rgPreview(){
 let b=RG.board, pv=document.getElementById('rgPreview');
 if(!b||!RG.selected.length){pv.style.display='none';pv.innerHTML='';return;}
 let cards=RG.selected.map(i=>b.my_hand[i]).filter(Boolean);
 let val=c=>c.rank==='Jester'?0:(['J','Q','K'].includes(c.rank)?({J:10,Q:15,K:20}[c.rank]):(c.rank==='A'?1:parseInt(c.rank)));
 let total=cards.reduce((a,c)=>a+val(c),0);
 if(b.phase==='discard'){
  let done=(b.discard_total||0)+total, need=b.discard_needed||0;
  pv.innerHTML='<b>Discard preview:</b><div class="vstack"><span>🗑 '+cards.map(c=>c.rank+c.suit).join(', ')+' = '+total+'</span><span>Total after: '+done+'/'+need+(done>=need?' ✅ covers the attack':' (still need '+(need-done)+' more)')+'</span></div>';
  pv.style.display='block'; return;}
 let e=b.enemy, immuneOff=b.immune_off||false;
 let suits=[...new Set(cards.filter(c=>c.rank!=='Jester').map(c=>c.suit))];
 let lines=[], blocked=[];
 if(cards.some(c=>c.rank==='Jester')){lines.push('🃏 Jester: cancels '+e.suit+' immunity, no damage, no enemy attack, pick next.');}
 else {
  for(let s of suits){ if(!immuneOff && e && s===e.suit){blocked.push(s+' blocked by '+e.rank+e.suit+' immunity'); continue;}
   if(s==='♥')lines.push('♥ Heal '+total+' from discard under Tavern');
   if(s==='♦')lines.push('♦ Draw '+total+' card(s)');
   if(s==='♠')lines.push('♠ Shield +'+total+' (enemy atk → '+Math.max(0,b.effective_attack-total)+')');
   if(s==='♣')lines.push('♣ Damage doubled'); }
  let dmg=(suits.includes('♣')&&!( !immuneOff && e && e.suit==='♣'))? total*2 : total;
  lines.push('⚔️ Damage '+dmg+' (enemy '+(b.enemy_damage+dmg)+'/'+(e?(e.rank==='K'?40:e.rank==='Q'?30:20):0)+')'+(b.enemy_damage+dmg>= (e?(e.rank==='K'?40:e.rank==='Q'?30:20):0) ? ' → DEFEATED' : ''));
 }
 pv.innerHTML='<b>Preview:</b><div class="vstack">'+lines.map(l=>'<span>'+l+'</span>').join('')+(blocked.length?'<span>⛔ Blocked: '+blocked.join(', ')+'</span>':'')+'</div>';
 pv.style.display='block';}
function rgRenderHandOnly(){
 document.querySelectorAll('#rgHand .rcimg').forEach((el,i)=>el.classList.toggle('sel',RG.selected.includes(i)));
 rgPreview();}
document.getElementById('rgPlay').addEventListener('click',()=>{
 if(!RG.selected.length){rgLog('Select a card first');return;}
 let cards=RG.selected.map(i=>RG.board.my_hand[i]);
 rgMove('play',{cards:cards});});
document.getElementById('rgYield').addEventListener('click',()=>rgMove('yield'));
document.getElementById('rgStart').addEventListener('click',()=>rgMove('start'));
document.getElementById('rgRematch').addEventListener('click',()=>rgMove('rematch'));
document.getElementById('rgDiscard').addEventListener('click',()=>{
 if(!RG.selected.length){rgLog('Select card(s) to discard');return;}
 let cards=RG.selected.map(i=>RG.board.my_hand[i]);
 rgMove('discard',{cards:cards});});
// Self-start when router (flip7.js) selected Regicide mode.
if(!document.getElementById('regicide').classList.contains('hidden')) rgLoad();
