(() => {
  'use strict';
  const VERSION = '0.17.3';
  const KEY = '__OMEGA_PM_NFL_TA_PROBE_0173__';
  const SCHEMA = 'OMEGA_PM_NFL_TA_PROBE_0.17.3';
  const DOWNLOAD_PREFIX = 'OMEGA_0173_PROPSMADNESS_NFL_TA_CAPTURE';
  if (window[KEY]?.active) {
    console.log('OMEGA PropsMadness NFL T+A probe already active.');
    return;
  }

  const state = {
    schemaVersion: SCHEMA,
    version: VERSION,
    active: true,
    startedAt: new Date().toISOString(),
    pageUrl: location.href,
    pageTitle: document.title,
    events: [],
    notes: [],
  };

  const MAX_BODY_CHARS = 8_000_000;
  const clean = x => String(x ?? '').replace(/\s+/g, ' ').trim();
  const isRelevantUrl = u => {
    try {
      const x = new URL(u, location.href);
      if (x.origin !== location.origin) return false;
      const p = x.pathname.toLowerCase();
      return p.includes('/api/offer/') || p.includes('/api/match') || p.includes('/api/fixture');
    } catch { return false; }
  };
  const relevance = (url, text) => {
    const s = `${url}\n${text.slice(0, 250000)}`.toLowerCase();
    const terms = ['tckl+ast','tackle+assist','tackles+assists','tackles + assists','tackle assists','player-tackles','player-assists','nfl'];
    return terms.filter(t => s.includes(t));
  };
  const summarize = data => {
    if (Array.isArray(data)) return { type: 'array', length: data.length };
    if (data && typeof data === 'object') return { type: 'object', keys: Object.keys(data).slice(0, 80) };
    return { type: typeof data };
  };
  const safeJson = text => { try { return JSON.parse(text); } catch { return null; } };
  const pushResponse = ({transport,url,status,contentType,text}) => {
    if (!isRelevantUrl(url)) return;
    const clipped = text.length > MAX_BODY_CHARS ? text.slice(0, MAX_BODY_CHARS) : text;
    const data = safeJson(clipped);
    const hits = relevance(url, clipped);
    const lower = String(url).toLowerCase();
    const full = lower.includes('/api/offer/nfl') || hits.some(x => x !== 'nfl');
    state.events.push({
      capturedAt: new Date().toISOString(), transport, url: String(url), status,
      contentType: contentType || null, relevanceTerms: hits,
      responseSummary: summarize(data),
      responseData: full ? data : null,
      responseTextFallback: full && data == null ? clipped : null,
      truncated: text.length > MAX_BODY_CHARS,
    });
  };

  const origFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const resp = await origFetch(...args);
    try {
      const url = resp.url || String(args[0]?.url || args[0] || '');
      if (isRelevantUrl(url)) {
        const clone = resp.clone();
        const text = await clone.text();
        pushResponse({transport:'fetch',url,status:resp.status,contentType:resp.headers.get('content-type'),text});
      }
    } catch (e) { state.notes.push(`fetch capture error: ${String(e)}`); }
    return resp;
  };

  const XHR = window.XMLHttpRequest;
  const origOpen = XHR.prototype.open, origSend = XHR.prototype.send;
  XHR.prototype.open = function(method,url,...rest) {
    this.__omega0173 = {method,url:String(url)};
    return origOpen.call(this,method,url,...rest);
  };
  XHR.prototype.send = function(body) {
    this.addEventListener('loadend', () => {
      try {
        const url = this.responseURL || this.__omega0173?.url || '';
        if (!isRelevantUrl(url)) return;
        let text = '';
        if (this.responseType === '' || this.responseType === 'text') text = this.responseText || '';
        else if (this.responseType === 'json') text = JSON.stringify(this.response ?? null);
        pushResponse({transport:'xhr',url,status:this.status,contentType:this.getResponseHeader('content-type'),text});
      } catch (e) { state.notes.push(`xhr capture error: ${String(e)}`); }
    });
    return origSend.call(this,body);
  };

  const buttons = () => [...document.querySelectorAll('button,[role="button"]')].filter(x => x.offsetParent !== null);
  const findButton = label => buttons().find(x => clean(x.textContent).toLowerCase() === label.toLowerCase());
  const click = label => {
    const b = findButton(label);
    if (!b) { state.notes.push(`button not found: ${label}`); return false; }
    b.click(); state.notes.push(`clicked: ${label}`); return true;
  };

  const makeOutput = () => ({
    ...state,
    active: undefined,
    exportedAt: new Date().toISOString(),
    pageUrl: location.href,
    eventCount: state.events.length,
    fullPayloadCount: state.events.filter(x => x.responseData != null || x.responseTextFallback != null).length,
  });

  const filename = () => {
    const stamp = new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d{3}Z$/,'Z');
    return `${DOWNLOAD_PREFIX}_${stamp}.json`;
  };

  const downloadCapture = () => {
    const out = makeOutput();
    const text = JSON.stringify(out, null, 2);
    const blob = new Blob([text], {type:'application/json'});
    const href = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = href;
    a.download = filename();
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(href); a.remove(); }, 2000);
    console.log(`OMEGA 0.17.3 capture download requested: ${out.eventCount} API events, ${out.fullPayloadCount} full payload(s).`);
    console.log('If Chrome blocked the automatic download, click the orange OMEGA download button on the page.');
    return out;
  };

  const installDownloadButton = () => {
    const old = document.getElementById('omega0173-download-capture');
    if (old) old.remove();
    const b = document.createElement('button');
    b.id = 'omega0173-download-capture';
    b.textContent = 'Download OMEGA T+A capture';
    Object.assign(b.style, {
      position:'fixed', top:'16px', right:'16px', zIndex:'2147483647', padding:'12px 16px',
      background:'#f97316', color:'#fff', border:'0', borderRadius:'8px', fontWeight:'700',
      boxShadow:'0 2px 10px rgba(0,0,0,.35)', cursor:'pointer'
    });
    b.addEventListener('click', downloadCapture);
    document.body.appendChild(b);
  };

  window[KEY] = { state, downloadCapture, click };
  console.log('OMEGA 0.17.3 NFL T+A probe ACTIVE. Forcing Tackles -> Tckl+Ast to capture the structured response...');
  click('Tackles');
  setTimeout(() => click('Tckl+Ast'), 1200);
  setTimeout(() => {
    installDownloadButton();
    const out = downloadCapture();
    console.log(`OMEGA 0.17.3 capture ready. events=${out.eventCount} fullPayloads=${out.fullPayloadCount}`);
  }, 9000);
})();
