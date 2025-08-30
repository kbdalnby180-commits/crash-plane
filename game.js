// الأصوات
const soundTakeoff = new Audio("sounds/take-off-36682.mp3"),
      soundExplosion = new Audio("sounds/explosion-312361.mp3"),
      soundClick = new Audio("sounds/ui-button-click-5-327756.mp3");

const MIN_BET = 10, INITIAL_BALANCE = 50.0, TICK_MS = 50, STEP = 0.02;
let balance = parseFloat(localStorage.getItem("balance") || INITIAL_BALANCE);
let multiplier = 1.0, crashPoint = 0, running = false, timer = null;
let userBets = [0], userCashed=[false], transactions=[], aiPlayers=[];
const elBalance = document.getElementById("balance"),
      elMultiplier = document.getElementById("multiplier"),
      elResult = document.getElementById("result"),
      plane = document.getElementById("plane"),
      line = document.getElementById("line"),
      explosion = document.getElementById("explosion"),
      elTransactionsList = document.getElementById("transactionsList"),
      playArea = document.getElementById("playArea"),
      playersArea = document.getElementById("playersArea");

function playClick(){ soundClick.currentTime=0; soundClick.play(); }
function saveState(){ localStorage.setItem("balance", balance.toFixed(2)); }
function updateBalance(){ elBalance.innerText = "رصيدك: " + balance.toFixed(2) + " جنيه"; saveState(); }
function pushTransaction(obj){ transactions.unshift(obj); renderTransactions(); }
function renderTransactions(){
  if(transactions.length===0){ elTransactionsList.innerText='لا توجد معاملات بعد'; return; }
  elTransactionsList.innerHTML = transactions.map(t=>{
    if(t.type==='cashout'){ return `<div>✅ <b>${t.player}</b> سحب عند <b>x${t.at}</b> — رهان: <b>${t.bet} ج</b> — كسب: <b>${t.won} ج</b></div>` }
    else if(t.type==='loss'){ return `<div>❌ <b>${t.player}</b> خسر — رهان: <b>${t.bet} ج</b></div>` }
    else if(t.type==='deposit'){ return `<div>💰 <b>${t.player||'محفظتك'}</b> دفع/إيداع: <b>+${t.amount} ج</b></div>` }
  }).join('');
}

function getCrashPoint(){ let r=Math.random(); if(r<0.55) return parseFloat((1+Math.random()*5).toFixed(2));
else if(r<0.75) return parseFloat((6+Math.random()*4).toFixed(2));
else if(r<0.9) return parseFloat((10+Math.random()*6).toFixed(2));
else return parseFloat((16+Math.random()*4).toFixed(2)); }

function generatePlayers(){
  playersArea.innerHTML=""; aiPlayers=[];
  let n = 10+Math.floor(Math.random()*15);
  for(let i=0;i<n;i++){
    const pid = maskId("X"); 
    const bet = 10+Math.floor(Math.random()*90);
    const cashAt = (Math.random()<0.4)?
