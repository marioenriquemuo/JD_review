const DEFAULT_WEBHOOK = "http://localhost:5678/webhook/job-ingest";

chrome.runtime.onMessage.addListener(function (message, _sender, sendResponse) {
  if (!message) return;
  if (message.type === "INGEST_TAB") {
    ingestActiveTab()
      .then(sendResponse)
      .catch(function (err) {
        sendResponse({ ok: false, error: String(err && err.message ? err.message : err) });
      });
    return true;
  }
  if (message.type === "RESUME_TAB") {
    resumeActiveTab()
      .then(sendResponse)
      .catch(function (err) {
        sendResponse({ ok: false, error: String(err && err.message ? err.message : err) });
      });
    return true;
  }
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
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || tab.id == null) {
    throw new Error("No active tab");
  }
  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["extract.js"]
  });
  const payload = results && results[0] && results[0].result;
  if (!payload || !payload.html) {
    const inline = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: function () {
        return { url: location.href, html: document.body ? document.body.innerHTML : "" };
      }
    });
    return postIngest(inline[0].result);
  }
  return postIngest(payload);
}

async function resumeActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const stored = await chrome.storage.sync.get({ webhookUrl: DEFAULT_WEBHOOK });
  const local = await chrome.storage.local.get({ lastResume: null });
  const last = local.lastResume || {};
  const resumeUrl = resumeUrlFromIngest(stored.webhookUrl || DEFAULT_WEBHOOK);
  const body = {
    url: (tab && tab.url) || last.url || "",
    page_id: last.page_id || ""
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

async function postIngest(payload) {
  const stored = await chrome.storage.sync.get({ webhookUrl: DEFAULT_WEBHOOK });
  const webhookUrl = stored.webhookUrl || DEFAULT_WEBHOOK;
  const response = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: payload.url, html: payload.html })
  });
  const text = await response.text();
  let body = text;
  try {
    body = JSON.parse(text);
  } catch (e) {
    body = { raw: text };
  }
  if (!response.ok) {
    return { ok: false, error: "HTTP " + response.status, body: body };
  }
  return { ok: true, body: body };
}
