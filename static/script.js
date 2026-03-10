// ============================================================
// LOS Bureau Rules Engine — Frontend Controller
// ============================================================

const API = {
    templates: '/api/v1/templates',
    companies: '/api/v1/companies',
    evaluate: '/api/v1/evaluate',
    companyRules: (id) => `/api/v1/companies/${id}/rules`,
};

let allTemplates = [];
let allCompanies = [];
let currentCompanyRules = [];
let editingRuleIndex = -1;

// ══════════════════════════════════════════════════════════
// INITIALIZATION
// ══════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', async () => {
    await loadTemplates();
    await loadCompanies();
    populateSimulatorDefaults();
});

// ══════════════════════════════════════════════════════════
// VIEW ROUTER
// ══════════════════════════════════════════════════════════

function switchView(view) {
    document.querySelectorAll('.view-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById(`view-${view}`).classList.add('active');
    document.querySelector(`[data-view="${view}"]`).classList.add('active');

    if (view === 'rules') loadCompanyRules();
    if (view === 'companies') renderCompanies();
}

// ══════════════════════════════════════════════════════════
// 1. VARIABLE LIBRARY
// ══════════════════════════════════════════════════════════

async function loadTemplates() {
    try {
        const res = await fetch(API.templates);
        const data = await res.json();
        allTemplates = data.templates || [];
        document.getElementById('total-var-count').textContent = data.total;
        renderGroupFilters(data.groups);
        renderTemplates(allTemplates);
    } catch (e) {
        console.error('Failed to load templates', e);
    }
}

function renderGroupFilters(groups) {
    const bar = document.getElementById('group-filter-bar');
    bar.innerHTML = `<button class="group-btn active" onclick="filterTemplates('all', this)">All (${Object.values(groups).reduce((a, b) => a + b, 0)})</button>`;
    for (const [name, count] of Object.entries(groups)) {
        bar.innerHTML += `<button class="group-btn" onclick="filterTemplates('${name}', this)">${name} (${count})</button>`;
    }
}

function filterTemplates(group, btn) {
    document.querySelectorAll('.group-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if (group === 'all') {
        renderTemplates(allTemplates);
    } else {
        renderTemplates(allTemplates.filter(t => t.group === group));
    }
}

function renderTemplates(templates) {
    const container = document.getElementById('templates-container');
    if (!templates.length) {
        container.innerHTML = '<div class="empty-state"><p>No variables found</p></div>';
        return;
    }
    const groupColors = {
        'Bureau Score': 'badge-gold',
        'DPD': 'badge-red',
        'Enquiry': 'badge-blue',
        'Loan Account': 'badge-purple',
        'Vintage': 'badge-green',
        'Cards': 'badge-orange',
    };
    container.innerHTML = templates.map(t => `
        <div class="template-card">
            <div class="template-card-top">
                <span class="badge ${groupColors[t.group] || 'badge-blue'}">${t.group}</span>
                <span class="template-id">#${t.template_id}</span>
            </div>
            <div class="template-name">${t.variable_name}</div>
            <div class="template-meta">
                <span class="template-col">${t.db_column}</span>
                <span class="template-filter">${t.status_filter}</span>
            </div>
        </div>
    `).join('');
}

// ══════════════════════════════════════════════════════════
// 2. COMPANIES
// ══════════════════════════════════════════════════════════

async function loadCompanies() {
    try {
        const res = await fetch(API.companies);
        allCompanies = await res.json();
        document.getElementById('total-company-count').textContent = allCompanies.length;
        populateCompanySelectors();
        renderCompanies();
    } catch (e) {
        console.error('Failed to load companies', e);
    }
}

function populateCompanySelectors() {
    const selectors = ['company-selector', 'sim-company-selector'];
    selectors.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.innerHTML = allCompanies.map(c => `<option value="${c.company_id}">${c.company_name}</option>`).join('');
    });
}

function renderCompanies() {
    const container = document.getElementById('companies-container');
    if (!allCompanies.length) {
        container.innerHTML = '<div class="empty-state"><p>No companies configured</p></div>';
        return;
    }
    container.innerHTML = allCompanies.map(c => `
        <div class="company-card">
            <div class="company-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
            </div>
            <div class="company-name">${c.company_name}</div>
            <div class="company-id">${c.company_id}</div>
            <div class="company-rules-count">${c.rule_count} rules configured</div>
        </div>
    `).join('');
}

