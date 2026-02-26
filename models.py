from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import List, Optional
from enum import Enum

# ============================================================
# LOS Bureau Rules Engine - Pydantic Models
# Matches the specification in LOS_Bureau_Rules_Engine.docx
# ============================================================

# --- Tradeline Model (LOS_BUREAU_TRADELINES) ---
class Tradeline(BaseModel):
    loan_type: str                                          # e.g. "PL", "HL", "CC", "AL", "GL"
    loan_status: str = "Active"                             # Active / Closed
    loan_sec_status: str = "Unsecured"                      # Secured / Unsecured / Card
    repayment_history: str = ""                             # e.g. "000030000000" (3-char blocks)
    reported_date: datetime = Field(default_factory=datetime.now)
    loan_disb_date: Optional[datetime] = None               # Disbursement date
    loan_disb_amt: Optional[float] = None                   # Sanctioned / Disbursed amount
    loan_outstanding_bal: Optional[float] = None            # Current outstanding balance
    loan_overdue_amt: Optional[float] = None                # Current overdue amount
    credit_limit: Optional[float] = None                    # Credit limit (for cards)
    current_balance: Optional[float] = None                 # Current balance (for cards)
    writeoff_stld_status: Optional[str] = None              # Written-off / Settled / SuitFiled / WilfulDefault
    suitfiled_wilful_dflt: Optional[str] = None             # Suit filed or wilful default marker
    stlmnt_amt: Optional[float] = None                      # Settlement amount
    tot_write_off_amt: Optional[float] = None               # Total written off amount

# --- Enquiry Model (LOS_BUREAU_ENQUIRIES) ---
class Enquiry(BaseModel):
    loan_enq_date: datetime = Field(default_factory=datetime.now)
    loan_enq_type: str = ""                                  # Loan type code for enquiry
    loan_enq_amt: Optional[float] = None                     # Enquiry amount
    loan_sec_status: str = "Unsecured"                       # Secured / Unsecured

# --- Bureau Data Input Payload (BUREAU_PULL_HEADER + Related) ---
class BureauData(BaseModel):
    """Main API input: raw bureau report data for evaluation."""
    company_id: str = "default"
    application_id: str = "app-001"
    bureau_pull_date: datetime = Field(default_factory=datetime.now)
    bureau_score: Optional[int] = None
    tradelines: List[Tradeline] = []
    enquiries: List[Enquiry] = []

# --- Company Rule Configuration (COMPANY_RULES) ---
class CompanyRule(BaseModel):
    rule_id: str
    template_id: int                                         # FK → RULE_TEMPLATES S.No
    rule_name: str
    operator: str = ">="                                     # >, >=, <, <=, =, BETWEEN, IN, NOT_IN
    threshold_value: str = "0"                               # Cutoff value(s)
    pass_outcome: str = "PASS"                               # PASS or FAIL on condition met
    score_weight: float = 1.0
    score_on_pass: float = 100.0
    score_on_fail: float = 0.0
    hard_reject: bool = False
    active_flag: bool = True
    effective_from: Optional[str] = None                     # ISO date string
    effective_to: Optional[str] = None

# --- Score Band (COMPANY_SCORE_BANDS) ---
class ScoreBand(BaseModel):
    min_score: float
    max_score: float
    grade: str
    label: str

# --- Company Configuration ---
class CompanyConfig(BaseModel):
    company_id: str
    company_name: str
    rules: List[CompanyRule] = []
    score_bands: List[ScoreBand] = [
        ScoreBand(min_score=80, max_score=100, grade="A", label="Strong profile, recommend approval"),
        ScoreBand(min_score=60, max_score=79, grade="B", label="Good profile, standard approval"),
        ScoreBand(min_score=40, max_score=59, grade="C", label="Moderate risk, manual review"),
        ScoreBand(min_score=20, max_score=39, grade="D", label="High risk, enhanced due diligence"),
        ScoreBand(min_score=0, max_score=19, grade="E", label="Decline recommended"),
    ]

# --- Platform Config (top-level JSON structure) ---
class PlatformConfig(BaseModel):
    companies: List[CompanyConfig] = []
