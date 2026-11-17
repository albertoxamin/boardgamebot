// Castle Combo Mini App (synced, initData auto-login). Loaded by flip7.html router.
const CCAPP={user_id:0,chat_id:null,board:null,timer:null,init:'',err:''};
const CC_SHEET='/castlecombo-cards.webp';
// BGA sprite sheet: 10 cols x 8 rows, cell 286x400 served at 132x186.
// Card id == sprite position t (1-39 Castle, 41-79 Village; t0/t40 = backs).
// col=t%10, row=floor(t/10). BGA renders cards 143x200 (bg-size auto 800%);
// our base tile 66x93 (bg 660x744), zoom 132x186 (bg 1320x1488).
function ccPos(t,s){const c=t%10,r=Math.floor(t/10);
 return "background-image:url('"+CC_SHEET+"');background-size:"+(660*s)+"px "+(744*s)+"px;background-position:"+(-c*66*s)+"px "+(-r*93*s)+"px";}
function ccArt(cid,fd,loc,s){
 const t=!cid?(loc===1?0:40):cid;
 return ccPos(t,s||1);}
// Registry for the zoom view: data-key -> card JSON of the last render.
const CC_CARDS={};
// BGA icon position indexes (position-icons.png, 9 columns)
const CC_POS_IDX={'0':0,'123':1,'456':2,'789':3,'147':4,'258':5,'369':6,'1379':7,'2468':8};
function ccIcon(o){
 switch(o.i){
  case 'gold':return '<span class="ccicon" style="width:16.8cqw;height:16.8cqw;background-image:url(/cc-icons/gold-icons.png);background-size:67.2cqw 16.8cqw;background-position-x:'+(o.q*33.333)+'%"></span>';
  case 'key':return '<span class="ccicon" style="width:16.8cqw;height:16.8cqw;background-image:url(/cc-icons/key-icons.png);background-size:33.6cqw 16.8cqw"></span>';
  case 'sh':return '<span class="ccicon" style="width:16.8cqw;height:13.6cqw;background-image:url(/cc-icons/shield-icons.png);background-size:100% auto;background-position-y:'+(o.c*16.6667)+'%"></span>';
  case 'dir':return '<span class="ccicon" style="width:26.7cqw;height:24.7cqw;background-image:url(/cc-icons/direction-shield-icons.png);background-size:300% 700%;background-position:'+(o.k==='line'?0:o.k==='col'?'50%':'100%')+' '+(o.c*16.6667)+'%"></span>';
  case 'pos':return '<span class="ccicon" style="width:14.2cqw;height:16.8cqw;background-image:url(/cc-icons/position-icons.png);background-size:127.8cqw 16.8cqw;background-position-x:'+(CC_POS_IDX[String(o.t)]*12.5)+'%"></span>';
  case 'pt':{const qs=[-1,1,2,3,4,5,6,7,8,9,10,12];const i=qs.indexOf(o.q);
   return '<span class="ccicon" style="width:22.4cqw;height:22.4cqw;background-image:url(/cc-icons/point-icons.png);background-size:268.8cqw 22.4cqw;background-position-x:'+(i*100/11)+'%"></span>';}
  case 'ban':return '<span class="ccicon" style="width:'+(o.t===12?40:22.4)+'cqw;height:22.4cqw;background-image:url(/cc-icons/card-type-icons.png);background-size:auto 400%;background-position-y:'+((o.t===1?0:o.t===2?1:2)*33.333)+'%"></span>';
  case 'disc':return '<span class="ccicon" style="width:67.1cqw;height:19.9cqw;background-image:url(/cc-icons/discount-icons.png);background-size:300% 100%;background-position-x:'+(o.t===1?0:o.t===2?50:100)+'%"></span>';
  case 'purse':return '<span class="ccicon" style="width:16.8cqw;height:16.8cqw;background-image:url(/cc-icons/card-icons.png);background-size:151.2cqw 16.8cqw"></span>';
  case 'flip':return '<span class="ccicon" style="width:16.8cqw;height:16.8cqw;background-image:url(/cc-icons/card-icons.png);background-size:151.2cqw 16.8cqw;background-position-x:87.5%"></span>';
  case 'shset':return '<span class="ccicon" style="width:33.6cqw;height:10.5cqw;background-image:url(/cc-icons/shields-icons.png);background-size:100% auto;background-position-y:'+(o.t*20)+'%"></span>';
  case 'card':{const col=o.t==='cost'?(o.v===-1?1:o.v===0?2:o.v===4?3:o.v===5?4:2):0;
   return '<span class="ccicon" style="width:16.8cqw;height:16.8cqw;background-image:url(/cc-icons/card-icons.png);background-size:151.2cqw 16.8cqw;background-position-x:'+(col*12.5)+'%"></span>';}
 }
 return '';
}
function ccSegs(line){
 return line.map(s=>s.i!==undefined?ccIcon(s):'<span class="ccseg">'+escapeHtml(String(s.t))+'</span>').join('');
}
function ccFace(cid,gold){
 const f=CC_FACES[String(cid)]; if(!f)return '';
 let h='<div class="ccface">';
 if(gold)h+='<div class="ccgoldc">'+ccIcon({i:'gold',q:Math.min(gold,3)})+(gold>3?'<b class="ccgn">'+gold+'</b>':'')+'</div>';
 h+='<div class="ccname'+(f.mm?' ccmn':'')+'"><span>'+escapeHtml(f.n)+'</span></div>';
 h+='<div class="ccabs">'+f.ab.map(l=>'<div class="ccab">'+ccSegs(l)+'</div>').join('')+'</div>';
 h+='<div class="ccsc">'+f.sc.map(l=>'<div class="ccab">'+ccSegs(l)+'</div>').join('')+'</div>';
 return h+'</div>';
}
// Shrink-to-fit pass for card names (approximates BGA bga-autofit).
function ccFit(root){
 if(!root||!root.querySelectorAll)return;
 root.querySelectorAll('.ccname span').forEach(el=>{
  el.style.fontSize='';
  let box=el.parentNode, fs=parseFloat(getComputedStyle(el).fontSize)||8;
  for(let i=0;i<14;i++){
   if(el.scrollWidth<=box.clientWidth+1&&el.scrollHeight<=box.clientHeight+1)break;
   fs*=0.93;el.style.fontSize=fs+'px';
  }
 });
}
function ccKey(c){return 'k'+c.iid+'_'+c.cid;}
function ccTileData(c){
 CC_CARDS[ccKey(c)]=c;
 return ccTile(c.cid,c.fd,c.loc,1,' data-key="'+ccKey(c)+'"',c.gold);}
