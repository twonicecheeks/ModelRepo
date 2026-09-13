(() => {
  "use strict";

  const VERSION = "OMEGA_PM_NFL_TA_EXACT_CAPTURE_0.17.5";
  const startedAt = new Date().toISOString();
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const norm = s => String(s || "").replace(/\s+/g, " ").trim();
  const safeText = s => String(s || "").slice(0, 250000);

  if (!location.pathname.startsWith("/nfl")) {
    console.error("OMEGA 0.17.5 FAIL: open https://propsmadness.com/nfl before running this probe.");
    return;
  }

  const output = {
    schemaVersion: VERSION,
    startedAt,
    initialUrl: location.href,
    pageTitle: document.title,
    candidateControls: [],
    selectedControl: null,
    apiEvents: [],
    performanceBefore: [],
    performanceAfter: [],
    domBefore: null,
    domAfter: null,
    notes: [],
    exportedAt: null
  };

  function resourceSnapshot() {
    return performance.getEntriesByType("resource").map(x => ({
      name: x.name,
      initiatorType: x.initiatorType,
      duration: x.duration,
      transferSize: x.transferSize
    }));
  }

  function domSnapshot(label) {
    const main = document.querySelector("main");
    const body = main || document.body;
    const clickables = [...document.querySelectorAll("button,[role='button'],a")]
      .filter(el => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      })
      .map(el => norm(el.innerText || el.textContent))
      .filter(Boolean);

    const exact = [...document.querySelectorAll("button,[role='button'],a")]
      .filter(el => norm(el.innerText || el.textContent) === "Tckl+Ast")
      .map(el => ({
        tag: el.tagName,
        role: el.getAttribute("role"),
        href: el.href || null,
        className: String(el.className || "").slice(0, 500),
        outerHTML: String(el.outerHTML || "").slice(0, 5000),
        inMain: !!el.closest("main")
      }));

    return {
      capturedAt: new Date().toISOString(),
      label,
      url: location.href,
      exactTACandidates: exact,
      clickables,
      mainText: safeText(body ? body.innerText : "")
    };
  }

  const originalFetch = window.fetch;
  window.fetch = async function(...args) {
    const req = args[0];
    const url = typeof req === "string" ? req : (req && req.url) || "";
    const method = (args[1] && args[1].method) || (req && req.method) || "GET";
    const res = await originalFetch.apply(this, args);
    try {
      const abs = new URL(url, location.href);
      if (abs.origin === location.origin && abs.pathname.startsWith("/api/")) {
        const clone = res.clone();
        const ct = clone.headers.get("content-type") || "";
        let responseData = null, responseText = null;
        if (ct.includes("application/json")) {
          try { responseData = await clone.json(); } catch (_) {}
        } else {
          try { responseText = safeText(await clone.text()); } catch (_) {}
        }
        output.apiEvents.push({
          capturedAt: new Date().toISOString(),
          transport: "fetch",
          method: String(method).toUpperCase(),
          url: abs.href,
          status: res.status,
          contentType: ct,
          responseData,
          responseText
        });
      }
    } catch (_) {}
    return res;
  };

  const XHROpen = XMLHttpRequest.prototype.open;
  const XHRSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.__omegaMethod = method;
    this.__omegaUrl = url;
    return XHROpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function(...args) {
    this.addEventListener("load", function() {
      try {
        const abs = new URL(this.__omegaUrl, location.href);
        if (abs.origin === location.origin && abs.pathname.startsWith("/api/")) {
          const ct = this.getResponseHeader("content-type") || "";
          let responseData = null, responseText = null;
          if (ct.includes("application/json")) {
            try { responseData = JSON.parse(this.responseText); } catch (_) {}
          } else {
            responseText = safeText(this.responseText);
          }
          output.apiEvents.push({
            capturedAt: new Date().toISOString(),
            transport: "xhr",
            method: String(this.__omegaMethod || "GET").toUpperCase(),
            url: abs.href,
            status: this.status,
            contentType: ct,
            responseData,
            responseText
          });
        }
      } catch (_) {}
    });
    return XHRSend.apply(this, args);
  };

  function downloadCapture() {
    output.exportedAt = new Date().toISOString();
    output.finalUrl = location.href;
    output.apiEventCount = output.apiEvents.length;
    const json = JSON.stringify(output, null, 2);
    const blob = new Blob([json], {type: "application/json"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const stamp = new Date().toISOString().replace(/[-:.]/g, "").replace("Z", "Z");
    a.download = `OMEGA_0175_PROPSMADNESS_NFL_TA_EXACT_CAPTURE_${stamp}.json`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 2000);
    console.log("OMEGA 0.17.5 PASS: capture downloaded.", {
      apiEvents: output.apiEvents.length,
      finalUrl: location.href
    });
  }

  async function run() {
    output.performanceBefore = resourceSnapshot();
    output.domBefore = domSnapshot("before_exact_ta_click");

    const all = [...document.querySelectorAll("button,[role='button'],a")]
      .filter(el => norm(el.innerText || el.textContent) === "Tckl+Ast")
      .filter(el => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      });

    output.candidateControls = all.map(el => ({
      tag: el.tagName,
      role: el.getAttribute("role"),
      href: el.href || null,
      inMain: !!el.closest("main"),
      outerHTML: String(el.outerHTML || "").slice(0, 5000)
    }));

    // Strong preference: exact visible non-anchor control inside MAIN.
    let target = all.find(el => el.closest("main") && el.tagName !== "A");
    if (!target) target = all.find(el => el.tagName !== "A");
    if (!target) {
      // Allow an anchor only if it stays on /nfl.
      target = all.find(el => {
        if (el.tagName !== "A" || !el.href) return false;
        try {
          const u = new URL(el.href, location.href);
          return u.origin === location.origin && u.pathname.startsWith("/nfl");
        } catch (_) { return false; }
      });
    }

    if (!target) {
      output.notes.push("FAIL: exact visible Tckl+Ast control not safely clickable");
      output.performanceAfter = resourceSnapshot();
      output.domAfter = domSnapshot("no_safe_exact_ta_control");
      downloadCapture();
      return;
    }

    output.selectedControl = {
      tag: target.tagName,
      role: target.getAttribute("role"),
      href: target.href || null,
      inMain: !!target.closest("main"),
      outerHTML: String(target.outerHTML || "").slice(0, 5000)
    };

    console.log("OMEGA 0.17.5: clicking exact Tckl+Ast control", output.selectedControl);
    target.scrollIntoView({block: "center"});
    target.click();

    await sleep(12000);

    output.performanceAfter = resourceSnapshot();
    output.domAfter = domSnapshot("after_exact_ta_click_12s");

    if (!location.pathname.startsWith("/nfl")) {
      output.notes.push("WARNING: exact Tckl+Ast click navigated away from /nfl");
    } else {
      output.notes.push("PASS: remained on /nfl after exact Tckl+Ast click");
    }

    downloadCapture();
  }

  run().catch(err => {
    output.notes.push("EXCEPTION: " + String(err && err.stack || err));
    try { downloadCapture(); } catch (_) {}
  });
})();