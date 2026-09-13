(() => {
  "use strict";
  const VERSION = "OMEGA_NFL_OFFICIAL_INACTIVES_CAPTURE_0.19.0";
  const TEAM_GROUPS = {
    CARDINALS:["ARIZONA CARDINALS","CARDINALS"], FALCONS:["ATLANTA FALCONS","FALCONS"],
    RAVENS:["BALTIMORE RAVENS","RAVENS"], BILLS:["BUFFALO BILLS","BILLS"],
    PANTHERS:["CAROLINA PANTHERS","PANTHERS"], BEARS:["CHICAGO BEARS","BEARS"],
    BENGALS:["CINCINNATI BENGALS","BENGALS"], BROWNS:["CLEVELAND BROWNS","BROWNS"],
    COWBOYS:["DALLAS COWBOYS","COWBOYS"], BRONCOS:["DENVER BRONCOS","BRONCOS"],
    LIONS:["DETROIT LIONS","LIONS"], PACKERS:["GREEN BAY PACKERS","PACKERS"],
    TEXANS:["HOUSTON TEXANS","TEXANS"], COLTS:["INDIANAPOLIS COLTS","COLTS"],
    JAGUARS:["JACKSONVILLE JAGUARS","JAGUARS"], CHIEFS:["KANSAS CITY CHIEFS","CHIEFS"],
    RAIDERS:["LAS VEGAS RAIDERS","RAIDERS"], CHARGERS:["LOS ANGELES CHARGERS","CHARGERS"],
    RAMS:["LOS ANGELES RAMS","RAMS"], DOLPHINS:["MIAMI DOLPHINS","DOLPHINS"],
    VIKINGS:["MINNESOTA VIKINGS","VIKINGS"], PATRIOTS:["NEW ENGLAND PATRIOTS","PATRIOTS"],
    SAINTS:["NEW ORLEANS SAINTS","SAINTS"], GIANTS:["NEW YORK GIANTS","GIANTS"],
    JETS:["NEW YORK JETS","JETS"], EAGLES:["PHILADELPHIA EAGLES","EAGLES"],
    STEELERS:["PITTSBURGH STEELERS","STEELERS"], SEAHAWKS:["SEATTLE SEAHAWKS","SEAHAWKS"],
    NINERS:["SAN FRANCISCO 49ERS","49ERS","NINERS"], BUCCANEERS:["TAMPA BAY BUCCANEERS","BUCCANEERS","BUCS"],
    TITANS:["TENNESSEE TITANS","TITANS"], COMMANDERS:["WASHINGTON COMMANDERS","COMMANDERS"]
  };
  const norm=s=>String(s||"").replace(/\s+/g," ").trim();
  const upper=s=>norm(s).toUpperCase();
  const visible=el=>{
    const r=el.getBoundingClientRect(),cs=getComputedStyle(el);
    return r.width>0&&r.height>0&&cs.display!=="none"&&cs.visibility!=="hidden";
  };
  if (!/(^|\.)nfl\.com$/i.test(location.hostname)) {
    console.error("OMEGA 0.19.0 FAIL: run only on an official nfl.com inactives page/article.");
    return;
  }
  const pageText=norm(document.body?.innerText||"");
  if (!/INACTIVE/i.test(pageText)) {
    console.error("OMEGA 0.19.0 FAIL: this NFL.com page does not appear to contain inactive-report content.");
    return;
  }

  function headingLevel(el) {
    const m=/^H([1-6])$/.exec(el.tagName||"");
    return m?Number(m[1]):99;
  }
  function teamForText(txt) {
    const u=upper(txt);
    for (const [canon,aliases] of Object.entries(TEAM_GROUPS)) {
      if (aliases.some(a=>u===a || u===`${a} INACTIVES` || u===`INACTIVES ${a}`)) return canon;
    }
    return null;
  }
  function cleanItem(txt) {
    let s=norm(txt).replace(/^[•·\-\u2022]\s*/,"");
    s=s.replace(/^[A-Z]{1,4}\s+(?=[A-Z][a-z])/, ""); // position prefix such as LB
    return s;
  }
  function plausiblePlayer(txt) {
    const s=cleanItem(txt);
    if (!s || s.length>90) return false;
    if (/^(WHERE|WHEN|TV|WATCH|STREAM|INACTIVES?|ACTIVE|RELATED CONTENT)\b/i.test(s)) return false;
    if (/\b(ET|PM|AM|STADIUM|NETWORK|WEEK|SEASON)\b/i.test(s) && !/^[A-Z]{1,4}\s+[A-Z]/.test(txt)) return false;
    const words=s.match(/[A-Za-zÀ-ÖØ-öø-ÿ'’.-]+/g)||[];
    return words.length>=2 && words.length<=6;
  }
  function followingItems(h) {
    const out=[];
    const level=headingLevel(h);
    let n=h.nextElementSibling,guard=0;
    while (n && guard++<20) {
      if (/^H[1-6]$/.test(n.tagName||"") && headingLevel(n)<=level) break;
      const lis=[...n.querySelectorAll?.("li")||[]].filter(visible).map(x=>norm(x.innerText||x.textContent));
      if (n.tagName==="LI" && visible(n)) lis.unshift(norm(n.innerText||n.textContent));
      const ps=(n.matches?.("p")&&visible(n))?[norm(n.innerText||n.textContent)]:[];
      for (const t of [...lis,...ps]) if (plausiblePlayer(t)) out.push(cleanItem(t));
      n=n.nextElementSibling;
    }
    return [...new Set(out)];
  }
  function cardItems(h) {
    let el=h;
    for (let depth=0;depth<6 && el;depth++,el=el.parentElement) {
      const txt=norm(el.innerText||"");
      if (txt.length<40 || txt.length>3500) continue;
      const lis=[...el.querySelectorAll("li")].filter(visible).map(x=>norm(x.innerText||x.textContent));
      const cand=[...new Set(lis.filter(plausiblePlayer).map(cleanItem))];
      if (cand.length>=2) return cand;
    }
    return [];
  }

  const headings=[...document.querySelectorAll("h1,h2,h3,h4,h5,h6,[role='heading']")].filter(visible);
  const sections=[];
  for (const h of headings) {
    const team=teamForText(h.innerText||h.textContent);
    if (!team) continue;
    let items=followingItems(h);
    if (items.length<2) items=cardItems(h);
    sections.push({
      canonicalTeam:team,
      heading: norm(h.innerText||h.textContent),
      headingTag:h.tagName,
      inactiveCandidates:items,
      candidateCount:items.length
    });
  }

  // Fallback: exact team text elements inside cards if semantic headings are absent.
  if (!sections.length) {
    const els=[...document.querySelectorAll("div,span,p,strong")].filter(visible);
    for (const el of els) {
      const team=teamForText(el.innerText||el.textContent);
      if (!team) continue;
      const items=cardItems(el);
      if (items.length>=2) sections.push({
        canonicalTeam:team,heading:norm(el.innerText||el.textContent),
        headingTag:el.tagName,inactiveCandidates:items,candidateCount:items.length
      });
    }
  }

  const out={
    schemaVersion:VERSION,
    capturedAt:new Date().toISOString(),
    sourceUrl:location.href,
    sourceTitle:document.title,
    pageText:pageText.slice(0,250000),
    pageSaysCheckBackSoon:/PLEASE CHECK BACK SOON/i.test(pageText),
    teamSections:sections,
    teamSectionCount:sections.length,
    credentialFieldsCaptured:0
  };

  const blob=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download=`OMEGA_0190_NFL_OFFICIAL_INACTIVES_${new Date().toISOString().replace(/[-:.]/g,"")}.json`;
  document.body.appendChild(a);a.click();
  setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove()},2000);
  console.log("OMEGA 0.19.0 official inactives capture", {
    teamSections:sections.length,
    checkBackSoon:out.pageSaysCheckBackSoon,
    source:location.href
  });
})();