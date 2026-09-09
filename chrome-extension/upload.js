const statusEl = document.getElementById("status");
const pdfFile = document.getElementById("pdf-file");

function formatStatus(body) {
  if (!body || typeof body !== "object") {
    return "ok";
  }
  const status = body.status || "ok";
  if (status === "duplicate") {
    return (
      body.message ||
      "Already filed. Click Continue Phase 2 to generate from Candidate Answers."
    );
  }
  if (status === "skipped") {
    const fit = body.fit_score != null ? body.fit_score : "?";
    const company = body.company || "";
    const title = body.job_title || "";
    const who = [company, title].filter(Boolean).join(" — ");
    const rationale = body.rationale || "";
    let line = "Skipped (fit " + fit + ").";
    if (who) line += " " + who;
    if (rationale) line += "\n" + rationale;
    return line;
  }
  if (status === "needs_context") {
    const company = body.company || "";
    const title = body.job_title || "";
    const who = [company, title].filter(Boolean).join(" — ");
    let line =
      "Needs Context saved.\n1) Fill Candidate Answers in Notion\n2) Click Continue Phase 2 (any tab is fine).";
    if (who) line = who + "\n" + line;
    return line;
  }
  return status;
}

function rememberResume(body) {
  if (!body || !body.page_id) return;
  chrome.storage.local.set({
    lastResume: {
      page_id: String(body.page_id).replace(/-/g, "").toLowerCase(),
      url: body.url || "",
      company: body.company || "",
      job_title: body.job_title || "",
      saved_at: Date.now()
    }
  });
}

function handleIngestResult(result) {
  if (chrome.runtime.lastError) {
    statusEl.textContent = chrome.runtime.lastError.message;
    return;
  }
  if (!result || !result.ok) {
    statusEl.textContent = (result && result.error) || "Request failed";
    return;
  }
  if (
    result.body &&
    (result.body.status === "needs_context" || result.body.status === "duplicate")
  ) {
    rememberResume(result.body);
  }
  statusEl.textContent = formatStatus(result.body);
}

pdfFile.addEventListener("change", function () {
  const file = pdfFile.files && pdfFile.files[0];
  pdfFile.value = "";
  if (!file) return;
  pdfFile.disabled = true;
  statusEl.textContent = "Scoring…";
  const reader = new FileReader();
  reader.onerror = function () {
    pdfFile.disabled = false;
    statusEl.textContent = "Could not read PDF";
  };
  reader.onload = function () {
    const bytes = new Uint8Array(reader.result);
    chrome.runtime.sendMessage(
      { type: "INGEST_PDF", filename: file.name, bytes: Array.from(bytes) },
      function (result) {
        pdfFile.disabled = false;
        handleIngestResult(result);
      }
    );
  };
  reader.readAsArrayBuffer(file);
});
