// DutyBack front end. Plain JavaScript, no build step.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const money = (x) => "$" + Number(x || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money0 = (x) => "$" + Math.round(Number(x || 0)).toLocaleString("en-US");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (iso) => iso ? new Date(iso + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—";
const COLORS = { file_now: "var(--file_now)", fix_first: "var(--fix_first)", protest: "var(--protest)", broker: "var(--broker)",
  no_route: "var(--no_route)", not_refundable: "var(--not_refundable)", review: "var(--review)" };
const FLAG_TEXT = {
  statement_conflict: "Statement total differs from line detail",
  amount_from_statement_only: "Amount from broker statement only",
  value_on_ch99_line: "Value reported on a Chapter 99 line",
  not_extracted: "Could not be read",
  lookalike_characters: "Look-alike characters in the entry number",
};

let STATUS = null, selected = null, currentJob = null, RESULT = null, pollTimer = null;

async function init() {
  STATUS = await (await fetch("/api/status")).json();
  $("#snap").textContent = fmtDate(STATUS.rules_snapshot);
  const pill = $("#modePill");
  if (STATUS.mode === "live") { pill.textContent = `Live: ${STATUS.engine || "AI agents"}`; pill.classList.add("live"); }
  else { pill.textContent = "Demo mode: recorded runs"; }
  $("#asOf").value = STATUS.today;
  $("#samples").innerHTML = STATUS.samples.map((s) => `
    <button class="sample" data-slug="${s.slug}">
      <b>${esc(s.name)}</b>
      <div class="what">${esc(s.what)}</div>
      <div class="docs">${esc(s.docs)}</div>
      <div class="files">${s.files.map((f) => `<a href="/api/samples/${s.slug}/${encodeURIComponent(f)}" target="_blank" onclick="event.stopPropagation()">${esc(f.replace(/^\d_/, "").replace(/_/g, " ").replace(".pdf", ""))}</a>`).join("")}</div>
    </button>`).join("");
  $$(".sample").forEach((b) => b.addEventListener("click", () => pickSample(b.dataset.slug)));
  $("#fileInput").addEventListener("change", (e) => {
    const fs = [...e.target.files];
    if (fs.length) { selected = { files: fs }; $$(".sample").forEach((x) => x.classList.remove("sel")); }
    $("#fileNames").textContent = fs.map((f) => f.name).join(", ");
    $("#runBtn").disabled = !fs.length;
    note();
  });
  if (STATUS.mode === "demo") $("#uploadLabel").classList.add("hidden");
  $("#runBtn").addEventListener("click", start);
  $$(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));
  $("#drawerClose").addEventListener("click", closeDrawer);
  $("#drawer").addEventListener("click", (e) => { if (e.target.id === "drawer") closeDrawer(); });
  note();
}

function note() {
  const n = $("#runNote");
  if (STATUS.mode === "demo") n.textContent = "Demo mode replays a real recorded run of the sample you pick, checked as of Oct 24, 2026.";
  else n.textContent = "Takes about 1.5 to 3 minutes. AI agents read and explain; code checks what they extract and makes every decision.";
}

function pickSample(slug) {
  selected = { sample: slug };
  $$(".sample").forEach((x) => x.classList.toggle("sel", x.dataset.slug === slug));
  $("#fileNames").textContent = "";
  $("#runBtn").disabled = false;
  if (["lotus", "northtrail", "casaverde", "meridian"].includes(slug)) $("#asOf").value = "2026-10-24";
}

async function start() {
  if (!selected) return;
  const fd = new FormData();
  fd.append("as_of", $("#asOf").value);
  if (selected.sample) fd.append("sample", selected.sample);
  else selected.files.forEach((f) => fd.append("files", f));
  $("#runBtn").disabled = true;
  $("#results").classList.add("hidden");
  $("#errorBox").classList.add("hidden");
  $("#progress").classList.remove("hidden");
  renderSteps({});
  const r = await fetch("/api/runs", { method: "POST", body: fd });
  const j = await r.json();
  if (!r.ok) { showError(j.detail || "Could not start."); return; }
  currentJob = j.id;
  $("#replayNote").classList.toggle("hidden", j.mode !== "demo");
  $("#progress").scrollIntoView({ behavior: "smooth", block: "start" });
  poll();
}

function renderSteps(steps) {
  $("#steps").innerHTML = STATUS.steps.map((s) => {
    const st = steps[s.key] || { status: "pending", detail: "" };
    const agent = /agent/i.test(s.who);
    return `<li class="${st.status}"><span class="dot"></span>
      <div><div>${esc(s.title)}</div><div class="detail">${esc(st.detail)}</div></div>
      <span class="who ${agent ? "agent" : ""}">${esc(s.who)}</span></li>`;
  }).join("");
}

