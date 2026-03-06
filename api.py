from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import uuid
from models import BureauData
from engine import CreditEngine
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

# ── X-Request-ID Middleware — attaches a unique trace ID to every request ──
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def _load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def _save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

@app.on_event("startup")
def migrate_templates_to_config():
    """Migrate python hardcoded templates to config.json if not present."""
    cfg = _load_config()
    if not cfg.get("templates"):
        try:
            from variable_templates import VARIABLE_TEMPLATES
            cfg["templates"] = VARIABLE_TEMPLATES
            _save_config(cfg)
            print("Migrated 119 variable templates to config.json")
        except ImportError:
            print("Templates already migrated, no fallback module found.")

def _get_engine():
    return CreditEngine(CONFIG_PATH)

def _get_company_or_404(cfg: dict, company_id: str) -> dict:
    """Centralized company lookup — raises 404 if not found."""
    for c in cfg.get("companies", []):
        if c["company_id"] == company_id:
            return c
    raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found")

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
    """List all bureau variable templates from dynamic configuration."""
    cfg = _load_config()
    templates = cfg.get("templates", [])
    
    # Calculate group counts dynamically
    groups = {}
    for t in templates:
        grp = t.get("group", "Unknown")
        groups[grp] = groups.get(grp, 0) + 1
        
    return {
        "total": len(templates),
        "groups": groups,
        "templates": templates,
    }

@app.post("/api/v1/templates")
def create_template(template: dict):
    """Dynamically create a new variable template."""
    cfg = _load_config()
    templates = cfg.get("templates", [])
    
    # Auto-assign next template_id if not provided
    if "template_id" not in template:
        max_id = max((t.get("template_id", 0) for t in templates), default=0)
        template["template_id"] = max_id + 1
        
    # Validation check for duplicate ID
    if any(t.get("template_id") == template["template_id"] for t in templates):
        raise HTTPException(status_code=400, detail=f"Template ID {template['template_id']} already exists")
        
    templates.append(template)
    cfg["templates"] = templates
    _save_config(cfg)
    return {"status": "created", "template": template}

@app.put("/api/v1/templates/{template_id}")
def update_template(template_id: int, updates: dict):
    """Update an existing dynamic variable template."""
    cfg = _load_config()
    templates = cfg.get("templates", [])
    
    for i, t in enumerate(templates):
        if t.get("template_id") == template_id:
            updated_template = {**t, **updates}
            templates[i] = updated_template
            cfg["templates"] = templates
            _save_config(cfg)
            return {"status": "updated", "template": updated_template}
            
    raise HTTPException(status_code=404, detail="Template not found")

@app.delete("/api/v1/templates/{template_id}")
def delete_template(template_id: int):
    """Delete a variable template."""
    cfg = _load_config()
    templates = cfg.get("templates", [])
    
    for i, t in enumerate(templates):
        if t.get("template_id") == template_id:
            deleted = templates.pop(i)
            cfg["templates"] = templates
            _save_config(cfg)
            return {"status": "deleted", "template": deleted}
            
    raise HTTPException(status_code=404, detail="Template not found")

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
    company = _get_company_or_404(cfg, company_id)
    return {"company_id": company_id, "rules": company.get("rules", [])}

@app.post("/api/v1/companies/{company_id}/rules")
def add_company_rule(company_id: str, rule: dict):
    cfg = _load_config()
    company = _get_company_or_404(cfg, company_id)
    rule["rule_id"] = rule.get("rule_id", f"rule-{uuid.uuid4().hex[:6]}")
    rule.setdefault("active_flag", True)
    company.setdefault("rules", []).append(rule)
    _save_config(cfg)
    return {"status": "added", "rule": rule}

@app.put("/api/v1/companies/{company_id}/rules/{rule_id}")
def update_company_rule(company_id: str, rule_id: str, updates: dict):
    cfg = _load_config()
    company = _get_company_or_404(cfg, company_id)
    for r in company.get("rules", []):
        if r["rule_id"] == rule_id:
            r.update(updates)
            _save_config(cfg)
            return {"status": "updated", "rule": r}
    raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

@app.delete("/api/v1/companies/{company_id}/rules/{rule_id}")
def delete_company_rule(company_id: str, rule_id: str):
    """Soft-delete: sets active_flag = false"""
    cfg = _load_config()
    company = _get_company_or_404(cfg, company_id)
    for r in company.get("rules", []):
        if r["rule_id"] == rule_id:
            r["active_flag"] = False
            _save_config(cfg)
            return {"status": "deactivated", "rule_id": rule_id}
    raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

# ══════════════════════════════════════════════════════════
# 5. HEALTH & READINESS PROBES
# ══════════════════════════════════════════════════════════

@app.get("/health")
def health_check():
    """Liveness probe — always returns 200 if the process is running."""
    return {"status": "healthy"}

@app.get("/ready")
def readiness_check():
    """Readiness probe — verifies config.json is readable."""
    try:
        _load_config()
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Not ready: {e}")

# Static files
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
