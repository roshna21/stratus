"""The web interface, as one self-contained page.

No build step, no framework, no dependency on a CDN. The whole reason this
project exists is that infrastructure should be simple to stand up, and a
page that needs npm before it can be served would sit badly beside that.

It also means the container image is Python and nothing else — the Dockerfile
copies `stratus/` and not `web/`, so this file, not the Next front end, is
what a deployed Stratus actually serves. It is the demo strangers see.

It deliberately shares the palette and the wording of the Next interface. Two
interfaces to one product that look like two products is worse than either.
What it does not share is the typeface: loading one would mean a request to
someone else's server, which is the dependency this page exists to avoid.
"""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stratus</title>
<style>
  :root {
    --canvas: #07050e; --surface: #100b1d; --raised: #180f2c;
    --hairline: #241a3d; --edge: #3a2a63;
    --fg: #f1ecfb; --fg-muted: #a89ec6; --fg-faint: #6f6593;
    --accent: #b39dff; --accent-bright: #d6c9ff; --violet: #7c3aed;
    --ok: #4fd7a4; --warn: #fbbf24; --danger: #fb7185;
    --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, monospace;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--canvas); color: var(--fg);
    font: 15px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    -webkit-font-smoothing: antialiased;
    font-variant-numeric: tabular-nums;
    display: flex; flex-direction: column; min-height: 100vh;
  }
  header {
    padding: 0 22px; height: 56px; flex-shrink: 0;
    border-bottom: 1px solid var(--hairline);
    display: flex; align-items: center; gap: 10px;
  }
  header h1 { margin: 0; font-size: 15px; font-weight: 600; letter-spacing: -.01em; }
  header p {
    margin: 0 0 0 auto; color: var(--fg-faint); font-size: 12px;
    font-family: var(--mono);
  }
  main { flex: 1; width: 100%; max-width: 780px; margin: 0 auto; padding: 28px 22px; }

  .msg { margin-bottom: 18px; animation: rise .3s cubic-bezier(.22,1,.36,1) both; }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } }

  .who {
    font-family: var(--mono); font-size: 10.5px; letter-spacing: .13em;
    text-transform: uppercase; color: var(--fg-faint); margin-bottom: 7px;
  }
  .bubble {
    background: var(--surface); border: 1px solid var(--hairline);
    border-radius: 12px; padding: 16px 18px; white-space: pre-wrap;
    overflow-wrap: anywhere; font-size: 14px;
  }
  /* What you said is shown as a quieter echo, not another card. The page is
     answering you; your own words are context, not content. */
  .msg.you { text-align: right; }
  .msg.you .bubble {
    display: inline-block; text-align: left; max-width: 85%;
    background: rgba(179,157,255,.10); border-color: rgba(179,157,255,.25);
  }
  .bubble.err { border-color: rgba(251,113,133,.4); background: rgba(251,113,133,.04); }
  .bubble.danger { border-color: rgba(251,113,133,.45); background: rgba(251,113,133,.04); }

  .alarm {
    display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
    background: rgba(251,113,133,.10); color: var(--danger);
    border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; font-size: 13.5px;
  }
  .alarm strong { font-weight: 600; }

  .actions { margin-top: 18px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  button {
    font: inherit; font-size: 14px; font-weight: 500;
    padding: 9px 16px; border-radius: 8px; cursor: pointer;
    border: 1px solid var(--edge); background: var(--raised); color: var(--fg);
    transition: background .18s, border-color .18s, box-shadow .18s;
  }
  button:hover:not(:disabled) { background: #22163d; }
  button.go {
    /* Lilac into a slightly brighter lilac, never down into the violet: a
       dark label on the deep end of the ramp falls below a readable
       contrast. The glow is where the violet goes instead. */
    background: linear-gradient(135deg, var(--accent-bright), var(--accent));
    border-color: transparent; color: var(--canvas);
    box-shadow: inset 0 1px 0 0 rgba(255,255,255,.25), 0 8px 24px -8px var(--violet);
  }
  button.go:hover:not(:disabled) { background: var(--accent-bright); }
  button.danger { border-color: rgba(251,113,133,.5); background: transparent; color: var(--danger); }
  button.danger:hover:not(:disabled) { background: rgba(251,113,133,.10); }
  button.quiet { border-color: transparent; background: transparent; color: var(--fg-muted); }
  button:disabled { opacity: .4; cursor: default; box-shadow: none; }

  form { border-top: 1px solid var(--hairline); padding: 16px 22px; flex-shrink: 0; }
  .row { display: flex; gap: 10px; max-width: 780px; margin: 0 auto; }
  input[type=text] {
    flex: 1; font: inherit; font-size: 14px; padding: 12px 15px; border-radius: 8px;
    border: 1px solid var(--hairline); background: var(--surface); color: var(--fg);
    transition: border-color .18s;
  }
  input[type=text]::placeholder { color: var(--fg-faint); }
  input[type=text]:focus { outline: none; border-color: var(--accent); }
  input.confirm {
    flex: 0 0 140px; font-family: var(--mono); background: var(--canvas);
    padding: 9px 12px;
  }
  input.confirm:focus { border-color: var(--danger); }
  .hint {
    max-width: 780px; margin: 11px auto 0; color: var(--fg-faint); font-size: 12px;
  }

  /* Terraform's own output. The one place the machinery is allowed to show:
     during a build, seeing something move is worth more than being shielded
     from the vocabulary. */
  .log {
    margin-top: 14px; max-height: 260px; overflow-y: auto;
    background: var(--canvas); border: 1px solid var(--hairline);
    border-radius: 8px; padding: 13px;
    font-family: var(--mono); font-size: 11.5px; line-height: 1.75;
    color: var(--fg-faint); white-space: pre-wrap; overflow-wrap: anywhere;
  }
  .done { color: var(--ok); font-size: 13.5px; margin-top: 14px; }

  code {
    background: var(--raised); padding: 2px 6px; border-radius: 4px;
    font-family: var(--mono); font-size: 12.5px;
  }
  .spin::after {
    content: ""; display: inline-block; width: 11px; height: 11px;
    margin-left: 8px; vertical-align: -1px;
    border: 2px solid var(--edge); border-top-color: var(--accent);
    border-radius: 50%; animation: turn .7s linear infinite;
  }
  @keyframes turn { to { transform: rotate(360deg); } }

  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--edge); border-radius: 999px; }

  @media (prefers-reduced-motion: reduce) {
    .msg { animation: none; }
    .spin::after { animation: none; }
  }
