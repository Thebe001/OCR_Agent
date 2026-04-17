const state = {
  data: null,
  originalData: null,
  lineItems: [],
  lastRequestedLanguage: "auto",
};

const MEMORY_KEY = "ocrCorrectionMemoryV1";

const els = {
  file: document.getElementById("invoiceFile"),
  fileLabel: document.getElementById("fileLabel"),
  tenantId: document.getElementById("tenantId"),
  ocrLanguage: document.getElementById("ocrLanguage"),
  readBtn: document.getElementById("readInvoiceBtn"),
  resetBtn: document.getElementById("resetBtn"),
  status: document.getElementById("statusText"),
  detectedLanguage: document.getElementById("detectedLanguage"),
  empty: document.getElementById("emptyState"),
  form: document.getElementById("invoiceForm"),
  warning: document.getElementById("warningBox"),
  suggestionBox: document.getElementById("suggestionBox"),
  qualityGate: document.getElementById("qualityGate"),
  vatHint: document.getElementById("vatHint"),
  lineItemsBody: document.getElementById("lineItemsBody"),
  createBtn: document.getElementById("createDraftBtn"),
  supplierName: document.getElementById("supplierName"),
  invoiceNumber: document.getElementById("invoiceNumber"),
  invoiceDate: document.getElementById("invoiceDate"),
  dueDate: document.getElementById("dueDate"),
  currency: document.getElementById("currency"),
  vatRate: document.getElementById("vatRate"),
  totalNet: document.getElementById("totalNet"),
  totalVat: document.getElementById("totalVat"),
  totalGross: document.getElementById("totalGross"),
};

function setStatus(message, isError = false) {
  els.status.textContent = message;
  els.status.style.color = isError ? "#9d2929" : "";
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || "");
      resolve(value.includes(",") ? value.split(",")[1] : value);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok || body.success === false) {
    const message = body.error?.message || "An error occurred.";
    throw new Error(message);
  }
  return body;
}

function toNumber(value) {
  if (value === null || value === undefined) return 0;
  const normalized = String(value)
    .trim()
    .replace(/\s+/g, "")
    .replace(/,/g, ".")
    .replace(/[^0-9.-]/g, "");
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalizeDateInput(value) {
  if (!value) return "";
  const v = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) {
    return v;
  }

  const match = v.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (!match) return "";
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  if (day < 1 || day > 31 || month < 1 || month > 12) return "";
  return `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${day
    .toString()
    .padStart(2, "0")}`;
}

function money(value) {
  return toNumber(value).toFixed(2);
}

function clearFieldFlags() {
  document.querySelectorAll("input.field-warning, input.field-error").forEach((node) => {
    node.classList.remove("field-warning", "field-error");
  });
}

function flagField(input, level) {
  if (!input) return;
  input.classList.remove("field-warning", "field-error");
  if (level === "error") input.classList.add("field-error");
  if (level === "warning") input.classList.add("field-warning");
}

function hasWeirdCharacters(value) {
  if (!value) return false;
  return /\?{1,}|[^A-Za-z0-9À-ÖØ-öø-ÿ\s\-./]/.test(String(value));
}

