const els = {
  date: document.getElementById("dateInput"),
  profile: document.getElementById("profileInput"),
  forceClose: document.getElementById("forceCloseInput"),
  status: document.getElementById("status"),
  output: document.getElementById("output"),
  btnTransactions: document.getElementById("btnTransactions"),
  btnValidate: document.getElementById("btnValidate"),
  btnAnomalies: document.getElementById("btnAnomalies"),
  btnClose: document.getElementById("btnClose"),
  btnFlow: document.getElementById("btnFlow"),
  btnClear: document.getElementById("btnClear"),
  sourceChip: document.getElementById("sourceChip"),
};

function setStatus(text, isError = false) {
  els.status.textContent = text;
  els.status.style.color = isError ? "#9d2929" : "";
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function eur(value) {
  const n = Number(value || 0);
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(n);
}

function setSourceChip(dataSource) {
  if (!dataSource) {
    els.sourceChip.style.display = "none";
    els.sourceChip.textContent = "";
    return;
  }
  const label = dataSource === "erpnext" ? "Real ERPNext Data" : "Mock Data";
  els.sourceChip.textContent = `Data Source: ${label}`;
  els.sourceChip.style.display = "inline-flex";
}

function renderCards(cards) {
  return `<div class="cards">${cards
    .map(
      (c) => `<div class="card"><div class="k">${esc(c.k)}</div><div class="v ${c.cls || ""}">${esc(c.v)}</div></div>`
    )
    .join("")}</div>`;
}

function renderTransactions(data) {
  const invoiceRows = (data.invoices || [])
    .map((inv) => {
      const modes = (inv.payments || []).map((p) => `${p.mode_of_payment}: ${eur(p.amount)}`).join(" | ");
      return `<tr>
        <td>${esc(inv.invoice_id)}</td>
        <td>${esc(inv.posting_time || "")}</td>
        <td>${esc(inv.cashier || "Unknown")}</td>
        <td>${eur(inv.total)}</td>
        <td>${esc(modes || "-")}</td>
      </tr>`;
    })
    .join("");

  const cashierRows = Object.entries(data.cashier_breakdown || {})
    .map(([cashier, total]) => `<tr><td>${esc(cashier)}</td><td>${eur(total)}</td></tr>`)
    .join("");

  return `
    ${renderCards([
      { k: "Date", v: data.date || "-" },
      { k: "Transactions", v: data.transaction_count || 0 },
      { k: "Total Sales", v: eur(data.total_sales) },
    ])}
    <h3>Cashier Breakdown</h3>
    <div class="table-wrap"><table><thead><tr><th>Cashier</th><th>Total</th></tr></thead><tbody>${cashierRows || "<tr><td colspan='2'>No data</td></tr>"}</tbody></table></div>
    <h3>Invoices</h3>
    <div class="table-wrap"><table><thead><tr><th>Invoice</th><th>Time</th><th>Cashier</th><th>Total</th><th>Payments</th></tr></thead><tbody>${invoiceRows || "<tr><td colspan='5'>No invoices for this date</td></tr>"}</tbody></table></div>
  `;
}

function renderValidation(data) {
  const modeRows = Object.keys(data.mode_breakdown_from_payments || {}).map((mode) => {
    const p = data.mode_breakdown_from_payments[mode] || 0;
    const i = (data.mode_breakdown_from_invoices || {})[mode] || 0;
    return `<tr><td>${esc(mode)}</td><td>${eur(i)}</td><td>${eur(p)}</td><td>${eur(p - i)}</td></tr>`;
  });

  return `
    ${renderCards([
      { k: "Invoice Total", v: eur(data.invoice_total) },
      { k: "Payment Total", v: eur(data.payment_total) },
      { k: "Difference", v: eur(data.difference), cls: Math.abs(Number(data.difference || 0)) < 0.01 ? "ok" : "err" },
    ])}
    <p class="${data.is_valid ? "ok" : "err"}"><strong>${esc(data.validation_message)}</strong></p>
    <div class="table-wrap"><table><thead><tr><th>Payment Mode</th><th>From Invoices</th><th>From Payment Summary</th><th>Delta</th></tr></thead><tbody>${modeRows.join("") || "<tr><td colspan='4'>No payment data</td></tr>"}</tbody></table></div>
  `;
}

function anomalyCard(a) {
  const inv = a.source_invoice ? `<div><strong>Invoice:</strong> ${esc(a.source_invoice)}</div>` : "";
  const item = a.source_item ? `<div><strong>Item:</strong> ${esc(a.source_item)}</div>` : "";
  const exp = a.expected_value !== undefined ? `<div><strong>Expected:</strong> ${eur(a.expected_value)}</div>` : "";
  const act = a.actual_value !== undefined ? `<div><strong>Actual:</strong> ${eur(a.actual_value)}</div>` : "";
  return `
    <div class="anomaly">
      <div><span class="badge ${esc(a.severity).toLowerCase()}">${esc(a.severity)}</span> <strong>${esc(a.anomaly_type)}</strong></div>
      <p>${esc(a.explanation)}</p>
      ${inv}${item}${exp}${act}
    </div>
  `;
}

function renderAnomalies(data) {
  const summary = data.summary || {};
  const anomalies = data.anomalies || [];
  return `
    ${renderCards([
      { k: "Total Anomalies", v: summary.total_anomalies || 0, cls: (summary.total_anomalies || 0) > 0 ? "err" : "ok" },
      { k: "Safe To Close", v: summary.safe_to_close ? "Yes" : "No", cls: summary.safe_to_close ? "ok" : "warn" },
      { k: "Recommendation", v: summary.safe_to_close ? "Close session" : "Review needed", cls: summary.safe_to_close ? "ok" : "warn" },
    ])}
    <p><strong>${esc(summary.recommendation || "")}</strong></p>
    <div class="anomaly-list">${anomalies.length ? anomalies.map(anomalyCard).join("") : '<div class="empty">No anomalies detected.</div>'}</div>
  `;
}

function renderClose(data) {
  return `
    ${renderCards([
      { k: "Status", v: data.status || "UNKNOWN", cls: data.status === "CLOSED" ? "ok" : data.status === "FORCE_CLOSED" ? "warn" : "err" },
      { k: "Transactions", v: data.transaction_count ?? "-" },
      { k: "Total Sales", v: eur(data.total_sales || 0) },
    ])}
    <p><strong>${esc(data.message || data.reason || "")}</strong></p>
    <p>${data.hint ? esc(data.hint) : ""}</p>
    <div class="table-wrap"><table><tbody>
      <tr><th>Closing Entry</th><td>${esc(data.closing_entry_id || "-")}</td></tr>
      <tr><th>Date</th><td>${esc(data.date || "-")}</td></tr>
      <tr><th>Closed At</th><td>${esc(data.closed_at || "-")}</td></tr>
      <tr><th>Overridden Anomalies</th><td>${esc(data.anomalies_overridden ?? 0)}</td></tr>
    </tbody></table></div>
  `;
}

function renderFlow(data) {
  return `
    ${renderCards([
      { k: "Transactions", v: data.transactions?.transaction_count ?? 0 },
      { k: "Total Sales", v: eur(data.transactions?.total_sales || 0) },
      { k: "Close Decision", v: data.close_hint || "-", cls: String(data.close_hint || "").includes("Safe") ? "ok" : "warn" },
    ])}
    <h3>Totals Check</h3>
    ${renderValidation(data.totals_validation || {})}
    <h3>Anomalies Summary</h3>
    ${renderAnomalies({ summary: data.anomalies_summary || {}, anomalies: [] })}
  `;
}

function renderResult(kind, data) {
  if (kind === "transactions") return renderTransactions(data);
  if (kind === "validate") return renderValidation(data);
  if (kind === "anomalies") return renderAnomalies(data);
  if (kind === "close") return renderClose(data);
  if (kind === "flow") return renderFlow(data);
  return `<div class="empty">No renderer for result type.</div>`;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const body = await response.json();
  if (!response.ok || body.success === false) {
    throw new Error(body.error?.message || "Request failed.");
  }
  return body;
}

function basePayload() {
  return {
    date: els.date.value,
    tenant_id: "daily-close-local",
  };
}

async function runTool(title, endpoint, payload) {
  setStatus(`Running ${title}...`);
  const body = await postJson(endpoint, payload);
  const kind = endpoint.includes("get_pos_transactions")
    ? "transactions"
    : endpoint.includes("validate_pos_totals")
      ? "validate"
      : endpoint.includes("detect_anomalies")
        ? "anomalies"
        : "close";
  setSourceChip(body.data?.data_source);
  els.output.innerHTML = renderResult(kind, body.data);
  setStatus(`${title} completed.`);
  return body.data;
}

els.btnTransactions.addEventListener("click", async () => {
  try {
    const payload = { ...basePayload(), pos_profile: els.profile.value.trim() || null };
    await runTool("Get Transactions", "/tools/daily_close/get_pos_transactions", payload);
  } catch (err) {
    setStatus(err.message, true);
  }
});

els.btnValidate.addEventListener("click", async () => {
  try {
    await runTool("Validate Totals", "/tools/daily_close/validate_pos_totals", basePayload());
  } catch (err) {
    setStatus(err.message, true);
  }
});

els.btnAnomalies.addEventListener("click", async () => {
  try {
    await runTool("Detect Anomalies", "/tools/daily_close/detect_anomalies", basePayload());
  } catch (err) {
    setStatus(err.message, true);
  }
});

els.btnClose.addEventListener("click", async () => {
  try {
    const payload = { ...basePayload(), force_close: Boolean(els.forceClose.checked) };
    await runTool("Close POS Session", "/tools/daily_close/close_pos_session", payload);
  } catch (err) {
    setStatus(err.message, true);
  }
});

els.btnFlow.addEventListener("click", async () => {
  try {
    const common = basePayload();
    const tx = await runTool("Step 1 - Get Transactions", "/tools/daily_close/get_pos_transactions", {
      ...common,
      pos_profile: els.profile.value.trim() || null,
    });
    const totals = await runTool("Step 2 - Validate Totals", "/tools/daily_close/validate_pos_totals", common);
    const anomalies = await runTool("Step 3 - Detect Anomalies", "/tools/daily_close/detect_anomalies", common);

    const flowData = {
      transactions: {
        transaction_count: tx.transaction_count,
        total_sales: tx.total_sales,
      },
      totals_validation: totals,
      anomalies_summary: anomalies.summary,
      close_hint: anomalies.summary?.safe_to_close ? "Safe to close" : "Not safe to close unless force_close=true",
    };
    els.output.innerHTML = renderResult("flow", flowData);
    setStatus("Full flow completed.");
  } catch (err) {
    setStatus(err.message, true);
  }
});

els.btnClear.addEventListener("click", () => {
  els.output.innerHTML = '<div class="empty">No execution yet.</div>';
  setSourceChip("");
  setStatus("Ready.");
});
