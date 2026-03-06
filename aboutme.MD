# LOS Bureau Rules Engine — Complete Application Documentation

> **Version:** 1.0  
> **Tech Stack:** Python 3 · FastAPI · Pydantic · Uvicorn  
> **Source:** CIBIL Bureau Data (JSON/XML)  
> **Storage:** JSON file (`config.json`)  
> **Frontend:** Vanilla HTML/CSS/JS served as static files

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture & Data Flow](#architecture--data-flow)
3. [File Structure](#file-structure)
4. [Data Models](#data-models)
5. [Normalization Layer](#normalization-layer)
6. [Variable Computation Engine](#variable-computation-engine)
7. [Rule Evaluation Engine](#rule-evaluation-engine)
8. [Lead Scoring & Grading](#lead-scoring--grading)
9. [API Reference (All Endpoints)](#api-reference-all-endpoints)
10. [Data Storage & Configuration](#data-storage--configuration)
11. [Frontend Dashboard](#frontend-dashboard)
12. [Testing](#testing)
13. [How to Run](#how-to-run)

---

## Overview

The **LOS Bureau Rules Engine** is a configurable credit underwriting engine designed for Loan Origination Systems (LOS). It takes raw CIBIL bureau data (tradelines, enquiries, credit score) for a loan applicant, normalizes it, computes 119 derived credit risk variables, evaluates them against company-specific rules, and produces a credit decision with a lead score and grade.

### What It Does

1. **Accepts** raw bureau data (CIBIL JSON/XML format).
2. **Normalizes** it into an internal schema — parsing repayment history strings into pre-parsed DPD (Days Past Due) arrays **once** (never re-parsed per rule).
3. **Computes** 119 bureau-derived variables (DPD counts, max DPD, enquiry counts, loan counts, write-off counts, overdue totals, credit card utilization, vintage metrics, etc.).
4. **Evaluates** each company's rules against the computed variables using configurable operators and thresholds.
5. **Scores** the applicant using a weighted lead scoring formula and assigns a grade (A–E).
6. **Returns** a decision: `APPROVED`, `MANUAL_REVIEW`, or `REJECTED`.

### Multi-Tenant

The engine is **multi-tenant**: each company (lender) has its own rules, thresholds, and score bands stored in `config.json`. Multiple companies can coexist.

---

## Architecture & Data Flow

The engine follows a strict **4-layer pipeline**:

```
Raw Bureau JSON/XML
        │
        ▼
╔══════════════════════════════════╗
║  Layer 0: NORMALIZE              ║
║  (normalizer.py / CIBILNormalizer)║
║                                  ║
║  • Parse repayment history ONCE  ║
║  • Resolve security status       ║
║  • Build Applicant object        ║
╚══════════════════════════════════╝
        │
        ▼
╔══════════════════════════════════╗
║  Layer 1: COMPUTE                ║
║  (engine.py / compute_all_variables)║
║                                  ║
║  • Iterate 119 variable templates║
║  • Each template has a logic_type║
║  • Produce a flat dict of values ║
╚══════════════════════════════════╝
        │
        ▼
╔══════════════════════════════════╗
║  Layer 2: EVALUATE               ║
║  (engine.py / _evaluate_single_rule)║
║                                  ║
║  • Match rule → variable template║
║  • Compare computed value with   ║
║    threshold using operator      ║
║  • PASS / FAIL / SKIP / ERROR    ║
║  • Hard reject flagging          ║
╚══════════════════════════════════╝
        │
        ▼
╔══════════════════════════════════╗
║  Layer 3: SCORE                  ║
║  (engine.py / _calculate_lead_score)║
║                                  ║
║  • Weighted average of scores    ║
║  • Grade assignment (A–E)        ║
║  • Final decision                ║
╚══════════════════════════════════╝
        │
        ▼
   JSON Response
   (decision, score, grade, rule results, computed variables)
```

### Detailed Pipeline Walkthrough

1. **API receives** `POST /api/v1/evaluate` with a `BureauData` payload.
2. **Engine initializes**: loads `config.json`, looks up the company.
3. **Normalization**: the raw payload is serialized to dict and passed to `CIBILNormalizer.normalize()`. Each tradeline's `repayment_history` string (e.g., `"000030000000"`) is parsed **once** into an array of `DPDBlock` objects, each with a numeric severity value. This is stored as a `RepaymentProfile` on each `NormalizedTradeline`.
4. **Variable Computation**: all 119 templates from `variable_templates.py` are iterated. For each template, the engine dispatches to the appropriate computation function based on `logic_type` (e.g., `dpd_count`, `max_dpd`, `enquiry_count`, etc.). DPD-related computations read **pre-parsed severity values** from the normalized data — **no re-parsing of the repayment string**.
5. **Rule Evaluation**: each active rule in the company's config is matched to its template. The computed variable value is compared to the rule's threshold using the specified operator (`>=`, `<=`, `>`, `<`, `=`, `BETWEEN`, `IN`, `NOT_IN`). Result is PASS or FAIL.
6. **Lead Scoring**: weighted score = `SUM(weight × score_contribution) / SUM(weight × 100) × 100`. The score is mapped to a grade band (A–E). Grades A/B → APPROVED, C → MANUAL_REVIEW, D/E → REJECTED.

---

## File Structure

```
credit_engine/
├── api.py                    # FastAPI REST API — all endpoints
├── engine.py                 # Core CreditEngine class — compute, evaluate, score
├── models.py                 # Pydantic input models (BureauData, Tradeline, Enquiry, etc.)
├── normalizer.py             # CIBIL normalizer — DPD parsing, security mapping
├── variable_templates.py     # 119 variable template definitions
├── config.json               # Company rules & score bands (JSON data store)
├── test_engine.py            # Test script with sample bureau data
├── test_output.json          # Sample output from test run
├── test_output.txt           # Human-readable test output
├── test_output2.txt          # Extended test output
├── doc_text.txt              # Reference documentation text
├── doc_tables.txt            # Reference documentation tables
├── LOS_Bureau_Rules_Engine.docx  # Original specification document
├── .gitignore                # Git ignore rules
└── static/
    ├── index.html            # Web dashboard UI (31KB)
    ├── styles.css            # Dashboard styling (31KB)
    └── script.js             # Dashboard logic & API calls (22KB)
```

---

## Data Models

All input/output models are defined in `models.py` using **Pydantic BaseModel**.

### `Tradeline` — Individual Loan/Credit Account

| Field                    | Type               | Description                                                     |
|--------------------------|--------------------|-----------------------------------------------------------------|
| `loan_type`              | `str`              | Loan type code: `PL`, `HL`, `CC`, `AL`, `GL`, `EL`, etc.       |
| `loan_status`            | `str`              | `Active` or `Closed`                                             |
| `loan_sec_status`        | `str`              | `Secured`, `Unsecured`, or `Card`                                |
| `repayment_history`      | `str`              | Raw DPD string (3-char blocks): `"000030000000"`                 |
| `reported_date`          | `datetime`         | Date tradeline was last reported                                 |
| `loan_disb_date`         | `datetime` (opt)   | Disbursement date                                                |
| `loan_disb_amt`          | `float` (opt)      | Sanctioned/disbursed amount                                      |
| `loan_outstanding_bal`   | `float` (opt)      | Current outstanding balance                                      |
| `loan_overdue_amt`       | `float` (opt)      | Current overdue amount                                           |
| `credit_limit`           | `float` (opt)      | Credit card limit                                                |
| `current_balance`        | `float` (opt)      | Current credit card balance                                      |
| `writeoff_stld_status`   | `str` (opt)        | Write-off/settled/suit filed/wilful default status               |
| `suitfiled_wilful_dflt`  | `str` (opt)        | Suit filed or wilful default marker                              |
| `stlmnt_amt`             | `float` (opt)      | Settlement amount                                                |
| `tot_write_off_amt`      | `float` (opt)      | Total written-off amount                                         |

### `Enquiry` — Credit Enquiry Record

| Field              | Type            | Description                          |
|--------------------|-----------------|--------------------------------------|
| `loan_enq_date`    | `datetime`      | Date the enquiry was made            |
| `loan_enq_type`    | `str`           | Loan type code for the enquiry       |
| `loan_enq_amt`     | `float` (opt)   | Amount enquired for                  |
| `loan_sec_status`  | `str`           | Security classification              |

### `BureauData` — Main API Input Payload

| Field              | Type               | Description                              |
|--------------------|--------------------|-----------------------------------------|
| `company_id`       | `str`              | Target company for evaluation            |
| `application_id`   | `str`              | Unique application identifier            |
| `bureau_pull_date` | `datetime`         | Date of bureau report pull               |
| `bureau_score`     | `int` (opt)        | CIBIL credit score (300–900)             |
| `tradelines`       | `List[Tradeline]`  | Array of loan/credit account records     |
| `enquiries`        | `List[Enquiry]`    | Array of enquiry records                 |

### `CompanyRule` — Rule Configuration

| Field              | Type          | Description                                                     |
|--------------------|---------------|-----------------------------------------------------------------|
| `rule_id`          | `str`         | Unique rule identifier                                           |
| `template_id`      | `int`         | FK → variable template S.No (1–119)                             |
| `rule_name`        | `str`         | Human-readable rule name                                         |
| `operator`         | `str`         | Comparison operator: `>=`, `<=`, `>`, `<`, `=`, `BETWEEN`, `IN`, `NOT_IN` |
| `threshold_value`  | `str`         | Cutoff value(s), e.g. `"700"`, `"30,60"` for BETWEEN            |
| `pass_outcome`     | `str`         | `PASS` (usually) — what outcome means when condition is met      |
| `score_weight`     | `float`       | Weight for lead scoring (higher = more important)                |
| `score_on_pass`    | `float`       | Score contribution on PASS (default 100)                         |
| `score_on_fail`    | `float`       | Score contribution on FAIL (default 0)                           |
| `hard_reject`      | `bool`        | If true and rule fails, application is auto-rejected             |
| `active_flag`      | `bool`        | If false, rule is skipped during evaluation                      |
| `effective_from`   | `str` (opt)   | ISO date — when rule becomes active                              |
| `effective_to`     | `str` (opt)   | ISO date — when rule expires                                     |

### `ScoreBand` — Grade Mapping

| Field       | Type    | Description                         |
|-------------|---------|-------------------------------------|
| `min_score` | `float` | Lower bound of the score range      |
| `max_score` | `float` | Upper bound of the score range      |
| `grade`     | `str`   | Grade letter (A–E)                  |
| `label`     | `str`   | Human-readable label                |

### `CompanyConfig` — Full Company Configuration

| Field          | Type                  | Description                           |
|----------------|-----------------------|---------------------------------------|
| `company_id`   | `str`                 | Unique identifier for the company     |
| `company_name` | `str`                 | Display name                          |
| `rules`        | `List[CompanyRule]`   | Array of credit rules                 |
| `score_bands`  | `List[ScoreBand]`     | Grade banding system (A–E default)    |

### Pydantic Field Validation (Data Quality)

To ensure the engine does not fail on malformed data, `models.py` uses strict Pydantic `@field_validator` constraints on incoming data:

1. **Repayment History (`repayment_history`)**: Enforces a strict Regex (`^([0-9]{3}|XXX|STD|SMA|SUB|DBT|LSS|NEW|DIS)*$`). It must be empty, or composed exclusively of 3-character numeric DPD values or known standard alpha codes.
2. **Loan Status (`loan_status`)**: Must strictly be `"Active"` or `"Closed"`.
3. **Security Status (`loan_sec_status`)**: Must strictly be `"Secured"`, `"Unsecured"`, or `"Card"`.
4. **Numeric Limits**: Fields like balances, limits, and amounts enforce `>= 0` constraints to prevent negative erroneous ledger values.
5. **Score Boundaries**: `bureau_score` is enforced to be `>= 0` and `<= 999`.

---

## Normalization Layer

**File:** `normalizer.py`  
**Class:** `CIBILNormalizer`

### Purpose

Converts raw CIBIL JSON/XML payloads into a clean internal schema (`Applicant`) where:
- Repayment history strings are **parsed once** into `DPDBlock` arrays.
- Security status is **resolved** using a built-in mapping table.
- All downstream computation uses pre-parsed data — **zero re-parsing**.

### Repayment History Parsing

The **core innovation** of the normalizer. A raw string like `"000030XXX065"` is parsed into:

| Month Index | Raw Block | Numeric Value | Severity | Label            | Is DPD |
|-------------|-----------|---------------|----------|------------------|--------|
| 0           | `000`     | 0             | 0        | Current          | No     |
| 1           | `030`     | 30            | 30       | 30 days past due | Yes    |
| 2           | `XXX`     | None          | 0        | No Data          | No     |
| 3           | `065`     | 65            | 65       | 65 days past due | Yes    |

**Supported alpha codes:**

| Code  | Severity | Meaning                 |
|-------|----------|-------------------------|
| `XXX` | 0        | No Data                 |
| `STD` | 0        | Standard (Current)      |
| `NEW` | 0        | New Account             |
| `DIS` | 0        | Disbursed               |
| `SMA` | 1        | Special Mention Account |
| `SUB` | 500      | Sub-standard            |
| `DBT` | 700      | Doubtful                |
| `LSS` | 999      | Loss                    |

### Secured Mapping

Loan types are automatically mapped to security classification:

| Code  | Classification | Loan Type                  |
|-------|----------------|----------------------------|
| `HL`  | Secured        | Home Loan                  |
| `LAP` | Secured        | Loan Against Property      |
| `AL`  | Secured        | Auto Loan                  |
| `GL`  | Secured        | Gold Loan                  |
| `TL`  | Secured        | Tractor Loan               |
| `CEL` | Secured        | Construction Equipment     |
| `BL`  | Secured        | Business Loan              |
| `PL`  | Unsecured      | Personal Loan              |
| `CL`  | Unsecured      | Consumer Loan              |
| `EL`  | Unsecured      | Education Loan             |
| `CC`  | Card           | Credit Card                |
| `OD`  | Unsecured      | Overdraft                  |
| `ML`  | Unsecured      | Microfinance Loan          |
| `KCC` | Secured        | Kisan Credit Card          |

If the payload provides an explicit `loan_sec_status`, that takes priority over the mapping.

### Normalized Output Objects

- **`NormalizedTradeline`**: all original tradeline fields + `repayment_profile: RepaymentProfile` (pre-parsed DPD array with summary stats).
- **`NormalizedEnquiry`**: enquiry with resolved security classification.
- **`Applicant`**: top-level container with `tradelines[]`, `enquiries[]`, metadata (total counts, normalization timestamp, source format).

---

## Variable Computation Engine

**File:** `engine.py` — `CreditEngine.compute_all_variables()`  
**Templates:** `variable_templates.py` — 119 templates

### Engine Architecture & Performance

The `CreditEngine` class is built for high performance and resilience:
- **Centralized Dispatch**: A single method iterates all 119 templates and uses a mapping dictionary to route execution to the correct `_compute_X` function based on the template's `logic_type`.
- **Zero Re-parsing**: Every DPD and Repayment computation acts strictly on the `repayment_profile.blocks` integer array generated in Layer 0. String parsing never happens in Layer 1, guaranteeing fast evaluation across hundreds of rules.
- **Fail-Safe Computation**: If a specific template computation fails due to missing data or an unexpected error, a broad `except Exception` handler catches it. The engine logs the failure and safely assigns `None` to that variable's `db_column`, allowing the rest of the 118 variables to compute successfully without crashing the evaluation payload.

### How Templates Work

Each of the 119 variables is defined as a template dict with:
- `template_id`: unique integer ID (1–119+)
- `variable_name`: human-readable name
- `db_column`: short column name used as key (e.g., `BUREAU_SCORE`, `NO_30DPD_L12M`)
- `logic_type`: computation function to use
- `group`: category group (`Bureau Score`, `DPD`, `Enquiry`, `Loan Account`, `Overdue/Negative`, `Vintage`, `Cards`)
- Optional filters: `status_filter`, `sec_filter`, `months_window`, `dpd_threshold`, `loan_type_filter`, `amt_op`, `amt_val`, `card_only`, `exclude_card`, etc.

The engine iterates all 119 templates and dispatches to the correct computation function based on `logic_type`.

### All 22 Logic Types

| # | Logic Type            | Function                        | Description                                                        |
|---|----------------------|----------------------------------|--------------------------------------------------------------------|
| 1 | `bureau_score`       | Direct read                      | Returns `bureau_score` from input                                  |
| 2 | `dpd_count`          | `_compute_dpd_count()`           | Count of DPD months ≥ threshold (e.g., 30+, 60+, 90+)             |
| 3 | `max_dpd`            | `_compute_max_dpd()`             | Maximum DPD severity across tradelines within window               |
| 4 | `trd_dpd`            | `_compute_tradeline_dpd()`       | Number of tradelines with any DPD ≥ threshold                      |
| 5 | `pct_dpd`            | `_compute_pct_dpd()`             | Percentage of tradelines with DPD ≥ threshold                      |
| 6 | `dpd_overdue`        | `_compute_dpd_overdue()`         | Accounts with DPD ≥ threshold AND overdue ≥ minimum                |
| 7 | `enquiry_count`      | `_compute_enquiry_count()`       | Count of enquiries within time window, optional security filter     |
| 8 | `max_enq_amt`        | `_compute_max_enq_amt()`         | Max enquiry amount within window                                   |
| 9 | `sum_field`          | `_compute_sum_field()`           | Sum a specific field across filtered tradelines                     |
| 10| `loan_count`         | `_compute_loan_count()`          | Count loans matching filters (sec, window, amount)                  |
| 11| `count_all`          | `_compute_count_all()`           | Total tradelines matching filters                                   |
| 12| `count_active`       | `_compute_count_active()`        | Count of active tradelines (with optional card exclusion)           |
| 13| `count_by_sec`       | `_compute_count_by_sec()`        | Count tradelines by security classification                         |
| 14| `count_by_amt`       | `_compute_count_by_amt()`        | Count tradelines by disbursement amount threshold                   |
| 15| `negative_count`     | `_compute_negative_count()`      | Count tradelines with negative status (WriteOff/SuitFiled/etc.)     |
| 16| `writeoff_count`     | `_compute_writeoff_count()`      | Count write-offs above minimum amount (card/non-card filter)        |
| 17| `writeoff_tl`        | `_compute_writeoff_tl()`         | Count tradelines with any write-off status within window            |
| 18| `overdue_count`      | `_compute_overdue_count()`       | Count accounts with overdue above minimum                           |
| 19| `sum_disb_amt`       | `_compute_sum_disb_amt()`        | Sum of disbursement amounts within window                           |
| 20| `ratio_unsec_active` | `_compute_ratio_unsec_active()`  | % of unsecured loans among active loans                             |
| 21| `ratio_new_active`   | `_compute_ratio_new_active()`    | % of new loans (within N months) among active loans                 |
| 22| `mob_first` / `mob_latest` | `_compute_mob()`           | Months on Book — first or latest loan                               |
| 23| `cc_utilization`     | `_compute_cc_utilization()`      | Credit card utilization = balance/limit × 100                       |

### Variable Groups (Sample)

| Group            | Example Variables                                              |
|------------------|----------------------------------------------------------------|
| **Bureau Score** | `BUREAU_SCORE`                                                 |
| **DPD**          | `NO_30DPD_L12M`, `NO_90DPD_L24M`, `MAX_DPD_L12M`, `TRD_DPD_L6M` |
| **Enquiry**      | `ENQ_L3M`, `ENQ_L12M`, `SEC_ENQ_L6M`, `USEC_ENQ_L3M`         |
| **Loan Account** | `TOT_LN_LIVE_CLSD`, `TOT_ACTIVE_LN`, `SEC_ACTIVE`, `USEC_ACTIVE` |
| **Overdue/Neg**  | `OVRD_LIVE_ACT`, `NEGATIVE_ACT`, `WRITEOFF_AMT_GT_5K`         |
| **Vintage**      | `MOB_FL` (first loan), `MOB_LL` (latest loan)                 |
| **Cards**        | `CC_UTL` (utilization)                                         |

### Tradeline Filtering

Before computing any variable, tradelines are filtered by:
1. **Status**: `Active`, `Closed`, or `Active/Closed` (all)
2. **Security**: `Secured`, `Unsecured`, or not filtered
3. **Loan Type**: optional specific type filter
4. **Time Window**: months since disbursement or reported date
5. **Amount**: amount-based filters (`>=`, `<`, etc.)

---

## Rule Evaluation Engine

**File:** `engine.py` — `CreditEngine._evaluate_single_rule()`

### How Rules Work

Each company rule binds a **variable template** (via `template_id`) to a **threshold** and **operator**. When evaluated:

1. Look up the template by `template_id`.
2. Get the computed value from the `computed_variables` dict using the template's `db_column`.
3. Compare: `computed_value <operator> threshold_value`.
4. If condition met → outcome = `pass_outcome` (usually `PASS`), score = `score_on_pass`.
5. If condition not met → outcome = inverted, score = `score_on_fail`.
6. If computed value is `None` → outcome = `SKIP`.

### Supported Operators

| Operator   | Example                 | Description                              |
|------------|-------------------------|------------------------------------------|
| `>=`       | Score >= 700            | Greater than or equal                    |
| `<=`       | DPD_count <= 0          | Less than or equal                       |
| `>`        | Loans > 5               | Greater than                             |
| `<`        | Enquiries < 10          | Less than                                |
| `=` / `==` | Negative_count = 0      | Equal                                    |
| `BETWEEN`  | Score BETWEEN 600,800   | Value within range (comma-separated)     |
| `IN`       | Status IN Active,Closed | Value in set (comma-separated)           |
| `NOT_IN`   | Type NOT_IN CC,OD       | Value not in set                         |

### Hard Reject

If a rule has `hard_reject: true` and the outcome is `FAIL`, the entire application is immediately marked as `REJECTED` regardless of the lead score.

### Rule Result Object

Each evaluated rule produces:
```json
{
  "rule_id": "rule-001",
  "rule_name": "Bureau Score >= 700",
  "variable": "BUREAU_SCORE",
  "variable_name": "Bureau Score",
  "computed_value": 780,
  "threshold": "700",
  "operator": ">=",
  "outcome": "PASS",
  "hard_reject": true,
  "score_weight": 3.0,
  "score_contribution": 100
}
```

---

## Lead Scoring & Grading

**File:** `engine.py` — `CreditEngine._calculate_lead_score()`

### Scoring Formula

```
Lead Score = (Σ weight_i × score_contribution_i) / (Σ weight_i × 100) × 100
```

- Each rule contributes a `score_contribution` (typically 100 on pass, 0 on fail).
- Each rule has a `score_weight` (e.g., 3.0 for critical rules, 1.0 for minor ones).
- Rules with `SKIP` or `ERROR` outcomes are excluded.
- Score is normalized to 0–100 range.

### Default Grade Bands

| Grade | Score Range | Label                                  | Decision         |
|-------|-------------|----------------------------------------|------------------|
| **A** | 80 – 100    | Strong profile, recommend approval     | `APPROVED`       |
| **B** | 60 – 79     | Good profile, standard approval        | `APPROVED`       |
| **C** | 40 – 59     | Moderate risk, manual review required  | `MANUAL_REVIEW`  |
| **D** | 20 – 39     | High risk, enhanced due diligence      | `REJECTED`       |
| **E** | 0 – 19      | Decline recommended                    | `REJECTED`       |

Score bands are **per-company** and fully configurable.

### Final Decision Logic

```
if any hard_reject rule fails:
    decision = "REJECTED"
elif grade in ("A", "B"):
    decision = "APPROVED"
elif grade == "C":
    decision = "MANUAL_REVIEW"
else:
    decision = "REJECTED"
```

---

## API Reference (All Endpoints)

**Base URL:** `http://localhost:8000`  
**Framework:** FastAPI  
**CORS:** Enabled for all origins

---

### 1. `POST /api/v1/evaluate` — Evaluate Bureau Data

**Description:** Submit full bureau data for evaluation against a company's rules. Returns decision, score, grade, and all computed variables.

**Request Body:** `BureauData` (JSON)
```json
{
  "company_id": "demo-lender-001",
  "application_id": "APP-001",
  "bureau_pull_date": "2026-02-01T00:00:00",
  "bureau_score": 780,
  "tradelines": [
    {
      "loan_type": "HL",
      "loan_status": "Active",
      "loan_sec_status": "Secured",
      "repayment_history": "000000000000",
      "reported_date": "2026-01-01T00:00:00",
      "loan_disb_date": "2023-06-01T00:00:00",
      "loan_disb_amt": 2500000,
      "loan_outstanding_bal": 1800000,
      "loan_overdue_amt": 0
    }
  ],
  "enquiries": [
    {
      "loan_enq_date": "2026-01-15T00:00:00",
      "loan_enq_type": "PL",
      "loan_enq_amt": 200000,
      "loan_sec_status": "Unsecured"
    }
  ]
}
```

**Response:**
```json
{
  "application_id": "APP-001",
  "company_id": "demo-lender-001",
  "overall_decision": "APPROVED",
  "hard_reject": false,
  "lead_score": 85.5,
  "grade": "A",
  "grade_label": "Strong profile, recommend approval",
  "summary": {
    "total_rules": 8,
    "passed": 7,
    "failed": 1
  },
  "computed_variables": { "BUREAU_SCORE": 780, "NO_30DPD_L12M": 0, "..." : "..." },
  "rule_results": [ { "rule_id": "rule-001", "outcome": "PASS", "..." : "..." } ],
  "evaluated_at": "2026-02-27T09:00:00"
}
```

---

### 2. `POST /api/v1/normalize` — Normalize Raw Bureau Data

**Description:** Convert raw CIBIL JSON into the normalized internal schema with pre-parsed repayment history blocks. Useful for debugging and inspection.

**Request Body:** Raw bureau JSON dict (same structure as `BureauData`)

**Response:** Normalized `Applicant` object with all tradelines containing `repayment_profile` (parsed DPD blocks, summary stats).

---

### 3. `GET /api/v1/templates` — List Variable Templates

**Description:** Returns all 119 bureau variable templates with their metadata.

**Response:**
```json
{
  "total": 119,
  "groups": {
    "Bureau Score": 1,
    "DPD": 42,
    "Enquiry": 12,
    "Overdue/Negative": 18,
    "Loan Account": 30,
    "Vintage": 2,
    "Cards": 14
  },
  "templates": [
    {
      "template_id": 1,
      "variable_name": "Bureau Score",
      "db_column": "BUREAU_SCORE",
      "logic_type": "bureau_score",
      "group": "Bureau Score"
    }
  ]
}
```

---

### 4. `GET /api/v1/companies` — List All Companies

**Description:** Returns a summary of all registered companies.

**Response:**
```json
[
  {
    "company_id": "demo-lender-001",
    "company_name": "Demo Lending Corp",
    "rule_count": 8
  }
]
```

---

### 5. `POST /api/v1/companies` — Create New Company

**Description:** Register a new company with default score bands.

**Request Body:**
```json
{
  "company_id": "new-lender",
  "company_name": "New Lending Company"
}
```

**Response:**
```json
{
  "status": "created",
  "company": {
    "company_id": "new-lender",
    "company_name": "New Lending Company",
    "rules": [],
    "score_bands": [...]
  }
}
```

---

### 6. `GET /api/v1/companies/{company_id}/rules` — Get Company Rules

**Description:** Retrieve all rules for a specific company.

**Path Params:** `company_id` (string)

**Response:**
```json
{
  "company_id": "demo-lender-001",
  "rules": [
    {
      "rule_id": "rule-001",
      "template_id": 1,
      "rule_name": "Bureau Score >= 700",
      "operator": ">=",
      "threshold_value": "700",
      "score_weight": 3.0,
      "hard_reject": true,
      "active_flag": true
    }
  ]
}
```

---

### 7. `POST /api/v1/companies/{company_id}/rules` — Add Rule to Company

**Description:** Add a new rule to an existing company.

**Path Params:** `company_id` (string)

**Request Body:**
```json
{
  "template_id": 3,
  "rule_name": "No 30+ DPD in 12M",
  "operator": "<=",
  "threshold_value": "0",
  "pass_outcome": "PASS",
  "score_weight": 2.5,
  "score_on_pass": 100,
  "score_on_fail": 0,
  "hard_reject": false
}
```

**Response:**
```json
{
  "status": "added",
  "rule": { "rule_id": "rule-abc123", "..." : "..." }
}
```

---

### 8. `PUT /api/v1/companies/{company_id}/rules/{rule_id}` — Update Rule

**Description:** Update specific fields of an existing rule.

**Path Params:** `company_id`, `rule_id`

**Request Body:** Partial update dict (only fields to change)
```json
{
  "threshold_value": "750",
  "score_weight": 4.0
}
```

**Response:**
```json
{
  "status": "updated",
  "rule": { "..." : "..." }
}
```

---

### 9. `DELETE /api/v1/companies/{company_id}/rules/{rule_id}` — Delete Rule (Soft)

**Description:** Soft-delete a rule by setting `active_flag = false`. The rule remains in config but is skipped during evaluation.

**Path Params:** `company_id`, `rule_id`

**Response:**
```json
{
  "status": "deactivated",
  "rule_id": "rule-001"
}
```

---

### 10. `GET /api/config` — Get Full Config (Legacy)

**Description:** Returns the entire `config.json` contents.

**Response:** Full JSON config object.

---

### 11. `POST /api/config` — Update Full Config (Legacy)

**Description:** Overwrite the entire configuration file.

**Request Body:** Full config JSON object.

**Response:**
```json
{ "status": "success" }
```

---

### 12. `GET /` — Web Dashboard (Static)

**Description:** Serves the static HTML/CSS/JS web dashboard for managing companies, rules, and running evaluations through a GUI.

---

## API Summary Table

| #  | Method   | Endpoint                                          | Description                    |
|----|----------|---------------------------------------------------|--------------------------------|
| 1  | `POST`   | `/api/v1/evaluate`                                | Evaluate bureau data           |
| 2  | `POST`   | `/api/v1/normalize`                               | Normalize raw bureau JSON      |
| 3  | `GET`    | `/api/v1/templates`                               | List 119 variable templates    |
| 4  | `GET`    | `/api/v1/companies`                               | List all companies             |
| 5  | `POST`   | `/api/v1/companies`                               | Create new company             |
| 6  | `GET`    | `/api/v1/companies/{company_id}/rules`            | Get company rules              |
| 7  | `POST`   | `/api/v1/companies/{company_id}/rules`            | Add rule to company            |
| 8  | `PUT`    | `/api/v1/companies/{company_id}/rules/{rule_id}`  | Update existing rule           |
| 9  | `DELETE` | `/api/v1/companies/{company_id}/rules/{rule_id}`  | Soft-delete rule               |
| 10 | `GET`    | `/api/config`                                     | Get full config (legacy)       |
| 11 | `POST`   | `/api/config`                                     | Update full config (legacy)    |

---

## Data Storage & Configuration

### Storage Mechanism

The application uses **flat-file JSON storage** — a single `config.json` file that serves as the database.

**File:** `config.json`

### Why JSON File?

- **Zero infrastructure**: No database server needed.
- **Human-readable**: Easy to inspect and manually edit.
- **Version-controllable**: Can be tracked in Git.
- **Portable**: Copy the file to migrate all configuration.

### Data Structure in `config.json`

```json
{
  "companies": [
    {
      "company_id": "demo-lender-001",
      "company_name": "Demo Lending Corp",
      "rules": [
        {
          "rule_id": "rule-001",
          "template_id": 1,
          "rule_name": "Bureau Score >= 700",
          "operator": ">=",
          "threshold_value": "700",
          "pass_outcome": "PASS",
          "score_weight": 3.0,
          "score_on_pass": 100,
          "score_on_fail": 0,
          "hard_reject": true,
          "active_flag": true,
          "effective_from": "2026-01-01"
        }
      ],
      "score_bands": [
        { "min_score": 80, "max_score": 100, "grade": "A", "label": "Strong profile, recommend approval" },
        { "min_score": 60, "max_score": 79,  "grade": "B", "label": "Good profile, standard approval" },
        { "min_score": 40, "max_score": 59,  "grade": "C", "label": "Moderate risk, manual review required" },
        { "min_score": 20, "max_score": 39,  "grade": "D", "label": "High risk, enhanced due diligence" },
        { "min_score": 0,  "max_score": 19,  "grade": "E", "label": "Decline recommended" }
      ]
    }
  ]
}
```

### Read/Write Operations

| Operation          | Function           | Trigger                                  |
|--------------------|--------------------|------------------------------------------|
| **Load config**    | `_load_config()`   | Every API request (ensures fresh data)   |
| **Save config**    | `_save_config()`   | After any create/update/delete operation |
| **Engine init**    | `CreditEngine()`   | Reads config on construction             |

### Data Lifecycle

1. **Bureau data** (tradelines, enquiries, score) is **not stored** — it is received per-request through the API, processed in memory, and discarded.
2. **Company rules and score bands** are **persisted** in `config.json` and survive server restarts.
3. **Evaluation results** are returned in the API response and **not persisted** by default.
4. **Variable templates** are **hardcoded** in `variable_templates.py` — they define the 119 possible variables and are not editable at runtime.

### Data Processing Flow

```
Input Bureau JSON (per request, transient)
    ↓
Normalize → In-memory Applicant object (transient)
    ↓
Compute Variables → In-memory dict (transient)
    ↓
Load Company Rules ← config.json (persistent)
    ↓
Evaluate Rules → In-memory results (transient)
    ↓
Score & Grade → In-memory (transient)
    ↓
Return JSON Response (transient)
```

---

## Frontend Dashboard

**Location:** `static/` directory (served at `/` by FastAPI)

### Files

| File         | Size  | Purpose                                  |
|-------------|-------|------------------------------------------|
| `index.html` | 31 KB | Dashboard layout — company management, rule editor, evaluation form |
| `styles.css` | 31 KB | Dark-themed professional styling          |
| `script.js`  | 22 KB | API integration, DOM manipulation, form handling |

### Features

- **Company Management**: Create, view, and manage lending companies.
- **Rule Configuration**: Add, edit, activate/deactivate rules per company via dropdown selection of 119 variable templates.
- **Bureau Data Submission**: Paste or build bureau JSON payloads for evaluation.
- **Results Display**: View decision, score, grade, rule-by-rule results, and computed variables.
- **Template Browser**: Browse all 119 variable templates grouped by category.

---

## Testing

**File:** `test_engine.py`

### Test Payload

The test creates a realistic `BureauData` payload with:
- **4 tradelines**: Home Loan (Active), Personal Loan (Active, with 30-DPD hit), Credit Card (Active), Auto Loan (Closed).
- **3 enquiries**: Recent PL, HL, and PL enquiries.
- **Bureau Score**: 780.

### Running Tests

```bash
python test_engine.py
```

### Sample Output

```
======================================================================
LOS Bureau Rules Engine — Test Results
======================================================================

Application: APP-20260226-001
Company:     demo-lender-001
Decision:    APPROVED / REJECTED
Hard Reject: True / False
Lead Score:  85.5
Grade:       A - Strong profile, recommend approval
Rules:       7 passed / 1 failed / 8 total

----------------------------------------------------------------------
RULE RESULTS:
----------------------------------------------------------------------
  + Bureau Score >= 700              PASS   | Value: 780 >= 700
  X No 30+ DPD in Last 12 Months    FAIL   | Value: 1 <= 0
  ...
```

---

## How to Run

### Prerequisites

- Python 3.9+
- `pip install fastapi uvicorn pydantic`

### Start the Server

```bash
cd credit_engine
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Or:
```bash
python api.py
```

### Access

- **API Docs**: http://localhost:8000/docs (Swagger UI auto-generated by FastAPI)
- **Dashboard**: http://localhost:8000/
- **API Base**: http://localhost:8000/api/v1/

---

*This documentation covers the complete architecture, data flow, all API endpoints, data models, storage mechanisms, and processing pipeline of the LOS Bureau Rules Engine.*
