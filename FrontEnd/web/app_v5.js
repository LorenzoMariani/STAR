let modules = [];
let moduleNames = [];
let currentRun = null;

let currentRequirements = [];
let requirementReviewStatus = "not_available";

let currentRequestedOutputs = [];
let requestedOutputsReviewStatus = "not_available";
let missionPlanningStatus = "not_available";

let currentMissingInformation = [];
let missingInformationReviewStatus = "not_available";
let assumptionsApproved = false;

let currentWorkflow = [];
let workflowReviewStatus = "not_available";
let workflowApproved = false;

let currentExecutionResults = [];
let executionReviewStatus = "not_available";
let executionApproved = false;
let executionRunning = false;
let executionStopRequested = false;
let activeModuleName = null;

let currentReportManifest = [];
let reportStatus = "not_available";

let allowedRequirementCategories = [
  "mission_objective",
  "payload",
  "orbit",
  "eps",
  "performance",
  "analysis",
  "constraint",
  "general",
];

let allowedRequirementStatuses = [
  "extracted",
  "under_specified",
  "requires_review",
];

let allowedMissingInformationStatuses = [
  "provided",
  "proposed",
  "requires_user_input",
  "expected_from_upstream",
  "not_applicable",
  "approved",
];

let allowedMissingInformationSources = [
  "mission_document",
  "module_registry_default",
  "module_registry_required_input",
  "upstream_module_output",
  "user_reviewed",
  "not_applicable",
];

let allowedWorkflowStatuses = [
  "proposed",
  "ready",
  "requires_review",
  "skipped",
  "stopped",
  "approved",
];

let allowedExecutionStatuses = [
  "pending",
  "running",
  "completed",
  "completed_with_fallback",
  "failed",
  "skipped",
  "skipped_out_of_scope",
  "skipped_blocked",
  "stopped",
  "approved",
];


function applyTheme(theme) {
  const normalizedTheme = theme === "light" ? "light" : "dark";
  document.body.dataset.theme = normalizedTheme;
  localStorage.setItem("star-ui-theme", normalizedTheme);

  const selector = document.getElementById("theme-select");
  if (selector) {
    selector.value = normalizedTheme;
  }
}

function initializeTheme() {
  const savedTheme = localStorage.getItem("star-ui-theme") || "dark";
  applyTheme(savedTheme);
}


function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getElement(id) {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing HTML element with id="${id}"`);
  return element;
}

function setLogs(logs) {
  const logConsole = getElement("log-console");
  logConsole.textContent = (logs || []).join("\n");
  if (logConsole.textContent) logConsole.textContent += "\n";
  logConsole.scrollTop = logConsole.scrollHeight;
}

function appendLog(line) {
  const logConsole = getElement("log-console");
  logConsole.textContent += `${line}\n`;
  logConsole.scrollTop = logConsole.scrollHeight;
}

function addChatMessage(sender, text) {
  const chatBox = getElement("chat-box");
  const div = document.createElement("div");
  div.className = `chat-message ${String(sender).toLowerCase()}`;
  div.innerHTML = `<strong>${escapeHtml(sender)}:</strong> ${escapeHtml(text)}`;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function showFrontendError(error) {
  console.error(error);
  try {
    appendLog(`[FRONTEND ERROR] ${error.message || error}`);
    addChatMessage("STAR", `Frontend error: ${error.message || error}`);
  } catch (_) {}
}

function makeOptions(options, selectedValue) {
  return (options || [])
    .map((option) => {
      const selected = option === selectedValue ? "selected" : "";
      return `<option value="${escapeHtml(option)}" ${selected}>${escapeHtml(option)}</option>`;
    })
    .join("");
}

function updateWorkflowModuleSelect() {
  const selectors = [
    document.getElementById("workflow-add-module-select"),
    document.getElementById("workflow-plus-module-select"),
  ].filter(Boolean);

  selectors.forEach((selector) => {
    const currentValue = selector.value;
    selector.innerHTML = moduleNames
      .map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
      .join("");

    if (currentValue && moduleNames.includes(currentValue)) {
      selector.value = currentValue;
    }
  });
}

function getModuleByName(moduleName) {
  return modules.find((module) => module.module_name === moduleName || module.name === moduleName) || null;
}

function buildWorkflowInputSummaryForModule(module) {
  const inputs = module?.required_inputs || [];
  if (!inputs.length) return "No explicit input declared in module registry.";
  return inputs.map((item) => item.name || "unknown_input").join("; ");
}

function buildWorkflowOutputSummaryForModule(module) {
  const outputs = module?.outputs || [];
  if (!outputs.length) return "No output artifact declared in module registry.";
  return outputs.map((item) => item.artifact_name || item.name || "unknown_output").join("; ");
}

function hasPywebviewApi() {
  return Boolean(window.pywebview && window.pywebview.api);
}

function waitForPywebview(timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    if (hasPywebviewApi()) {
      resolve();
      return;
    }

    let done = false;

    const timer = setTimeout(() => {
      if (!done) {
        reject(new Error("pywebview API was not ready. Start the app using python app_webview.py."));
      }
    }, timeoutMs);

    window.addEventListener(
      "pywebviewready",
      () => {
        done = true;
        clearTimeout(timer);
        resolve();
      },
      { once: true }
    );

    const poll = setInterval(() => {
      if (hasPywebviewApi()) {
        done = true;
        clearTimeout(timer);
        clearInterval(poll);
        resolve();
      }
    }, 100);
  });
}


function updateUploadButtonState(run) {
  const button = document.getElementById("upload-button");
  if (!button) return;
  const loaded = Boolean(run && run.current_run_id && run.input_document_filename);
  button.classList.toggle("loaded", loaded);
  button.classList.toggle("unloaded", !loaded);
  button.title = loaded ? `Loaded: ${run.input_document_filename} (press to upload another document)` : "Upload the mission request document (.docx, .txt, .md)";
}

// Document bar (2026-10-18): after the upload the document is shown below the tabs (type, name, size, words, lines, upload
// time, run and saved copy), with "Show text" (the text STAR read, in a window) and "Replace" (upload another document).
function formatDocumentSize(bytes) {
  if (bytes === null || bytes === undefined) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// v5 (2026-10-18): the document is shown only in the Upload Document tab: the bar in its control panel and the text read
// by STAR in its data panel.
function renderDocumentBar(run) {
  const slot = document.getElementById("star-doc-slot");
  if (!slot) return;
  let bar = document.getElementById("star-doc-bar");
  const doc = run && run.current_run_id && run.input_document_filename ? (run.input_document || {}) : null;
  const uploadToolbar = document.querySelector(".upload-toolbar");   // Select Document + folder note; Replace is in the bar once loaded
  if (uploadToolbar) uploadToolbar.hidden = Boolean(doc);
  renderDocumentText(run, doc);
  if (!doc) {
    if (bar) bar.remove();
    return;
  }
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "star-doc-bar";
    bar.className = "star-doc-bar";
    slot.appendChild(bar);
  }
  const meta = [
    formatDocumentSize(doc.size_bytes),
    doc.words !== undefined ? `${Number(doc.words).toLocaleString("en-US")} words` : null,
    doc.lines !== undefined ? `${Number(doc.lines).toLocaleString("en-US")} lines` : null,
    doc.uploaded_at || null,
    run.current_run_id,
    doc.saved_relative_to_star ? `saved in ${doc.saved_relative_to_star.replace(/[^/]+$/, "")}` : null,
  ].filter(Boolean).join(" · ");
  bar.innerHTML = `
    <div class="star-doc-icon">${escapeHtml(String(doc.type || "FILE").slice(0, 4))}</div>
    <div class="star-doc-main">
      <div class="star-doc-name" title="${escapeHtml(run.input_document_filename)}">${escapeHtml(run.input_document_filename)}<span class="star-doc-ok">&#10003; loaded</span></div>
      <div class="star-doc-meta" title="${escapeHtml(meta)}">${escapeHtml(meta)}</div>
    </div>
    <div class="star-doc-actions">
      <button class="tab-button" type="button" id="star-doc-replace">Replace</button>
    </div>`;
  bar.querySelector("#star-doc-replace").addEventListener("click", uploadDocument);
  const hint = document.getElementById("star-v1-initial-hint");
  if (hint) hint.style.display = "none";
}

let shownDocumentKey = null;

async function renderDocumentText(run, doc) {
  const pre = document.getElementById("star-doc-text");
  const info = document.getElementById("star-doc-text-info");
  if (!pre) return;
  if (!doc) {
    shownDocumentKey = null;
    pre.textContent = "No mission request document loaded yet: press Select Document.";
    if (info) info.textContent = "";
    return;
  }
  const key = `${run.current_run_id}|${run.input_document_filename}`;
  if (key === shownDocumentKey) return;
  shownDocumentKey = key;
  try {
    await waitForPywebview();
    const result = await window.pywebview.api.get_uploaded_document_text();
    if (key !== shownDocumentKey) return;
    pre.textContent = result && result.ok ? result.text : ((result && result.error) || "The document text is not available.");
    if (info) info.textContent = result && result.ok
      ? `${Number(doc.words || 0).toLocaleString("en-US")} words · ${Number(doc.lines || 0).toLocaleString("en-US")} lines` : "";
  } catch (error) {
    shownDocumentKey = null;
    pre.textContent = "The document text is not available.";
  }
}

function renderRun(run) {
  currentRun = run || null;
  updateUploadButtonState(run);
  renderDocumentBar(run);
  const chip = getElement("run-chip");
  const fileCard = getElement("file-card");
  const extractButton = getElement("extract-button");

  if (!run || !run.current_run_id) {
    chip.textContent = "No active run";
    fileCard.innerHTML = "<strong>Input document:</strong> no document loaded yet.";
    extractButton.disabled = true;
    return;
  }

  chip.textContent = run.current_run_id;
  fileCard.innerHTML = `
    <strong>Input document:</strong> ${escapeHtml(run.input_document_filename)}<br>
    <span class="muted">Saved copy:</span> <code>${escapeHtml(run.input_document_saved_relative_path)}</code><br>
    <span class="muted">Output folder:</span> <code>${escapeHtml(run.current_run_path)}</code>
  `;
  extractButton.disabled = false;
}

function renderModules(moduleList) {
  modules = moduleList || [];
  moduleNames = modules.map((module) => module.module_name);

  syncAdaptiveModuleCardSize();

  const grid = getElement("module-grid");
  grid.innerHTML = "";

  updateWorkflowModuleSelect();

  modules.forEach((module) => {
    let status = module.status || "Idle";
    if (status === "Skipped") status = "Idle";
    const owner = module.owner || "unknown";
    const moduleId = module.module_id || module.id || "END-???";
    const moduleName = module.module_name || module.name || "Unnamed module";

    const card = document.createElement("div");
    card.className = "module-card";
    card.dataset.moduleId = moduleId;

    card.innerHTML = `
      <div class="status-light ${escapeHtml(status)}"></div>
      <div class="module-text-block">
        <div class="module-code">${escapeHtml(moduleId)}</div>
        <div class="module-name-small" title="${escapeHtml(moduleName)}">${escapeHtml(moduleName)}</div>
        <div class="module-owner-small">${escapeHtml(owner)}</div>
      </div>
      <div class="status-pill ${escapeHtml(status)}">${escapeHtml(status)}</div>
      ${module.cef_iteration ? `<span class="iter-chip" title="Design loop: the module ran in iteration ${escapeHtml(module.cef_iteration)} of at most ${escapeHtml(module.cef_max || "")}">iter ${escapeHtml(module.cef_iteration)}/${escapeHtml(module.cef_max || "?")}</span>` : ""}
    `;

    grid.appendChild(card);
  });

  syncModuleBayLayout();
}

function renderWorkflowPreviewFromModules() {
  const preview = getElement("workflow-preview");
  if (currentWorkflow.length) {
    preview.innerHTML = currentWorkflow
      .map((step) => `<strong>${escapeHtml(step.module)}</strong>`)
      .join(" → ");
  } else if (moduleNames.length) {
    preview.innerHTML = moduleNames
      .slice(0, 3)
      .map((name) => `<strong>${escapeHtml(name)}</strong>`)
      .join(" → ");
  } else {
    preview.textContent = "No workflow proposed yet.";
  }
}

/* Requirements */
function renderReviewStatus(status) {
  requirementReviewStatus = status || "not_available";

  const reviewCard = getElement("review-card");
  const saveButton = getElement("save-reviewed-button");
  const addButton = getElement("add-requirement-button");
  const analyzeButton = getElement("analyze-missing-button");
  const extractButton = getElement("extract-button");

  let label = "no requirements available yet";
  if (requirementReviewStatus === "not_reviewed") label = "requirements extracted, waiting for user review";
  if (requirementReviewStatus === "edited_not_saved") label = "table edited, not saved yet";
  if (requirementReviewStatus === "reviewed_by_user") label = "reviewed by user and saved";

  reviewCard.innerHTML = `
    <strong>Review status:</strong> ${escapeHtml(label)}
    <br>
    <span class="muted">
      Edited requirements are saved as <code>requirements_reviewed.json</code> and become the active <code>requirements.json</code>.
      Raw extraction is preserved as <code>requirements_extracted.json</code>.
    </span>
  `;

  const extractionAlreadyStarted = requirementReviewStatus !== "not_available" || currentRequirements.length > 0;
  extractButton.disabled = !currentRun || extractionAlreadyStarted;
  saveButton.disabled = currentRequirements.length === 0 || requirementReviewStatus === "reviewed_by_user";
  addButton.disabled = !currentRun;
  analyzeButton.disabled = currentRequirements.length === 0 || requirementReviewStatus === "edited_not_saved";
}

function clearMissingAndWorkflowClientSide() {
  renderMissingInformation([], "not_available", false);
  renderWorkflow([], "not_available", false);
}

function markRequirementsEdited() {
  if (currentRequirements.length === 0) return;
  renderReviewStatus("edited_not_saved");
  clearMissingAndWorkflowClientSide();
}

function renderRequirements(requirements, reviewStatus = "not_available") {
  currentRequirements = requirements || [];
  const tbody = document.querySelector("#requirements-table tbody");
  tbody.innerHTML = "";

  if (!currentRequirements.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">No requirements extracted yet.</td></tr>`;
    renderReviewStatus("not_available");
    return;
  }

  currentRequirements.forEach((req, index) => {
    const row = document.createElement("tr");
    row.dataset.rowIndex = String(index);
    const qualityFlags = Array.isArray(req.quality_flags) ? req.quality_flags.join("|") : "";
    const standardReference = req.standard_reference || "";

    row.innerHTML = `
      <td><input class="cell-input req-id-input" value="${escapeHtml(req.id)}" data-field="id" /></td>
      <td><textarea class="cell-textarea req-text-input" data-field="text">${escapeHtml(req.text)}</textarea></td>
      <td><select class="cell-select req-category-select" data-field="category">${makeOptions(allowedRequirementCategories, req.category)}</select></td>
      <td><select class="cell-select req-status-select" data-field="status">${makeOptions(allowedRequirementStatuses, req.status)}</select></td>
      <td class="actions-cell"><button class="small-action-button delete-requirement-button" type="button">Delete</button></td>
      <td class="hidden-meta" data-field="quality_flags">${escapeHtml(qualityFlags)}</td>
      <td class="hidden-meta" data-field="standard_reference">${escapeHtml(standardReference)}</td>
    `;
    tbody.appendChild(row);
  });

  tbody.querySelectorAll("tr.workflow-row input, tr.workflow-row textarea, tr.workflow-row select").forEach((element) => {
    element.addEventListener("input", markRequirementsEdited);
    element.addEventListener("change", markRequirementsEdited);
  });

  tbody.querySelectorAll(".delete-requirement-button").forEach((button) => {
    button.addEventListener("click", deleteRequirementRow);
  });

  renderReviewStatus(reviewStatus);
}

