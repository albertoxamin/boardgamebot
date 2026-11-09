// Let's Summon Demons Mini App (synced, initData auto-login). Loaded by flip7.html router.
const SD={user_id:0,chat_id:null,board:null,timer:null,init:'',sacSel:[],demonSel:null,summonMode:false,replaceSel:[],prevMarket:[]};
function sdLog(s){let e=document.getElementById('lsdLog');if(e)e.textContent+=s+'\n';}
function sdCard(c,selected,extra,big){
 if(!c)return '';
 return '<img class="lsdcard'+(big?' big':'')+(selected?' sel':'')+(extra?' '+extra:'')
  +'" src="lsd-cards/'+c.slug+'.jpg" data-iid="'+c.iid+'" title="'+escapeHtml(c.name)+' ('+(c.num!==null&&c.num!==undefined?c.num:(c.nums?c.nums.join('/'):'∞'))+')" alt="'+escapeHtml(c.name)+'">';}
function sdNew(prev,keys){let pool=[...prev],out=new Set();keys.forEach((k,i)=>{let j=pool.indexOf(k);if(j>=0)pool.splice(j,1);else out.add(i);});return out;}
function sdApi(path,opts){return fetch(path,opts).then(r=>r.json());}
async function sdLoad(){
 let tg=tgInit();
 if(!tg.id){document.getElementById('lsdBoard').innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot\'s Summon Demons link.</div>';return;}
 SD.user_id=tg.id; SD.init=tg.init;
 let r=await sdApi('/api/lsd/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 let pref=parseInt(tg.start,10)||0; if(!pref && tg.chat_instance) pref=parseInt(tg.chat_instance,10)||0;
 if(tg.start && String(tg.start).startsWith('lsd')) pref=parseInt(String(tg.start).slice(3),10)||pref;
 let pick=mine.find(g=>g.chat_id===pref);
 if(!pick && pref){let spec=await sdApi('/api/lsd/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
  if(spec.ok) pick={chat_id:pref};}
 if(!pick) pick=mine.find(g=>g.phase!=='game_end') || mine[0];
 if(pick) sdSelect(pick.chat_id);
 else if(pref){let cr=await sdApi('/api/lsd/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});
  if(cr.game) sdSelect(cr.game.chat_id); else sdLog('⛔ '+(cr.error||'create failed'));}
 else document.getElementById('lsdBoard').innerHTML='<div class="table lobby-note">No Summon Demons game for you yet — send /lsd in a chat, then open its Mini App link.</div>';
}
async function sdSelect(chat_id){SD.chat_id=chat_id; await sdRefresh();
 if(SD.timer)clearInterval(SD.timer); SD.timer=setInterval(sdRefresh,3000);}
async function sdRefresh(){ if(!SD.chat_id)return;
 let r=await sdApi('/api/lsd/game?chat_id='+encodeURIComponent(SD.chat_id)+'&init_data='+encodeURIComponent(SD.init));
 if(r.ok){SD.board=r.game; sdRender();}}
async function sdMove(action,extra){
 let body=Object.assign({chat_id:SD.chat_id,action:action,init_data:SD.init},extra||{});
 let r=await sdApi('/api/lsd/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.events)r.events.forEach(e=>sdLog(e)); if(r.error)sdLog('⛔ '+r.error);
 if(r.game){SD.board=r.game; SD.sacSel=[]; SD.demonSel=null; SD.summonMode=false; SD.replaceSel=[]; sdRender();}}
function summonCost(b){
 for(let j=0;j<b.players.length;j++){ if(j===b.current_index)continue;
  if((b.players[j].demons||[]).some(c=>c.eff==='baphometal')) return 4; }
 return 3;}
function sdRender(){let b=SD.board; if(!b)return;
 SD.spectating=b.is_player===false;
 let me=b.players.find(p=>p.user_id===SD.user_id);
 let myTurn=(b.phase==='playing'&&b.players[b.current_index]&&b.players[b.current_index].user_id===SD.user_id&&!b.pending);
 let cost=summonCost(b);
 let marketKeys=(b.market||[]).map(c=>c.iid), newMarket=sdNew(SD.prevMarket,marketKeys); SD.prevMarket=marketKeys;
 let market='<div class="small"><b>THE BLOCK</b> (buy for 3 👻) · Supply '+b.supply+'</div><div class="lsdrow">'
  + (b.market||[]).map((c,i)=>sdCard(c,false,newMarket.has(i)?'card-in':'',true)).join('') + '</div>';
 if(b.dice) market+='<div class="small">🎲 Last roll: '+b.dice[0]+'+'+b.dice[1]+'='+b.last_total+'</div>';
 let seats=b.players.map((p,i)=>{
   let isTurn=b.current_index===i&&b.phase==='playing';
   return '<div class="lsdseat'+(isTurn?' current':'')+'"><div class="seat-head"><span><span class="avatar">'+escapeHtml(p.name.slice(0,1).toUpperCase())+'</span>'+escapeHtml(p.name)+'</span><span class="score">'+p.souls+'👻 · '+p.demons.length+'😈</span></div>'
    +(p.candle?'<div class="small">Candle: '+escapeHtml(p.candle.name)+' ('+(p.candle.nums||[]).join('/')+')</div>':'')
    +'<div class="lsdrow">'+p.in_play.map(c=>sdCard(c,SD.summonMode&&me&&p.user_id===SD.user_id&&SD.sacSel.includes(c.iid))).join('')+'</div>'
    +(p.demons.length?'<div class="small">Demons:</div><div class="lsdrow">'+p.demons.map(c=>sdCard(c)).join('')+'</div>':'')
    +(isTurn?'<div class="small"><b>▶ Turn</b></div>':'')+'</div>';}).join('');
 document.getElementById('lsdBoard').innerHTML='<div class="table" style="position:relative">'
  +(SD.spectating?'<div class="lobby-note">👁 Spectating — view only (join in Telegram to play)</div>':'')
  +market+seats+'</div>';
 // My demon hand (private) + summon selection
 let mh=document.getElementById('lsdActions');
 let hand=b.my_demon_hand||[];
 if(!SD.spectating && hand.length){
   mh.innerHTML='<b>My Demons ('+hand.length+' unsummoned)</b><div class="lsdrow">'
    + hand.map(c=>sdCard(c,SD.demonSel===c.iid)).join('') + '</div>'
    +(SD.summonMode?'<div class="small">Tap 1 Demon to summon it, and tap '+cost+' Block cards above to sacrifice.</div>':'');
   mh.querySelectorAll('.lsdcard').forEach(el=>el.addEventListener('click',()=>{SD.demonSel=parseInt(el.dataset.iid); sdRender();}));
 } else mh.innerHTML=SD.spectating?'<div class="small">👁 Spectating — demon hands are private</div>':'';
 // In-play taps (sacrifice selection in summon mode, market taps for buy)
 let boardEl=document.getElementById('lsdBoard');
 if(myTurn && SD.summonMode && me){
   let blockIids=new Set(me.in_play.map(c=>c.iid));
   boardEl.querySelectorAll('.lsdseat .lsdcard').forEach(el=>el.addEventListener('click',()=>{
     let iid=parseInt(el.dataset.iid);
     if(!blockIids.has(iid))return; // only Block cards can be sacrificed
     if(SD.sacSel.includes(iid)) SD.sacSel=SD.sacSel.filter(x=>x!==iid); else SD.sacSel.push(iid);
     boardEl.querySelectorAll('.lsdseat .lsdcard').forEach(x=>x.classList.toggle('sel',SD.sacSel.includes(parseInt(x.dataset.iid))));}));
 }
 if(myTurn && me && b.turn && !b.turn.bought){
   let mkt=boardEl.querySelectorAll('.lsdrow .lsdcard');
 }
 document.getElementById('lsdRoll').classList.toggle('hidden',!(myTurn&&b.turn&&!b.turn.rolled));
 document.getElementById('lsdSummon').classList.toggle('hidden',!(myTurn&&b.turn&&!b.turn.summoned));
 document.getElementById('lsdSummon').textContent=SD.summonMode?'✖ Cancel summon':'😈 Summon (select cards)';
 document.getElementById('lsdEnd').classList.toggle('hidden',!(myTurn&&b.turn&&b.turn.rolled));
 document.getElementById('lsdStart').classList.toggle('hidden',!(b.phase==='lobby'&&b.players.some(p=>p.user_id===SD.user_id)));
 // Summon confirm (in Actions, appended after demon hand)
 if(SD.summonMode && myTurn){
   let ok=SD.sacSel.length===cost&&SD.demonSel!==null;
   let btn=document.createElement('button'); btn.className='hit'; btn.textContent='😈 Confirm summon ('+SD.sacSel.length+'/'+cost+' sacrificed'+(SD.demonSel!==null?' + Demon ✓':'')+')';
   btn.disabled=!ok;
   btn.addEventListener('click',()=>sdMove('summon',{sacrifice:SD.sacSel,demon_iid:SD.demonSel}));
   mh.appendChild(btn);
 }
 // Pending choices
 let ch=document.getElementById('lsdChoice'); ch.innerHTML='';
 if(b.pending){
   let pend=b.pending, opts=pend.options_detail||[];
   let title={reroll:'🔁 Re-roll?',optional:'⚡ '+(pend.name||'')+' — optional discard?',steal_souls:'👻 Steal Souls from:',steal_card:'😈 Steal which card?',gain_block:'🛒 Gain which card from THE BLOCK?',activate_choice:'⚡ Activate which card?',replace_block:'🔁 Replace any number of BLOCK cards, then Done:',alligator:'🐊 Discard up to 2 BOYs/GIRLs from others:',goat_boy:'🐐 Discard 1 BOY:',goat_girl:'🐐 Discard 1 GIRL:',sam_animal:'🐀 Discard 1 ANIMAL:',rosemary:'🥚 Hatch which Demon (top 3)?',gross_book:'📖 Summon which Demon from the deck?',glen_player:'👻 Choose who collects a Soul:',steal_player:'😈 Steal all cards from:',annie_branch:'😈 Annie: steal or gain?'}[pend.kind]||'Choose:';
   let box=document.createElement('div'); box.className='card';
   box.innerHTML='<b>'+title+'</b>';
   if(pend.kind==='replace_block'){
     // market cards are tappable toggles; Done sends the list
     let rows=document.createElement('div'); rows.className='lsdrow';
     (b.market||[]).forEach(c=>{
       let wrap=document.createElement('span'); wrap.innerHTML=sdCard(c,SD.replaceSel.includes(c.iid));
       wrap.querySelector('.lsdcard').addEventListener('click',()=>{
         if(SD.replaceSel.includes(c.iid)) SD.replaceSel=SD.replaceSel.filter(x=>x!==c.iid); else SD.replaceSel.push(c.iid);
         wrap.querySelector('.lsdcard').classList.toggle('sel');});
       rows.appendChild(wrap);});
     box.appendChild(rows);
     let done=document.createElement('button'); done.className='lsdchoice'; done.textContent='✅ Done replacing';
     done.addEventListener('click',()=>sdMove('choice',{choice:SD.replaceSel}));
     box.appendChild(done);
   } else {
     opts.forEach(o=>{let btn=document.createElement('button'); btn.className='lsdchoice'; btn.textContent=o.label;
       btn.addEventListener('click',()=>sdMove('choice',{choice:o.choice})); box.appendChild(btn);});
   }
   ch.appendChild(box);
 }
 let t=document.getElementById('lsdTurn');
 if(b.phase==='playing') t.textContent=b.pending? '👉 '+nameOf(b,b.pending.player)+' to choose' : (myTurn?'👉 Your turn - Roll, Buy (tap a BLOCK card), Summon, End':'👉 '+b.players[b.current_index].name+"'s turn");
 else if(b.phase==='lobby') t.textContent='🪑 Lobby - anyone taps Start';
 else if(b.phase==='game_end') t.textContent='🏆 Game over!';
 else t.textContent='';
 // Market buy taps (only when my turn, souls>=3, not bought, no pending)
 if(myTurn && me && b.turn && !b.turn.bought && me.souls>=3){
   let rows=boardEl.querySelectorAll('.lsdrow'); if(rows[0]) rows[0].querySelectorAll('.lsdcard').forEach(el=>el.addEventListener('click',()=>sdMove('buy',{market_iid:parseInt(el.dataset.iid)})));
 }
}
function nameOf(b,uid){let p=b.players.find(p=>p.user_id===uid);return p?p.name:'?';}
document.getElementById('lsdRoll').addEventListener('click',()=>sdMove('roll'));
document.getElementById('lsdEnd').addEventListener('click',()=>sdMove('end'));
document.getElementById('lsdStart').addEventListener('click',()=>sdMove('start'));
document.getElementById('lsdSummon').addEventListener('click',()=>{SD.summonMode=!SD.summonMode; SD.sacSel=[]; SD.demonSel=null; sdRender();});
// Self-start when router (flip7.js) selected LSD mode.
if(!document.getElementById('lsd').classList.contains('hidden')) sdLoad();
