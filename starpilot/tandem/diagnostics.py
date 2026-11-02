"""Unattended diagnostics stay on the device; explicit user reports may still be sent."""

AUTOMATIC_DIAGNOSTICS_ENABLED = False
MANUAL_REPORT_TYPES = frozenset({"manual_issue_report", "flm_tune_submission"})


def _manual_reports_only(event: dict, hint: dict) -> dict | None:
  return event if event.get("tags", {}).get("report_type") in MANUAL_REPORT_TYPES else None


def _no_transactions(event: dict, hint: dict) -> None:
  return None


def sentry_options() -> dict:
  """Extra SDK options; ordinary capture calls stay upstream and are filtered before transport."""
  if AUTOMATIC_DIAGNOSTICS_ENABLED:
    return {}
  return {
    "auto_enabling_integrations": False,
    "profiles_sample_rate": 0.0,
    "auto_session_tracking": False,
    "send_client_reports": False,
    "before_send": _manual_reports_only,
    "before_send_transaction": _no_transactions,
  }