async function poll() {
  clearTimeout(pollTimer);
  const j = await (await fetch(`/api/runs/${currentJob}`)).json();
  renderSteps(j.steps);
  $("#elapsed").textContent = `· ${Math.round(j.elapsed)}s`;
  if (j.state === "running") { pollTimer = setTimeout(poll, 900); return; }
  $("#runBtn").disabled = false;
  if (j.state === "error") { showError(j.error); return; }
  RESULT = j.result;
  renderResults();
}

function showError(msg) {
  const b = $("#errorBox");
  b.textContent = msg;
  b.classList.remove("hidden");
  $("#runBtn").disabled = false;
}

function renderResults() {
  const R = RESULT, S = R.summary, B = S.buckets;
  $("#results").classList.remove("hidden");
  $("#resImporter").textContent = (R.importer?.name || "Your company") + (R.replayed ? " · recorded run" : "");
  const claimable = B.file_now.amount + B.fix_first.amount;
  $("#resHeadline").textContent = `${money0(claimable)} can go into CAPE now or after one fix. ${money0(B.protest.amount)} needs a protest.`;
  $("#resMeta").textContent = `${S.entries} entries · ${money(S.ieepa_paid)} IEEPA duty paid · deadlines as of ${fmtDate(S.as_of)} · rules as of ${fmtDate(S.rules_snapshot)}`;
  const risk = $("#riskBanner");
  if (S.at_risk_this_week.count) {
    risk.innerHTML = `Money at risk this week<b>${money(S.at_risk_this_week.amount)}</b><span class="small">${S.at_risk_this_week.count} entr${S.at_risk_this_week.count === 1 ? "y" : "ies"} with a deadline in the next 7 days</span>`;
    risk.classList.remove("hidden");
  } else risk.classList.add("hidden");
  const warns = [...(R.warnings || [])];
  const removed = (R.screen?.removed_lines || []).length, hidden = R.screen?.hidden_chars_dropped || 0;
  if (removed || hidden) warns.push(`The safety screen removed ${removed} line(s) that looked like instructions to an AI and ${hidden} character(s) of text a person couldn't see. See "How this was made".`);
  const review = R.entries.filter((e) => e.bucket === "review").length;
  if (review) warns.push(`${review} entr${review === 1 ? "y needs" : "ies need"} a person to check: something couldn't be verified in your documents, or the documents contradict themselves. They are left out of the CAPE file.`);
  $("#warnBox").innerHTML = warns.length ? `<b>Before you act</b><ul>${warns.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : "";
  $("#warnBox").classList.toggle("hidden", !warns.length);
  const order = ["file_now", "fix_first", "protest", "no_route", "broker", "review"];
  $("#buckets").innerHTML = order.map((k) => `
    <div class="bucket" style="--c:${COLORS[k]}">
      <div class="lbl">${esc(B[k].label)}</div>
      <div class="amt">${money0(B[k].amount)}</div>
      <div class="cnt">${B[k].count} entr${B[k].count === 1 ? "y" : "ies"}</div>
    </div>`).join("");
  renderEntries(); renderPlan(); renderTimeline(); renderFiles(); renderHow(); renderRules();
  showTab("entries");
  setTimeout(() => $("#results").scrollIntoView({ behavior: "smooth", block: "start" }), 150);
}

function showTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $$(".tabpane").forEach((p) => p.classList.toggle("hidden", p.id !== "tab-" + name));
}

function daysText(e) {
  if (e.days_left == null) return "";
  if (e.days_left === 0) return `<span class="days urgent">today</span>`;
  return `<span class="days ${e.urgent ? "urgent" : ""}">${e.days_left} days left</span>`;
}

function flagsHtml(e) {
  return (e.flags || []).filter((f) => !f.startsWith("unverified:")).map((f) => `<span class="flag warn">${esc(FLAG_TEXT[f] || f)}</span>`).join("")
    + (e.repaired ? `<span class="flag">Fixed on re-read</span>` : "");
}

function renderEntries() {
  const rows = RESULT.entries.map((e, i) => `
    <tr class="row" data-i="${i}">
      <td class="mono">${esc(e.entry_number)}</td>
      <td><span class="chip" style="--c:${COLORS[e.bucket]}">${esc(e.label)}</span><div>${flagsHtml(e)}</div></td>
      <td class="num">${e.bucket === "not_refundable" || e.bucket === "review" ? "—" : money(e.refund_amount)}</td>
      <td>${fmtDate(e.deadline)}<div>${daysText(e)}</div></td>
      <td class="small muted">${esc(e.liquidation_status === "liquidated" ? "Liquidated " + fmtDate(e.liquidation_date) : (e.liquidation_status || ""))}</td>
    </tr>`).join("");
  $("#tab-entries").innerHTML = `<p class="small muted">Sorted by deadline. Click an entry to see the quotes from your documents and every check it passed.</p>
    <table><thead><tr><th>Entry</th><th>What to do</th><th style="text-align:right">IEEPA refund</th><th>Deadline</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
  $$("#tab-entries tr.row").forEach((r) => r.addEventListener("click", () => openEntry(RESULT.entries[r.dataset.i])));
}

