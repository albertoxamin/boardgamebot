// Castle Combo Mini App (synced, initData auto-login). Loaded by flip7.html router.
const CCAPP={user_id:0,chat_id:null,board:null,timer:null,init:'',err:''};
const CC_SHEET='/castlecombo-cards.webp';
// BGA sprite sheet: 10 cols x 8 rows, cell 286x400 served at 132x186.
// Card id == sprite position t (1-39 Castle, 41-79 Village; t0/t40 = backs).
// col=t%10, row=floor(t/10). Display cell 44x62; zoom 132x186.
function ccPos(t,s){const c=t%10,r=Math.floor(t/10);
 return "background-image:url('"+CC_SHEET+"');background-size:"+(440*s)+"px "+(496*s)+"px;background-position:"+(-c*44*s)+"px "+(-r*62*s)+"px";}
function ccArt(cid,fd,loc,s){
 const t=!cid?(loc===1?0:40):cid;
 return ccPos(t,s||1);}
function ccTile(cid,fd,loc,s,extra){
 return '<div class="cctile'+(fd?' ccfd':'')+'" style="'+ccArt(cid,fd,loc,s||1)+'"'+(extra||'')+'></div>';}
// Registry for the zoom view: data-key -> card JSON of the last render.
const CC_CARDS={};
function ccKey(c){return 'k'+c.iid+'_'+c.cid;}
function ccTileData(c){
 CC_CARDS[ccKey(c)]=c;
 return ccTile(c.cid,c.fd,c.loc,1,' data-key="'+ccKey(c)+'"');}
function ccLog(s){let e=document.getElementById('ccLog');if(e)e.textContent+=s+'\n';}
function ccApi(path,opts){return fetch(path,opts).then(r=>r.json());}
function ccChatId(raw){let s=String(raw||'');if(s.startsWith('castlecombo'))s=s.slice(11);
 let n=parseInt(s,10);return isNaN(n)?0:n;}
