(() => {
  const ws       = new WebSocket(`ws://${location.host}/ws/chat`);
  const inp      = document.getElementById('msg');
  const btn      = document.getElementById('send');
  const msgs     = document.getElementById('messages');
  let botBubble  = null;

  function addBubble(text, cls) {
    const li = document.createElement('li');
    li.className = `list-group-item ${cls}`;
    li.textContent = text;
    msgs.appendChild(li);
    msgs.scrollTop = msgs.scrollHeight;
    return li;
  }

  function send() {
    const q = inp.value.trim();
    if (!q) return;
    addBubble(`You: ${q}`, 'user');
    inp.value = '';
    botBubble = null;
    ws.send(JSON.stringify({ question: q }));
  }

  btn.onclick = send;
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

  ws.onmessage = ({ data }) => {
    if (data === '[DONE]') {
      botBubble = null;
      return;
    }
    if (!botBubble) botBubble = addBubble('', 'bot');
    botBubble.textContent += data;
  };

  ws.onopen  = () => console.log('WS connected');
  ws.onerror = e => console.error('WS error', e);
})();
