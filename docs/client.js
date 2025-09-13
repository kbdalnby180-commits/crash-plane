async function loadConfig() {
  const res = await fetch("config.json");
  return res.json();
}

loadConfig().then(config => {
  const socket = io(config.serverUrl);
  const messages = document.getElementById("messages");
  const formInput = document.getElementById("m");
  const sendBtn = document.getElementById("send");

  function addMessage(msg, self=false) {
    const li = document.createElement("li");
    li.className = self ? "self" : "other";
    li.innerHTML = msg.text + '<span class="time">' + msg.time + "</span>";
    messages.appendChild(li);
    messages.scrollTop = messages.scrollHeight;
  }

  socket.on("chat message", msg => {
    addMessage(msg, msg.self === true);
  });

  sendBtn.onclick = () => {
    if(formInput.value.trim() !== "") {
      const now = new Date();
      const time = now.getHours().toString().padStart(2, '0') + ":" +
                   now.getMinutes().toString().padStart(2, '0');
      const msg = { text: formInput.value, time: time };
      socket.emit("chat message", msg);
      formInput.value = "";
    }
  };

  formInput.addEventListener("keypress", e => {
    if(e.key === "Enter") sendBtn.click();
  });
});
