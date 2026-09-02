const statusEl = document.getElementById("status");
const sendBtn = document.getElementById("send");

sendBtn.addEventListener("click", function () {
  statusEl.textContent = "Sending…";
  sendBtn.disabled = true;
  chrome.runtime.sendMessage({ type: "INGEST_TAB" }, function (result) {
    sendBtn.disabled = false;
    if (chrome.runtime.lastError) {
      statusEl.textContent = chrome.runtime.lastError.message;
      return;
    }
    if (!result || !result.ok) {
      statusEl.textContent = (result && result.error) || "Request failed";
      return;
    }
    const body = result.body;
    const status = body && body.status ? body.status : "ok";
    statusEl.textContent = status;
  });
});
