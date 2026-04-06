const API_BASE = "http://localhost:8001/api/v1";

const STAGES = [
    { id: "domain_intelligence", name: "Domain Intelligence", desc: "Analyzing company profile and market positioning", pct: 12 },
    { id: "competitor_discovery", name: "Competitor Analysis", desc: "Identifying and profiling market competitors", pct: 25 },
    { id: "web_intelligence", name: "Web Intelligence", desc: "Scraping competitor websites for technical data", pct: 38 },
    { id: "data_cleaning", name: "Data Cleaning", desc: "Filtering noise and structuring unstructured data", pct: 50 },
    { id: "gap_analysis", name: "Gap Analysis", desc: "Finding untapped opportunities and pain points", pct: 62 },
    { id: "icp_generation", name: "ICP Generation", desc: "Building Ideal Customer Profiles", pct: 75 },
    { id: "persona_generation", name: "Persona Mapping", desc: "Mapping target buyer personas", pct: 88 },
    { id: "outreach_generation", name: "Outreach Generation", desc: "Crafting personalized multi-channel copy", pct: 100 }
];

let currentJobId = null;
let pollInterval = null;

// ─── Pipeline Submission ──────────────────────────────────────────────────────

async function startPipeline() {
    const companyName = document.getElementById("companyName").value.trim();
    if (!companyName) return alert("Please enter a company name");

    const syncMode = document.getElementById("syncMode").checked;
    const url = syncMode ? `${API_BASE}/pipeline/run/sync` : `${API_BASE}/pipeline/run`;

    const payload = {
        company_name: companyName,
        product_description: document.getElementById("productDescription").value.trim() || "AI-powered B2B sales intelligence platform.",
        industry: document.getElementById("industry").value.trim() || "B2B SaaS",
        target_geography: document.getElementById("geography").value.trim() || "Global",
        pricing_model: document.getElementById("pricingModel").value,
        customer_type: document.getElementById("customerType").value,
        core_problem_solved: document.getElementById("coreProblem").value.trim() || "Inefficiency in B2B sales development processes.",
        website: document.getElementById("website").value.trim() || null,
        product_features: [],
        tech_stack: []
    };

    resetUI();
    setLoading(true);

    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            const detail = typeof err.detail === 'object' ? JSON.stringify(err.detail, null, 2) : err.detail;
            throw new Error(`Pipeline Error: ${detail || "Unknown error"}`);
        }

        const data = await response.json();

        if (syncMode) {
            // Mark all stages as done instantly since it's synchronous
            applyProgressPct(100);
            renderFinalResult(data);
            setLoading(false);
        } else {
            currentJobId = data.job_id;
            document.getElementById("jobIdDisplay").innerText = `Job: ${currentJobId.slice(0, 8)}…`;
            startPolling();
        }
    } catch (err) {
        alert(err.message);
        setLoading(false);
        renderError(err.message);
    }
}

// ─── Fill demo data ───────────────────────────────────────────────────────────

function fillDemoData() {
    document.getElementById("companyName").value = "Acme Logistics";
    document.getElementById("productDescription").value = "AI-powered freight forwarding and supply chain management platform for global shipping.";
    document.getElementById("industry").value = "Logistics Tech";
    document.getElementById("geography").value = "North America & Europe";
    document.getElementById("pricingModel").value = "subscription";
    document.getElementById("customerType").value = "B2B";
    document.getElementById("coreProblem").value = "Real-time visibility and fragmented supply chains in ocean freight.";
    document.getElementById("website").value = "https://acme-logistics.com";
}