</style>
</head>
<body>
<header>
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
    <rect x="4" y="5" width="16" height="3.4" rx="1.7" fill="#b39dff"/>
    <rect x="2.5" y="10.3" width="19" height="3.4" rx="1.7" fill="#b39dff" opacity=".62"/>
    <rect x="6.5" y="15.6" width="11" height="3.4" rx="1.7" fill="#b39dff" opacity=".32"/>
  </svg>
  <h1>Stratus</h1>
  <p>nothing is built without your say-so</p>
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
  wrap.className = 'msg' + (cls === 'you' ? ' you' : '');
  wrap.innerHTML = `<div class="who"></div><div class="bubble"></div>`;
  wrap.querySelector('.who').textContent = who;
  const bubble = wrap.querySelector('.bubble');
  if (cls && cls !== 'you') bubble.classList.add(cls);
  // textContent, never innerHTML: this carries a summary written by a
  // language model and a plan describing someone's account.
  bubble.textContent = text;
  log.appendChild(wrap);
  wrap.scrollIntoView({behavior: 'smooth', block: 'end'});
  return wrap;
}

/**
 * What is happening, and how long it is reasonable to wait for it.
 *
 * The waiting time is the important half. Working out a plan takes thirty to
 * ninety seconds — it asks a model, reads the account, and runs a full plan
 * against Azure — and a bare spinner for that long reads as a hung page.
 */
function busy(on, label, wait) {
  send.disabled = on; box.disabled = on;
  hint.textContent = on
    ? label + (wait ? ' — ' + wait : '')
    : 'Connected to your Azure account.';
  hint.className = on ? 'hint spin' : 'hint';
}

