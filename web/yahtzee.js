// Yahtzee Mini App (synced, initData auto-login). Loaded by flip7.html router.
const YZ={user_id:0,chat_id:null,board:null,timer:null,init:'',reroll:[false,false,false,false,false],prevDice:[]};
const YZ_UPPER=['ones','twos','threes','fours','fives','sixes'];
function yzLog(s){let e=document.getElementById('yzLog');if(e)e.textContent+=s+'\n';}
function yzApi(path,opts){return fetch(path,opts).then(r=>r.json());}
function yzNew(prev,keys){let pool=[...prev],out=new Set();keys.forEach((k,i)=>{let j=pool.indexOf(k);if(j>=0)pool.splice(j,1);else out.add(i);});return out;}
async function yzLoad(){
 let tg=tgInit();
 if(!tg.id){document.getElementById('yzBoard').innerHTML='<div class="table lobby-note">Open as Telegram Mini App via the bot\'s Yahtzee link.</div>';return;}
 YZ.user_id=tg.id; YZ.init=tg.init;
 let r=await yzApi('/api/yahtzee/mygames?init_data='+encodeURIComponent(tg.init));
 let mine=r.games||[];
 let pref=parseInt(tg.start,10)||0; if(!pref && tg.chat_instance) pref=parseInt(tg.chat_instance,10)||0;
 if(tg.start && String(tg.start).startsWith('yahtzee')) pref=parseInt(String(tg.start).slice(7),10)||pref;
 let pick=mine.find(g=>g.chat_id===pref);
 if(!pick && pref){let spec=await yzApi('/api/yahtzee/game?chat_id='+encodeURIComponent(pref)+'&init_data='+encodeURIComponent(tg.init));
  if(spec.ok) pick={chat_id:pref};}
 if(!pick) pick=mine.find(g=>g.phase!=='game_end') || mine[0];
 if(pick) yzSelect(pick.chat_id);
 else if(pref){let cr=await yzApi('/api/yahtzee/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.init,chat_id:pref})});
  if(cr.game) yzSelect(cr.game.chat_id); else yzLog('⛔ '+(cr.error||'create failed'));}
 else document.getElementById('yzBoard').innerHTML='<div class="table lobby-note">No Yahtzee game for you yet — send /yahtzee in a chat, then open its Mini App link.</div>';
}
async function yzSelect(chat_id){YZ.chat_id=chat_id; await yzRefresh();
 if(YZ.timer)clearInterval(YZ.timer); YZ.timer=setInterval(yzRefresh,3000);}
async function yzRefresh(){ if(!YZ.chat_id)return;
 let r=await yzApi('/api/yahtzee/game?chat_id='+encodeURIComponent(YZ.chat_id)+'&init_data='+encodeURIComponent(YZ.init));
 if(r.ok){let prev=YZ.board; YZ.board=r.game;
  let a=prev&&prev.turn, c=r.game.turn;
  if(!a||!c||a.rolls!==c.rolls||prev.current_index!==r.game.current_index) YZ.reroll=[false,false,false,false,false];
  yzRender();}}
async function yzMove(action,extra){
 let body=Object.assign({chat_id:YZ.chat_id,action:action,init_data:YZ.init},extra||{});
 let r=await yzApi('/api/yahtzee/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.events)r.events.forEach(e=>yzLog(e)); if(r.error)yzLog('⛔ '+r.error);
 if(r.game){YZ.board=r.game; YZ.reroll=[false,false,false,false,false]; yzRender();}}
function yzRender(){
 let b=YZ.board; if(!b)return;
 let t=b.turn||null, cur=b.players[b.current_index]||null;
 let myTurn=(b.phase==='playing'&&cur&&(cur.user_id===YZ.user_id||cur.npc));
 let spect=b.is_player===false&&!myTurn;
 let diceKeys=(t&&t.dice?t.dice:[]).map(String), newDice=yzNew(YZ.prevDice,diceKeys); YZ.prevDice=diceKeys;
 let diceHtml='';
 if(t&&t.dice&&t.dice.length){
  diceHtml='<div class="ydice">'+t.dice.map((d,i)=>
    '<div class="ydie'+(YZ.reroll[i]?' reroll':'')+(newDice.has(i)?' card-in':'')+'" data-i="'+i+'">'+d+'</div>').join('')+'</div>'
    +'<div class="small">'+(t.rolls>=3?'No rolls left — score a box.':'Tap dice to reroll · the rest are kept')+'</div>';
 } else if(myTurn){ diceHtml='<div class="small">Tap Roll to start your turn.</div>'; }
 let cards=b.players.map((p,i)=>yzScorecard(p,i,b)).join('');
 let specBar=spect?'<div class="lobby-note">👁 Spectating — view only (join in Telegram to play)</div>':'';
 document.getElementById('yzDice').innerHTML=diceHtml;
 document.getElementById('yzBoard').innerHTML='<div class="table">'+specBar+cards+'</div>';
 // Action buttons
 let roll=document.getElementById('yzRoll'), start=document.getElementById('yzStart'), rem=document.getElementById('yzRematch');
 roll.classList.toggle('hidden',!(myTurn&&t&&t.rolls<3));
 if(t&&t.rolls>0){
  let n=YZ.reroll.filter(Boolean).length;
  roll.textContent='🎲 Reroll selected ('+n+')';
  roll.disabled=(n===0);
 } else { roll.textContent='🎲 Roll dice'; roll.disabled=false; }
 start.classList.toggle('hidden',!(b.phase==='lobby'&&b.players.some(p=>p.user_id===YZ.user_id)));
 rem.classList.toggle('hidden',!(b.phase==='game_end'&&b.is_player));
 // Turn line
 let turn=document.getElementById('yzTurn');
 if(b.phase==='playing') turn.textContent=myTurn?'👉 Your turn':'👉 '+(cur?cur.name:'?')+"'s turn";
 else if(b.phase==='lobby') turn.textContent='🪑 Lobby - anyone taps Start';
 else if(b.phase==='game_end') turn.textContent='🏆 Game over!';
 else turn.textContent='';
 // Tap a die to mark it for reroll (unmarked dice are kept)
 document.querySelectorAll('#yzDice .ydie').forEach(el=>el.addEventListener('click',()=>{
  if(!myTurn||!t||t.rolls===0||t.rolls>=3)return;
  let i=parseInt(el.dataset.i); YZ.reroll[i]=!YZ.reroll[i]; yzRender();}));
 // Score taps on current player's open boxes
 if(myTurn&&t&&t.rolls>=1){
  document.querySelectorAll('#yzBoard .yscore.free').forEach(el=>el.addEventListener('click',()=>{
   yzMove('score',{category:el.dataset.cat});}));
 }
}
function yzScorecard(p,i,b){
 let isCur=(b.phase==='playing'&&i===b.current_index);
 let myTurn=isCur&&(p.user_id===YZ.user_id||p.npc);
 let upper=0, lower=0;
 YZ_UPPER.forEach(k=>{let v=p.scores[k]; if(v!=null)upper+=v;});
 b.categories.filter(c=>!YZ_UPPER.includes(c.key)).forEach(c=>{let v=p.scores[c.key]; if(v!=null)lower+=v;});
 let cell=(c)=>{
  let v=p.scores[c.key], used=(v!==null&&v!==undefined);
  let pts=(!used&&myTurn&&b.dice_scores)?(b.dice_scores[c.key]||0):null;
  let cls='yscore'+(used?' used':' free');
  let label=c.label+(pts!==null?' <span class="pts">'+pts+'</span>':'');
  return '<div class="'+cls+'"'+(used?'':' data-cat="'+c.key+'"')+'>'+label+'<b>'+(used?v:'–')+'</b></div>';
 };
 return '<div class="yscard'+(isCur?' current':'')+'"><div class="yshead"><span>'+escapeHtml(p.name)+(p.npc?' 🤖':'')+'</span><span class="score">'+p.total+'</span></div>'
  +'<div class="ysgrid">'+b.categories.map(cell).join('')+'</div>'
  +'<div class="small">Upper '+upper+'/63'+(upper>=63?' · +35 ✓':'')+' · Yahtzee bonus +'+(p.yahtzee_bonus||0)+' · '+p.filled+'/13 filled</div></div>';
}
document.getElementById('yzRoll').addEventListener('click',()=>yzMove('roll',{keep:YZ.reroll.map(x=>!x)}));
document.getElementById('yzStart').addEventListener('click',()=>yzMove('start'));
document.getElementById('yzRematch').addEventListener('click',()=>yzMove('rematch'));
// Self-start when router (flip7.js) selected Yahtzee mode.
if(!document.getElementById('yahtzee').classList.contains('hidden')) yzLoad();