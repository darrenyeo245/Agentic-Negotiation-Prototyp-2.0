import {
  approvals,
  avatar,
  button,
  fullDate,
  h,
  ic,
  live,
  money,
  packageRows,
  reviewNote,
  statusName,
  strategies,
  tag,
  time,
} from './ui.js';

const openLabels = {
  early_qty: 'Menge der Teillieferung',
  early_day: 'Termin der Teillieferung',
  price: 'Gesamtpreis des neuen Pakets',
  hours: 'Leistungsumfang',
  due: 'Fertigstellungstermin',
};
const roleName = (side) => side === 'A' ? 'Einkauf' : 'Lieferant';

export function roomHeader(v, tab) {
  const p = v.room, isBuyer = v.me.side === 'A';
  const invite = isBuyer && !p.joined.B && live(p);
  const remaining = Math.max(0, Math.ceil((p.deadline - Date.now() / 1000) / 60));
  const meta = p.status === 'active' || p.status === 'review'
    ? `Frist ${time(p.deadline)} Uhr`
    : `Fristende ${time(p.deadline)} Uhr`;
  return `<div class="crumb-row"><div class="crumb">${
    button('rooms', 'Arbeitsbereich', 'grid', 'crumb-btn')
  }${ic('chevron', 13)}<span>Verhandlungsraum</span></div>
    <div class="crumb-actions">${button('new', 'Neue Verhandlung', 'plus', 'btn secondary compact')}${
    invite ? button('invite', 'Gegenfirma einladen', 'invite', 'btn primary compact') : ''
  }</div></div>
    <section class="hero ${p.scenario === 'boxes' ? 'box-hero' : 'service-hero'}">
      <div class="hero-photo" aria-hidden="true"></div>
      <div class="hero-inner"><div class="hero-meta">${tag(p.status)}<span class="hero-id">${
    p.demo ? 'DEMORAUM' : 'RAUM'
  } · ${h(p.id.slice(0, 6))}</span></div>
      <h1>${h(p.subject)}</h1><div class="hero-firms">${ic('building', 16)}<span>${h(p.companies.A)}</span>${
    ic('exchange', 16)
  }<span>${h(p.companies.B)}</span></div></div>
    </section>
    <div class="tabbar"><div class="tabs" role="navigation" aria-label="Verhandlungsansichten">
      ${
    [['overview', 'chat', 'Verhandlungsraum'], ['offers', 'layers', 'Angebote'], [
      'mandate',
      'lock',
      'Mein Mandat',
    ]].map(([k, i, l]) =>
      `<button type="button" data-tab="${k}" class="tab ${tab === k ? 'active' : ''}" ${
        tab === k ? 'aria-current="page"' : ''
      }>${ic(i, 16)}${l}${k === 'offers' ? `<span class="count">${p.offers.length}</span>` : ''}</button>`
    ).join('')
  }</div>
      ${
    button(
      'rules',
      h(meta),
      'clock',
      'deadline',
      'title="Spielregeln und verbleibende Frist anzeigen" data-minutes="' + remaining + '"',
    )
  }</div>`;
}

function dayLabel(stamp) {
  const date = new Date(stamp * 1000);
  const prefix = date.toDateString() === new Date().toDateString() ? 'Heute, ' : '';
  return prefix + date.toLocaleDateString('de-DE', { day: '2-digit', month: 'long' });
}
function message(p, e) {
  const name = p.companies[e.side];
  if (['mode', 'joined', 'approve', 'agreement', 'end'].includes(e.kind)) {
    const prepend = ['mode', 'joined', 'approve'].includes(e.kind) ? h(name) + ' ' : '';
    // An agent's reasoned exit keeps its own words above the platform's closing line.
    return (e.note ? bubble(p, e, `<p>${h(e.note)}</p>`) : '') + `<div class="system-event">${
      ic(
        e.kind === 'agreement'
          ? 'checkCircle'
          : e.kind === 'mode'
          ? 'exchange'
          : e.kind === 'end'
          ? 'flag'
          : e.kind === 'approve'
          ? 'check'
          : 'people',
        14,
      )
    }<span>${prepend}${h(e.text)}</span><time>${time(e.at)}</time></div>`;
  }
  // The binding wording comes from the platform. An agent's accompanying note stays visibly separate.
  const text = e.note ? `<p>${h(e.note)}</p><p class="binding">${h(e.text)}</p>` : `<p>${h(e.text)}</p>`;
  return bubble(
    p,
    e,
    text + (e.kind === 'offer'
      ? `<button class="version-link" data-cmd="offer-detail" data-version="${e.version}">${
        ic('doc', 13)
      } Angebot V${e.version}${ic('upRight', 12)}</button>`
      : ''),
  );
}

