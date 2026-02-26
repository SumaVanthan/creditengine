from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional, Union

# ============================================================
# LOS Bureau Rules Engine — Normalization Layer
# Converts raw CIBIL JSON/XML into pre-parsed internal schema.
# Repayment history → parsed ONCE into monthly DPD array.
# ============================================================


# ── Repayment History Block (pre-parsed, never re-parsed per rule) ──

class DPDBlock(BaseModel):
    """Single month's DPD value, pre-parsed from repayment history string."""
    month_index: int                    # 0 = most recent, 1 = one month back, etc.
    raw_block: str                      # Original 3-char block, e.g. "032", "000", "XXX"
    numeric_value: Union[int, None]     # Numeric DPD value (None for non-numeric like XXX)
    label: str = ""                     # Human-readable: "32 days", "Current", "No Data", etc.
    is_dpd: bool = False                # True if actual delinquency (numeric > 0)
    severity: int = 0                   # Unified severity for comparison: 0=clean, 1=SMA, 30+=dpd, 500=SUB, etc.


class RepaymentProfile(BaseModel):
    """Pre-parsed repayment history for one tradeline. Parsed ONCE, reused everywhere."""
    raw_string: str = ""                # Original string e.g. "032000XXX065"
    blocks: List[DPDBlock] = []         # Parsed monthly array
    total_months: int = 0               # len(blocks)
    max_dpd: int = 0                    # Max severity across all blocks
    has_any_dpd: bool = False           # Quick check: any block with severity > 0
    clean_months: int = 0               # Count of months with severity == 0
    delinquent_months: int = 0          # Count of months with severity > 0


# ── Secured Mapping ──

SECURED_MAPPING = {
    # Loan types → security classification
    "HL":  "Secured",       # Home Loan
    "LAP": "Secured",       # Loan Against Property
    "AL":  "Secured",       # Auto Loan
    "GL":  "Secured",       # Gold Loan
    "TL":  "Secured",       # Tractor Loan
    "CEL": "Secured",       # Construction Equipment Loan
    "BL":  "Secured",       # Business Loan (Secured)
    "PL":  "Unsecured",     # Personal Loan
    "CL":  "Unsecured",     # Consumer Loan
    "EL":  "Unsecured",     # Education Loan
    "CC":  "Card",          # Credit Card
    "OD":  "Unsecured",     # Overdraft
    "ML":  "Unsecured",     # Microfinance Loan
    "KCC": "Secured",       # Kisan Credit Card
}


class SecuredMap(BaseModel):
    """Maps loan types to security classification with override support."""
    default_mapping: dict = Field(default_factory=lambda: dict(SECURED_MAPPING))

    def classify(self, loan_type: str, explicit_status: str = None) -> str:
        """Return security classification. Explicit status takes priority."""
        if explicit_status and explicit_status in ("Secured", "Unsecured", "Card"):
            return explicit_status
        return self.default_mapping.get(loan_type, "Unsecured")


# ── Normalized Internal Objects ──

class NormalizedTradeline(BaseModel):
    """Tradeline with pre-parsed repayment profile. Engine reads .repayment_profile, never raw string."""
    # Identity
    loan_type: str
    loan_status: str = "Active"
    loan_sec_status: str = "Unsecured"

    # Dates
    reported_date: datetime = Field(default_factory=datetime.now)
    loan_disb_date: Optional[datetime] = None

    # Amounts
    loan_disb_amt: Optional[float] = None
    loan_outstanding_bal: Optional[float] = None
    loan_overdue_amt: Optional[float] = None
    credit_limit: Optional[float] = None
    current_balance: Optional[float] = None

    # Flags
    writeoff_stld_status: Optional[str] = None
    suitfiled_wilful_dflt: Optional[str] = None
    stlmnt_amt: Optional[float] = None
    tot_write_off_amt: Optional[float] = None

    # ── PRE-PARSED ──
    repayment_history: str = ""                     # Raw string preserved for reference
    repayment_profile: RepaymentProfile = Field(default_factory=RepaymentProfile)  # PARSED ONCE


class NormalizedEnquiry(BaseModel):
    """Enquiry with resolved security classification."""
    loan_enq_date: datetime = Field(default_factory=datetime.now)
    loan_enq_type: str = ""
    loan_enq_amt: Optional[float] = None
    loan_sec_status: str = "Unsecured"


