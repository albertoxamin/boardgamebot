// Castle Combo Mini App (synced, initData auto-login). Loaded by flip7.html router.

const CC_HOW_TO_PLAY_URL = 'https://youtu.be/W7D1JK_-HvU?si=sbc2HwRdyPHuV1p0';
const CCAPP={user_id:0,chat_id:null,board:null,timer:null,init:'',err:'',prev:null};
function ccCounts(b){let c={};(b.players||[]).forEach((p,i)=>{c['c:'+i+':gold']=p.gold;c['c:'+i+':keys']=p.keys;c['c:'+i+':cards']=p.cards;});return c;}
function ccZones(b){let z={};[1,2].forEach(loc=>{let sec=b.rows&&b.rows[String(loc)];if(sec&&sec.live)(sec.cards||[]).forEach(c=>z[ccKey(c)]='row:'+loc);});
 (b.players||[]).forEach((p,i)=>(p.tableau||[]).forEach(c=>z[ccKey(c)]='tableau:'+i));return z;}
function ccOldRects(){let m={};document.querySelectorAll('#ccBoard .cctile[data-key]').forEach(el=>{
 let zone=el.closest('.ccrow')?'row':el.closest('.ccgrid')?'tableau':'';
 m[el.dataset.key]={rect:el.getBoundingClientRect(),zone:zone,html:el.outerHTML};});return m;}
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
  case 'gold':return '<span class="ccicon" style="width:2.545em;height:2.545em;background-image:url(/cc-icons/gold-icons.png);background-size:10.182em 2.545em;background-position-x:'+(o.q*33.333)+'%"></span>';
  case 'key':return '<span class="ccicon" style="width:2.545em;height:2.545em;background-image:url(/cc-icons/key-icons.png);background-size:5.091em 2.545em"></span>';
  case 'sh':return '<span class="ccicon" style="width:2.545em;height:2.061em;background-image:url(/cc-icons/shield-icons.png);background-size:100% auto;background-position-y:'+(o.c*16.6667)+'%"></span>';
  case 'dir':return '<span class="ccicon" style="width:4.045em;height:3.742em;background-image:url(/cc-icons/direction-shield-icons.png);background-size:300% 700%;background-position:'+(o.k==='line'?0:o.k==='col'?'50%':'100%')+' '+(o.c*16.6667)+'%"></span>';
  case 'pos':return '<span class="ccicon" style="width:2.152em;height:2.545em;background-image:url(/cc-icons/position-icons.png);background-size:19.364em 2.545em;background-position-x:'+(CC_POS_IDX[String(o.t)]*12.5)+'%"></span>';
  case 'pt':{const qs=[-1,1,2,3,4,5,6,7,8,9,10,12];const i=qs.indexOf(o.q);
   return '<span class="ccicon" style="width:3.394em;height:3.394em;background-image:url(/cc-icons/point-icons.png);background-size:40.727em 3.394em;background-position-x:'+(i*100/11)+'%"></span>';}
  case 'ban':return '<span class="ccicon" style="width:'+(o.t===12?6.061:3.394)+'em;height:3.394em;background-image:url(/cc-icons/card-type-icons.png);background-size:auto 400%;background-position-y:'+((o.t===1?0:o.t===2?1:2)*33.333)+'%"></span>';
  case 'disc':return '<span class="ccicon" style="width:10.167em;height:3.015em;background-image:url(/cc-icons/discount-icons.png);background-size:300% 100%;background-position-x:'+(o.t===1?0:o.t===2?50:100)+'%"></span>';
  case 'purse':return '<span class="ccicon" style="width:2.545em;height:2.545em;background-image:url(/cc-icons/card-icons.png);background-size:22.909em 2.545em"></span>';
  case 'flip':return '<span class="ccicon" style="width:2.545em;height:2.545em;background-image:url(/cc-icons/card-icons.png);background-size:22.909em 2.545em;background-position-x:87.5%"></span>';
  case 'shset':return '<span class="ccicon" style="width:5.091em;height:1.591em;background-image:url(/cc-icons/shields-icons.png);background-size:100% auto;background-position-y:'+(o.t*20)+'%"></span>';
  case 'card':{const col=o.t==='cost'?(o.v===-1?1:o.v===0?2:o.v===4?3:o.v===5?4:2):0;
   return '<span class="ccicon" style="width:2.545em;height:2.545em;background-image:url(/cc-icons/card-icons.png);background-size:22.909em 2.545em;background-position-x:'+(col*12.5)+'%"></span>';}
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
 root.querySelectorAll('.ccabs,.ccsc').forEach(box=>{
  let lines=box.querySelectorAll('.ccab');
  if(!lines.length)return;
  lines.forEach(el=>el.style.fontSize='');
  for(let i=0;i<16;i++){
   if(box.scrollHeight<=box.clientHeight+1 &&
      Array.prototype.every.call(lines,el=>el.scrollWidth<=el.clientWidth+1))break;
   lines.forEach(el=>{
    let fs=parseFloat(getComputedStyle(el).fontSize)||6;
    el.style.fontSize=Math.max(2,fs*0.9)+'px';
   });
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
 let qp=new URLSearchParams(location.search);
 let pref=ccChatId(tg.start)||ccChatId(qp.get('app'))||parseInt(qp.get('chat_id'),10)||0;
 if(!pref && tg.chat_instance) pref=parseInt(tg.chat_instance,10)||0;
 let r=await ccApi('/api/castlecombo/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 if(pref){
  let pick=mine.find(g=>g.chat_id===pref);
  if(!pick){
   let spec=await ccApi('/api/castlecombo/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
   if(spec.ok&&spec.game) pick={chat_id:pref};
  }
  if(pick){ccSelect(pick.chat_id);return;}
  let cr=await ccApi('/api/castlecombo/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});
  if(cr.game){ccSelect(cr.game.chat_id);return;}
  CCAPP.err=cr.error||'could not create the game';
  board.innerHTML='<div class="table lobby-note">⛔ '+escapeHtml(CCAPP.err)+'</div>';
  return;
 }
 let cands=mine.slice().sort((a,b)=>((a.phase==='game_end')-(b.phase==='game_end')) ||
  ((b.players?b.players.length:0)-(a.players?a.players.length:0)));
 if(cands.length){ccSelect(cands[0].chat_id);return;}
 board.innerHTML='<div class="table lobby-note">No Castle Combo game for you yet — send /castlecombo in a chat, then open its Mini App link.</div>';
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
 ccFit(z);
}
// ---- render
function ccRowDisplay(b,locName,loc,myTurn){
 let sec=b.rows[String(loc)];
 let cards=(sec&&sec.live)?(sec.cards||[]):null;
 let deck=sec?sec.deck:0, total=sec?sec.deck_total:0;
 let inactive=b.phase==='playing'&&b.messenger!==loc;
 let msg=b.messenger===loc?'<img class="ccmsgr" src="/castlecombo-messenger.png" alt="messenger">':'';
 let h='<div class="table"><div class="small">'+locName+' '+(cards?'':'(out of cards)')+'</div><div class="ccrowflex">'+
  '<div class="ccdeck'+(inactive?' ccinactive':'')+'" title="'+deck+' cards left in deck (of '+total+')">'+
   '<div class="cctile" style="'+ccArt(0,false,loc,1)+'"></div>'+
   '<div class="ccdecknum">'+deck+'<span>/'+total+'</span></div>'+msg+'</div>'+
  '<div class="ccrow'+(inactive?' ccinactive':'')+'">';
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
 let rs=b.results||[];
 let lefts=[38,86.5,135,183.5,232];
 let centers=[56.5,83.5,110.5,145.75,173,200,235.25,262.5,289.75];
 let h='<div class="ccsheet">';
 for(let j=0;j<5;j++)h+='<div class="ccsheet-cell ccsheet-pname" style="left:'+lefts[j]+'px;top:8px">'+
  (rs[j]?escapeHtml(rs[j].name):'')+'</div>';
 for(let i=0;i<9;i++)for(let j=0;j<5;j++)
  h+='<div class="ccsheet-cell ccsheet-entry'+(i===8?' ccsheet-last':'')+
   '" style="left:'+lefts[j]+'px;top:'+(centers[i]-11)+'px">'+
   (rs[j]&&rs[j].entries?rs[j].entries[i]:'')+'</div>';
 for(let j=0;j<5;j++)h+='<div class="ccsheet-cell ccsheet-entry ccsheet-keys" style="left:'+lefts[j]+'px;top:300.75px">'+
  (rs[j]&&rs[j].keys?'🗝️'+rs[j].keys:'')+'</div>';
 for(let j=0;j<5;j++)h+='<div class="ccsheet-cell ccsheet-total'+
  (rs[j]&&j===b.winner?' ccsheet-win':'')+'" style="left:'+lefts[j]+'px;top:338.75px">'+
  (rs[j]?rs[j].score:'')+'</div>';
 return h+'</div>';
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
 else{
  let minY=Math.min.apply(null,ys),maxY=Math.max.apply(null,ys);
  let minX=Math.min.apply(null,xs),maxX=Math.max.apply(null,xs);
  if(!opts.some(o=>o.y===y0))y0=minY;
  if(!opts.some(o=>o.y===y1))y1=maxY;
  if(!opts.some(o=>o.x===x0))x0=minX;
  if(!opts.some(o=>o.x===x1))x1=maxX;
 }
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
 let old=CCAPP.prev,rects=ccOldRects(),rectMem=Object.assign({},old&&old.rectMem||{},rects);
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
   ph+='<div class="ftpc'+(p.is_current?' current':'')+'"><div style="display:flex;justify-content:space-between"><b>'+escapeHtml(p.name)+(p.npc?' 🤖':'')+'</b><span class="score"><span data-fx-count="c:'+i+':gold">'+p.gold+'</span>💰 <span data-fx-count="c:'+i+':keys">'+p.keys+'</span>🔑 · <span data-fx-count="c:'+i+':cards">'+p.cards+'</span>/9</span></div>'+ccGrid(p)+'</div>';
  });
  ph+='</div></div>'; parts.push(ph);
 }
 if(CCAPP.err)parts.unshift('<div class="table lobby-note">⛔ '+escapeHtml(CCAPP.err)+'</div>');
 board.innerHTML=parts.join('');
 ccFit(board);
 document.getElementById('ccJoin').classList.toggle('hidden',!(b.phase==='lobby'&&!b.is_player));
 document.getElementById('ccStart').classList.toggle('hidden',!(b.phase==='lobby'&&b.is_player));
 document.getElementById('ccHowTo').classList.toggle('hidden', b.phase !== 'lobby');
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
  let fresh=ccCounts(b),zones=ccZones(b),zoneMem=Object.assign({},old&&old.zoneMem||{},old&&old.zones||{},zones);
  if(old){
   FX.bump(board,'data-fx-count',old.counts,fresh);
   board.querySelectorAll('.cctile[data-key]').forEach(el=>{let k=el.dataset.key,prev=(old.zones&&old.zones[k])||(old.zoneMem&&old.zoneMem[k]);
    if(prev&&prev.indexOf('row:')===0&&zones[k]&&zones[k].indexOf('tableau:')===0&&rectMem[k])
     FX.tile(rectMem[k].html,rectMem[k].rect,el.getBoundingClientRect(),.45);});
  }
  CCAPP.prev={counts:fresh,zones:zones,zoneMem:zoneMem,rectMem:rectMem};
}
document.getElementById('ccJoin').addEventListener('click',()=>ccMove('join'));
document.getElementById('ccStart').addEventListener('click',()=>ccMove('start'));
document.getElementById('ccHowTo').addEventListener('click', () => {
  try {
    if (window.Telegram && Telegram.WebApp && Telegram.WebApp.openLink)
      Telegram.WebApp.openLink(CC_HOW_TO_PLAY_URL);
    else window.open(CC_HOW_TO_PLAY_URL, '_blank');
  } catch (e) { window.open(CC_HOW_TO_PLAY_URL, '_blank'); }
});
document.getElementById('ccRematch').addEventListener('click',()=>ccMove('rematch'));
document.getElementById('ccZoom').addEventListener('click',ccZoomClose);
if(!document.getElementById('castlecombo').classList.contains('hidden')) ccLoad();