function bubble(p, e, body) {
  const isBot = e.actor === 'agent';
  return `<article class="message"><div class="msg-avatar ${e.side === 'A' ? 'buyer' : 'seller'}">${
    ic(isBot ? 'bot' : 'person', 19)
  }</div>
    <div class="msg-body"><div class="msg-head"><strong>${h(p.companies[e.side])}</strong><span class="actor ${
    isBot ? 'agent' : ''
  }">${isBot ? ic('spark', 10) : ''}${isBot ? 'Agent' : 'Mensch'}</span><time>${time(e.at)}</time></div>
    <div class="bubble ${isBot ? 'agent-bubble' : ''}">${body}</div>
    </div></article>`;
}

function conversation(v, draft, connected) {
  const p = v.room, side = v.me.side, agent = p.modes[side] === 'agent';
  let lastDay = '';
  const events = p.events.map((e) => {
    const d = dayLabel(e.at);
    const divider = d !== lastDay ? `<div class="day-divider"><span>${h(d)}</span></div>` : '';
    lastDay = d;
    return divider + message(p, e);
  }).join('');
  let composer;
  if (!live(p)) {
    composer = `<div class="compose-status"><span>${ic(p.status === 'agreed' ? 'checkCircle' : 'flag')} ${
      p.status === 'agreed' ? 'Einigung dokumentiert' : 'Verhandlung beendet'
    }</span>${button('offers', 'Angebote ansehen', 'arrow', 'btn secondary compact')}</div>`;
  } else if (agent) {
    composer = `<div class="compose-status"><div class="compose-identity"><span class="soft-icon">${
      ic('bot', 19)
    }</span><div><strong>Ihr Agent vertritt Sie</strong><small>${
      v.preparing === side ? 'Eine Antwort wird vorbereitet.' : 'Die Freigabe liegt bei Ihnen.'
    }</small></div></div>${button('take', 'Selbst übernehmen', 'person', 'btn secondary compact')}</div>`;
  } else {
    composer =
      `<form id="message-form" class="composer"><label class="sr" for="message-text">Ihre Nachricht</label><textarea id="message-text" maxlength="2000" rows="2" placeholder="Nachricht an ${
        h(p.companies[side === 'A' ? 'B' : 'A'])
      } …" required>${h(draft)}</textarea><div><button type="button" class="text-btn" data-cmd="make-offer">${
        ic('doc', 15)
      }Angebot erstellen</button><button class="btn primary compact" type="submit">Senden ${
        ic('send', 14)
      }</button></div></form>`;
  }
  return `<section class="card discussion"><div class="panel-head"><h2><span class="heading-icon">${
    ic('chat', 19)
  }</span>Gesprächsverlauf</h2><span class="live-indicator ${connected ? '' : 'offline'}"><i></i>${
    connected ? 'Live' : 'Offline'
  }</span></div>
    <div class="thread" id="thread" tabindex="0" aria-label="Gesprächsverlauf">${events}${
    v.preparing
      ? `<div class="typing"><i></i>Der Agent von ${
        h(p.companies[v.preparing])
      } bereitet eine Antwort vor …</div>`
      : ''
  }</div>${composer}</section>`;
}

