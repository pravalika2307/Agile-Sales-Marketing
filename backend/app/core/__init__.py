"""Core configuration, settings, classification utilities, and QA safeguards."""
from .config import settings, Settings
from .test_detection import classify_is_test
from .qa_safeguard import (
    PRODUCTION_ORG_ID,
    QA_SANDBOX_ORG_ID,
    QA_SANDBOX_SLUG,
    ProductionDataProtectionError,
    AmbiguousOrganizationError,
    assert_safe_test_organization,
    get_qa_organization,
    resolve_script_target_organization,
    install_production_mutation_guard,
)

__all__ = [
    "settings",
    "Settings",
    "classify_is_test",
    "PRODUCTION_ORG_ID",
    "QA_SANDBOX_ORG_ID",
    "QA_SANDBOX_SLUG",
    "ProductionDataProtectionError",
    "AmbiguousOrganizationError",
    "assert_safe_test_organization",
    "get_qa_organization",
    "resolve_script_target_organization",
    "install_production_mutation_guard",
]


