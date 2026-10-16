"""Lead generation service module."""
from app.services.lead_generation.base import (
    GeneratedLead,
    LeadGenerationProvider,
    LeadGenerationResult,
    LeadSearchCriteria,
)
from app.services.lead_generation.mock_provider import MockLeadGenerationProvider
from app.services.lead_generation.scoring import (
    TEMP_COLD_MAX,
    TEMP_HOT_MIN,
    TEMP_WARM_MAX,
    calculate_lead_score,
    calculate_lead_temperature,
)
from app.services.lead_generation.service import (
    DuplicateLeadError,
    bulk_update_lead_status,
    convert_lead_to_crm,
    create_lead,
    delete_lead,
    generate_leads,
    get_lead,
    import_leads,
    list_leads,
    select_leads,
    update_lead_qualification,
)

__all__ = [
    "LeadSearchCriteria",
    "GeneratedLead",
    "LeadGenerationResult",
    "LeadGenerationProvider",
    "MockLeadGenerationProvider",
    "calculate_lead_score",
    "calculate_lead_temperature",
    "TEMP_COLD_MAX",
    "TEMP_WARM_MAX",
    "TEMP_HOT_MIN",
    "generate_leads",
    "list_leads",
    "get_lead",
    "DuplicateLeadError",
    "create_lead",
    "delete_lead",
    "bulk_update_lead_status",
    "update_lead_qualification",
    "select_leads",
    "convert_lead_to_crm",
    "import_leads",
]

