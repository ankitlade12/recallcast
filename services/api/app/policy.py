from __future__ import annotations

import re
from datetime import datetime, timezone

from app.domain.models import FactContract, PolicyConceptGroup, PolicyPack


_STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "can", "cause", "for", "from",
    "has", "in", "is", "it", "of", "on", "or", "the", "this", "to", "with",
    "available", "product", "consumer", "consumers",
}
_STOP_ACTIONS = ("stop", "discontinue", "do not use", "don't use", "cease")
_URGENCY = ("immediate", "immediately", "now", "urgent")
_REMEDIES = ("refund", "repair", "replacement", "replace")


def _fold(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _concepts(value: str, *, limit: int = 6) -> tuple[str, ...]:
    result: list[str] = []
    for token in _fold(value).split():
        if len(token) < 3 or token in _STOPWORDS or token in result:
            continue
        result.append(token)
        if len(result) == limit:
            break
    return tuple(result)


def _proposed_group(field: str, value: str) -> PolicyConceptGroup:
    concepts = list(_concepts(value))
    if field == "required_action":
        folded = _fold(value)
        priority = [
            item for item in (*_STOP_ACTIONS, *_URGENCY)
            if _fold(item) in folded
        ]
        concepts = list(dict.fromkeys([*priority, *concepts]))[:8]
    elif field == "remedy":
        folded = _fold(value)
        priority = [item for item in _REMEDIES if item in folded]
        concepts = list(dict.fromkeys([*priority, *concepts]))[:6]
    return PolicyConceptGroup(
        field=field,
        canonical_value=value,
        required_concepts=tuple(concepts),
    )


def build_policy_draft(draft_id: str, contract: FactContract) -> PolicyPack:
    endpoints = tuple(
        endpoint
        for item in contract.affected_lot_ranges
        for endpoint in (item.start, item.end)
    )
    return PolicyPack(
        policy_id=f"policy_{contract.contract_sha256[:16]}",
        draft_id=draft_id,
        recall_id=contract.recall_id,
        contract_sha256=contract.contract_sha256,
        exact_identifiers=contract.affected_models,
        range_endpoints=endpoints,
        concept_groups=(
            _proposed_group("hazard", contract.hazard),
            _proposed_group("required_action", contract.required_action),
            _proposed_group("remedy", contract.remedy),
        ),
        require_phone=bool(contract.contact.phone),
        require_url_on_visual=bool(contract.contact.url),
    )


def activate_policy(
    draft: PolicyPack,
    contract: FactContract,
    groups: tuple[PolicyConceptGroup, ...],
    reviewer: str,
) -> PolicyPack:
    errors: list[str] = []
    if draft.contract_sha256 != contract.contract_sha256:
        errors.append("The policy is not bound to the active contract hash.")
    if not 1 <= len(contract.affected_models) <= 4:
        errors.append("This MVP policy supports 1–4 exact model identifiers per card.")
    if not 1 <= len(contract.affected_lot_ranges) <= 3:
        errors.append("This MVP policy supports 1–3 identifier ranges.")
    if tuple(contract.supported_locales) != ("en-US",):
        errors.append("The custom stop-use template currently supports English (US) only.")
    if not contract.contact.phone.strip() or not contract.contact.url.strip():
        errors.append("This template requires both a contact phone and recall URL.")

    by_field = {group.field: group for group in groups}
    if set(by_field) != {"hazard", "required_action", "remedy"}:
        errors.append("Hazard, required action, and remedy concept rules are required.")
    canonical = {
        "hazard": contract.hazard,
        "required_action": contract.required_action,
        "remedy": contract.remedy,
    }
    for field, value in canonical.items():
        group = by_field.get(field)
        if not group:
            continue
        if group.canonical_value != value:
            errors.append(f"The {field} rule must remain bound to its canonical value.")
        folded_value = _fold(value)
        for concept in group.required_concepts:
            if not _fold(concept) or _fold(concept) not in folded_value:
                errors.append(f"The {field} concept ‘{concept}’ is not source-grounded.")

    action_group = by_field.get("required_action")
    action_concepts = " ".join(
        _fold(item) for item in (action_group.required_concepts if action_group else ())
    )
    if not any(_fold(item) in action_concepts for item in _STOP_ACTIONS):
        errors.append("The required-action rule must lock a stop-use concept.")
    if not any(_fold(item) in action_concepts for item in _URGENCY):
        errors.append("The required-action rule must lock an urgency concept.")
    remedy_group = by_field.get("remedy")
    remedy_concepts = " ".join(
        _fold(item) for item in (remedy_group.required_concepts if remedy_group else ())
    )
    if not any(item in remedy_concepts for item in _REMEDIES):
        errors.append("The remedy rule must lock refund, repair, or replacement.")
    if errors:
        raise ValueError("; ".join(dict.fromkeys(errors)))

    ordered = tuple(by_field[field] for field in ("hazard", "required_action", "remedy"))
    return draft.model_copy(
        update={
            "status": "active",
            "concept_groups": ordered,
            "reviewer": reviewer.strip(),
            "activated_at": datetime.now(timezone.utc),
        }
    )
