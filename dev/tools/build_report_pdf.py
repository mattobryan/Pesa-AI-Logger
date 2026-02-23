from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer


def p(text: str, style: str = "BodyText"):
    return Paragraph(text, STYLES[style])


def bullet(items):
    return ListFlowable(
        [ListItem(Paragraph(item, STYLES["BodyText"])) for item in items],
        bulletType="bullet",
        leftIndent=18,
    )


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
OUT = DOCS / "MPESA_Hybrid_System_Report.pdf"

STYLES = getSampleStyleSheet()
STYLES.add(ParagraphStyle(name="H1", parent=STYLES["Heading1"], spaceAfter=8))
STYLES.add(ParagraphStyle(name="H2", parent=STYLES["Heading2"], spaceAfter=6))
STYLES.add(ParagraphStyle(name="H3", parent=STYLES["Heading3"], spaceAfter=4))
STYLES["BodyText"].leading = 16


def build_pdf() -> Path:
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="MPESA Hybrid Financial Logging and Intelligence System",
        author="Pesa AI Logger Project",
    )

    story = []
    story.append(p("MPESA Hybrid Financial Logging and Intelligence System", "H1"))
    story.append(p("Local-First Ledger Architecture, Implementation Logic, and Operational Research Notes", "H2"))
    story.append(Spacer(1, 8))

    story.append(p("1. Executive Summary", "H2"))
    story.append(
        p(
            "The MPESA Hybrid Financial Logging and Intelligence System is a local-first data pipeline that transforms raw M-Pesa SMS notifications into a structured, auditable, and queryable financial ledger for a single user. The implementation emphasizes reliability before interface complexity."
        )
    )
    story.append(
        p(
            "The core design decision is raw-first ingestion: every message is stored as immutable evidence before parsing. This guarantees recoverability and auditability even when parser logic fails due to format changes."
        )
    )

    story.append(p("2. Problem Context and Rationale", "H2"))
    story.append(
        p(
            "In mobile-money-first environments, financial activity is often trapped in SMS text. Users and small businesses struggle with manual bookkeeping, fragmented visibility, and delayed insights. This project converts that unstructured stream into a reliable ledger."
        )
    )
    story.append(bullet([
        "Continuously capture transaction evidence from SMS.",
        "Preserve both raw and parsed forms for traceability.",
        "Enforce idempotency and deduplication.",
        "Generate practical intelligence outputs locally."
    ]))

    story.append(p("3. System Architecture Overview", "H2"))
    story.append(p("3.1 High-Level Data Flow", "H3"))
    story.append(bullet([
        "Android SMS source forwards raw messages.",
        "Webhook/API receives payload and validates input.",
        "Ingestion layer stores raw SMS in inbox_sms.",
        "Parser extracts canonical transaction fields.",
        "Database writes normalized transactions linked to raw records.",
        "Categorization/anomaly logic enriches metadata.",
        "Reporting and analytics generate summaries, exports, and insights."
    ]))

    story.append(p("3.2 Core Architectural Principles", "H3"))
    story.append(bullet([
        "Local-first: SQLite as source of truth.",
        "Raw-first: evidence before interpretation.",
        "Canonical schema: consistent query and reporting behavior.",
        "Idempotency: duplicate-safe ingestion with hashes and unique constraints.",
        "Auditability: correction history and parse state tracking.",
        "Modularity: separable ingestion, parsing, storage, analytics, and ops layers."
    ]))

    story.append(p("4. Code-by-Code Module Explanation", "H2"))
    modules = [
        ("main.py", "CLI command router", [
            "Defines user commands such as sms, serve, export, insights, summary, anomalies, heartbeat, backup, scheduler, corpus validation, and corrections.",
            "Routes each command to the right business module.",
            "Provides user-facing command output."
        ]),
        ("pesa_logger/webhook.py", "API front door", [
            "Receives SMS payloads via /sms and forwards to ingestion.",
            "Exposes health, transactions, analytics, exports, monitoring, and correction endpoints.",
            "Normalizes input and status handling."
        ]),
        ("pesa_logger/ingestion.py", "Raw-first orchestrator", [
            "Save raw SMS first.",
            "Parse second.",
            "Categorize/tag and persist canonical transaction.",
            "Record parse status and duplicate outcomes."
        ]),
        ("pesa_logger/parser.py", "SMS translator", [
            "Regex parsing of transaction classes: send, receive, paybill, till, airtime, withdrawal, deposit, reversal.",
            "Extracts IDs, amounts, counterparties, timestamps, balances, and fees.",
            "Returns normalized Transaction object or None."
        ]),
        ("pesa_logger/categorizer.py", "Labeling layer", [
            "Rule-based category assignment.",
            "Fallback category by transaction type.",
            "Tag enrichment (debit/credit/high-value/micro/has-fee)."
        ]),
        ("pesa_logger/anomaly.py", "Risk detector", [
            "Statistical outlier checks by type.",
            "Burst detection for rapid successive debits.",
            "Unusual-hour transaction flags."
        ]),
        ("pesa_logger/database.py", "Ledger vault", [
            "Defines schema for raw inbox, canonical transactions, report runs, heartbeat checks, and correction audit.",
            "Implements dedupe hash strategy and uniqueness constraints.",
            "Links canonical transactions back to immutable raw SMS rows."
        ]),
        ("pesa_logger/analytics.py", "Insight brain", [
            "Top spending categories, cashflow trends, counterparties, and velocity.",
            "Narrative insights over net position and behavior.",
            "Optional OpenAI narrative when OPENAI_API_KEY is set."
        ]),
        ("pesa_logger/reports.py", "Output engine", [
            "Weekly/monthly summaries.",
            "CSV/Excel exports with running balance and metadata.",
            "Report-run logging for traceability."
        ]),
        ("pesa_logger/monitoring.py", "Heartbeat monitor", [
            "Checks silence windows since last SMS.",
            "Raises alert states when threshold exceeded.",
            "Stores telemetry history."
        ]),
        ("pesa_logger/automation.py", "Maintenance robot", [
            "Database backups with retention.",
            "Scheduled cycle orchestration.",
            "Weekly export behavior integration."
        ]),
        ("pesa_logger/corpus.py", "Parser quality gate", [
            "Loads JSONL parser corpus.",
            "Validates parse success/failure and expected fields.",
            "Computes gate decision for safe parser changes."
        ]),
        ("tests/", "Safety net", [
            "Regression checks across parser, ingestion, DB, reports, webhook, monitoring, and automation.",
            "Prevents accidental breakage."
        ]),
    ]

    for file_name, role, points in modules:
        story.append(p(f"{file_name} — {role}", "H3"))
        story.append(bullet(points))

    story.append(p("5. Dependency Map and Runtime Semantics", "H2"))
    story.append(
        p(
            "Primary chain: Input Source -> Webhook/CLI -> Ingestion -> Database (raw) -> Parser -> Categorizer/Tags -> Database (canonical) -> Analytics/Reports/API output."
        )
    )
    story.append(bullet([
        "Monitoring depends on inbox timestamps and heartbeat history.",
        "Automation depends on monitoring and reporting.",
        "Corrections depend on audit schema and API/CLI entrypoints.",
        "Optional AI narrative depends on OPENAI_API_KEY and openai package availability."
    ]))

    story.append(p("6. Data Integrity and Reliability Strategy", "H2"))
    story.append(bullet([
        "Immutable raw SMS persistence in inbox_sms.",
        "Normalized hash dedupe against repeat forwards.",
        "Canonical transaction constraints to prevent duplicate ledger inserts.",
        "Parse status lifecycle for observability.",
        "Parser versioning for reprocessing readiness.",
        "Audited correction trail with reason, actor, and before/after values."
    ]))

    story.append(p("7. Research Module: Script-Based Android Forwarder (Termux)", "H2"))
    story.append(
        p(
            "For private use, a full native Android app can be postponed. A script-based forwarder can run on-device and push M-Pesa SMS to /sms."
        )
    )
    story.append(bullet([
        "Install Termux, Termux:API, and Termux:Boot.",
        "Run polling script to read inbox and filter M-Pesa messages.",
        "POST matching messages to /sms endpoint.",
        "Persist local last_seen state so only new SMS messages are sent.",
        "Implement retry queue with backoff for offline windows."
    ]))
    story.append(p("Tradeoff", "H3"))
    story.append(
        p(
            "The script approach is faster to build but less reliable under Android background and battery restrictions. For always-on, near-zero-miss behavior, a minimal native app remains the stronger long-term option."
        )
    )

    story.append(p("8. Video Walkthrough Script", "H2"))
    story.append(bullet([
        "Show a real incoming M-Pesa SMS on the phone.",
        "Show forwarding into the local /sms endpoint.",
        "Show raw inbox row created first.",
        "Show parser creating canonical transaction record.",
        "Show categorization and anomaly checks.",
        "Show insights, weekly summary, and CSV/Excel export outputs.",
        "Show heartbeat status and backup cycle.",
        "Show audited correction history to prove traceability."
    ]))

    story.append(p("9. Current Maturity and Next Steps", "H2"))
    story.append(
        p(
            "Current state is a strong backend milestone with broad module coverage and passing tests. Immediate improvements include optional dependency packaging for AI, webhook auth hardening, parser corpus expansion, and backup restore drills."
        )
    )

    story.append(p("10. Conclusion", "H2"))
    story.append(
        p(
            "This project proves that SMS-driven mobile money records can be transformed into a trusted local ledger when architecture prioritizes evidence preservation, idempotency, and modular processing. The result is a reliable foundation for future interfaces and scale."
        )
    )

    doc.build(story)
    return OUT


if __name__ == "__main__":
    path = build_pdf()
    print(path)
