const DEFAULT_WEBHOOK = "http://localhost:5678/webhook/job-ingest";

chrome.runtime.onMessage.addListener(function (message, _sender, sendResponse) {
  if (!message || message.type !== "INGEST_TAB") {
    return;
  }
  ingestActiveTab()
    .then(sendResponse)
    .catch(function (err) {
      sendResponse({ ok: false, error: String(err && err.message ? err.message : err) });
    });
  return true;
});

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
    return postPayload(inline[0].result);
  }
  return postPayload(payload);
}

async function postPayload(payload) {
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