function showCreateCompany() {
    const name = prompt('Enter company name:');
    if (!name) return;
    const id = prompt('Enter unique company ID (lowercase, no spaces):', name.toLowerCase().replace(/\s+/g, '-'));
    if (!id) return;
    fetch(API.companies, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_id: id, company_name: name })
    }).then(() => { loadCompanies(); showToast('Company created'); });
}

// ══════════════════════════════════════════════════════════
// 3. COMPANY RULES
// ══════════════════════════════════════════════════════════

async function loadCompanyRules() {
    const companyId = document.getElementById('company-selector').value;
    if (!companyId) return;
    try {
        const res = await fetch(API.companyRules(companyId));
        const data = await res.json();
        currentCompanyRules = data.rules || [];
        renderRules();
    } catch (e) {
        console.error('Failed to load rules', e);
    }
}

function renderRules() {
    const container = document.getElementById('rules-container');
    if (!currentCompanyRules.length) {
        container.innerHTML = '<div class="empty-state"><p>No rules configured. Click "Add Rule" to get started.</p></div>';
        return;
    }
    container.innerHTML = currentCompanyRules.map((r, i) => {
        const tmpl = allTemplates.find(t => t.template_id === r.template_id) || {};
        const active = r.active_flag !== false;
        return `
        <div class="rule-listItem ${!active ? 'rule-inactive' : ''}">
            <div class="rule-listItem-header">
                <div class="rule-name-wrapper">
                    <span class="rule-name">${r.rule_name}</span>
                    ${r.hard_reject ? '<span class="badge badge-red">HARD REJECT</span>' : ''}
                    ${!active ? '<span class="badge badge-dim">INACTIVE</span>' : ''}
                </div>
                <div class="rule-listItem-actions">
                    <button class="icon-button" onclick="editRule(${i})" title="Edit"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
                    <button class="icon-button danger" onclick="deleteRule('${r.rule_id}')" title="Deactivate"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14H7L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg></button>
                </div>
            </div>
            <div class="rule-desc">${tmpl.variable_name || ''} &mdash; ${tmpl.db_column || ''}</div>
            <div class="rule-params-grid">
                <div class="param-item"><span class="key">Operator</span><span class="val highlight">${r.operator} ${r.threshold_value}</span></div>
                <div class="param-item"><span class="key">Weight</span><span class="val">${r.score_weight}</span></div>
                <div class="param-item"><span class="key">Pass Score</span><span class="val">${r.score_on_pass}</span></div>
                <div class="param-item"><span class="key">Fail Score</span><span class="val">${r.score_on_fail}</span></div>
                <div class="param-item"><span class="key">Template</span><span class="val">#${r.template_id}</span></div>
            </div>
        </div>
    `}).join('');
}

function openAddRule() {
    editingRuleIndex = -1;
    document.getElementById('slideover-title').textContent = 'Add Rule';
    populateTemplateDropdown();
    document.getElementById('rule-form').reset();
    document.getElementById('rf-weight').value = '1.0';
    document.getElementById('rf-score-pass').value = '100';
    document.getElementById('rf-score-fail').value = '0';
    document.getElementById('rule-slide-over').classList.add('open');
}

function editRule(index) {
    editingRuleIndex = index;
    const r = currentCompanyRules[index];
    document.getElementById('slideover-title').textContent = 'Edit Rule';
    populateTemplateDropdown();
    document.getElementById('rf-template').value = r.template_id;
    document.getElementById('rf-name').value = r.rule_name;
    document.getElementById('rf-operator').value = r.operator;
    document.getElementById('rf-threshold').value = r.threshold_value;
    document.getElementById('rf-pass-outcome').value = r.pass_outcome || 'PASS';
    document.getElementById('rf-weight').value = r.score_weight;
    document.getElementById('rf-score-pass').value = r.score_on_pass;
    document.getElementById('rf-score-fail').value = r.score_on_fail;
    document.getElementById('rf-hard-reject').checked = r.hard_reject;
    document.getElementById('rule-slide-over').classList.add('open');
}

function closeSlideOver() {
    document.getElementById('rule-slide-over').classList.remove('open');
}

