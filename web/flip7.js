const WIN=200;
let G=null;
// Router: same Main Mini App serves both games. startapp=regicide<chat_id>
// (or ?app=regicide in private) shows Regicide, else Flip 7.
(function router(){
 try{let start=new URLSearchParams(location.search).get('app')||'';
  try{let p=new URLSearchParams(Telegram.WebApp.initData||''); start=start||p.get('start_param')||'';}catch(e){}
  if(String(start).startsWith('regicide')){document.getElementById('regicide').classList.remove('hidden');document.getElementById('synced').classList.add('hidden');document.querySelector('h1').textContent='⚔️ Regicide';}
  else if(String(start).startsWith('odin')){document.getElementById('odin').classList.remove('hidden');document.getElementById('synced').classList.add('hidden');document.querySelector('h1').textContent='🛡️ Odin';}
  else if(String(start).startsWith('lsd')){document.getElementById('lsd').classList.remove('hidden');document.getElementById('synced').classList.add('hidden');document.querySelector('h1').textContent='😈 Summon Demons';}
  else if(String(start).startsWith('spots')){document.getElementById('spots').classList.remove('hidden');document.getElementById('synced').classList.add('hidden');document.querySelector('h1').textContent='🐶 Spots';}
  else if(String(start).startsWith('yahtzee')){document.getElementById('yahtzee').classList.remove('hidden');document.getElementById('synced').classList.add('hidden');document.querySelector('h1').textContent='🎲 Yahtzee';}
  else if(String(start).startsWith('fliptoons')){document.getElementById('fliptoons').classList.remove('hidden');document.getElementById('synced').classList.add('hidden');document.querySelector('h1').textContent='🦋 Fliptoons';}
  else if(String(start).startsWith('tornado')){document.getElementById('tornado').classList.remove('hidden');document.getElementById('synced').classList.add('hidden');document.querySelector('h1').textContent='🛥️ Tornado Splash';}
 }catch(e){}})();
function buildDeck(){let d=[{k:'n',v:0}];for(let n=1;n<=12;n++)for(let i=0;i<n;i++)d.push({k:'n',v:n});
['+2','+4','+6','+8','+10','x2'].forEach(m=>d.push({k:'m',v:m}));
['Freeze','Flip Three','Second Chance'].forEach(a=>{for(let i=0;i<3;i++)d.push({k:'a',v:a})});return d;}
function shuffle(a){for(let i=a.length-1;i>0;i--){let j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]];}return a;}
function log(s){let e=document.getElementById('log');if(e)e.textContent+=s+'\n';}
function save(){localStorage.setItem('flip7_save',JSON.stringify(G));}
function score(p){if(p.status==='busted')return 0;let t=p.numbers.reduce((a,b)=>a+b,0);
 if(p.mods.includes('x2'))t*=2; t+=p.mods.filter(m=>m[0]==='+').reduce((a,b)=>a+parseInt(b.slice(1)),0);
 if(p.numbers.length===7)t+=15; return t;}