function openEntry(e) {
  const ev = e.evidence || {};
  const quotes = ["entry", "liquidation", "flags", "ieepa_statement"].filter((k) => ev[k])
    .map((k) => `<div class="small muted">${{ entry: "Entry", liquidation: "Liquidation", flags: "Flags", ieepa_statement: "Stated IEEPA amount" }[k]}</div><div class="quote">${esc(ev[k])}</div>`).join("");
  const lines = (e.lines || []).map((ln) => `
    <tr><td colspan="4"><b>${esc(ln.line_no)}</b> ${esc(ln.description || "")}</td></tr>
    ${(ln.hts || []).map((h) => {
      const c = String(h.code).replace(/\D/g, "");
      const ieepa = c.startsWith("990301") || c.startsWith("990302");
      const tag = ieepa ? `<span class="flag warn">IEEPA</span>` : (c.startsWith("9903") ? `<span class="flag">not IEEPA</span>` : "");
      return `<tr><td class="mono">${esc(h.code)} ${tag}</td><td class="num">${h.entered_value != null ? money(h.entered_value) : ""}</td><td class="num">${h.rate != null ? (h.rate * 100).toFixed(1).replace(/\.0$/, "") + "%" : ""}</td><td class="num">${money(h.duty)}</td></tr>`;
    }).join("")}`).join("");
  const checks = (e.checks || []).map((c) => `<div class="check ${c.ok ? "ok" : "bad"}">${esc(c.check)}${!c.ok && c.detail ? ` <span class="muted">(${esc(c.detail)})</span>` : ""}</div>`).join("") || `<div class="small muted">No checks recorded.</div>`;
  $("#drawerBody").innerHTML = `
    <div class="eyebrow">Entry</div><h2 class="mono">${esc(e.entry_number)}</h2>
    <p><span class="chip" style="--c:${COLORS[e.bucket]}">${esc(e.label)}</span> ${daysText(e)}</p>
    <p>${esc(e.reason)}</p>
    <div class="kv small">
      <span class="muted">IEEPA refund</span><b>${e.bucket === "not_refundable" ? "None" : money(e.refund_amount)}</b>
      <span class="muted">Deadline</span><span>${fmtDate(e.deadline)}</span>
      <span class="muted">Entry type</span><span>${esc(e.entry_type || "")}</span>
      <span class="muted">Entry date</span><span>${fmtDate(e.entry_date)}</span>
      <span class="muted">Liquidation</span><span>${esc(e.liquidation_status || "")} ${e.liquidation_date ? fmtDate(e.liquidation_date) : ""}${e.days_since_liquidation != null ? ` (${e.days_since_liquidation} days ago)` : ""}</span>
      <span class="muted">Found in</span><span>${esc((e.source_docs || []).join(", "))}</span>
    </div>
    <h3 style="margin-top:16px;font-size:15px">What your documents say</h3>${quotes || '<p class="small muted">No quotes.</p>'}
    ${lines ? `<h3 style="margin-top:16px;font-size:15px">Duty lines</h3><table>${lines}</table>` : ""}
    <h3 style="margin-top:16px;font-size:15px">Checks run by code</h3>${checks}`;
  $("#drawer").classList.remove("hidden");
}
function closeDrawer() { $("#drawer").classList.add("hidden"); }

