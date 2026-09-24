const DEFAULT_WEBHOOK = "http://localhost:5678/webhook/job-ingest";

const input = document.getElementById("webhookUrl");
const statusEl = document.getElementById("status");

browser.storage.sync.get({ webhookUrl: DEFAULT_WEBHOOK }).then(function (stored) {
  input.value = stored.webhookUrl || DEFAULT_WEBHOOK;
});

document.getElementById("save").addEventListener("click", function () {
  const webhookUrl = input.value.trim() || DEFAULT_WEBHOOK;
  browser.storage.sync.set({ webhookUrl: webhookUrl }).then(function () {
    statusEl.textContent = "Saved.";
  });
});
