(() => {
  'use strict';
  const V='3.0.0';
  const SERVICE='http://127.0.0.1:8765';
  const SERVICE_TOKEN='8a3a2e320be2dd7c09064eae91f3b4412c687e769f05aa4bd384a8d3ed7d309e';
  const core=window.MODELV2Core;
  if(!core) return;

  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const hasNum=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
  const pct=v=>hasNum(v)?`${(Number(v)*100).toFixed(1)}%`:'—';
  const odds=v=>hasNum(v)?(Number(v)>0?`+${Math.round(Number(v))}`:`${Math.round(Number(v))}`):'—';
  const normName=v=>String(v||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9 ]+/g,' ').replace(/\s+/g,' ').trim();
  const sameName=(a,b)=>{const aa=normName(a),bb=normName(b);if(!aa||!bb)return false;if(aa===bb)return true;const at=aa.split(' '),bt=bb.split(' ');return at.length>1&&bt.length>1&&at.at(-1)===bt.at(-1)&&at[0][0]===bt[0][0];};
  function refreshStructuredMoneylineFreshness(projection,game,board){
    if(!projection) return projection;
    const p={...projection};
    const raw=[...(game?.sourceFreshness?.timestamps||[]),board?.builtAt].filter(Boolean);
    const times=raw.map(x=>Date.parse(x)).filter(Number.isFinite);
    if(times.length){
      const now=Date.now();
      p.modelInputAgeMinutes=Math.max(...times.map(t=>Math.max(0,(now-t)/60000)));
      p.modelCaptureSkewMinutes=(Math.max(...times)-Math.min(...times))/60000;
    }else{
      p.modelInputAgeMinutes=null;
      p.modelCaptureSkewMinutes=null;
    }
    p.dataQuality=p.dataQuality||((game?.status==='READY'&&game?.projectionEligible)?'High':'Low');
    p.productionInputSource='STRUCTURED_ML_BOARD';
    p.structuredBoardBuiltAt=board?.builtAt||null;
    p.structuredEngineVersion=board?.engineVersion||null;
    p.calibrationStatus=board?.calibrationStatus||p.calibrationStatus||null;
    return p;
  }
  function refreshKFreshness(projection){
    if(!projection) return projection;
    const p={...projection};
    const rows=Array.isArray(projection.marketFreshness)?projection.marketFreshness:[];
    const times=rows.map(x=>Date.parse(x?.capturedAt||'')).filter(Number.isFinite);
    if(times.length){
      const now=Date.now();
      p.oldestMarketAgeMinutes=Math.max(...times.map(t=>Math.max(0,(now-t)/60000)));
      p.captureSkewMinutes=(Math.max(...times)-Math.min(...times))/60000;
      const freshLimit=Number(p.sourceFreshLimitMinutes??20);
      const skewLimit=Number(p.sourceMaxSkewMinutes??2);
      p.freshnessWarning=p.oldestMarketAgeMinutes>freshLimit
        ? `structured model package stale (${Math.round(p.oldestMarketAgeMinutes)}m)`
        : p.captureSkewMinutes>skewLimit
          ? `structured market sync skew ${p.captureSkewMinutes.toFixed(1)}m`
          : null;
    }else{
      p.oldestMarketAgeMinutes=null;
      p.captureSkewMinutes=null;
      p.freshnessWarning='structured model-source timestamps missing';
    }
    return p;
  }
  const state={health:null,config:null,snapshot:null,edges:[],error:null,busy:false,copyNotice:null,copyButtonState:'idle',lastRefreshMode:null};

  async function fetchJson(path){
    const r=await fetch(`${SERVICE}${path}`,{cache:'no-store',headers:{'X-Model-Token':SERVICE_TOKEN}});
    const j=await r.json().catch(()=>({error:`HTTP ${r.status}`}));
    if(!r.ok) throw new Error(j?.error||`HTTP ${r.status}`);
    return j;
  }

  function installStyle(){
    if(document.getElementById('modelV2Style')) return;
    const s=document.createElement('style'); s.id='modelV2Style';
    s.textContent=`
      #modelV2Panel{margin:12px 0;padding:14px;border:1px solid rgba(125,211,252,.35);border-radius:14px;background:linear-gradient(180deg,rgba(12,24,38,.97),rgba(7,15,25,.97));color:#e8f2fa;font-family:system-ui,-apple-system,sans-serif}
      #modelV2Panel .m2-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.m2-title{font-weight:800;font-size:15px}.m2-sub{font-size:11px;opacity:.72;margin-top:3px}.m2-badge{font-size:10px;border-radius:999px;padding:4px 8px;background:#163047}.m2-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:11px 0}.m2-actions button{border:0;border-radius:9px;padding:9px 10px;font-weight:700;cursor:pointer}.m2-primary{background:#c7f9cc;color:#102216}.m2-secondary{background:#20364c;color:#e8f2fa}.m2-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:8px 0}.m2-stat{background:rgba(255,255,255,.045);padding:7px;border-radius:8px}.m2-stat b{display:block;font-size:13px}.m2-stat span{font-size:9px;opacity:.68}.m2-row{border-top:1px solid rgba(255,255,255,.08);padding:9px 0}.m2-row:first-child{border-top:0}.m2-state{font-weight:800;font-size:10px}.m2-VERIFIED{color:#8ff0a4}.m2-WATCH{color:#ffd166}.m2-ANOMALY{color:#ff9f7a}.m2-BLOCKED{color:#ff7b7b}.m2-PASS{color:#9fb0bd}.m2-small{font-size:10px;opacity:.72;line-height:1.35}.m2-edge{font-size:12px;margin-top:3px}.m2-error{margin-top:8px;color:#ff9f9f;font-size:11px}.m2-tabs{display:flex;gap:5px;margin-top:8px}.m2-tab{font-size:9px;padding:4px 7px;border-radius:999px;background:#172637}.m2-tab.off{opacity:.45}.m2-note{font-size:10px;line-height:1.4;background:rgba(255,255,255,.035);padding:8px;border-radius:8px;margin-top:8px}.m2-copy-status{font-size:10px;line-height:1.35;margin:-3px 0 9px;padding:7px 8px;border-radius:8px;background:rgba(143,240,164,.08);color:#9df0af;border:1px solid rgba(143,240,164,.2)}.m2-copy-status.bad{background:rgba(255,123,123,.08);color:#ff9f9f;border-color:rgba(255,123,123,.22)}.m2-secondary.copied{background:#1e5b39;color:#d8ffe7}.m2-secondary.copy-failed{background:#5b2525;color:#ffe0e0}
    `;
    document.head.appendChild(s);
  }

  function host(){
    let p=document.getElementById('modelV2Panel');
    if(p) return p;
    p=document.createElement('section'); p.id='modelV2Panel';
    let control=document.getElementById('modelControlPlaneRoot');
    if(!control){ control=document.createElement('div'); control.id='modelControlPlaneRoot'; document.body.prepend(control); }
    let trustHost=document.getElementById('modelTrustHost');
    if(!trustHost){ trustHost=document.createElement('div'); trustHost.id='modelTrustHost'; control.appendChild(trustHost); }
    trustHost.appendChild(p);
    return p;
  }

  function render(){
    installStyle(); const p=host();
    const verified=state.edges.filter(x=>x.trust.state==='VERIFIED').length;
    const watch=state.edges.filter(x=>x.trust.state==='WATCH').length;
    const anomaly=state.edges.filter(x=>x.trust.state==='ANOMALY').length;
    const blocked=state.edges.filter(x=>x.trust.state==='BLOCKED').length;
    const serviceOk=state.health?.ok;
    const rows=core.sortEdgesByOpportunity(state.edges.filter(x=>['VERIFIED','WATCH','ANOMALY'].includes(x.trust.state)));
    p.innerHTML=`
      <div class="m2-head"><div><div class="m2-title">MODEL · Trust Layer <span style="opacity:.6">v${V}</span></div><div class="m2-sub">Independent model → source-appropriate market truth → integrity gate → edge</div></div><div class="m2-badge">${serviceOk?'SERVICE ONLINE':'SERVICE OFFLINE'}</div></div>
      <div class="m2-tabs"><span class="m2-tab">MLB ACTIVE</span><span class="m2-tab off">NFL PLANNED</span><span class="m2-tab off">CFB PLANNED</span></div>
      <div class="m2-actions"><button id="m2KOnly" class="m2-primary" ${state.busy?'disabled':''}>${state.busy?'WORKING…':'REFRESH K EDGES · 0 API'}</button><button id="m2Refresh" class="m2-secondary" ${state.busy?'disabled':''}>${state.busy?'WORKING…':'REFRESH ML + ALL · ~3 API'}</button><button id="m2Audit" style="grid-column:1/-1" class="m2-secondary ${state.copyButtonState==='ok'?'copied':state.copyButtonState==='bad'?'copy-failed':''}">${state.copyButtonState==='ok'?'COPIED ✓':state.copyButtonState==='bad'?'COPY FAILED':'COPY TRUST AUDIT'}</button></div>
      ${state.copyNotice?`<div class="m2-copy-status ${state.copyNotice.ok?'':'bad'}">${esc(state.copyNotice.text)}</div>`:''}
      <div class="m2-grid"><div class="m2-stat"><b>${verified}</b><span>VERIFIED</span></div><div class="m2-stat"><b>${watch}</b><span>WATCH</span></div><div class="m2-stat"><b>${anomaly}</b><span>ANOMALY</span></div><div class="m2-stat"><b>${blocked}</b><span>BLOCKED</span></div></div>
      <div>${rows.length?rows.map(edgeRow).join(''):'<div class="m2-small">No verified/watch edges built yet. Refresh after your MLB model data is ready.</div>'}</div>
      <div class="m2-note"><b>Decision hierarchy:</b> VERIFIED first. WATCH is promising but explicitly NOT verified. ANOMALY is research-only and never outranks a clean WATCH. PASS/BLOCKED are not opportunities. <br><b>Trust boundary:</b> MLB moneyline uses OddsPapi game-market truth. Starter-K uses PropsMadness K market truth after the independent K distribution is built. OddsPapi is reserved for supported game markets on this plan.</div>
      ${state.error?`<div class="m2-error">${esc(state.error)}</div>`:''}
    `;
    p.querySelector('#m2KOnly')?.addEventListener('click',refreshKOnly);
    p.querySelector('#m2Refresh')?.addEventListener('click',refreshAndBuild);
    p.querySelector('#m2Audit')?.addEventListener('click',copyAudit);
  }

  function edgeRow(x){
    const t=x.trust,s=t.side||{}; const m=x.market||{};
    const isK=x.kind==='K';
    const title=isK ? `${m.away||'?'} @ ${m.home||'?'} · ${m.player||'?'} ${s.label||''}${Number.isFinite(Number(m.line))?Number(m.line):''} K` : `${m.away||'?'} @ ${m.home||'?'} · ${s.team||''}`;
    const qual=isK ? (x.projection?.confidence||'—') : (x.projection?.dataQuality||'—');
    const offenseInfo=!isK&&Number.isFinite(Number(x.projection?.awayOffenseRating))&&Number.isFinite(Number(x.projection?.homeOffenseRating))?` · offense ${m.away||'?'} ${Number(x.projection.awayOffenseRating).toFixed(0)} / ${m.home||'?'} ${Number(x.projection.homeOffenseRating).toFixed(0)}`:'';
    return `<div class="m2-row"><div class="m2-state m2-${esc(t.state)}">${esc(core.opportunityLabel(x))} · ${isK?'K':'ML'}</div><div><b>${esc(title)}</b></div><div class="m2-edge">Model ${pct(s.model)} · ${isK?'Market':'Sharp'} ${pct(s.market)} · Edge ${Number.isFinite(s.edge)?(s.edge*100).toFixed(1)+'pp':'—'} · Fair ${odds(s.fair)} · Best ${s.best?`${odds(s.best.american)} ${esc(s.best.book)}`:'—'} · EV ${Number.isFinite(s.ev)?(s.ev*100).toFixed(1)+'%':'—'}</div><div class="m2-small">Model quality ${esc(qual)}${offenseInfo} · market age ${Math.round(t.marketAgeSeconds||0)}s${t.reasons?.length?' · '+esc(t.reasons.join(' · ')):''}</div></div>`;
  }

  function marketRowRank(r){
    if(!r) return -1;
    const sharpBooks=Array.isArray(r?.sharp?.books)?r.sharp.books.length:0;
    const quoteBooks=Object.keys(r?.quotes||{}).length;
    return (r?.identityStatus==='VERIFIED'?1000:0)+(sharpBooks>=2?500:sharpBooks===1?300:0)+(quoteBooks*10)+(r?.bestAvailable?.away?1:0)+(r?.bestAvailable?.home?1:0);
  }

  function indexMarketsByGamePk(rows){
    const out=new Map();
    for(const r of (rows||[])){
      const pk=String(r?.gamePk||''); if(!pk) continue;
      const prev=out.get(pk);
      if(!prev||marketRowRank(r)>marketRowRank(prev)) out.set(pk,r);
    }
    return out;
  }

  async function getModelEdges(snapshot,config,{includeMoneyline=true}={}){
    const out=[];
    const marketByPk=indexMarketsByGamePk(snapshot.rows||[]);

    if(includeMoneyline){
      const mlStored=await chrome.storage.local.get('model_mlb_ml_projection_board_current');
      const mlBoard=mlStored.model_mlb_ml_projection_board_current||null;
      for(const game of (mlBoard?.games||[])){
        const pk=String(game.gamePk||''); if(!pk) continue;
        const market=marketByPk.get(pk)||null;
        let projection=game?.projection?refreshStructuredMoneylineFreshness(game.projection,game,mlBoard):null;
        let trust;
        if(game?.status!=='READY'||!game?.projectionEligible||!projection){
          trust={state:'BLOCKED',reasons:[...new Set(game?.reasons?.length?game.reasons:['structured ML production projection unavailable'])]};
        }else{
          trust=core.trustMoneyline({projection,market,config});
        }
        const fallbackMarket=market||{gamePk:pk,away:game.away||'?',home:game.home||'?',identityStatus:'UNJOINED',observedAt:null,marketSource:'OddsPapi'};
        out.push({kind:'ML',gamePk:pk,projection,market:fallbackMarket,trust,structuredStatus:game?.status||'BLOCKED',structuredReasons:game?.reasons||[],calibrationStatus:mlBoard?.calibrationStatus||null,productionModelSource:'STRUCTURED_ML_BOARD',legacyProductionDependency:false});
      }
    }

    const stored=await chrome.storage.local.get('model_mlb_k_projection_board_current');
    const kBoard=stored.model_mlb_k_projection_board_current||null;

    for(const game of (kBoard?.games||[])){
      const pk=String(game.gamePk||''); if(!pk) continue;
      for(const row of (game.starters||[])){
        let projection=row?.projection?refreshKFreshness(row.projection):null;
        let market=null;
        let trust={state:'BLOCKED',reasons:[]};

        if(!projection){
          trust.reasons.push(...(row?.reasons?.length?row.reasons:['structured K distribution unavailable']));
        }else if(!core.localStarterKMarket){
          trust.reasons.push('PropsMadness local K market adapter unavailable');
        }else{
          market=core.localStarterKMarket({projection,row,game});
          if(!market){
            trust.reasons.push('no current PropsMadness K line available for this official starter');
          }else{
            trust=core.trustStarterK({projection,market,config});
            if(trust.state==='BLOCKED'&&row?.hardReasons?.length){
              trust={...trust,reasons:[...new Set([...(row.hardReasons||[]),...(trust.reasons||[])])]};
            }
            const prospective=(projection?.calibrationStatus||kBoard?.calibrationStatus)!=='VALIDATED';
            if(trust.state==='WATCH'&&prospective){
              trust={...trust,reasons:[...new Set([...(trust.reasons||[]),'structured K lineage is prospective after input migration'])]};
            }
            if(trust.state==='VERIFIED'&&(prospective||row?.status==='WATCH')){
              const reasons=[...(trust.reasons||[])];
              if(prospective) reasons.push('structured K lineage is prospective after input migration');
              if(row?.status==='WATCH') reasons.push('structured K input confidence is WATCH');
              trust={...trust,state:'WATCH',reasons:[...new Set(reasons)]};
            }
          }
        }

        const fallbackMarket=market||{gamePk:pk,away:game.away||'?',home:game.home||'?',player:projection?.player||row?.officialName||'?',line:projection?.localKLine??null,marketSource:'PropsMadness'};
        out.push({kind:'K',gamePk:pk,projection,market:fallbackMarket,trust,structuredStatus:row?.status||'BLOCKED',structuredReasons:row?.reasons||[],calibrationStatus:projection?.calibrationStatus||kBoard?.calibrationStatus||null,marketCandidatesEvaluated:market?1:0,targetMarketSeparation:'EXPECTED_K_INDEPENDENT_OF_TARGET_K_LINE',marketReferenceSource:'PROPSMADNESS_MULTI_BOOK_K_REFERENCE'});
      }
    }

    return core.sortEdgesByOpportunity(out);
  }

  function edgeMarketSignature(edges){
    const rows=(edges||[]).map(e=>{const t=e?.trust||{},s=t?.side||{},m=e?.market||{};return[e?.kind||'',String(e?.gamePk||''),String(m?.player||''),Number.isFinite(Number(m?.line))?Number(m.line):null,String(s?.team||s?.side||s?.label||''),Number.isFinite(Number(s?.market))?Number(s.market):null,Number.isFinite(Number(s?.best?.american))?Number(s.best.american):null];});
    rows.sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));return JSON.stringify(rows);
  }
  async function persistEdgeBoard(board){
    const st=await chrome.storage.local.get(['modelV2LastEdgeBoard','modelV2PreviousEdgeBoard']),current=st.modelV2LastEdgeBoard||null,prior=st.modelV2PreviousEdgeBoard||null,payload={modelV2LastEdgeBoard:{...board,marketSignature:edgeMarketSignature(board?.edges)}};
    const currentSig=current?.marketSignature||edgeMarketSignature(current?.edges),nextSig=payload.modelV2LastEdgeBoard.marketSignature;
    if(current?.builtAt&&currentSig!==nextSig)payload.modelV2PreviousEdgeBoard=current;else if(prior)payload.modelV2PreviousEdgeBoard=prior;
    await chrome.storage.local.set(payload);
  }

  async function refreshFromLatest({source='PIPELINE_SYNC'}={}){
    if(state.busy)return{status:'BUSY',verified:0,watch:0,anomaly:0,blocked:0,oddsPapiRequests:0};
    state.busy=true;state.error=null;state.copyNotice=null;state.copyButtonState='idle';state.lastRefreshMode='LATEST_MARKET_ZERO_API';render();
    try{
      state.health=await fetchJson('/v1/health');state.config=state.config||await fetchJson('/v1/config');
      let latest={rows:[],observedAt:null,cacheAgeSeconds:null};try{latest=await fetchJson('/v1/markets/latest?sport=mlb');}catch(e){if(!/no snapshot|404/i.test(String(e?.message||e)))throw e;}
      state.snapshot=latest;state.edges=await getModelEdges(latest,state.config);
      const board={version:V,builtAt:new Date().toISOString(),snapshotObservedAt:latest?.observedAt||null,mode:'LATEST_MARKET_ZERO_API',trigger:source,oddsPapiRequests:0,edges:state.edges};await persistEdgeBoard(board);
      const count=x=>state.edges.filter(e=>e?.trust?.state===x).length;return{status:'PASS',verified:count('VERIFIED'),watch:count('WATCH'),anomaly:count('ANOMALY'),blocked:count('BLOCKED'),pass:count('PASS'),latestAgeSeconds:latest?.cacheAgeSeconds??null,latestObservedAt:latest?.observedAt||null,oddsPapiRequests:0};
    }catch(e){state.error=e?.message||String(e);return{status:'ERROR',error:state.error,oddsPapiRequests:0};}
    finally{state.busy=false;render();}
  }

  async function refreshKOnly(){
    if(state.busy) return; state.busy=true; state.error=null; state.copyNotice=null; state.copyButtonState='idle'; state.lastRefreshMode='K_ONLY_ZERO_ODDSPAPI'; render();
    try{
      state.health=await fetchJson('/v1/health');
      state.config=state.config||await fetchJson('/v1/config');
      state.edges=(await getModelEdges({rows:[]},state.config,{includeMoneyline:false})).filter(x=>x.kind==='K');
      await persistEdgeBoard({version:V,builtAt:new Date().toISOString(),mode:state.lastRefreshMode,oddsPapiRequests:0,edges:state.edges});
    }catch(e){ state.error=e?.message||String(e); }
    finally{state.busy=false;render();}
  }

  async function refreshAndBuild(){
    if(state.busy) return; state.busy=true; state.error=null; state.copyNotice=null; state.copyButtonState='idle'; state.lastRefreshMode='STRUCTURED_ML_FULL_GAME_MARKET'; render();
    try{
      state.health=await fetchJson('/v1/health');
      state.config=await fetchJson('/v1/config');
      state.snapshot=await fetchJson('/v1/markets/refresh?sport=mlb');
      state.edges=await getModelEdges(state.snapshot,state.config);
      await persistEdgeBoard({version:V,builtAt:new Date().toISOString(),snapshotObservedAt:state.snapshot.observedAt,edges:state.edges});
    }catch(e){ state.error=e?.message||String(e); }
    finally{state.busy=false;render();}
  }

  async function copyAudit(){
    try{
      const service=await fetchJson('/v1/audit');
      const lines=[];
      lines.push(`MODEL v2 TRUST AUDIT ${V}`);
      lines.push(`Generated: ${new Date().toISOString()}`);
      lines.push('');
      lines.push(`Service: ${service.serviceVersion||'—'} · provider OddsPapi`);
      lines.push(`Refresh mode: ${state.lastRefreshMode||'unknown / latest snapshot'}`);
      const quota=service.latest?.quotaPolicy||null;
      if(state.lastRefreshMode==='K_ONLY_ZERO_ODDSPAPI') lines.push('OddsPapi usage this action: 0 requests · K-only local evaluation'); else lines.push(`OddsPapi usage: ${service.latest?.requestCount??0} request(s) in latest game-market refresh · books ${Array.isArray(service.latest?.booksRequested)&&service.latest.booksRequested.length?service.latest.booksRequested.join(', '):'—'} · player-prop requests ${quota?.playerPropRequestsThisRefresh??0}`);
      if(state.lastRefreshMode!=='K_ONLY_ZERO_ODDSPAPI'){
        const coverage=service.latest?.bookCoverage||{};
        const parts=Object.entries(coverage).map(([book,x])=>`${book} ${x?.requestOutcome||'unknown'} · fixtures ${x?.fixturesReturned??0} · joined ${x?.officialJoined??0} · ML ${x?.moneylineQuotesParsed??0}`);
        if(parts.length) lines.push(`OddsPapi book coverage: ${parts.join(' | ')}`);
        lines.push(`Sharp-ready market rows: ${service.latest?.sharpReadyRowCount??0} · 2-sharp consensus ${service.latest?.twoSharpConsensusRowCount??0} · multi-book merged ${service.latest?.multiBookMergedRowCount??0} · canonical games ${service.latest?.canonicalGameCount??service.latest?.rows??0}`);
        const failures=(service.latest?.requestLog||[]).filter(x=>x?.outcome&&x.outcome!=='ok');
        if(failures.length) lines.push(`OddsPapi request failures: ${failures.map(x=>`${x.book||x.endpoint||'?'} ${x.error||x.outcome}`).join(' | ')}`);
      }
      lines.push(`OddsPapi plan policy: ${quota?.monthlyRequestLimit??250}/month · player props NOT INCLUDED · game markets only`);
      lines.push('K market reference: PropsMadness book-level K offers · Pinnacle/Circa same-line no-vig sharp consensus when available · local executable price remains downstream · one-sided price = EV-only WATCH fallback');
      lines.push(`Credential boundary: ${service.credentialBoundary}`);
      lines.push(`Persistence: ${service.persistence}`);
      lines.push(`Canonical identity: ${state.lastRefreshMode==='K_ONLY_ZERO_ODDSPAPI'?'MLB gamePk for K; OddsPapi fixtureId join occurs only during supported game-market refresh':service.canonicalIdentity}`);
      lines.push(`Fail closed identity: ${service.failClosedIdentity?'YES':'NO'}`);
      lines.push(`Production model mutation: ${service.productionModelMutation?'YES':'NO'}`);
      lines.push(`Market comparison stage: ${service.marketComparisonStage}`);
      const mlBoard=(await chrome.storage.local.get('model_mlb_ml_projection_board_current')).model_mlb_ml_projection_board_current||null;
      const radarBoard=(await chrome.storage.local.get('model_mlb_slate_radar_current')).model_mlb_slate_radar_current||null;
      lines.push(`ML production source: STRUCTURED_ML_BOARD${mlBoard?` · engine ${mlBoard.engineVersion} · ${mlBoard.modelVersion}`:''}`);
      if(radarBoard) lines.push(`Slate Radar: ${radarBoard.mlCandidateCount||0} ML candidate(s) · ${radarBoard.kCandidateCount||0} K candidate(s) · ${radarBoard.mode||'PRELIMINARY'} · actionable NO · OddsPapi 0`);
      lines.push('Legacy PMV1Engine runtime: REMOVED · production dependency: NO');
      lines.push('Opportunity order: VERIFIED > WATCH (NOT VERIFIED) > preliminary Radar > RESEARCH ANOMALY > PASS/BLOCKED');
      if(mlBoard) lines.push(`Structured ML board: ${mlBoard.readyCount||0} READY · ${mlBoard.blockedCount||0} BLOCKED · calibration ${mlBoard.calibrationStatus||'—'} · built ${mlBoard.builtAt||'—'}`);
      lines.push('');
      for(const x of state.edges){
        const t=x.trust,s=t.side||{},m=x.market||{};
        const oi=x.kind==='ML'&&Number.isFinite(Number(x.projection?.awayOffenseRating))&&Number.isFinite(Number(x.projection?.homeOffenseRating))?` · offense ${m.away||'?'} ${Number(x.projection.awayOffenseRating).toFixed(0)} / ${m.home||'?'} ${Number(x.projection.homeOffenseRating).toFixed(0)}`:'';
        const auditState=t.state==='WATCH'?'WATCH (NOT VERIFIED)':t.state==='ANOMALY'?'RESEARCH ANOMALY':t.state;
        lines.push(`${auditState} · ${m.away||'?'} @ ${m.home||'?'} · ${s.team||'—'} · model ${pct(s.model)} · market ${pct(s.market)} · edge ${Number.isFinite(s.edge)?(s.edge*100).toFixed(1)+'pp':'—'} · EV ${Number.isFinite(s.ev)?(s.ev*100).toFixed(1)+'%':'—'}${oi}${t.reasons?.length?' · '+t.reasons.join('; '):''}`);
      }
      lines.push('');
      lines.push('K status: v0.8.3 shrinks small current-season pitcher skill samples and surfaces limited workload uncertainty. Expected K remains independent of the target K line/price. PropsMadness supplies downstream book-level K offers; Pinnacle/Circa form the sharp reference only when both quote the same line. OddsPapi player-prop calls remain disabled.');
      lines.push('ML status: production probability comes from the structured ML board before OddsPapi comparison. OddsPapi remains downstream game-market truth only; blocked structured inputs fail closed. Slate Radar is preliminary-only scouting and never feeds Trust.');
      const txt=lines.join('\n');
      await navigator.clipboard.writeText(txt);
      state.error=null;
      state.copyButtonState='ok';
      state.copyNotice={ok:true,text:`Trust audit copied ✓ · ${txt.length.toLocaleString()} characters · ${new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit',second:'2-digit'})}. Clipboard write confirmed by browser.`};
      render();
      setTimeout(()=>{ if(state.copyButtonState==='ok'){ state.copyButtonState='idle'; render(); } },3000);
    }catch(e){
      state.copyButtonState='bad';
      state.copyNotice={ok:false,text:`Trust audit copy FAILED · ${e?.message||String(e)}`};
      state.error=null;
      render();
    }
  }

  async function boot(){
    render();
    try{ state.health=await fetchJson('/v1/health'); state.config=await fetchJson('/v1/config'); }
    catch(e){ state.error=`Local MODEL service unavailable: ${e?.message||e}`; }
    render();
  }
  window.MODEL_TRUST_CONTROLLER={version:V,refreshFromLatest,refreshKOnly,refreshAndBuild,serviceGet:fetchJson,getState:()=>({...state})};
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,80),{once:true}); else setTimeout(boot,80);
})();
