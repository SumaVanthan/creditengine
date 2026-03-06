"""Phase 0 validation tests — verifies new input validators work correctly."""
import sys

from models import Tradeline, BureauData, Enquiry

passed = 0
failed = 0

def test(name, should_raise, fn):
    global passed, failed
    try:
        fn()
        if should_raise:
            print(f"  FAIL  {name} — expected error but none raised")
            failed += 1
        else:
            print(f"  PASS  {name}")
            passed += 1
    except Exception as e:
        if should_raise:
            print(f"  PASS  {name} — caught: {type(e).__name__}")
            passed += 1
        else:
            print(f"  FAIL  {name} — unexpected error: {e}")
            failed += 1

print("=" * 60)
print("Phase 0 — Input Validation Tests")
print("=" * 60)

# --- Repayment History Validation ---
print("\n[repayment_history regex]")
test("Invalid string 'ABCDEF'", True,
     lambda: Tradeline(loan_type="PL", repayment_history="ABCDEF"))
test("Invalid string 'HELLO'", True,
     lambda: Tradeline(loan_type="PL", repayment_history="HELLO"))
test("Valid numeric '000030000000'", False,
     lambda: Tradeline(loan_type="PL", repayment_history="000030000000"))
test("Valid with alpha codes '000XXX030STD'", False,
     lambda: Tradeline(loan_type="PL", repayment_history="000XXX030STD"))
test("Valid SMA code '000SMA000'", False,
     lambda: Tradeline(loan_type="PL", repayment_history="000SMA000"))
test("Valid empty string", False,
     lambda: Tradeline(loan_type="PL", repayment_history=""))

# --- Amount Validation ---
print("\n[non-negative amounts]")
test("Negative loan_disb_amt", True,
     lambda: Tradeline(loan_type="PL", loan_disb_amt=-5000))
test("Negative loan_outstanding_bal", True,
     lambda: Tradeline(loan_type="PL", loan_outstanding_bal=-100))
test("Negative loan_overdue_amt", True,
     lambda: Tradeline(loan_type="PL", loan_overdue_amt=-1))
test("Negative credit_limit", True,
     lambda: Tradeline(loan_type="PL", credit_limit=-50000))
test("Negative enquiry amount", True,
     lambda: Enquiry(loan_enq_amt=-10000))
test("Valid amounts (all zero)", False,
     lambda: Tradeline(loan_type="PL", loan_disb_amt=0, loan_outstanding_bal=0))
test("Valid amounts (positive)", False,
     lambda: Tradeline(loan_type="PL", loan_disb_amt=500000))

# --- Bureau Score Range ---
print("\n[bureau_score range 0-999]")
test("Score 1500 (too high)", True,
     lambda: BureauData(bureau_score=1500))
test("Score -10 (negative)", True,
     lambda: BureauData(bureau_score=-10))
test("Score 780 (valid)", False,
     lambda: BureauData(bureau_score=780))
test("Score 0 (edge)", False,
     lambda: BureauData(bureau_score=0))
test("Score 999 (edge)", False,
     lambda: BureauData(bureau_score=999))
test("Score None (optional)", False,
     lambda: BureauData(bureau_score=None))

# --- Enum Validation ---
print("\n[loan_status / loan_sec_status enums]")
test("Invalid loan_status 'Unknown'", True,
     lambda: Tradeline(loan_type="PL", loan_status="Unknown"))
test("Invalid loan_sec_status 'Mixed'", True,
     lambda: Tradeline(loan_type="PL", loan_sec_status="Mixed"))
test("Valid loan_status 'Active'", False,
     lambda: Tradeline(loan_type="PL", loan_status="Active"))
test("Valid loan_status 'Closed'", False,
     lambda: Tradeline(loan_type="PL", loan_status="Closed"))
test("Valid loan_sec_status 'Card'", False,
     lambda: Tradeline(loan_type="CC", loan_sec_status="Card"))
test("Invalid enquiry sec_status", True,
     lambda: Enquiry(loan_sec_status="Invalid"))

print(f"\n{'=' * 60}")
print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
print(f"{'=' * 60}")

sys.exit(1 if failed else 0)
