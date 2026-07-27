import json
from pathlib import Path

from db import get_connection


def _explain_analyze(conn, query: str, params=None) -> dict:
    with conn.cursor() as cur:
        cur.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {query}", params)
        row = cur.fetchone()
    raw = row[0]
    plan_data = json.loads(raw) if isinstance(raw, str) else raw
    return plan_data[0]["Plan"]


def _summarize(plan: dict, depth: int = 0) -> list[str]:
    target = plan.get("Relation Name") or plan.get("Index Name") or ""
    label = f"on {target}" if target else ""
    lines = [
        "  " * depth
        + f"{plan.get('Node Type')} {label} "
        + f"(planned cost={plan.get('Total Cost')}, actual time={plan.get('Actual Total Time')}ms, "
        + f"rows={plan.get('Actual Rows')})"
    ]
    for child in plan.get("Plans", []):
        lines.extend(_summarize(child, depth + 1))
    return lines


def main() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, account_number FROM accounts LIMIT 1")
            account_id, account_number = cur.fetchone()
            cur.execute("SELECT email FROM customers LIMIT 1")
            (email,) = cur.fetchone()

        queries = [
            (
                "Account lookup by ID",
                "SELECT * FROM accounts WHERE id = %s",
                (account_id,),
            ),
            (
                "Account lookup by account_number",
                "SELECT * FROM accounts WHERE account_number = %s",
                (account_number,),
            ),
            (
                "Transaction history for an account",
                "SELECT * FROM transactions WHERE account_id = %s",
                (account_id,),
            ),
            (
                "Transaction lookup by idempotency_key",
                "SELECT * FROM transactions WHERE idempotency_key = %s",
                ("nonexistent-key",),
            ),
            (
                "Transfers sent by an account",
                "SELECT * FROM transfers WHERE from_account_id = %s",
                (account_id,),
            ),
            (
                "Transfers received by an account",
                "SELECT * FROM transfers WHERE to_account_id = %s",
                (account_id,),
            ),
            (
                "Flagged transfers (partial index)",
                "SELECT * FROM transfers WHERE flagged_for_review = true",
                None,
            ),
            (
                "Audit trail for an account",
                "SELECT * FROM audit_logs WHERE account_id = %s",
                (account_id,),
            ),
            (
                "Customer lookup by email",
                "SELECT * FROM customers WHERE email = %s",
                (email,),
            ),
            (
                "Customer lookup by full_name (no index — expect Seq Scan)",
                "SELECT * FROM customers WHERE full_name = %s",
                ("Nonexistent Person",),
            ),
        ]

        report_lines = [
            "# BankGuard Performance Report",
            "",
            "Timing figures below are informational only — no test in this project "
            "asserts on execution time. Correctness checks (index vs. sequential "
            "scan) live in `tests/test_performance.py`.",
            "",
        ]
        for label, query, params in queries:
            plan = _explain_analyze(conn, query, params)
            report_lines.append(f"## {label}")
            report_lines.append(f"```sql\n{query}\n```")
            report_lines.append("```")
            report_lines.extend(_summarize(plan))
            report_lines.append("```")
            report_lines.append("")

        conn.rollback()
    finally:
        conn.close()

    output_path = Path(__file__).parent.parent / "reports" / "performance_report.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Performance report written to {output_path}")


if __name__ == "__main__":
    main()