function active(){return G.players.map((p,i)=>p.status==='active'?i:-1).filter(i=>i>=0);}
function draw(){if(!G.deck.length){if(!G.aside.length)return null;G.deck=G.aside;G.aside=[];shuffle(G.deck);log('🔀 Deck reshuffled');}return G.deck.pop();}
function cs(c){return c.k==='n'?String(c.v):c.v;}
function addName(){let n=document.getElementById('names');if(!n)return;let d=document.createElement('div');d.innerHTML='<input placeholder="Player '+(n.children.length+1)+'">';n.appendChild(d);}
function startGame(){
 const names=[...document.querySelectorAll('#names input')].map(i=>i.value.trim()).filter(Boolean);
 if(names.length<2){alert('Add at least 2 players');return;}
 G={players:names.map(n=>({name:n,total:0,numbers:[],mods:[],sc:false,status:'active'})),
    deck:shuffle(buildDeck()),aside:[],dealer:0,round:1,phase:'dealing',current:0,queue:[],pending:null,flip3:null,q:[]};
 document.getElementById('setup').classList.add('hidden');document.getElementById('game').classList.remove('hidden');
 G.queue=G.players.map((_,i)=>(G.dealer+i)%G.players.length); log('🎮 Flip 7 started - first to '+WIN); advance(); render();
}
function applyCard(idx,card,inFlip3){
 const p=G.players[idx];
 if(card.k==='n'){ if(p.numbers.includes(card.v)){
   if(p.sc){p.sc=false;G.aside.push(card);log('💛 '+p.name+"'s Second Chance saved them from duplicate "+card.v);return 'saved';}
   p.status='busted';log('💥 '+p.name+' BUSTED on second '+card.v+' - 0 pts');return 'bust';}
  p.numbers.push(card.v);log('🎴 '+p.name+' flips '+card.v);
  if(p.numbers.length===7){log('🃏 FLIP 7! '+p.name+' +15 - round ends');return 'flip7';} return 'ok';}
 if(card.k==='m'){p.mods.push(card.v);log('🎴 '+p.name+' flips modifier '+card.v);return 'ok';}
 if(inFlip3){ if(card.v==='Second Chance'){if(!p.sc){p.sc=true;log('🎴 '+p.name+' flips Second Chance (kept)');}else log('🎴 Second Chance for '+p.name+' discarded (already has one)');}
  else {G.flip3.deferred.push(card.v);log('🎴 '+p.name+' flips '+card.v+' - deferred');} return 'ok';}
 G.pending={action:card.v,chooser:p.name}; log('🎴 '+p.name+' flips '+card.v+' - choose who gets it:'); return 'action';
}
function eligible(a){return active().filter(i=>!(a==='Second Chance'&&G.players[i].sc));}
function resolveAction(t){const a=G.pending.action;G.pending=null;const p=G.players[t];
 if(a==='Freeze'){p.status='frozen';log('❄️ '+p.name+' FROZEN - banks and leaves');}
 else if(a==='Second Chance'){p.sc=true;log('💛 '+p.name+' keeps a Second Chance');}
 else if(a==='Flip Three'){if(p.status!=='active'){log('🎲 Flip Three fizzles');}else{G.flip3={target:t,remaining:3,deferred:[],resume:G.phase};log('🎲 '+p.name+' must Flip Three!');}}
 afterAction(); render();}
function afterAction(){
 if(G.q.length){G.pending={action:G.q.shift(),chooser:G.players[G.lastChooser].name};}
 else if(G.phase==='playing'){ if(!active().length)endRound(); else endTurn(); }
 else {G.phase='dealing'; advance();}
}
function endTurn(){let n=G.players.length;for(let k=1;k<=n;k++){let i=(G.current+k)%n;if(G.players[i].status==='active'){G.current=i;return;}} endRound();}
function advance(){
 while(true){
  if(G.pending){ if(!eligible(G.pending.action).length){log('🗑 '+G.pending.action+' discarded - nobody can take it');G.pending=null;afterAction();continue;} return; }
  if(G.flip3){ let card=draw(); let out=card?applyCard(G.flip3.target,card,true):'done';
   if(out==='bust'){G.flip3=null; if(!active().length)endRound(); else if(G.phase==='dealing')advance(); else endTurn(); return;}
   if(out==='flip7'){endRound();return;}
   G.flip3.remaining--; if(G.flip3.remaining>0)continue;
   G.lastChooser=G.flip3.target; G.q.push(...G.flip3.deferred); let resume=G.flip3.resume; G.flip3=null; G.phase=resume; afterAction(); return; }
  if(G.phase==='dealing'){
   if(!G.queue.length){G.phase='playing';G.current=active().includes(G.dealer)?G.dealer:active()[0]; if(G.current===undefined)endRound(); return;}
   let idx=G.queue.shift(); if(G.players[idx].status!=='active')continue;
   let card=draw(); let out=applyCard(idx,card,false);
   if(out==='action')return; if(out==='flip7'){endRound();return;} continue; }
  return; }
}
function doHit(){let idx=G.current;let card=draw();let out=applyCard(idx,card,false);
 if(out==='action'){} else if(out==='flip7')endRound(); else if(out==='bust'){if(!active().length)endRound();else endTurn();}
 else endTurn(); if(out!=='flip7'&&G.phase!=='round_end'&&G.phase!=='game_end')advance(); render();}