function ccTile(cid,fd,loc,s,extra,gold){
 return '<div class="cctile'+(fd?' ccfd':'')+'" style="'+ccArt(cid,fd,loc,s||1)+'"'+(extra||'')+'>'+
  (fd?'':ccFace(cid,gold||0))+'</div>';}
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
 z.innerHTML='<div class="cczcard"><div class="cctile zcard-big" style="'+ccArt(c.cid,c.fd,c.loc,2)+'">'+(c.fd?'':ccFace(c.cid,0))+'</div></div>'+
  '<div class="cczdesc"><b>'+escapeHtml(c.name)+'</b> · '+c.cost+'g'+
  (flags.length?' · '+flags.join(' · '):'')+
  '<div class="small" style="margin-top:6px">'+escapeHtml(c.txt||'')+'</div></div>';
 z.classList.add('open');
}
// ---- render
function ccRowDisplay(b,locName,loc,myTurn){
 let sec=b.rows[String(loc)];
 let cards=(sec&&sec.live)?(sec.cards||[]):null;
 let h='<div class="table"><div class="small">'+locName+' '+(cards?'':'(out of cards)')+'</div><div class="ccrowflex">'+
  (b.messenger===loc?'<img class="ccmsgr" src="/castlecombo-messenger.png" alt="messenger">':'')+
  '<div class="ccrow">';
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
 return h+'</div></div></div>';
}
function ccGrid(p){
 if(!p.tableau||!p.tableau.length)return '<div class="ccgrid empty"></div>';
 let xs=p.tableau.map(c=>c.x),ys=p.tableau.map(c=>c.y);
 let x0=Math.min.apply(null,xs),x1=Math.max.apply(null,xs),y0=Math.min.apply(null,ys),y1=Math.max.apply(null,ys);
 let h='<div class="ccgrid" style="grid-template-columns:repeat('+(x1-x0+1)+',66px)">';
 for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){
  let c=p.tableau.find(c=>c.x===x&&c.y===y);
  if(!c){h+='<div class="cctile ccempty"></div>';continue;}
  h+='<div class="ccwrap">'+ccTileData(c)+'</div>';
 }
 return h+'</div>';
}
// BGA-style end-game score sheet: background art with printed labels
// (entries 1..9, keys, total); our table overlays the player columns.
function ccScoreSheet(b){
 let rs=b.results;
 let nameW=Math.min(97, Math.round(420/Math.max(rs.length,1)));
 let h='<div class="ccsheet"><table class="ccsheet-t" style="--csnw:'+nameW+'px">'+
  '<tr><th class="ccsheet-corner"></th>'+
  rs.map(r=>'<th class="ccsheet-pname">'+escapeHtml(r.name)+'</th>').join('')+'</tr>';
 for(let i=1;i<=9;i++){
  h+='<tr><th class="ccsheet-lbl"></th>'+
   rs.map(r=>'<td class="ccsheet-entry'+(i===9?' ccsheet-last':'')+'">'+((r.entries&&r.entries[i-1])||0)+'</td>').join('')+'</tr>';
 }
 h+='<tr><th class="ccsheet-lbl"></th>'+
  rs.map(r=>'<td class="ccsheet-entry ccsheet-keys">'+(r.keys?('🗝️'+r.keys):'')+'</td>').join('')+'</tr>'+
  '<tr><th class="ccsheet-lbl ccsheet-totlbl"></th>'+
  rs.map(r=>'<td class="ccsheet-entry ccsheet-total'+(r.idx===b.winner?' ccsheet-win':'')+'">'+r.score+'</td>').join('')+'</tr>'+
  '</table></div>';
 return h;
}
// Clickable placement grid: the pending player's tableau extended by one
// ring, with the valid spots as dashed slots (pending.kind === 'place').
function ccPlaceGrid(b){
 let pend=b.pending,p=b.players[pend.player];
 let opts=pend.options.map(o=>{let a=String(o.v).split(',');return {x:+a[0],y:+a[1],v:o.v};});
 let xs=p.tableau.map(c=>c.x),ys=p.tableau.map(c=>c.y);
 let x0=Math.min.apply(null,xs)-1,x1=Math.max.apply(null,xs)+1;
 let y0=Math.min.apply(null,ys)-1,y1=Math.max.apply(null,ys)+1;
 if(!p.tableau.length){x0=x1=0;y0=y1=0;}
 let h='<div class="table"><div class="small">'+escapeHtml(pend.prompt)+' — tap a dashed slot</div>'+
  '<div class="ccgrid" style="grid-template-columns:repeat('+(x1-x0+1)+',66px)">';
 for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){
  let c=p.tableau.find(c=>c.x===x&&c.y===y);
  if(c){h+='<div class="ccwrap">'+ccTileData(c)+'</div>';continue;}
  let o=opts.find(o=>o.x===x&&o.y===y);
  h+=o?'<div class="ccspot" data-choose="'+escapeHtml(o.v)+'" title="place here"></div>'
     :'<div class="cctile ccempty ccghost"></div>';
 }
 return h+'</div></div>';
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
  if(b.results&&b.results[0].entries)parts.push(ccScoreSheet(b));
  else if(b.results)parts.push('<div class="table"><div class="small">Final scores</div>'+
   b.results.map(r=>'<div>'+escapeHtml(r.name)+' — <b>'+r.score+'</b> pts'+(r.leftover?' ('+r.leftover+'g tiebreak)':'')+'</div>').join('')+'</div>');
  if(b.results&&b.results.length>1)parts.push('<div class="table lobby-note small">Tiebreak: leftover gold</div>');
 } else {
  let mloc=b.messenger===1?'🏰 Castle':'🏘️ Village';
  t.textContent=isActor?(b.pending?'👉 Your choice':'👉 Your turn — take from '+mloc):(cur?'👉 '+escapeHtml(cur.name)+'\'s turn':'…');
  if(b.pending){
   let pp=b.pending.player!=null?b.players[b.pending.player]:null;
   let mine=pp&&(pp.user_id===CCAPP.user_id||pp.npc);
   if(!mine)parts.push('<div class="table"><div class="lobby-note">'+escapeHtml(b.pending.prompt)+
    (pp?' <i>(waiting for '+escapeHtml(pp.name)+')</i>':'')+'</div></div>');
   else if(b.pending.kind==='place')parts.push(ccPlaceGrid(b));
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
 ccFit(board);
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