// ─── Polling ──────────────────────────────────────────────────────────────────

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);

    // Show a small initial pulse on the first stage immediately
    applyProgressPct(2);

    pollInterval = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE}/pipeline/status/${currentJobId}`);
            if (!resp.ok) { console.warn("Status fetch failed:", resp.status); return; }
            const status = await resp.json();

            applyStatusUpdate(status);

            if (status.state === "SUCCESS") {
                clearInterval(pollInterval);
                applyProgressPct(100);
                await fetchResult();
            } else if (status.state === "FAILURE") {
                clearInterval(pollInterval);
                renderError(status.error || "Pipeline failed. Check your Celery worker logs.");
                setLoading(false);
            }
        } catch (e) {
            console.error("Polling error", e);
        }
    }, 2000);
}

async function fetchResult() {
    try {
        const resp = await fetch(`${API_BASE}/pipeline/result/${currentJobId}`);
        const result = await resp.json();
        renderFinalResult(result);
        setLoading(false);
    } catch (e) {
        console.error("Result fetch error", e);
        setLoading(false);
    }
}

// ─── Progress Rendering ───────────────────────────────────────────────────────

function applyStatusUpdate(status) {
    const state = status.state || "PENDING";
    document.getElementById("jobIdDisplay").innerText =
        `State: ${state}` + (currentJobId ? ` · Job: ${currentJobId.slice(0, 8)}…` : "");

    // Use numeric progress from the backend callback (set by on_progress in tasks.py)
    const backendPct = status.progress || 0;

    if (state === "PENDING") {
        applyProgressPct(2); // just a pulse — job is queued
    } else if (state === "RUNNING" || state === "STARTED") {
        applyProgressPct(backendPct > 0 ? backendPct : 10);
    }
    // SUCCESS is handled by the caller
}

function applyProgressPct(pct) {
    const progressBar = document.getElementById("progressBar");
    const progressText = document.getElementById("progressText");

    progressBar.style.width = `${pct}%`;
    progressText.innerText = `${Math.round(pct)}%`;

    // Light up completed stages based on threshold percentage
    STAGES.forEach(stage => {
        const stepEl = document.getElementById(`step-${stage.id}`);
        if (stepEl && pct >= stage.pct) {
            stepEl.classList.add("active");
        }
    });
}

// ─── Result & Error Rendering ─────────────────────────────────────────────────

function renderFinalResult(data) {
    const resultArea = document.getElementById("finalResult");
    resultArea.style.display = "block";

    // Build a prettier summary card instead of raw JSON
    const companySummary = data.company_id ? `<p style="color:var(--text-muted); font-size:0.85rem; margin-bottom:1rem;">Company ID: ${data.company_id}</p>` : "";
    const duration = data.duration_seconds ? `<div class="status-pill" style="width:fit-content; margin-bottom:1.5rem;">⏱ Completed in ${data.duration_seconds.toFixed(1)}s</div>` : "";
    const errors = data.errors && data.errors.length
        ? `<div style="color:var(--error); margin-top:1rem; font-size:0.85rem;">⚠ ${data.errors.join("<br>")}</div>` : "";

    resultArea.innerHTML = `
        <div class="card animate-fade">
            <h2 class="card-title">✅ Pipeline Complete</h2>
            ${companySummary}
            ${duration}
            <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:12px; margin-bottom:1.5rem;">
                ${stat("ICPs", data.icps?.length || 0)}
                ${stat("Personas", data.personas?.length || 0)}
                ${stat("Competitors", data.competitors?.length || 0)}
                ${stat("Market Gaps", data.market_gaps?.length || 0)}
                ${stat("Outreach Assets", data.outreach_assets?.length || 0)}
            </div>
            ${errors}
            <details style="margin-top:1.5rem;">
                <summary style="cursor:pointer; color:var(--text-muted); font-size:0.9rem;">View Raw JSON ▾</summary>
                <div class="code-block" style="margin-top:1rem; max-height:500px; overflow-y:auto;">${escapeHtml(JSON.stringify(data, null, 2))}</div>
            </details>
        </div>
    `;
    resultArea.scrollIntoView({ behavior: 'smooth' });
}

function stat(label, value) {
    return `<div class="card" style="padding:1rem; margin:0; text-align:center;">
        <div style="font-size:1.8rem; font-weight:800; color:var(--primary);">${value}</div>
        <div style="font-size:0.8rem; color:var(--text-muted);">${label}</div>
    </div>`;
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderError(msg) {
    const resultArea = document.getElementById("finalResult");
    resultArea.style.display = "block";
    resultArea.innerHTML = `
        <div class="card" style="border-color: var(--error)">
            <h2 class="card-title" style="color: var(--error)">⚠ Pipeline Error</h2>
            <p style="font-family:var(--font-mono); font-size:0.85rem; white-space:pre-wrap;">${msg}</p>
        </div>
    `;
    setLoading(false);
}

// ─── UI Helpers ───────────────────────────────────────────────────────────────

function resetUI() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    applyProgressPct(0);
    document.getElementById("progressText").innerText = "0%";
    document.getElementById("jobIdDisplay").innerText = "State: IDLE";
    document.getElementById("finalResult").style.display = "none";
    document.querySelectorAll(".step-item").forEach(s => s.classList.remove("active"));
}

function setLoading(isLoading) {
    const btn = document.getElementById("startBtn");
    btn.disabled = isLoading;
    btn.innerHTML = isLoading
        ? `<span style="display:inline-block;width:14px;height:14px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;"></span> Executing Pipeline…`
        : "Execute Workflow";
}

// ─── Build Timeline on Load ───────────────────────────────────────────────────

window.onload = () => {
    const timeline = document.getElementById("stepsTimeline");
    STAGES.forEach(stage => {
        const div = document.createElement("div");
        div.className = "step-item";
        div.id = `step-${stage.id}`;
        div.innerHTML = `
            <div class="step-icon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"/>
                </svg>
            </div>
            <div class="step-info">
                <div class="step-name">${stage.name}</div>
                <div class="step-desc">${stage.desc}</div>
            </div>
        `;
        timeline.appendChild(div);
    });
};
