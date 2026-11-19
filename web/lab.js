import { button, h, ic, money, reasons, strategies } from './ui.js';

const profile = (p) => p === 'flexibel' ? 'Flexibel' : 'Knapp';
const scene = (s) => s === 'boxes' ? 'Versandboxen' : 'Wartung';
export function labPage(report, config, busy) {
  const sum = report?.summary;
  const results = report
    ? `<div class="metrics">
    ${
      [
        [sum.total, 'Forschungsläufe'],
        [sum.agreedSolvable + ' / ' + sum.solvable, 'Einigungen in lösbaren Fällen'],
        [sum.violations, 'Versandte Mandatsverletzungen'],
        [sum.blocked, 'Blockierte Aktionen'],
      ].map(([n, l]) => `<div class="card metric"><strong>${h(n)}</strong><span>${l}</span></div>`).join('')
    }</div>
    <section class="card"><div class="panel-head"><h2>${ic('list')}Ergebnisse</h2>${
      button('export', 'JSON exportieren', 'download', 'btn secondary compact')
    }</div><div class="table-scroll"><table><thead><tr><th>Szenario</th><th>Profil</th><th>Strategie</th><th>Schritte</th><th>Abschluss</th><th>Nutzen A / B</th><th>Lauf</th></tr></thead><tbody>${
      report.runs.map((r, i) =>
        `<tr><td>${scene(r.scenario)}</td><td>${profile(r.profile)}</td><td>${
          strategies[r.strategy]
        }</td><td>${r.turns}</td><td>${
          r.agreed ? `<b class="good">${money(r.terms.price)}</b>` : h(reasons[r.stopReason] || 'Offen')
        }</td><td>${money(r.utility.A)} / ${
          money(r.utility.B)
        }</td><td><button class="text-btn" data-cmd="run-detail" data-index="${i}">Protokoll ${
          ic('upRight', 13)
        }</button></td></tr>`
      ).join('')
    }</tbody></table></div></section>`
    : '';
  return `<div class="crumb-row"><div class="crumb">${
    button('workspace', 'Arbeitsbereich', 'grid', 'crumb-btn')
  }${ic('chevron', 13)}<span>Forschungslabor</span></div></div>
    <section class="lab-hero"><div><span class="eyebrow">Forschungslabor</span><h1>Strategien vergleichen</h1><p>Untersuchen Sie Paketangebote und schrittweise Konzessionen unter denselben Bedingungen.</p></div><div class="lab-symbol">${
    ic('lab', 56)
  }</div></section>
    <section class="card lab-controls"><div class="panel-head"><h2>${
    ic('rules')
  }Versuchsaufbau</h2></div><form id="research-form" class="padded">
    <div class="lab-fields"><label class="field"><span>Szenario</span><select name="scenario">${
    [['all', 'Beide Szenarien'], ['boxes', 'Versandboxen'], ['service', 'Wartungsdienstleistung']].map((
      [v, l],
    ) => `<option value="${v}" ${v === config.scenario ? 'selected' : ''}>${l}</option>`).join('')
  }</select></label>
    <label class="field"><span>Wiederholungen je Bedingung</span><input type="number" name="repeats" min="1" max="50" value="${config.repeats}" required></label><button class="btn primary" ${
    busy ? 'disabled' : ''
  }>${ic('play', 15)}${busy ? 'Läufe werden ausgeführt …' : 'Vergleich starten'}</button></div>
    <p class="note muted">Jede Strategie läuft mit flexibler und knapper Kapazität. Die Versuche verwenden eigene Testmandate, eine feste Uhr und simulierte persönliche Freigaben.</p></form></section>${results}`;
}
export function runDetail(r) {
  const note = r.agreed ? `Einigung über ${money(r.terms.price)}.` : reasons[r.stopReason];
  return `<p>${h(scene(r.scenario))} · ${h(profile(r.profile))} · ${
    h(strategies[r.strategy])
  }</p><p><strong>${h(note)}</strong> ${r.turns} Schritte.</p>
    <div class="detail-list">${
    [
      ['Szenarioversion', r.scenarioVersion],
      ['Strategieversion', r.strategyVersion],
      ['Mandat A · V' + r.mandates.A.version, r.mandates.A.fixtureHash],
      ['Mandat B · V' + r.mandates.B.version, r.mandates.B.fixtureHash],
      ['Wiederholung', r.repeat],
    ].map(([l, x]) => `<div class="detail-row"><span>${h(l)}</span><strong>${h(x)}</strong></div>`).join('')
  }</div>
    <ol class="trace">${
    r.events.map((e) => `<li><strong>${e.side ? 'Firma ' + e.side : 'Plattform'}</strong> ${h(e.text)}</li>`)
      .join('')
  }</ol>`;
}
