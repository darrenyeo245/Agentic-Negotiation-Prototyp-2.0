const paths = {
  grid:
    '<rect x="3" y="3" width="7" height="7" rx="1.3"/><rect x="14" y="3" width="7" height="7" rx="1.3"/><rect x="3" y="14" width="7" height="7" rx="1.3"/><rect x="14" y="14" width="7" height="7" rx="1.3"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 1 1 8 0v3m-4 5v2"/>',
  shield:
    '<path d="m12 3 8 3v6c0 4.7-3.4 7.4-8 9.3C7.4 19.4 4 16.7 4 12V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
  chevron: '<path d="m9 18 6-6-6-6"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  close: '<path d="m6 6 12 12m0-12L6 18"/>',
  invite:
    '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20v-2c0-3.5 3-5.8 6.5-5.8s6.5 2.3 6.5 5.8v2m3-12v6m-3-3h6"/>',
  people:
    '<circle cx="9" cy="8" r="3.5"/><path d="M2 20v-1c0-3.8 3-6 7-6s7 2.2 7 6v1m0-15a3.2 3.2 0 0 1 0 6m2 3c2.7.6 4 2.3 4 5"/>',
  person: '<circle cx="12" cy="8" r="3.5"/><path d="M4.5 20v-1c0-3.9 3.4-6 7.5-6s7.5 2.1 7.5 6v1"/>',
  bot:
    '<rect x="3" y="7" width="18" height="13" rx="3"/><path d="M12 7V4m-5 8v1m5 3h3m2-4v1M1 12v3m22-3v3"/><circle cx="12" cy="3" r="1"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/>',
  chat:
    '<path d="M20.5 11.5c0 4.7-3.8 7.5-8.7 7.5-1.3 0-2.6-.2-3.6-.6L3 20l1.5-4.3a7.1 7.1 0 0 1-1.4-4.2C3.1 7 7 4 12 4s8.5 3 8.5 7.5z"/><path d="M7.5 10h9m-9 3.3h6"/>',
  doc:
    '<path d="M6 3h8l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm8 0v5h4M8.5 12h6.5m-6.5 4h6.5"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5zm-9 9 9 5 9-5m-18 5 9 5 9-5"/>',
  box: '<path d="m12 2 9 5v10l-9 5-9-5V7zm-9 5 9 5 9-5m-9 5v10M7.5 4.5l9 5"/>',
  truck:
    '<path d="M2 5h12v12H2zm12 4h4l4 4v4h-8"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
  split: '<path d="M5 5h4c4.5 0 3.5 5 7 5h4m-3-3 3 3-3 3M5 19h4c3.5 0 3.5-5 6-6"/>',
  building: '<path d="M3 21h18M5 21V5l10-2v18m0-13 4 1v12M8 8h1m2-1h1m-4 5h1m2-1h1m-4 5h1m2-1h1"/>',
  exchange: '<path d="M3 8h16l-4-4m6 12H5l4 4"/>',
  arrow: '<path d="M4 12h15m-6-6 6 6-6 6"/>',
  upRight: '<path d="M5 19 19 5M8 5h11v11"/>',
  send: '<path d="m3 11 18-8-7 18-3-7zM11 14 21 3"/>',
  check: '<path d="m4 12 5 5L20 6"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  key: '<circle cx="8" cy="15" r="5"/><path d="m11.7 11.3 8-8m-4 4 3 3m-1-5 3 3"/>',
  copy:
    '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4 2c-1 .7-1.5 1.2-1.5 2.5m0 3h.01"/>',
  list:
    '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r=".6"/><circle cx="4" cy="12" r=".6"/><circle cx="4" cy="18" r=".6"/>',
  edit: '<path d="m4 16 12-12a2 2 0 0 1 3 3L7 19l-4 1zm10-10 4 4"/>',
  flag: '<path d="M5 21V4c5-4 9 3 14 0v10c-5 3-9-4-14 0"/>',
  folder: '<path d="M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
  link: '<path d="m9 15 6-6m-6-2 2-2a5 5 0 0 1 7 7l-2 2m-1 3-2 2a5 5 0 0 1-7-7l2-2"/>',
  rules:
    '<path d="M4 6h8m4 0h4M4 18h4m4 0h8M4 12h3m4 0h9"/><circle cx="14" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
  spark: '<path d="m12 2 2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4z"/>',
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
};
export const ic = (key, size = 18) =>
  `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${
    paths[key] || ''
  }</svg>`;
export const h = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]),
  );
export const money = (cents) =>
  new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(cents / 100);
export const number = (n) => new Intl.NumberFormat('de-DE').format(n);
export const time = (stamp) =>
  new Date(stamp * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
export const fullDate = (stamp) =>
  new Date(stamp * 1000).toLocaleDateString('de-DE', { day: '2-digit', month: 'short', year: 'numeric' });
export const initials = (s) =>
  s.trim().split(/\s+/).slice(0, 2).map((x) => Array.from(x)[0]).join('').toUpperCase();
export const states = {
  active: 'In Verhandlung',
  review: 'Zur Freigabe',
  agreed: 'Abgeschlossen',
  ended: 'Beendet',
};
export const strategies = { direkt: 'Direktes Paket', stufen: 'Schrittweise Konzession' };
export const live = (r) => ['active', 'review'].includes(r.status);
export const amount = (f, v) =>
  v == null ? 'Entfällt' : f.key === 'price' ? money(v) : `${number(v)} ${f.unit}`;
export const tag = (status) => `<span class="status status-${status}"><i></i>${states[status]}</span>`;
export const button = (cmd, label, icon = '', style = 'btn', extra = '') =>
  `<button type="button" class="${style}" data-cmd="${cmd}" ${extra}>${
    icon ? ic(icon, 16) : ''
  }${label}</button>`;
export const avatar = (name, side, small = false) =>
  `<span aria-hidden="true" class="avatar side-${side} ${small ? 'small' : ''}">${h(initials(name))}</span>`;
export const brand = `<span class="brand-mark" aria-hidden="true"></span><span>Paktwerk</span>`;
export const statusName = (mode) => mode === 'agent' ? 'Agent' : 'Mensch';
export function packageRows(schema, terms, previous = null) {
  return schema.fields.map((f) => {
    const changed = previous && previous[f.key] !== terms[f.key];
    return `<div class="detail-row ${changed ? 'changed' : ''}"><span>${h(f.label)}</span><strong>${
      changed ? `<s>${h(amount(f, previous[f.key]))}</s>` : ''
    }${h(amount(f, terms[f.key]))}</strong></div>`;
  }).join('');
}
export function reviewNote(me) {
  const a = me.assessment;
  if (!a) return '';
  return `<section class="private-note ${a.valid ? '' : 'caution'}"><h3>${
    ic('lock', 15)
  } Ihre private Bewertung</h3>${a.reasons.map((x) => `<p>${h(x)}</p>`).join('')}</section>`;
}
export function approvals(p) {
  const version = p.offers.length;
  return ['A', 'B'].map((s) =>
    `<div class="approval-person">${avatar(p.companies[s], s, true)}<span>${
      h(p.companies[s])
    }</span><b class="${p.approvals[s] === version ? 'good' : ''}">${
      p.approvals[s] === version ? ic('checkCircle', 14) + ' Freigegeben' : 'Ausstehend'
    }</b></div>`
  ).join('');
}