async function ccLoad(){
 let tg=tgInit();
 let board=document.getElementById('ccBoard');
 if(!tg.id){board.innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot\'s Castle Combo link.</div>';return;}
 CCAPP.user_id=tg.id; CCAPP.init=tg.init;
 let pref=ccChatId(tg.start)||ccChatId(new URLSearchParams(location.search).get('app'));
 let r=await ccApi('/api/castlecombo/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 let cands=mine.slice().sort((a,b)=>((a.phase==='game_end')-(b.phase==='game_end')) ||
  ((b.players?b.players.length:0)-(a.players?a.players.length:0)));
 let pick=cands.find(g=>g.chat_id===pref)||cands[0];
 if(pick){ccSelect(pick.chat_id);return;}
 if(!pref){board.innerHTML='<div class="table lobby-note">No Castle Combo game for you yet — send /castlecombo in a chat, then open its Mini App link.</div>';return;}
 let spec=await ccApi('/api/castlecombo/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
 if(spec.ok&&spec.game){ccSelect(pref);return;}
 let cr=await ccApi('/api/castlecombo/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});
 if(cr.game){ccSelect(cr.game.chat_id);return;}
 CCAPP.err=cr.error||'could not create the game';
 board.innerHTML='<div class="table lobby-note">⛔ '+escapeHtml(CCAPP.err)+'</div>';
}
async function ccSelect(chat_id){CCAPP.chat_id=chat_id; CCAPP.err=''; await ccRefresh();
 if(CCAPP.timer)clearInterval(CCAPP.timer); CCAPP.timer=setInterval(ccRefresh,3000);}
async function ccRefresh(){ if(!CCAPP.chat_id)return;
 let r=await ccApi('/api/castlecombo/game?chat_id='+encodeURIComponent(CCAPP.chat_id)+'&init_data='+encodeURIComponent(CCAPP.init));
 if(r.ok){CCAPP.board=r.game; CCAPP.err=''; ccRender();}
 else if(CCAPP.board){CCAPP.err=r.error||'game not found'; ccRender();}}
async function ccMove(action,extra){
 let body=Object.assign({chat_id:CCAPP.chat_id,action:action,init_data:CCAPP.init},extra||{});
 let r=await ccApi('/api/castlecombo/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.events)r.events.forEach(e=>ccLog(e));
 CCAPP.err=r.error||''; if(r.error)ccLog('⛔ '+r.error);
 if(r.game)CCAPP.board=r.game;
 if(CCAPP.board)ccRender();}
function ccZoomClose(){let z=document.getElementById('ccZoom');if(z){z.classList.remove('open');z.innerHTML='';}}
function ccZoom(key){
 let c=CC_CARDS[key]; if(!c)return;
 let z=document.getElementById('ccZoom');
 let flags=[];
 if(c.mm)flags.push('🚩 moves the messenger');
 if(c.purse)flags.push('💰 purse '+c.purse);
 if(c.disc)flags.push('🏷️ -1 '+(c.disc===1?'Castle':c.disc===2?'Village':''));
 z.innerHTML='<div class="cczcard"><div class="cctile zcard-big" style="'+ccArt(c.cid,c.fd,c.loc,3)+'"></div></div>'+
  '<div class="cczdesc"><b>'+escapeHtml(c.name)+'</b> · '+c.cost+'g'+
  (flags.length?' · '+flags.join(' · '):'')+
  '<div class="small" style="margin-top:6px">'+escapeHtml(c.txt||'')+'</div></div>';
 z.classList.add('open');
}
// ---- render
function ccRowDisplay(b,locName,loc,myTurn){
 let sec=b.rows[String(loc)];
 let cards=(sec&&sec.live)?(sec.cards||[]):null;
 let h='<div class="table"><div class="small">'+locName+' '+(cards?'':'(out of cards)')+'</div><div class="ccrow">';
 if(cards){
  cards.forEach(c=>{
   h+='<div class="ccslot">'+ccTileData(c)+
    '<div class="cccbtns">';
   if(myTurn&&!b.pending){
    h+='<button class="hit ccbuy" data-buy="'+c.iid+'">🛒 '+c.cost+'g</button>'+
       '<button class="stay ccflip" data-flip="'+c.iid+'">🔄</button>';
   }
   h+='</div></div>';
   });
 } else {
  h+='<div class="small">—</div>';
 }
 return h+'</div></div>';
}
function ccGrid(p){
 if(!p.tableau||!p.tableau.length)return '<div class="ccgrid empty"></div>';
 let xs=p.tableau.map(c=>c.x),ys=p.tableau.map(c=>c.y);
 let x0=Math.min.apply(null,xs),x1=Math.max.apply(null,xs),y0=Math.min.apply(null,ys),y1=Math.max.apply(null,ys);
 let h='<div class="ccgrid" style="grid-template-columns:repeat('+(x1-x0+1)+',44px)">';
 for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){
  let c=p.tableau.find(c=>c.x===x&&c.y===y);
  if(!c){h+='<div class="cctile ccempty"></div>';continue;}
  h+='<div class="ccwrap">'+ccTileData(c)+
   (c.gold?'<span class="ccgold">💰'+c.gold+'</span>':'')+
   '</div>';
 }
 return h+'</div>';
}
function ccRender(){
 let b=CCAPP.board; if(!b)return;
 let t=document.getElementById('ccTurn'), board=document.getElementById('ccBoard');
 let cur=b.actor!=null?b.players[b.actor]:null;
 let isActor=b.actor!=null&&(cur.user_id===CCAPP.user_id||cur.npc);
 let myTurn=b.can_act&&!b.pending;
 let parts=[];
 if(b.phase==='lobby'){
  t.textContent='🪑 Lobby - '+b.players.length+'/'+b.max_players+' players';
  parts.push('<div class="table"><div class="small">Players</div>'+b.players.map(p=>'<div>'+escapeHtml(p.name)+(p.npc?' 🤖':'')+(p.user_id===CCAPP.user_id?' (you)':'')+'</div>').join('')+
   '<div class="lobby-note">Friends join in Telegram, then anyone taps Start.</div></div>');
 } else if(b.phase==='game_end'){
  t.textContent='🏆 Game over!';
  if(b.winner!=null){let w=b.players[b.winner]; parts.push('<div class="table lobby-note">Winner: <b>'+escapeHtml(w.name)+'</b>!</div>');}
  else parts.push('<div class="table lobby-note">It\'s a draw!</div>');
  if(b.results)parts.push('<div class="table"><div class="small">Final scores</div>'+
   b.results.map(r=>'<div>'+escapeHtml(r.name)+' — <b>'+r.score+'</b> pts'+(r.leftover?' ('+r.leftover+'g tiebreak)':'')+'</div>').join('')+'</div>');
 } else {
  let mloc=b.messenger===1?'🏰 Castle':'🏘️ Village';
  t.textContent=isActor?(b.pending?'👉 Your choice':'👉 Your turn — take from '+mloc):(cur?'👉 '+escapeHtml(cur.name)+'\'s turn':'…');
  if(b.pending){
   let pp=b.pending.player!=null?b.players[b.pending.player]:null;
   let mine=pp&&(pp.user_id===CCAPP.user_id||pp.npc);
   if(!mine)parts.push('<div class="table"><div class="lobby-note">'+escapeHtml(b.pending.prompt)+
    (pp?' <i>(waiting for '+escapeHtml(pp.name)+')</i>':'')+'</div></div>');
   else parts.push('<div class="table"><div class="small">'+escapeHtml(b.pending.prompt)+'</div><div class="ccopts">'+
    b.pending.options.map(o=>'<button class="hit" data-choose="'+escapeHtml(String(o.v))+'">'+escapeHtml(o.label)+'</button>').join('')+'</div></div>');
  }
  parts.push(ccRowDisplay(b,'🏰 Castle display',1,myTurn));
  parts.push(ccRowDisplay(b,'🏘️ Village display',2,myTurn));
  if(myTurn&&(b.players[b.actor].keys>0))parts.push('<div class="table"><div class="ccopts">'+
   '<button class="stay" data-move="1">🔑 Move messenger</button>'+
   '<button class="stay" data-renew="1">🔑 Renew display</button></div></div>');
  let ph='<div class="table"><div class="small">Players · round '+b.round+'/9</div><div class="ftplayers">';
  b.players.forEach((p,i)=>{
   ph+='<div class="ftpc'+(p.is_current?' current':'')+'"><div style="display:flex;justify-content:space-between"><b>'+escapeHtml(p.name)+(p.npc?' 🤖':'')+'</b><span class="score">'+p.gold+'💰 '+p.keys+'🔑 · '+p.cards+'/9</span></div>'+ccGrid(p)+'</div>';
  });
  ph+='</div></div>'; parts.push(ph);
 }
 if(CCAPP.err)parts.unshift('<div class="table lobby-note">⛔ '+escapeHtml(CCAPP.err)+'</div>');
 board.innerHTML=parts.join('');
 document.getElementById('ccJoin').classList.toggle('hidden',!(b.phase==='lobby'&&!b.is_player));
 document.getElementById('ccStart').classList.toggle('hidden',!(b.phase==='lobby'&&b.is_player));
 document.getElementById('ccRematch').classList.toggle('hidden',!(b.phase==='game_end'&&b.is_player));
 board.querySelectorAll('[data-buy]').forEach(el=>el.addEventListener('click',ev=>{ev.stopPropagation();ccMove('buy',{iid:parseInt(el.dataset.buy)});}));
 board.querySelectorAll('[data-flip]').forEach(el=>el.addEventListener('click',ev=>{ev.stopPropagation();ccMove('flip',{iid:parseInt(el.dataset.flip)});}));
 board.querySelectorAll('[data-choose]').forEach(el=>el.addEventListener('click',()=>ccMove('choose',{choice:el.dataset.choose})));
 board.querySelectorAll('[data-move]').forEach(el=>el.addEventListener('click',()=>ccMove('move')));
 board.querySelectorAll('[data-renew]').forEach(el=>el.addEventListener('click',()=>ccMove('renew')));
 // zoom on display/tableau tiles (skip face-down + empties)
 board.querySelectorAll('.cctile[data-key]:not(.ccfd)').forEach(el=>{
  el.addEventListener('click',()=>ccZoom(el.dataset.key));
 });
}
document.getElementById('ccJoin').addEventListener('click',()=>ccMove('join'));
document.getElementById('ccStart').addEventListener('click',()=>ccMove('start'));
document.getElementById('ccRematch').addEventListener('click',()=>ccMove('rematch'));
document.getElementById('ccZoom').addEventListener('click',ccZoomClose);
if(!document.getElementById('castlecombo').classList.contains('hidden')) ccLoad();
