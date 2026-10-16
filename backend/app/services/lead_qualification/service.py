"""Lead qualification and explainable scoring evaluation service (Phases 2 & 3)."""
from __future__ import annotations

import uuid
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.icp import IdealCustomerProfile
from app.models.lead import Lead
from app.models.tenant import Organization
from app.schemas.qualification import (
    CriterionDetail,
    LeadBatchEvaluateResult,
    LeadQualificationResult,
)
from app.services.lead_generation.scoring import (
    MAX_LEAD_SCORE,
    SCORE_CITY_MATCH,
    SCORE_COMPANY_SIZE_MATCH,
    SCORE_COUNTRY_MATCH,
    SCORE_DOMAIN_EXISTS,
    SCORE_INDUSTRY_MATCH,
    SCORE_JOB_TITLE_MATCH,
    SCORE_SENIORITY_MATCH,
    SCORE_TECH_KEYWORD_MATCH,
    _parse_size_range,
    _string_matches_list,
    calculate_lead_temperature,
)


def evaluate_single_lead_qualification(
    db: Session,
    current_org: Organization,
    lead: Lead,
    icp: Optional[IdealCustomerProfile] = None,
    dry_run: bool = False,
    qualification_threshold: int = 50,
) -> LeadQualificationResult:
    """
    Evaluates an existing Lead record against ICP criteria deterministically.
    Never invents missing business data. Explains every matched, unmatched, or missing criterion.
    """
    if lead.organization_id != current_org.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead '{lead.id}' not found.",
        )

    # Resolve target ICP: passed explicitly, or lead.icp, or first active org ICP
    target_icp = icp
    if target_icp is None and lead.icp_id:
        target_icp = db.execute(
            select(IdealCustomerProfile).where(
                IdealCustomerProfile.id == lead.icp_id,
                IdealCustomerProfile.organization_id == current_org.id,
            )
        ).scalar_one_or_none()

    if target_icp is None:
        target_icp = db.execute(
            select(IdealCustomerProfile).where(
                IdealCustomerProfile.organization_id == current_org.id,
                IdealCustomerProfile.is_active == True,
            ).order_by(IdealCustomerProfile.created_at.asc())
        ).scalars().first()

    criteria_evals: List[CriterionDetail] = []
    score = 0
    matched_reasons: List[str] = []

    # If organization has zero configured ICPs
    if target_icp is None:
        return LeadQualificationResult(
            lead_id=lead.id,
            icp_id=None,
            icp_name=None,
            score=0,
            temperature="cold",
            qualification_status=lead.qualification_status or "new",
            is_qualified=lead.qualification_status == "qualified",
            is_assessed=False,
            qualification_reason="No active Ideal Customer Profile (ICP) configured in organization.",
            criteria=[
                CriterionDetail(
                    criterion="ICP Configuration",
                    points=0,
                    max_points=100,
                    status="not_configured",
                    detail="Organization has no active ICP defined to evaluate criteria against.",
                )
            ],
            matched_criteria_count=0,
            missing_criteria_count=0,
            unmatched_criteria_count=0,
        )

    # 1. Industry (20 pts)
    if target_icp.industries:
        if not lead.industry:
            criteria_evals.append(
                CriterionDetail(
                    criterion="Industry",
                    points=0,
                    max_points=SCORE_INDUSTRY_MATCH,
                    status="missing_data",
                    detail="Lead industry is not recorded.",
                )
            )
        elif _string_matches_list(lead.industry, target_icp.industries):
            score += SCORE_INDUSTRY_MATCH
            matched_reasons.append(f"Industry '{lead.industry}' matches ICP target ({', '.join(target_icp.industries)})")
            criteria_evals.append(
                CriterionDetail(
                    criterion="Industry",
                    points=SCORE_INDUSTRY_MATCH,
                    max_points=SCORE_INDUSTRY_MATCH,
                    status="matched",
                    detail=f"Industry '{lead.industry}' matches ICP criteria.",
                )
            )
        else:
            criteria_evals.append(
                CriterionDetail(
                    criterion="Industry",
                    points=0,
                    max_points=SCORE_INDUSTRY_MATCH,
                    status="unmatched",
                    detail=f"Industry '{lead.industry}' does not match target industries ({', '.join(target_icp.industries)}).",
                )
            )
    else:
        criteria_evals.append(
            CriterionDetail(
                criterion="Industry",
                points=0,
                max_points=0,
                status="not_configured",
                detail="No industry restrictions specified in ICP.",
            )
        )

    # 2. Company Size (15 pts)
    if target_icp.company_size_min is not None or target_icp.company_size_max is not None:
        if not lead.employee_count_range:
            criteria_evals.append(
                CriterionDetail(
                    criterion="Company Size",
                    points=0,
                    max_points=SCORE_COMPANY_SIZE_MATCH,
                    status="missing_data",
                    detail="Lead company size/employee count range is not recorded.",
                )
            )
        else:
            size_bounds = _parse_size_range(lead.employee_count_range)
            if size_bounds:
                lead_min, lead_max = size_bounds
                matches = True
                if target_icp.company_size_min is not None and lead_max < target_icp.company_size_min:
                    matches = False
                if target_icp.company_size_max is not None and lead_min > target_icp.company_size_max:
                    matches = False

                if matches:
                    score += SCORE_COMPANY_SIZE_MATCH
                    matched_reasons.append(f"Company size '{lead.employee_count_range}' within target ICP range")
                    criteria_evals.append(
                        CriterionDetail(
                            criterion="Company Size",
                            points=SCORE_COMPANY_SIZE_MATCH,
                            max_points=SCORE_COMPANY_SIZE_MATCH,
                            status="matched",
                            detail=f"Employee count '{lead.employee_count_range}' is within ICP bounds ({target_icp.company_size_min or 0}-{target_icp.company_size_max or 'unlimited'}).",
                        )
                    )
                else:
                    criteria_evals.append(
                        CriterionDetail(
                            criterion="Company Size",
                            points=0,
                            max_points=SCORE_COMPANY_SIZE_MATCH,
                            status="unmatched",
                            detail=f"Employee count '{lead.employee_count_range}' is outside target bounds ({target_icp.company_size_min or 0}-{target_icp.company_size_max or 'unlimited'}).",
                        )
                    )
            else:
                criteria_evals.append(
                    CriterionDetail(
                        criterion="Company Size",
                        points=0,
                        max_points=SCORE_COMPANY_SIZE_MATCH,
                        status="unmatched",
                        detail=f"Unable to parse employee count range format '{lead.employee_count_range}'.",
                    )
                )
    else:
        criteria_evals.append(
            CriterionDetail(
                criterion="Company Size",
                points=0,
                max_points=0,
                status="not_configured",
                detail="No employee count bounds specified in ICP.",
            )
        )

    # 3. Country (15 pts)
    if target_icp.countries:
        if not lead.country:
            criteria_evals.append(
                CriterionDetail(
                    criterion="Country",
                    points=0,
                    max_points=SCORE_COUNTRY_MATCH,
                    status="missing_data",
                    detail="Lead country is not recorded.",
                )
            )
        elif _string_matches_list(lead.country, target_icp.countries):
            score += SCORE_COUNTRY_MATCH
            matched_reasons.append(f"Country '{lead.country}' matches ICP geography")
            criteria_evals.append(
                CriterionDetail(
                    criterion="Country",
                    points=SCORE_COUNTRY_MATCH,
                    max_points=SCORE_COUNTRY_MATCH,
                    status="matched",
                    detail=f"Country '{lead.country}' is an approved target country.",
                )
            )
        else:
            criteria_evals.append(
                CriterionDetail(
                    criterion="Country",
                    points=0,
                    max_points=SCORE_COUNTRY_MATCH,
                    status="unmatched",
                    detail=f"Country '{lead.country}' does not match target countries ({', '.join(target_icp.countries)}).",
                )
            )
    else:
        criteria_evals.append(
            CriterionDetail(
                criterion="Country",
                points=0,
                max_points=0,
                status="not_configured",
                detail="No geographic country restrictions specified in ICP.",
            )
        )

    # 4. City (10 pts)
    if target_icp.cities:
        if not lead.city:
            criteria_evals.append(
                CriterionDetail(
                    criterion="City",
                    points=0,
                    max_points=SCORE_CITY_MATCH,
                    status="missing_data",
                    detail="Lead city is not recorded.",
                )
            )
        elif _string_matches_list(lead.city, target_icp.cities):
            score += SCORE_CITY_MATCH
            matched_reasons.append(f"City '{lead.city}' matches ICP target cities")
            criteria_evals.append(
                CriterionDetail(
                    criterion="City",
                    points=SCORE_CITY_MATCH,
                    max_points=SCORE_CITY_MATCH,
                    status="matched",
                    detail=f"City '{lead.city}' is in target metropolitan regions.",
                )
            )
        else:
            criteria_evals.append(
                CriterionDetail(
                    criterion="City",
                    points=0,
                    max_points=SCORE_CITY_MATCH,
                    status="unmatched",
                    detail=f"City '{lead.city}' does not match target cities.",
                )
            )
    else:
        criteria_evals.append(
            CriterionDetail(
                criterion="City",
                points=0,
                max_points=0,
                status="not_configured",
                detail="No city restrictions specified in ICP.",
            )
        )

    # 5. Job Title & Seniority (15 pts + 10 pts)
    if target_icp.job_titles:
        if not lead.job_title:
            criteria_evals.append(
                CriterionDetail(
                    criterion="Job Title",
                    points=0,
                    max_points=SCORE_JOB_TITLE_MATCH,
                    status="missing_data",
                    detail="Lead job title is not recorded.",
                )
            )
        elif _string_matches_list(lead.job_title, target_icp.job_titles):
            score += SCORE_JOB_TITLE_MATCH
            matched_reasons.append(f"Job title '{lead.job_title}' matches target persona")
            criteria_evals.append(
                CriterionDetail(
                    criterion="Job Title",
                    points=SCORE_JOB_TITLE_MATCH,
                    max_points=SCORE_JOB_TITLE_MATCH,
                    status="matched",
                    detail=f"Job title '{lead.job_title}' aligns with decision maker persona.",
                )
            )
        else:
            criteria_evals.append(
                CriterionDetail(
                    criterion="Job Title",
                    points=0,
                    max_points=SCORE_JOB_TITLE_MATCH,
                    status="unmatched",
                    detail=f"Job title '{lead.job_title}' does not match target roles.",
                )
            )
    else:
        criteria_evals.append(
            CriterionDetail(
                criterion="Job Title",
                points=0,
                max_points=0,
                status="not_configured",
                detail="No specific job titles configured in ICP.",
            )
        )

    # Seniority Level
    if target_icp.seniority_levels:
        if not lead.job_title:
            criteria_evals.append(
                CriterionDetail(
                    criterion="Seniority",
                    points=0,
                    max_points=SCORE_SENIORITY_MATCH,
                    status="missing_data",
                    detail="Lead job title is missing, unable to evaluate seniority.",
                )
            )
        elif _string_matches_list(lead.job_title, target_icp.seniority_levels):
            score += SCORE_SENIORITY_MATCH
            matched_reasons.append("Seniority level matched ICP requirements")
            criteria_evals.append(
                CriterionDetail(
                    criterion="Seniority",
                    points=SCORE_SENIORITY_MATCH,
                    max_points=SCORE_SENIORITY_MATCH,
                    status="matched",
                    detail="Seniority level verified from title.",
                )
            )
        else:
            criteria_evals.append(
                CriterionDetail(
                    criterion="Seniority",
                    points=0,
                    max_points=SCORE_SENIORITY_MATCH,
                    status="unmatched",
                    detail="Job title does not indicate required seniority level.",
                )
            )
    else:
        criteria_evals.append(
            CriterionDetail(
                criterion="Seniority",
                points=0,
                max_points=0,
                status="not_configured",
                detail="No seniority level requirements configured.",
            )
        )

    # 6. Technologies & Keywords (10 pts)
    tech_matched = False
    if target_icp.technologies or target_icp.keywords:
        full_text = f"{lead.company_name} {lead.industry or ''} {lead.job_title or ''}".lower()
        matched_tags: List[str] = []

        if target_icp.technologies:
            for tech in target_icp.technologies:
                if tech.lower() in full_text:
                    tech_matched = True
                    matched_tags.append(tech)

        if target_icp.keywords:
            for kw in target_icp.keywords:
                if kw.lower() in full_text:
                    tech_matched = True
                    matched_tags.append(kw)

        if tech_matched:
            score += SCORE_TECH_KEYWORD_MATCH
            matched_reasons.append(f"Keywords/Tech matched: {', '.join(matched_tags)}")
            criteria_evals.append(
                CriterionDetail(
                    criterion="Tech & Keywords",
                    points=SCORE_TECH_KEYWORD_MATCH,
                    max_points=SCORE_TECH_KEYWORD_MATCH,
                    status="matched",
                    detail=f"Matched relevant keywords/technologies ({', '.join(matched_tags)}).",
                )
            )
        else:
            criteria_evals.append(
                CriterionDetail(
                    criterion="Tech & Keywords",
                    points=0,
                    max_points=SCORE_TECH_KEYWORD_MATCH,
                    status="unmatched",
                    detail="No matching technologies or keywords found in lead attributes.",
                )
            )
    else:
        criteria_evals.append(
            CriterionDetail(
                criterion="Tech & Keywords",
                points=0,
                max_points=0,
                status="not_configured",
                detail="No technologies or keywords specified in ICP.",
            )
        )

    # 7. Company Domain Exists (5 pts)
    if lead.company_domain:
        score += SCORE_DOMAIN_EXISTS
        matched_reasons.append("Company domain verified")
        criteria_evals.append(
            CriterionDetail(
                criterion="Verified Domain",
                points=SCORE_DOMAIN_EXISTS,
                max_points=SCORE_DOMAIN_EXISTS,
                status="matched",
                detail=f"Verified corporate domain: {lead.company_domain}",
            )
        )
    else:
        criteria_evals.append(
            CriterionDetail(
                criterion="Verified Domain",
                points=0,
                max_points=SCORE_DOMAIN_EXISTS,
                status="missing_data",
                detail="No company web domain provided.",
            )
        )

    # Final Score & Qualification Outcome
    final_score = min(max(score, 0), MAX_LEAD_SCORE)
    temperature = calculate_lead_temperature(final_score)

    matched_count = sum(1 for c in criteria_evals if c.status == "matched")
    missing_count = sum(1 for c in criteria_evals if c.status == "missing_data")
    unmatched_count = sum(1 for c in criteria_evals if c.status == "unmatched")

    # Safety: If all configured ICP evaluation criteria are missing, do not mark qualified or disqualified
    icp_criteria = [c for c in criteria_evals if c.criterion != "Verified Domain" and c.status != "not_configured"]
    has_evaluated_icp_criteria = any(c.status in ("matched", "unmatched") for c in icp_criteria)
    is_assessed = len(icp_criteria) > 0 and has_evaluated_icp_criteria

    if not is_assessed or (missing_count >= 4 and matched_count == 0):
        outcome = "new"  # Unassessed neutral state per data integrity rules
        reason = "Insufficient persisted data to evaluate qualification (missing data for configured ICP criteria)."
    elif final_score >= qualification_threshold:
        outcome = "qualified"
        reason = f"Qualified (Score {final_score}/100 >= {qualification_threshold}); " + ("; ".join(matched_reasons) if matched_reasons else "Meets criteria.")
    else:
        outcome = "disqualified"
        reason = f"Disqualified (Score {final_score}/100 < {qualification_threshold}); did not meet minimum criteria threshold."

    # Persist evaluation if not a dry-run
    if not dry_run:
        lead.icp_id = target_icp.id
        lead.lead_score = final_score
        lead.lead_temperature = temperature
        lead.qualification_status = outcome
        lead.qualification_reason = reason
        db.commit()
        db.refresh(lead)

    return LeadQualificationResult(
        lead_id=lead.id,
        icp_id=target_icp.id,
        icp_name=target_icp.name,
        score=final_score,
        temperature=temperature,
        qualification_status=outcome,
        is_qualified=outcome == "qualified",
        is_assessed=is_assessed,
        qualification_reason=reason,
        criteria=criteria_evals,
        matched_criteria_count=matched_count,
        missing_criteria_count=missing_count,
        unmatched_criteria_count=unmatched_count,
    )


