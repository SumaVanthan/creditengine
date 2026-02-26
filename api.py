from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import uuid
from models import BureauData
from engine import CreditEngine
from variable_templates import VARIABLE_TEMPLATES, GROUPS
from normalizer import CIBILNormalizer, normalize_bureau_data

# ============================================================
# LOS Bureau Rules Engine — REST API
# ============================================================

app = FastAPI(title="LOS Bureau Rules Engine API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def _load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def _save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def _get_engine():
    return CreditEngine(CONFIG_PATH)

# ══════════════════════════════════════════════════════════
# 1. EVALUATE — POST /api/v1/evaluate
# ══════════════════════════════════════════════════════════

@app.post("/api/v1/evaluate")
def evaluate_bureau_data(data: BureauData):
    """Submit bureau data for evaluation against company rules."""
    try:
        engine = _get_engine()
        return engine.evaluate(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ══════════════════════════════════════════════════════════
# 1b. NORMALIZE — POST /api/v1/normalize
# ══════════════════════════════════════════════════════════

@app.post("/api/v1/normalize")
def normalize_raw_bureau(raw_payload: dict):
    """Convert raw CIBIL JSON into normalized internal schema with pre-parsed repayment history."""
    try:
        return normalize_bureau_data(raw_payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ══════════════════════════════════════════════════════════
# 2. VARIABLE TEMPLATES — GET /api/v1/templates
# ══════════════════════════════════════════════════════════

@app.get("/api/v1/templates")
def list_templates():
    """List all 119 bureau variable templates."""
    return {
        "total": len(VARIABLE_TEMPLATES),
        "groups": {k: len(v) for k, v in GROUPS.items()},
        "templates": VARIABLE_TEMPLATES,
    }

# ══════════════════════════════════════════════════════════
# 3. COMPANIES — CRUD
# ══════════════════════════════════════════════════════════

@app.get("/api/v1/companies")
def list_companies():
    cfg = _load_config()
    companies = cfg.get("companies", [])
    return [{"company_id": c["company_id"], "company_name": c["company_name"], "rule_count": len(c.get("rules", []))} for c in companies]

@app.post("/api/v1/companies")
def create_company(body: dict):
    cfg = _load_config()
    new_company = {
        "company_id": body.get("company_id", str(uuid.uuid4())[:8]),
        "company_name": body.get("company_name", "New Company"),
        "rules": [],
        "score_bands": [
            {"min_score": 80, "max_score": 100, "grade": "A", "label": "Strong profile, recommend approval"},
            {"min_score": 60, "max_score": 79,  "grade": "B", "label": "Good profile, standard approval"},
            {"min_score": 40, "max_score": 59,  "grade": "C", "label": "Moderate risk, manual review required"},
            {"min_score": 20, "max_score": 39,  "grade": "D", "label": "High risk, enhanced due diligence"},
            {"min_score": 0,  "max_score": 19,  "grade": "E", "label": "Decline recommended"},
        ],
    }
    cfg.setdefault("companies", []).append(new_company)
    _save_config(cfg)
    return {"status": "created", "company": new_company}

# ══════════════════════════════════════════════════════════
# 4. COMPANY RULES — CRUD
# ══════════════════════════════════════════════════════════

@app.get("/api/v1/companies/{company_id}/rules")
def get_company_rules(company_id: str):
    cfg = _load_config()
    for c in cfg.get("companies", []):
        if c["company_id"] == company_id:
            return {"company_id": company_id, "rules": c.get("rules", [])}
    raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found")

@app.post("/api/v1/companies/{company_id}/rules")
def add_company_rule(company_id: str, rule: dict):
    cfg = _load_config()
    for c in cfg.get("companies", []):
        if c["company_id"] == company_id:
            rule["rule_id"] = rule.get("rule_id", f"rule-{uuid.uuid4().hex[:6]}")
            rule.setdefault("active_flag", True)
            c.setdefault("rules", []).append(rule)
            _save_config(cfg)
            return {"status": "added", "rule": rule}
    raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found")

@app.put("/api/v1/companies/{company_id}/rules/{rule_id}")
def update_company_rule(company_id: str, rule_id: str, updates: dict):
    cfg = _load_config()
    for c in cfg.get("companies", []):
        if c["company_id"] == company_id:
            for r in c.get("rules", []):
                if r["rule_id"] == rule_id:
                    r.update(updates)
                    _save_config(cfg)
                    return {"status": "updated", "rule": r}
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found")

@app.delete("/api/v1/companies/{company_id}/rules/{rule_id}")
def delete_company_rule(company_id: str, rule_id: str):
    """Soft-delete: sets active_flag = false"""
    cfg = _load_config()
    for c in cfg.get("companies", []):
        if c["company_id"] == company_id:
            for r in c.get("rules", []):
                if r["rule_id"] == rule_id:
                    r["active_flag"] = False
                    _save_config(cfg)
                    return {"status": "deactivated", "rule_id": rule_id}
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found")

# ══════════════════════════════════════════════════════════
# 5. FULL CONFIG (legacy compat)
# ══════════════════════════════════════════════════════════

@app.get("/api/config")
def get_config():
    return _load_config()

@app.post("/api/config")
def update_config(new_config: dict):
    _save_config(new_config)
    return {"status": "success"}

# Static files
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