function renderPlan() {
  const P = RESULT.plan || {};
  const steps = (P.steps || []).map((s) => {
    const d = s.deadline ? Math.round((new Date(s.deadline) - new Date(RESULT.as_of)) / 864e5) : null;
    return `<div class="plan-step"><div class="when ${d != null && d <= 14 ? "urgent" : ""}">${s.deadline ? "By " + fmtDate(s.deadline) : "When you can"}</div>
      <div><h4>${esc(s.title)}</h4><div>${esc(s.detail)}</div>${(s.entries || []).length ? `<div class="small muted mono">${s.entries.map(esc).join(" · ")}</div>` : ""}</div></div>`;
  }).join("");
  const removed = (RESULT.plan_removed_sentences || []).length;
  $("#tab-plan").innerHTML = `
    <h3 style="font-size:17px;margin-bottom:6px">${esc(P.headline || "")}</h3>
    ${steps}
    <h3 style="font-size:16px;margin:20px 0 6px">Draft email to your broker</h3>
    <div class="small muted">Subject: ${esc(P.broker_email_subject || "")}</div>
    <div class="email" id="emailBody">${esc(P.broker_email_body || "")}</div>
    <button class="btn" id="copyEmail">Copy email</button>
    <p class="small muted">Written by the Advisor agent from the rules engine's results. Code checked every dollar amount, date and entry number against those results${removed ? ` and removed ${removed} sentence${removed === 1 ? "" : "s"} that didn't match` : ""}. Not legal advice.</p>`;
  $("#copyEmail").addEventListener("click", () => {
    navigator.clipboard.writeText(`Subject: ${P.broker_email_subject}\n\n${P.broker_email_body}`);
    $("#copyEmail").textContent = "Copied";
  });
}

function renderTimeline() {
  const withD = RESULT.entries.filter((e) => e.deadline).sort((a, b) => a.days_left - b.days_left);
  const max = Math.max(30, ...withD.map((e) => e.days_left));
  const rows = withD.map((e) => `
    <div class="tl-row"><span class="mono small">${esc(e.entry_number)}</span>
      <div class="tl-track"><div class="tl-bar" style="--c:${COLORS[e.bucket]};width:${Math.max(1, (e.days_left / max) * 100)}%"></div></div>
      <span class="small"><b>${fmtDate(e.deadline)}</b> · ${money0(e.refund_amount)}</span></div>`).join("");
  const noD = RESULT.entries.filter((e) => !e.deadline && ["file_now", "fix_first"].includes(e.bucket));
  $("#tab-timeline").innerHTML = `<p class="small muted">Each bar is the time left before that entry's window closes (CAPE: 80 days after liquidation; protest: 180 days). Every week some money moves from "file online" to "needs a protest", and then to "waiting on the court".</p>
    <div class="tl">${rows || '<p class="muted">No dated deadlines.</p>'}</div>
    ${noD.length ? `<p class="small muted" style="margin-top:12px">${noD.length} unliquidated entr${noD.length === 1 ? "y has" : "ies have"} no deadline yet: the CAPE window opens now and closes 80 days after liquidation.</p>` : ""}`;
}

function renderFiles() {
  const S = RESULT.summary;
  const replay = RESULT.replayed;
  const csvHref = replay ? "data:text/csv;charset=utf-8," + encodeURIComponent(RESULT.files.cape_csv) : `/api/runs/${currentJob}/cape.csv`;
  const icsHref = replay ? "data:text/calendar;charset=utf-8," + encodeURIComponent(RESULT.files.ics) : `/api/runs/${currentJob}/deadlines.ics`;
  $("#tab-files").innerHTML = `<div class="files-grid">
    <div class="card"><h3 style="font-size:16px">CAPE upload list</h3><p class="small">${S.cape_csv_count} entries · ${money(S.cape_csv_amount)}. Entry numbers only, as CBP asks. Compare with the template on the CAPE tab of the ACE Portal before uploading.</p>
      <a class="btn" href="${csvHref}" download="cape_declaration_draft.csv">Download CSV</a></div>
    <div class="card"><h3 style="font-size:16px">Deadline calendar</h3><p class="small">One event per deadline, with reminders 7 days and 1 day before. Works with Google, Outlook and Apple calendars.</p>
      <a class="btn" href="${icsHref}" download="refund_deadlines.ics">Download .ics</a></div>
    <div class="card"><h3 style="font-size:16px">Printable summary</h3><p class="small">Entries, action plan and deadlines on paper, to bring to your broker.</p>
      <button class="btn" onclick="window.print()">Print</button></div></div>
    <h3 style="font-size:15px;margin:16px 0 6px">CSV preview</h3><pre class="email mono">${esc(RESULT.files.cape_csv)}</pre>`;
}