function collectRequirementsFromTable() {
  const rows = document.querySelectorAll("#requirements-table tbody tr");
  const requirements = [];

  rows.forEach((row) => {
    if (row.querySelector(".empty-cell") || row.classList.contains("workflow-add-row")) return;
    const qualityFlagsRaw = row.querySelector('[data-field="quality_flags"]')?.textContent?.trim() ?? "";
    const qualityFlags = qualityFlagsRaw ? qualityFlagsRaw.split("|").filter(Boolean) : [];
    const standardReference = row.querySelector('[data-field="standard_reference"]')?.textContent?.trim() ?? "";

    requirements.push({
      id: row.querySelector('[data-field="id"]').value.trim(),
      text: row.querySelector('[data-field="text"]').value.trim(),
      category: row.querySelector('[data-field="category"]').value,
      status: row.querySelector('[data-field="status"]').value,
      source: "mission_request_document",
      confidence: null,
      quality_flags: qualityFlags,
      standard_reference: standardReference,
    });
  });

  return requirements;
}

function nextRequirementId(requirements) {
  let maxNumber = 0;

  requirements.forEach((req) => {
    const match = String(req.id || "").match(/REQ-(\d+)/i);
    if (match) {
      maxNumber = Math.max(maxNumber, Number(match[1]));
    }
  });

  return `REQ-${String(maxNumber + 1).padStart(3, "0")}`;
}

function addRequirementRow() {
  if (!currentRun) {
    addChatMessage("STAR", "Upload a mission request document before adding manual requirements.");
    return;
  }

  const requirements = collectRequirementsFromTable();

  requirements.push({
    id: nextRequirementId(requirements),
    text: "The system shall ...",
    category: allowedRequirementCategories.includes("functional") ? "functional" : allowedRequirementCategories[0],
    status: "requires_review",
    source: "user_reviewed",
    confidence: null,
    quality_flags: ["manual_user_entry"],
    standard_reference: "ECSS-E-ST-10-06C-inspired",
  });

  renderRequirements(requirements, "edited_not_saved");
  markRequirementsEdited();
}

function deleteRequirementRow(event) {
  const row = event.target.closest("tr");
  if (!row) return;

  row.remove();
  const requirements = collectRequirementsFromTable();

  if (!requirements.length) {
    renderRequirements([], "not_available");
    clearMissingAndWorkflowClientSide();
    renderReviewStatus("edited_not_saved");
    return;
  }

  renderRequirements(requirements, "edited_not_saved");
  markRequirementsEdited();
}

function validateRequirementsBeforeSave(requirements) {
  if (!requirements.length) return "No requirements are available to save.";

  const ids = new Set();

  for (const req of requirements) {
    if (!req.id) return "One requirement has an empty ID.";
    if (ids.has(req.id)) return `Duplicate requirement ID found: ${req.id}`;
    if (!req.text) return `Requirement ${req.id} has empty text.`;
    if (!allowedRequirementCategories.includes(req.category)) return `Invalid category for ${req.id}: ${req.category}`;
    if (!allowedRequirementStatuses.includes(req.status)) return `Invalid status for ${req.id}: ${req.status}`;
    ids.add(req.id);
  }

  return null;
}

/* Missing information */
function renderMissingReviewStatus(status, approved = false) {
  missingInformationReviewStatus = status || "not_available";
  assumptionsApproved = Boolean(approved);

  const card = getElement("missing-review-card");
  const chip = getElement("assumption-chip");
  const saveButton = getElement("save-missing-button");
  const approveButton = getElement("approve-missing-button");

  let label = "no missing-parameter analysis available yet";
  if (missingInformationReviewStatus === "not_reviewed") label = "missing parameters generated, waiting for user review";
  if (missingInformationReviewStatus === "edited_not_saved") label = "table edited, not saved yet";
  if (missingInformationReviewStatus === "reviewed_by_user") label = "reviewed by user and saved";
  if (missingInformationReviewStatus === "approved_by_user") label = "approved by user";

  chip.textContent = "";

  card.innerHTML = `
    <strong>Review status:</strong> ${escapeHtml(label)}
    <br>
    <span class="muted">
      Reviewed missing parameters are saved as <code>missing_information_reviewed.json</code>.
      Approved assumptions are saved as <code>approved_assumptions.json</code>.
    </span>
  `;

  saveButton.disabled =
    currentMissingInformation.length === 0 ||
    missingInformationReviewStatus === "reviewed_by_user" ||
    assumptionsApproved;

  approveButton.disabled =
    currentMissingInformation.length === 0 ||
    missingInformationReviewStatus === "edited_not_saved" ||
    assumptionsApproved;

  renderWorkflowReviewStatus(workflowReviewStatus, workflowApproved);
}

function markMissingInformationEdited() {
  if (currentMissingInformation.length === 0) return;
  renderMissingReviewStatus("edited_not_saved", false);
  renderWorkflow([], "not_available", false);
}

function renderMissingInformation(items, reviewStatus = "not_available", approved = false) {
  currentMissingInformation = items || [];
  const tbody = document.querySelector("#missing-table tbody");
  tbody.innerHTML = "";

  if (!currentMissingInformation.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">No missing parameters identified yet.</td></tr>`;
    renderMissingReviewStatus("not_available", false);
    return;
  }

  currentMissingInformation.forEach((item, index) => {
    const row = document.createElement("tr");
    row.dataset.rowIndex = String(index);
    row.innerHTML = `
      <td><input class="cell-input mi-parameter" value="${escapeHtml(item.parameter)}" data-field="parameter" /></td>
      <td><select class="cell-select mi-needed" data-field="needed_by">${makeOptions(moduleNames, item.needed_by)}</select></td>
      <td><textarea class="cell-textarea mi-reason" data-field="reason">${escapeHtml(item.reason)}</textarea></td>
      <td><textarea class="cell-textarea mi-value" data-field="proposed_value">${escapeHtml(item.proposed_value)}</textarea></td>
      <td><input class="cell-input mi-unit" value="${escapeHtml(item.unit)}" data-field="unit" /></td>
      <td><select class="cell-select mi-status" data-field="status">${makeOptions(allowedMissingInformationStatuses, item.status)}</select></td>
      <td><select class="cell-select mi-source" data-field="source">${makeOptions(allowedMissingInformationSources, item.source)}</select></td>
      <td class="hidden-meta" data-field="required">${escapeHtml(item.required)}</td>
      <td class="hidden-meta" data-field="assumption_allowed">${escapeHtml(item.assumption_allowed)}</td>
      <td class="hidden-meta" data-field="data_type">${escapeHtml(item.data_type)}</td>
    `;
    tbody.appendChild(row);
  });

  tbody.querySelectorAll("input, textarea, select").forEach((element) => {
    element.addEventListener("input", markMissingInformationEdited);
    element.addEventListener("change", markMissingInformationEdited);
  });

  renderMissingReviewStatus(reviewStatus, approved);
}

function collectMissingInformationFromTable() {
  const rows = document.querySelectorAll("#missing-table tbody tr");
  const items = [];

  rows.forEach((row) => {
    if (row.querySelector(".empty-cell") || row.classList.contains("workflow-add-row")) return;

    const get = (selector) => row.querySelector(selector)?.value?.trim() ?? "";
    const getText = (selector) => row.querySelector(selector)?.textContent?.trim() ?? "";

    items.push({
      parameter: get('[data-field="parameter"]'),
      needed_by: get('[data-field="needed_by"]'),
      reason: get('[data-field="reason"]'),
      proposed_value: get('[data-field="proposed_value"]'),
      unit: get('[data-field="unit"]') || "-",
      status: get('[data-field="status"]'),
      source: get('[data-field="source"]'),
      required: getText('[data-field="required"]').toLowerCase() === "true",
      assumption_allowed: getText('[data-field="assumption_allowed"]').toLowerCase() === "true",
      data_type: getText('[data-field="data_type"]') || "unknown",
    });
  });

  return items;
}

function validateMissingBeforeSave(items) {
  if (!items.length) return "No missing parameters are available to save.";

  const keys = new Set();

  for (const item of items) {
    if (!item.parameter) return "One missing-parameter row has an empty parameter name.";
    if (!item.needed_by) return `Parameter ${item.parameter} has an empty module name.`;
    if (!moduleNames.includes(item.needed_by)) return `Invalid module for ${item.parameter}: ${item.needed_by}`;
    if (!item.reason) return `Parameter ${item.parameter} has an empty reason.`;
    if (!allowedMissingInformationStatuses.includes(item.status)) return `Invalid status for ${item.parameter}: ${item.status}`;
    if (!allowedMissingInformationSources.includes(item.source)) return `Invalid source for ${item.parameter}: ${item.source}`;

    const key = `${item.needed_by}::${item.parameter}`;
    if (keys.has(key)) return `Duplicate missing parameter found: ${key}`;
    keys.add(key);
  }

  return null;
}

