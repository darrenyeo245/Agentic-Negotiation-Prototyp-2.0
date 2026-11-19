import { avatar, brand, button, fullDate, h, ic, statusName, tag, time } from './ui.js';
import { mandateView, offerPanel, offers, overview, roomHeader } from './room.js';
import { mandateFields, offerFields, optionFields, readMandate, readOffer, setupFields } from './forms.js';
import { labPage, runDetail } from './lab.js';

const app = document.querySelector('#app'),
  dialog = document.querySelector('#dialog'),
  notice = document.querySelector('#notice');
const prefix = 'paktwerk.room.';
let session,
  view,
  draft = '',
  tab = 'overview',
  page = 'workspace',
  connected = true,
  ticket = 0,
  pending = false;
let flow = null,
  toastTimer,
  research = null,
  researchBusy = false,
  labConfig = { scenario: 'all', repeats: 1 };
const getRecord = (id) => JSON.parse(sessionStorage.getItem(prefix + id) || 'null');
const apiRoom = (suffix = '') => '/api/rooms/' + session.room + suffix;
async function api(url, body, auth = session?.token) {
  const headers = {};
  if (auth) headers.Authorization = 'Bearer ' + auth;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(url, {
    method: body === undefined ? 'GET' : 'POST',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Die Anfrage konnte nicht verarbeitet werden.');
  return data;
}
function notify(text) {
  clearTimeout(toastTimer);
  notice.textContent = text;
  notice.classList.add('visible');
  toastTimer = setTimeout(() => notice.classList.remove('visible'), 3800);
}
function errorText(e) {
  return e instanceof TypeError
    ? 'Die Plattform ist gerade nicht erreichbar. Bitte die Verbindung prüfen.'
    : e.message;
}
function reportError(e) {
  const error = dialog.open && dialog.querySelector('.form-error');
  if (error) {
    error.textContent = errorText(e);
    error.hidden = false;
    error.scrollIntoView({ block: 'nearest' });
  } else notify(errorText(e));
}
function setSession(s) {
  session = s;
  sessionStorage.setItem(prefix + s.room, JSON.stringify(s));
  sessionStorage.setItem('paktwerk.active', s.room);
  history.replaceState(null, '', '/r/' + s.room);
  view = null;
  draft = '';
  page = 'workspace';
  tab = 'overview';
  connected = true;
}
function clearTabCredentials() {
  for (const k of Object.keys(sessionStorage)) if (k.startsWith('paktwerk.')) sessionStorage.removeItem(k);
}
async function start() {
  try {
    const fragment = new URLSearchParams(location.hash.slice(1));
    if (fragment.has('join')) {
      const [id, secret] = fragment.get('join').split('.');
      clearTabCredentials();
      history.replaceState(null, '', '/r/' + encodeURIComponent(id));
      setSession(await api('/api/rooms/' + encodeURIComponent(id) + '/join', { invite: secret }, null));
    } else {
      const requested = location.pathname.match(/^\/r\/([A-F0-9]{10})\/?$/)?.[1];
      if (!requested) {
        // Without a room in the address, the tab opens in the workspace instead of creating a demo room.
        visit('rooms');
        return;
      }
      const saved = getRecord(requested);
      if (!saved) {
        throw new Error(
          'Für diesen Raum fehlt in diesem Tab der persönliche Zugang. Öffnen Sie den Gastlink oder den ursprünglichen Raum-Tab.',
        );
      }
      setSession(saved);
    }
    await refresh(true);
  } catch (e) {
    app.innerHTML =
      `<main id="main" class="entry-error"><div class="brand">${brand}</div><h1>Raumzugang</h1><p>${
        h(errorText(e))
      }</p><div class="crumb-actions">${button('rooms', 'Zum Arbeitsbereich', 'grid', 'btn secondary')}${
        button('new-demo', 'Eigenen Demoraum öffnen', 'arrow', 'btn primary')
      }</div></main>`;
  }
}
function remember() {
  const p = view.room;
  session = {
    ...session,
    title: p.subject,
    company: p.companies[view.me.side],
    status: p.status,
    at: p.created,
  };
  sessionStorage.setItem(prefix + session.room, JSON.stringify(session));
}
async function refresh(force = false) {
  if (!session) return;
  const seq = ++ticket, id = session.room;
  const next = await api(apiRoom());
  if (seq !== ticket || id !== session.room) return;
  const changed = force || !view || !connected || next.room.revision !== view.room.revision ||
    view.me.blocked !== next.me.blocked;
  if (view && view.room.epochs[view.me.side] !== next.room.epochs[next.me.side]) draft = '';
  connected = true;
  view = next;
  if (changed) {
    remember();
    render();
  }
}
function shell(body) {
  const p = view?.room, s = view?.me.side;
  return `<header class="topbar"><div class="top-inner">
    <button class="brand" data-cmd="workspace" aria-label="Paktwerk Arbeitsbereich">${brand}</button>
    <nav class="primary-nav" aria-label="Hauptnavigation">${
    [['workspace', 'grid', 'Arbeitsbereich'], ['lab', 'lab', 'Forschungslabor']].map(([k, i, l]) =>
      `<button data-cmd="${k}" class="nav-item ${(page === 'lab') === (k === 'lab') ? 'active' : ''}" ${
        (page === 'lab') === (k === 'lab') ? 'aria-current="page"' : ''
      }>${ic(i, 16)}${l}</button>`
    ).join('')
  }</nav>
    <div class="top-profile">${
    view
      ? `<span class="secure">${ic('shield', 15)}Geschützter Raum</span><button class="profile" data-cmd="identity">${
        avatar(p.companies[s], s, true)
      }<span><strong>${h(p.companies[s])}</strong><small>Firma ${s} · ${
        s === 'A' ? 'Einkauf' : 'Lieferant'
      }</small></span>${ic('down', 13)}</button>`
      : ''
  }</div></div></header>
    <main class="workspace" id="main">${body}</main>
    <footer class="page-foot"><span>${
    ic('lock', 13)
  }Geschützter Verhandlungsraum</span><span>Paktwerk · Forschungsprototyp</span></footer>`;
}
function roomList() {
  const items = Object.keys(sessionStorage).filter((k) => k.startsWith(prefix)).map((k) =>
    JSON.parse(sessionStorage[k])
  ).sort((a, b) => b.at - a.at);
  return `<div class="crumb-row"><div class="crumb">${
    ic('grid', 15)
  }Arbeitsbereich</div></div><div class="page-heading"><h1>Meine Verhandlungsräume</h1><div class="crumb-actions">${
    button('new-demo', 'Demoraum öffnen', 'arrow', 'btn secondary')
  }${button('new', 'Neue Verhandlung', 'plus', 'btn primary')}</div></div>
    <section class="card room-list">${
    items.length ? '' : '<p class="empty-copy">In diesem Tab gibt es noch keine Verhandlungsräume. Legen Sie eine neue Verhandlung an oder öffnen Sie den vorbereiteten Demoraum.</p>'
  }${
    items.map((s) =>
      `<button data-cmd="open-room" data-id="${h(s.room)}"><span class="heading-icon">${
        ic('folder', 22)
      }</span><span><strong>${h(s.title || 'Verhandlungsraum')}</strong><small>${
        h(s.company || '')
      } · Firma ${h(s.side)}</small></span>${tag(s.status || 'active')}${ic('chevron', 16)}</button>`
    ).join('')
  }</section>`;
}
function render() {
  if (!view && page === 'workspace') return;
  const thread = document.querySelector('#thread');
  const previous = thread
    ? { top: thread.scrollTop, nearEnd: thread.scrollHeight - thread.scrollTop - thread.clientHeight < 40 }
    : null;
  const input = document.activeElement?.id === 'message-text' ? document.activeElement : null;
  const selection = input ? [input.selectionStart, input.selectionEnd] : null;
  const body = page === 'lab'
    ? labPage(research, labConfig, researchBusy)
    : page === 'rooms'
    ? roomList()
    : roomHeader(view, tab) + (tab === 'offers'
      ? offers(view)
      : tab === 'mandate'
      ? mandateView(view)
      : overview(view, draft, connected));
  app.innerHTML = shell(body);
  document.title =
    (page === 'lab' ? 'Forschungslabor' : page === 'rooms' ? 'Arbeitsbereich' : view.room.subject) +
    ' · Paktwerk';
  const next = document.querySelector('#thread');
  if (next && previous) next.scrollTop = previous.nearEnd ? next.scrollHeight : previous.top;
  if (selection) {
    const input = document.querySelector('#message-text');
    if (input) {
      input.focus({ preventScroll: true });
      input.setSelectionRange(...selection);
    }
  }
  if (dialog.open && flow?.kind === 'review') review(flow.version);
}
function modal(title, body, wide = false) {
  dialog.className = wide ? 'wide-dialog' : '';
  dialog.innerHTML = `<div class="dialog-head"><h2 id="dialog-title">${
    h(title)
  }</h2><button type="button" class="icon-button" data-cmd="close" aria-label="Schließen">${
    ic('close', 19)
  }</button></div><div class="dialog-body">${body}<p class="form-error" role="alert" hidden></p></div>`;
  if (!dialog.open) dialog.showModal();
  dialog.querySelector('.dialog-body').scrollTop = 0;
}
function close() {
  if (dialog.open) dialog.close();
  flow = null;
}
function visit(nextPage, nextTab = 'overview') {
  close();
  if (nextPage === 'workspace' && !view) nextPage = 'rooms';
  // The address follows the view, so reloading the workspace does not reopen the last room.
  if (nextPage === 'rooms') history.replaceState(null, '', '/');
  if (nextPage === 'workspace') history.replaceState(null, '', '/r/' + session.room);
  page = nextPage;
  tab = nextTab;
  render();
  scrollTo({ top: 0, behavior: 'instant' });
}
async function act(action, data = {}, message = '') {
  if (pending) return;
  pending = true;
  const submit = dialog.open ? dialog.querySelector('button[type="submit"], [data-cmd="approve"]') : null;
  if (submit) submit.disabled = true;
  try {
    const p = view.room;
    await api(apiRoom('/action'), {
      action,
      epoch: p.epochs[view.me.side],
      version: p.offers.length,
      ...data,
    });
    if (action === 'message') draft = '';
    close();
    await refresh(true);
    if (message) notify(message);
  } catch (e) {
    if (submit) submit.disabled = false;
    reportError(e);
    await refresh();
  } finally {
    pending = false;
  }
}
async function invite() {
  const recordKey = 'paktwerk.invite.' + session.room;
  let key = sessionStorage.getItem(recordKey);
  if (!key) {
    key = (await api(apiRoom('/invite'), {})).invite;
    sessionStorage.setItem(recordKey, key);
  }
  const url = location.origin + '/#join=' + session.room + '.' + key;
  modal(
    'Gegenfirma einladen',
    `<div class="modal-symbol">${ic('invite', 26)}</div><h3>Gastzugang für ${
      h(view.room.companies.B)
    }</h3><p>Über diesen Link tritt eine berechtigte Person als Firma B bei. Der Link lässt sich einmal einlösen.</p>
    <label class="field"><span>Persönlicher Einladungslink</span><input id="invite-url" readonly value="${
      h(url)
    }"></label>
    <div class="dialog-actions">${
      button('copy', 'Link kopieren', 'copy', 'btn secondary')
    }<a class="btn primary" href="${h(url)}" target="_blank" rel="noopener noreferrer">Gastansicht öffnen ${
      ic('upRight', 15)
    }</a></div>
    <p class="note muted">Für die Vorführung können Sie den Gastzugang im zweiten Tab öffnen. Die Freigabe des Einkaufs bleibt im ersten Tab.</p>`,
  );
}
function rules() {
  const p = view.room;
  const remaining = Math.max(0, Math.ceil((p.deadline - Date.now() / 1000) / 60));
  modal(
    'Gemeinsame Spielregeln',
    `<p>${h(view.schema.rule)}</p><div class="detail-list">${
      [
        ['Verhandlungsfrist', fullDate(p.deadline) + ' · ' + time(p.deadline) + ' Uhr'],
        ['Verbleibende Zeit', remaining + ' Minuten'],
        ['Verhandlungsschritte', p.turns + ' von ' + p.maxTurns],
        ['Szenarioversion', p.scenarioVersion],
      ].map(([l, x]) => `<div class="detail-row"><span>${l}</span><strong>${h(x)}</strong></div>`).join('')
    }</div><p>Je Firma versendet die aktive Vertretung Nachrichten und Angebote. Für den simulierten Abschluss müssen beide Firmen dieselbe aktuelle Version persönlich freigeben.</p>`,
  );
}
function identity() {
  const s = view.me.side, p = view.room;
  modal(
    'Ihr Raumzugang',
    `<div class="identity-row">${avatar(p.companies[s], s)}<div><h3>${
      h(p.companies[s])
    }</h3><p>Firma ${s} · ${
      s === 'A' ? 'Einkauf und Raumgründung' : 'Lieferant mit Gastzugang'
    }</p></div></div><div class="detail-row"><span>Aktive Vertretung</span><strong>${
      statusName(p.modes[s])
    }</strong></div><p>In diesem Tab können Sie Angebote für Ihre Firma prüfen und persönlich freigeben.</p><div class="dialog-actions">${
      button('rooms', 'Meine Räume', 'folder', 'btn secondary')
    }${button('own-mandate', 'Mein Mandat', 'lock', 'btn primary')}</div>`,
  );
}
function review(version = view.room.offers.length) {
  flow = { kind: 'review', version };
  const latest = view.room.offers.length;
  const updated = version < latest
    ? `<div class="review-banner"><span>V${version} wurde ersetzt.</span>${
      button('review', 'Aktuelle V' + latest + ' prüfen', 'arrow', 'text-btn')
    }</div>`
    : '';
  modal('Angebot V' + version + ' prüfen', updated + offerPanel(view, version, true));
}
function makeOffer() {
  const p = view.room;
  const fallback = Object.fromEntries(view.schema.fields.map((f) => [f.key, p.request[f.key] ?? null]));
  const current = p.offers.at(-1)?.terms || fallback;
  flow = { kind: 'offer', version: p.offers.length, epoch: p.epochs[view.me.side] };
  modal(
    'Strukturiertes Angebot',
    `<form id="offer-form"><p>Geben Sie das vollständige Paket für V${
      flow.version + 1
    } an. Mit dem Versand verfallen frühere Freigaben.</p>
    ${offerFields(view.schema, current)}<div class="dialog-actions">${
      button('close', 'Abbrechen', '', 'btn secondary')
    }<button class="btn primary" type="submit">Angebot versenden ${ic('send', 15)}</button></div></form>`,
  );
}
async function editMandate(kind, profile = 'flexibel') {
  const own = view.me.mandate;
  if (kind === 'delegate' && own) {
    return act('mode', { mode: 'agent' }, 'Der Agent hat den bisherigen Verlauf übernommen.');
  }
  const m = own || await api(apiRoom('/template?profile=' + profile));
  flow = {
    kind,
    side: view.me.side,
    schema: view.schema,
    mandate: m,
    profile,
    version: own?.version || 0,
    epoch: view.room.epochs[view.me.side],
  };
  showMandate();
}
function showMandate() {
  const f = flow;
  const create = f.kind === 'create-mandate', delegate = f.kind === 'delegate';
  const profile = f.side === 'B' && !f.version ? f.profile : null;
  const text = create ? 'Raum erstellen' : delegate ? 'Mandat erteilen und übergeben' : 'Mandat speichern';
  modal(
    create
      ? 'Privates Käufermandat'
      : delegate
      ? 'An meinen Agenten übergeben'
      : 'Privates Mandat bearbeiten',
    `<form id="mandate-form">${mandateFields(f.schema, f.mandate, f.side, profile)}
    <div class="dialog-actions">${
      button(create ? 'back-setup' : 'close', create ? 'Zurück' : 'Abbrechen', '', 'btn secondary')
    }<button type="submit" class="btn primary">${
      ic(delegate ? 'bot' : 'check', 16)
    }${text}</button></div></form>`,
    true,
  );
}
async function newRoom() {
  const setup = await api('/api/setup?scenario=boxes', undefined, null);
  const config = {
    scenario: 'boxes',
    subject: setup.schema.title,
    companies: { ...setup.schema.companies },
    minutes: 60,
    maxTurns: 18,
    mode: 'agent',
  };
  flow = { kind: 'setup', side: 'A', config, schema: setup.schema, mandate: setup.mandate, version: 0 };
  showSetup();
}
function showSetup() {
  modal(
    'Neue Verhandlung',
    `<form id="setup-form"><p>Richten Sie den Raum für beide Firmen ein. Im nächsten Schritt erteilen Sie Ihr privates Mandat.</p>${
      setupFields(flow.config)
    }<div class="dialog-actions">${
      button('close', 'Abbrechen', '', 'btn secondary')
    }<button type="submit" class="btn primary">Zum Käufermandat ${ic('arrow', 15)}</button></div></form>`,
    true,
  );
}
async function command(cmd, el) {
  switch (cmd) {
    case 'close':
      close();
      break;
    case 'workspace':
      visit('workspace');
      break;
    case 'rooms':
      visit('rooms');
      break;
    case 'lab':
      visit('lab');
      break;
    case 'offers':
      visit('workspace', 'offers');
      break;
    case 'own-mandate':
      visit('workspace', 'mandate');
      break;
    case 'open-room':
      setSession(getRecord(el.dataset.id));
      await refresh(true);
      break;
    case 'new-demo':
      setSession(await api('/api/rooms', { demo: true }, null));
      await refresh(true);
      break;
    case 'new':
      await newRoom();
      break;
    case 'invite':
      await invite();
      break;
    case 'identity':
      identity();
      break;
    case 'rules':
      rules();
      break;
    case 'copy': {
      const input = document.querySelector('#invite-url');
      try {
        await navigator.clipboard.writeText(input.value);
        notify('Einladungslink kopiert.');
      } catch {
        input.select();
        if (document.execCommand('copy')) notify('Einladungslink kopiert.');
        else notify('Link markiert. Mit Strg/Cmd + C kopieren.');
      }
      break;
    }
    case 'review':
      review();
      break;
    case 'offer-detail':
      review(Number(el.dataset.version));
      break;
    case 'approve':
      if (!dialog.open) {
        review(Number(el.dataset.version));
        break;
      }
      await act(
        'approve',
        { version: Number(el.dataset.version) },
        'Ihre persönliche Freigabe wurde gespeichert.',
      );
      break;
    case 'take':
      await act('mode', { mode: 'human' }, 'Sie vertreten Ihre Firma jetzt persönlich.');
      break;
    case 'delegate':
    case 'edit-mandate':
      await editMandate(cmd);
      break;
    case 'make-offer':
      makeOffer();
      break;
    case 'back-setup':
      flow.mandate = readMandate(document.querySelector('#mandate-form'), flow.schema, 'A');
      flow.kind = 'setup';
      showSetup();
      break;
    case 'add-option': {
      const rows = [...dialog.querySelectorAll('[data-option]')];
      if (rows.length >= 8) {
        notify('Bis zu acht Leistungspakete sind möglich.');
        break;
      }
      const idx = Math.max(-1, ...rows.map((x) => Number(x.dataset.option))) + 1;
      const template = flow.mandate.options[0];
      document.querySelector('#seller-options').insertAdjacentHTML(
        'beforeend',
        optionFields(flow.schema, template, idx),
      );
      break;
    }
    case 'remove-option':
      if (dialog.querySelectorAll('[data-option]').length > 1) el.closest('[data-option]').remove();
      else notify('Mindestens ein leistbares Paket ist erforderlich.');
      break;
    case 'export': {
      const blob = new Blob([JSON.stringify(research, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob), a = document.createElement('a');
      a.href = url;
      a.download = 'paktwerk-forschung.json';
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 3000);
      break;
    }
    case 'run-detail':
      modal('Laufprotokoll', runDetail(research.runs[Number(el.dataset.index)]));
      break;
  }
}
document.addEventListener('click', async (e) => {
  const el = e.target.closest('[data-cmd],[data-tab]');
  if (!el || el.disabled) return;
  try {
    if (el.dataset.tab) {
      visit('workspace', el.dataset.tab);
      return;
    }
    await command(el.dataset.cmd, el);
  } catch (err) {
    reportError(err);
  }
});
dialog.addEventListener('click', (e) => {
  if (e.target === dialog) {
    const r = dialog.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) close();
  }
});
dialog.addEventListener('cancel', () => {
  flow = null;
});
document.addEventListener('input', (e) => {
  if (e.target.id === 'message-text') draft = e.target.value;
});
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && e.target.id === 'message-text') {
    e.target.form.requestSubmit();
  }
});
document.addEventListener('change', async (e) => {
  try {
    if (e.target.id === 'scenario' && flow?.kind === 'setup') {
      const f = flow, selected = e.target.value, values = Object.fromEntries(new FormData(e.target.form));
      const setup = await api('/api/setup?scenario=' + selected, undefined, null);
      if (flow !== f || dialog.querySelector('#scenario')?.value !== selected) return;
      const previous = f.schema;
      f.schema = setup.schema;
      f.mandate = setup.mandate;
      f.config = {
        scenario: selected,
        mode: values.mode,
        minutes: values.minutes,
        maxTurns: values.maxTurns,
        subject: values.subject === previous.title ? setup.schema.title : values.subject,
        companies: {
          A: values.firmA,
          B: values.firmB === previous.companies.B ? setup.schema.companies.B : values.firmB,
        },
      };
      showSetup();
    }
    if (e.target.id === 'profile' && flow) {
      const f = flow, selected = e.target.value;
      const m = await api(apiRoom('/template?profile=' + selected));
      if (flow !== f || dialog.querySelector('#profile')?.value !== selected) return;
      f.profile = selected;
      f.mandate = m;
      showMandate();
    }
  } catch (err) {
    reportError(err);
  }
});
document.addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  try {
    if (form.id === 'message-form') {
      if (!draft.trim()) return;
      await act('message', { text: draft.trim() });
    } else if (form.id === 'offer-form') {
      await act(
        'offer',
        { terms: readOffer(form, view.schema), version: flow.version, epoch: flow.epoch },
        'Das neue Angebot wurde versendet.',
      );
    } else if (form.id === 'setup-form') {
      const v = Object.fromEntries(new FormData(form));
      if (v.scenario !== flow.schema.key) return;
      flow.config = {
        scenario: v.scenario,
        mode: v.mode,
        subject: v.subject,
        companies: { A: v.firmA, B: v.firmB },
        minutes: +v.minutes,
        maxTurns: +v.maxTurns,
      };
      flow.kind = 'create-mandate';
      showMandate();
    } else if (form.id === 'mandate-form') {
      const f = flow, m = readMandate(form, f.schema, f.side);
      if (f.kind === 'create-mandate') {
        if (pending) return;
        pending = true;
        form.querySelector('[type="submit"]').disabled = true;
        try {
          setSession(await api('/api/rooms', { ...f.config, mandate: m }, null));
          close();
          await refresh(true);
          await invite();
        } finally {
          pending = false;
          if (form.isConnected) form.querySelector('[type="submit"]').disabled = false;
        }
      } else if (f.kind === 'delegate') {
        await act(
          'mode',
          { mode: 'agent', mandate: m, epoch: f.epoch },
          'Mandat erteilt. Ihr Agent hat übernommen.',
        );
      } else {
        await act(
          'mandate',
          { mandate: m, mandateVersion: f.version },
          'Ihr privates Mandat wurde gespeichert.',
        );
      }
    } else if (form.id === 'research-form') {
      if (researchBusy) return;
      labConfig = { scenario: form.elements.scenario.value, repeats: form.elements.repeats.valueAsNumber };
      researchBusy = true;
      render();
      try {
        research = await api('/api/research', labConfig, null);
      } finally {
        researchBusy = false;
        render();
      }
    }
  } catch (err) {
    reportError(err);
  }
});
let polling = false;
setInterval(async () => {
  if (!session || !view || pending || polling || document.visibilityState === 'hidden') return;
  polling = true;
  try {
    await refresh();
  } catch {
    if (connected) {
      connected = false;
      render();
    }
  } finally {
    polling = false;
  }
}, 1100);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && session && view) refresh().catch(() => {});
});
start();
