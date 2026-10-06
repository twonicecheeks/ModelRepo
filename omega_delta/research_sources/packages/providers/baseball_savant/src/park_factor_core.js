(() => {
  'use strict';

  const VERSION='1.1';
  const PROVIDER='Baseball Savant Statcast Park Factors';
  const PREFERRED_ROLLING_YEARS=3;
  const FALLBACK_ROLLING_YEARS=[3,2,1];

  const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
  const finite=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(String(v).replace(/,/g,'')));
  const num=(v,f=null)=>finite(v)?Number(String(v).replace(/,/g,'')):f;
  const validRolling=v=>[1,2,3].includes(Number(v))?Number(v):PREFERRED_ROLLING_YEARS;

  function buildUrl(year,rollingYears=PREFERRED_ROLLING_YEARS){
    const y=Number(year)||new Date().getUTCFullYear(),rolling=validRolling(rollingYears);
    const q=new URLSearchParams({condition:'All',parks:'mlb',rolling:String(rolling),stat:'index_wOBA',type:'year',year:String(y)});
    return `https://baseballsavant.mlb.com/leaderboard/statcast-park-factors?${q.toString()}`;
  }

  function decodeEntities(s=''){
    return String(s)
      .replace(/&nbsp;/gi,' ')
      .replace(/&amp;/gi,'&')
      .replace(/&quot;/gi,'"')
      .replace(/&#39;|&apos;/gi,"'")
      .replace(/&ndash;|&#8211;/gi,'-')
      .replace(/&mdash;|&#8212;/gi,'-')
      .replace(/&#(\d+);/g,(_,n)=>String.fromCharCode(Number(n)))
      .replace(/&#x([0-9a-f]+);/gi,(_,n)=>String.fromCharCode(parseInt(n,16)));
  }

  function cellText(html=''){
    return decodeEntities(String(html)
      .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,' ')
      .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi,' ')
      .replace(/<[^>]+>/g,' '))
      .replace(/\s+/g,' ').trim();
  }

  function rowCells(rowHtml=''){
    const out=[];
    const re=/<(?:th|td)\b[^>]*>([\s\S]*?)<\/(?:th|td)>/gi;
    let m;while((m=re.exec(String(rowHtml))))out.push(cellText(m[1]));
    return out;
  }

  function normalizeHeader(v){return String(v||'').toLowerCase().replace(/[^a-z0-9]+/g,'').trim();}
  function normalizeVenue(v){return String(v||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/&/g,' and ').replace(/[^a-z0-9]+/g,' ').replace(/\s+/g,' ').trim();}
  function canonicalVenue(v){return normalizeVenue(v).split(' ').filter(x=>!['the','park','stadium','field','ballpark','at'].includes(x)).join(' ');}

  function braceMatch(text,start,open,close){
    let depth=0,inString=null,escape=false;
    for(let i=start;i<text.length;i++){
      const ch=text[i];
      if(escape){escape=false;continue;}
      if(ch==='\\'){escape=true;continue;}
      if(inString){if(ch===inString)inString=null;continue;}
      if(ch==='"'||ch==="'"){inString=ch;continue;}
      if(ch===open)depth++;
      else if(ch===close&&--depth===0)return text.slice(start,i+1);
    }
    return null;
  }

  function inlineData(html){
    const m=/(?:\b(?:var|const|let)\s+)?\bdata\s*=\s*([\[{])/m.exec(html);
    if(!m)return null;
    const start=m.index+m[0].lastIndexOf(m[1]);
    const blob=braceMatch(html,start,m[1],m[1]==='['?']':'}');
    if(!blob)return null;
    try{const parsed=JSON.parse(blob);return Array.isArray(parsed)?parsed:(Array.isArray(parsed?.data)?parsed.data:null);}catch{return null;}
  }

  function rowObject(r,year,rollingYears){
    const rolling=validRolling(rollingYears),venue=r?.venue_name??r?.venueName??r?.venue??'';
    const runIndex=num(r?.index_runs??r?.r_factor??r?.index_run??r?.index_r??r?.runs??r?.R,null);
    if(!venue||!Number.isFinite(runIndex)||runIndex<50||runIndex>160)return null;
    const parkIndex=num(r?.index_woba??r?.index_wOBA??r?.park_factor??r?.parkFactor,null),runPct=runIndex-100;
    return {
      provider:PROVIDER,providerVersion:VERSION,year:Number(year)||null,rollingYears:rolling,
      preferredRollingYears:PREFERRED_ROLLING_YEARS,fallbackWindowUsed:rolling<PREFERRED_ROLLING_YEARS,
      team:r?.team_name??r?.team??r?.club??null,venue,venueKey:normalizeVenue(venue),canonicalVenueKey:canonicalVenue(venue),
      window:r?.year_display??r?.year_range??r?.year??null,parkIndex:Number.isFinite(parkIndex)?parkIndex:null,
      runIndex,runPct,runFactor:clamp(runIndex/100,.85,1.15),pa:num(r?.pa??r?.PA,null)
    };
  }

  function objectRows(html,year,rollingYears){
    const data=inlineData(html);if(!Array.isArray(data))return [];
    return data.map(r=>rowObject(r,year,rollingYears)).filter(Boolean);
  }

  function tableRows(html,year,rollingYears){
    const rolling=validRolling(rollingYears),trs=[...html.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)].map(m=>m[1]);
    if(!trs.length)return [];
    let header=null,headerIndex=-1;
    for(let i=0;i<trs.length;i++){const cells=rowCells(trs[i]),hs=cells.map(normalizeHeader);if(hs.includes('venue')&&hs.includes('r')&&(hs.includes('parkfactor')||hs.includes('wobacon'))){header=cells;headerIndex=i;break;}}
    const h=(header||[]).map(normalizeHeader),idx={team:h.indexOf('team'),venue:h.indexOf('venue'),window:h.indexOf('year'),park:h.indexOf('parkfactor'),run:h.indexOf('r'),pa:h.indexOf('pa')};
    const fallback=idx.venue<0||idx.run<0,rows=[];
    for(let i=0;i<trs.length;i++){
      if(i===headerIndex)continue;const c=rowCells(trs[i]);if(c.length<11)continue;
      const venue=c[fallback?2:idx.venue]||'',runIndex=num(c[fallback?10:idx.run],null);if(!venue||!Number.isFinite(runIndex)||runIndex<50||runIndex>160)continue;
      const parkIndex=num(c[fallback?4:idx.park],null),runPct=runIndex-100;
      rows.push({provider:PROVIDER,providerVersion:VERSION,year:Number(year)||null,rollingYears:rolling,preferredRollingYears:PREFERRED_ROLLING_YEARS,fallbackWindowUsed:rolling<PREFERRED_ROLLING_YEARS,team:c[fallback?1:idx.team]||null,venue,venueKey:normalizeVenue(venue),canonicalVenueKey:canonicalVenue(venue),window:c[fallback?3:idx.window]||null,parkIndex:Number.isFinite(parkIndex)?parkIndex:null,runIndex,runPct,runFactor:clamp(runIndex/100,.85,1.15),pa:num(c[fallback?19:idx.pa],null)});
    }
    return rows;
  }

  function indexRows(rows){
    const byVenue={};
    for(const r of rows){byVenue[r.venueKey]=r;if(r.canonicalVenueKey&&!byVenue[r.canonicalVenueKey])byVenue[r.canonicalVenueKey]=r;}
    return byVenue;
  }

  function parseHtml(html,year,rollingYears=PREFERRED_ROLLING_YEARS){
    const rolling=validRolling(rollingYears);
    if(typeof html!=='string'||html.length<100)throw new Error('Baseball Savant park-factor response was empty or too small');
    const embedded=objectRows(html,year,rolling),rows=embedded.length?embedded:tableRows(html,year,rolling);
    if(rows.length<20)throw new Error(`Baseball Savant park-factor parse produced only ${rows.length} MLB venue rows for rolling=${rolling}`);
    return {provider:PROVIDER,providerVersion:VERSION,year:Number(year)||null,rollingYears:rolling,preferredRollingYears:PREFERRED_ROLLING_YEARS,sourceUrl:buildUrl(year,rolling),rowCount:rows.length,rows,byVenue:indexRows(rows)};
  }

  function getForVenue(bundle,venueName){if(!bundle||!venueName)return null;const exact=normalizeVenue(venueName),canon=canonicalVenue(venueName);return bundle.byVenue?.[exact]||bundle.byVenue?.[canon]||null;}

  function mergeBundles(bundles){
    const valid=(bundles||[]).filter(Boolean).sort((a,b)=>Number(b.rollingYears||0)-Number(a.rollingYears||0));
    if(!valid.length)return null;
    const rows=[],seen=new Set(),sourceUrls=[];
    for(const b of valid){if(b.sourceUrl)sourceUrls.push(b.sourceUrl);for(const r of b.rows||[]){const key=r.venueKey||normalizeVenue(r.venue);if(!key||seen.has(key))continue;seen.add(key);rows.push({...r,fallbackWindowUsed:Number(r.rollingYears)<PREFERRED_ROLLING_YEARS});}}
    const fallbackRows=rows.filter(r=>r.fallbackWindowUsed);
    return {provider:PROVIDER,providerVersion:VERSION,year:valid[0].year,rollingYears:PREFERRED_ROLLING_YEARS,preferredRollingYears:PREFERRED_ROLLING_YEARS,availableRollingYears:valid.map(b=>b.rollingYears),sourceUrls:[...new Set(sourceUrls)],sourceUrl:valid[0].sourceUrl,rowCount:rows.length,fallbackRowCount:fallbackRows.length,fallbackVenues:fallbackRows.map(r=>({venue:r.venue,rollingYears:r.rollingYears,window:r.window,runIndex:r.runIndex})),rows,byVenue:indexRows(rows)};
  }

  function conditionLines(row){
    if(!row||!Number.isFinite(Number(row.runPct)))return [];
    const p=Number(row.runPct),rounded=Math.abs(p-Math.round(p))<1e-9?String(Math.round(p)):p.toFixed(1),windowNote=row.fallbackWindowUsed?` (${row.rollingYears}y fallback)`:'';
    return [`Park: ${row.venue}`,`Runs ${p>=0?'+':''}${rounded}%${windowNote}`];
  }

  function compact(bundle){
    return bundle?{provider:bundle.provider,providerVersion:bundle.providerVersion,year:bundle.year,preferredRollingYears:bundle.preferredRollingYears??bundle.rollingYears,availableRollingYears:bundle.availableRollingYears||[bundle.rollingYears],rowCount:bundle.rowCount,fallbackRowCount:bundle.fallbackRowCount||0,fallbackVenues:bundle.fallbackVenues||[],requestCount:bundle.requestCount||null,unresolvedVenues:bundle.unresolvedVenues||[],sourceUrls:bundle.sourceUrls||[bundle.sourceUrl].filter(Boolean)}:null;
  }

  const api={VERSION,PROVIDER,PREFERRED_ROLLING_YEARS,FALLBACK_ROLLING_YEARS,buildUrl,parseHtml,mergeBundles,getForVenue,conditionLines,compact,normalizeVenue,canonicalVenue};
  if(typeof window!=='undefined')window.MODEL_SAVANT_PARK_CORE=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})();

