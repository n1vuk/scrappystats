"""
Compatibility shim for legacy slash-command imports.

This forwards reporting calls to the services layer.
"""

from scrappystats.services.report_service import run_service_report

__all__ = ["run_service_report"]
