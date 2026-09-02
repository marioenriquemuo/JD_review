const DEFAULT_WEBHOOK = "http://localhost:5678/webhook/job-ingest";

const input = document.getElementById("webhookUrl");
const statusEl = document.getElementById("status");

chrome.storage.sync.get({ webhookUrl: DEFAULT_WEBHOOK }, function (stored) {
  input.value = stored.webhookUrl || DEFAULT_WEBHOOK;
});

document.getElementById("save").addEventListener("click", function () {
  const webhookUrl = input.value.trim() || DEFAULT_WEBHOOK;
  chrome.storage.sync.set({ webhookUrl: webhookUrl }, function () {
    statusEl.textContent = "Saved.";
  });
});