function doStay(){let p=G.players[G.current];
 if(!p.numbers.length&&!p.mods.length&&!p.sc){alert('No cards yet - must Hit');return;}
 p.status='stayed';log('✅ '+p.name+' stays and banks'); if(!active().length)endRound(); else endTurn(); render();}
function endRound(){G.phase='round_end';G.flip3=null;G.pending=null;G.q=[];
 G.players.forEach(p=>{let s=score(p);p.last=s;p.total+=s;log('• '+p.name+': ['+p.numbers.join(',')+'] mods ['+p.mods.join(',')+'] → +'+s+' (total '+p.total+')');});
 let top=Math.max(...G.players.map(p=>p.total));
 if(top>=WIN){let lead=G.players.filter(p=>p.total===top);
  if(lead.length===1){G.phase='game_end';log('🏆 '+lead[0].name+' wins with '+top+' points!');
   sendToBot({winner:lead[0].name,score:top,round:G.round});} else log('🤝 Tie at 200+ - keep playing!');}
 else log('Round '+G.round+' over. First to '+WIN+'.'); save();}
function nextRound(){G.players.forEach(p=>{p.numbers.forEach(v=>G.aside.push({k:'n',v}));p.mods.forEach(m=>G.aside.push({k:'m',v:m}));if(p.sc)G.aside.push({k:'a',v:'Second Chance'});p.numbers=[];p.mods=[];p.sc=false;p.status='active';});
 G.round++;G.dealer=(G.dealer+1)%G.players.length;G.queue=G.players.map((_,i)=>(G.dealer+i)%G.players.length);
 G.phase='dealing';log('Dealer rotates to '+G.players[G.dealer].name+'. Round '+G.round);advance();render();}
function sendToBot(o){try{if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.sendData)Telegram.WebApp.sendData(JSON.stringify(o));}catch(e){}}
function render(){ if(!G)return; save();
 document.getElementById('roundInfo').textContent='Round '+G.round+' · Dealer '+G.players[G.dealer].name+' · Deck '+G.deck.length+' · First to '+WIN;
 document.getElementById('board').innerHTML='<div class="seats">'+G.players.map((p,i)=>{
  let pile=[...p.numbers].sort((a,b)=>a-b).map(v=>cardImg('n',v)).join('')+[...p.mods].sort((a,b)=>(a==='x2'?Infinity:parseInt(a.slice(1)))-(b==='x2'?Infinity:parseInt(b.slice(1)))).map(m=>cardImg('m',m)).join('')+(p.sc?cardImg('a','Second Chance'):'')||'<span class="small">no cards</span>';
  return '<div class="seat '+(G.phase==='playing'&&i===G.current?'current ':'')+p.status+'"><div class="seat-head"><span><span class="avatar">'+escapeHtml(p.name.slice(0,1).toUpperCase())+'</span>'+escapeHtml(p.name)+'</span><span class="score">'+p.total+'</span></div><div class="pile">'+pile+'</div></div>';}).join('')+'</div>';
 let t=document.getElementById('turnText'),ab=document.getElementById('actionBox');
 document.getElementById('hitBtn').classList.toggle('hidden',G.phase!=='playing'||!!G.pending);
 document.getElementById('stayBtn').classList.toggle('hidden',G.phase!=='playing'||!!G.pending);
 document.getElementById('nextBtn').classList.toggle('hidden',G.phase!=='round_end');
 document.getElementById('newBtn').classList.toggle('hidden',G.phase!=='game_end');
 if(G.pending){t.textContent=G.pending.chooser+' - who gets '+G.pending.action+'?';
  ab.innerHTML=''; eligible(G.pending.action).forEach(i=>{let b=document.createElement('button');b.className='targetbtn';b.textContent='➡️ '+G.players[i].name;b.addEventListener('click',()=>resolveAction(i));ab.appendChild(b);});}
 else ab.innerHTML='';
 if(G.phase==='playing')t.textContent='👉 '+G.players[G.current].name+' - Hit or Stay?';
 if(G.phase==='round_end')t.textContent='Round scored! Next round when ready.';
 if(G.phase==='game_end')t.textContent='🏆 Game over!';
 if(G.phase==='dealing')t.textContent='Dealing…';}
