"""The web interface, as one self-contained page.

No build step, no framework, no dependency on a CDN. The whole reason this
project exists is that infrastructure should be simple to stand up, and a
page that needs npm before it can be served would sit badly beside that.

It also means the container image is Python and nothing else.
"""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stratus</title>
<style>
  :root {
    --bg: #0f1117; --panel: #171a23; --line: #262b38;
    --text: #e6e8ee; --dim: #9aa3b2; --accent: #6ea8fe;
    --warn: #f0b849; --danger: #f2777a; --ok: #7ec699;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg: #f7f8fa; --panel: #fff; --line: #e3e6ec;
      --text: #1b1f27; --dim: #5f6875; --accent: #2563eb;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    display: flex; flex-direction: column; min-height: 100vh;
  }
  header {
    padding: 18px 22px; border-bottom: 1px solid var(--line);
    display: flex; align-items: baseline; gap: 14px;
  }
  header h1 { margin: 0; font-size: 19px; letter-spacing: -.01em; }
  header p { margin: 0; color: var(--dim); font-size: 13px; }
  main { flex: 1; width: 100%; max-width: 760px; margin: 0 auto; padding: 22px; }
  .msg { margin-bottom: 16px; }
  .msg .who { font-size: 12px; color: var(--dim); margin-bottom: 5px; }
  .bubble {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 10px; padding: 13px 15px; white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .bubble.you { background: transparent; border-style: dashed; }
  .bubble.err { border-color: var(--danger); }
  .actions { margin-top: 12px; display: flex; gap: 9px; flex-wrap: wrap; }
  button {
    font: inherit; padding: 8px 15px; border-radius: 7px; cursor: pointer;
    border: 1px solid var(--line); background: var(--panel); color: var(--text);
  }
  button.go { background: var(--accent); border-color: var(--accent); color: #fff; }
  button.danger { border-color: var(--danger); color: var(--danger); }
  button:disabled { opacity: .45; cursor: default; }
  form { border-top: 1px solid var(--line); padding: 14px 22px; }
  .row { display: flex; gap: 9px; max-width: 760px; margin: 0 auto; }
  input[type=text] {
    flex: 1; font: inherit; padding: 11px 13px; border-radius: 8px;
    border: 1px solid var(--line); background: var(--panel); color: var(--text);
  }
  input[type=text]:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  .hint { max-width: 760px; margin: 9px auto 0; color: var(--dim); font-size: 12px; }
  .spin::after {
    content: ""; display: inline-block; width: 11px; height: 11px;
    margin-left: 7px; vertical-align: -1px;
    border: 2px solid var(--dim); border-top-color: transparent;
    border-radius: 50%; animation: turn .7s linear infinite;
  }
  @keyframes turn { to { transform: rotate(360deg); } }
  code { background: var(--bg); padding: 1px 5px; border-radius: 4px; font-size: 13px; }
</style>
</head>
<body>
<header>
  <h1>Stratus</h1>
  <p>Describe the infrastructure you need. Nothing is built without your say-so.</p>
</header>

<main id="log">
  <div class="msg">
    <div class="who">Stratus</div>
    <div class="bubble">Tell me what you need and I'll work out how to build it on Azure.

You'll see exactly what would change, and what it would cost, before anything happens.

Try: <code>a private place to store some files</code></div>
  </div>
</main>

<form id="ask">
  <div class="row">
    <input type="text" id="q" placeholder="What do you need?" autocomplete="off" autofocus>
    <button class="go" id="send">Send</button>
  </div>
  <div class="hint" id="hint">Connected to your Azure account.</div>
</form>

<script>
const log = document.getElementById('log');
const form = document.getElementById('ask');
const box = document.getElementById('q');
const send = document.getElementById('send');
const hint = document.getElementById('hint');

function add(who, text, cls) {
  const wrap = document.createElement('div');
  wrap.className = 'msg';
  wrap.innerHTML = `<div class="who"></div><div class="bubble ${cls || ''}"></div>`;
  wrap.querySelector('.who').textContent = who;
  wrap.querySelector('.bubble').textContent = text;
  log.appendChild(wrap);
  wrap.scrollIntoView({behavior: 'smooth', block: 'end'});
  return wrap;
}

function busy(on, label) {
  send.disabled = on; box.disabled = on;
  hint.textContent = label || 'Connected to your Azure account.';
  hint.className = on ? 'hint spin' : 'hint';
}

form.onsubmit = async (e) => {
  e.preventDefault();
  const text = box.value.trim();
  if (!text) return;
  box.value = '';
  add('You', text, 'you');
  busy(true, 'Working out what to build');

  try {
    const res = await fetch('/api/plan', {
      method: 'POST',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({request: text}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Something went wrong.');

    if (data.nothing_to_do) { add('Stratus', data.summary); return; }

    let body = data.summary;
    if (data.assumptions && data.assumptions.length) {
      body += '\n\nI assumed:\n' + data.assumptions.map(a => '  - ' + a).join('\n');
    }
    body += '\n\n' + data.question;
    const bubble = add('Stratus', body);
    offerChoice(bubble, data);
  } catch (err) {
    add('Stratus', String(err.message || err), 'err');
  } finally {
    busy(false);
  }
};

function offerChoice(bubble, data) {
  const row = document.createElement('div');
  row.className = 'actions';

  const yes = document.createElement('button');
  // A destructive plan needs the word typed, exactly as on the command line.
  // Making it a single click here would quietly remove the gate.
  yes.className = data.destructive ? 'danger' : 'go';
  yes.textContent = data.destructive ? 'Type DELETE to confirm' : 'Build it';

  const no = document.createElement('button');
  no.textContent = 'Cancel';

  row.append(yes, no);
  bubble.appendChild(row);

  no.onclick = () => { row.remove(); add('Stratus', 'Cancelled. Nothing was changed.'); };

  yes.onclick = async () => {
    let answer = 'yes';
    if (data.destructive) {
      answer = prompt('This will destroy things. Type DELETE to confirm:') || '';
      if (answer !== 'DELETE') {
        row.remove();
        add('Stratus', 'Cancelled. Nothing was changed.');
        return;
      }
    }
    row.remove();
    busy(true, 'Building — this takes a couple of minutes');
    try {
      const res = await fetch('/api/apply', {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({id: data.id, answer}),
      });
      const out = await res.json();
      if (!res.ok) throw new Error(out.detail || 'Something went wrong.');
      add('Stratus', out.applied
        ? out.message + (out.summary ? '\n\n' + out.summary : '')
        : out.message);
    } catch (err) {
      add('Stratus', String(err.message || err), 'err');
    } finally {
      busy(false);
    }
  };
}
</script>
</body>
</html>
"""
