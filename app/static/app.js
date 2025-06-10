async function submitQuestion() {
  const q = document.getElementById("question").value;
  const resp = await fetch('/planner', {
    method: 'POST',
    headers: { 'Content-Type':'application/json' },
    body: JSON.stringify({ question: q })
  });
  const data = await resp.json();
  document.getElementById('result').innerText =
    JSON.stringify(data, null, 2);
}