form.onsubmit = async (e) => {
  e.preventDefault();
  const text = box.value.trim();
  if (!text) return;
  box.value = '';
  add('You', text, 'you');
  busy(true, 'Working out what to build', 'reading your account, designing it, then checking what would change. Usually under a minute.');

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
    // The server's own wording for the plan, unaltered. The command line,
    // this page and the Next interface must never describe one change three
    // different ways — two of them would be wrong.
    body += '\n\n' + data.question;

    const wrap = add('Stratus', body);
    if (data.destructive) {
      wrap.querySelector('.bubble').classList.add('danger');
      const alarm = document.createElement('div');
      alarm.className = 'alarm';
      alarm.innerHTML = '<strong>This will destroy things.</strong><span>Read it carefully.</span>';
      wrap.querySelector('.bubble').prepend(alarm);
    }
    offerChoice(wrap, data);
  } catch (err) {
    add('Stratus', String(err.message || err), 'err');
  } finally {
    busy(false);
  }
};

/**
 * Watch a build to completion, reporting each new batch of output.
 *
 * Only lines not already seen are requested, so a build producing hundreds
 * of them does not resend the whole log every second.
 */
async function followJob(id, onLines) {
  let seen = 0;
  for (;;) {
    const res = await fetch(`/api/jobs/${id}?since=${seen}`);
    const snap = await res.json();
    if (!res.ok) throw new Error(snap.detail || 'Lost track of the build.');
    if (snap.log && snap.log.length) { onLines(snap.log); seen = snap.log_length; }
    if (snap.status !== 'running') return snap;
    await new Promise(r => setTimeout(r, 1200));
  }
}

function offerChoice(wrap, data) {
  const bubble = wrap.querySelector('.bubble');
  const row = document.createElement('div');
  row.className = 'actions';

  const no = document.createElement('button');
  no.className = 'quiet';
  no.textContent = 'Cancel';
  no.onclick = () => { row.remove(); add('Stratus', 'Cancelled. Nothing was changed.'); };

  if (data.destructive) {
    // Typed in the page, exactly as on the command line. This used to be a
    // browser modal, which a browser is free to suppress — and a suppressed
    // one returns null, which read as "not DELETE" and so cancelled
    // silently. The gate has to be part of the page to be a gate.
    const field = document.createElement('input');
    field.type = 'text';
    field.className = 'confirm';
    field.placeholder = 'DELETE';
    field.setAttribute('aria-label', 'Type DELETE to confirm');

    const yes = document.createElement('button');
    yes.className = 'danger';
    yes.textContent = 'Destroy and build';
    yes.disabled = true;

    // An empty answer is never consent, and neither is anything else.
    field.oninput = () => { yes.disabled = field.value !== 'DELETE'; };
    yes.onclick = () => build(wrap, row, data.id, 'DELETE');

    row.append(field, yes, no);
  } else {
    const yes = document.createElement('button');
    yes.className = 'go';
    yes.textContent = 'Build it';
    yes.onclick = () => build(wrap, row, data.id, 'yes');
    row.append(yes, no);
  }

  bubble.appendChild(row);
}

async function build(wrap, row, id, answer) {
  row.remove();
  busy(true, 'Building', 'progress appears above as it happens. This takes a couple of minutes.');

  try {
    const res = await fetch('/api/apply', {
      method: 'POST',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({id, answer}),
    });
    const out = await res.json();
    if (!res.ok) throw new Error(out.detail || 'Something went wrong.');

    // A started build answers with a job to watch, not a result: a build
    // takes minutes, and an HTTP request that waits that long hits a
    // timeout somewhere between here and the server. Reading this reply as
    // though it were the finished answer printed "undefined" and left the
    // build running invisibly.
    if (!out.job) { add('Stratus', out.message || 'Cancelled. Nothing was changed.'); return; }

    const panel = add('Stratus', '');
    const stream = document.createElement('div');
    stream.className = 'log';
    panel.querySelector('.bubble').appendChild(stream);

    const finished = await followJob(out.job, (lines) => {
      stream.textContent += lines.join('\n') + '\n';
      stream.scrollTop = stream.scrollHeight;
    });

    if (finished.status === 'failed') {
      add('Stratus', finished.error || 'The build failed.', 'err');
      return;
    }

    const done = document.createElement('div');
    done.className = 'done';
    done.textContent = (finished.result && finished.result.summary) || 'Done.';
    panel.querySelector('.bubble').appendChild(done);
    panel.scrollIntoView({behavior: 'smooth', block: 'end'});
  } catch (err) {
    add('Stratus', String(err.message || err), 'err');
  } finally {
    busy(false);
  }
}
</script>
</body>
</html>
"""
