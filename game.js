// الأصوات
const soundTakeoff = new Audio("sounds/take-off-36682.mp3"),
      soundExplosion = new Audio("sounds/explosion-312361.mp3"),
      soundClick = new Audio("sounds/ui-button-click-5-327756.mp3");


// باقي الكود بتاعك زي ما هو 100%
 const MIN_BET = 10, INITIAL_BALANCE = 50.0, TICK_MS = 50, STEP = 0.02;
    let balance = parseFloat(localStorage.getItem("balance") || INITIAL_BALANCE);
    let multiplier = 1.0, crashPoint = 0, running = false, timer = null, userBets = [0, 0], userCashed = [false, false];
    let transactions = [], aiPlayers = [];
    const elBalance = document.getElementById("balance"),
      elMultiplier = document.getElementById("multiplier"),
      elResult = document.getElementById("result"),
      plane = document.getElementById("plane"),
      line = document.getElementById("line"),
      explosion = document.getElementById("explosion"),
      elTransactionsList = document.getElementById("transactionsList"),
      playArea = document.getElementById("playArea"),
      playersArea = document.getElementById("playersArea");

    // صندوق إجمالي الرهانات
    const totalBetsEl = document.createElement("div");
    totalBetsEl.style.cssText = "margin:6px;font-size:16px;color:#ffd700";
    document.querySelector(".play-container").prepend(totalBetsEl);
    function updateTotalBets(sum) { totalBetsEl.innerHTML = "💰 إجمالي الرهانات: " + sum + " ج"; }

 
    function playClick() { soundClick.currentTime = 0; soundClick.play(); }

    function saveState() { localStorage.setItem("balance", balance.toFixed(2)) }
    function updateBalance() { elBalance.innerText = "رصيدك: " + balance.toFixed(2) + " جنيه"; saveState() }

    function pushTransaction(obj) { transactions.unshift(obj); renderTransactions(); }
    function renderTransactions() {
      if (transactions.length === 0) { elTransactionsList.innerText = 'لا توجد معاملات بعد'; return }
      elTransactionsList.innerHTML = transactions.map(t => {
        if (t.type === 'cashout') {
          return `<div>✅ <b>${t.player}</b> سحب عند <b>x${t.at}</b> — رهان: <b>${t.bet} ج</b> — كسب: <b>${t.won} ج</b></div>`
        } else if (t.type === 'loss') {
          return `<div>❌ <b>${t.player}</b> خسر — رهان: <b>${t.bet} ج</b></div>`
        } else if (t.type === 'deposit') {
          return `<div>💰 <b>${t.player || 'محفظتك'}</b> دفع/إيداع: <b>+${t.amount} ج</b></div>`
        } else { return `<div>${JSON.stringify(t)}</div>` }
      }).join('')
    }

    // توزيع احتمالي للكراش
    function getCrashPoint() {
      let r = Math.random();
      if (r < 0.55) { return parseFloat((1 + Math.random() * 5).toFixed(2)); }
      else if (r < 0.75) { return parseFloat((6 + Math.random() * 4).toFixed(2)); }
      else if (r < 0.90) { return parseFloat((10 + Math.random() * 6).toFixed(2)); }
      else { return parseFloat((16 + Math.random() * 4).toFixed(2)); }
    }

    // إنشاء لاعبين جدد
    function generatePlayers() {
      playersArea.innerHTML = "";
      aiPlayers = [];
      let n = 25 + Math.floor(Math.random() * 26);
      let sum = 0;
      for (let i = 0; i < n; i++) {
        const pid = maskId("X");
        const bet = 10 + Math.floor(Math.random() * 90);
        sum += bet;
        const cashAt = (Math.random() < 0.4) ? (1.2 + Math.random() * 8).toFixed(2) : null;
        aiPlayers.push({ id: pid, bet: bet, cashAt: cashAt, cashed: false });
        const card = document.createElement("div");
        card.className = "player-card";
        card.innerHTML = `<div class="player-id">${pid}</div>
        <div class="player-bet">رهان: ${bet}ج</div>
        <div class="player-status ok">✅ مستمر</div>`;
        playersArea.appendChild(card);
      }
      updateTotalBets(sum);
    }

    // بدء الجولة
    function startBet(index) {
      if (running) { alert("جولة جارية!"); return }

      // 🆕 تصفير سجل الجولة السابقة
      transactions = [];
      renderTransactions();

      const input = document.getElementById("bet" + (index + 1));
      const val = parseFloat(input.value);
      if (isNaN(val) || val < MIN_BET) { alert("ادخل رهان صحيح"); return }
      if (val > balance) { alert("رصيدك غير كافي"); return }
      playClick();
      balance -= val; updateBalance();
      userBets[index] = val; userCashed[index] = false;
      multiplier = 1.0; elMultiplier.innerText = "x1.00"; elResult.innerHTML = "";
      crashPoint = getCrashPoint();
      generatePlayers();
      running = true;
      plane.style.right = "0px"; line.style.width = "0px"; line.style.right = "0px"; explosion.style.display = "none";
      soundTakeoff.currentTime = 0; soundTakeoff.play();

      timer = setInterval(() => {
        multiplier = parseFloat((multiplier + STEP).toFixed(2));
        elMultiplier.innerText = `x${multiplier.toFixed(2)}`;
        const maxWidth = playArea.clientWidth - plane.clientWidth;
        const pos = (multiplier / 30) * maxWidth;
        plane.style.right = pos + "px"; line.style.width = pos + "px";

        // AI يسحب
        aiPlayers.forEach((p, idx) => {
          if (p.cashAt && !p.cashed && multiplier >= p.cashAt && multiplier < crashPoint) {
            p.cashed = true;
            const win = (p.bet * multiplier).toFixed(2);
            pushTransaction({ type: 'cashout', player: p.id, bet: p.bet, at: multiplier.toFixed(2), won: win });
            playersArea.children[idx].querySelector(".player-status").innerText = "سحب";
          }
        });

        if (multiplier >= crashPoint) {
          clearInterval(timer); running = false;
          explosion.style.width = plane.clientWidth + 40 + 'px';
          explosion.style.right = plane.style.right;
          explosion.style.top = '50%';
          explosion.style.display = 'block';
          soundExplosion.currentTime = 0; soundExplosion.play();

          // خسارة البشر
          userBets.forEach((b, i) => {
            if (b > 0 && !userCashed[i]) {
              pushTransaction({ type: 'loss', player: maskId('Player' + (i + 1)), bet: b });
            }
          });
          // خسارة AI
          aiPlayers.forEach((p, idx) => {
            if (!p.cashed) {
              pushTransaction({ type: 'loss', player: p.id, bet: p.bet });
              playersArea.children[idx].querySelector(".player-status").innerText = "❌ خسر";
            }
          });
          elResult.innerHTML = `💥 الطيارة تحطمت عند x${crashPoint}`;
        }
      }, TICK_MS)
    }

    // سحب المستخدم
    function cashout(i) {
      if (!running || userCashed[i]) return;
      playClick();
      userCashed[i] = true;
      const win = parseFloat((userBets[i] * multiplier).toFixed(2));
      balance += win; updateBalance();
      pushTransaction({ type: 'cashout', player: maskId('Player' + (i + 1)), bet: userBets[i], at: multiplier.toFixed(2), won: win.toFixed(2) })
    }

    function maskId(id) { return `211***${Math.floor(100 + Math.random() * 900)}`; }

    document.getElementById("bet1Start").onclick = () => startBet(0);
    document.getElementById("bet2Start").onclick = () => startBet(1);
    document.getElementById("bet1Cash").onclick = () => cashout(0);
    document.getElementById("bet2Cash").onclick = () => cashout(1);
    document.getElementById("depositConfirm").onclick = () => {
      playClick();
      const amt = parseFloat(document.getElementById("depositAmount").value);
      if (isNaN(amt) || amt < 20 || amt > 60000) { alert("ادخل مبلغ بين 20 و60000"); return }
      balance += amt; updateBalance(); pushTransaction({ type: 'deposit', amount: amt });
      document.getElementById("depositAmount").value = ""
    }

    updateBalance(); renderTransactions();





   
