import json
from datetime import datetime
from models import BureauData
from normalizer import CIBILNormalizer, Applicant

# ============================================================
# LOS Bureau Rules Engine - Core Engine
# 3-Layer Architecture: Compute → Evaluate → Score
# ============================================================

class CreditEngine:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.platform_config = json.load(f)
        self.normalizer = CIBILNormalizer()

    # ══════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════

    def evaluate(self, bureau_data: BureauData) -> dict:
        """Full evaluation pipeline: normalize → compute variables → evaluate rules → score."""
        company_id = bureau_data.company_id
        company = self._get_company(company_id)
        if not company:
            return {"error": f"Company '{company_id}' not found in configuration."}

        # Layer 0: Normalize — parse repayment history ONCE into DPDBlocks
        raw_dict = bureau_data.model_dump(mode="json")
        self._applicant = self.normalizer.normalize(raw_dict)

        # Dynamically build template dictionary lookup for this evaluation
        templates = self.platform_config.get("templates", [])
        self.templates_by_id = {t.get("template_id"): t for t in templates}

        # Layer 1: Compute all variables (using pre-parsed DPD blocks)
        computed = self.compute_all_variables(bureau_data, templates)

        # Layer 2: Evaluate company rules against computed values
        rules = company.get("rules", [])
        rule_results = []
        hard_rejected = False

        for rule in rules:
            if not rule.get("active_flag", True):
                continue
            result = self._evaluate_single_rule(rule, computed)
            rule_results.append(result)
            if result["outcome"] == "FAIL" and rule.get("hard_reject", False):
                hard_rejected = True

        # Layer 3: Lead scoring
        score_data = self._calculate_lead_score(rule_results, company.get("score_bands", []))

        return {
            "application_id": bureau_data.application_id,
            "company_id": company_id,
            "overall_decision": "REJECTED" if hard_rejected else score_data["decision"],
            "hard_reject": hard_rejected,
            "lead_score": score_data["score"],
            "grade": score_data["grade"],
            "grade_label": score_data["label"],
            "summary": {
                "total_rules": len(rule_results),
                "passed": sum(1 for r in rule_results if r["outcome"] == "PASS"),
                "failed": sum(1 for r in rule_results if r["outcome"] == "FAIL"),
            },
            "computed_variables": computed,
            "rule_results": rule_results,
            "evaluated_at": datetime.now().isoformat(),
        }

    def compute_all_variables(self, data: BureauData, templates: list) -> dict:
        """Compute all active bureau-derived variables from raw data."""
        computed = {}
        for tmpl in templates:
            # Skip inactive templates completely
            if not tmpl.get("active", True):
                continue
                
            db_col = tmpl["db_column"]
            logic = tmpl["logic_type"]
            try:
                computed[db_col] = self._compute_variable(data, tmpl)
            except Exception as e:
                computed[db_col] = None
        return computed

    # ══════════════════════════════════════════════════════════
    # LAYER 1: VARIABLE COMPUTATION
    # ══════════════════════════════════════════════════════════

    def _compute_variable(self, data: BureauData, tmpl: dict):
        logic = tmpl["logic_type"]

        if logic == "bureau_score":
            return data.bureau_score

        elif logic == "dpd_count":
            return self._compute_dpd_count(data, tmpl)

        elif logic == "max_dpd":
            return self._compute_max_dpd(data, tmpl)

        elif logic == "trd_dpd":
            return self._compute_tradeline_dpd(data, tmpl)

        elif logic == "pct_dpd":
            return self._compute_pct_dpd(data, tmpl)

        elif logic == "dpd_overdue":
            return self._compute_dpd_overdue(data, tmpl)

        elif logic == "enquiry_count":
            return self._compute_enquiry_count(data, tmpl)

        elif logic == "max_enq_amt":
            return self._compute_max_enq_amt(data, tmpl)

        elif logic in ("sum_field",):
            return self._compute_sum_field(data, tmpl)

        elif logic == "loan_count":
            return self._compute_loan_count(data, tmpl)

        elif logic == "count_all":
            return self._compute_count_all(data, tmpl)

        elif logic == "count_active":
            return self._compute_count_active(data, tmpl)

        elif logic == "count_by_sec":
            return self._compute_count_by_sec(data, tmpl)

        elif logic == "count_by_amt":
            return self._compute_count_by_amt(data, tmpl)

        elif logic == "negative_count":
            return self._compute_negative_count(data, tmpl)

        elif logic == "writeoff_count":
            return self._compute_writeoff_count(data, tmpl)

        elif logic == "writeoff_tl":
            return self._compute_writeoff_tl(data, tmpl)

        elif logic == "overdue_count":
            return self._compute_overdue_count(data, tmpl)

        elif logic == "sum_disb_amt":
            return self._compute_sum_disb_amt(data, tmpl)

        elif logic == "ratio_unsec_active":
            return self._compute_ratio_unsec_active(data)

        elif logic == "ratio_new_active":
            return self._compute_ratio_new_active(data, tmpl)

        elif logic == "mob_first":
            return self._compute_mob(data, first=True)

        elif logic == "mob_latest":
            return self._compute_mob(data, first=False)

        elif logic == "cc_utilization":
            return self._compute_cc_utilization(data)

        return None

    # ── DPD Helpers (now uses pre-parsed RepaymentProfile from normalizer) ──

    @staticmethod
    def _month_diff(d1: datetime, d2: datetime) -> int:
        return (d1.year - d2.year) * 12 + (d1.month - d2.month)

    def _get_severity_values(self, data: BureauData, tl, months_window):
        """Get pre-parsed severity values from normalizer's RepaymentProfile.
        No string parsing — reads directly from DPDBlock.severity array."""
        # Find matching normalized tradeline by index or repayment string
        profile = getattr(tl, 'repayment_profile', None)

        # Fallback: find from normalized applicant if profile not directly on tl
        if profile is None and hasattr(self, '_applicant'):
            for ntl in self._applicant.tradelines:
                if ntl.repayment_history == getattr(tl, 'repayment_history', ''):
                    profile = ntl.repayment_profile
                    break

        if profile is None or not profile.blocks:
            return []

        blocks = profile.blocks

        # Apply time window trimming using pre-parsed blocks
        if months_window is not None:
            diff = self._month_diff(data.bureau_pull_date, tl.reported_date)
            if diff >= months_window:
                return []
            months_to_use = months_window - diff
            blocks = blocks[:months_to_use]

        return [b.severity for b in blocks]

    # Keep legacy name as alias for backward compatibility
    def _get_dpd_blocks(self, data, tl, months_window):
        """Legacy wrapper — returns severity ints from pre-parsed profile."""
        return self._get_severity_values(data, tl, months_window)

    @staticmethod
    def _dpd_block_to_num(block):
        """Now accepts both raw string blocks AND pre-parsed severity ints."""
        if isinstance(block, int):
            return block
        if block in ("000", "XXX", "STD", ""):
            return 0
        if block == "SMA":
            return 1
        if block == "SUB":
            return 500
        if block == "DBT":
            return 700
        if block == "LSS":
            return 999
        try:
            return int(block)
        except ValueError:
            return 0

    def _filter_tradelines(self, data: BureauData, tmpl: dict):
        """Filter tradelines by status and sec_filter from template."""
        status_filter = tmpl.get("status_filter", "Active/Closed")
        sec_filter = tmpl.get("sec_filter")
        loan_type_filter = tmpl.get("loan_type_filter")

        result = []
        for tl in data.tradelines:
            # Status filter
            if status_filter == "Active" and tl.loan_status != "Active":
                continue
            if status_filter == "Closed" and tl.loan_status != "Closed":
                continue
            # Active/Closed = include all

            # Secured/Unsecured filter
            if sec_filter:
                if sec_filter == "Secured" and tl.loan_sec_status != "Secured":
                    continue
                if sec_filter == "Unsecured" and tl.loan_sec_status != "Unsecured":
                    continue

            # Loan type filter
            if loan_type_filter and tl.loan_type != loan_type_filter:
                continue

            result.append(tl)
        return result

    # ── DPD Computation Functions ──

    def _compute_dpd_count(self, data: BureauData, tmpl: dict) -> int:
        """Count of DPD months >= threshold. Uses pre-parsed severity values."""
        threshold = tmpl.get("dpd_threshold", 30)
        months = tmpl.get("months_window")
        tradelines = self._filter_tradelines(data, tmpl)
        count = 0
        for tl in tradelines:
            severities = self._get_severity_values(data, tl, months)
            for sev in severities:
                if sev >= threshold:
                    count += 1
        return count

    def _compute_max_dpd(self, data: BureauData, tmpl: dict) -> int:
        """Maximum DPD severity across tradelines within window. Pre-parsed."""
        months = tmpl.get("months_window")
        tradelines = self._filter_tradelines(data, tmpl)
        max_val = 0
        for tl in tradelines:
            severities = self._get_severity_values(data, tl, months)
            for sev in severities:
                if sev > max_val:
                    max_val = sev
        return max_val

    def _compute_tradeline_dpd(self, data: BureauData, tmpl: dict) -> int:
        """Number of TRADELINES that have any DPD severity >= threshold. Pre-parsed."""
        threshold = tmpl.get("dpd_threshold", 30)
        months = tmpl.get("months_window")
        tradelines = self._filter_tradelines(data, tmpl)
        tl_count = 0
        for tl in tradelines:
            severities = self._get_severity_values(data, tl, months)
            if any(s >= threshold for s in severities):
                tl_count += 1
        return tl_count

    def _compute_pct_dpd(self, data: BureauData, tmpl: dict) -> float:
        """Percentage of tradelines with DPD severity >= threshold. Pre-parsed."""
        threshold = tmpl.get("dpd_threshold", 30)
        months = tmpl.get("months_window")
        tradelines = self._filter_tradelines(data, tmpl)
        if not tradelines:
            return 0.0
        hit_count = 0
        for tl in tradelines:
            severities = self._get_severity_values(data, tl, months)
            if any(s >= threshold for s in severities):
                hit_count += 1
        return round((hit_count / len(tradelines)) * 100, 2)

    def _compute_dpd_overdue(self, data: BureauData, tmpl: dict) -> int:
        """Count of accounts with DPD severity >= threshold AND overdue >= overdue_min. Pre-parsed."""
        threshold = tmpl.get("dpd_threshold", 30)
        months = tmpl.get("months_window")
        overdue_min = tmpl.get("overdue_min", 5000)
        tradelines = self._filter_tradelines(data, tmpl)
        count = 0
        for tl in tradelines:
            overdue = tl.loan_overdue_amt or 0
            if overdue < overdue_min:
                continue
            severities = self._get_severity_values(data, tl, months)
            if any(s >= threshold for s in severities):
                count += 1
        return count

    # ── Enquiry Computation Functions ──

    def _compute_enquiry_count(self, data: BureauData, tmpl: dict) -> int:
        months = tmpl.get("months_window")
        sec_filter = tmpl.get("sec_filter")
        count = 0
        for eq in data.enquiries:
            if sec_filter and eq.loan_sec_status != sec_filter:
                continue
            if months is not None:
                diff = self._month_diff(data.bureau_pull_date, eq.loan_enq_date)
                if diff > months:
                    continue
            count += 1
        return count

    def _compute_max_enq_amt(self, data: BureauData, tmpl: dict) -> float:
        months = tmpl.get("months_window")
        sec_filter = tmpl.get("sec_filter")
        max_amt = 0
        for eq in data.enquiries:
            if sec_filter and eq.loan_sec_status != sec_filter:
                continue
            if months is not None:
                diff = self._month_diff(data.bureau_pull_date, eq.loan_enq_date)
                if diff > months:
                    continue
            amt = eq.loan_enq_amt or 0
            if amt > max_amt:
                max_amt = amt
        return max_amt

    # ── Loan Account Computation Functions ──

    def _compute_sum_field(self, data: BureauData, tmpl: dict) -> float:
        """Sum a specific field across filtered tradelines."""
        field = tmpl.get("field", "loan_overdue_amt")
        tradelines = self._filter_tradelines(data, tmpl)
        total = 0
        for tl in tradelines:
            val = getattr(tl, field, None) or 0
            total += val
        return total

    def _compute_loan_count(self, data: BureauData, tmpl: dict) -> int:
        """Count loans matching filters (sec, window, amount)."""
        months = tmpl.get("months_window")
        amt_op = tmpl.get("amt_op")
        amt_val = tmpl.get("amt_val")
        tradelines = self._filter_tradelines(data, tmpl)
        count = 0
        for tl in tradelines:
            # Time window check on disbursement date
            if months is not None:
                disb = tl.loan_disb_date or tl.reported_date
                diff = self._month_diff(data.bureau_pull_date, disb)
                if diff > months:
                    continue
            # Amount filter
            if amt_op and amt_val is not None:
                amt = tl.loan_disb_amt or 0
                if amt_op == ">=" and amt < amt_val:
                    continue
                if amt_op == "<" and amt >= amt_val:
                    continue
                if amt_op == ">" and amt <= amt_val:
                    continue
                if amt_op == "<=" and amt > amt_val:
                    continue
            count += 1
        return count

    def _compute_count_all(self, data: BureauData, tmpl: dict) -> int:
        return len(self._filter_tradelines(data, tmpl))

    def _compute_count_active(self, data: BureauData, tmpl: dict) -> int:
        tradelines = self._filter_tradelines(data, tmpl)
        exclude_card = tmpl.get("exclude_card", False)
        count = 0
        for tl in tradelines:
            if exclude_card and tl.loan_sec_status == "Card":
                continue
            count += 1
        return count

    def _compute_count_by_sec(self, data: BureauData, tmpl: dict) -> int:
        return len(self._filter_tradelines(data, tmpl))

    def _compute_count_by_amt(self, data: BureauData, tmpl: dict) -> int:
        amt_op = tmpl.get("amt_op", ">=")
        amt_val = tmpl.get("amt_val", 50000)
        tradelines = self._filter_tradelines(data, tmpl)
        count = 0
        for tl in tradelines:
            amt = tl.loan_disb_amt or 0
            if amt_op == ">=" and amt >= amt_val:
                count += 1
            elif amt_op == "<" and amt < amt_val:
                count += 1
            elif amt_op == ">" and amt > amt_val:
                count += 1
            elif amt_op == "<=" and amt <= amt_val:
                count += 1
        return count

    def _compute_negative_count(self, data: BureauData, tmpl: dict) -> int:
        """Count tradelines with negative status (Writeoff/SuitFiled/WilfulDefault/Settled)."""
        NEGATIVE_STATUSES = {"Written-off", "Settled", "SuitFiled", "WilfulDefault", "WriteOff",
                           "Written Off", "Suit Filed", "Wilful Default", "Settlement"}
        tradelines = self._filter_tradelines(data, tmpl)
        count = 0
        for tl in tradelines:
            status = (tl.writeoff_stld_status or "").strip()
            sfwd = (tl.suitfiled_wilful_dflt or "").strip()
            if status in NEGATIVE_STATUSES or sfwd in NEGATIVE_STATUSES:
                count += 1
        return count

    def _compute_writeoff_count(self, data: BureauData, tmpl: dict) -> int:
        """Count write-offs above minimum amount, with card/non-card filter."""
        wo_min = tmpl.get("wo_min", 0)
        card_only = tmpl.get("card_only", False)
        exclude_card = tmpl.get("exclude_card", False)
        months = tmpl.get("months_window")
        count = 0
        for tl in data.tradelines:
            if card_only and tl.loan_sec_status != "Card":
                continue
            if exclude_card and tl.loan_sec_status == "Card":
                continue
            wo_amt = tl.tot_write_off_amt or 0
            if wo_amt <= wo_min:
                continue
            if months:
                disb = tl.loan_disb_date or tl.reported_date
                diff = self._month_diff(data.bureau_pull_date, disb)
                if diff > months:
                    continue
            count += 1
        return count

    def _compute_writeoff_tl(self, data: BureauData, tmpl: dict) -> int:
        """Count tradelines with any write-off status within time window."""
        months = tmpl.get("months_window")
        WO_STATUSES = {"Written-off", "WriteOff", "Written Off"}
        count = 0
        for tl in data.tradelines:
            status = (tl.writeoff_stld_status or "").strip()
            if status not in WO_STATUSES:
                continue
            if months:
                disb = tl.loan_disb_date or tl.reported_date
                diff = self._month_diff(data.bureau_pull_date, disb)
                if diff > months:
                    continue
            count += 1
        return count

    def _compute_overdue_count(self, data: BureauData, tmpl: dict) -> int:
        """Count accounts with overdue above minimum, card/non-card filter."""
        od_min = tmpl.get("od_min", 0)
        card_only = tmpl.get("card_only", False)
        exclude_card = tmpl.get("exclude_card", False)
        months = tmpl.get("months_window")
        count = 0
        for tl in data.tradelines:
            if card_only and tl.loan_sec_status != "Card":
                continue
            if exclude_card and tl.loan_sec_status == "Card":
                continue
            od = tl.loan_overdue_amt or 0
            if od <= od_min:
                continue
            if months:
                ref = tl.reported_date
                diff = self._month_diff(data.bureau_pull_date, ref)
                if diff > months:
                    continue
            count += 1
        return count

    def _compute_sum_disb_amt(self, data: BureauData, tmpl: dict) -> float:
        months = tmpl.get("months_window")
        tradelines = self._filter_tradelines(data, tmpl)
        total = 0
        for tl in tradelines:
            if months:
                disb = tl.loan_disb_date or tl.reported_date
                diff = self._month_diff(data.bureau_pull_date, disb)
                if diff > months:
                    continue
            total += tl.loan_disb_amt or 0
        return total

    def _compute_ratio_unsec_active(self, data: BureauData) -> float:
        active = [tl for tl in data.tradelines if tl.loan_status == "Active"]
        if not active:
            return 0.0
        unsec = [tl for tl in active if tl.loan_sec_status == "Unsecured"]
        return round((len(unsec) / len(active)) * 100, 2)

    def _compute_ratio_new_active(self, data: BureauData, tmpl: dict) -> float:
        months = tmpl.get("months_window", 6)
        active = [tl for tl in data.tradelines if tl.loan_status == "Active"]
        if not active:
            return 0.0
        new_count = 0
        for tl in active:
            disb = tl.loan_disb_date or tl.reported_date
            diff = self._month_diff(data.bureau_pull_date, disb)
            if diff <= months:
                new_count += 1
        return round((new_count / len(active)) * 100, 2)

    # ── Vintage & Cards ──

    def _compute_mob(self, data: BureauData, first: bool) -> int:
        """Months on Book of first or latest loan."""
        tradelines = data.tradelines
        if not tradelines:
            return 0
        dates = []
        for tl in tradelines:
            d = tl.loan_disb_date or tl.reported_date
            dates.append(d)
        target = min(dates) if first else max(dates)
        return self._month_diff(data.bureau_pull_date, target)

    def _compute_cc_utilization(self, data: BureauData) -> float:
        """Credit Card utilization = sum(current_balance) / sum(credit_limit) * 100."""
        total_balance = 0
        total_limit = 0
        for tl in data.tradelines:
            if tl.loan_sec_status == "Card" or tl.loan_type in ("CC", "Credit Card"):
                total_balance += tl.current_balance or tl.loan_outstanding_bal or 0
                total_limit += tl.credit_limit or 0
        if total_limit == 0:
            return 0.0
        return round((total_balance / total_limit) * 100, 2)

    # ══════════════════════════════════════════════════════════
    # LAYER 2: RULE EVALUATION
    # ══════════════════════════════════════════════════════════

    def _evaluate_single_rule(self, rule: dict, computed: dict) -> dict:
        """Evaluate one company rule against computed variables."""
        template_id = rule.get("template_id")
        tmpl = self.templates_by_id.get(template_id, {})
        db_column = tmpl.get("db_column", "UNKNOWN")
        computed_value = computed.get(db_column)
        threshold_str = rule.get("threshold_value", "0")
        operator = rule.get("operator", ">=")
        pass_outcome = rule.get("pass_outcome", "PASS")

        result = {
            "rule_id": rule.get("rule_id"),
            "rule_name": rule.get("rule_name", ""),
            "variable": db_column,
            "variable_name": tmpl.get("variable_name", ""),
            "computed_value": computed_value,
            "threshold": threshold_str,
            "operator": operator,
            "outcome": "ERROR",
            "hard_reject": rule.get("hard_reject", False),
            "score_weight": rule.get("score_weight", 1.0),
            "score_contribution": 0,
        }

        if computed_value is None:
            result["outcome"] = "SKIP"
            return result

        try:
            condition_met = self._compare(computed_value, operator, threshold_str)
        except Exception:
            return result

        if condition_met:
            result["outcome"] = pass_outcome  # typically "PASS"
            result["score_contribution"] = rule.get("score_on_pass", 100)
        else:
            result["outcome"] = "FAIL" if pass_outcome == "PASS" else "PASS"
            result["score_contribution"] = rule.get("score_on_fail", 0)

        return result

    @staticmethod
    def _compare(value, operator: str, threshold_str: str) -> bool:
        """Compare a computed value against a threshold using the specified operator."""
        if operator == "BETWEEN":
            parts = threshold_str.split(",")
            low, high = float(parts[0].strip()), float(parts[1].strip())
            return low <= float(value) <= high
        if operator in ("IN", "NOT_IN"):
            items = {x.strip() for x in threshold_str.split(",")}
            is_in = str(value) in items
            return is_in if operator == "IN" else not is_in

        threshold = float(threshold_str)
        val = float(value)
        if operator == ">=":  return val >= threshold
        if operator == "<=":  return val <= threshold
        if operator == ">":   return val > threshold
        if operator == "<":   return val < threshold
        if operator in ("=", "=="):  return val == threshold
        return False

    # ══════════════════════════════════════════════════════════
    # LAYER 3: LEAD SCORING
    # ══════════════════════════════════════════════════════════

    def _calculate_lead_score(self, rule_results: list, score_bands: list) -> dict:
        """Weighted lead score = SUM(weight * score) / SUM(weight) * 100 normalised."""
        total_weighted_score = 0
        total_weight = 0

        for r in rule_results:
            if r["outcome"] in ("ERROR", "SKIP"):
                continue
            weight = r.get("score_weight", 1.0)
            contribution = r.get("score_contribution", 0)
            total_weighted_score += weight * contribution
            total_weight += weight

        if total_weight == 0:
            score = 0
        else:
            # Normalise: max possible = 100 per rule, so divide by max and *100
            max_possible = total_weight * 100
            score = round((total_weighted_score / max_possible) * 100, 2)

        # Determine grade from bands
        grade = "E"
        label = "Decline recommended"
        for band in score_bands:
            min_s = band.get("min_score", band.get("min", 0))
            max_s = band.get("max_score", band.get("max", 100))
            if min_s <= score <= max_s:
                grade = band.get("grade", "E")
                label = band.get("label", "")
                break

        # Decision based on grade
        if grade in ("A", "B"):
            decision = "APPROVED"
        elif grade == "C":
            decision = "MANUAL_REVIEW"
        else:
            decision = "REJECTED"

        return {"score": score, "grade": grade, "label": label, "decision": decision}

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    def _get_company(self, company_id: str) -> dict | None:
        for c in self.platform_config.get("companies", []):
            if c.get("company_id") == company_id:
                return c
        return None

    def get_all_companies(self) -> list:
        return self.platform_config.get("companies", [])