/* Workflow */
function renderWorkflowReviewStatus(status, approved = false) {
  workflowReviewStatus = status || "not_available";
  workflowApproved = Boolean(approved);

  const chip = getElement("workflow-chip");
  const card = getElement("workflow-review-card");
  const proposeButton = getElement("propose-workflow-button");
  const addModuleButton = document.getElementById("add-workflow-module-button");
  const saveButton = getElement("save-reviewed-workflow-button");
  const approveButton = getElement("approve-workflow-button");

  let label = "no workflow proposal available yet";
  if (workflowReviewStatus === "not_reviewed") label = "workflow proposed, waiting for user review";
  if (workflowReviewStatus === "edited_not_saved") label = "workflow edited, not saved yet";
  if (workflowReviewStatus === "reviewed_by_user") label = "reviewed by user and saved";
  if (workflowReviewStatus === "approved_by_user") label = "approved by user";

  chip.textContent = "";

  card.innerHTML = `
    <strong>Review status:</strong> ${escapeHtml(label)}
    <br>
    <span class="muted">
      Reviewed workflow proposals are saved as <code>workflow_proposal_reviewed.json</code>.
      Approved workflows are saved as <code>approved_workflow.json</code>.
    </span>
  `;

  const planningAlreadyStarted = workflowReviewStatus !== "not_available" || currentWorkflow.length > 0 || currentRequestedOutputs.length > 0;
  proposeButton.disabled = !assumptionsApproved || workflowReviewStatus === "edited_not_saved" || planningAlreadyStarted;
  if (addModuleButton) addModuleButton.disabled = workflowApproved || executionRunning || moduleNames.length === 0;

  saveButton.disabled =
    currentWorkflow.length === 0 ||
    workflowReviewStatus === "reviewed_by_user" ||
    workflowReviewStatus === "approved_by_user" ||
    workflowApproved;
  approveButton.disabled =
    currentWorkflow.length === 0 ||
    workflowReviewStatus === "edited_not_saved" ||
    workflowReviewStatus === "approved_by_user" ||
    workflowApproved;

  if (document.getElementById("execute-workflow-button")) {
    renderExecutionReviewStatus(executionReviewStatus, executionApproved);
  }
}

function markWorkflowEdited() {
  if (currentWorkflow.length === 0) return;
  renderWorkflowReviewStatus("edited_not_saved", false);
}

function renderWorkflow(workflow, reviewStatus = "not_available", approved = false) {
  currentWorkflow = workflow || [];
  const tbody = document.querySelector("#workflow-table tbody");
  tbody.innerHTML = "";

  if (!currentWorkflow.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">No workflow proposed yet.</td></tr>`;
    renderWorkflowPreviewFromModules();
    renderWorkflowReviewStatus(reviewStatus, approved);
    return;
  }

  currentWorkflow.forEach((step, index) => {
    const row = document.createElement("tr");
    row.dataset.rowIndex = String(index);
    row.className = "workflow-row";

    row.innerHTML = `
      <td><input class="cell-input wf-step" value="${escapeHtml(step.step)}" data-field="step" /></td>
      <td><select class="cell-select wf-module" data-field="module">${makeOptions(moduleNames, step.module)}</select></td>
      <td><textarea class="cell-textarea wf-inputs" data-field="input_data_artifacts">${escapeHtml(step.input_data_artifacts)}</textarea></td>
      <td><textarea class="cell-textarea wf-outputs" data-field="output_artifacts">${escapeHtml(step.output_artifacts)}</textarea></td>
      <td><textarea class="cell-textarea wf-rationale" data-field="rationale">${escapeHtml(step.rationale)}</textarea></td>
      <td><select class="cell-select wf-status" data-field="status">${makeOptions(allowedWorkflowStatuses, step.status)}</select></td>
      <td class="workflow-actions-cell">
        <button type="button" class="table-action-button workflow-drag-handle" title="Drag to reorder this module">↕</button>
        <button type="button" class="table-action-button danger-link remove-workflow-module-button" title="Remove this module from workflow">Remove</button>
      </td>
    `;

    tbody.appendChild(row);
  });

  renderWorkflowAddRow(tbody);

  tbody.querySelectorAll("tr.workflow-row input, tr.workflow-row textarea, tr.workflow-row select").forEach((element) => {
    element.addEventListener("input", markWorkflowEdited);
    element.addEventListener("change", markWorkflowEdited);
  });

  tbody.querySelectorAll(".remove-workflow-module-button").forEach((button) => {
    button.addEventListener("click", () => {
      const row = button.closest("tr");
      const moduleName = row?.querySelector('[data-field="module"]')?.value || "module";
      row?.remove();
      renumberWorkflowTableRows();
      currentWorkflow = collectWorkflowFromTable();
      markWorkflowEdited();
      renderWorkflowPreviewFromModules();
      addChatMessage("STAR", `Removed ${moduleName} from the workflow. Save the reviewed workflow to persist the change.`);
    });
  });

  enableWorkflowDragAndDrop(tbody);
  renderWorkflowReviewStatus(reviewStatus, approved);
  renderWorkflowPreviewFromModules();
}

function renderWorkflowAddRow(tbody) {
  const addRow = document.createElement("tr");
  addRow.className = "workflow-add-row";
  addRow.innerHTML = `
    <td colspan="7">
      <div class="workflow-plus-row">
        <button type="button" class="workflow-plus-button" id="workflow-plus-add-button" title="Add module">+</button>
        <select id="workflow-plus-module-select" class="cell-select workflow-plus-select"></select>
        <span class="muted">Add a module manually. Drag rows with ↕ to change execution order.</span>
      </div>
    </td>
  `;
  tbody.appendChild(addRow);
  updateWorkflowModuleSelect();
  const addButton = addRow.querySelector("#workflow-plus-add-button");
  if (addButton) addButton.addEventListener("click", () => addWorkflowModuleRow("workflow-plus-module-select"));
}

function enableWorkflowDragAndDrop(tbody) {
  let draggedRow = null;

  tbody.querySelectorAll(".workflow-drag-handle").forEach((handle) => {
    handle.draggable = true;
    handle.addEventListener("dragstart", (event) => {
      draggedRow = handle.closest("tr.workflow-row");
      if (!draggedRow) return;
      draggedRow.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", draggedRow.dataset.rowIndex || "");
    });
    handle.addEventListener("dragend", () => {
      if (draggedRow) draggedRow.classList.remove("dragging");
      tbody.querySelectorAll("tr").forEach((row) => row.classList.remove("drag-over"));
      draggedRow = null;
    });
  });

  tbody.querySelectorAll("tr.workflow-row").forEach((row) => {
    row.addEventListener("dragover", (event) => {
      if (!draggedRow || draggedRow === row) return;
      event.preventDefault();
      row.classList.add("drag-over");
    });
    row.addEventListener("dragleave", () => row.classList.remove("drag-over"));
    row.addEventListener("drop", (event) => {
      if (!draggedRow || draggedRow === row) return;
      event.preventDefault();
      row.classList.remove("drag-over");
      const bounds = row.getBoundingClientRect();
      const after = event.clientY > bounds.top + bounds.height / 2;
      row.parentNode.insertBefore(draggedRow, after ? row.nextSibling : row);
      renumberWorkflowTableRows();
      currentWorkflow = collectWorkflowFromTable();
      markWorkflowEdited();
      renderWorkflowPreviewFromModules();
    });
  });
}

function collectWorkflowFromTable() {
  const rows = document.querySelectorAll("#workflow-table tbody tr");
  const workflow = [];

  rows.forEach((row) => {
    if (row.querySelector(".empty-cell") || row.classList.contains("workflow-add-row")) return;

    const get = (selector) => row.querySelector(selector)?.value?.trim() ?? "";

    workflow.push({
      step: get('[data-field="step"]'),
      module: get('[data-field="module"]'),
      input_data_artifacts: get('[data-field="input_data_artifacts"]'),
      output_artifacts: get('[data-field="output_artifacts"]'),
      rationale: get('[data-field="rationale"]'),
      status: get('[data-field="status"]'),
    });
  });

  return workflow;
}

function validateWorkflowBeforeSave(workflow) {
  if (!workflow.length) return "No workflow is available to save.";

  const steps = new Set();

  for (const step of workflow) {
    if (!step.step) return "One workflow row has an empty step.";
    if (steps.has(step.step)) return `Duplicate workflow step found: ${step.step}`;
    if (!step.module) return `Workflow step ${step.step} has an empty module.`;
    if (!moduleNames.includes(step.module)) return `Workflow step ${step.step} has invalid module: ${step.module}`;
    if (!step.output_artifacts) return `Workflow step ${step.step} has empty output artifacts.`;
    if (!allowedWorkflowStatuses.includes(step.status)) return `Workflow step ${step.step} has invalid status: ${step.status}`;
    steps.add(step.step);
  }

  return null;
}

function renumberWorkflowTableRows() {
  const rows = document.querySelectorAll("#workflow-table tbody tr");
  let counter = 1;
  rows.forEach((row) => {
    if (row.querySelector(".empty-cell") || row.classList.contains("workflow-add-row")) return;
    const stepInput = row.querySelector('[data-field="step"]');
    if (stepInput) stepInput.value = String(counter);
    counter += 1;
  });
}

function addWorkflowModuleRow(selectorId = "workflow-plus-module-select") {
  const selector = document.getElementById(selectorId) || document.getElementById("workflow-plus-module-select");
  if (!selector) {
    addChatMessage("STAR", "Workflow module selector is not available.");
    return;
  }
  const moduleName = selector.value;
  if (!moduleName) return;

  const module = getModuleByName(moduleName);
  if (!module) {
    addChatMessage("STAR", `Module not found: ${moduleName}`);
    return;
  }

  const existing = collectWorkflowFromTable();
  if (existing.some((step) => step.module === moduleName)) {
    addChatMessage("STAR", `Module already present in workflow: ${moduleName}`);
    return;
  }

  existing.push({
    step: String(existing.length + 1),
    module: moduleName,
    input_data_artifacts: buildWorkflowInputSummaryForModule(module),
    output_artifacts: buildWorkflowOutputSummaryForModule(module),
    rationale: "Added manually by the user during workflow review.",
    status: "proposed",
  });

  renderWorkflow(existing, "edited_not_saved", false);
  addChatMessage("STAR", `Added ${moduleName} to the workflow. Save the reviewed workflow to persist the change.`);
}


/* Execution */
function renderExecutionReviewStatus(status, approved = false, running = executionRunning) {
  executionReviewStatus = status || "not_available";
  executionApproved = Boolean(approved);
  executionRunning = Boolean(running);

  const chip = getElement("execution-chip");
  const card = getElement("execution-review-card");
  const executeButton = getElement("execute-workflow-button");
  const stopButton = getElement("stop-execution-button");
  const saveButton = getElement("save-reviewed-execution-button");
  const approveButton = getElement("approve-execution-button");

  let label = "no execution results available yet";
  if (executionReviewStatus === "not_reviewed") label = "execution completed, waiting for user review";
  if (executionReviewStatus === "edited_not_saved") label = "execution table edited, not saved yet";
  if (executionReviewStatus === "reviewed_by_user") label = "reviewed by user and saved";
  if (executionReviewStatus === "approved_by_user") label = "approved by user";
  if (executionRunning) label = activeModuleName ? `execution running: ${activeModuleName}` : "execution running";
  if (executionStopRequested) label = activeModuleName ? `stop requested: ${activeModuleName}` : "stop requested";

  chip.textContent = "";

  card.innerHTML = `
    <strong>Review status:</strong> ${escapeHtml(label)}
    <br>
    <span class="muted">
      Reviewed execution results are saved as <code>execution_results_reviewed.json</code>.
      Approved execution results are saved as <code>approved_execution_results.json</code>.
    </span>
  `;

  executeButton.disabled = executionRunning || !workflowApproved || !assumptionsApproved || executionReviewStatus === "edited_not_saved";
  stopButton.disabled = !executionRunning || executionStopRequested;
  stopButton.textContent = executionStopRequested ? "Stopping..." : "Stop Execution";
  saveButton.disabled =
    executionRunning ||
    currentExecutionResults.length === 0 ||
    executionReviewStatus === "reviewed_by_user" ||
    executionReviewStatus === "approved_by_user" ||
    executionApproved;
  approveButton.disabled =
    executionRunning ||
    currentExecutionResults.length === 0 ||
    executionReviewStatus === "edited_not_saved" ||
    executionReviewStatus === "approved_by_user" ||
    executionApproved;
}

function markExecutionEdited() {
  if (currentExecutionResults.length === 0) return;
  renderExecutionReviewStatus("edited_not_saved", false);
}