def evaluate_leads_batch(
    db: Session,
    current_org: Organization,
    lead_ids: List[uuid.UUID],
    icp_id: Optional[uuid.UUID] = None,
    dry_run: bool = False,
    qualification_threshold: int = 50,
) -> LeadBatchEvaluateResult:
    """
    Evaluates multiple leads in a batch within current organization.
    Tenant-isolated.
    """
    leads = list(
        db.execute(
            select(Lead).where(
                Lead.id.in_(lead_ids),
                Lead.organization_id == current_org.id,
            )
        ).scalars().all()
    )

    results: List[LeadQualificationResult] = []
    qualified_count = 0
    disqualified_count = 0
    unassessed_count = 0

    target_icp = None
    if icp_id:
        target_icp = db.execute(
            select(IdealCustomerProfile).where(
                IdealCustomerProfile.id == icp_id,
                IdealCustomerProfile.organization_id == current_org.id,
            )
        ).scalar_one_or_none()

    for lead in leads:
        eval_res = evaluate_single_lead_qualification(
            db=db,
            current_org=current_org,
            lead=lead,
            icp=target_icp,
            dry_run=dry_run,
            qualification_threshold=qualification_threshold,
        )
        results.append(eval_res)
        if eval_res.qualification_status == "qualified":
            qualified_count += 1
        elif eval_res.qualification_status == "disqualified":
            disqualified_count += 1
        else:
            unassessed_count += 1

    return LeadBatchEvaluateResult(
        total_evaluated=len(results),
        qualified_count=qualified_count,
        disqualified_count=disqualified_count,
        unassessed_count=unassessed_count,
        results=results,
    )