class Applicant(BaseModel):
    """Top-level applicant container with all normalized bureau data."""
    company_id: str = "default"
    application_id: str = "app-001"
    bureau_pull_date: datetime = Field(default_factory=datetime.now)
    bureau_score: Optional[int] = None

    # ── Normalized tradelines with pre-parsed DPD arrays ──
    tradelines: List[NormalizedTradeline] = []

    # ── Normalized enquiries ──
    enquiries: List[NormalizedEnquiry] = []

    # ── Metadata ──
    normalization_timestamp: Optional[str] = None
    source_format: str = "cibil_json"            # cibil_json | cibil_xml | experian_json | etc.
    total_tradelines: int = 0
    total_enquiries: int = 0
    total_active_tradelines: int = 0


# ============================================================
# NORMALIZER ENGINE
# ============================================================

class CIBILNormalizer:
    """
    Converts raw CIBIL JSON/XML payloads into the internal Applicant schema.
    Key guarantee: repayment_history is parsed into DPDBlocks ONCE here.
    The engine never parses the string again.
    """

    def __init__(self):
        self.secured_map = SecuredMap()

    # ── Main entry point ──

    def normalize(self, raw_payload: dict) -> Applicant:
        """Convert raw CIBIL payload → normalized Applicant with pre-parsed DPD blocks."""

        tradelines = []
        for raw_tl in raw_payload.get("tradelines", []):
            tradelines.append(self._normalize_tradeline(raw_tl, raw_payload))

        enquiries = []
        for raw_eq in raw_payload.get("enquiries", []):
            enquiries.append(self._normalize_enquiry(raw_eq))

        active_count = sum(1 for tl in tradelines if tl.loan_status == "Active")

        return Applicant(
            company_id=raw_payload.get("company_id", "default"),
            application_id=raw_payload.get("application_id", "app-001"),
            bureau_pull_date=self._parse_datetime(raw_payload.get("bureau_pull_date")),
            bureau_score=raw_payload.get("bureau_score"),
            tradelines=tradelines,
            enquiries=enquiries,
            normalization_timestamp=datetime.now().isoformat(),
            source_format=raw_payload.get("source_format", "cibil_json"),
            total_tradelines=len(tradelines),
            total_enquiries=len(enquiries),
            total_active_tradelines=active_count,
        )

    # ── Tradeline normalization ──

    def _normalize_tradeline(self, raw: dict, payload: dict) -> NormalizedTradeline:
        loan_type = raw.get("loan_type", "")
        explicit_sec = raw.get("loan_sec_status")
        resolved_sec = self.secured_map.classify(loan_type, explicit_sec)

        raw_rh = raw.get("repayment_history", "")
        profile = self._parse_repayment_history(raw_rh)

        return NormalizedTradeline(
            loan_type=loan_type,
            loan_status=raw.get("loan_status", "Active"),
            loan_sec_status=resolved_sec,
            reported_date=self._parse_datetime(raw.get("reported_date")),
            loan_disb_date=self._parse_datetime(raw.get("loan_disb_date")),
            loan_disb_amt=raw.get("loan_disb_amt"),
            loan_outstanding_bal=raw.get("loan_outstanding_bal"),
            loan_overdue_amt=raw.get("loan_overdue_amt"),
            credit_limit=raw.get("credit_limit"),
            current_balance=raw.get("current_balance"),
            writeoff_stld_status=raw.get("writeoff_stld_status"),
            suitfiled_wilful_dflt=raw.get("suitfiled_wilful_dflt"),
            stlmnt_amt=raw.get("stlmnt_amt"),
            tot_write_off_amt=raw.get("tot_write_off_amt"),
            repayment_history=raw_rh,
            repayment_profile=profile,
        )

    # ── Enquiry normalization ──

    def _normalize_enquiry(self, raw: dict) -> NormalizedEnquiry:
        loan_type = raw.get("loan_enq_type", "")
        explicit_sec = raw.get("loan_sec_status")
        resolved_sec = self.secured_map.classify(loan_type, explicit_sec)

        return NormalizedEnquiry(
            loan_enq_date=self._parse_datetime(raw.get("loan_enq_date")),
            loan_enq_type=loan_type,
            loan_enq_amt=raw.get("loan_enq_amt"),
            loan_sec_status=resolved_sec,
        )

    # ═══════════════════════════════════════════════════════
    # REPAYMENT HISTORY PARSER — THE CORE OF NORMALIZATION
    # Parse ONCE, never again per rule.
    #
    # Input:  "032000XXX065"
    # Output: [
    #   DPDBlock(month_index=0, raw_block="032", numeric_value=32, severity=32, is_dpd=True),
    #   DPDBlock(month_index=1, raw_block="000", numeric_value=0,  severity=0,  is_dpd=False),
    #   DPDBlock(month_index=2, raw_block="XXX", numeric_value=None, severity=0, is_dpd=False),
    #   DPDBlock(month_index=3, raw_block="065", numeric_value=65, severity=65, is_dpd=True),
    # ]
    # ═══════════════════════════════════════════════════════

    def _parse_repayment_history(self, raw_string: str) -> RepaymentProfile:
        """Convert repayment history string into pre-parsed monthly array. Done ONCE."""
        if not raw_string:
            return RepaymentProfile(raw_string="", blocks=[], total_months=0)

        blocks = []
        i = 0
        month_idx = 0

        while i < len(raw_string):
            # ── Check for 3-char alpha codes (XXX, STD, SMA, SUB, DBT, LSS, NEW) ──
            remaining = raw_string[i:]
            alpha_match = self._try_alpha_block(remaining)
            if alpha_match:
                severity = self._alpha_severity(alpha_match)
                label = self._alpha_label(alpha_match)
                blocks.append(DPDBlock(
                    month_index=month_idx,
                    raw_block=alpha_match,
                    numeric_value=None,
                    label=label,
                    is_dpd=(severity > 0),
                    severity=severity,
                ))
                i += len(alpha_match)
                month_idx += 1
                continue

            # ── Numeric: read 3 chars (zero-padded DPD) ──
            chunk = raw_string[i:i + 3]
            if len(chunk) < 3:
                # Trailing partial — still capture
                chunk = chunk.ljust(3, '0')

            numeric_val = self._safe_int(chunk)
            severity = numeric_val if numeric_val is not None else 0
            is_dpd = (numeric_val is not None and numeric_val > 0)

            blocks.append(DPDBlock(
                month_index=month_idx,
                raw_block=chunk,
                numeric_value=numeric_val,
                label=self._numeric_label(numeric_val),
                is_dpd=is_dpd,
                severity=severity,
            ))
            i += 3
            month_idx += 1

        # Compute summary stats
        max_dpd = max((b.severity for b in blocks), default=0)
        has_any = any(b.is_dpd for b in blocks)
        clean = sum(1 for b in blocks if b.severity == 0)
        delinquent = sum(1 for b in blocks if b.severity > 0)

        return RepaymentProfile(
            raw_string=raw_string,
            blocks=blocks,
            total_months=len(blocks),
            max_dpd=max_dpd,
            has_any_dpd=has_any,
            clean_months=clean,
            delinquent_months=delinquent,
        )

    # ── Alpha block detection ──

    ALPHA_CODES = {"XXX", "STD", "SMA", "SUB", "DBT", "LSS", "NEW", "DIS"}

    def _try_alpha_block(self, remaining: str) -> Optional[str]:
        """Check if remaining string starts with a known alpha code."""
        if len(remaining) >= 3:
            code = remaining[:3].upper()
            if code in self.ALPHA_CODES:
                return code
        return None

    @staticmethod
    def _alpha_severity(code: str) -> int:
        """Map alpha DPD codes to unified severity for comparison."""
        return {
            "XXX": 0,       # No data
            "STD": 0,       # Standard (current)
            "NEW": 0,       # New account
            "DIS": 0,       # Disbursed
            "SMA": 1,       # Special Mention Account
            "SUB": 500,     # Sub-standard
            "DBT": 700,     # Doubtful
            "LSS": 999,     # Loss
        }.get(code, 0)

    @staticmethod
    def _alpha_label(code: str) -> str:
        return {
            "XXX": "No Data",
            "STD": "Standard",
            "NEW": "New Account",
            "DIS": "Disbursed",
            "SMA": "Special Mention",
            "SUB": "Sub-standard",
            "DBT": "Doubtful",
            "LSS": "Loss",
        }.get(code, code)

    @staticmethod
    def _numeric_label(val) -> str:
        if val is None:
            return "Unknown"
        if val == 0:
            return "Current"
        return f"{val} days past due"

    @staticmethod
    def _safe_int(s: str) -> Optional[int]:
        try:
            return int(s)
        except (ValueError, TypeError):
            return None

    # ── DateTime parsing ──

    @staticmethod
    def _parse_datetime(val) -> datetime:
        if val is None:
            return datetime.now()
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    return datetime.strptime(val, fmt)
                except ValueError:
                    continue
        return datetime.now()


# ── Standalone utility for quick testing ──

def normalize_bureau_data(raw_json: dict) -> dict:
    """Convenience function: raw dict → normalized Applicant dict."""
    normalizer = CIBILNormalizer()
    applicant = normalizer.normalize(raw_json)
    return applicant.model_dump(mode="json")
