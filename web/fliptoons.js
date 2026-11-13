// Fliptoons Mini App (synced, initData auto-login). Loaded by flip7.html router.
const FLP={user_id:0,chat_id:null,board:null,timer:null,init:'',err:''};
function ftLog(s){let e=document.getElementById('ftLog');if(e)e.textContent+=s+'\n';}
function ftApi(path,opts){return fetch(path,opts).then(r=>r.json());}
function ftChatId(raw){let s=String(raw||'');if(s.startsWith('fliptoons'))s=s.slice(9);
 let n=parseInt(s,10);return isNaN(n)?0:n;}
async function ftLoad(){
 let tg=tgInit();
 let board=document.getElementById('ftBoard');
 if(!tg.id){board.innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot\'s Fliptoons link.</div>';return;}
 FLP.user_id=tg.id; FLP.init=tg.init;
 // Trusted chat id comes only from the startapp/URL param ("fliptoons<chat>"),
 // never from chat_instance (that is not a chat id and used to spawn a stray
 // lobby, leaving the Mini App stuck on "1/4" while the real game lived elsewhere).
 let pref=ftChatId(tg.start)||ftChatId(new URLSearchParams(location.search).get('app'));
 let r=await ftApi('/api/fliptoons/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 let cands=mine.slice().sort((a,b)=>((a.phase==='game_end')-(b.phase==='game_end')) ||
   ((b.players?b.players.length:0)-(a.players?a.players.length:0)));
 let pick=cands.find(g=>g.chat_id===pref)||cands[0];
 if(pick){ftSelect(pick.chat_id);return;}
 if(!pref){board.innerHTML='<div class="table lobby-note">No Fliptoons game for you yet — send /fliptoons in a chat, then open its Mini App link.</div>';return;}
 let spec=await ftApi('/api/fliptoons/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
 if(spec.ok&&spec.game){ftSelect(pref);return;}
 let cr=await ftApi('/api/fliptoons/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});
 if(cr.game){ftSelect(cr.game.chat_id);return;}
 FLP.err=cr.error||'could not create the game';
 board.innerHTML='<div class="table lobby-note">⛔ '+escapeHtml(FLP.err)+'</div>';
}
async function ftSelect(chat_id){FLP.chat_id=chat_id; FLP.err=''; await ftRefresh();
 if(FLP.timer)clearInterval(FLP.timer); FLP.timer=setInterval(ftRefresh,3000);}
async function ftRefresh(){ if(!FLP.chat_id)return;
 let r=await ftApi('/api/fliptoons/game?chat_id='+encodeURIComponent(FLP.chat_id)+'&init_data='+encodeURIComponent(FLP.init));
 if(r.ok){FLP.board=r.game; FLP.err=''; ftRender();}
 else if(FLP.board){FLP.err=r.error||'game not found'; ftRender();}}
async function ftMove(action,extra){
 let body=Object.assign({chat_id:FLP.chat_id,action:action,init_data:FLP.init},extra||{});
 let r=await ftApi('/api/fliptoons/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.events)r.events.forEach(e=>ftLog(e));
 FLP.err=r.error||''; if(r.error)ftLog('⛔ '+r.error);
 if(r.game)FLP.board=r.game;
 if(FLP.board)ftRender();}
// BGA sprite sheet: 6 columns x 5 rows. Cells 0-4 are the starters in
// STARTER_NAMES order; toon rank r (1-25) sits at cell r+4 (ostrich=5 .. cow=29).
const FT_SHEET='/fliptoons/fl-toon-cards.webp', FT_BACK='/fliptoons/fl-toon-cards-back.webp';
// BGA-style card faces (mirrors the official BGA client renderer):
// - c: band colour (sampled from the sprite's flat name band; matches the
//   official BGA hexes, e.g. Camel #8385A0, Deer #00ADB3, Bear #A4644B)
// - k: copies in the deck, r: rank, f: printed fame
// - sp: special banner {i: icon, t: text, l: single|multi|threelines}
// - ab: ability box {s: XL|L|M|S, v: single|double, rows: [[segment,..],..]}
// Segments: [f:N] fame coin, [i:name] icon, <kw>IF</kw>/<kw>PER</kw> badge, <b>..</b> bold.
const FT_ICON_POS={coin:'0 0',dismiss:'10% 0','no-flip':'20% 0',adjacent:'30% 0','lower-row':'40% 0','upper-row':'50% 0','middle-column':'60% 0','move-row-above':'70% 0','hire-dismiss':'80% 0',hire:'90% 0','no-dismiss':'100% 0','cards-above':'0 100%','cards-below':'10% 100%','first-and-last':'20% 100%',fish:'30% 100%','stack-above':'40% 100%','no-return':'50% 100%','next-move-row-above':'60% 100%',na:'70% 100%'};
const FT_BGA={
"snail":{n:"Snail",c:"#818181",k:1,r:0,f:"2",ab:{s:"XL",v:"single",rows:[]}},
"caterpillar":{n:"Caterpillar",c:"#818181",k:2,r:0,f:"0",sp:{i:"dismiss",t:"COSTS [f:3] TO DISMISS INSTEAD OF [f:5]",l:"multi"},ab:{s:"M",v:"single",rows:[]}},
"dragonfly":{n:"Dragonfly",c:"#818181",k:1,r:0,f:"0",ab:{s:"XL",v:"double",rows:[["[f:+1]","<kw>PER</kw> unique <b>adjacent</b> card","[i:adjacent]"]]}},
"skunk":{n:"Skunk",c:"#818181",k:1,r:0,f:"0",ab:{s:"XL",v:"double",rows:[["<kw>IF</kw> you have the least fame after the Check Fame phase, <b>dismiss</b> a card in your grid for [f:0]"]]}},
"bee":{n:"Bee",c:"#818181",k:1,r:0,f:"1",ab:{s:"XL",v:"single",rows:[]}},
"ostrich":{n:"Ostrich",c:"#4A6172",k:3,r:1,f:"1",ab:{s:"XL",v:"double",rows:[["<b>Stack</b> the next revealed card on this card"]]}},
"eagle":{n:"Eagle",c:"#5C718E",k:2,r:2,f:"4",sp:{i:"no-flip",t:"CANNOT BE FLIPPED",l:"single"},ab:{s:"L",v:"double",rows:[["<b>Flip</b> the next placed card unless it [i:no-flip] (its ability does not activate)"]]}},
"donkey":{n:"Donkey",c:"#559074",k:2,r:3,f:"1",ab:{s:"XL",v:"double",rows:[["[f:+5]","<kw>IF</kw> in the lower row","[i:lower-row]"],["If so, <b>dismiss</b> this card after the Market phase"]]}},
"butterfly":{n:"Butterfly",c:"#C44B59",k:3,r:4,f:"2",sp:{i:"hire",t:"WHEN HIRED, YOU MAY DISMISS A CATERPILLAR",l:"multi"},ab:{s:"M",v:"single",rows:[]}},
"dog":{n:"Dog",c:"#8D7E91",k:4,r:5,f:"0",ab:{s:"XL",v:"double",rows:[["[f:+5]","<kw>IF</kw> there is at least one DOG in the market or any other player's <b>grid</b>"]]}},
"goat":{n:"Goat",c:"#89513F",k:2,r:6,f:"1",ab:{s:"XL",v:"double",rows:[["[f:+3]","<kw>IF</kw> in the upper row","[i:upper-row]"]]}},
"sheep":{n:"Sheep",c:"#D95642",k:2,r:7,f:"1",ab:{s:"XL",v:"double",rows:[["[f:+4]","<kw>IF</kw> in the middle column","[i:middle-column]"]]}},
"camel":{n:"Camel",c:"#8385A0",k:5,r:8,f:"2",ab:{s:"XL",v:"double",rows:[["[f:+2]","<kw>IF</kw> no other player or the market has more CAMELS than you"]]}},
"rabbit":{n:"Rabbit",c:"#AD6871",k:4,r:9,f:"3",sp:{i:"no-flip",t:"CANNOT BE FLIPPED",l:"single"},ab:{s:"L",v:"double",rows:[["<b>Stack</b> this card on top of the first RABBIT or face-down card in your grid, if possible"]]}},
"horse":{n:"Horse",c:"#B09668",k:2,r:10,f:"4",sp:{i:"hire",t:"WHEN HIRED, DISCARD ANY NUMBER OF CARDS IN THE MARKET AND REFILL",l:"threelines"},ab:{s:"S",v:"single",rows:[]}},
"snake":{n:"Snake",c:"#6F905E",k:2,r:11,f:"1",ab:{s:"XL",v:"double",rows:[["<b>Dismiss</b> the top card of your deck and <b>stack</b> the top card from the toon deck on this card"]]}},
"elephant":{n:"Elephant",c:"#787A8A",k:2,r:12,f:"7",sp:{i:"no-flip",t:"CANNOT BE FLIPPED",l:"single"},ab:{s:"L",v:"double",rows:[["<b>Flip</b> the previously placed card (unless it [i:no-flip])"]]}},
"rooster":{n:"Rooster",c:"#008A8C",k:2,r:13,f:"0",ab:{s:"XL",v:"double",rows:[["[f:+1]","<kw>PER</kw> card rank 13 or lower (including this card)"]]}},
"cat":{n:"Cat",c:"#AD6F3B",k:2,r:14,f:"1",sp:{i:"no-dismiss",t:"CANNOT BE DISMISSED",l:"single"},ab:{s:"L",v:"double",rows:[["[f:+1]","<kw>PER</kw> <b>Starting Card</b> in your <b>dismissed</b> Cards"]]}},
"alligator":{n:"Alligator",c:"#5D7953",k:2,r:15,f:"6",ab:{s:"XL",v:"double",rows:[["After the Market phase, dismiss one card <b>adjacent</b> to the right of this card"]]}},
"lion":{n:"Lion",c:"#AE6143",k:2,r:16,f:"3",ab:{s:"XL",v:"double",rows:[["[f:+4]","<kw>IF</kw> all adjacent cards are rank 16 or lower"]]}},
"monkey":{n:"Monkey",c:"#5B8F75",k:2,r:17,f:"3",ab:{s:"XL",v:"double",rows:[["[f:+3]","<kw>IF</kw> in the upper row","[i:upper-row]"],["If placed in the upper row, move this card to a row above"]]}},
"pig":{n:"Pig",c:"#A67376",k:1,r:18,f:"-1",sp:{i:"hire-dismiss",t:"WHEN HIRED OR DISMISSED, PLACE THIS CARD IN ANY DECK",l:"threelines"},ab:{s:"S",v:"single",rows:[]}},
"peacock":{n:"Peacock",c:"#008A8B",k:2,r:19,f:"5",sp:{i:"hire",t:"WHEN HIRED, GAIN [f:2] AND TAKE A BONUS MARKET ACTION",l:"multi"},ab:{s:"M",v:"single",rows:[]}},
"turkey":{n:"Turkey",c:"#A67077",k:2,r:20,f:"5",ab:{s:"XL",v:"double",rows:[["<b>Stack</b> this card on the previous placed card"]]}},
"bull":{n:"Bull",c:"#734436",k:1,r:21,f:"3",sp:{i:"no-flip",t:"CANNOT BE FLIPPED",l:"single"},ab:{s:"L",v:"double",rows:[["[f:+7]","<kw>IF</kw> one or more cards in your <b>grid</b> are face down"]]}},
"tiger":{n:"Tiger",c:"#B8443B",k:1,r:22,f:"3",sp:{i:"no-dismiss",t:"CANNOT BE DISMISSED",l:"single"},ab:{s:"L",v:"double",rows:[["[f:+1]","<kw>PER</kw> card in your dismissed cards"]]}},
"deer":{n:"Deer",c:"#00ADB3",k:1,r:23,f:"3",ab:{s:"XL",v:"double",rows:[["[f:+5]","<kw>IF</kw> each face-up card in your <b>grid</b> is unique"]]}},
"bear":{n:"Bear",c:"#A4644B",k:1,r:24,f:"1",ab:{s:"XL",v:"double",rows:[["[f:+1]","<kw>PER</kw> face-up card in your <b>grid</b>"]]}},
"cow":{n:"Cow",c:"#C59296",k:1,r:25,f:"=",ab:{s:"XL",v:"double",rows:[["Copy the fame of one <b>adjacent</b> card"]]}},
};
// Plain-text info derived from the face data (titles + market desc line).
function ftPlain(s){return s.replace(/\[(i|f):[^\]]+\]/g,'').replace(/<\/?(kw|b)>/g,'').replace(/\s+/g,' ').trim();}
const FT_CARDS={};
for(const k in FT_BGA){const b=FT_BGA[k],parts=[];
 if(b.sp)parts.push(ftPlain(b.sp.t));
 (b.ab&&b.ab.rows||[]).forEach(r=>{const t=ftPlain(r.join(' '));if(t)parts.push(t);});
 FT_CARDS[k]={n:b.n,r:b.r,f:b.f,d:parts.join(' · ')};}
function ftCardInfo(c){
 if(!c||c.fd)return null;
 return FT_CARDS[String(c.name||'').toLowerCase()]||null;
}
function ftIcon(name,sz,text){
 return '<span class="fticon" style="background-position:'+(FT_ICON_POS[name]||'0 0')+';--icsz:'+sz+'cqw;--iccs:'+(text&&String(text).length>1?0.6:0.8)+'">'+(text||'')+'</span>';
}
function ftCoin(v,sz){return ftIcon('coin',sz,v);}
function ftRich(s,isz){
 return s.replace(/\[i:([a-z-]+)\]/g,(m,n)=>ftIcon(n,isz))
  .replace(/\[f:([^\]]+)\]/g,(m,v)=>ftCoin(v,isz))
  .replace(/<kw>([^<]*)<\/kw>/g,'<span class="ftckw">$1</span>');
}
function ftFace(c){
 const b=FT_BGA[String(c.name||'').toLowerCase()]; if(!b)return '';
 let h='<div class="ftcface" style="--ftc:'+b.c+'">'
  +'<div class="ftcrank">'+b.r+'</div><div class="ftccount">'+b.k+'</div>'
  +'<div class="ftcname">'+escapeHtml(b.n)+'</div>';
 if(b.sp)h+='<div class="ftcspecial ftcl-'+b.sp.l+'">'+ftIcon(b.sp.i,10.1)
  +'<div class="ftcsdesc">'+ftRich(b.sp.t,10.1)+'</div>'+ftIcon(b.sp.i,10.1)+'</div>';
 const ab=b.ab, rows=ab.rows||[];
 h+='<div class="ftcab ftcs-'+ab.s+' ftcv-'+ab.v+'"><div class="ftcbase">'+ftCoin(b.f,16.9)+'</div>';
 if(rows.length){
  h+='<div class="ftcdw">'+rows.map(row=>{
   const w=row.length===1?'67.6cqw':row.length===2?'54cqw':'33.8cqw';
   return '<div class="ftcrow2">'+row.map(seg=>{
    const mi=seg.match(/^\[i:([a-z-]+)\]$/), mf=seg.match(/^\[f:([^\]]+)\]$/);
    if(mi)return '<div class="ftcblock ftcib">'+ftIcon(mi[1],13.5)+'</div>';
    if(mf)return '<div class="ftcblock ftcib">'+ftCoin(mf[1],13.5)+'</div>';
    return '<div class="ftcblock" style="max-width:'+w+'"><span class="ftct">'+ftRich(seg,13.5)+'</span></div>';
   }).join('')+'</div>';
  }).join('')+'</div>';
 }
 return h+'</div></div>';
}
// Shrink-to-fit pass (approximates BGA's bga-autofit on ability text).
function ftFit(root){
 if(!root||!root.querySelectorAll)return;
 root.querySelectorAll('.ftcblock,.ftcsdesc,.ftcname').forEach(el=>{
  el.style.fontSize='';
  let fs=parseFloat(getComputedStyle(el).fontSize)||8;
  for(let i=0;i<16;i++){
   if(el.scrollWidth<=el.clientWidth+1&&el.scrollHeight<=el.clientHeight+1)break;
   fs*=0.93;el.style.fontSize=fs+'px';
  }
 });
}
function ftCellIdx(c){
 if(!c)return -1;
 if(c.starter)return c.s;
 return c.r>=1?c.r+4:-1;
}
function ftArt(c){
 if(!c)return '';
 if(c.fd)return "background-image:url('"+FT_BACK+"');background-size:cover;background-position:center";
 let n=ftCellIdx(c); if(n<0)return '';
 return "background-image:url('"+FT_SHEET+"');background-size:600% 500%;background-position:"+((n%6)*20)+'% '+(Math.floor(n/6)*25)+'%';
}
function ftCell(st){
 if(!st||!st.length)return '<div class="ftcell empty">·</div>';
 let top=st[st.length-1], cls='ftcell'+(top.fd?' fd':''), stack=st.length>1?'<span class="ftstack">×'+st.length+'</span>':'';
 return '<div class="'+cls+'" style="'+ftArt(top)+'" title="'+escapeHtml(top.name)+(top.fd?'':' ('+(FT_CARDS[String(top.name).toLowerCase()]||{}).d+')')+'">'+(top.fd?'':ftFace(top))+stack+'</div>';
}
function ftGrid(p){
 let cells=p.grid.map(ftCell);
 while(cells.length<6)cells.push('<div class="ftcell empty">·</div>');
 let h='<div class="ftgrid">'+cells.join('')+'</div>';
 (p.extra||[]).forEach(e=>{h+='<div class="ftrow-extra">+ '+e.cards.map(c=>'<span class="ftmini" style="'+ftArt(c)+'" title="'+escapeHtml(c.name)+(c.fd?'':' ('+c.fame+')')+'"></span>').join('')+'</div>';});
 return h;
}
function ftDismissButtons(p){
 let out=[];
 let add=c=>{if(c.dismissable)out.push('<button class="ftdismiss" data-dismiss="'+c.id+'">🗑 '+escapeHtml(c.name)+' ('+c.dismiss_cost+')</button>');};
 p.grid.forEach(st=>st.forEach(add));
 (p.extra||[]).forEach(e=>e.cards.forEach(add));
 return out.length?'<div class="ftopts">'+out.join('')+'</div>':'';
}
 // Full-size card view (market cards are small; tap to inspect + read the text).
 function ftZoom(name){
  let b=FT_BGA[String(name||'').toLowerCase()]; if(!b)return;
  let info=FT_CARDS[String(name||'').toLowerCase()]||{d:''};
  let c={name:b.n,r:b.r};
  let si=['Caterpillar','Skunk','Dragonfly','Bee','Snail'].indexOf(b.n);
  if(b.r===0&&si>=0){c.starter=true;c.s=si;}
  let z=document.getElementById('ftZoom');
  z.innerHTML='<div class="ftzcard"><div class="ftmart" style="'+ftArt(c)+'">'+ftFace(c)+'</div></div>'+
   '<div class="ftzdesc">'+(info.d?'ℹ️ '+escapeHtml(info.d):'')+'</div>'+
   '<div class="small" style="margin-top:8px">tap anywhere to close</div>';
  z.classList.add('open');
  ftFit(z);
 }
 function ftZoomClose(){let z=document.getElementById('ftZoom');if(z){z.classList.remove('open');z.innerHTML='';}}
