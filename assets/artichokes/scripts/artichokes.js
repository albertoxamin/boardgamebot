const ATAPP={user_id:0,chat_id:null,board:null,timer:null,init:'',err:'',sel:[],pass:new Set(),popupTimer:null,sig:''};
const AT_HOW_TO_PLAY_URL = 'https://youtu.be/WP1hqBnqAiY';
const AT_VER=4;
const AT_SPRITE={beet:0,broccoli:1,carrot:2,corn:3,eggplant:4,leek:5,onion:6,peas:7,
 pepper:8,potato:9,artichoke:10,rhubarb:15,back:16};
const AT_COLOR={beet:'#9f2645',broccoli:'#33762f',carrot:'#ef9131',corn:'#f3d80d',
 eggplant:'#7c3883',leek:'#6e8d51',onion:'#b66d36',peas:'#72b146',pepper:'#f3b637',
   potato:'#a27c3e',artichoke:'#c9d336',rhubarb:'#cb4f6b'};
function atCardName(v){return String(v||'').replace(/^./,c=>c.toUpperCase());}
function atChoiceVeg(label){let s=String(label||'').toLowerCase();
 let v=Object.keys(AT_SPRITE).find(k=>k!=='back'&&s.indexOf(k)>=0);
 return v||'';}
function atChoiceCard(label){let v=atChoiceVeg(label);
 if(!v)return '';
 return '<img class="atchoiceimg" src="/assets/artichokes/images/artichokes_cards/'+AT_SPRITE[v]+'.jpg?v='+AT_VER+'" alt="'+escapeHtml(atCardName(v))+'">';}
function atChoiceDesc(label){
 let v=atChoiceVeg(label);
 if(!v)return '';
 return (ATAPP.board&&ATAPP.board.descriptions&&ATAPP.board.descriptions[v])||'';}
function atCardDesc(c){
 let fromBoard=(ATAPP.board&&ATAPP.board.descriptions&&ATAPP.board.descriptions[c.v])||'';
 return fromBoard||String(c.desc||'');}
function atRevealCards(msg){
 let s=String(msg||''),found=[];
 if(!/revealed|drew|turned up/i.test(s))return found;
 Object.keys(AT_SPRITE).forEach(v=>{
  if(v==='back')return;
  let re=new RegExp('(?:^|[^a-z])'+v+'(?:s)?(?:[^a-z]|$)','i');
  if(re.test(s)&&found.indexOf(v)<0)found.push(v);
 });
 return found;}
function atPopup(cards,msg){
 let p=document.getElementById('atPopup');if(!p||!cards.length)return;
 p.innerHTML='<div class="atpopuptext">'+escapeHtml(msg)+'</div><div class="atpopupcards">'+
  cards.map(v=>'<img class="atpopupcard" src="/assets/artichokes/images/artichokes_cards/'+AT_SPRITE[v]+'.jpg?v='+AT_VER+'" alt="'+escapeHtml(atCardName(v))+'">').join('')+'</div>';
 p.classList.remove('hidden','atpopupin');void p.offsetWidth;p.classList.add('atpopupin');
 clearTimeout(ATAPP.popupTimer);
 ATAPP.popupTimer=setTimeout(()=>p.classList.add('hidden'),2800);}
function atChatId(raw){let s=String(raw||'');if(s.startsWith('artichokes'))s=s.slice(10);
 let n=parseInt(s,10);return isNaN(n)?0:n;}
function atApi(path,opts){return fetch(path,opts).then(r=>r.json());}
function atLog(s){
 let e=document.getElementById('atLog');if(e)e.textContent+=s+'\n';
 let cards=atRevealCards(s);if(cards.length)atPopup(cards,s);}
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
async function atSelect(chat_id){ATAPP.chat_id=chat_id;ATAPP.err='';ATAPP.sel=[];ATAPP.pass.clear();ATAPP.sig='';await atRefresh();
 if(ATAPP.timer)clearInterval(ATAPP.timer);ATAPP.timer=setInterval(atRefresh,3000);}
