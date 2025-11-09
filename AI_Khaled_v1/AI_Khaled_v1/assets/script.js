document.addEventListener("DOMContentLoaded", function(){
  const chat = document.getElementById("chat");
  const form = document.getElementById("form");
  const input = document.getElementById("input");
  const btnTrain = document.getElementById("btn-train");
  const btnSave = document.getElementById("btn-save");

  function addBubble(who, text){
    const d = document.createElement("div");
    d.className = "bubble " + (who==="user" ? "user" : "bot");
    d.textContent = (who==="user" ? "أنت: " : "AI Khaled: ") + text;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
  }

  async function send(text){
    addBubble("user", text);
    try{
      const res = await fetch("/api/chat", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({text})});
      const j = await res.json();
      addBubble("bot", j.reply || "(خطأ)");
    }catch(e){
      addBubble("bot", "خطأ في الاتصال بالمحرك المحلي.");
    }
  }

  form.addEventListener("submit", function(e){
    e.preventDefault();
    const v = input.value.trim();
    if(!v) return;
    input.value = "";
    send(v);
  });

  btnTrain.addEventListener("click", async function(){
    btnTrain.textContent = "جارى التشغيل...";
    await fetch("/api/train", {method:"POST"});
    setTimeout(()=>{ btnTrain.textContent = "🔄 إعادة تدريب الذكاء"; alert("تم تشغيل التدريب في الخلفية."); }, 2000);
  });

  btnSave.addEventListener("click", async function(){
    const res = await fetch("/api/save");
    const j = await res.json();
    alert("تم حفظ الذاكرة في: " + j.path + "\\nحجم الملف: " + j.size + " بايت");
  });

  // load last conversations to UI
  (async function loadRecent(){
    try{
      const mem = await fetch("/data/memory.json").then(r=>r.json());
      const convs = mem.conversations || [];
      for(const c of convs.slice(-30)){
        addBubble("user", c.user_text);
        addBubble("bot", c.bot_text);
      }
    }catch(e){}
  })();
});
