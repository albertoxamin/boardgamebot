// Odin Mini App (synced, initData auto-login). Loaded by flip7.html router.
const OD={user_id:0,chat_id:null,board:null,timer:null,init:'',selected:[],pickupSel:null,prevTable:[],prevHand:[]};
// BGA sprite: 10 cols x 6 rows (sheet 1813x2048, cell ~181x341); cols 1-9, rows = colours in order below. Col 9: empty except [9,5] Grumpy Goat bonus (unused).
const OD_SUIT_ORDER={blue:0,red:1,pink:2,green:3,black:4,orange:5};
function odLog(s){let e=document.getElementById('odLog');if(e)e.textContent+=s+'\n';}
function odCard(c,selected,extra,big){
 let col=c.rank-1, row=OD_SUIT_ORDER[c.suit]||0, w=big?72:58, h=big?135:109;
 return '<div class="ocard'+(big?' big':'')+(selected?' sel':'')+(extra?' '+extra:'')
  +'" data-suit="'+c.suit+'" data-rank="'+c.rank+'" title="'+c.rank+' '+c.suit+'" style="background-position:-'+(col*w)+'px -'+(row*h)+'px"></div>';}
function odNew(prev,keys){let pool=[...prev],out=new Set();keys.forEach((k,i)=>{let j=pool.indexOf(k);if(j>=0)pool.splice(j,1);else out.add(i);});return out;}
function odSetValue(cards){return parseInt(cards.map(c=>c.rank).sort((a,b)=>b-a).join(''),10);}
function odMono(cards){return cards.length>0&&(cards.every(c=>c.suit===cards[0].suit)||cards.every(c=>c.rank===cards[0].rank));}
function odApi(path,opts){return fetch(path,opts).then(r=>r.json());}
async function odLoad(){
 let tg=tgInit();
 if(!tg.id){document.getElementById('odBoard').innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot\'s Odin link.</div>';return;}
 OD.user_id=tg.id; OD.init=tg.init;
 let r=await odApi('/api/odin/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 let pref=parseInt(tg.start,10)||0; if(!pref && tg.chat_instance) pref=parseInt(tg.chat_instance,10)||0;
 if(tg.start && String(tg.start).startsWith('odin')) pref=parseInt(String(tg.start).slice(4),10)||pref;
 let pick=mine.find(g=>g.chat_id===pref);
 if(!pick && pref){ // spectate the chat's game if one exists
  let spec=await odApi('/api/odin/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
  if(spec.ok) pick={chat_id:pref};}
 if(!pick) pick=mine.find(g=>g.phase!=='game_end') || mine[0];
 if(pick) odSelect(pick.chat_id);
 else if(pref){let cr=await odApi('/api/odin/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});
  if(cr.game) odSelect(cr.game.chat_id); else odLog('⛔ '+(cr.error||'create failed'));}
 else document.getElementById('odBoard').innerHTML='<div class="table lobby-note">No Odin game for you yet — send /odin in a chat, then open its Mini App link.</div>';
}
async function odSelect(chat_id){OD.chat_id=chat_id; await odRefresh();
 if(OD.timer)clearInterval(OD.timer); OD.timer=setInterval(odRefresh,3000);}
async function odRefresh(){ if(!OD.chat_id)return;
 let r=await odApi('/api/odin/game?chat_id='+encodeURIComponent(OD.chat_id)+'&init_data='+encodeURIComponent(OD.init));
 if(r.ok){OD.board=r.game; odRender();}}
async function odMove(action,extra){
 let body=Object.assign({chat_id:OD.chat_id,action:action,init_data:OD.init},extra||{});
 let r=await odApi('/api/odin/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.events)r.events.forEach(e=>odLog(e)); if(r.error)odLog('⛔ '+r.error);
 if(r.game){OD.board=r.game; OD.selected=[]; OD.pickupSel=null; odRender();}}
function odRender(){let b=OD.board; if(!b)return;
 OD.spectating=b.is_player===false;
 let tableKeys=(b.table||[]).map(c=>c.rank+c.suit), newTable=odNew(OD.prevTable,tableKeys); OD.prevTable=tableKeys;
 let tableHtml=b.table&&b.table.length
  ? '<div class="odtable">'+b.table.map((c,i)=>odCard(c,false,newTable.has(i)?'card-in':'',true)).join('')
    +'<div class="vstack"><span class="odvalue">'+b.table_value+'</span><span class="small">to beat</span></div></div>'
  : '<div class="small">Table empty — leader plays 1 card'+(b.phase==='playing'?'':'')+'</div>';
 let pendingHtml=(b.pending_play&&b.pending_play.length)
  ? '<div class="small">Just played:</div><div class="pile">'+b.pending_play.map(c=>odCard(c,false,'',true)).join('')+'</div>' : '';
 let seats='<div class="seats reg-row">'+b.players.map((p,i)=>{
   let isTurn=(b.phase==='playing'&&i===b.current_index)||(b.phase==='pickup'&&i===b.pickup_player);
   let backs='<div class="handbacks">'+Array.from({length:Math.min(p.hand_count,10)},()=>'<img class="ocard" src="cards/odin_back.svg" alt="hand">').join('')+'</div>';
   return '<div class="seat'+(isTurn?' current':'')+'"><div class="seat-head"><span><span class="avatar">'+escapeHtml(p.name.slice(0,1).toUpperCase())+'</span>'+escapeHtml(p.name)+'</span><span class="score">'+p.score+'</span></div>'+backs
    +(isTurn?'<div class="small"><b>▶ Turn</b></div>':'')+'</div>';}).join('')+'</div>';
 document.getElementById('odBoard').innerHTML='<div class="table" style="position:relative">'+(OD.spectating?'<div class="lobby-note">👁 Spectating — view only (join in Telegram to play)</div>':'')+tableHtml+pendingHtml+seats+'</div>';
 // My hand (only mine, private), sorted by suit then rank for grouping sets
 let hand=[...(b.my_hand||[])].sort((x,y)=>((OD_SUIT_ORDER[x.suit]??99)-(OD_SUIT_ORDER[y.suit]??99))||(x.rank-y.rank));
 OD.handSorted=hand;
 let handKeys=hand.map(c=>c.rank+c.suit), newHand=odNew(OD.prevHand,handKeys); OD.prevHand=handKeys;
 OD.selected=OD.selected.filter(k=>handKeys.includes(k)); // prune stale picks (hand changed)
 let mh=document.getElementById('odHand');
 mh.innerHTML=OD.spectating?'<div class="small">👁 Spectating — hands are private</div>'
  : '<b>My hand ('+hand.length+')</b><div class="pile">'
  + hand.map((c,i)=>odCard(c,OD.selected.includes(c.rank+c.suit),newHand.has(i)?'card-in':'')).join('') + '</div>';
 mh.querySelectorAll('.ocard').forEach(el=>el.addEventListener('click',()=>{
   let k=el.dataset.rank+el.dataset.suit;
   if(OD.selected.includes(k)) OD.selected=OD.selected.filter(x=>x!==k); else OD.selected.push(k); odRenderHandOnly();}));
 odPreview();
 let myTurn=(b.phase==='playing'&&b.players[b.current_index]&&b.players[b.current_index].user_id===OD.user_id);
 let myPickup=(b.phase==='pickup'&&b.pickup_player!==null&&b.players[b.pickup_player]&&b.players[b.pickup_player].user_id===OD.user_id);
 document.getElementById('odPlay').classList.toggle('hidden',!myTurn);
 document.getElementById('odPass').classList.toggle('hidden',!(myTurn&&b.table&&b.table.length));
 document.getElementById('odPickup').classList.toggle('hidden',!myPickup);
 document.getElementById('odStart').classList.toggle('hidden',!(b.phase==='lobby'&&b.players.some(p=>p.user_id===OD.user_id)));
 // Pickup selection: table set cards are tappable only for the picker
 let tb=document.getElementById('odBoard');
 tb.querySelectorAll('.odtable .ocard').forEach(el=>el.addEventListener('click',()=>{
   if(!myPickup)return;
   OD.pickupSel={suit:el.dataset.suit,rank:parseInt(el.dataset.rank)};
   tb.querySelectorAll('.odtable .ocard').forEach(x=>x.classList.toggle('sel',x===el));}));
 let t=document.getElementById('odTurn'),ab=document.getElementById('odActions'); ab.innerHTML='';
 if(b.phase==='playing') t.textContent=myTurn?'👉 Your turn - select card(s) and Play, or Pass':'👉 '+b.players[b.current_index].name+"'s turn";
 else if(b.phase==='pickup') t.textContent=myPickup? '✋ You played - tap 1 card from the previous set to take' : '✋ '+b.players[b.pickup_player].name+' is taking a card';
 else if(b.phase==='lobby') t.textContent='🪑 Lobby - anyone taps Start';
 else if(b.phase==='game_end') t.textContent='🏆 Game over - fewest points wins';
 else t.textContent='';
}
function odPreview(){
 let b=OD.board, pv=document.getElementById('odPreview'), pb=document.getElementById('odPlay');
 if(!b||!OD.selected.length){pv.style.display='none';pv.innerHTML=''; if(pb)pb.disabled=true; return;}
 let cards=(OD.handSorted||[]).filter(c=>OD.selected.includes(c.rank+c.suit));
 if(!cards.length){pv.style.display='none';pv.innerHTML=''; if(pb)pb.disabled=true; return;}
 let hand=OD.handSorted||[], val=odSetValue(cards), lines=[], ok=true;
 if(!b.table||!b.table.length){
   if(cards.length===1) lines.push('🃏 Lead with '+val);
   else if(cards.length===hand.length&&odMono(hand)) lines.push('🃏 Lead all ('+cards.length+') - goes out, hand ends');
   else {ok=false; lines.push('⛔ Lead must be 1 card'+(odMono(hand)?' or all '+hand.length+' (single colour/number)':''));}
 } else {
   if(cards.length!==b.table.length&&cards.length!==b.table.length+1){ok=false; lines.push('⛔ Play '+b.table.length+' or '+(b.table.length+1)+' cards');}
   if(cards.length>=2&&!odMono(cards)){ok=false; lines.push('⛔ A set of 2+ must share a colour or a number');}
   if(val<=b.table_value){ok=false; lines.push('⛔ Must beat '+b.table_value+' (yours: '+val+')');}
   if(ok) lines.push('⚔️ Set value '+val+' beats '+b.table_value);
 }
 if(ok){
   if(cards.length===hand.length) lines.push('🏁 Goes out! Hand ends - no pickup, scores now');
   else if(!b.table||!b.table.length) lines.push('Lead: no pickup');
   else lines.push('Then take 1 card from the previous set');
 }
 pv.innerHTML='<b>Preview:</b><div class="vstack">'+lines.map(l=>'<span>'+l+'</span>').join('')+'</div>';
 pv.style.display='block';
 if(pb)pb.disabled=!ok;}
function odRenderHandOnly(){
 document.querySelectorAll('#odHand .ocard').forEach(el=>el.classList.toggle('sel',OD.selected.includes(el.dataset.rank+el.dataset.suit)));
 odPreview();}
document.getElementById('odPlay').addEventListener('click',()=>{
 let cards=(OD.handSorted||[]).filter(c=>OD.selected.includes(c.rank+c.suit));
 if(!cards.length){odLog('Select a card first');return;}
 odMove('play',{cards:cards});});
document.getElementById('odPass').addEventListener('click',()=>odMove('pass'));
document.getElementById('odStart').addEventListener('click',()=>odMove('start'));
document.getElementById('odPickup').addEventListener('click',()=>{
 if(!OD.pickupSel){odLog('Tap 1 card from the previous set first');return;}
 odMove('pickup',{card:OD.pickupSel});});
// Self-start when router (flip7.js) selected Odin mode.
if(!document.getElementById('odin').classList.contains('hidden')) odLoad();