function populateTemplateDropdown() {
    const sel = document.getElementById('rf-template');
    sel.innerHTML = allTemplates.map(t => `<option value="${t.template_id}">[${t.group}] ${t.variable_name} (${t.db_column})</option>`).join('');
}

function onTemplateSelect() {
    const tid = parseInt(document.getElementById('rf-template').value);
    const t = allTemplates.find(x => x.template_id === tid);
    if (t && !document.getElementById('rf-name').value) {
        document.getElementById('rf-name').value = t.variable_name;
    }
}

async function saveRule() {
    const companyId = document.getElementById('company-selector').value;
    const rule = {
        template_id: parseInt(document.getElementById('rf-template').value),
        rule_name: document.getElementById('rf-name').value,
        operator: document.getElementById('rf-operator').value,
        threshold_value: document.getElementById('rf-threshold').value,
        pass_outcome: document.getElementById('rf-pass-outcome').value,
        score_weight: parseFloat(document.getElementById('rf-weight').value) || 1.0,
        score_on_pass: parseFloat(document.getElementById('rf-score-pass').value) || 100,
        score_on_fail: parseFloat(document.getElementById('rf-score-fail').value) || 0,
        hard_reject: document.getElementById('rf-hard-reject').checked,
        active_flag: true,
    };

    if (editingRuleIndex >= 0) {
        const existing = currentCompanyRules[editingRuleIndex];
        await fetch(`/api/v1/companies/${companyId}/rules/${existing.rule_id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(rule)
        });
        showToast('Rule updated');
    } else {
        await fetch(API.companyRules(companyId), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(rule)
        });
        showToast('Rule added');
    }
    closeSlideOver();
    loadCompanyRules();
}

async function deleteRule(ruleId) {
    if (!confirm('Deactivate this rule?')) return;
    const companyId = document.getElementById('company-selector').value;
    await fetch(`/api/v1/companies/${companyId}/rules/${ruleId}`, { method: 'DELETE' });
    showToast('Rule deactivated');
    loadCompanyRules();
}

// ══════════════════════════════════════════════════════════
// 4. LIVE SIMULATOR
// ══════════════════════════════════════════════════════════

function populateSimulatorDefaults() {
    document.getElementById('eval-json-input').value = JSON.stringify({
        "company_id": "demo-lender-001",
        "application_id": "SIM-001",
        "bureau_pull_date": "2026-02-01T00:00:00",
        "bureau_score": 780,
        "tradelines": [
            {
                "loan_type": "HL",
                "loan_status": "Active",
                "loan_sec_status": "Secured",
                "reported_date": "2026-01-01T00:00:00",
                "loan_disb_date": "2023-06-01T00:00:00",
                "loan_disb_amt": 2500000,
                "loan_outstanding_bal": 1800000,
                "loan_overdue_amt": 0,
                "repayment_history": "000000000000000000000000"
            },
            {
                "loan_type": "PL",
                "loan_status": "Active",
                "loan_sec_status": "Unsecured",
                "reported_date": "2026-01-01T00:00:00",
                "loan_disb_date": "2025-03-01T00:00:00",
                "loan_disb_amt": 300000,
                "loan_outstanding_bal": 180000,
                "loan_overdue_amt": 0,
                "repayment_history": "000030000000000000"
            },
            {
                "loan_type": "CC",
                "loan_status": "Active",
                "loan_sec_status": "Card",
                "reported_date": "2026-01-01T00:00:00",
                "loan_disb_amt": 100000,
                "credit_limit": 200000,
                "current_balance": 45000,
                "loan_overdue_amt": 0,
                "repayment_history": "000000000000"
            }
        ],
        "enquiries": [
            { "loan_enq_date": "2026-01-15T00:00:00", "loan_enq_type": "PL", "loan_enq_amt": 200000, "loan_sec_status": "Unsecured" },
            { "loan_enq_date": "2025-11-01T00:00:00", "loan_enq_type": "HL", "loan_enq_amt": 3000000, "loan_sec_status": "Secured" }
        ]
    }, null, 2);
}

async function runSimulation() {
    const inputStr = document.getElementById('eval-json-input').value;
    const resBox = document.getElementById('eval-results-container');
    const btn = document.getElementById('run-eval-btn');

    try {
        btn.textContent = 'Evaluating...';
        btn.disabled = true;

        let payload;
        try {
            payload = JSON.parse(inputStr);
        } catch (parseErr) {
            resBox.innerHTML = `<div class="eval-error"><strong>JSON Syntax Error</strong><br><span style="font-family:var(--font-mono);margin-top:8px;display:block">${parseErr.message}</span></div>`;
            return;
        }

        // Override company_id from selector
        const selectedCompany = document.getElementById('sim-company-selector').value;
        if (selectedCompany) payload.company_id = selectedCompany;

        const res = await fetch(API.evaluate, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (res.ok && !data.error) {
            resBox.innerHTML = renderResults(data);
        } else if (data.error) {
            resBox.innerHTML = `<div class="eval-error"><strong>Engine Error</strong><br>${data.error}</div>`;
        } else {
            let msg = data.detail;
            if (Array.isArray(msg)) msg = msg.map(e => `${e.loc.filter(l => l !== 'body').join('.')}: ${e.msg}`).join('<br>');
            resBox.innerHTML = `<div class="eval-error"><strong>Validation Error (${res.status})</strong><br>${msg}</div>`;
        }
    } catch (e) {
        resBox.innerHTML = `<div class="eval-error"><strong>Error</strong><br>${e.message}</div>`;
    } finally {
        btn.textContent = 'Execute Evaluation';
        btn.disabled = false;
    }
}

function renderResults(data) {
    const d = data.overall_decision;
    const dClass = d === 'APPROVED' ? 'decision-approved' : d === 'REJECTED' ? 'decision-rejected' : 'decision-review';

    let html = `
    <div class="results-header ${dClass}">
        <div class="results-decision-row">
            <div class="decision-badge">${d}</div>
            ${data.hard_reject ? '<span class="badge badge-red" style="font-size:12px">HARD REJECT</span>' : ''}
        </div>
        <div class="score-row">
            <div class="score-block">
                <div class="score-value">${data.lead_score}</div>
                <div class="score-label">Lead Score</div>
            </div>
            <div class="score-block">
                <div class="score-value grade-${data.grade}">${data.grade}</div>
                <div class="score-label">${data.grade_label}</div>
            </div>
        </div>
        <div class="results-summary-stats">
            <span class="stat stat-pass">${data.summary.passed} Passed</span>
            <span class="stat stat-fail">${data.summary.failed} Failed</span>
            <span class="stat stat-info">${data.summary.total_rules} Total</span>
        </div>
        <div class="eval-timestamp">App: ${data.application_id} | ${new Date(data.evaluated_at).toLocaleString()}</div>
    </div>
    <div class="rule-results-list">
    `;

    (data.rule_results || []).forEach(r => {
        const sc = r.outcome === 'PASS' ? 'status-pass' : r.outcome === 'FAIL' ? 'status-fail' : 'status-info';
        const icon = r.outcome === 'PASS' ? '&#10003;' : r.outcome === 'FAIL' ? '&#10007;' : '&#8505;';
        html += `
        <div class="rule-result-card ${sc}">
            <div class="rule-result-top">
                <div class="rule-result-status-badge ${sc}">${icon} ${r.outcome}</div>
                ${r.hard_reject ? '<span class="badge badge-red" style="font-size:10px">HARD REJECT</span>' : ''}
                <span class="rule-result-type-tag">${r.variable}</span>
            </div>
            <div class="rule-result-name">${r.rule_name}</div>
            <div class="rule-result-metrics">
                <div class="metric"><span class="metric-label">Computed</span><span class="metric-value ${sc}">${r.computed_value !== null ? r.computed_value : '---'}</span></div>
                <div class="metric"><span class="metric-label">Threshold</span><span class="metric-value">${r.operator} ${r.threshold}</span></div>
                <div class="metric"><span class="metric-label">Weight</span><span class="metric-value">${r.score_weight}</span></div>
                <div class="metric"><span class="metric-label">Score</span><span class="metric-value">${r.score_contribution}</span></div>
            </div>
        </div>`;
    });

    html += '</div>';
    return html;
}

// ══════════════════════════════════════════════════════════
// UTILITIES
// ══════════════════════════════════════════════════════════

function showToast(msg) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast success';
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => { toast.style.animation = 'toastFadeOut 0.3s forwards'; setTimeout(() => toast.remove(), 300); }, 2500);
}
