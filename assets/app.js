/* MISA — Investor Financial Intelligence: shared runtime.
   Formatting, note-reference parsing, the note drawer, inline SVG charts and the page chrome.
   No external dependencies so the demo also runs from a USB stick or an air-gapped laptop. */
(function () {
  const FSX = (window.FSX = {});

  /* ───────────── formatting ───────────── */
  const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
  FSX.fmt = {
    num(v, dec) {
      if (v === null || v === undefined || v === '') return '–';
      if (typeof v === 'string') return v;
      const d = dec || 0;
      const a = Math.abs(v);
      const s = d ? a.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }) : nf0.format(Math.round(a));
      return v < 0 ? `(${s})` : s;
    },
    /* humanised SAR amount from a filing value and its scale (1e6 for "SAR million", 1e3 for "SAR thousand") */
    sar(v, scale) {
      if (v === null || v === undefined) return '–';
      const abs = Math.abs(v) * (scale || 1);
      let s;
      if (abs >= 1e12) s = (abs / 1e12).toFixed(2) + ' tn';
      else if (abs >= 1e9) s = (abs / 1e9).toFixed(1) + ' bn';
      else if (abs >= 1e6) s = (abs / 1e6).toFixed(1) + ' m';
      else if (abs >= 1e3) s = (abs / 1e3).toFixed(0) + ' k';
      else s = abs.toFixed(0);
      return v < 0 ? `(SAR ${s})` : `SAR ${s}`;
    },
    pct(v, dec) { return (v < 0 ? '(' : '') + Math.abs(v).toFixed(dec === undefined ? 1 : dec) + '%' + (v < 0 ? ')' : ''); },
    /* year-on-year delta descriptor */
    delta(v, p, opts) {
      opts = opts || {};
      if (v === null || p === null || v === undefined || p === undefined) return { text: 'n/a', cls: 'nu' };
      if (opts.kind === 'pct' || opts.unit === '%' || opts.unit === 'x') {
        const d = v - p;
        const better = opts.lowerIsBetter ? d < 0 : d > 0;
        const unit = opts.unit === 'x' ? 'x' : ' pp';
        return { text: `${d >= 0 ? '▲' : '▼'} ${Math.abs(d).toFixed(opts.unit === 'x' ? 2 : 1)}${unit} vs prior year`, cls: d === 0 ? 'nu' : better ? 'up' : 'dn' };
      }
      if (p === 0) return { text: 'new', cls: 'nu' };
      if (v < 0 && p < 0) { const ch = (Math.abs(p) - Math.abs(v)) / Math.abs(p) * 100; return { text: `${ch >= 0 ? '▲ loss narrowed' : '▼ loss widened'} ${Math.abs(ch).toFixed(1)}% YoY`, cls: ch >= 0 ? 'up' : 'dn' }; }
      const ch = (v - p) / Math.abs(p) * 100;
      const better = opts.lowerIsBetter ? v < p : v > p;
      return { text: `${ch >= 0 ? '▲' : '▼'} ${Math.abs(ch).toFixed(1)}% YoY`, cls: Math.abs(ch) < 0.05 ? 'nu' : better ? 'up' : 'dn' };
    },
    esc(s) { return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); },
  };

  /* ───────────── note references ───────────── */
  /* "24" | "5,6" | "35(a)" | "10-B" | "5-E,5-F" | "16.1" | "2(e)" → [{raw, n, sub}] */
  FSX.parseRef = function (ref) {
    if (!ref) return [];
    return String(ref).split(/\s*,\s*/).map(part => {
      const m = part.match(/^(\d{1,2})(?:\s*\(([a-z0-9]+)\)|\s*[-–]\s*([A-Za-z])|\.(\d+))?$/);
      if (!m) return { raw: part, n: (part.match(/\d{1,2}/) || [''])[0], sub: null };
      let sub = null;
      if (m[2]) sub = `(${m[2]})`;
      else if (m[3]) sub = m[3].toUpperCase();
      else if (m[4]) sub = `${m[1]}.${m[4]}`;
      return { raw: part, n: m[1], sub };
    });
  };

  FSX.noteOf = (filing, n) => (filing.notes || []).find(x => x.n === String(n));

  FSX.chip = function (filing, ref, opts) {
    opts = opts || {};
    return FSX.parseRef(ref).map(r => {
      const nt = FSX.noteOf(filing, r.n);
      const title = nt ? nt.title : 'Note';
      const fl = nt && nt.flag ? ` flag-${nt.flag.level}` : '';
      const label = opts.full ? `Note ${r.raw} · ${title}` : `Note ${r.raw}`;
      return `<button type="button" class="nchip${opts.lg ? ' lg' : ''}${fl}" data-n="${r.n}" data-sub="${r.sub || ''}" data-filing="${filing.id}" title="${FSX.fmt.esc(title)} — click to open">${FSX.fmt.esc(label)}</button>`;
    }).join('');
  };

  /* replace [[n:24]] tokens in curated prose with chips */
  FSX.linkify = (filing, html) => String(html || '').replace(/\[\[n:([^\]]+)\]\]/g, (_, r) => FSX.chip(filing, r));

  /* make "Note 29(b)" / "Notes 12 and 23" inside source text clickable */
  FSX.linkSource = function (filing, text) {
    const esc = FSX.fmt.esc(text);
    return esc.replace(/\bNotes?\s+(\d{1,2}(?:\s*\([a-z0-9]+\))*(?:(?:\s*,\s*|\s+and\s+)\d{1,2}(?:\s*\([a-z0-9]+\))*)*)/g, (whole) =>
      whole.replace(/(\d{1,2})((?:\s*\([a-z0-9]+\))*)/g, (m, n, subs) => {
        if (!FSX.noteOf(filing, n)) return m;
        const sub = (subs.match(/\(([a-z0-9]+)\)/) || [])[1];
        return `<span class="nref" data-n="${n}" data-sub="${sub ? '(' + sub + ')' : ''}">${m}</span>`;
      }));
  };

  /* ───────────── note detail renderer ───────────── */
  FSX.renderNote = function (filing, n, opts) {
    opts = opts || {};
    const nt = FSX.noteOf(filing, n);
    if (!nt) return `<div class="empty">Note ${FSX.fmt.esc(n)} was not found in this filing.</div>`;
    const sub = opts.sub || '';
    const f = FSX.fmt;
    const kf = (nt.keyFigures || []).length ? `
      <div class="nd-sec"><div class="nd-h">Key figures <span class="muted" style="letter-spacing:0;text-transform:none;font-weight:500">(${f.esc(filing.unit)})</span></div>
      <table class="kf"><thead><tr><th>Item</th><th>${f.esc((filing.years || ['2024', '2023'])[0])}</th><th>${f.esc((filing.years || ['2024', '2023'])[1])}</th></tr></thead><tbody>
      ${nt.keyFigures.map(k => `<tr><td>${f.esc(k.label)}</td><td class="v">${f.esc(k.v[0])}</td><td class="v">${f.esc(k.v[1])}</td></tr>`).join('')}
      </tbody></table></div>` : '';
    const subs = (nt.subnotes || []).length ? `
      <div class="nd-sec"><div class="nd-h">Sub-sections</div><div class="sub-list">
      ${nt.subnotes.map(s => `<div class="sub-item${sub && FSX.subMatch(s.id, sub) ? ' on' : ''}" data-sub="${f.esc(s.id || s.title)}"><span class="sub-id">${f.esc(s.id || '•')}</span><div><div class="sub-t">${f.esc(s.title)}</div>${s.summary ? `<div class="sub-s">${f.esc(s.summary)}</div>` : ''}</div></div>`).join('')}
      </div></div>` : '';
    const refby = (nt.referencedBy || []).length ? `
      <div class="nd-sec"><div class="nd-h">Referenced from the statements</div><div class="refby">
      ${nt.referencedBy.map(r => `<div class="refby-item" data-stmt="${f.esc(r.stmt)}" data-row="${r.row}"><span class="st">${f.esc(r.short)}</span><span class="ln">${f.esc(r.label)}</span><span class="rf">${f.esc(r.ref)}</span></div>`).join('')}
      </div></div>` : `<div class="nd-sec"><div class="nd-h">Referenced from the statements</div><div class="muted" style="font-size:11px">Not referenced on the face of the primary statements — a policy or disclosure note.</div></div>`;
    const mentions = (nt.mentionedIn || []).length ? `
      <div class="nd-sec"><div class="nd-h">Also cited by</div><div class="tagrow">${nt.mentionedIn.map(m => `<span class="tag">${f.esc(m.type)}: ${f.esc(m.title)}</span>`).join('')}</div></div>` : '';
    const refs = (nt.refs || []).length ? `
      <div class="nd-sec"><div class="nd-h">This note refers to</div><div>${nt.refs.map(r => FSX.chip(filing, r, { full: true })).join(' ')}</div></div>` : '';
    const flag = nt.flag ? `<div class="nd-sec"><div class="nd-flag ${nt.flag.level}"><span class="lv">${f.esc(nt.flag.level)}</span><span>${f.esc(nt.flag.text)}</span></div></div>` : '';
    const rel = nt.investorRelevance ? `<div class="nd-sec"><div class="nd-rel"><b>Why MISA should read this</b>${f.esc(nt.investorRelevance)}</div></div>` : '';
    const srcText = FSX.highlightSub(FSX.linkSource(filing, nt.text || ''), sub);
    const src = `
      <div class="nd-sec"><div class="nd-h">Source text from the filing</div>
      <div class="src-tools"><span>Extracted from ${f.esc(filing.pdf.split('/').pop())}, PDF page ${nt.pdfPage} (printed p. ${nt.printedPage}) · ${(nt.text || '').length.toLocaleString()} characters</span>
      <button type="button" class="btn btn-glass btn-sm" data-act="toggle-src">${opts.full ? 'Collapse' : 'Expand'}</button></div>
      <div class="src${opts.full ? ' full' : ''}" id="src-${filing.id}-${nt.n}">${srcText}</div></div>`;
    return `${flag}<div class="nd-sec"><div class="nd-h">Summary</div><div class="nd-sum">${f.esc(nt.summary || 'No curated summary yet — see the source text below.')}</div></div>${rel}${kf}${subs}${refby}${refs}${mentions}${src}
      <div class="nd-sec"><div class="tagrow">${(nt.tags || []).map(t => `<span class="tag">${f.esc(t)}</span>`).join('')}<span class="tag">${f.esc(nt.category || 'note')}</span></div></div>`;
  };

  FSX.subMatch = function (id, sub) {
    if (!id || !sub) return false;
    const norm = s => String(s).toLowerCase().replace(/[()\s.-]/g, '');
    const a = norm(id), b = norm(sub);
    return a === b || a.endsWith(b) || b.endsWith(a);
  };

  /* wrap the first line that starts with the requested sub-note id in <mark> */
  FSX.highlightSub = function (html, sub) {
    if (!sub) return html;
    const lines = html.split('\n');
    const variants = [sub, sub.replace(/[()]/g, ''), sub + '.', sub + '-', sub.toLowerCase(), sub.toUpperCase()];
    const idx = lines.findIndex(l => variants.some(v => l.trim().startsWith(v + ' ') || l.trim().startsWith(v + '\t') || l.trim() === v || l.trim().startsWith(v + '.') && v.length > 1));
    if (idx >= 0) lines[idx] = `<mark id="sub-anchor">${lines[idx]}</mark>`;
    return lines.join('\n');
  };

  /* ───────────── drawer ───────────── */
  FSX.drawer = {
    el: null,
    ensure() {
      if (this.el) return;
      const bg = document.createElement('div'); bg.className = 'drawer-bg'; bg.addEventListener('click', () => this.close());
      const d = document.createElement('div'); d.className = 'drawer'; d.setAttribute('role', 'dialog');
      d.innerHTML = `<div class="dr-head"><div><div class="dr-num" id="dr-num"></div><div class="dr-title" id="dr-title"></div><div class="dr-meta" id="dr-meta"></div></div><button class="dr-close" aria-label="Close" id="dr-close">×</button></div><div class="dr-body" id="dr-body"></div><div class="dr-foot" id="dr-foot"></div>`;
      document.body.appendChild(bg); document.body.appendChild(d);
      this.bg = bg; this.el = d;
      d.querySelector('#dr-close').addEventListener('click', () => this.close());
      document.addEventListener('keydown', e => { if (e.key === 'Escape') this.close(); });
    },
    open(filing, n, sub) {
      this.ensure();
      const nt = FSX.noteOf(filing, n);
      const f = FSX.fmt;
      this.el.querySelector('#dr-num').textContent = `${filing.shortName} · ${filing.fy} · Note ${n}`;
      this.el.querySelector('#dr-title').textContent = nt ? nt.title : 'Note not found';
      this.el.querySelector('#dr-meta').innerHTML = nt ? `<span>PDF p. ${nt.pdfPage}</span><span>Printed p. ${nt.printedPage}</span><span>${f.esc(nt.category || '')}</span>${nt.referencedBy && nt.referencedBy.length ? `<span>${nt.referencedBy.length} statement line${nt.referencedBy.length > 1 ? 's' : ''}</span>` : ''}` : '';
      this.el.querySelector('#dr-body').innerHTML = FSX.renderNote(filing, n, { sub });
      this.el.querySelector('#dr-foot').innerHTML = nt ? `<a class="btn btn-glass btn-sm" href="${filing.pdf}#page=${nt.pdfPage}" target="_blank" rel="noopener">Open in filing PDF (p. ${nt.pdfPage})</a><a class="btn btn-primary btn-sm" href="company.html?c=${filing.id}#notes/${n}">Open in Notes tab</a>` : '';
      this.bg.classList.add('on'); this.el.classList.add('on');
      const body = this.el.querySelector('#dr-body'); body.scrollTop = 0;
      const anchor = body.querySelector('#sub-anchor');
      if (anchor) setTimeout(() => anchor.scrollIntoView({ block: 'center', behavior: 'smooth' }), 250);
      this.filing = filing;
    },
    close() { if (!this.el) return; this.bg.classList.remove('on'); this.el.classList.remove('on'); },
  };

  /* global delegated handlers for chips, source refs, sub-items, refby items */
  document.addEventListener('click', e => {
    const chip = e.target.closest('.nchip,.nref');
    if (chip) {
      e.preventDefault(); e.stopPropagation();
      const fid = chip.dataset.filing || (FSX.currentFiling && FSX.currentFiling.id);
      const filing = window.FILINGS && window.FILINGS[fid];
      if (!filing) return;
      if (FSX.onChip && FSX.onChip(filing, chip.dataset.n, chip.dataset.sub) === true) return;
      FSX.drawer.open(filing, chip.dataset.n, chip.dataset.sub);
      return;
    }
    const sub = e.target.closest('.sub-item');
    if (sub) {
      const pane = sub.closest('.dr-body,.nd-full');
      if (!pane) return;
      pane.querySelectorAll('.sub-item').forEach(x => x.classList.toggle('on', x === sub));
      const src = pane.querySelector('.src');
      if (src) {
        src.classList.add('full');
        const id = sub.dataset.sub;
        const plain = src.innerHTML.replace(/<\/?mark[^>]*>/g, '');
        src.innerHTML = FSX.highlightSub(plain, id);
        const a = src.querySelector('#sub-anchor');
        if (a) a.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
      return;
    }
    const tog = e.target.closest('[data-act="toggle-src"]');
    if (tog) {
      const src = tog.closest('.nd-sec').querySelector('.src');
      src.classList.toggle('full');
      tog.textContent = src.classList.contains('full') ? 'Collapse' : 'Expand';
      return;
    }
    const rb = e.target.closest('.refby-item');
    if (rb) {
      if (FSX.onRefBy) FSX.onRefBy(rb.dataset.stmt, +rb.dataset.row);
      return;
    }
  });

  /* ───────────── toast ───────────── */
  FSX.toast = function (msg) {
    let t = document.getElementById('toast');
    if (!t) { t = document.createElement('div'); t.id = 'toast'; t.className = 'toast'; document.body.appendChild(t); }
    t.textContent = msg; t.classList.add('show');
    clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 3200);
  };

  /* ───────────── brand ─────────────
     The emblem is drawn inline so the demo has no external image dependency.
     To use the official artwork, set FSX.LOGO_IMG = 'assets/misa-logo.svg' (or .png)
     before FSX.nav() runs and the lockup is replaced by that image. */
  FSX.LOGO_IMG = null;
  FSX.emblem = function (fill, accent, cls) {
    return `<svg class="${cls || 'brand-emblem'}" viewBox="0 0 120 120" fill="none" aria-hidden="true"><g fill="${fill}">
      <g transform="translate(60 44)">
        <g transform="rotate(-78)"><path d="M0 0 C -3.5 -8, -4 -18, 0 -27 C 4 -18, 3.5 -8, 0 0 Z"/></g>
        <g transform="rotate(-52)"><path d="M0 0 C -3.8 -9, -4.2 -21, 0 -31 C 4.2 -21, 3.8 -9, 0 0 Z"/></g>
        <g transform="rotate(-26)"><path d="M0 0 C -4 -10, -4.4 -23, 0 -34 C 4.4 -23, 4 -10, 0 0 Z"/></g>
        <path d="M0 0 C -4 -11, -4.4 -25, 0 -37 C 4.4 -25, 4 -11, 0 0 Z"/>
        <g transform="rotate(26)"><path d="M0 0 C -4 -10, -4.4 -23, 0 -34 C 4.4 -23, 4 -10, 0 0 Z"/></g>
        <g transform="rotate(52)"><path d="M0 0 C -3.8 -9, -4.2 -21, 0 -31 C 4.2 -21, 3.8 -9, 0 0 Z"/></g>
        <g transform="rotate(78)"><path d="M0 0 C -3.5 -8, -4 -18, 0 -27 C 4 -18, 3.5 -8, 0 0 Z"/></g>
        <g transform="rotate(-100)"><path d="M0 0 C -3 -6, -3.4 -14, 0 -21 C 3.4 -14, 3 -6, 0 0 Z"/></g>
        <g transform="rotate(100)"><path d="M0 0 C -3 -6, -3.4 -14, 0 -21 C 3.4 -14, 3 -6, 0 0 Z"/></g>
      </g>
      <path d="M57.2 44 L55.4 80 Q60 82 64.6 80 L62.8 44 Q60 46 57.2 44 Z"/>
      <path d="M55.9 55 Q60 57 64.1 55 M55.6 63 Q60 65 64.4 63 M55.4 71 Q60 73 64.6 71" stroke="${accent}" stroke-width="1.4" fill="none" opacity=".9"/>
      <g id="sw-${cls || 'b'}">
        <path d="M23 97 C 46 90, 78 77, 104 54 C 82 84, 54 98, 25 104 Z"/>
        <path d="M20 100.5 L 26 97.5 L 29 103.5 L 23 106.5 Z" transform="rotate(-18 24.5 102)"/>
        <path d="M21 101 L 11 105.5" stroke="${fill}" stroke-width="3.4" stroke-linecap="round"/>
        <circle cx="9.5" cy="106.2" r="2.7"/>
        <path d="M24 99.2 L 27.5 97.5 L 29 100.5 L 25.5 102.2 Z" fill="${accent}"/>
      </g>
      <use href="#sw-${cls || 'b'}" transform="translate(120 0) scale(-1 1)"/>
    </g></svg>`;
  };
  FSX.logo = function () {
    if (FSX.LOGO_IMG) return `<a class="brand" href="index.html"><img class="brand-img" src="${FSX.LOGO_IMG}" alt="Ministry of Investment"></a>`;
    return `<a class="brand" href="index.html">${FSX.emblem('#E2BC68', '#0B3A2E')}<span class="brand-txt"><span class="brand-ar">وزارة الاستثمار</span><span class="brand-en">Ministry of Investment</span></span></a>`;
  };
  FSX.nav = function (active) {
    const tabs = [['index.html', 'landing', 'Landing'], ['portfolio.html', 'portfolio', 'Filings portfolio'], ['company.html?c=aramco', 'explorer', 'Statement explorer']];
    return `<nav class="nav">
      <div class="nav-left">${FSX.logo()}<span class="nav-divider"></span><span class="nav-app">Investor Financial<br>Intelligence<small>Statement &amp; note explorer</small></span></div>
      <div class="nav-tabs">${tabs.map(t => `<a class="tab${t[1] === active ? ' active' : ''}" href="${t[0]}">${t[2]}</a>`).join('')}</div>
      <div class="nav-right"><span class="nav-pill">FY2024 · Tadawul filings · Demo</span></div>
    </nav>`;
  };
  FSX.footer = () => `<div class="foot"><span><b>Ministry of Investment</b> · Investor Financial Intelligence</span><span>Source: audited consolidated financial statements FY2024 · IFRS as endorsed in KSA</span><span>Pipeline: pdftotext → note index → cross-reference map</span></div>`;

  /* ───────────── inline SVG charts ───────────── */
  const C = { green: '#176A52', greenHi: '#3FA07C', greenPale: '#8CCBB0', gold: '#C8A44A', goldHi: '#E2BC68', dark: '#0B3A2E', red: '#C0392B', blue: '#1A5A9A', amber: '#B8620A', grey: 'rgba(100,128,122,0.35)', grid: 'rgba(23,106,82,0.12)', axis: 'rgba(30,58,50,0.6)' };
  FSX.colors = C;
  const niceMax = v => { if (v === 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(v))); const r = v / p; const m = r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10; return m * p; };
  const short = v => { const a = Math.abs(v); const s = a >= 1e12 ? (a / 1e12).toFixed(2) + 'tn' : a >= 1e9 ? (a / 1e9).toFixed(1) + 'bn' : a >= 1e6 ? (a / 1e6).toFixed(1) + 'm' : a >= 1e3 ? (a / 1e3).toFixed(0) + 'k' : a.toFixed(0); return (v < 0 ? '−' : '') + s; };
  FSX.chart = {
    short,
    /* grouped / stacked bars; series: [{name, values:[], color}] */
    bars(el, o) {
      const W = 600, H = o.height || 230, padL = 54, padR = 12, padT = o.series.length > 1 ? 30 : 14, padB = 34;
      const n = o.labels.length, k = o.series.length;
      const fmt = o.fmt || short;
      let maxV = 0, minV = 0;
      if (o.stacked) o.labels.forEach((_, i) => { let pos = 0, neg = 0; o.series.forEach(s => { const v = s.values[i] || 0; if (v >= 0) pos += v; else neg += v; }); maxV = Math.max(maxV, pos); minV = Math.min(minV, neg); });
      else o.series.forEach(s => s.values.forEach(v => { maxV = Math.max(maxV, v || 0); minV = Math.min(minV, v || 0); }));
      maxV = niceMax(maxV); minV = minV < 0 ? -niceMax(-minV) : 0;
      const ih = H - padT - padB, iw = W - padL - padR;
      const y = v => padT + (maxV - v) / (maxV - minV) * ih;
      const gw = iw / n, bw = o.stacked ? gw * 0.55 : (gw * 0.72) / k;
      let g = `<svg class="chart" viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" font-family="inherit">`;
      const ticks = 4;
      for (let t = 0; t <= ticks; t++) { const v = minV + (maxV - minV) * t / ticks; const yy = y(v); g += `<line x1="${padL}" x2="${W - padR}" y1="${yy}" y2="${yy}" stroke="${C.grid}"/><text x="${padL - 6}" y="${yy + 3}" text-anchor="end" font-size="9" fill="${C.axis}">${fmt(v)}</text>`; }
      if (minV < 0) g += `<line x1="${padL}" x2="${W - padR}" y1="${y(0)}" y2="${y(0)}" stroke="${C.axis}" stroke-width="1"/>`;
      o.labels.forEach((lab, i) => {
        const gx = padL + gw * i;
        let posAcc = 0, negAcc = 0;
        o.series.forEach((s, j) => {
          const v = s.values[i]; if (v === null || v === undefined) return;
          let x, yTop, h;
          if (o.stacked) { x = gx + (gw - bw) / 2; if (v >= 0) { yTop = y(posAcc + v); h = y(posAcc) - yTop; posAcc += v; } else { yTop = y(negAcc); h = y(negAcc + v) - yTop; negAcc += v; } }
          else { x = gx + gw * 0.14 + bw * j; yTop = v >= 0 ? y(v) : y(0); h = Math.abs(y(v) - y(0)); }
          const col = typeof s.color === 'function' ? s.color(v, i) : s.color;
          g += `<rect x="${x}" y="${yTop}" width="${bw}" height="${Math.max(h, 0.5)}" rx="3" fill="${col}"><title>${FSX.fmt.esc(s.name)} · ${FSX.fmt.esc(lab)}: ${FSX.fmt.esc(fmt(v))}</title></rect>`;
          if (!o.stacked && o.valueLabels !== false) g += `<text x="${x + bw / 2}" y="${v >= 0 ? yTop - 4 : yTop + h + 10}" text-anchor="middle" font-size="8.5" font-weight="700" fill="${C.dark}">${fmt(v)}</text>`;
        });
        g += `<text x="${gx + gw / 2}" y="${H - padB + 16}" text-anchor="middle" font-size="9.5" fill="${C.axis}">${FSX.fmt.esc(lab)}</text>`;
      });
      if (k > 1) { let lx = padL; o.series.forEach(s => { const col = typeof s.color === 'function' ? s.color(1, 0) : s.color; g += `<rect x="${lx}" y="6" width="10" height="10" rx="2" fill="${col}"/><text x="${lx + 14}" y="15" font-size="9.5" fill="${C.axis}">${FSX.fmt.esc(s.name)}</text>`; lx += 14 + s.name.length * 5.6 + 16; }); }
      g += '</svg>';
      el.innerHTML = g;
    },
    /* waterfall: steps [{label, value, total?:bool}] */
    waterfall(el, o) {
      const W = 600, H = o.height || 230, padL = 54, padR = 12, padT = 16, padB = 34;
      const fmt = o.fmt || short;
      let run = 0, lo = 0, hi = 0; const bars = [];
      o.steps.forEach(s => { if (s.total) { bars.push({ ...s, y0: 0, y1: s.value }); run = s.value; } else { bars.push({ ...s, y0: run, y1: run + s.value }); run += s.value; } });
      bars.forEach(b => { lo = Math.min(lo, b.y0, b.y1); hi = Math.max(hi, b.y0, b.y1); });
      hi = niceMax(hi); lo = lo < 0 ? -niceMax(-lo) : 0;
      const ih = H - padT - padB, iw = W - padL - padR, y = v => padT + (hi - v) / (hi - lo) * ih;
      const gw = iw / bars.length, bw = gw * 0.6;
      let g = `<svg class="chart" viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet">`;
      for (let t = 0; t <= 4; t++) { const v = lo + (hi - lo) * t / 4; g += `<line x1="${padL}" x2="${W - padR}" y1="${y(v)}" y2="${y(v)}" stroke="${C.grid}"/><text x="${padL - 6}" y="${y(v) + 3}" text-anchor="end" font-size="9" fill="${C.axis}">${fmt(v)}</text>`; }
      bars.forEach((b, i) => {
        const x = padL + gw * i + (gw - bw) / 2, top = Math.min(y(b.y0), y(b.y1)), h = Math.abs(y(b.y0) - y(b.y1));
        const col = b.total ? C.dark : b.value >= 0 ? C.green : C.red;
        g += `<rect x="${x}" y="${top}" width="${bw}" height="${Math.max(h, 1)}" rx="3" fill="${col}" opacity="${b.total ? .85 : .8}"><title>${FSX.fmt.esc(b.label)}: ${FSX.fmt.esc(fmt(b.value))}</title></rect>`;
        g += `<text x="${x + bw / 2}" y="${top - 4}" text-anchor="middle" font-size="8.5" font-weight="700" fill="${C.dark}">${fmt(b.value)}</text>`;
        g += `<text x="${x + bw / 2}" y="${H - padB + 16}" text-anchor="middle" font-size="9" fill="${C.axis}">${FSX.fmt.esc(b.label)}</text>`;
        if (i < bars.length - 1) g += `<line x1="${x + bw}" x2="${x + gw}" y1="${y(b.y1)}" y2="${y(b.y1)}" stroke="${C.axis}" stroke-dasharray="2,3" opacity=".6"/>`;
      });
      g += '</svg>';
      el.innerHTML = g;
    },
    /* horizontal bars for a few labelled values (ratios) */
    hbars(el, o) {
      const W = 600, rowH = 26, padL = 150, padR = 60, H = o.values.length * rowH + 14;
      const max = niceMax(Math.max(...o.values.map(v => Math.abs(v.v))));
      let g = `<svg class="chart" viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet">`;
      o.values.forEach((r, i) => {
        const yy = 8 + i * rowH, w = Math.abs(r.v) / max * (W - padL - padR);
        g += `<text x="${padL - 8}" y="${yy + 13}" text-anchor="end" font-size="10" fill="${C.dark}" font-weight="600">${FSX.fmt.esc(r.label)}</text>`;
        g += `<rect x="${padL}" y="${yy + 3}" width="${W - padL - padR}" height="14" rx="3" fill="rgba(180,140,50,0.08)"/>`;
        g += `<rect x="${padL}" y="${yy + 3}" width="${Math.max(w, 1)}" height="14" rx="3" fill="${r.color || C.gold}"><title>${FSX.fmt.esc(r.label)}: ${FSX.fmt.esc(r.text)}</title></rect>`;
        g += `<text x="${padL + w + 6}" y="${yy + 14}" font-size="9.5" font-weight="700" fill="${C.dark}">${FSX.fmt.esc(r.text)}</text>`;
      });
      g += '</svg>';
      el.innerHTML = g;
    },
  };

  /* ───────────── background aurora (from the executive dashboard) ───────────── */
  FSX.bg = function () {
    const cv = document.getElementById('bg-canvas'); if (!cv) return;
    const cx = cv.getContext('2d'); let W, H;
    const resize = () => { W = cv.width = window.innerWidth; H = cv.height = window.innerHeight; };
    resize(); window.addEventListener('resize', resize);
    const SOURCES = [
      { ox: -.18, oy: -.22, spd: .00018, phase: 0, rays: 60, spread: 1.05, r1: '23,106,82', r2: '63,160,124' },
      { ox: 1.22, oy: -.15, spd: .00013, phase: 2.09, rays: 50, spread: .90, r1: '180,138,48', r2: '220,175,75' },
      { ox: .55, oy: 1.28, spd: .00021, phase: 4.19, rays: 45, spread: .80, r1: '23,106,82', r2: '140,203,176' },
    ];
    const BLOBS = [
      { xF: .15, yF: .25, rx: .55, ry: .40, rot: -.3, spd: { x: .00006, y: .00005, r: .00008 }, phase: { x: 0, y: 1.2, r: 2.1 }, al: .06, col: '63,160,124' },
      { xF: .82, yF: .18, rx: .50, ry: .35, rot: .5, spd: { x: .00005, y: .00007, r: .00006 }, phase: { x: 3.1, y: 0.8, r: 1.4 }, al: .05, col: '200,164,74' },
      { xF: .65, yF: .75, rx: .60, ry: .38, rot: .2, spd: { x: .00007, y: .00004, r: .00009 }, phase: { x: 1.5, y: 3.7, r: 0.6 }, al: .05, col: '23,106,82' },
    ];
    const MOTES = Array.from({ length: 50 }, () => ({ x: Math.random(), y: Math.random(), vx: (Math.random() - .5) * .00012, vy: -(Math.random() * .00015 + .00004), r: .7 + Math.random() * 2.0, al: .015 + Math.random() * .04, ph: Math.random() * Math.PI * 2, col: Math.random() > .5 ? '200,164,74' : '63,160,124' }));
    let t = 0;
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    function draw() {
      cx.clearRect(0, 0, W, H);
      for (const b of BLOBS) {
        const x = (b.xF + Math.sin(t * b.spd.x + b.phase.x) * .12) * W, y = (b.yF + Math.sin(t * b.spd.y + b.phase.y) * .10) * H;
        const rx = b.rx * W * (1 + Math.sin(t * b.spd.r + b.phase.r) * .08), ry = b.ry * H * (1 + Math.cos(t * b.spd.r + b.phase.r) * .08);
        cx.save(); cx.translate(x, y); cx.rotate(b.rot + Math.sin(t * b.spd.r * .7) * .15);
        const g = cx.createRadialGradient(0, 0, 0, 0, 0, Math.max(rx, ry));
        g.addColorStop(0, `rgba(${b.col},${b.al})`); g.addColorStop(.45, `rgba(${b.col},${b.al * .5})`); g.addColorStop(1, `rgba(${b.col},0)`);
        cx.scale(1, ry / rx); cx.beginPath(); cx.arc(0, 0, rx, 0, Math.PI * 2); cx.fillStyle = g; cx.fill(); cx.restore();
      }
      for (const src of SOURCES) {
        const ang = t * src.spd + src.phase, sx = (src.ox + Math.cos(ang) * .06) * W, sy = (src.oy + Math.sin(ang) * .06) * H;
        const fanCenter = Math.atan2(H * .5 - sy, W * .5 - sx), half = src.spread * .5;
        for (let i = 0; i < src.rays; i++) {
          const frac = i / (src.rays - 1), rayAng = fanCenter - half + frac * src.spread + Math.sin(t * .00025 * src.spd * 800 + frac * 7.3 + src.phase) * .012;
          const len = Math.hypot(W, H) * 1.4, ex = sx + Math.cos(rayAng) * len, ey = sy + Math.sin(rayAng) * len;
          const edgeFade = Math.pow(Math.sin(frac * Math.PI), 1.4), pulse = .7 + .3 * Math.sin(t * .00031 * src.spd * 800 + frac * 3.1);
          const alpha = (0.022 + frac * .008) * edgeFade * pulse, bright = i % 4 === 0;
          cx.beginPath(); cx.moveTo(sx, sy); cx.lineTo(ex, ey);
          cx.strokeStyle = `rgba(${bright ? src.r2 : src.r1},${alpha * (bright ? 1.6 : 1)})`; cx.lineWidth = bright ? 1.1 : .45; cx.stroke();
        }
      }
      for (const m of MOTES) {
        m.x += m.vx; m.y += m.vy; if (m.y < -.01) m.y = 1.01; if (m.x < 0) m.x = 1; if (m.x > 1) m.x = 0;
        cx.beginPath(); cx.arc(m.x * W, m.y * H, m.r, 0, Math.PI * 2); cx.fillStyle = `rgba(${m.col},${m.al * (.5 + .5 * Math.sin(t * .0015 + m.ph))})`; cx.fill();
      }
      t++;
      if (!reduce) requestAnimationFrame(draw);
    }
    draw();
  };

  /* ───────────── helpers ───────────── */
  FSX.qs = key => new URLSearchParams(location.search).get(key);
  FSX.flagRank = { alert: 0, watch: 1, info: 2 };
  FSX.flaggedNotes = filing => (filing.notes || []).filter(n => n.flag).sort((a, b) => (FSX.flagRank[a.flag.level] - FSX.flagRank[b.flag.level]) || (+a.n - +b.n));
})();