function renderHow() {
  const A = RESULT.agents || [], T = RESULT.totals || {};
  const rows = A.map((a) => `<tr><td>${esc(a.agent)}</td><td class="mono small">${esc(a.model_id || a.model)}</td><td class="num">${a.seconds}s</td>
    <td class="num">${(a.input_tokens + a.cache_read_tokens + a.cache_write_tokens).toLocaleString()} / ${a.output_tokens.toLocaleString()}</td>
    <td class="num">${a.tool_calls.length}</td><td class="num">$${a.cost_usd.toFixed(3)}</td></tr>`).join("");
  const tools = A.flatMap((a) => a.tool_calls.map((t) => `${t.tool}${t.input && Object.keys(t.input).length ? " " + JSON.stringify(t.input) : ""}`));
  const issues = (RESULT.checker?.issues || []).map((i) => `<li><span class="mono">${esc(i.entry_number)}</span> · ${esc(i.kind)} ${i.grounded ? "" : '<span class="flag">dismissed: quote not found</span>'}<div class="small muted">${esc(i.detail)}</div></li>`).join("");
  const allChecks = RESULT.entries.flatMap((e) => e.checks || []);
  const okChecks = allChecks.filter((c) => c.ok).length;
  const scr = RESULT.screen || {};
  $("#tab-how").innerHTML = `
    <p>Three AI agents and plain code, each doing what it is good at. <b>The agents read and explain. Code checks what they extract (quotes, dates, amounts, entry types, flag words) and makes every decision.</b></p>
    <table><thead><tr><th>Agent</th><th>Model</th><th style="text-align:right">Time</th><th style="text-align:right">Tokens in / out</th><th style="text-align:right">Tool calls</th><th style="text-align:right">Cost</th></tr></thead>
    <tbody>${rows}<tr><td><b>Total</b></td><td></td><td class="num"><b>${T.seconds}s</b></td><td class="num">${(T.input_tokens || 0).toLocaleString()} / ${(T.output_tokens || 0).toLocaleString()}</td><td class="num">${T.tool_calls}</td><td class="num"><b>$${(T.cost_usd || 0).toFixed(2)}</b></td></tr></tbody></table>
    <p class="small muted">${(RESULT.agents || []).some((a) => /gpt/i.test(a.model || "")) ? "Cost is computed from the token counts the API reported, at gpt-6-luna list prices ($0.10 / $0.01 cached / $0.50 per million tokens in / cached / out)." : "Cost is what these calls would cost at Claude API list prices, as reported by the Claude Agent SDK."}${RESULT.replayed ? " This is a recorded run." : ""}</p>
    <div class="how-grid">
      <div><h3 style="font-size:15px">Code checks</h3>
        <p class="small">${okChecks} of ${allChecks.length} checks passed. An entry with a failed check on a key fact (or flag words the extraction missed) goes to "Check by hand" and is left out of the CAPE file.</p>
        <h3 style="font-size:15px">Safety screen</h3>
        <p class="small">${scr.pages || 0} pages read · ${(scr.removed_lines || []).length} line(s) matching AI-instruction patterns removed · ${scr.hidden_chars_dropped || 0} invisible (white or tiny) characters dropped.</p>
        ${(scr.removed_lines || []).map((l) => `<div class="quote">${esc(l.doc)} p${l.page}: ${esc(l.line)}</div>`).join("")}
        ${(RESULT.warnings || []).map((w) => `<p class="small error">${esc(w)}</p>`).join("")}
      </div>
      <div><h3 style="font-size:15px">Checker agent</h3>
        <p class="small">${esc(RESULT.checker?.summary || "")}</p>
        <ul class="small">${issues || "<li>No issues found.</li>"}</ul>
        <details><summary class="small">Its ${tools.length} tool calls</summary><div class="mono small">${tools.map(esc).join("<br>")}</div></details>
        ${(RESULT.reader_notes || []).length ? `<h3 style="font-size:15px">Reader's notes</h3><ul class="small">${RESULT.reader_notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
      </div>
    </div>`;
}

function renderRules() {
  const routes = Object.entries(STATUS.routes).map(([k, r]) => `<tr><td><span class="chip" style="--c:${COLORS[r.bucket]}">${esc(r.label)}</span></td><td class="small">${esc(r.reason)}</td></tr>`).join("");
  $("#tab-rules").innerHTML = `<p class="small">These rules are written in plain code (<span class="mono">app/pipeline/rules.py</span>), not decided by an AI. Snapshot: ${fmtDate(STATUS.rules_snapshot)}.</p>
    <table><tbody>${routes}</tbody></table>
    <p class="small muted">Sources: CBP CSMS #68340863 (CAPE Phase 1, Apr 20, 2026); CBP Phase 2 (Jun 29, 2026) and Phase 3 (Oct 6, 2026) announcements; 19 U.S.C. 1514 (protests); Freestyle World, Inc. v. United States, CIT No. 26-01088 (class certified Oct 8, 2026). Section 301 and 232 duties are not part of the IEEPA refund.</p>`;
}

init();