async function atRefresh(){if(!ATAPP.chat_id)return;
 let r=await atApi('/api/artichokes/game?chat_id='+encodeURIComponent(ATAPP.chat_id)+'&init_data='+encodeURIComponent(ATAPP.init));
 if(r.ok){ATAPP.board=r.game;ATAPP.err='';atAutoLog();
  let sig=JSON.stringify(ATAPP.board);
  if(sig===ATAPP.sig)return;
  ATAPP.sig=sig;atRender();}
 else if(ATAPP.board){ATAPP.err=r.error||'game not found';atRender();}}
function atAutoLog(){let b=ATAPP.board;if(!b||!b.events)return;b.events.forEach(e=>atLog(e));delete b.events;}
async function atMove(action,extra){
 let body=Object.assign({chat_id:ATAPP.chat_id,action:action,init_data:ATAPP.init},extra||{});
 let r=await atApi('/api/artichokes/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.events)r.events.forEach(e=>atLog(e));
  ATAPP.err=r.error||'';if(r.error)atLog('⛔ '+r.error);
  if(!r.error){ATAPP.sel=[];ATAPP.pass.clear();}
  if(r.game){ATAPP.board=r.game;delete ATAPP.board.events;ATAPP.sig=JSON.stringify(ATAPP.board);}
  if(ATAPP.board)atRender();}

function atCard(c,cls,extra){
 let num=AT_SPRITE[c.v];if(num===undefined)num=AT_SPRITE.back;
 let name=atCardName(c.v||'').toUpperCase(),desc=atCardDesc(c);
 let light=['beet','broccoli','eggplant','artichoke'].indexOf(c.v)>=0;
 let art=c.v==='artichoke'?' artichoke':'';
 return '<div class="atcard '+cls+'" data-at-card-id="'+escapeHtml(String(c.id))+'" data-at-v="'+escapeHtml(String(c.v))+'"'+(extra||'')+'>'+
  '<img class="atart" src="/assets/artichokes/images/artichokes_cards/'+num+'.jpg?v='+AT_VER+'" alt="'+escapeHtml(name)+'">'+
  '<div class="atname'+art+'" style="color:'+(AT_COLOR[c.v]||'#fff')+'">'+escapeHtml(name)+'</div>'+
  '<div class="atdesc'+(light?' light-text':'')+'"><span>'+escapeHtml(desc)+'</span></div></div>';}
function atPlayer(p,i,b){
 let bits=[];
 if(b.phase!=='lobby'&&i===b.actor)bits.push('👉');
 if(p.npc)bits.push('🤖');
 return '<div class="atseat'+(i===b.actor?' atcurrent':'')+'" data-at-seat="'+i+'">'+
  '<div class="atseatname">'+bits.join(' ')+' '+escapeHtml(p.name)+'</div>'+
  '<div class="small">🥬 <span class="atcount" data-at-count="'+i+':artichokes">'+p.artichokes+'</span> · '+
  '✋ <span class="atcount" data-at-count="'+i+':hand">'+p.hand_count+'</span> · '+
  '🎴 <span class="atcount" data-at-count="'+i+':deck">'+p.deck+'</span> · '+
  '♻️ <span class="atcount" data-at-count="'+i+':discard">'+p.discard+'</span></div></div>';}
function atToggle(list,v){let i=list.indexOf(v);if(i<0)list.push(v);else list.splice(i,1);}
function atCounts(b){
 let out={};
 (b.players||[]).forEach((p,i)=>{
  out[i+':artichokes']=p.artichokes;
  out[i+':hand']=p.hand_count;
  out[i+':deck']=p.deck;
  out[i+':discard']=p.discard;
 });
 return out;}
function atSnapshot(b){
 return {phase:b.phase,actor:b.actor,
  garden_row:(b.garden_row||[]).map(c=>({id:c.id,v:c.v})),counts:atCounts(b)};}
function atOldRects(){
 let out={cards:{},seats:{}};
 document.querySelectorAll('.atcard[data-at-card-id]').forEach(el=>{
  out.cards[String(el.dataset.atCardId)]=el.getBoundingClientRect();});
 document.querySelectorAll('[data-at-seat]').forEach(el=>{
  out.seats[el.dataset.atSeat]=el.getBoundingClientRect();});
 return out;}
function atBumpCounts(oldCounts,newCounts){
 document.querySelectorAll('[data-at-count]').forEach(el=>{
  let k=el.dataset.atCount;
  if(oldCounts[k]!==undefined&&oldCounts[k]!==newCounts[k]){
   el.classList.remove('atbump');void el.offsetWidth;el.classList.add('atbump');}
 });}
function atFlyHarvest(card,from,to){
 if(!from||!to||AT_SPRITE[card.v]===undefined)return;
 let img=document.createElement('img');
 img.className='atfly';
 img.src='/assets/artichokes/images/artichokes_cards/'+AT_SPRITE[card.v]+'.jpg?v='+AT_VER;
 let cx=from.left+from.width/2,cy=from.top+from.height/2;
 let tx=to.left+to.width/2,ty=to.top+to.height/2;
 img.style.left=from.left+'px';img.style.top=from.top+'px';
 img.style.width=from.width+'px';img.style.height=from.height+'px';
 document.body.appendChild(img);
 requestAnimationFrame(()=>{
  img.style.transform='translate('+(tx-cx)+'px,'+(ty-cy)+'px) scale(.16) rotate(12deg)';
  img.style.opacity='.15';});
 setTimeout(()=>img.remove(),700);}
function atRender(){
 let b=ATAPP.board;if(!b)return;
 let old=ATAPP.prevBoard,rects=atOldRects(),oldCounts=old&&old.counts||{};
 let scroll=window.PXSCROLL?window.PXSCROLL.save(['#atBoard .atrowcards','#atHand .athand']):null;
 let turn=document.getElementById('atTurn'),board=document.getElementById('atBoard'),
  actions=document.getElementById('atActions'),hand=document.getElementById('atHand'),
  choice=document.getElementById('atChoice');
 let winner=b.players.find(p=>p.user_id===b.winner_id);
 if(b.phase==='lobby')turn.textContent='🥬 Lobby — '+b.players.length+'/4 players';
 else if(b.phase==='game_end')turn.textContent='🏆 '+(winner?escapeHtml(winner.name):'Someone')+' abandoned all artichokes!';
 else if(b.phase==='harvest')turn.textContent='🌱 '+(b.can_act?'Your turn':'Waiting for '+escapeHtml((b.players[b.actor]||{}).name||'player'))+' — harvest one card';
 else if(b.pending)turn.textContent='⚡ '+(b.can_act?'Choose':'Waiting for '+escapeHtml((b.players[b.pending.by]||{}).name||'player'))+' — '+b.pending.prompt;
  else turn.textContent='🎴 '+(b.can_act?'Your turn':'Waiting for '+escapeHtml((b.players[b.actor]||{}).name||'player'))+' — play vegetables (auto-skips when none remain)';
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
   let need=Math.min(2,opts.length),n=ATAPP.pass.size;
   choice.innerHTML='<div class="table"><b>'+escapeHtml(pend.prompt)+'</b>'+
    '<div class="small">Selected '+n+' / '+need+'</div><div class="atchoices">'+
    opts.map(o=>{
     let on=ATAPP.pass.has(String(o.v));
      return '<button class="atchoice'+(on?' atsel':'')+'" data-at-pass="'+escapeHtml(String(o.v))+'">'+atChoiceCard(o.label)+'<span>'+escapeHtml(o.label)+'</span></button>';
    }).join('')+'</div>'+(b.can_act?'<button class="hit" id="atPassGo"'+(n!==need?' disabled':'')+'>✅ Pass selected ('+n+'/'+need+')</button>':'')+'</div>';
  }else{
   // FB-0088: show the cards revealed by Peas (name + description) above
   // the choice, so the chooser can see both cards while picking who
   // receives the other one. pending.revealed comes from the board JSON.
   let revealed='';
   if(pend.revealed){
    let cards=Array.isArray(pend.revealed)?pend.revealed:[pend.revealed];
    if(cards.length)revealed='<div class="atrowcards">'+cards.map(c=>atCard(c,'atrowcard')).join('')+'</div>';
   }
   choice.innerHTML='<div class="table"><b>'+escapeHtml(pend.prompt)+'</b>'+revealed+'<div class="atchoices">'+
     opts.map(o=>{
      let d=atChoiceDesc(o.label);
      return '<button class="atchoice" data-at-ch="'+escapeHtml(String(o.v))+'">'+atChoiceCard(o.label)+
       '<span style="display:flex;flex-direction:column;align-items:flex-start;text-align:left;gap:1px"><span>'+escapeHtml(o.label)+'</span>'+
       (d?'<span style="font-weight:400;font-size:11px;line-height:1.25;opacity:.85">'+escapeHtml(d)+'</span>':'')+'</span></button>';
     }).join('')+'</div></div>';
  }
 }
  let a='';
  if(b.phase==='lobby'){
  if(!b.is_player)a+='<button class="primary" id="atJoin">🙋 Join</button>';
  if(b.players.length>=2)a+='<button class="primary" id="atStart">🎮 Start game</button>';
  a+='<button class="primary" id="atHowTo">🎥 How to play</button>';
 }else if(b.phase==='game_end'){
  a+='<button class="primary" id="atRematch">🔄 Rematch!</button>';
 }else if(b.can_act&&!b.pending){
  if(b.phase==='harvest')a+='<button class="stay" id="atSkip">⏭ Skip harvest</button>';
  else{a+='<button class="hit" id="atPlay">🃏 Play selected ('+ATAPP.sel.length+')</button>'+
        '<button class="stay" id="atEnd">🏁 End turn</button>';}
 }
  actions.innerHTML=a;
  if(ATAPP.err)choice.innerHTML+='<div class="lobby-note">⛔ '+escapeHtml(ATAPP.err)+'</div>';
  let fresh=atSnapshot(b);
  if(old){
   atBumpCounts(oldCounts,fresh.counts);
   if(old.phase==='harvest'&&b.phase==='play'){
    let newIds=(b.garden_row||[]).map(c=>String(c.id));
    let gone=(old.garden_row||[]).find(c=>newIds.indexOf(String(c.id))<0);
    if(gone)atFlyHarvest(gone,rects.cards[String(gone.id)],rects.seats[String(b.actor)]);
   }
  }
  ATAPP.prevBoard=fresh;
  if(window.PXSCROLL)window.PXSCROLL.restore(scroll);
}
(function atEvents(){
 document.addEventListener('click',e=>{
  let t=e.target.closest('[data-at-h],[data-at-p],[data-at-ch],[data-at-pass]');
  if(!t)return;
  if(t.hasAttribute('data-at-h'))return atMove('harvest',{pos:parseInt(t.dataset.atH,10)});
  if(t.hasAttribute('data-at-p')){atToggle(ATAPP.sel,parseInt(t.dataset.atP,10));atRender();return;}
  if(t.hasAttribute('data-at-ch'))return atMove('choose',{choice:/^-?\d+$/.test(t.dataset.atCh)?parseInt(t.dataset.atCh,10):t.dataset.atCh});
  if(t.hasAttribute('data-at-pass')){
   let v=t.dataset.atPass,opts=(ATAPP.board&&ATAPP.board.pending&&ATAPP.board.pending.options)||[];
   let need=Math.min(2,opts.length);
   if(ATAPP.pass.has(v))ATAPP.pass.delete(v);
   else if(ATAPP.pass.size<need)ATAPP.pass.add(v);
   atRender();return;}
 });
 document.addEventListener('click',e=>{
   let id=e.target.id;
   if(id==='atJoin')return atMove('join');
  if(id==='atStart')return atMove('start');
  if(id==='atHowTo'){
   try {
    if (window.Telegram && Telegram.WebApp && Telegram.WebApp.openLink)
     Telegram.WebApp.openLink(AT_HOW_TO_PLAY_URL);
    else window.open(AT_HOW_TO_PLAY_URL, '_blank');
   } catch (e) { window.open(AT_HOW_TO_PLAY_URL, '_blank'); }
   return;
  }
  if(id==='atRematch')return atMove('rematch');
  if(id==='atSkip')return atMove('skip');
  if(id==='atPlay'){if(!ATAPP.sel.length){ATAPP.err='Select a card first.';atRender();return;}
   return atMove('play',{iid:ATAPP.sel[0]});}
  if(id==='atEnd')return atMove('end');
  if(id==='atPassGo'){
   let opts=(ATAPP.board&&ATAPP.board.pending&&ATAPP.board.pending.options)||[];
   let need=Math.min(2,opts.length);
   if(ATAPP.pass.size!==need){ATAPP.err='Select '+need+' cards.';atRender();return;}
   return atMove('pass',{ids:Array.from(ATAPP.pass)});}
 });
 })();
(function atStart(){if(document.getElementById('atBoard'))atLoad();})();