function escapeHtml(s){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
try{if(window.Telegram&&Telegram.WebApp){Telegram.WebApp.ready();Telegram.WebApp.expand();}}catch(e){}
// addEventListener (no inline onclick): survives Cloudflare Rocket Loader
// (hot-seat UI removed - Mini App is synced-only now; guards keep old code harmless)
['hitBtn','stayBtn','nextBtn','newBtn','startBtn','addBtn','resetBtn'].forEach(id=>{
 let el=document.getElementById(id); if(!el)return;
 el.addEventListener('click',()=>{({hitBtn:doHit,stayBtn:doStay,nextBtn:nextRound,newBtn:()=>location.reload(),startBtn:startGame,addBtn:addName,resetBtn:()=>{localStorage.removeItem('flip7_save');location.reload();}})[id]();});});
let saved=localStorage.getItem('flip7_save');
if(saved){try{G=JSON.parse(saved);document.getElementById('setup').classList.add('hidden');document.getElementById('game').classList.remove('hidden');log('↩️ Restored saved game');render();}catch(e){}}

// ---------- Synced mode: live Telegram games via /api (Mini App auto-login) ----------
const SYNC={user_id:0,chat_id:null,board:null,timer:null,name:'',init:'',prevPiles:{},prevDeck:-1};
function syncLog(s){document.getElementById('syncLog').textContent+=s+'\n';}
function tgInit(){try{let id=Telegram.WebApp.initData||'';
 let p=new URLSearchParams(id);let u=p.get('user');if(u){let o=JSON.parse(u);
  return {id:o.id,name:o.first_name||'',init:id,start:p.get('start_param')||'',chat_instance:p.get('chat_instance')||p.get('chat_type')||''};}}catch(e){} return {id:0,name:'',init:'',start:'',chat_instance:''};}
function api(path,opts){return fetch(path,opts).then(r=>r.json());}
async function loadGames(){
 let tg=tgInit();
 if(!tg.id){document.getElementById('syncBoard').innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot\'s /web link.</div>';return;}
 SYNC.user_id=tg.id; SYNC.name=tg.name; SYNC.init=tg.init;
 let r=await api('/api/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 let pref=parseInt(tg.start,10)||0; if(!pref && tg.chat_instance) pref=parseInt(tg.chat_instance,10)||0;
 let pick=mine.find(g=>g.chat_id===pref);
 if(!pick && pref){ // spectate the chat's game if one exists
  let spec=await api('/api/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
  if(spec.ok) pick={chat_id:pref};}
 if(!pick) pick=mine.find(g=>g.phase!=='game_end') || mine[0];
 if(pick) selectGame(pick.chat_id);
 else if(pref){ // no game in this chat yet: create it automatically (you are creator)
  let cr=await api('/api/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init})});
  if(cr.game) selectGame(cr.game.chat_id); else syncLog('⛔ '+(cr.error||'create failed'));
 } else document.getElementById('syncBoard').innerHTML='<div class="table lobby-note">No game for you yet — create one in Telegram with /newgame, then open /web here.</div>';
}
async function selectGame(chat_id){SYNC.chat_id=chat_id; await refreshBoard();
 if(SYNC.timer)clearInterval(SYNC.timer); SYNC.timer=setInterval(refreshBoard,3000);}
async function refreshBoard(){ if(!SYNC.chat_id)return;
 let r=await api('/api/game?chat_id='+encodeURIComponent(SYNC.chat_id)+'&init_data='+encodeURIComponent(SYNC.init)); if(!r.ok)return;
 SYNC.board=r.game; renderSync();}
// Flip 7 sprite: 7 cols x 4 rows (cell 130x204 at full size)
const F7_POS={'0':[0,0],'1':[1,0],'10':[2,0],'11':[3,0],'12':[4,0],'2':[5,0],'+8':[6,0],
 '3':[0,1],'4':[1,1],'5':[2,1],'6':[3,1],'7':[4,1],'8':[5,1],'Second Chance':[6,1],
 '9':[0,2],'back':[1,2],'+10':[2,2],'+2':[3,2],'+4':[4,2],'+6':[5,2],'Freeze':[6,2],
 'Flip Three':[0,3],'x2':[1,3]};
function newIdx(prev,keys){let pool=[...prev],out=new Set();keys.forEach((k,i)=>{let j=pool.indexOf(k);if(j>=0)pool.splice(j,1);else out.add(i);});return out;}
function cardImg(kind,v,extra){let pos=F7_POS[String(v)]||[1,2];
 return '<div class="fcard'+(extra?' '+extra:'')+'" title="'+escapeHtml(String(v))+'" style="background-position:-'+(pos[0]*44)+'px -'+(pos[1]*69)+'px"></div>';}
function handScore(p){ // hypothetical hand if stayed now; bust = 0
 if(p.status==='busted') return 0;
 let t=p.numbers.reduce((a,b)=>a+b,0);
 if(p.modifiers.includes('x2')) t*=2;
 t+=p.modifiers.filter(m=>m[0]==='+').reduce((a,b)=>a+parseInt(b.slice(1)),0);
 if(p.numbers.length===7) t+=15;
 return t;}
function seatHtml(p,i,b){
 let isDealer=b.dealer===p.name, isTurn=b.phase==='playing'&&i===b.current_index;
 let isFlipping=!!(b.flip3&&b.flip3.target_index===i), f3cards=p.flip3_cards||[], isFlip3=isFlipping||f3cards.length>0;
 let nums=[...p.numbers].sort((a,b)=>a-b);
 let mods=[...p.modifiers].sort((a,b)=>(a==='x2'?Infinity:parseInt(a.slice(1)))-(b==='x2'?Infinity:parseInt(b.slice(1))));
 let cards=[...nums.map(v=>({k:'n',v})),...mods.map(m=>({k:'m',v:m}))];
 if(p.second_chance)cards.push({k:'a',v:'Second Chance'});
 let pileKeys=cards.map(c=>String(c.v)), newCards=newIdx(SYNC.prevPiles[p.name]||[],pileKeys); SYNC.prevPiles[p.name]=pileKeys;
 let f3pool=[...f3cards];
 let pile=cards.map((c,i)=>{let cls=[]; if(newCards.has(i))cls.push('card-in');
   let j=f3pool.indexOf(String(c.v)); if(j>=0){cls.push('f3card'); f3pool.splice(j,1);}
   return cardImg(c.k,c.v,cls.join(' '));}).join('')
  ||'<span class="small">'+(b.phase==='lobby'?'waiting…':'no cards')+'</span>';
 let statusBadge=p.status==='active'?'': '<span class="badge">'+p.status+'</span>';
 return '<div class="seat '+(isFlip3?'flip3 ':'')+(isTurn?'current ':'')+p.status+'">'
  +'<div class="seat-head"><span><span class="avatar">'+escapeHtml(p.name.slice(0,1).toUpperCase())+'</span>'+escapeHtml(p.name)
  +(isDealer?'<span class="badge dealer">🎩 Dealer</span>':'')+(isTurn?'<span class="badge turn">▶ Turn</span>':'')
  +(isFlip3?'<span class="badge flip3">🎲 '+(isFlipping?'Flipping '+b.flip3.remaining+'…':'Flip Three')+'</span>':'')+statusBadge+'</span>'
  +'<span class="score">'+p.total+'</span></div>'
  +'<div class="pile">'+pile+'</div>'
  +(isFlip3&&!isFlipping?'<div class="small">🎲 Subjected to Flip Three this round — forced card(s) have a dashed outline</div>':'')
  +'<div class="small">Hand <b>'+handScore(p)+'</b> → total <b>'+(p.total+handScore(p))+'</b>'+(p.status==='busted'?' (bust: hand 0)':'')+'</div>'
  +(p.last_round!==null&&p.last_round!==undefined?'<div class="small">last round: +'+p.last_round+'</div>':'')
  +'</div>';}
function renderSync(){let b=SYNC.board; if(!b)return;
 let _ch=b.pending_action?b.players.find(p=>p.user_id===b.pending_action.chooser_id):null;
 SYNC.spectating=b.is_player===false&&!((b.players[b.current_index]||{}).npc)&&!(_ch&&_ch.npc);
 let deckAnim=(SYNC.prevDeck>=0&&b.deck_count<SYNC.prevDeck)?'card-in':''; SYNC.prevDeck=b.deck_count;
 let seats='<div class="seats">'+b.players.map((p,i)=>seatHtml(p,i,b)).join('')+'</div>';
 let specBar=SYNC.spectating?'<div class="lobby-note">👁 Spectating — view only (join in Telegram to play)</div>':'';
 if(b.phase==='lobby'){
  document.getElementById('syncBoard').innerHTML='<div class="table">'+specBar+'<div class="lobby-note"><b>🎴 Lobby</b> — '+b.players.length+' player(s) seated<br><span class="small">Anyone can tap Start (or send <b>/startgame</b> in Telegram).</span></div>'+seats+'</div>';
 } else {
  document.getElementById('syncBoard').innerHTML='<div class="table">'+specBar+'<div class="deckpile"><div class="fcard" title="deck" style="background-position:-44px -138px"></div><div><b>Deck</b> ×'+b.deck_count+'<br><span class="small">Round '+b.round+' · Dealer '+escapeHtml(b.dealer)+'</span></div></div>'+seats+'</div>';
 }
 let me=b.players.find(p=>p.user_id===SYNC.user_id); let cur=b.players[b.current_index]; let myTurn=b.phase==='playing'&&!b.pending_action&&cur&&(cur.user_id===SYNC.user_id||cur.npc);
 document.getElementById('syncHit').classList.toggle('hidden',!myTurn);
 document.getElementById('syncStay').classList.toggle('hidden',!myTurn);
 document.getElementById('syncStart').classList.toggle('hidden',!(b.phase==='lobby'&&me));
 document.getElementById('syncJoin').classList.toggle('hidden',!(b.phase==='lobby'&&me&&!b.is_player));
 document.getElementById('syncRematch').classList.toggle('hidden',!(b.phase==='game_end'&&b.is_player));
 let t=document.getElementById('syncTurn'),ab=document.getElementById('syncActions'); ab.innerHTML='';
 if(b.flip3){let tgt=b.players[b.flip3.target_index];
  t.textContent='🎲 '+tgt.name+' is flipping three ('+b.flip3.remaining+' left)';}
 else if(b.pending_action){let iAmChooser=b.pending_action.chooser_id===SYNC.user_id||(_ch&&_ch.npc);
  t.textContent=iAmChooser? '❓ You choose who gets '+b.pending_action.action : '⏳ Waiting for action choice ('+b.pending_action.action+')';
  if(iAmChooser) b.pending_action.targets.forEach(i=>{let btn=document.createElement('button');btn.className='targetbtn';btn.textContent=(b.pending_action.action==='Flip Three'?'🎲 ':'➡️ ')+b.players[i].name;btn.addEventListener('click',()=>move('action',i));ab.appendChild(btn);});}
 else if(b.phase==='playing') t.textContent=myTurn? '👉 Your turn - Hit or Stay?' : '👉 '+b.players[b.current_index].name+"'s turn";
 else if(b.phase==='lobby') t.textContent='🪑 Lobby - tap Start';
 else if(b.phase==='round_end') t.textContent='Round scored!';
 else if(b.phase==='game_end') t.textContent='🏆 Game over!';
}
async function move(action,target){ if(!SYNC.chat_id)return;
 let r=await api('/api/move',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({chat_id:SYNC.chat_id,action:action,target_index:target,init_data:SYNC.init})});
 if(r.events) r.events.forEach(e=>syncLog(e));
 if(r.error) syncLog('⛔ '+r.error);
 if(r.game) SYNC.board=r.game; renderSync();}
document.getElementById('syncHit').addEventListener('click',()=>move('hit'));
document.getElementById('syncStay').addEventListener('click',()=>move('stay'));
document.getElementById('syncJoin').addEventListener('click',()=>move('join'));
document.getElementById('syncStart').addEventListener('click',()=>move('start'));
document.getElementById('syncRematch').addEventListener('click',()=>move('rematch'));
(function autoSync(){let tg=tgInit(); if(!tg.id)return;
 // Regicide/Odin/LSD/Spots modes are started by their own scripts (loaded after this file).
  if(document.getElementById('regicide').classList.contains('hidden')&&document.getElementById('odin').classList.contains('hidden')&&document.getElementById('lsd').classList.contains('hidden')&&document.getElementById('spots').classList.contains('hidden')&&document.getElementById('yahtzee').classList.contains('hidden')&&document.getElementById('fliptoons').classList.contains('hidden')) loadGames();})();
