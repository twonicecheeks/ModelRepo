(() => {
  'use strict';
  const VERSION = '0.17.4';
  const KEY = '__OMEGA_PM_NFL_TA_PROBE_0174__';
  const SCHEMA = 'OMEGA_PM_NFL_TA_DISCOVERY_0.17.4';
  const DOWNLOAD_PREFIX = 'OMEGA_0174_PROPSMADNESS_NFL_TA_DISCOVERY';
  if (window[KEY]?.active) { console.log('OMEGA 0.17.4 discovery probe already active.'); return; }

  const MAX_BODY_CHARS = 8_000_000;
  const MAX_DOM_CHARS = 1_500_000;
  const MAX_JSON_STATE_CHARS = 6_000_000;
  const sensitiveParam = /(token|auth|key|session|jwt|secret|signature|^sig$)/i;
  const clean = x => String(x ?? '').replace(/\s+/g, ' ').trim();
  const state = {
    schemaVersion: SCHEMA, version: VERSION, active: true,
    startedAt: new Date().toISOString(), pageUrl: location.href, pageTitle: document.title,
    apiEvents: [], performanceResources: [], domSnapshots: [], jsonState: [], notes: [],
  };

  const sanitizeUrl = raw => {
    try {
      const u = new URL(raw, location.href);
      for (const [k] of [...u.searchParams.entries()]) if (sensitiveParam.test(k)) u.searchParams.set(k, '[REDACTED]');
      return u.toString();
    } catch { return String(raw || ''); }
  };
  const sameOrigin = raw => { try { return new URL(raw, location.href).origin === location.origin; } catch { return false; } };
  const interestingNetwork = raw => {
    try {
      const u = new URL(raw, location.href); if (u.origin !== location.origin) return false;
      const p = u.pathname.toLowerCase();
      return p.includes('/api/') || p.includes('/graphql') || p.includes('/trpc') || p.includes('/_next/data/') || p.includes('/offer/') || p.includes('/explore/');
    } catch { return false; }
  };
  const safeJson = text => { try { return JSON.parse(text); } catch { return null; } };
  const summarize = data => {
    if (Array.isArray(data)) return {type:'array',length:data.length};
    if (data && typeof data === 'object') return {type:'object',keys:Object.keys(data).slice(0,100)};
    return {type:typeof data};
  };
  const relevance = text => {
    const s = String(text || '').toLowerCase();
    return ['tckl+ast','tackles + assists','tackles+assists','tackle','assist','nfl','sportsbook','fanduel','draftkings','pinnacle','circa','odds','over','under'].filter(x => s.includes(x));
  };
  const pushApi = ({transport,url,status,contentType,text,method}) => {
    if (!interestingNetwork(url)) return;
    const clipped = String(text || '').slice(0, MAX_BODY_CHARS);
    const data = safeJson(clipped);
    state.apiEvents.push({
      capturedAt:new Date().toISOString(), transport, method:method || null,
      url:sanitizeUrl(url), status:Number(status || 0), contentType:contentType || null,
      relevanceTerms:relevance(`${url}\n${clipped.slice(0,300000)}`), responseSummary:summarize(data),
      responseData:data, responseTextFallback:data == null ? clipped : null,
      truncated:String(text || '').length > MAX_BODY_CHARS,
    });
  };

  const origFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const resp = await origFetch(...args);
    try {
      const rawUrl = resp.url || String(args[0]?.url || args[0] || '');
      if (interestingNetwork(rawUrl)) {
        const clone = resp.clone(); const text = await clone.text();
        const method = String(args[1]?.method || args[0]?.method || 'GET').toUpperCase();
        pushApi({transport:'fetch',url:rawUrl,status:resp.status,contentType:resp.headers.get('content-type'),text,method});
      }
    } catch (e) { state.notes.push(`fetch capture error: ${String(e)}`); }
    return resp;
  };

  const XHR = window.XMLHttpRequest, origOpen = XHR.prototype.open, origSend = XHR.prototype.send;
  XHR.prototype.open = function(method,url,...rest) { this.__omega0174={method:String(method || 'GET').toUpperCase(),url:String(url)}; return origOpen.call(this,method,url,...rest); };
  XHR.prototype.send = function(body) {
    this.addEventListener('loadend', () => {
      try {
        const rawUrl = this.responseURL || this.__omega0174?.url || ''; if (!interestingNetwork(rawUrl)) return;
        let text='';
        if (this.responseType==='' || this.responseType==='text') text=this.responseText || '';
        else if (this.responseType==='json') text=JSON.stringify(this.response ?? null);
        pushApi({transport:'xhr',url:rawUrl,status:this.status,contentType:this.getResponseHeader('content-type'),text,method:this.__omega0174?.method});
      } catch (e) { state.notes.push(`xhr capture error: ${String(e)}`); }
    });
    return origSend.call(this,body);
  };

  const snapshotPerformance = label => {
    const rows=[];
    for (const e of performance.getEntriesByType('resource')) {
      if (!sameOrigin(e.name)) continue;
      rows.push({name:sanitizeUrl(e.name),initiatorType:e.initiatorType || null,duration:Math.round((e.duration||0)*100)/100,transferSize:e.transferSize || 0});
    }
    state.performanceResources.push({capturedAt:new Date().toISOString(),label,resources:rows});
  };

  const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  const snapshotDom = label => {
    const selectors = ['table','[role="table"]','[role="grid"]','[role="row"]','[data-testid]','main','section'];
    const chunks=[]; const seen=new Set();
    for (const sel of selectors) {
      for (const el of document.querySelectorAll(sel)) {
        if (!visible(el)) continue;
        const text=clean(el.innerText || el.textContent); if (!text) continue;
        const low=text.toLowerCase();
        if (!(low.includes('tckl') || low.includes('tackle') || low.includes('assist') || low.includes('over') || low.includes('under') || low.includes('fanduel') || low.includes('draftkings') || low.includes('sportsbook'))) continue;
        const sig=text.slice(0,500); if (seen.has(sig)) continue; seen.add(sig);
        chunks.push({tag:el.tagName,role:el.getAttribute('role'),testid:el.getAttribute('data-testid'),text:text.slice(0,120000)});
        if (JSON.stringify(chunks).length > MAX_DOM_CHARS) break;
      }
      if (JSON.stringify(chunks).length > MAX_DOM_CHARS) break;
    }
    const clickable=[...document.querySelectorAll('button,[role="button"],[role="tab"],a')].filter(visible).map(el=>clean(el.innerText||el.textContent||el.getAttribute('aria-label')||el.getAttribute('title'))).filter(Boolean);
    state.domSnapshots.push({capturedAt:new Date().toISOString(),label,clickables:[...new Set(clickable)].slice(0,500),relevantBlocks:chunks});
  };

  const snapshotJsonState = label => {
    const out=[];
    const nd=document.querySelector('#__NEXT_DATA__');
    if (nd?.textContent) {
      const t=nd.textContent.slice(0,MAX_JSON_STATE_CHARS); if (relevance(t).length) out.push({source:'__NEXT_DATA__',text:t,truncated:nd.textContent.length>MAX_JSON_STATE_CHARS});
    }
    for (const [i,s] of [...document.querySelectorAll('script[type="application/json"]')].entries()) {
      const raw=s.textContent || ''; if (!raw || !relevance(raw).length) continue;
      out.push({source:`script[type=application/json]#${i}`,text:raw.slice(0,MAX_JSON_STATE_CHARS),truncated:raw.length>MAX_JSON_STATE_CHARS});
      if (out.length>=20) break;
    }
    state.jsonState.push({capturedAt:new Date().toISOString(),label,items:out});
  };

  const candidates = () => [...document.querySelectorAll('button,[role="button"],[role="tab"],a')].filter(visible);
  const findControl = label => {
    const want=label.toLowerCase().replace(/\s+/g,'');
    return candidates().find(el => {
      const t=clean(el.innerText||el.textContent||el.getAttribute('aria-label')||el.getAttribute('title')).toLowerCase().replace(/\s+/g,'');
      return t===want || t.includes(want) || want.includes(t);
    });
  };
  const click = label => { const el=findControl(label); if (!el) { state.notes.push(`control not found: ${label}`); return false; } el.click(); state.notes.push(`clicked: ${label}`); return true; };

  const captureAll = label => { snapshotPerformance(label); snapshotDom(label); snapshotJsonState(label); };
  const makeOutput = () => ({...state,active:undefined,exportedAt:new Date().toISOString(),pageUrl:location.href,
    apiEventCount:state.apiEvents.length,
    performanceResourceCount:state.performanceResources.reduce((n,x)=>n+x.resources.length,0),
    relevantDomBlockCount:state.domSnapshots.reduce((n,x)=>n+x.relevantBlocks.length,0),
    jsonStateItemCount:state.jsonState.reduce((n,x)=>n+x.items.length,0)});
  const filename = () => `${DOWNLOAD_PREFIX}_${new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d{3}Z$/,'Z')}.json`;
  const downloadCapture = () => {
    captureAll('export');
    const out=makeOutput(), blob=new Blob([JSON.stringify(out,null,2)],{type:'application/json'}), href=URL.createObjectURL(blob), a=document.createElement('a');
    a.href=href; a.download=filename(); a.style.display='none'; document.body.appendChild(a); a.click();
    setTimeout(()=>{URL.revokeObjectURL(href);a.remove();},2000);
    console.log(`OMEGA 0.17.4 discovery download requested: api=${out.apiEventCount} perf=${out.performanceResourceCount} dom=${out.relevantDomBlockCount} jsonState=${out.jsonStateItemCount}`);
    return out;
  };
  const installButton = () => {
    document.getElementById('omega0174-download')?.remove(); const b=document.createElement('button'); b.id='omega0174-download'; b.textContent='Download OMEGA broad discovery';
    Object.assign(b.style,{position:'fixed',top:'16px',right:'16px',zIndex:'2147483647',padding:'12px 16px',background:'#2563eb',color:'#fff',border:'0',borderRadius:'8px',fontWeight:'700',boxShadow:'0 2px 10px rgba(0,0,0,.35)',cursor:'pointer'});
    b.addEventListener('click',downloadCapture); document.body.appendChild(b);
  };

  window[KEY]={state,downloadCapture,click,captureAll};
  console.log('OMEGA 0.17.4 broad NFL T+A discovery ACTIVE. Capturing API + performance + relevant DOM/state.');
  captureAll('initial');
  click('Tackles');
  setTimeout(()=>{captureAll('after_tackles'); click('Tckl+Ast') || click('Tackles + Assists') || click('Tackles+Assists');},1500);
  setTimeout(()=>captureAll('after_ta_4s'),5500);
  setTimeout(()=>{installButton(); const out=downloadCapture(); console.log('OMEGA 0.17.4 discovery ready',out);},15000);
})();
