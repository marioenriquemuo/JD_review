const statusEl = document.getElementById("status");
const sendBtn = document.getElementById("send");
const pdfBtn = document.getElementById("pdf");
const resumeBtn = document.getElementById("resume");
const letterBtn = document.getElementById("letter");

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
      "Needs Context saved.\n1) Fill Candidate Answers in Notion\n2) Click Continue Phase 2 (any tab is fine).\n3) After Ready to Apply, set Status to Write Cover Letter, then click Write cover letter.";
    if (who) line = who + "\n" + line;
    return line;
  }
  if (status === "not_found") {
    return (
      body.message ||
      "No Notion row found. Click Send job on the job posting first."
    );
  }
  if (status === "ready_to_apply") {
    const company = body.company || "";
    const title = body.job_title || "";
    const who = [company, title].filter(Boolean).join(" — ");
    let line = "Ready to Apply.";
    if (who) line = who + "\n" + line;
    if (body.cv_path) line += "\nCV: " + body.cv_path;
    if (body.letter_path) line += "\nLetter: " + body.letter_path;
    if (!body.letter_path) {
      line += "\nSet Notion Status to Write Cover Letter (one row only), then click Write cover letter.";
    }
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

function setBusy(busy, label) {
  sendBtn.disabled = busy;
  pdfBtn.disabled = busy;
  resumeBtn.disabled = busy;
  if (letterBtn) letterBtn.disabled = busy;
  if (busy) statusEl.textContent = label || "Working…";
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
    (result.body.status === "needs_context" ||
      result.body.status === "duplicate" ||
      result.body.status === "ready_to_apply")
  ) {
    rememberResume(result.body);
  }
  statusEl.textContent = formatStatus(result.body);
}

sendBtn.addEventListener("click", function () {
  setBusy(true, "Scoring…");
  chrome.runtime.sendMessage({ type: "INGEST_TAB" }, function (result) {
    setBusy(false);
    handleIngestResult(result);
  });
});

pdfBtn.addEventListener("click", function () {
  chrome.tabs.create({ url: chrome.runtime.getURL("upload.html") });
});

resumeBtn.addEventListener("click", function () {
  setBusy(true, "Generating CV…");
  chrome.runtime.sendMessage({ type: "RESUME_TAB" }, function (result) {
    setBusy(false);
    handleResumeResult(result);
  });
});

letterBtn.addEventListener("click", function () {
  setBusy(true, "Generating letter…");
  chrome.runtime.sendMessage({ type: "LETTER_TAB" }, function (result) {
    setBusy(false);
    handleResumeResult(result);
  });
});

function handleResumeResult(result) {
  if (chrome.runtime.lastError) {
    statusEl.textContent = chrome.runtime.lastError.message;
    return;
  }
  if (!result || !result.ok) {
    statusEl.textContent = (result && result.error) || "Request failed";
    return;
  }
  if (result.body && result.body.status === "ready_to_apply") {
    rememberResume(result.body);
  }
  statusEl.textContent = formatStatus(result.body);
}