function ftRender(){
 let b=FLP.board; if(!b)return;
 let t=document.getElementById('ftTurn'), board=document.getElementById('ftBoard');
 let cur=b.actor!=null?b.players[b.actor]:null;
 let isActor=b.actor!=null&&(cur.user_id===FLP.user_id||cur.npc);
 let myMarket=b.can_act&&b.stage==='market'&&!b.pending;
 let parts=[];
 if(b.phase==='lobby'){
  t.textContent='🪑 Lobby - '+b.players.length+'/4 players';
  parts.push('<div class="table"><div class="small">Players</div>'+b.players.map(p=>'<div>'+escapeHtml(p.name)+(p.npc?' 🤖':'')+(p.user_id===FLP.user_id?' (you)':'')+'</div>').join('')+
   '<div class="lobby-note">Friends join in Telegram, then anyone taps Start.</div></div>');
 } else if(b.phase==='game_end'){
  t.textContent='🏆 Game over!';
  if(b.winner!=null){let w=b.players[b.winner]; parts.push('<div class="table lobby-note">Winner: <b>'+escapeHtml(w.name)+'</b> with '+w.fame+' fame!</div>');}
  else parts.push('<div class="table lobby-note">It\'s a draw!</div>');
 } else {
  t.textContent=isActor?(b.pending?'👉 Your choice':(b.stage==='market'?'👉 Your market turn':'⏳ Resolving flips…')):(cur?'👉 '+escapeHtml(cur.name)+'\'s turn':'⏳ Resolving flips…');
  if(b.pending){
   let pp=b.players[b.pending.player];
   let mine=b.pending.player!=null&&pp&&(pp.user_id===FLP.user_id||pp.npc);
   parts.push('<div class="table"><div class="lobby-note">'+escapeHtml(b.pending.prompt)+
    (!mine&&pp?' <i>(waiting for '+escapeHtml(pp.name)+')</i>':'')+'</div>'+
    (mine?'<div class="ftopts">'+b.pending.options.map(o=>'<button class="hit" data-choose="'+escapeHtml(String(o.v))+'">'+escapeHtml(o.label)+'</button>').join('')+'</div>':'')+
    '</div>');
  }
  parts.push('<div class="table"><div class="small">🛒 Market (cost = slot) · round '+b.round+' · target '+b.target+' fame</div><div class="ftmarket">'+
   b.market.map(m=>{
    return '<div class="ftmcard"><div class="price">'+m.price+'💰</div>'+
    (m.card?'<div class="ftmart" style="'+ftArt(m.card)+'" data-zoom="'+escapeHtml(m.card.name)+'" title="'+escapeHtml(m.card.name)+'">'+ftFace(m.card)+'</div>':'<div class="ftmart empty">—</div>')+
    (m.card&&myMarket?'<button class="hit" data-hire="'+m.slot+'">Hire</button>':'')+'</div>';}).join('')+'</div></div>');
  let ph='<div class="table"><div class="ftplayers">';
  b.players.forEach((p,i)=>{
   let badges=(i===b.first?'<img class="ftbadge" src="/fliptoons/fl-first-player.webp" title="First player" alt="first player">':'')+
    (b.critic_holder===i?'<img class="ftbadge" src="/fliptoons/fl-critics-choice.webp" title="Critics\' Choice" alt="critics choice">':'');
   ph+='<div class="ftpc'+(p.is_current?' current':'')+'"><div style="display:flex;justify-content:space-between"><b>'+escapeHtml(p.name)+(p.npc?' 🤖':'')+'</b>'+badges+'<span class="score">'+p.fame+'</span></div>'+
    '<div class="small">deck '+p.deck+' · discarded '+p.discarded+(p.is_current&&b.stage==='market'?' · budget '+p.budget:'')+'</div>'+ftGrid(p)+
    (i===b.actor&&myMarket?ftDismissButtons(p):'')+'</div>';
  });
  ph+='</div></div>'; parts.push(ph);
 }
 if(FLP.err)parts.unshift('<div class="table lobby-note">⛔ '+escapeHtml(FLP.err)+'</div>');
 board.innerHTML=parts.join('');
 ftFit(board);
 document.getElementById('ftJoin').classList.toggle('hidden',!(b.phase==='lobby'&&!b.is_player));
 document.getElementById('ftStart').classList.toggle('hidden',!(b.phase==='lobby'&&b.is_player));
 document.getElementById('ftSkip').classList.toggle('hidden',!myMarket);
 document.getElementById('ftRematch').classList.toggle('hidden',!(b.phase==='game_end'&&b.is_player));
 board.querySelectorAll('[data-hire]').forEach(el=>el.addEventListener('click',()=>ftMove('hire',{slot:parseInt(el.dataset.hire)})));
 board.querySelectorAll('[data-zoom]').forEach(el=>el.addEventListener('click',()=>ftZoom(el.dataset.zoom)));
 board.querySelectorAll('[data-choose]').forEach(el=>el.addEventListener('click',()=>ftMove('choose',{choice:el.dataset.choose})));
 board.querySelectorAll('[data-dismiss]').forEach(el=>el.addEventListener('click',()=>ftMove('dismiss',{iid:parseInt(el.dataset.dismiss)})));
}
document.getElementById('ftJoin').addEventListener('click',()=>ftMove('join'));
document.getElementById('ftStart').addEventListener('click',()=>ftMove('start'));
document.getElementById('ftSkip').addEventListener('click',()=>ftMove('skip'));
document.getElementById('ftZoom').addEventListener('click',ftZoomClose);
document.getElementById('ftRematch').addEventListener('click',()=>ftMove('rematch'));
if(!document.getElementById('fliptoons').classList.contains('hidden')) ftLoad();
