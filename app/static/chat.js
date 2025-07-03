(() => {
  const ws       = new WebSocket(`ws://${location.host}/ws/chat`);
  const inp      = document.getElementById('msg');
  const btn      = document.getElementById('send');
  const msgs     = document.getElementById('messages');
  let botBubble  = null;

  /* Utility to append a list-item “bubble” ----------------- */
  function addBubble(text, cls) {
    const li = document.createElement('li');
    li.className = `list-group-item ${cls}`.trim();
    li.textContent = text;
    msgs.appendChild(li);
    msgs.scrollTop = msgs.scrollHeight;
    return li;
  }

  /* Send a user message ------------------------------------ */
  function send() {
    const q = inp.value.trim();
    if (!q) return;

    /* Show user bubble */
    addBubble(`You: ${q}`, 'user');

    /* Show placeholder “Thinking…” bubble immediately */
    botBubble = addBubble('Thinking…', 'bot thinking');

    inp.value = '';
    ws.send(JSON.stringify({ question: q }));
  }

  btn.onclick = send;
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

  /* Handle streaming tokens -------------------------------- */
  ws.onmessage = ({ data }) => {
    if (data === '[DONE]') {
      botBubble = null;
      return;
    }

    // Ignore empty / whitespace-only chunks while still “Thinking…”
    if (botBubble && botBubble.classList.contains('thinking')) {
      if (data.trim() === '') return;   // nothing useful yet

      // First real token ➜ switch bubble out of “thinking” mode
      botBubble.classList.remove('thinking');
      botBubble.textContent = '';       // clear “…”
    }

    // Safety: recreate bubble if it vanished for any reason
    if (!botBubble) botBubble = addBubble('', 'bot');

    botBubble.textContent += data;      // append streamed chunk
  };

  ws.onopen  = () => console.log('WS connected');
  ws.onerror = e  => console.error('WS error', e);
})();

// ── File‐upload logic ──
(() => {
  const fileInput = document.getElementById('file-input');
  const submitBtn = document.getElementById('file-submit');
  const resultPre = document.getElementById('file-result');

  submitBtn.onclick = async () => {
    const files = fileInput.files;
    if (!files || files.length === 0) {
      return alert('Please select a .py file');
    }

    const form = new FormData();
    form.append('file', files[0]);

    resultPre.textContent = 'Uploading & running…';
    try {
      const resp = await fetch('/exec_shell', {
        method: 'POST',
        body: form
      });
      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(err);
      }
      const out = await resp.text();
      resultPre.textContent = out;
    } catch (e) {
      resultPre.textContent = `Error: ${e.message}`;
    }
  };
})();
