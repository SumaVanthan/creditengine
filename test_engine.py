import json
from datetime import datetime
from models import BureauData, Tradeline, Enquiry
from engine import CreditEngine

def test_engine():
    engine = CreditEngine('config.json')

    # Build a realistic bureau payload
    payload = BureauData(
        company_id="demo-lender-001",
        application_id="APP-20260226-001",
        bureau_pull_date=datetime(2026, 2, 1),
        bureau_score=780,
        tradelines=[
            Tradeline(
                loan_type="HL",
                loan_status="Active",
                loan_sec_status="Secured",
                reported_date=datetime(2026, 1, 1),
                loan_disb_date=datetime(2023, 6, 1),
                loan_disb_amt=2500000,
                loan_outstanding_bal=1800000,
                loan_overdue_amt=0,
                repayment_history="000000000000000000000000000000"  # 10 months clean
            ),
            Tradeline(
                loan_type="PL",
                loan_status="Active",
                loan_sec_status="Unsecured",
                reported_date=datetime(2026, 1, 1),
                loan_disb_date=datetime(2025, 3, 1),
                loan_disb_amt=300000,
                loan_outstanding_bal=180000,
                loan_overdue_amt=0,
                repayment_history="000030000000000000"  # 30 DPD hit 4 months back
            ),
            Tradeline(
                loan_type="CC",
                loan_status="Active",
                loan_sec_status="Card",
                reported_date=datetime(2026, 1, 1),
                loan_disb_date=datetime(2022, 1, 1),
                loan_disb_amt=100000,
                loan_outstanding_bal=45000,
                credit_limit=200000,
                current_balance=45000,
                loan_overdue_amt=0,
                repayment_history="000000000000"
            ),
            Tradeline(
                loan_type="AL",
                loan_status="Closed",
                loan_sec_status="Secured",
                reported_date=datetime(2025, 6, 1),
                loan_disb_date=datetime(2021, 1, 1),
                loan_disb_amt=500000,
                loan_outstanding_bal=0,
                loan_overdue_amt=0,
                repayment_history="000000000000000000000000"
            ),
        ],
        enquiries=[
            Enquiry(loan_enq_date=datetime(2026, 1, 15), loan_enq_type="PL", loan_enq_amt=200000, loan_sec_status="Unsecured"),
            Enquiry(loan_enq_date=datetime(2025, 11, 1), loan_enq_type="HL", loan_enq_amt=3000000, loan_sec_status="Secured"),
            Enquiry(loan_enq_date=datetime(2025, 8, 1),  loan_enq_type="PL", loan_enq_amt=150000, loan_sec_status="Unsecured"),
        ]
    )

    result = engine.evaluate(payload)

    print("=" * 70)
    print("LOS Bureau Rules Engine — Test Results")
    print("=" * 70)
    print(f"\nApplication: {result['application_id']}")
    print(f"Company:     {result['company_id']}")
    print(f"Decision:    {result['overall_decision']}")
    print(f"Hard Reject: {result['hard_reject']}")
    print(f"Lead Score:  {result['lead_score']}")
    print(f"Grade:       {result['grade']} - {result['grade_label']}")
    print(f"Rules:       {result['summary']['passed']} passed / {result['summary']['failed']} failed / {result['summary']['total_rules']} total")

    print(f"\n{'-' * 70}")
    print("RULE RESULTS:")
    print(f"{'-' * 70}")
    for r in result['rule_results']:
        icon = "+" if r['outcome'] == 'PASS' else "X" if r['outcome'] == 'FAIL' else "!"
        hr = " [HARD REJECT]" if r.get('hard_reject') and r['outcome'] == 'FAIL' else ""
        print(f"  {icon} {r['rule_name']:<35} {r['outcome']:<6} | Value: {r['computed_value']} {r['operator']} {r['threshold']}{hr}")

    print(f"\n{'-' * 70}")
    print("COMPUTED VARIABLES (sample):")
    print(f"{'-' * 70}")
    cv = result['computed_variables']
    samples = ['BUREAU_SCORE', 'NO_30DPD_L12M', 'NO_90DPD_L12M', 'MAX_DPD_L12M', 'MAX_DPD_L6M',
               'ENQ_L3M', 'ENQ_L12M', 'USEC_ENQ_L3M', 'TOT_ACTIVE_LN', 'OVRD_LIVE_ACT',
               'NEGATIVE_ACT', 'CC_UTL', 'MOB_FL', 'MOB_LL', 'RATIO_USEC_ACTIVE']
    for key in samples:
        print(f"  {key:<30} = {cv.get(key, 'N/A')}")

    # Also dump the full JSON for API verification
    print(f"\n{'=' * 70}")
    print("FULL JSON RESPONSE:")
    print(f"{'=' * 70}")
    # Only print the non-variables part for brevity
    brief = {k: v for k, v in result.items() if k != 'computed_variables'}
    print(json.dumps(brief, indent=2))

if __name__ == "__main__":
    test_engine()