function summary(v) {
  const p = v.room, schema = v.schema, offer = p.offers.at(-1);
  if (!offer) {
    return `<section class="card offer-card"><div class="panel-head"><h2>${
      ic('doc', 19)
    }Aktuelles Angebot</h2></div><div class="empty"><span class="soft-icon">${
      ic('doc', 24)
    }</span><p>Das erste vollständige Angebot steht noch aus.</p>${
      p.modes[v.me.side] === 'human' && live(p)
        ? button('make-offer', 'Angebot erstellen', 'plus', 'btn primary')
        : ''
    }</div></section>`;
  }
  const t = offer.terms;
  const details = p.scenario === 'boxes'
    ? [
      ['box', 'Gesamtmenge', t.quantity + ' Stück'],
      ['split', 'Teillieferung', t.early_qty ? `${t.early_qty} bis Werktag ${t.early_day}` : 'Keine'],
      ['truck', 'Gesamtlieferung', `Bis Werktag ${t.final_day}`],
    ]
    : [['rules', 'Leistungsumfang', t.hours + ' Stunden'], [
      'calendar',
      'Fertigstellung',
      `Bis Werktag ${t.due}`,
    ]];
  return `<section class="card offer-card"><div class="panel-head"><h2>${
    ic('doc', 19)
  }Aktuelles Angebot</h2><span class="version">V${offer.version}</span></div>
    <div class="offer-main"><span class="eyebrow">Gesamtpreis</span><div class="price">${
    h(money(t.price))
  }</div><small>${h(schema.priceNote)}</small></div>
    <dl class="specs">${
    details.map(([i, k, value]) => `<div><dt>${ic(i, 16)}${k}</dt><dd>${h(value)}</dd></div>`).join('')
  }</dl>
    <div class="offer-foot"><button class="btn primary full" data-cmd="review">Angebot prüfen ${
    ic('arrow', 16)
  }</button></div></section>`;
}