function renderExecutionResults(results, reviewStatus = "not_available", approved = false) {
  currentExecutionResults = results || [];
  const tbody = document.querySelector("#execution-table tbody");
  tbody.innerHTML = "";

  if (!currentExecutionResults.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">No execution results yet.</td></tr>`;
    renderExecutionReviewStatus(reviewStatus, approved);
    return;
  }

  currentExecutionResults.forEach((result, index) => {
    const row = document.createElement("tr");
    row.dataset.rowIndex = String(index);

    row.innerHTML = `
      <td><input class="cell-input exe-step" value="${escapeHtml(result.step)}" data-field="step" /></td>
      <td><select class="cell-select exe-module" data-field="module">${makeOptions(moduleNames, result.module)}</select></td>
      <td><textarea class="cell-textarea exe-inputs" data-field="input_data_artifacts">${escapeHtml(result.input_data_artifacts)}</textarea></td>
      <td><textarea class="cell-textarea exe-outputs" data-field="output_artifacts">${escapeHtml(result.output_artifacts)}</textarea></td>
      <td><textarea class="cell-textarea exe-generated" data-field="generated_artifacts">${escapeHtml(result.generated_artifacts)}</textarea></td>
      <td><textarea class="cell-textarea exe-evidence" data-field="evidence">${escapeHtml(result.evidence)}</textarea></td>
      <td><select class="cell-select exe-status" data-field="status">${makeOptions(allowedExecutionStatuses, result.status)}</select></td>
      <td class="hidden-meta" data-field="started_at">${escapeHtml(result.started_at)}</td>
      <td class="hidden-meta" data-field="completed_at">${escapeHtml(result.completed_at)}</td>
    `;

    tbody.appendChild(row);
  });

  tbody.querySelectorAll("input, textarea, select").forEach((element) => {
    element.addEventListener("input", markExecutionEdited);
    element.addEventListener("change", markExecutionEdited);
  });

  renderExecutionReviewStatus(reviewStatus, approved);
}

function collectExecutionResultsFromTable() {
  const rows = document.querySelectorAll("#execution-table tbody tr");
  const results = [];

  rows.forEach((row) => {
    if (row.querySelector(".empty-cell") || row.classList.contains("workflow-add-row")) return;

    const get = (selector) => row.querySelector(selector)?.value?.trim() ?? "";
    const getText = (selector) => row.querySelector(selector)?.textContent?.trim() ?? "";

    results.push({
      step: get('[data-field="step"]'),
      module: get('[data-field="module"]'),
      input_data_artifacts: get('[data-field="input_data_artifacts"]'),
      output_artifacts: get('[data-field="output_artifacts"]'),
      generated_artifacts: get('[data-field="generated_artifacts"]'),
      evidence: get('[data-field="evidence"]'),
      status: get('[data-field="status"]'),
      started_at: getText('[data-field="started_at"]'),
      completed_at: getText('[data-field="completed_at"]'),
    });
  });

  return results;
}

function validateExecutionBeforeSave(results) {
  if (!results.length) return "No execution results are available to save.";

  const steps = new Set();

  for (const result of results) {
    if (!result.step) return "One execution row has an empty step.";
    if (steps.has(result.step)) return `Duplicate execution step found: ${result.step}`;
    if (!result.module) return `Execution step ${result.step} has an empty module.`;
    if (!moduleNames.includes(result.module)) return `Execution step ${result.step} has invalid module: ${result.module}`;
    if (!result.output_artifacts) return `Execution step ${result.step} has empty output artifacts.`;
    if (!allowedExecutionStatuses.includes(result.status)) return `Execution step ${result.step} has invalid status: ${result.status}`;
    if (!result.generated_artifacts && !["stopped", "failed", "skipped", "skipped_out_of_scope", "skipped_blocked"].includes(String(result.status || "").toLowerCase())) {
      return `Execution step ${result.step} has empty generated artifacts.`;
    }
    if (!result.evidence) return `Execution step ${result.step} has empty evidence.`;
    steps.add(result.step);
  }

  return null;
}



/* Reports */
function renderReportStatus(status = "not_available", manifest = []) {
  reportStatus = status || "not_available";
  currentReportManifest = manifest || [];

  const chip = getElement("report-chip");
  const card = getElement("report-status-card");
  const button = getElement("generate-report-button");

  let label = "no report generated yet";
  if (reportStatus === "generated") label = `report package generated (${currentReportManifest.length} files)`;

  chip.textContent = "";

  card.innerHTML = `
    <strong>Report status:</strong> ${escapeHtml(label)}
    <br>
    <span class="muted">
      The generated package includes a Markdown report, executive summary, traceability matrix,
      artifact registry, run summary and report manifest. Paths are written in chat and log.
    </span>
  `;

  button.disabled = !executionApproved;
}

async function generateReportPackage() {
  try {
    await waitForPywebview();

    if (!executionApproved) {
      addChatMessage("STAR", "Approve execution results before generating the report package.");
      return;
    }

    const button = getElement("generate-report-button");
    button.disabled = true;
    button.textContent = "Generating...";

    const result = await window.pywebview.api.generate_report_package();

    button.textContent = "Generate Report Package";
    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "Report generation failed.");
      renderReportStatus(reportStatus, currentReportManifest);
      return;
    }

    renderReportStatus(result.report_status || "generated", result.report_manifest || []);

    addChatMessage("STAR", result.message || "Report package generated.");
    if (result.report_manifest && result.report_manifest.length) {
      result.report_manifest.forEach((item) => {
        addChatMessage("STAR", `${item.artifact}: ${item.path}`);
      });
    }
    if (result.report_manifest_path) {
      addChatMessage("STAR", `Report manifest saved at: ${result.report_manifest_path}`);
    }
  } catch (error) {
    showFrontendError(error);
  }
}


/* Initialization */
async function initialize() {
  try {
    await waitForPywebview();

    const state = await window.pywebview.api.get_initial_state();

    allowedRequirementCategories = state.allowed_requirement_categories || allowedRequirementCategories;
    allowedRequirementStatuses = state.allowed_requirement_statuses || allowedRequirementStatuses;
    allowedMissingInformationStatuses = state.allowed_missing_information_statuses || allowedMissingInformationStatuses;
    allowedMissingInformationSources = state.allowed_missing_information_sources || allowedMissingInformationSources;
    allowedWorkflowStatuses = state.allowed_workflow_statuses || allowedWorkflowStatuses;
    allowedExecutionStatuses = state.allowed_execution_statuses || allowedExecutionStatuses;

    getElement("app-title").textContent = state.app_name || "STAR";
    getElement("app-subtitle").textContent = state.subtitle || "Desktop HTML prototype ready.";
    const requirementMode = document.getElementById("requirement-mode");
    if (requirementMode) requirementMode.value = "Local LLM via Ollama";

    setLogs(state.logs || []);
    renderModules(state.modules || []);
    renderRun(state.run || null);
    renderRequirements(state.requirements || [], state.requirements_review_status || "not_available");
    renderMissingInformation(
      state.missing_information || [],
      state.missing_information_review_status || "not_available",
      state.assumptions_approved || false
    );
    renderWorkflow(
      state.workflow || [],
      state.workflow_review_status || "not_available",
      state.workflow_approved || false
    );
    executionRunning = Boolean(state.execution_running);
    executionStopRequested = Boolean(state.execution_stop_requested);
    activeModuleName = state.active_module_name || null;
    renderExecutionResults(
      state.execution_results || [],
      state.execution_review_status || "not_available",
      state.execution_approved || false
    );
    renderExecutionReviewStatus(state.execution_review_status || "not_available", state.execution_approved || false, executionRunning);
    renderReportStatus(
      state.report_status || "not_available",
      state.report_manifest || []
    );

    addChatMessage("STAR", "Desktop HTML interface initialized. Upload a mission request document to start.");
  } catch (error) {
    showFrontendError(error);
  }
}

/* Backend actions */
async function uploadDocument() {
  try {
    await waitForPywebview();
    addChatMessage("STAR", "Opening document selection dialog...");

    const customRunFolderName = (document.getElementById("run-folder-name")?.value || "").trim();
    const result = await window.pywebview.api.upload_document(customRunFolderName);

    if (result.cancelled) {
      addChatMessage("STAR", "Upload cancelled.");
      return;
    }
    if (!result.ok) {
      setLogs(result.logs || []);
      addChatMessage("STAR", result.error || "Upload failed.");
      return;
    }

    setLogs(result.logs || []);
    renderModules(result.modules || modules);
    renderRun(result.run);
    renderRequirements(result.requirements || [], result.requirements_review_status || "not_available");
    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "not_available", result.assumptions_approved || false);
    renderWorkflow(result.workflow || [], result.workflow_review_status || "not_available", result.workflow_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);

    addChatMessage("STAR", result.message || "Mission request received.");
  } catch (error) {
    showFrontendError(error);
  }
}

