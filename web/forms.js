import { button, h, ic, strategies } from './ui.js';

function field(name, label, input, wide = false) {
  return `<label class="field ${wide ? 'wide' : ''}" for="${name}"><span>${h(label)}</span>${input}</label>`;
}
function textField(name, label, value, max = 100, wide = false) {
  return field(
    name,
    label,
    `<input id="${name}" name="${name}" value="${h(value)}" maxlength="${max}" required>`,
    wide,
  );
}
function numberField(name, label, value, min, max, step = 1, optional = false) {
  return field(
    name,
    label,
    `<input type="number" inputmode="${
      step === 1 ? 'numeric' : 'decimal'
    }" id="${name}" name="${name}" value="${h(value ?? '')}" min="${min}" max="${max}" step="${step}" ${
      optional ? '' : 'required'
    }>`,
  );
}
function select(name, label, values, current) {
  return field(
    name,
    label,
    `<select id="${name}" name="${name}">${
      Object.entries(values).map(([v, l]) =>
        `<option value="${h(v)}" ${current === v ? 'selected' : ''}>${h(l)}</option>`
      ).join('')
    }</select>`,
  );
}
function euroField(name, label, v, min = 0) {
  return numberField(name, label + ' (€)', v / 100, min, 1000000, .01);
}
function termsFields(schema, terms, prefix, privateBuyer = false, skipPrice = false) {
  return schema.fields.filter((f) => !skipPrice || f.key !== 'price').map((f) => {
    const k = prefix + f.key;
    if (f.key === 'price') {
      return euroField(
        k,
        privateBuyer ? 'Maximales Gesamtbudget' : 'Gesamtpreis ' + schema.priceNote,
        terms[f.key],
        .01,
      );
    }
    const rule = privateBuyer ? ({ min: 'Mindestens ', max: 'Höchstens ', exact: '' }[f.rule]) : '';
    return numberField(
      k,
      rule + f.label + ' (' + f.unit + ')',
      terms[f.key],
      f.minimum,
      f.maximum,
      1,
      f.key === 'early_day',
    );
  }).join('');
}
export function optionFields(schema, o, i) {
  return `<fieldset class="seller-option" data-option="${i}"><legend>Leistungspaket</legend><button class="remove-option" type="button" data-cmd="remove-option" aria-label="Dieses Leistungspaket entfernen">${
    ic('close', 15)
  }</button><div class="form-grid">${termsFields(schema, o.terms, 'o' + i + '-', false, true)}
    ${euroField('cost' + i, 'Eigene Kosten', o.cost)}${
    euroField('floor' + i, 'Harte Preisuntergrenze', o.floor, .01)
  }${euroField('target' + i, 'Verhandelbarer Zielpreis', o.target, .01)}</div></fieldset>`;
}
export function mandateFields(schema, m, side, profile = null) {
  const a = side === 'A';
  return `<div class="privacy-line">${ic('lock', 15)} Dieses Mandat sieht nur Ihre Firma.</div>
    ${
    profile
      ? `<div class="form-section">${
        select('profile', 'Vertrauliches Verkäuferprofil', {
          flexibel: 'Flexible Kapazität',
          eng: 'Knappe Kapazität',
        }, profile)
      }</div>`
      : ''
  }
    <div class="form-section"><h3>Verhandlungsziel</h3>${
    textField('goal', 'Ziel des Mandats', m.goal, 400, true)
  }</div>
    <div class="form-section"><h3>${a ? 'Harte Grenzen' : 'Leistbare Pakete und Preisgrenzen'}</h3>
    ${
    a
      ? `<div class="form-grid">${termsFields(schema, m.limits, 'limit-', true)}</div>`
      : `<div id="seller-options">${m.options.map((o, i) => optionFields(schema, o, i)).join('')}</div>${
        button('add-option', 'Leistungspaket ergänzen', 'plus', 'text-btn')
      }`
  }</div>
    <div class="form-section"><h3>Verhandelbare Präferenzen</h3><div class="form-grid">
    ${select('strategy', 'Strategie', strategies, m.strategy)}
    ${select('priority', 'Priorität', { price: 'Preis zuerst', time: 'Frühe Termine zuerst' }, m.priority)}
    ${a ? euroField('preferred', 'Angestrebter Gesamtpreis', m.preferred, .01) : ''}
    ${euroField('step', 'Preisänderung je Konzession', m.step, .01)}</div></div>
    <div class="form-section"><h3>Alternative bei Nichteinigung</h3><div class="form-grid">
    ${textField('batna', 'Alternative', m.batna, 400, true)}${
    euroField(
      'batnaValue',
      a ? 'Kosten der Ersatzbeschaffung' : 'Deckungsbeitrag der Alternative',
      m.batnaValue,
    )
  }</div></div>
    <div class="form-section"><h3>Offenlegung</h3><label class="check-field"><input type="checkbox" name="shareTerms" ${
    m.shareTerms ? 'checked' : ''
  }><span>${
    a
      ? 'Mengen und Terminziele in der Anfrage offenlegen.'
      : 'Ein abschließendes Angebot als solches kennzeichnen.'
  }</span></label></div>`;
}
function readTerms(form, schema, prefix, skipPrice = false) {
  const t = {};
  for (const f of schema.fields) {
    if (skipPrice && f.key === 'price') continue;
    const el = form.elements.namedItem(prefix + f.key);
    t[f.key] = el.value === ''
      ? null
      : f.key === 'price'
      ? Math.round(el.valueAsNumber * 100)
      : el.valueAsNumber;
  }
  if (t.early_qty === 0) t.early_day = null;
  return t;
}
export function readMandate(form, schema, side) {
  const value = (n) => form.elements.namedItem(n).value;
  const cents = (n) => Math.round(form.elements.namedItem(n).valueAsNumber * 100);
  const m = {
    goal: value('goal'),
    batna: value('batna'),
    batnaValue: cents('batnaValue'),
    strategy: value('strategy'),
    priority: value('priority'),
    step: cents('step'),
    shareTerms: form.elements.shareTerms.checked,
  };
  if (side === 'A') {
    m.limits = readTerms(form, schema, 'limit-');
    m.preferred = cents('preferred');
  } else {
    m.options = [...form.querySelectorAll('[data-option]')].map((el) => {
      const i = el.dataset.option;
      return {
        terms: readTerms(form, schema, 'o' + i + '-', true),
        cost: cents('cost' + i),
        floor: cents('floor' + i),
        target: cents('target' + i),
      };
    });
  }
  return m;
}
export function setupFields(config) {
  return `<div class="form-grid">${
    select(
      'scenario',
      'Szenario',
      { boxes: 'Versandboxen', service: 'Wartungsdienstleistung' },
      config.scenario,
    )
  }
    ${select('mode', 'Ihre Vertretung beim Start', { agent: 'Mein Agent', human: 'Ich selbst' }, config.mode)}
    ${textField('subject', 'Verhandlungsgegenstand', config.subject, 100, true)}
    ${textField('firmA', 'Ihre Firma · Einkauf', config.companies.A, 60)}${
    textField('firmB', 'Eingeladene Firma', config.companies.B, 60)
  }
    ${numberField('minutes', 'Verhandlungsfrist (Minuten)', config.minutes, 1, 10080)}
    ${numberField('maxTurns', 'Maximale Verhandlungsschritte', config.maxTurns, 3, 100)}</div>`;
}
export function offerFields(schema, current) {
  return `<div class="form-grid">${termsFields(schema, current, 'term-')}</div>`;
}
export const readOffer = (form, schema) => readTerms(form, schema, 'term-');