function representation(v) {
  const p = v.room, side = v.me.side, agent = p.modes[side] === 'agent';
  return `<section class="card representation"><div class="panel-head"><h2>${
    ic('people', 19)
  }Vertretung</h2>${
    button('rules', '', 'rules', 'icon-button', 'aria-label="Spielregeln" title="Spielregeln"')
  }</div>
    <div class="party-list">${
    ['A', 'B'].map((k) =>
      `<div class="party">${avatar(p.companies[k], k, true)}<div><strong>${
        h(p.companies[k])
      }</strong><small>${roleName(k)}${side === k ? ' · Ihre Firma' : ''}</small></div><span class="actor ${
        p.modes[k] === 'agent' ? 'agent' : ''
      }">${ic(p.modes[k] === 'agent' ? 'bot' : 'person', 12)}${statusName(p.modes[k])}</span></div>`
    ).join('')
  }</div>
    ${
    live(p) && !agent
      ? `<div class="rep-action">${
        button('delegate', 'An meinen Agenten übergeben', 'bot', 'btn secondary full')
      }</div>`
      : ''
  }</section>`;
}

function openPoints(v) {
  if (!v.openKeys.length) return '';
  return `<section class="card open-points"><div class="panel-head"><h2>${
    ic('list', 18)
  }Offene Punkte</h2><span class="count">${v.openKeys.length}</span></div><ul>${
    v.openKeys.map((k) => `<li><i></i>${h(openLabels[k] || k)}</li>`).join('')
  }</ul></section>`;
}

export function overview(v, draft, connected) {
  const p = v.room;
  const review = p.status === 'review' || p.status === 'agreed';
  return `${
    review
      ? `<div class="review-banner"><span>${ic('checkCircle', 20)}${
        p.status === 'agreed'
          ? 'Beide Firmen haben dasselbe Paket freigegeben.'
          : 'Ein vollständiges Paket liegt zur Freigabe bereit.'
      }</span>${button('review', 'V' + p.offers.length + ' ansehen', 'arrow', 'text-btn')}</div>`
      : ''
  }
    <div class="room-grid"><div class="main-column">${conversation(v, draft, connected)}${
    openPoints(v)
  }</div><aside>${summary(v)}${representation(v)}</aside></div>`;
}

export function offerPanel(v, version, compact = false) {
  const p = v.room,
    offer = p.offers[version - 1],
    prev = p.offers[version - 2],
    current = version === p.offers.length;
  if (!offer) return '<p>Es liegt noch kein Angebot vor.</p>';
  const approved = p.approvals[v.me.side] === version;
  return `<div class="offer-line"><span class="version">V${version}</span><strong>${
    h(p.companies[offer.side])
  }</strong><small>${fullDate(offer.at)} · ${time(offer.at)} Uhr</small></div>
    ${
    prev ? '<p class="muted note">Geänderte Konditionen zeigen den vorherigen Wert durchgestrichen.</p>' : ''
  }
    <div class="detail-list">${packageRows(v.schema, offer.terms, prev?.terms)}</div>
    ${
    current
      ? `${reviewNote(v.me)}<h3 class="subheading">Persönliche Freigaben für V${version}</h3>${approvals(p)}
    ${
        compact && live(p)
          ? `<div class="dialog-actions">${
            p.modes[v.me.side] === 'human'
              ? button('make-offer', 'Gegenangebot', 'edit', 'btn secondary')
              : ''
          }<button type="button" data-cmd="approve" data-version="${version}" class="btn primary" ${
            approved || !v.me.assessment?.valid ? 'disabled' : ''
          }>${ic('check', 15)}${
            approved ? 'Bereits freigegeben' : `V${version} persönlich freigeben`
          }</button></div>`
          : ''
      }`
      : ''
  }`;
}

export function offers(v) {
  const p = v.room;
  if (!p.offers.length) return summary(v);
  const version = p.offers.length;
  return `<div class="room-grid"><section class="card content-card"><div class="panel-head"><h2>${
    ic('layers')
  }Angebote und Freigaben</h2>${
    p.modes[v.me.side] === 'human' && live(p)
      ? button('make-offer', 'Angebot erstellen', 'plus', 'btn secondary compact')
      : ''
  }</div>
    <div class="padded">${
    offerPanel(v, version, true)
  }</div></section><aside><section class="card"><div class="panel-head"><h2>${
    ic('clock')
  }Versionsverlauf</h2></div><div class="version-list">${
    [...p.offers].reverse().map((o) =>
      `<button data-cmd="offer-detail" data-version="${o.version}"><span class="version">V${o.version}</span><span><strong>${
        money(o.terms.price)
      }</strong><small>${h(p.companies[o.side])} · ${time(o.at)}</small></span>${ic('chevron', 15)}</button>`
    ).join('')
  }</div></section>${representation(v)}</aside></div>`;
}

export function mandateView(v) {
  const p = v.room, m = v.me.mandate, side = v.me.side;
  const edit = live(p)
    ? button('edit-mandate', m ? 'Mandat bearbeiten' : 'Mandat erteilen', 'edit', 'btn secondary compact')
    : '';
  return `<div class="room-grid"><section class="card content-card"><div class="panel-head"><h2>${
    ic('lock')
  }Mein privates Mandat</h2>${edit}</div><div class="padded">
    <div class="privacy-line">${ic('shield', 17)}Nur für ${
    h(p.companies[side])
  } und den eigenen Agenten sichtbar</div>
    ${
    m
      ? `<h3 class="subheading">Verhandlungsziel</h3><p>${
        h(m.goal)
      }</p><h3 class="subheading">Harte Grenzen</h3>
    ${
        side === 'A'
          ? `<div class="detail-list">${packageRows(v.schema, m.limits)}</div>`
          : m.options.map((o, i) =>
            `<details class="option-details" ${i === 0 ? 'open' : ''}><summary>Leistungspaket ${i + 1} · ab ${
              money(o.floor)
            }</summary><div class="detail-list">${
              packageRows(v.schema, { ...o.terms, price: o.target })
            }</div><p>Kosten ${money(o.cost)} · Preisuntergrenze ${money(o.floor)}</p></details>`
          ).join('')
      }
    <h3 class="subheading">Verhandelbare Präferenzen</h3><p>${
        m.priority === 'price' ? 'Preis zuerst' : 'Frühe Termine zuerst'
      } · ${strategies[m.strategy]}${side === 'A' ? ' · Zielpreis ' + money(m.preferred) : ''}</p>
    <h3 class="subheading">Alternative bei Nichteinigung</h3><p>${h(m.batna)} · ${money(m.batnaValue)}</p>
    <h3 class="subheading">Offenlegung</h3><p>${
        side === 'A'
          ? (m.shareTerms
            ? 'Mengen und Terminziele im Gespräch nennen.'
            : 'Mengen und Terminziele erst durch ein Angebot offenlegen.')
          : (m.shareTerms
            ? 'Ein abschließendes Paket ausdrücklich kennzeichnen.'
            : 'Nur die angebotenen Konditionen offenlegen.')
      }</p>
    ${
        v.me.agentNote
          ? `<h3 class="subheading">Arbeitsnotiz Ihres Agenten</h3><p>${h(v.me.agentNote)}</p>`
          : ''
      }
    <p class="muted note">Mandatsversion ${m.version}</p>`
      : '<p class="empty-copy">Sie verhandeln persönlich. Für die erste Übergabe können Sie hier ein privates Mandat hinterlegen.</p>'
  }</div></section><aside>${representation(v)}${summary(v)}</aside></div>`;
}
