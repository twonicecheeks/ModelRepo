(() => {
  'use strict';
  const VERSION='0.2';
  const STORE_KEY='model_table_probe_v02_store';
  const ACTIVE_KEY='model_table_probe_v02_active';
  const MAX_EVENTS=120;
  const MAX_KEYS=50;
  const MAX_TEXT=2_500_000;
  const nowIso=()=>new Date().toISOString();
  const safeParse=s=>{try{return JSON.parse(s)}catch{return null}};
  function readStore(){
    const x=safeParse(sessionStorage.getItem(STORE_KEY)||'');
    return x&&typeof x==='object'?x:{version:VERSION,startedAt:null,events:[],notes:[]};
  }
  function writeStore(x){try{sessionStorage.setItem(STORE_KEY,JSON.stringify(x));}catch{}}
  function shape(value,depth=0){
    if(depth>2)return typeof value;
    if(Array.isArray(value))return {type:'array',length:value.length,item:value.length?shape(value[0],depth+1):null};
    if(value&&typeof value==='object'){
      const keys=Object.keys(value).slice(0,MAX_KEYS), sample={};
      for(const k of keys.slice(0,15)){
        const v=value[k];
        sample[k]=v==null?String(v):Array.isArray(v)?`array(${v.length})`:typeof v==='object'?`object(${Object.keys(v).length})`:typeof v;
      }
      return {type:'object',keys,sample};
    }
    return {type:typeof value};
  }
  function textSummary(txt){
    const terms=['strikeouts','pitcher outs','earned runs','hits allowed','pitcher walks','playerid','matchid','eventid','sportsbook','odds','line','props'];
    const low=txt.toLowerCase(), termCounts={};
    for(const t of terms){let n=0,p=0;while((p=low.indexOf(t,p))>=0){n++;p+=t.length;if(n>500)break;}termCounts[t]=n;}
    const playerIds=[...txt.matchAll(/images\/players\/(\d+)/g)].map(m=>m[1]);
    const teamIds=[...txt.matchAll(/images\/teams\/(\d+)/g)].map(m=>m[1]);
    const snippets=[];
    for(const term of ['playerId','sportsbook','strikeouts','Pitcher Outs','Earned Runs','Hits Allowed','Pitcher Walks']){
      const i=txt.indexOf(term);if(i>=0)snippets.push(txt.slice(Math.max(0,i-100),Math.min(txt.length,i+260)).replace(/\s+/g,' '));
      if(snippets.length>=6)break;
    }
    return {bodyChars:txt.length,termCounts,uniquePlayerAssetIds:[...new Set(playerIds)].slice(0,80),uniqueTeamAssetIds:[...new Set(teamIds)].slice(0,40),snippets};
  }
  function pushEvent(ev){
    const st=readStore();st.events=Array.isArray(st.events)?st.events:[];st.events.push({...ev,capturedAt:nowIso()});
    if(st.events.length>MAX_EVENTS)st.events=st.events.slice(-MAX_EVENTS);writeStore(st);
  }
  async function summarizeResponse(resp,meta){
    try{
      const ct=resp.headers?.get?.('content-type')||'';
      const out={...meta,status:resp.status,contentType:ct,contentLength:resp.headers?.get?.('content-length')||null};
      const relevant=/json|graphql|text\/x-component|text\/plain|text\/html/i.test(ct) || /propsmadness\.com\/mlb\/props/i.test(String(meta.url||''));
      if(relevant){
        const txt=await resp.clone().text();out.bodyChars=txt.length;
        if(txt.length<=MAX_TEXT){
          if(/json|graphql/i.test(ct)){const j=safeParse(txt);if(j)out.jsonShape=shape(j);else out.jsonParse=false;}
          out.textSummary=textSummary(txt);
        }else out.textSkipped=`>${MAX_TEXT}`;
      }
      pushEvent(out);
    }catch(e){pushEvent({...meta,error:String(e)});}
  }
  function patch(){
    if(window.__MODEL_TABLE_PROBE_V02_PATCHED__)return;
    window.__MODEL_TABLE_PROBE_V02_PATCHED__=true;
    const nativeFetch=window.fetch;
    if(typeof nativeFetch==='function'){
      window.fetch=async function(...args){
        const req=args[0],url=typeof req==='string'?req:req?.url,method=(args[1]?.method||req?.method||'GET').toUpperCase(),started=performance.now();
        const resp=await nativeFetch.apply(this,args);
        summarizeResponse(resp,{transport:'fetch',url:String(url||''),method,durationMs:Math.round(performance.now()-started)});
        return resp;
      };
    }
    const XHR=window.XMLHttpRequest;
    if(XHR?.prototype){
      const open=XHR.prototype.open,send=XHR.prototype.send;
      XHR.prototype.open=function(method,url,...rest){this.__modelProbeV02={method:String(method||'GET').toUpperCase(),url:String(url||'')};return open.call(this,method,url,...rest);};
      XHR.prototype.send=function(body){const started=performance.now();this.addEventListener('loadend',()=>{
        try{const ct=this.getResponseHeader('content-type')||'',ev={transport:'xhr',url:this.__modelProbeV02?.url||'',method:this.__modelProbeV02?.method||'GET',status:this.status,contentType:ct,durationMs:Math.round(performance.now()-started)};
          if(typeof this.responseText==='string'&&this.responseText.length<=MAX_TEXT){ev.bodyChars=this.responseText.length;ev.textSummary=textSummary(this.responseText);if(/json|graphql/i.test(ct)){const j=safeParse(this.responseText);if(j)ev.jsonShape=shape(j);}}
          pushEvent(ev);
        }catch(e){pushEvent({transport:'xhr',error:String(e)});}
      },{once:true});return send.call(this,body);};
    }
    const st=readStore();st.startedAt=st.startedAt||nowIso();st.notes=Array.from(new Set([...(st.notes||[]),'v0.2 main-world capture active; summaries only, no full response bodies retained.']));writeStore(st);
  }
  window.__MODEL_TABLE_PROBE_V02_START__=()=>{sessionStorage.setItem(ACTIVE_KEY,'1');patch();return true;};
  window.__MODEL_TABLE_PROBE_V02_READ__=()=>readStore();
  window.__MODEL_TABLE_PROBE_V02_CLEAR__=()=>{sessionStorage.removeItem(STORE_KEY);return true;};
  if(sessionStorage.getItem(ACTIVE_KEY)==='1')patch();
})();
