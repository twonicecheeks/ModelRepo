(() => {
  'use strict';
  const VERSION = '0.17.2';
  const KEY = '__OMEGA_PM_NFL_TA_PROBE_0172__';
  if (window[KEY]?.active) {
    console.log('OMEGA PropsMadness NFL T+A probe already active.');
    return;
  }

  const state = {
    schemaVersion: 'OMEGA_PM_NFL_TA_PROBE_0.17.2',
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
    this.__omega0172 = {method,url:String(url)};
    return origOpen.call(this,method,url,...rest);
  };
  XHR.prototype.send = function(body) {
    this.addEventListener('loadend', () => {
      try {
        const url = this.responseURL || this.__omega0172?.url || '';
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

  const exportCapture = async () => {
    const out = {
      ...state,
      active: undefined,
      exportedAt: new Date().toISOString(),
      pageUrl: location.href,
      eventCount: state.events.length,
      fullPayloadCount: state.events.filter(x => x.responseData != null || x.responseTextFallback != null).length,
    };
    const text = JSON.stringify(out, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      console.log(`OMEGA 0.17.2 capture copied to clipboard: ${out.eventCount} API events, ${out.fullPayloadCount} full payload(s).`);
    } catch (e) {
      console.log('Clipboard write was blocked. Copy the object below manually:');
      console.log(text);
    }
    return out;
  };

  window[KEY] = { state, exportCapture, click };
  console.log('OMEGA 0.17.2 NFL T+A probe ACTIVE. Forcing a Tackles -> Tckl+Ast market switch to capture the structured response...');

  // Force a market transition so a cached current T+A view does not hide the endpoint.
  click('Tackles');
  setTimeout(() => click('Tckl+Ast'), 1200);
  setTimeout(() => exportCapture(), 9000);
})();
