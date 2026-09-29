const DEFAULT_WEBHOOK = "http://localhost:5678/webhook/job-ingest";

function asError(err) {
  return { ok: false, error: String(err && err.message ? err.message : err) };
}

// ponytail: storage.session heartbeat. Firefox kills this event page after 30s idle, and an open fetch does not count. onChanged is what resets the timer (bug 1851373).
browser.storage.session.onChanged.addListener(function () {});

function keepAlive(promise) {
  const key = "keepAlive";
  function beat() {
    browser.storage.session.set({ [key]: Date.now() }).catch(function () {});
  }
  beat();
  const timer = setInterval(beat, 10000);
  function stop() {
    clearInterval(timer);
    browser.storage.session.remove(key).catch(function () {});
  }
  return promise.then(function (result) {
    stop();
    return result;
  }, function (err) {
    stop();
    throw err;
  });
}

browser.runtime.onMessage.addListener(function (message) {
  if (!message || !message.type) return;
  let run = null;
  if (message.type === "INGEST_TAB") run = ingestActiveTab();
  else if (message.type === "INGEST_PDF") run = ingestPdf(message.filename, message.bytes);
  else if (message.type === "RESUME_TAB") run = resumeActiveTab(false);
  else if (message.type === "LETTER_TAB") run = resumeActiveTab(true);
  if (!run) return;
  return keepAlive(run).catch(asError);
});

function resumeUrlFromIngest(ingestUrl) {
  const url = String(ingestUrl || DEFAULT_WEBHOOK);
  if (url.indexOf("job-ingest") !== -1) {
    return url.split("job-ingest").join("job-resume");
  }
  if (url.endsWith("/")) return url + "job-resume";
  return url.replace(/\/[^/]*$/, "/job-resume");
}

async function ingestActiveTab() {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  if (!tab || tab.id == null) {
    throw new Error("No active tab");
  }
  const results = await browser.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["extract.js"]
  });
  const payload = results && results[0] && results[0].result;
  if (!payload || !payload.html) {
    const inline = await browser.scripting.executeScript({
      target: { tabId: tab.id },
      func: function () {
        return { url: location.href, html: document.body ? document.body.innerHTML : "" };
      }
    });
    return postIngest(inline[0].result);
  }
  return postIngest(payload);
}

async function resumeActiveTab(writeLetter) {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  const stored = await browser.storage.sync.get({ webhookUrl: DEFAULT_WEBHOOK });
  const local = await browser.storage.local.get({ lastResume: null });
  const last = local.lastResume || {};
  const resumeUrl = resumeUrlFromIngest(stored.webhookUrl || DEFAULT_WEBHOOK);
  const body = {
    url: (tab && tab.url) || last.url || "",
    page_id: last.page_id || "",
    write_letter: !!writeLetter
  };
  if (!body.page_id && !body.url) {
    throw new Error("No saved application. Send the job first.");
  }
  const response = await fetch(resumeUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const text = await response.text();
  let parsed = text;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    parsed = { raw: text };
  }
  if (!response.ok) {
    return { ok: false, error: "HTTP " + response.status, body: parsed };
  }
  return { ok: true, body: parsed };
}

function bytesToB64(bytes) {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []);
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < arr.length; i += chunk) {
    bin += String.fromCharCode.apply(null, arr.subarray(i, i + chunk));
  }
  return btoa(bin);
}

function bytesToHex(buffer) {
  const arr = new Uint8Array(buffer);
  let hex = "";
  for (let i = 0; i < arr.length; i++) {
    hex += ("0" + arr[i].toString(16)).slice(-2);
  }
  return hex;
}

async function ingestPdf(filename, byteList) {
  const bytes = new Uint8Array(byteList || []);
  if (!bytes.length) {
    throw new Error("PDF file is empty");
  }
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  const url = "https://jd-flow.local/pdf/" + bytesToHex(hash);
  return postIngest({
    url: url,
    pdf_b64: bytesToB64(bytes),
    filename: filename || "job.pdf"
  });
}

async function postIngest(payload) {
  const stored = await browser.storage.sync.get({ webhookUrl: DEFAULT_WEBHOOK });
  const webhookUrl = stored.webhookUrl || DEFAULT_WEBHOOK;
  const reqBody = payload.pdf_b64
    ? { url: payload.url, pdf_b64: payload.pdf_b64, filename: payload.filename || "" }
    : { url: payload.url, html: payload.html };
  const response = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(reqBody)
  });
  const text = await response.text();
  let parsed = text;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    parsed = { raw: text };
  }
  if (!response.ok) {
    return { ok: false, error: "HTTP " + response.status, body: parsed };
  }
  return { ok: true, body: parsed };
}