async function extractRequirements() {
  try {
    await waitForPywebview();

    const mode = getElement("requirement-mode").value;
    const extractButton = getElement("extract-button");

    extractButton.disabled = true;
    extractButton.textContent = "Extracting...";

    addChatMessage("STAR", `Extracting requirements using ${mode}.`);

    const result = await window.pywebview.api.extract_requirements(mode);

    extractButton.textContent = "Extract Requirements";
    extractButton.disabled = !currentRun;

    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "Requirement extraction failed.");
      return;
    }

    renderRequirements(result.requirements || [], result.requirements_review_status || "not_reviewed");
    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "not_available", result.assumptions_approved || false);
    renderWorkflow(result.workflow || [], result.workflow_review_status || "not_available", result.workflow_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);
    renderRun(result.run || currentRun);

    addChatMessage("STAR", result.message || "Requirements extracted.");
    addChatMessage("STAR", `Active requirements saved at: ${result.requirements_path}`);
    addChatMessage("STAR", `Raw extracted requirements preserved at: ${result.requirements_extracted_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

async function saveReviewedRequirements() {
  try {
    await waitForPywebview();

    const reviewedRequirements = collectRequirementsFromTable();
    const validationError = validateRequirementsBeforeSave(reviewedRequirements);

    if (validationError) {
      addChatMessage("STAR", validationError);
      return;
    }

    const saveButton = getElement("save-reviewed-button");
    saveButton.disabled = true;
    saveButton.textContent = "Saving...";

    const result = await window.pywebview.api.save_reviewed_requirements(reviewedRequirements);

    saveButton.textContent = "Save Reviewed Requirements";
    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "Could not save reviewed requirements.");
      saveButton.disabled = false;
      return;
    }

    renderRequirements(result.requirements || reviewedRequirements, result.requirements_review_status || "reviewed_by_user");
    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "not_available", result.assumptions_approved || false);
    renderWorkflow(result.workflow || [], result.workflow_review_status || "not_available", result.workflow_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);

    addChatMessage("STAR", result.message || "Reviewed requirements saved.");
    addChatMessage("STAR", `Reviewed requirements saved at: ${result.requirements_reviewed_path}`);
    addChatMessage("STAR", `Active requirements updated at: ${result.requirements_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

async function analyzeMissingInformation() {
  try {
    await waitForPywebview();

    if (requirementReviewStatus === "edited_not_saved") {
      addChatMessage("STAR", "Please save the reviewed requirements before analyzing missing parameters.");
      return;
    }

    const mode = getElement("missing-analysis-mode").value;
    const button = getElement("analyze-missing-button");
    button.disabled = true;
    button.textContent = "Analyzing...";

    addChatMessage("STAR", `Analyzing missing parameters using ${mode}.`);
    const result = await window.pywebview.api.analyze_missing_information(mode);

    button.textContent = "Analyze Missing Parameters";
    button.disabled = currentRequirements.length === 0 || requirementReviewStatus === "edited_not_saved";

    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "Missing-parameter analysis failed.");
      return;
    }

    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "not_reviewed", result.assumptions_approved || false);
    renderWorkflow(result.workflow || [], result.workflow_review_status || "not_available", result.workflow_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);

    addChatMessage("STAR", result.message || "Missing parameters identified.");
    addChatMessage("STAR", `Active missing information saved at: ${result.missing_information_path}`);
    addChatMessage("STAR", `Raw missing information preserved at: ${result.missing_information_extracted_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

async function saveReviewedMissingInformation() {
  try {
    await waitForPywebview();

    const items = collectMissingInformationFromTable();
    const validationError = validateMissingBeforeSave(items);

    if (validationError) {
      addChatMessage("STAR", validationError);
      return;
    }

    const button = getElement("save-missing-button");
    button.disabled = true;
    button.textContent = "Saving...";

    const result = await window.pywebview.api.save_reviewed_missing_information(items);

    button.textContent = "Save Reviewed Missing Parameters";
    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "Could not save reviewed missing parameters.");
      button.disabled = false;
      return;
    }

    renderMissingInformation(result.missing_information || items, result.missing_information_review_status || "reviewed_by_user", result.assumptions_approved || false);
    renderWorkflow(result.workflow || [], result.workflow_review_status || "not_available", result.workflow_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);

    addChatMessage("STAR", result.message || "Reviewed missing parameters saved.");
    addChatMessage("STAR", `Reviewed missing information saved at: ${result.missing_information_reviewed_path}`);
    addChatMessage("STAR", `Active missing information updated at: ${result.missing_information_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

async function approveMissingInformation() {
  try {
    await waitForPywebview();

    if (missingInformationReviewStatus === "edited_not_saved") {
      addChatMessage("STAR", "Please save the reviewed missing parameters before approving assumptions.");
      return;
    }

    const result = await window.pywebview.api.approve_missing_information();
    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "Could not approve assumptions.");
      return;
    }

    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "approved_by_user", result.assumptions_approved || true);
    renderWorkflow(result.workflow || [], result.workflow_review_status || "not_available", result.workflow_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);

    addChatMessage("STAR", result.message || "Assumptions approved.");
    addChatMessage("STAR", `Approved assumptions saved at: ${result.approved_assumptions_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

async function proposeWorkflow() {
  try {
    await waitForPywebview();

    if (!assumptionsApproved) {
      addChatMessage("STAR", "Approve assumptions before proposing a workflow.");
      return;
    }

    const mode = getElement("workflow-proposal-mode").value;
    const button = getElement("propose-workflow-button");
    button.disabled = true;
    button.textContent = "Proposing...";

    addChatMessage("STAR", `Proposing workflow using ${mode}.`);
    const result = await window.pywebview.api.propose_workflow(mode);

    button.textContent = "Propose Workflow";
    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "Workflow proposal failed.");
      renderWorkflowReviewStatus(workflowReviewStatus, workflowApproved);
      return;
    }

    renderModules(result.modules || modules);
    renderWorkflow(result.workflow || [], result.workflow_review_status || "not_reviewed", result.workflow_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);

    addChatMessage("STAR", result.message || "Workflow proposal generated.");
    addChatMessage("STAR", `Active workflow proposal saved at: ${result.workflow_proposal_path}`);
    addChatMessage("STAR", `Raw workflow proposal preserved at: ${result.workflow_proposal_extracted_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

async function saveReviewedWorkflow() {
  try {
    await waitForPywebview();

    const workflow = collectWorkflowFromTable();
    const validationError = validateWorkflowBeforeSave(workflow);

    if (validationError) {
      addChatMessage("STAR", validationError);
      return;
    }

    const button = getElement("save-reviewed-workflow-button");
    button.disabled = true;
    button.textContent = "Saving...";

    const result = await window.pywebview.api.save_reviewed_workflow(workflow);

    button.textContent = "Save Reviewed Workflow";
    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "Could not save reviewed workflow.");
      button.disabled = false;
      return;
    }

    const savedWorkflow = Array.isArray(result.workflow) && result.workflow.length ? result.workflow : workflow;
    renderWorkflow(savedWorkflow, result.workflow_review_status || "reviewed_by_user", Boolean(result.workflow_approved));
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);

    renderWorkflowReviewStatus("reviewed_by_user", false);
    addChatMessage("STAR", result.message || "Reviewed workflow saved.");
    addChatMessage("STAR", `Reviewed workflow saved at: ${result.workflow_reviewed_path}`);
    addChatMessage("STAR", `Active workflow proposal updated at: ${result.workflow_proposal_path}`);
  } catch (error) {
    const button = document.getElementById("save-reviewed-workflow-button");
    if (button) {
      button.textContent = "Save Reviewed Workflow";
      button.disabled = false;
    }
    showFrontendError(error);
  }
}

async function approveWorkflow() {
  try {
    await waitForPywebview();

    if (workflowReviewStatus === "edited_not_saved") {
      addChatMessage("STAR", "Please save the reviewed workflow before approving it.");
      return;
    }

    const result = await window.pywebview.api.approve_workflow();
    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "Could not approve workflow.");
      return;
    }

    renderModules(result.modules || modules);
    renderWorkflow(result.workflow || [], result.workflow_review_status || "approved_by_user", result.workflow_approved || true);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);

    addChatMessage("STAR", result.message || "Workflow approved.");
    addChatMessage("STAR", `Approved workflow saved at: ${result.approved_workflow_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}



function cloneModulesForAnimation() {
  return modules.map((module) => ({ ...module }));
}

function setLocalModuleStatusByName(moduleList, moduleName, status) {
  moduleList.forEach((module) => {
    if (module.module_name === moduleName) {
      module.status = status;
    }
  });
}

async function playSequentialExecutionAnimation() {
  if (!currentWorkflow.length) return;

  const animatedModules = cloneModulesForAnimation();
  const workflowModuleNames = currentWorkflow.map((step) => step.module);

  animatedModules.forEach((module) => {
    module.status = workflowModuleNames.includes(module.module_name) ? "Ready" : "Idle";
  });
  renderModules(animatedModules);
  await delay(500);

  for (const step of currentWorkflow) {
    const moduleName = step.module;
    setLocalModuleStatusByName(animatedModules, moduleName, "Running");
    renderModules(animatedModules);
    await delay(1400);

    setLocalModuleStatusByName(animatedModules, moduleName, "Completed");
    renderModules(animatedModules);
    await delay(650);
  }
}

function showWorkflowModulesRunningDuringBackendExecution() {
  if (!currentWorkflow.length) return;

  const animatedModules = cloneModulesForAnimation();
  const workflowModuleNames = new Set(currentWorkflow.map((step) => step.module));

  animatedModules.forEach((module) => {
    if (workflowModuleNames.has(module.module_name)) {
      module.status = "Running";
    }
  });

  renderModules(animatedModules);
}


async function stopExecution() {
  try {
    await waitForPywebview();

    const button = getElement("stop-execution-button");
    button.disabled = true;
    button.textContent = "Stopping...";
    executionStopRequested = true;
    renderExecutionReviewStatus(executionReviewStatus, executionApproved, true);

    const result = await window.pywebview.api.stop_workflow_execution();
    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "No execution is currently running.");
      executionStopRequested = false;
      renderExecutionReviewStatus(executionReviewStatus, executionApproved, executionRunning);
      return;
    }

    executionStopRequested = Boolean(result.execution_stop_requested);
    activeModuleName = result.active_module_name || activeModuleName;
    renderModules(result.modules || modules);
    renderExecutionReviewStatus(result.execution_review_status || executionReviewStatus, result.execution_approved || false, true);
    addChatMessage("STAR", result.message || "Stop requested.");
  } catch (error) {
    showFrontendError(error);
  }
}

async function executeWorkflow() {
  try {
    await waitForPywebview();

    if (!workflowApproved) {
      addChatMessage("STAR", "Approve the workflow before executing it.");
      return;
    }

    const button = getElement("execute-workflow-button");
    executionStopRequested = false;
    button.disabled = true;
    button.textContent = "Executing...";
    renderExecutionReviewStatus(executionReviewStatus, executionApproved, true);

    const startResult = await window.pywebview.api.execute_workflow_async();
    setLogs(startResult.logs || []);

    if (!startResult.ok) {
      addChatMessage("STAR", startResult.error || "Workflow execution could not start.");
      renderExecutionReviewStatus(executionReviewStatus, executionApproved);
      button.textContent = "Execute Workflow";
      return;
    }

    executionRunning = Boolean(startResult.execution_running);
    executionStopRequested = Boolean(startResult.execution_stop_requested);
    activeModuleName = startResult.active_module_name || null;
    renderModules(startResult.modules || modules);
    renderExecutionReviewStatus(startResult.execution_review_status || executionReviewStatus, startResult.execution_approved || false, executionRunning);
    addChatMessage("STAR", startResult.message || "Workflow execution started.");

    let result = startResult;

    while (result.execution_running) {
      await delay(800);
      result = await window.pywebview.api.get_execution_progress();
      executionRunning = Boolean(result.execution_running);
      executionStopRequested = Boolean(result.execution_stop_requested);
      activeModuleName = result.active_module_name || null;
      setLogs(result.logs || []);
      renderModules(result.modules || modules);
      renderExecutionReviewStatus(result.execution_review_status || executionReviewStatus, result.execution_approved || false, executionRunning);
    }

    executionRunning = false;
    executionStopRequested = false;
    activeModuleName = null;
    button.textContent = "Execute Workflow";
    setLogs(result.logs || []);
    renderModules(result.modules || modules);
    renderExecutionResults(
      result.execution_results || [],
      result.execution_review_status || "not_reviewed",
      result.execution_approved || false
    );
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);

    if (result.execution_error) {
      addChatMessage("STAR", `Workflow execution failed: ${result.execution_error}`);
      renderExecutionReviewStatus(result.execution_review_status || executionReviewStatus, result.execution_approved || false);
      return;
    }

    addChatMessage("STAR", result.message || "Workflow executed.");
    if (result.execution_results_path) {
      addChatMessage("STAR", `Active execution results saved at: ${result.execution_results_path}`);
    }
    if (result.execution_results_extracted_path) {
      addChatMessage("STAR", `Raw execution results preserved at: ${result.execution_results_extracted_path}`);
    }
  } catch (error) {
    showFrontendError(error);
  }
}

async function saveReviewedExecutionResults() {
  try {
    await waitForPywebview();

    const results = collectExecutionResultsFromTable();
    const validationError = validateExecutionBeforeSave(results);

    if (validationError) {
      addChatMessage("STAR", validationError);
      return;
    }

    const button = getElement("save-reviewed-execution-button");
    button.disabled = true;
    button.textContent = "Saving...";

    const result = await window.pywebview.api.save_reviewed_execution_results(results);

    button.textContent = "Save Reviewed Execution Results";
    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "Could not save reviewed execution results.");
      button.disabled = false;
      return;
    }

    renderExecutionResults(result.execution_results || results, result.execution_review_status || "reviewed_by_user", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);

    addChatMessage("STAR", result.message || "Reviewed execution results saved.");
    addChatMessage("STAR", `Reviewed execution results saved at: ${result.execution_results_reviewed_path}`);
    addChatMessage("STAR", `Active execution results updated at: ${result.execution_results_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

async function approveExecutionResults() {
  try {
    await waitForPywebview();

    if (executionReviewStatus === "edited_not_saved") {
      addChatMessage("STAR", "Please save the reviewed execution results before approving them.");
      return;
    }

    const result = await window.pywebview.api.approve_execution_results();
    setLogs(result.logs || []);

    if (!result.ok) {
      addChatMessage("STAR", result.error || "Could not approve execution results.");
      return;
    }

    renderModules(result.modules || modules);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "approved_by_user", result.execution_approved || true);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);

    addChatMessage("STAR", result.message || "Execution results approved.");
    addChatMessage("STAR", `Approved execution results saved at: ${result.approved_execution_results_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}


async function setReady() {
  try {
    await waitForPywebview();
    const result = await window.pywebview.api.set_all_modules_ready();
    setLogs(result.logs || []);
    renderModules(result.modules);
    addChatMessage("STAR", "All modules set to Ready.");
  } catch (error) {
    showFrontendError(error);
  }
}

async function resetModules() {
  try {
    await waitForPywebview();
    const result = await window.pywebview.api.reset_modules();
    setLogs(result.logs || []);
    renderModules(result.modules);
    addChatMessage("STAR", "Module states reset to Idle.");
  } catch (error) {
    showFrontendError(error);
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runVisualDemo() {
  try {
    await waitForPywebview();
    const result = await window.pywebview.api.run_visual_demo();
    setLogs(result.logs || []);

    for (const step of result.sequence) {
      const update = await window.pywebview.api.set_module_status(step.module_id, step.status);
      setLogs(update.logs || []);
      renderModules(update.modules);
      await delay(step.status === "Running" ? 800 : 350);
    }

    addChatMessage("STAR", "Visual execution demo completed.");
  } catch (error) {
    showFrontendError(error);
  }
}

async function sendChat() {
  try {
    await waitForPywebview();

    const input = getElement("chat-input");
    const text = input.value.trim();

    if (!text) return;

    addChatMessage("User", text);
    input.value = "";

    const result = await window.pywebview.api.send_chat_message(text);
    setLogs(result.logs || []);
    if (result.modules) renderModules(result.modules);
    addChatMessage("STAR", result.reply || "No reply.");
  } catch (error) {
    showFrontendError(error);
  }
}



function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function getNumericCssVar(name, fallback) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const value = parseFloat(raw);
  return Number.isFinite(value) ? value : fallback;
}

function setLayoutVar(name, valuePx) {
  document.documentElement.style.setProperty(name, `${Math.round(valuePx)}px`);
}

function setCssPxVar(name, valuePx) {
  document.documentElement.style.setProperty(name, `${Math.round(valuePx)}px`);
}

function estimateTextLines(text, widthPx, averageCharPx) {
  const cleanText = String(text || "").trim();
  if (!cleanText) return 1;
  return Math.max(1, Math.ceil((cleanText.length * averageCharPx) / Math.max(60, widthPx)));
}

function syncAdaptiveModuleCardSize() {
  if (!modules || !modules.length) return;

  const longestNameLength = Math.max(...modules.map((module) => String(module.module_name || module.name || "").length));
  const longestOwnerLength = Math.max(...modules.map((module) => String(module.owner || "unknown").length));

  // Uniform cards, sized from the module that needs the most room.
  // The target is compact but still large enough for the status light, module id, name, owner and status pill.
  const cardWidth = clamp(102 + longestNameLength * 1.15, 118, 150);
  const textColumnWidth = cardWidth - 56;
  const nameLines = estimateTextLines("W".repeat(longestNameLength), textColumnWidth, 4.2);
  const ownerLines = 1;
  const cardHeight = clamp(24 + nameLines * 9 + ownerLines * 7, 44, 60);

  setCssPxVar('--module-card-width', cardWidth);
  setCssPxVar('--module-card-min-height', cardHeight);
}

function syncModuleBayLayout() {
  const moduleBay = document.querySelector('.module-bay');
  const moduleGrid = document.getElementById('module-grid');
  if (!moduleBay || !moduleGrid) return;

  const height = moduleBay.getBoundingClientRect().height || getNumericCssVar('--module-row-height', 112);
  const cardHeight = getNumericCssVar('--module-card-min-height', 58);
  const expandedThreshold = Math.max(132, cardHeight * 2 + 46);
  const expanded = height >= expandedThreshold && !moduleBay.classList.contains('collapsed');

  moduleBay.classList.toggle('expanded-modules', expanded);
  moduleGrid.classList.toggle('module-grid-wrapped', expanded);
}

// Frontend v5 (2026-10-18): the terminal (log + chat) is in the bottom row, on the left of the STAR modules; the column
// resizer of that row sets --bottom-left-width. Sizes are saved under star5_* keys (the v4 sizes do not apply).
function setupResizableLayout() {
  const root = document.documentElement;
  const topGrid = document.querySelector('.top-workbench');
  const bottomGrid = document.querySelector('.bottom-workbench');
  const moduleBay = document.querySelector('.module-bay');
  const topRowResizer = document.getElementById('top-row-resizer');
  const moduleRowResizer = document.getElementById('module-row-resizer');
  const bottomColumnResizer = document.getElementById('bottom-column-resizer');

  const savedTop = Number(localStorage.getItem('star5_top_row_height'));
  const savedModule = Number(localStorage.getItem('star5_module_row_height'));
  const savedLeft = Number(localStorage.getItem('star5_bottom_left_width'));

  if (Number.isFinite(savedTop) && savedTop > 0) setLayoutVar('--top-row-height', savedTop);
  if (Number.isFinite(savedModule) && savedModule > 0) {
    setLayoutVar('--module-row-height', savedModule);
  } else {
    setLayoutVar('--module-row-height', Math.max(260, Math.min(340, window.innerHeight * 0.30)));
  }
  if (Number.isFinite(savedLeft) && savedLeft > 0) setLayoutVar('--bottom-left-width', savedLeft);

  syncModuleBayLayout();

  if (topRowResizer && topGrid) {
    topRowResizer.addEventListener('mousedown', (event) => {
      event.preventDefault();
      document.body.classList.add('is-resizing');

      const startY = event.clientY;
      const startHeight = topGrid.getBoundingClientRect().height;

      const onMove = (moveEvent) => {
        const maxHeight = Math.max(160, window.innerHeight * 0.55);
        const newHeight = clamp(startHeight + (moveEvent.clientY - startY), 120, maxHeight);
        setLayoutVar('--top-row-height', newHeight);
        localStorage.setItem('star5_top_row_height', String(Math.round(newHeight)));
      };

      const onUp = () => {
        document.body.classList.remove('is-resizing');
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
      };

      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    });

    topRowResizer.addEventListener('dblclick', () => {
      root.style.removeProperty('--top-row-height');
      localStorage.removeItem('star5_top_row_height');
    });
  }

  if (moduleRowResizer && moduleBay) {
    moduleRowResizer.addEventListener('mousedown', (event) => {
      event.preventDefault();
      document.body.classList.add('is-resizing');

      const startY = event.clientY;
      const startHeight = moduleBay.getBoundingClientRect().height;

      const onMove = (moveEvent) => {
        const maxHeight = Math.max(210, window.innerHeight * 0.62);
        const newHeight = clamp(startHeight - (moveEvent.clientY - startY), 84, maxHeight);
        setLayoutVar('--module-row-height', newHeight);
        localStorage.setItem('star5_module_row_height', String(Math.round(newHeight)));
        syncModuleBayLayout();
      };

      const onUp = () => {
        document.body.classList.remove('is-resizing');
        syncModuleBayLayout();
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
      };

      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    });

    moduleRowResizer.addEventListener('dblclick', () => {
      root.style.removeProperty('--module-row-height');
      localStorage.removeItem('star5_module_row_height');
      syncModuleBayLayout();
    });
  }

  if (bottomColumnResizer && bottomGrid) {
    bottomColumnResizer.addEventListener('mousedown', (event) => {
      event.preventDefault();
      document.body.classList.add('is-resizing', 'is-resizing-horizontal');

      const startX = event.clientX;
      const firstPanel = bottomGrid.querySelector('.communication-panel');
      const startWidth = firstPanel ? firstPanel.getBoundingClientRect().width : bottomGrid.getBoundingClientRect().width * 0.26;

      const onMove = (moveEvent) => {
        const gridWidth = bottomGrid.getBoundingClientRect().width;
        const minLeft = 300;
        const minRight = 520;
        const newWidth = clamp(startWidth + (moveEvent.clientX - startX), minLeft, gridWidth - minRight);
        setLayoutVar('--bottom-left-width', newWidth);
        localStorage.setItem('star5_bottom_left_width', String(Math.round(newWidth)));
        syncAdaptiveModuleCardSize();
      };

      const onUp = () => {
        document.body.classList.remove('is-resizing', 'is-resizing-horizontal');
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
      };

      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    });

    bottomColumnResizer.addEventListener('dblclick', () => {
      root.style.removeProperty('--bottom-left-width');
      localStorage.removeItem('star5_bottom_left_width');
      syncAdaptiveModuleCardSize();
    });
  }

  window.addEventListener('resize', () => {
    syncAdaptiveModuleCardSize();
    syncModuleBayLayout();
  });
}

function setupCollapsiblePanels() {
  const collapsiblePanels = document.querySelectorAll(".panel.console-panel, .panel.chat-panel, .panel.module-bay");

  collapsiblePanels.forEach((panel) => {
    if (panel.dataset.collapseReady === "true") return;

    const header = panel.querySelector(".panel-header");
    if (!header) return;

    panel.dataset.collapseReady = "true";

    const rightArea = document.createElement("div");
    rightArea.className = "panel-header-actions";

    const existingMuted = header.querySelector(".muted");
    if (existingMuted) {
      rightArea.appendChild(existingMuted);
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "collapse-panel-button";
    button.textContent = "−";
    button.title = "Collapse / expand panel";

    button.addEventListener("click", () => {
      panel.classList.toggle("collapsed");
      button.textContent = panel.classList.contains("collapsed") ? "+" : "−";
      syncModuleBayLayout();
    });

    rightArea.appendChild(button);
    header.appendChild(rightArea);
  });
}

function setupTabs() {
  const buttons = document.querySelectorAll(".tab-button");
  const dataContents = document.querySelectorAll(".tab-data-content");
  const controlContents = document.querySelectorAll(".tab-controls-content");

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      dataContents.forEach((c) => c.classList.remove("active"));
      controlContents.forEach((c) => c.classList.remove("active"));

      button.classList.add("active");
      const tabName = button.dataset.tab;
      const dataContent = document.getElementById(`tab-${tabName}`);
      const controlContent = document.getElementById(`tab-${tabName}-controls`);
      if (dataContent) dataContent.classList.add("active");
      if (controlContent) controlContent.classList.add("active");
    });
  });
}

function setupCommunicationTabs() {
  const buttons = document.querySelectorAll(".comm-tab-button");
  const contents = document.querySelectorAll(".comm-tab-content");

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      contents.forEach((c) => c.classList.remove("active"));

      button.classList.add("active");
      const content = document.getElementById(`comm-${button.dataset.commTab}`);
      if (content) content.classList.add("active");
    });
  });
}

function setupEvents() {
  const themeSelect = document.getElementById("theme-select");
  if (themeSelect) {
    themeSelect.addEventListener("change", (event) => {
      applyTheme(event.target.value);
    });
  }

  getElement("select-document-button").addEventListener("click", uploadDocument);   // v5: Upload Document is a tab
  getElement("extract-button").addEventListener("click", extractRequirements);
  getElement("add-requirement-button").addEventListener("click", addRequirementRow);
  getElement("save-reviewed-button").addEventListener("click", saveReviewedRequirements);

  getElement("analyze-missing-button").addEventListener("click", analyzeMissingInformation);
  getElement("save-missing-button").addEventListener("click", saveReviewedMissingInformation);
  getElement("approve-missing-button").addEventListener("click", approveMissingInformation);

  getElement("propose-workflow-button").addEventListener("click", proposeWorkflow);
  const addWorkflowModuleToolbarButton = document.getElementById("add-workflow-module-button");
  if (addWorkflowModuleToolbarButton) {
    addWorkflowModuleToolbarButton.addEventListener("click", () => addWorkflowModuleRow("workflow-plus-module-select"));
  }
  getElement("save-reviewed-workflow-button").addEventListener("click", saveReviewedWorkflow);
  getElement("approve-workflow-button").addEventListener("click", approveWorkflow);

  getElement("execute-workflow-button").addEventListener("click", executeWorkflow);
  getElement("stop-execution-button").addEventListener("click", stopExecution);
  getElement("save-reviewed-execution-button").addEventListener("click", saveReviewedExecutionResults);
  getElement("approve-execution-button").addEventListener("click", approveExecutionResults);

  getElement("generate-report-button").addEventListener("click", generateReportPackage);

  const setReadyButton = document.getElementById("set-ready-button");
  if (setReadyButton) setReadyButton.addEventListener("click", setReady);

  const resetButton = document.getElementById("reset-button");
  if (resetButton) resetButton.addEventListener("click", resetModules);

  const runDemoButton = document.getElementById("run-demo-button");
  if (runDemoButton) runDemoButton.addEventListener("click", runVisualDemo);
  getElement("send-button").addEventListener("click", sendChat);

  const chatInput = getElement("chat-input");
  chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendChat();
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  try {
    initializeTheme();
    getElement("app-subtitle").textContent = "Initializing frontend...";
    setupTabs();
    setupCommunicationTabs();
    setupCollapsiblePanels();
    setupResizableLayout();
    setupEvents();
    initialize();
  } catch (error) {
    showFrontendError(error);
  }
});


/* ------------------------------------------------------------------
   STAR pipeline refactor overrides: Requirements -> Mission Planning
   -> Input Resolution -> Execution
------------------------------------------------------------------ */
function renderRequestedOutputs(outputs, reviewStatus = "not_available") {
  currentRequestedOutputs = outputs || [];
  requestedOutputsReviewStatus = reviewStatus || "not_available";

  const table = document.getElementById("requested-outputs-table");
  if (!table) return;
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";

  if (!currentRequestedOutputs.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-cell">No requested outputs identified yet.</td></tr>`;
    return;
  }

  currentRequestedOutputs.forEach((output) => {
    const derived = Array.isArray(output.derived_from_requirements)
      ? output.derived_from_requirements.join(", ")
      : String(output.derived_from_requirements || "-");
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(output.id || "")}</td>
      <td>${escapeHtml(output.description || "")}</td>
      <td>${escapeHtml(output.output_type || "")}</td>
      <td>${escapeHtml(output.priority || "")}</td>
      <td>${escapeHtml(derived)}</td>
      <td>${escapeHtml(output.rationale || "")}</td>
    `;
    tbody.appendChild(row);
  });
}

function renderReviewStatus(status) {
  requirementReviewStatus = status || "not_available";

  const reviewCard = getElement("review-card");
  const saveButton = getElement("save-reviewed-button");
  const addButton = getElement("add-requirement-button");
  const extractButton = getElement("extract-button");
  const planningButton = getElement("propose-workflow-button");

  let label = "no requirements available yet";
  if (requirementReviewStatus === "not_reviewed") label = "requirements extracted, waiting for user review";
  if (requirementReviewStatus === "edited_not_saved") label = "table edited, not saved yet";
  if (requirementReviewStatus === "reviewed_by_user") label = "reviewed by user and saved";

  reviewCard.innerHTML = `
    <strong>Review status:</strong> ${escapeHtml(label)}
    <br>
    <span class="muted">
      Edited requirements are saved as <code>requirements_reviewed.json</code> and become the active <code>requirements.json</code>.
      Mission planning is enabled only after requirements are reviewed.
    </span>
  `;

  const extractionAlreadyStarted = requirementReviewStatus !== "not_available" || currentRequirements.length > 0;
  const planningAlreadyStarted = workflowReviewStatus !== "not_available" || currentWorkflow.length > 0 || currentRequestedOutputs.length > 0;
  extractButton.disabled = !currentRun || extractionAlreadyStarted;
  saveButton.disabled = currentRequirements.length === 0 || requirementReviewStatus === "reviewed_by_user";
  addButton.disabled = !currentRun;
  if (planningButton) {
    planningButton.disabled = requirementReviewStatus !== "reviewed_by_user" || workflowReviewStatus === "edited_not_saved" || planningAlreadyStarted;
  }
}

function clearMissingAndWorkflowClientSide() {
  renderRequestedOutputs([], "not_available");
  renderMissingInformation([], "not_available", false);
  renderWorkflow([], "not_available", false);
}

function renderWorkflowReviewStatus(status, approved = false) {
  workflowReviewStatus = status || "not_available";
  workflowApproved = Boolean(approved);

  const chip = getElement("workflow-chip");
  const card = getElement("workflow-review-card");
  const proposeButton = getElement("propose-workflow-button");
  const addModuleButton = document.getElementById("add-workflow-module-button");
  const saveButton = getElement("save-reviewed-workflow-button");
  const approveButton = getElement("approve-workflow-button");

  let label = "no mission planning proposal available yet";
  if (workflowReviewStatus === "not_reviewed") label = "mission planning generated, waiting for workflow review";
  if (workflowReviewStatus === "edited_not_saved") label = "workflow edited, not saved yet";
  if (workflowReviewStatus === "reviewed_by_user") label = "workflow reviewed by user and saved";
  if (workflowReviewStatus === "approved_by_user") label = "workflow approved by user";

  chip.textContent = "";
  card.innerHTML = `
    <strong>Planning status:</strong> ${escapeHtml(label)}
    <br>
    <span class="muted">
      Requested outputs are saved as <code>requested_outputs.json</code>. Workflow proposals are saved as <code>workflow_proposal.json</code>.
      After approving the workflow, resolve module inputs and approve first-guess assumptions before execution.
    </span>
  `;

  const planningAlreadyStarted = workflowReviewStatus !== "not_available" || currentWorkflow.length > 0 || currentRequestedOutputs.length > 0;
  proposeButton.disabled = requirementReviewStatus !== "reviewed_by_user" || workflowReviewStatus === "edited_not_saved" || planningAlreadyStarted;
  if (addModuleButton) addModuleButton.disabled = workflowApproved || executionRunning || moduleNames.length === 0;
  saveButton.disabled =
    !currentWorkflow.length ||
    workflowReviewStatus === "reviewed_by_user" ||
    workflowReviewStatus === "approved_by_user" ||
    workflowApproved;
  approveButton.disabled =
    !currentWorkflow.length ||
    workflowReviewStatus === "edited_not_saved" ||
    workflowReviewStatus === "approved_by_user" ||
    workflowApproved;

  const analyzeButton = document.getElementById("analyze-missing-button");
  if (analyzeButton) {
    const inputResolutionAlreadyStarted = missingInformationReviewStatus !== "not_available" || currentMissingInformation.length > 0;
    analyzeButton.disabled = !workflowApproved || inputResolutionAlreadyStarted;
  }
  renderExecutionReviewStatus(executionReviewStatus, executionApproved, executionRunning);
}

function renderMissingReviewStatus(status, approved = false) {
  missingInformationReviewStatus = status || "not_available";
  assumptionsApproved = Boolean(approved);

  const card = getElement("missing-review-card");
  const chip = getElement("assumption-chip");
  const analyzeButton = getElement("analyze-missing-button");
  const saveButton = getElement("save-missing-button");
  const approveButton = getElement("approve-missing-button");

  let label = "no workflow input resolution available yet";
  if (missingInformationReviewStatus === "not_reviewed") label = "workflow inputs resolved, waiting for user review";
  if (missingInformationReviewStatus === "edited_not_saved") label = "input table edited, not saved yet";
  if (missingInformationReviewStatus === "reviewed_by_user") label = "reviewed by user and saved";
  if (missingInformationReviewStatus === "approved_by_user") label = "approved by user";

  chip.textContent = "";
  card.innerHTML = `
    <strong>Review status:</strong> ${escapeHtml(label)}
    <br>
    <span class="muted">
      Reviewed workflow inputs are saved as <code>missing_information_reviewed.json</code>.
      Approved inputs and first guesses are saved in <code>approved_assumptions.json</code> and <code>approved_planning_package.json</code>.
    </span>
  `;

  const inputResolutionAlreadyStarted = missingInformationReviewStatus !== "not_available" || currentMissingInformation.length > 0;
  analyzeButton.disabled = !workflowApproved || missingInformationReviewStatus === "edited_not_saved" || inputResolutionAlreadyStarted;
  saveButton.disabled =
    !currentMissingInformation.length ||
    missingInformationReviewStatus === "reviewed_by_user" ||
    missingInformationReviewStatus === "approved_by_user" ||
    assumptionsApproved;
  approveButton.disabled =
    !currentMissingInformation.length ||
    missingInformationReviewStatus === "edited_not_saved" ||
    missingInformationReviewStatus === "approved_by_user" ||
    assumptionsApproved;

  renderExecutionReviewStatus(executionReviewStatus, executionApproved, executionRunning);
}

function executionHasStoppedResult() {
  return (currentExecutionResults || []).some((result) => String(result.status || "").toLowerCase() === "stopped");
}

function renderExecutionReviewStatus(status, approved = false, running = executionRunning) {
  executionReviewStatus = status || "not_available";
  executionApproved = Boolean(approved);
  executionRunning = Boolean(running);

  const chip = getElement("execution-chip");
  const card = getElement("execution-review-card");
  const executeButton = getElement("execute-workflow-button");
  const stopButton = getElement("stop-execution-button");
  const saveButton = getElement("save-reviewed-execution-button");
  const approveButton = getElement("approve-execution-button");

  const hasStoppedResult = executionHasStoppedResult();

  let label = "no execution results available yet";
  if (executionReviewStatus === "not_reviewed") label = "execution completed, waiting for user review";
  if (executionReviewStatus === "edited_not_saved") label = "execution table edited, not saved yet";
  if (executionReviewStatus === "reviewed_by_user") label = "reviewed by user and saved";
  if (executionReviewStatus === "approved_by_user") label = "approved by user";
  if (hasStoppedResult && !executionRunning) label = "execution stopped by user; workflow can be executed again";
  if (executionRunning) label = activeModuleName ? `execution running: ${activeModuleName}` : "execution running";
  if (executionStopRequested && executionRunning) label = activeModuleName ? `stop requested: ${activeModuleName}` : "stop requested";

  chip.textContent = "";
  card.innerHTML = `
    <strong>Review status:</strong> ${escapeHtml(label)}
    <br>
    <span class="muted">
      Execution requires both an approved workflow and approved workflow inputs/assumptions.
      STAR generates one input JSON file per module step before calling the module runner or placeholder.
    </span>
  `;

  executeButton.disabled = executionRunning || !(workflowApproved && assumptionsApproved) || executionReviewStatus === "edited_not_saved";
  stopButton.disabled = !executionRunning || executionStopRequested;
  stopButton.textContent = executionStopRequested && executionRunning ? "Stopping..." : "Stop Execution";
  saveButton.disabled = executionRunning || !currentExecutionResults.length || executionReviewStatus === "reviewed_by_user" || executionReviewStatus === "approved_by_user" || executionApproved;
  approveButton.disabled = executionRunning || !currentExecutionResults.length || executionReviewStatus === "edited_not_saved" || executionReviewStatus === "approved_by_user" || executionApproved;

  renderReportStatus(reportStatus, currentReportManifest);
}

async function initialize() {
  try {
    await waitForPywebview();
    const state = await window.pywebview.api.get_initial_state();

    allowedRequirementCategories = state.allowed_requirement_categories || allowedRequirementCategories;
    allowedRequirementStatuses = state.allowed_requirement_statuses || allowedRequirementStatuses;
    allowedMissingInformationStatuses = state.allowed_missing_information_statuses || allowedMissingInformationStatuses;
    allowedMissingInformationSources = state.allowed_missing_information_sources || allowedMissingInformationSources;
    allowedWorkflowStatuses = state.allowed_workflow_statuses || allowedWorkflowStatuses;
    allowedExecutionStatuses = state.allowed_execution_statuses || allowedExecutionStatuses;

    getElement("app-title").textContent = state.app_name || "STAR";
    getElement("app-subtitle").textContent = state.subtitle || "Desktop HTML prototype ready.";

    setLogs(state.logs || []);
    renderModules(state.modules || []);
    renderRun(state.run || null);
    renderRequirements(state.requirements || [], state.requirements_review_status || "not_available");
    renderRequestedOutputs(state.requested_outputs || [], state.requested_outputs_review_status || "not_available");
    executionRunning = Boolean(state.execution_running);
    executionStopRequested = Boolean(state.execution_stop_requested);
    activeModuleName = state.active_module_name || null;
    renderWorkflow(state.workflow || [], state.workflow_review_status || "not_available", state.workflow_approved || false);
    renderMissingInformation(state.missing_information || [], state.missing_information_review_status || "not_available", state.assumptions_approved || false);
    renderExecutionResults(state.execution_results || [], state.execution_review_status || "not_available", state.execution_approved || false);
    renderExecutionReviewStatus(state.execution_review_status || "not_available", state.execution_approved || false, executionRunning);
    renderReportStatus(state.report_status || "not_available", state.report_manifest || []);
    updateUploadButtonState(state.run || null);
    syncAdaptiveModuleCardSize();
    syncModuleBayLayout();

    addChatMessage("STAR", "Desktop HTML interface initialized. Upload a mission request document to start.");
  } catch (error) {
    showFrontendError(error);
  }
}

async function uploadDocument() {
  try {
    await waitForPywebview();
    addChatMessage("STAR", "Opening document selection dialog...");
    const customRunFolderName = (document.getElementById("run-folder-name")?.value || "").trim();
    const result = await window.pywebview.api.upload_document(customRunFolderName);
    if (result.cancelled) {
      addChatMessage("STAR", "Upload cancelled.");
      return;
    }
    if (!result.ok) {
      setLogs(result.logs || []);
      addChatMessage("STAR", result.error || "Upload failed.");
      return;
    }
    setLogs(result.logs || []);
    renderModules(result.modules || modules);
    renderRun(result.run);
    renderRequirements(result.requirements || [], result.requirements_review_status || "not_available");
    renderRequestedOutputs(result.requested_outputs || [], result.requested_outputs_review_status || "not_available");
    renderWorkflow(result.workflow || [], result.workflow_review_status || "not_available", result.workflow_approved || false);
    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "not_available", result.assumptions_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);
    addChatMessage("STAR", result.message || "Mission request received.");
  } catch (error) {
    showFrontendError(error);
  }
}

async function extractRequirements() {
  try {
    await waitForPywebview();
    const mode = getElement("requirement-mode").value;
    const extractButton = getElement("extract-button");
    extractButton.disabled = true;
    extractButton.textContent = "Extracting...";
    addChatMessage("STAR", `Extracting requirements using ${mode}.`);
    const result = await window.pywebview.api.extract_requirements(mode);
    extractButton.textContent = "Extract Requirements";
    extractButton.disabled = !currentRun;
    setLogs(result.logs || []);
    if (!result.ok) {
      addChatMessage("STAR", result.error || "Requirement extraction failed.");
      return;
    }
    renderRequirements(result.requirements || [], result.requirements_review_status || "not_reviewed");
    renderRequestedOutputs(result.requested_outputs || [], result.requested_outputs_review_status || "not_available");
    renderWorkflow(result.workflow || [], result.workflow_review_status || "not_available", result.workflow_approved || false);
    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "not_available", result.assumptions_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);
    renderRun(result.run || currentRun);
    addChatMessage("STAR", result.message || "Requirements extracted.");
    addChatMessage("STAR", `Active requirements saved at: ${result.requirements_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

async function saveReviewedRequirements() {
  try {
    await waitForPywebview();
    const reviewedRequirements = collectRequirementsFromTable();
    const validationError = validateRequirementsBeforeSave(reviewedRequirements);
    if (validationError) {
      addChatMessage("STAR", validationError);
      return;
    }
    const saveButton = getElement("save-reviewed-button");
    saveButton.disabled = true;
    saveButton.textContent = "Saving...";
    const result = await window.pywebview.api.save_reviewed_requirements(reviewedRequirements);
    saveButton.textContent = "Save Reviewed Requirements";
    setLogs(result.logs || []);
    if (!result.ok) {
      addChatMessage("STAR", result.error || "Could not save reviewed requirements.");
      saveButton.disabled = false;
      return;
    }
    renderRequirements(result.requirements || reviewedRequirements, result.requirements_review_status || "reviewed_by_user");
    renderRequestedOutputs(result.requested_outputs || [], result.requested_outputs_review_status || "not_available");
    renderWorkflow(result.workflow || [], result.workflow_review_status || "not_available", result.workflow_approved || false);
    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "not_available", result.assumptions_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);
    addChatMessage("STAR", result.message || "Reviewed requirements saved.");
    addChatMessage("STAR", `Active requirements updated at: ${result.requirements_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

async function proposeWorkflow() {
  try {
    await waitForPywebview();
    if (requirementReviewStatus !== "reviewed_by_user") {
      addChatMessage("STAR", "Save reviewed requirements before generating mission planning.");
      return;
    }
    const mode = getElement("workflow-proposal-mode").value;
    const button = getElement("propose-workflow-button");
    button.disabled = true;
    button.textContent = "Planning...";
    addChatMessage("STAR", `Generating mission planning using ${mode}.`);
    const result = await window.pywebview.api.propose_workflow(mode);
    button.textContent = "Generate Mission Planning";
    setLogs(result.logs || []);
    if (!result.ok) {
      addChatMessage("STAR", result.error || "Mission planning failed.");
      renderWorkflowReviewStatus(workflowReviewStatus, workflowApproved);
      return;
    }
    renderModules(result.modules || modules);
    renderRequestedOutputs(result.requested_outputs || [], result.requested_outputs_review_status || "not_reviewed");
    renderWorkflow(result.workflow || [], result.workflow_review_status || "not_reviewed", result.workflow_approved || false);
    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "not_available", result.assumptions_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);
    addChatMessage("STAR", result.message || "Mission planning generated.");
    if (result.requested_outputs_path) addChatMessage("STAR", `Requested outputs saved at: ${result.requested_outputs_path}`);
    if (result.workflow_proposal_path) addChatMessage("STAR", `Workflow proposal saved at: ${result.workflow_proposal_path}`);
    if (result.mission_planning_package_path) addChatMessage("STAR", `Mission planning package saved at: ${result.mission_planning_package_path}`);
  } catch (error) {
    const button = document.getElementById("save-reviewed-workflow-button");
    if (button) {
      button.textContent = "Save Reviewed Workflow";
      button.disabled = false;
    }
    showFrontendError(error);
  }
}

async function approveWorkflow() {
  try {
    await waitForPywebview();
    if (workflowReviewStatus === "edited_not_saved") {
      addChatMessage("STAR", "Please save the reviewed workflow before approving it.");
      return;
    }
    const result = await window.pywebview.api.approve_workflow();
    setLogs(result.logs || []);
    if (!result.ok) {
      addChatMessage("STAR", result.error || "Could not approve workflow.");
      return;
    }
    renderModules(result.modules || modules);
    renderRequestedOutputs(result.requested_outputs || [], result.requested_outputs_review_status || "not_reviewed");
    renderWorkflow(result.workflow || [], result.workflow_review_status || "approved_by_user", result.workflow_approved || true);
    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "not_available", result.assumptions_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);
    addChatMessage("STAR", result.message || "Workflow approved.");
    addChatMessage("STAR", `Approved workflow saved at: ${result.approved_workflow_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

async function analyzeMissingInformation() {
  try {
    await waitForPywebview();
    if (!workflowApproved) {
      addChatMessage("STAR", "Approve the workflow before resolving module inputs.");
      return;
    }
    const mode = getElement("missing-analysis-mode").value;
    const button = getElement("analyze-missing-button");
    button.disabled = true;
    button.textContent = "Resolving...";
    addChatMessage("STAR", `Resolving workflow inputs using ${mode}.`);
    const result = await window.pywebview.api.analyze_missing_information(mode);
    button.textContent = "Resolve Workflow Inputs";
    setLogs(result.logs || []);
    if (!result.ok) {
      addChatMessage("STAR", result.error || "Input resolution failed.");
      renderMissingReviewStatus(missingInformationReviewStatus, assumptionsApproved);
      return;
    }
    renderRequestedOutputs(result.requested_outputs || currentRequestedOutputs, result.requested_outputs_review_status || requestedOutputsReviewStatus);
    renderWorkflow(result.workflow || currentWorkflow, result.workflow_review_status || workflowReviewStatus, result.workflow_approved || workflowApproved);
    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "not_reviewed", result.assumptions_approved || false);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);
    addChatMessage("STAR", result.message || "Workflow inputs resolved.");
    addChatMessage("STAR", `Input resolution saved at: ${result.missing_information_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

async function saveReviewedMissingInformation() {
  try {
    await waitForPywebview();
    const items = collectMissingInformationFromTable();
    const validationError = validateMissingBeforeSave(items);
    if (validationError) {
      addChatMessage("STAR", validationError);
      return;
    }
    const button = getElement("save-missing-button");
    button.disabled = true;
    button.textContent = "Saving...";
    const result = await window.pywebview.api.save_reviewed_missing_information(items);
    button.textContent = "Save Reviewed Inputs";
    setLogs(result.logs || []);
    if (!result.ok) {
      addChatMessage("STAR", result.error || "Could not save reviewed workflow inputs.");
      button.disabled = false;
      return;
    }
    renderMissingInformation(result.missing_information || items, result.missing_information_review_status || "reviewed_by_user", result.assumptions_approved || false);
    renderWorkflow(result.workflow || currentWorkflow, result.workflow_review_status || workflowReviewStatus, result.workflow_approved || workflowApproved);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);
    addChatMessage("STAR", result.message || "Reviewed workflow inputs saved.");
  } catch (error) {
    showFrontendError(error);
  }
}

async function approveMissingInformation() {
  try {
    await waitForPywebview();
    if (missingInformationReviewStatus === "edited_not_saved") {
      addChatMessage("STAR", "Please save the reviewed workflow inputs before approving them.");
      return;
    }
    const result = await window.pywebview.api.approve_missing_information();
    setLogs(result.logs || []);
    if (!result.ok) {
      addChatMessage("STAR", result.error || "Could not approve workflow inputs and assumptions.");
      return;
    }
    renderMissingInformation(result.missing_information || [], result.missing_information_review_status || "approved_by_user", result.assumptions_approved || true);
    renderWorkflow(result.workflow || currentWorkflow, result.workflow_review_status || workflowReviewStatus, result.workflow_approved || workflowApproved);
    renderExecutionResults(result.execution_results || [], result.execution_review_status || "not_available", result.execution_approved || false);
    renderReportStatus(result.report_status || "not_available", result.report_manifest || []);
    addChatMessage("STAR", result.message || "Workflow inputs and assumptions approved.");
    if (result.approved_planning_package_path) addChatMessage("STAR", `Approved planning package saved at: ${result.approved_planning_package_path}`);
  } catch (error) {
    showFrontendError(error);
  }
}

/* ------------------------------------------------------------------
   Execution stop-state hardening patch v2
   ------------------------------------------------------------------ */
function renderCefChip(progress) {
  const chip = getElement("cef-loop-chip");
  if (!chip) return;
  if (!progress || !progress.max_iterations || !progress.iteration) {
    chip.hidden = true;
    return;
  }
  const done = progress.status;
  const labels = { converged: "converged", not_converged: "not converged", stalled: "stalled", interrupted: "interrupted", stopped: "stopped", not_applicable: "" };
  chip.hidden = false;
  chip.className = "cef-chip" + (done ? " " + done : "");
  chip.textContent = `Design loop · iteration ${progress.iteration}/${progress.max_iterations}` + (labels[done] ? ` · ${labels[done]}` : "");
}

function applyExecutionBackendState(state, options = {}) {
  if (!state) return;
  const renderResults = options.renderResults !== false;

  executionRunning = Boolean(state.execution_running);
  executionStopRequested = Boolean(state.execution_stop_requested);
  activeModuleName = state.active_module_name || null;
  activeModuleId = state.active_module_id || null;

  if (Array.isArray(state.logs)) setLogs(state.logs);
  if (Array.isArray(state.modules)) renderModules(state.modules);
  renderCefChip(state.cef_progress);

  if (renderResults && Object.prototype.hasOwnProperty.call(state, "execution_results")) {
    renderExecutionResults(
      state.execution_results || [],
      state.execution_review_status || "not_available",
      state.execution_approved || false
    );
  } else {
    renderExecutionReviewStatus(
      state.execution_review_status || executionReviewStatus,
      state.execution_approved || false,
      executionRunning
    );
  }

  if (Object.prototype.hasOwnProperty.call(state, "report_manifest")) {
    renderReportStatus(state.report_status || "not_available", state.report_manifest || []);
  }
}

async function synchronizeExecutionUiState() {
  try {
    await waitForPywebview();
    if (window.pywebview.api.recover_execution_ui_state) {
      const recovered = await window.pywebview.api.recover_execution_ui_state();
      applyExecutionBackendState(recovered, { renderResults: true });
      return recovered;
    }
    const progress = await window.pywebview.api.get_execution_progress();
    applyExecutionBackendState(progress, { renderResults: true });
    return progress;
  } catch (error) {
    showFrontendError(error);
    return null;
  }
}

async function stopExecution() {
  try {
    await waitForPywebview();

    const button = getElement("stop-execution-button");
    button.disabled = true;
    button.textContent = "Stopping...";
    executionStopRequested = true;
    renderExecutionReviewStatus(executionReviewStatus, executionApproved, executionRunning);

    const result = await window.pywebview.api.stop_workflow_execution();
    applyExecutionBackendState(result, { renderResults: true });

    if (!result.ok) {
      addChatMessage("STAR", result.error || "No execution is currently running.");
      await synchronizeExecutionUiState();
      return;
    }

    addChatMessage("STAR", result.message || "Stop requested.");
  } catch (error) {
    showFrontendError(error);
    await synchronizeExecutionUiState();
  }
}

async function executeWorkflow() {
  const button = getElement("execute-workflow-button");
  let lastResult = null;

  try {
    await waitForPywebview();

    if (!workflowApproved) {
      addChatMessage("STAR", "Approve the workflow before executing it.");
      return;
    }

    executionStopRequested = false;
    executionRunning = true;
    button.disabled = true;
    button.textContent = "Executing...";
    renderExecutionReviewStatus(executionReviewStatus, executionApproved, true);

    const startResult = await window.pywebview.api.execute_workflow_async();
    lastResult = startResult;
    applyExecutionBackendState(startResult, { renderResults: false });

    if (!startResult.ok) {
      addChatMessage("STAR", startResult.error || "Workflow execution could not start.");
      return;
    }

    addChatMessage("STAR", startResult.message || "Workflow execution started.");

    while (Boolean(lastResult.execution_running)) {
      await delay(800);
      lastResult = await window.pywebview.api.get_execution_progress();
      applyExecutionBackendState(lastResult, { renderResults: true });
    }

    // Fetch one final snapshot after the background thread has cleared its
    // transient execution flags. This prevents stale cached payloads from
    // leaving the Execute button stuck in the "Executing..." state.
    try {
      const finalResult = await window.pywebview.api.get_execution_progress();
      if (finalResult && finalResult.ok) {
        lastResult = finalResult;
        applyExecutionBackendState(finalResult, { renderResults: true });
      }
    } catch (ignored) {
      // Keep the last valid polling result.
    }

    if (lastResult && lastResult.execution_error) {
      addChatMessage("STAR", `Workflow execution failed: ${lastResult.execution_error}`);
      return;
    }

    if (lastResult) {
      addChatMessage("STAR", lastResult.message || "Workflow executed.");
      if (lastResult.execution_results_path) {
        addChatMessage("STAR", `Active execution results saved at: ${lastResult.execution_results_path}`);
      }
      if (lastResult.execution_results_extracted_path) {
        addChatMessage("STAR", `Raw execution results preserved at: ${lastResult.execution_results_extracted_path}`);
      }
    }
  } catch (error) {
    showFrontendError(error);
    await synchronizeExecutionUiState();
  } finally {
    // Do not trust a local stale flag: ask the backend once more if possible.
    if (window.pywebview && window.pywebview.api && window.pywebview.api.get_execution_progress) {
      try {
        const finalState = await window.pywebview.api.get_execution_progress();
        if (finalState && finalState.ok) {
          applyExecutionBackendState(finalState, { renderResults: true });
        }
      } catch (ignored) {
        // Leave the UI in the last known state.
      }
    }

    if (!executionRunning) {
      executionStopRequested = false;
      activeModuleName = null;
      activeModuleId = null;
      button.textContent = "Execute Workflow";
      renderExecutionReviewStatus(executionReviewStatus, executionApproved, false);
    } else {
      button.textContent = "Executing...";
      renderExecutionReviewStatus(executionReviewStatus, executionApproved, true);
    }
  }
}