function normalizeSuspiciousText(value) {
  return String(value || "")
    .replace(/\?+/g, "")
    .replace(/[^A-Za-z0-9À-ÖØ-öø-ÿ\s\-./]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeInvoiceNumberSuggestion(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/\?+/g, "")
    .replace(/[^A-Z0-9\-_/]/g, "")
    .replace(/-{2,}/g, "-")
    .trim();
}

function parseDate(value) {
  const normalized = normalizeDateInput(value);
  return normalized ? new Date(`${normalized}T00:00:00`) : null;
}

function renderWarnings(messages, isError = false) {
  if (!messages.length) {
    els.warning.classList.add("hidden");
    els.warning.classList.remove("error");
    return;
  }
  els.warning.classList.remove("hidden");
  els.warning.classList.toggle("error", Boolean(isError));
  els.warning.innerHTML = messages.map((item) => `<div>${item}</div>`).join("");
}

function renderQualityGate(status) {
  const labels = {
    safe: "Quality Gate: Safe",
    review: "Quality Gate: Review",
    blocked: "Quality Gate: Blocked",
  };

  const cssState = status in labels ? status : "review";
  els.qualityGate.textContent = labels[cssState];
  els.qualityGate.classList.remove("hidden", "safe", "review", "blocked");
  els.qualityGate.classList.add(cssState);
}

function renderVatHint(vatRate) {
  if (vatRate > 0 && vatRate !== 7 && vatRate !== 19) {
    els.vatHint.textContent = `Floravi note: VAT ${vatRate}% is uncommon here. Usual values are 7% or 19%.`;
    els.vatHint.classList.remove("hidden");
    return;
  }

  els.vatHint.textContent = "";
  els.vatHint.classList.add("hidden");
}

function loadCorrectionMemory() {
  try {
    const raw = localStorage.getItem(MEMORY_KEY);
    if (!raw) return { supplier: {}, invoice: {}, item: {} };
    const parsed = JSON.parse(raw);
    return {
      supplier: parsed.supplier || {},
      invoice: parsed.invoice || {},
      item: parsed.item || {},
    };
  } catch {
    return { supplier: {}, invoice: {}, item: {} };
  }
}

function saveCorrectionMemory(memory) {
  try {
    localStorage.setItem(MEMORY_KEY, JSON.stringify(memory));
  } catch {
    // Ignore storage failures.
  }
}

function applyCorrectionMemory(data) {
  const memory = loadCorrectionMemory();
  const patched = { ...data, line_items: Array.isArray(data.line_items) ? data.line_items.map((it) => ({ ...it })) : [] };

  const supplierKey = normalizeSuspiciousText(data.vendor_name || "");
  if (supplierKey && memory.supplier[supplierKey]) {
    patched.vendor_name = memory.supplier[supplierKey];
  }

  const invoiceKey = normalizeInvoiceNumberSuggestion(data.invoice_number || "");
  if (invoiceKey && memory.invoice[invoiceKey]) {
    patched.invoice_number = memory.invoice[invoiceKey];
  }

  patched.line_items = patched.line_items.map((item) => {
    const k = normalizeSuspiciousText(item.description || "");
    if (k && memory.item[k]) {
      return { ...item, description: memory.item[k] };
    }
    return item;
  });

  return patched;
}

function persistCorrectionsFromCurrentForm() {
  if (!state.originalData) return;
  const memory = loadCorrectionMemory();

  const originalSupplier = normalizeSuspiciousText(state.originalData.vendor_name || "");
  const currentSupplier = normalizeSuspiciousText(els.supplierName.value || "");
  if (originalSupplier && currentSupplier && originalSupplier !== currentSupplier) {
    memory.supplier[originalSupplier] = currentSupplier;
  }

  const originalInvoice = normalizeInvoiceNumberSuggestion(state.originalData.invoice_number || "");
  const currentInvoice = normalizeInvoiceNumberSuggestion(els.invoiceNumber.value || "");
  if (originalInvoice && currentInvoice && originalInvoice !== currentInvoice) {
    memory.invoice[originalInvoice] = currentInvoice;
  }

  const originalItems = Array.isArray(state.originalData.line_items) ? state.originalData.line_items : [];
  const currentItems = state.lineItems || [];
  for (let i = 0; i < Math.min(originalItems.length, currentItems.length); i += 1) {
    const src = normalizeSuspiciousText(originalItems[i]?.description || "");
    const dst = normalizeSuspiciousText(currentItems[i]?.description || "");
    if (src && dst && src !== dst) {
      memory.item[src] = dst;
    }
  }

  saveCorrectionMemory(memory);
}

async function enrichLineItemsValidation() {
  if (!state.lineItems.length) return;
  try {
    const result = await postJson("/tools/validate_items", {
      tenant_id: els.tenantId.value.trim(),
      items: state.lineItems.map((item) => ({
        description: item.description || "",
        quantity: toNumber(item.quantity),
        unit_price: toNumber(item.unit_price),
      })),
    });

    const validated = result?.data?.items || [];
    if (!validated.length) return;

    state.lineItems = state.lineItems.map((item, idx) => {
      const v = validated[idx] || {};
      return {
        ...item,
        matched_item_code: v.erpnext_item_code || item.matched_item_code || null,
        match_confidence: typeof v.match_confidence === "number" ? v.match_confidence : item.match_confidence || 0,
      };
    });
    renderLineItems(state.lineItems);
  } catch {
    // Validation is advisory; ignore runtime/API failures.
  }
}

function collectSuggestions() {
  const suggestions = [];

  if (hasWeirdCharacters(els.supplierName.value)) {
    const proposal = normalizeSuspiciousText(els.supplierName.value);
    if (proposal && proposal !== els.supplierName.value) {
      suggestions.push({ key: "supplier", text: `Supplier: ${proposal}`, value: proposal });
    }
  }

  if (hasWeirdCharacters(els.invoiceNumber.value) || /\?/.test(els.invoiceNumber.value)) {
    const proposal = normalizeInvoiceNumberSuggestion(els.invoiceNumber.value);
    if (proposal && proposal !== els.invoiceNumber.value) {
      suggestions.push({ key: "invoice", text: `Invoice number: ${proposal}`, value: proposal });
    }
  }

  const descInputs = els.lineItemsBody.querySelectorAll('input[data-field="description"]');
  descInputs.forEach((input, idx) => {
    if (!hasWeirdCharacters(input.value)) return;
    const proposal = normalizeSuspiciousText(input.value);
    if (!proposal || proposal === input.value) return;
    suggestions.push({ key: `item-${idx}`, text: `Item ${idx + 1}: ${proposal}`, value: proposal, index: idx });
  });

  return suggestions;
}

function renderSuggestions(suggestions) {
  if (!suggestions.length) {
    els.suggestionBox.classList.add("hidden");
    els.suggestionBox.innerHTML = "";
    return;
  }

  const rows = suggestions
    .map(
      (s) => `
      <div class="suggestion-row">
        <div class="suggestion-text">${s.text}</div>
        <button type="button" class="suggestion-btn" data-suggestion-key="${s.key}" data-index="${s.index ?? ""}" data-value="${encodeURIComponent(s.value)}">Apply</button>
      </div>
    `
    )
    .join("");

  els.suggestionBox.innerHTML = `<div class="suggestion-title">Suggested Corrections</div>${rows}`;
  els.suggestionBox.classList.remove("hidden");
}

function analyzeAndHighlight(forSubmit = false) {
  clearFieldFlags();

  const messages = [];
  const blockingMessages = [];
  let blocking = false;
  let hasBlockingCondition = false;
  let hasErrors = false;

  const confidence = toNumber(state.data?.confidence_score);
  const supplier = els.supplierName.value.trim();
  const invoiceNumber = els.invoiceNumber.value.trim();
  const invoiceDate = normalizeDateInput(els.invoiceDate.value);
  const dueDate = normalizeDateInput(els.dueDate.value);
  const vatRate = toNumber(els.vatRate.value);
  const net = toNumber(els.totalNet.value);
  const vat = toNumber(els.totalVat.value);
  const gross = toNumber(els.totalGross.value);

  if (confidence > 0 && confidence < 0.5) {
    messages.push("OCR confidence is low. Please verify all fields carefully.");
    [els.supplierName, els.invoiceNumber, els.invoiceDate, els.totalNet, els.totalVat, els.totalGross].forEach((input) => flagField(input, "error"));
  } else if (confidence >= 0.5 && confidence < 0.75) {
    messages.push("OCR confidence is medium. Some extracted fields may need correction.");
    [els.supplierName, els.invoiceNumber, els.invoiceDate, els.totalNet, els.totalVat, els.totalGross].forEach((input) => flagField(input, "warning"));
  }

  const required = [
    { input: els.supplierName, value: supplier, label: "Supplier" },
    { input: els.invoiceNumber, value: invoiceNumber, label: "Invoice number" },
    { input: els.invoiceDate, value: invoiceDate, label: "Invoice date" },
  ];

  required.forEach((field) => {
    if (field.value) return;
    flagField(field.input, "error");
    const msg = `${field.label} is missing.`;
    messages.push(msg);
    blockingMessages.push(msg);
    hasErrors = true;
    hasBlockingCondition = true;
    if (forSubmit) blocking = true;
  });

  if (gross <= 0) {
    flagField(els.totalGross, "error");
    const msg = "Gross amount must be greater than zero.";
    messages.push(msg);
    blockingMessages.push(msg);
    hasErrors = true;
    hasBlockingCondition = true;
    if (forSubmit) blocking = true;
  }

  if (!state.lineItems.length) {
    messages.push("No line items were detected. You can add them manually before submitting.");
  }

  const invDate = parseDate(invoiceDate);
  const due = parseDate(dueDate);
  if (invDate && due && due < invDate) {
    flagField(els.dueDate, "error");
    const msg = "Due date is earlier than invoice date.";
    messages.push(msg);
    blockingMessages.push(msg);
    hasErrors = true;
    hasBlockingCondition = true;
    if (forSubmit) blocking = true;
  }

  if (Math.abs(net + vat - gross) > 0.05) {
    [els.totalNet, els.totalVat, els.totalGross].forEach((input) => flagField(input, "error"));
    const msg = `Totals mismatch: net ${money(net)} + VAT ${money(vat)} must equal gross ${money(gross)}.`;
    messages.push(msg);
    blockingMessages.push(msg);
    hasErrors = true;
    hasBlockingCondition = true;
    if (forSubmit) blocking = true;
  }

  if (vatRate > 0 && vatRate !== 7 && vatRate !== 19) {
    flagField(els.vatRate, "warning");
  }

  if (vatRate > 0 && net > 0) {
    const expectedVat = Math.round((net * vatRate / 100) * 100) / 100;
    if (Math.abs(expectedVat - vat) > 0.1) {
      flagField(els.vatRate, "warning");
      flagField(els.totalVat, "warning");
      messages.push(`VAT amount seems inconsistent with VAT rate ${vatRate}%.`);
    }
  }

  if (state.lineItems.length) {
    const lineSum = state.lineItems.reduce((sum, row) => sum + toNumber(row.total_price), 0);
    if (Math.abs(lineSum - net) > 0.5 && Math.abs(lineSum - gross) > 0.5) {
      messages.push(`Line item totals (${money(lineSum)}) do not match net (${money(net)}) or gross (${money(gross)}).`);
    }
  }

  state.lineItems.forEach((item) => {
    const conf = toNumber(item.match_confidence);
    if (conf > 0 && conf < 0.5) {
      messages.push(`Item '${item.description || "(unnamed)"}' has low catalog match confidence.`);
    }
  });

  if (hasWeirdCharacters(supplier)) {
    flagField(els.supplierName, "warning");
    messages.push("Supplier name contains unusual characters. Please verify.");
  }
  if (hasWeirdCharacters(invoiceNumber)) {
    flagField(els.invoiceNumber, "warning");
    messages.push("Invoice number contains unusual characters. Please verify.");
  }

  const descInputs = els.lineItemsBody.querySelectorAll('input[data-field="description"]');
  descInputs.forEach((input) => {
    if (hasWeirdCharacters(input.value)) {
      flagField(input, "warning");
    }
  });

  if (state.data?.ocr_warning) {
    messages.push(state.data.ocr_warning);
  }

  const uniqMessages = [...new Set(messages)];
  const uniqBlocking = [...new Set(blockingMessages)];
  if (forSubmit && uniqBlocking.length) {
    renderWarnings(uniqBlocking, true);
  } else {
    renderWarnings(uniqMessages, hasErrors);
  }

  const gateStatus = hasBlockingCondition ? "blocked" : (uniqMessages.length ? "review" : "safe");
  renderQualityGate(gateStatus);
  renderVatHint(vatRate);
  renderSuggestions(collectSuggestions());
  return { blocking, messages: uniqMessages, blockingMessages: uniqBlocking };
}

function renderLineItems(items) {
  els.lineItemsBody.innerHTML = "";
  items.forEach((item, index) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input data-field="description" data-index="${index}" value="${item.description || ""}" /></td>
      <td><input data-field="quantity" data-index="${index}" type="number" step="0.01" value="${item.quantity || 0}" /></td>
      <td><input data-field="unit_price" data-index="${index}" type="number" step="0.01" value="${item.unit_price || 0}" /></td>
      <td><input data-field="total_price" data-index="${index}" type="number" step="0.01" value="${item.total_price || 0}" /></td>
    `;
    els.lineItemsBody.appendChild(row);
  });
}

function fillForm(data) {
  const corrected = applyCorrectionMemory(data);
  els.empty.classList.add("hidden");
  els.form.classList.remove("hidden");

  els.supplierName.value = corrected.vendor_name || "";
  els.invoiceNumber.value = corrected.invoice_number || "";
  els.invoiceDate.value = normalizeDateInput(corrected.invoice_date);
  els.dueDate.value = normalizeDateInput(corrected.due_date);
  els.currency.value = corrected.currency || "EUR";
  els.vatRate.value = corrected.vat_rate ?? "";
  els.totalNet.value = money(corrected.total_net);
  els.totalVat.value = money(corrected.total_vat);
  els.totalGross.value = money(corrected.total_gross);

  state.lineItems = Array.isArray(corrected.line_items) ? corrected.line_items.map((item) => ({ ...item })) : [];
  renderLineItems(state.lineItems);
  analyzeAndHighlight(false);
}

function collectInvoicePayload() {
  return {
    tenant_id: els.tenantId.value.trim(),
    supplier_name: els.supplierName.value.trim(),
    invoice_number: els.invoiceNumber.value.trim(),
    invoice_date: normalizeDateInput(els.invoiceDate.value),
    due_date: normalizeDateInput(els.dueDate.value) || null,
    currency: els.currency.value.trim() || "EUR",
    line_items: state.lineItems.map((item) => ({
      description: item.description || "",
      item_code: item.matched_item_code || item.item_code || null,
      quantity: toNumber(item.quantity),
      unit_price: toNumber(item.unit_price),
      total_price: toNumber(item.total_price),
    })),
    total_net: toNumber(els.totalNet.value),
    total_vat: toNumber(els.totalVat.value),
    total_gross: toNumber(els.totalGross.value),
    vat_rate: toNumber(els.vatRate.value),
    confirmed: true,
  };
}

els.file.addEventListener("change", () => {
  const file = els.file.files?.[0];
  els.fileLabel.textContent = file ? file.name : "Choose an invoice";
});

els.lineItemsBody.addEventListener("input", (event) => {
  const input = event.target;
  const index = Number(input.dataset.index);
  const field = input.dataset.field;
  if (!field || !Number.isInteger(index) || !state.lineItems[index]) return;
  state.lineItems[index][field] = field === "description" ? input.value : toNumber(input.value);
  analyzeAndHighlight(false);
});

els.form.addEventListener("input", (event) => {
  if (event.target.tagName !== "INPUT") return;
  analyzeAndHighlight(false);
});

els.suggestionBox.addEventListener("click", (event) => {
  const btn = event.target.closest("button[data-suggestion-key]");
  if (!btn) return;
  const key = btn.dataset.suggestionKey;
  const value = decodeURIComponent(btn.dataset.value || "");

  if (key === "supplier") {
    els.supplierName.value = value;
  } else if (key === "invoice") {
    els.invoiceNumber.value = value;
  } else if (key.startsWith("item-")) {
    const index = Number(btn.dataset.index);
    const input = els.lineItemsBody.querySelector(`input[data-field="description"][data-index="${index}"]`);
    if (input) {
      input.value = value;
      if (state.lineItems[index]) state.lineItems[index].description = value;
    }
  }

  analyzeAndHighlight(false);
});

els.readBtn.addEventListener("click", async () => {
  const file = els.file.files?.[0];
  if (!file) {
    setStatus("Choose a file first.", true);
    return;
  }

  try {
    els.readBtn.disabled = true;
    setStatus("Running OCR...");
    state.lastRequestedLanguage = els.ocrLanguage.value;
    const imageData = await readFileAsBase64(file);
    const result = await postJson("/tools/process_ocr_document", {
      tenant_id: els.tenantId.value.trim(),
      image_data: imageData,
      document_type: "invoice",
      language: els.ocrLanguage.value,
    });
    state.originalData = result.data;
    state.data = result.data;
    fillForm(result.data);
    await enrichLineItemsValidation();
    analyzeAndHighlight(false);
    const detected = (result.data.detected_language || "").toLowerCase();
    if (state.lastRequestedLanguage === "auto" && ["en", "de"].includes(detected)) {
      els.ocrLanguage.value = detected;
      els.detectedLanguage.textContent = `Detected language: ${detected === "en" ? "English" : "German"}`;
      els.detectedLanguage.classList.remove("hidden");
    } else if (state.lastRequestedLanguage === "auto") {
      els.detectedLanguage.textContent = "Detected language: unknown";
      els.detectedLanguage.classList.remove("hidden");
    } else {
      els.detectedLanguage.classList.add("hidden");
    }
    setStatus("Invoice read. Review the fields before creating the draft.");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    els.readBtn.disabled = false;
  }
});

els.createBtn.addEventListener("click", async () => {
  try {
    const check = analyzeAndHighlight(true);
    if (check.blocking) {
      setStatus("Please fix the highlighted fields before creating the draft.", true);
      return;
    }

    els.createBtn.disabled = true;
    setStatus("Creating draft...");
    const result = await postJson("/tools/create_purchase_invoice", collectInvoicePayload());
    persistCorrectionsFromCurrentForm();
    setStatus(`Draft created: ${result.data.invoice_id}. Status: ${result.data.status}.`);
  } catch (error) {
    els.warning.classList.remove("hidden");
    els.warning.classList.add("error");
    els.warning.textContent = `${error.message} The data stays on screen.`;
    setStatus("Creation failed for now.", true);
  } finally {
    els.createBtn.disabled = false;
  }
});

els.resetBtn.addEventListener("click", () => {
  state.data = null;
  state.lineItems = [];
  els.file.value = "";
  els.fileLabel.textContent = "Choose an invoice";
  els.empty.classList.remove("hidden");
  els.form.classList.add("hidden");
  els.warning.classList.add("hidden");
  els.suggestionBox.classList.add("hidden");
  els.qualityGate.classList.add("hidden");
  els.vatHint.classList.add("hidden");
  els.detectedLanguage.classList.add("hidden");
  clearFieldFlags();
  setStatus("Ready.");
});
