from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
from typing import List, Optional
from enum import Enum
import re

# ============================================================
# LOS Bureau Rules Engine - Pydantic Models
# Matches the specification in LOS_Bureau_Rules_Engine.docx
# ============================================================

# Regex for valid repayment history: 3-char blocks of digits or known alpha codes
_RH_PATTERN = re.compile(r'^([0-9]{3}|XXX|STD|SMA|SUB|DBT|LSS|NEW|DIS)*$', re.IGNORECASE)

# --- Tradeline Model (LOS_BUREAU_TRADELINES) ---
class Tradeline(BaseModel):
    loan_type: str                                          # e.g. "PL", "HL", "CC", "AL", "GL"
    loan_status: str = "Active"                             # Active / Closed
    loan_sec_status: str = "Unsecured"                      # Secured / Unsecured / Card
    repayment_history: str = ""                             # e.g. "000030000000" (3-char blocks)
    reported_date: datetime = Field(default_factory=datetime.now)
    loan_disb_date: Optional[datetime] = None               # Disbursement date
    loan_disb_amt: Optional[float] = Field(default=None, ge=0)  # Sanctioned / Disbursed amount
    loan_outstanding_bal: Optional[float] = Field(default=None, ge=0)  # Current outstanding balance
    loan_overdue_amt: Optional[float] = Field(default=None, ge=0)      # Current overdue amount
    credit_limit: Optional[float] = Field(default=None, ge=0)          # Credit limit (for cards)
    current_balance: Optional[float] = None                 # Current balance (for cards)
    writeoff_stld_status: Optional[str] = None              # Written-off / Settled / SuitFiled / WilfulDefault
    suitfiled_wilful_dflt: Optional[str] = None             # Suit filed or wilful default marker
    stlmnt_amt: Optional[float] = Field(default=None, ge=0)            # Settlement amount
    tot_write_off_amt: Optional[float] = Field(default=None, ge=0)     # Total written off amount

    @field_validator("repayment_history")
    @classmethod
    def validate_repayment_history(cls, v: str) -> str:
        if v and not _RH_PATTERN.match(v):
            raise ValueError(
                f"Invalid repayment_history format: '{v}'. "
                "Must be 3-char blocks of digits (000-999) or "
                "known codes (XXX, STD, SMA, SUB, DBT, LSS, NEW, DIS)."
            )
        return v

    @field_validator("loan_status")
    @classmethod
    def validate_loan_status(cls, v: str) -> str:
        allowed = {"Active", "Closed"}
        if v not in allowed:
            raise ValueError(f"loan_status must be one of {allowed}, got '{v}'")
        return v

    @field_validator("loan_sec_status")
    @classmethod
    def validate_loan_sec_status(cls, v: str) -> str:
        allowed = {"Secured", "Unsecured", "Card"}
        if v not in allowed:
            raise ValueError(f"loan_sec_status must be one of {allowed}, got '{v}'")
        return v

# --- Enquiry Model (LOS_BUREAU_ENQUIRIES) ---
class Enquiry(BaseModel):
    loan_enq_date: datetime = Field(default_factory=datetime.now)
    loan_enq_type: str = ""                                  # Loan type code for enquiry
    loan_enq_amt: Optional[float] = Field(default=None, ge=0)  # Enquiry amount
    loan_sec_status: str = "Unsecured"                       # Secured / Unsecured

    @field_validator("loan_sec_status")
    @classmethod
    def validate_enq_sec_status(cls, v: str) -> str:
        allowed = {"Secured", "Unsecured", "Card"}
        if v not in allowed:
            raise ValueError(f"loan_sec_status must be one of {allowed}, got '{v}'")
        return v

# --- Bureau Data Input Payload (BUREAU_PULL_HEADER + Related) ---
class BureauData(BaseModel):
    """Main API input: raw bureau report data for evaluation."""
    company_id: str = "default"
    application_id: str = "app-001"
    bureau_pull_date: datetime = Field(default_factory=datetime.now)
    bureau_score: Optional[int] = Field(default=None, ge=0, le=999)
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

# --- Variable Template (DYNAMIC RULES) ---
class VariableTemplate(BaseModel):
    template_id: int
    variable_name: str
    db_column: str
    logic_type: str
    group: str
    section: Optional[str] = "Tradelines"
    description: Optional[str] = None
    active: bool = True
    params: dict = {}

# --- Platform Config (top-level JSON structure) ---
class PlatformConfig(BaseModel):
    companies: List[CompanyConfig] = []
    templates: List[VariableTemplate] = []

