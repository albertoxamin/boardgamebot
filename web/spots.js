// Spots Mini App (synced, initData auto-login). Loaded by flip7.html router.
const SP={user_id:0,chat_id:null,board:null,timer:null,init:'',dieSel:null,rerollSel:new Set()};
function spLog(s){let e=document.getElementById('spotsLog');if(e)e.textContent+=s+'\n';}
const DOG_ORDER=["leif-mudge-bucky","bristles","sundrop-nori","goliath","gumbo","bongo","pebble","wilbur","eloise","cabbage-taters-ham","honcho","ursula","mayor","burt","wolfgang","raya","doog","tolene","rogue","nutmeg","xerxes","rupert","louise","missy-maam","mirabelle","lil-beth","pierogi-gyota-momo","handsome","frankie","zipper","bitsy","gretchen"];
function spDogImg(dog,scored){
 let col=DOG_ORDER.indexOf(dog.slug); if(col<0)col=0;
 let row=Math.floor(col/8); col=col%8;
 return '<div class="sdog'+(scored?' scored':'')+'" style="background-position:-'+(col*96)+'px -'+(row*68)+'px" title="'+escapeHtml(dog.name)+'"></div>';}
function spApi(path,opts){return fetch(path,opts).then(r=>r.json());}
async function spLoad(){
 let tg=tgInit();
 if(!tg.id){document.getElementById('spotsBoard').innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot\'s Spots link.</div>';return;}
 SP.user_id=tg.id; SP.init=tg.init;
 let r=await spApi('/api/spots/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 let pref=parseInt(tg.start,10)||0; if(!pref && tg.chat_instance) pref=parseInt(tg.chat_instance,10)||0;
 if(tg.start && String(tg.start).startsWith('spots')) pref=parseInt(String(tg.start).slice(5),10)||pref;
 let pick=mine.find(g=>g.chat_id===pref);
 if(!pick && pref){let spec=await spApi('/api/spots/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
  if(spec.ok) pick={chat_id:pref};}
 if(!pick) pick=mine.find(g=>g.phase!=='game_end') || mine[0];
 if(pick) spSelect(pick.chat_id);
 else if(pref){let cr=await spApi('/api/spots/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});
  if(cr.game) spSelect(cr.game.chat_id); else spLog('⛔ '+(cr.error||'create failed'));}
 else document.getElementById('spotsBoard').innerHTML='<div class="table lobby-note">No Spots game for you yet — send /spots in a chat, then open its Mini App link.</div>';
}
async function spSelect(chat_id){SP.chat_id=chat_id; await spRefresh();
 if(SP.timer)clearInterval(SP.timer); SP.timer=setInterval(spRefresh,3000);}
async function spRefresh(){ if(!SP.chat_id)return;
 let r=await spApi('/api/spots/game?chat_id='+encodeURIComponent(SP.chat_id)+'&init_data='+encodeURIComponent(SP.init));
 if(r.ok){SP.board=r.game; spRender();}}
async function spMove(action,extra){
 let body=Object.assign({chat_id:SP.chat_id,action:action,init_data:SP.init},extra||{});
 let r=await spApi('/api/spots/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.events)r.events.forEach(e=>spLog(e)); if(r.error)spLog('⛔ '+r.error);
 if(r.game){SP.board=r.game; SP.dieSel=null; SP.rerollSel=new Set(); spRender();}}
function spRender(){let b=SP.board; if(!b)return;
 SP.spectating=b.is_player===false&&!(cur&&cur.npc);
 let me=b.players.find(p=>p.user_id===SP.user_id);
 let cur=b.players[b.current_index]; let myTurn=(b.phase==='playing'&&cur&&(cur.user_id===SP.user_id||cur.npc)&&!b.pending);
 let tiles='<div class="small"><b>Trick tiles</b> (tap one to do it — the card shows its steps)</div><div>'
  + b.tiles.map(t=>'<span class="tiley'+(t.faceup?'':' tilety')+'" data-slug="'+t.slug+'" title="'+escapeHtml(t.slug)+'"><img src="spots-tiles/'+t.slug+'.jpg?v=2" alt="'+escapeHtml(t.slug)+'">'+(t.treat_on?'<div>🦴</div>':'')+'</span>').join('') + '</div>';
 let seats=b.players.map((p,i)=>{
   let isTurn=b.current_index===i&&b.phase==='playing';
   return '<div class="lsdseat'+(isTurn?' current':'')+'"><div class="seat-head"><span><span class="avatar">'+escapeHtml(p.name.slice(0,1).toUpperCase())+'</span>'+escapeHtml(p.name)+'</span><span class="score">'+p.scored.length+'🏅 · '+p.treats+'🦴</span></div>'
    +'<div style="display:flex;gap:8px;align-items:flex-start"><div class="tyard" data-yard="'+i+'" style="background-position:-'+(i*84)+'px 0" title="yard (buried dice)"></div><div class="small">Yard: '+(p.yard.length?p.yard.join(' '):'—')+' = '+p.yard.reduce((a,c)=>a+c,0)+'</div></div>'
    + p.dogs.map(d=>'<div style="margin:4px 0">'+spDogImg(d,false)
      +'<div>'+d.spots.map((s,si)=>{let filled=(d.placed||{})[si]!==undefined;
        return '<span class="spotbox'+(filled?' filled':'')+'" data-dog="'+d.iid+'" data-spot="'+si+'">'+(filled?d.placed[si]:s)+'</span>';}).join('')+'</div></div>').join('')
    + p.scored.map(d=>'<div title="scored" style="opacity:.6">'+spDogImg(d,true)+'</div>').join('')
    +(isTurn?'<div class="small"><b>▶ Turn</b></div>':'')+'</div>';}).join('');
 document.getElementById('spotsBoard').innerHTML='<div class="table" style="position:relative">'
  +(SP.spectating?'<div class="lobby-note">👁 Spectating — view only (join in Telegram to play)</div>':'')
  +tiles+seats+'</div>';
 // Trick tiles tap (choose a trick)
 if(myTurn && !b.trick){
   document.querySelectorAll('#spotsBoard .tiley').forEach(el=>{
     if(!el.classList.contains('tilety')) el.addEventListener('click',()=>spMove('trick',{tile:el.dataset.slug}));
   });
 }
 // Dice pool (placement pending)
 let pool=document.getElementById('spotsPool'); pool.innerHTML='';
 let pend=b.pending;
 if(pend&&pend.kind==='place'&&me&&b.current_index===b.players.indexOf(me)){
   let dice=(b.trick?b.trick.dice:[]);
    pool.innerHTML='<div class="small"><b>Dice to place:</b> tap a die, then tap a matching spot or your yard'+(b.trick&&b.trick.tile==='search'?' — place dice totalling exactly 8, then use Done below':'')+'</div><div>'
     + dice.map((v,i)=>'<span class="sdice'+(SP.dieSel===i?' sel':'')+'" data-i="'+i+'" title="die showing '+v+'" style="background-position:-'+((v-1)*40)+'px 0"></span>').join('')+'</div>'
     + '<button class="lsdchoice" id="spBury">⛏ Bury selected die in yard</button>'
     + (me.treats>0?'<button class="lsdchoice" id="spReroll">🎲 Reroll'+(b.trick&&b.trick.tile==='track'?' selected':' all')+' (1 treat)</button>':'')
     + (b.trick&&b.trick.tile==='search'?'<button class="lsdchoice" id="spDone">✅ Done (discard rest)</button>':'');
   pool.querySelectorAll('.sdice').forEach(el=>el.addEventListener('click',()=>{
     let i=parseInt(el.dataset.i);
     if(b.trick&&b.trick.tile==='track'){SP.rerollSel.has(i)?SP.rerollSel.delete(i):SP.rerollSel.add(i); el.classList.toggle('sel');}
     else {SP.dieSel=SP.dieSel===i?null:i; spRender();}
   }));
   let buryBtn=document.getElementById('spBury');
   if(buryBtn)buryBtn.addEventListener('click',()=>{if(SP.dieSel===null){spLog('Select a die first');return;} spMove('place',{die_pos:SP.dieSel,target:['yard']});});
   let rrBtn=document.getElementById('spReroll');
   if(rrBtn)rrBtn.addEventListener('click',()=>spMove('reroll',{indices:b.trick&&b.trick.tile==='track'?[...SP.rerollSel]:null}));
   let dnBtn=document.getElementById('spDone');
   if(dnBtn)dnBtn.addEventListener('click',()=>spMove('choice',{choice:'done'}));
   // yard tap = bury
   document.querySelectorAll('#spotsBoard .tyard').forEach(el=>el.addEventListener('click',()=>{
     if(parseInt(el.dataset.yard)!==b.players.indexOf(me))return; // only your own yard
     if(SP.dieSel===null){spLog('Select a die first');return;}
     spMove('place',{die_pos:SP.dieSel,target:['yard']});
   }));
   // dog spot taps
   document.querySelectorAll('#spotsBoard .spotbox').forEach(el=>el.addEventListener('click',()=>{
     if(SP.dieSel===null){spLog('Select a die first');return;}
     spMove('place',{die_pos:SP.dieSel,target:['dog',parseInt(el.dataset.dog),parseInt(el.dataset.spot)]});
   }));
 }
 document.getElementById('spotsScore').classList.toggle('hidden',!(myTurn&&!b.trick&&(me?me.dogs.some(d=>Object.keys(d.placed||{}).length===d.spots.length):false)));
 document.getElementById('spotsStart').classList.toggle('hidden',!(b.phase==='lobby'&&b.players.some(p=>p.user_id===SP.user_id)));
 // Pending choices (non-place)
 let ch=document.getElementById('spotsChoice'); ch.innerHTML='';
 if(pend&&pend.kind!=='place'){
   let pendPlayer=b.players[pend.player];
   let box=document.createElement('div'); box.className='card';
   box.innerHTML='<b>⏳ '+(pendPlayer?escapeHtml(pendPlayer.name):'')+' to choose:</b>';
   (pend.options_detail||[]).forEach(o=>{let btn=document.createElement('button'); btn.className='lsdchoice'; btn.textContent=o.label;
     btn.addEventListener('click',()=>spMove('choice',{choice:o.choice})); box.appendChild(btn);});
   ch.appendChild(box);
 }
 let t=document.getElementById('spotsTurn');
 if(b.phase==='playing') t.textContent=pend? '👉 '+nameOf(b,pend.player)+' to choose' : (myTurn?'👉 Your turn - choose a trick or Score':'👉 '+b.players[b.current_index].name+"'s turn");
 else if(b.phase==='lobby') t.textContent='🪑 Lobby - anyone taps Start';
 else if(b.phase==='game_end') t.textContent='🏆 Game over!';
 else t.textContent='';
}
function nameOf(b,uid){let p=b.players.find(p=>p.user_id===uid);return p?p.name:'?';}
document.getElementById('spotsScore').addEventListener('click',()=>spMove('score'));
document.getElementById('spotsStart').addEventListener('click',()=>spMove('start'));
// Self-start when router (flip7.js) selected Spots mode.
if(!document.getElementById('spots').classList.contains('hidden')) spLoad();
