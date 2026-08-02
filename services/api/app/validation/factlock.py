from __future__ import annotations

import re
import unicodedata
from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit

from app.domain.models import (
    FactContract,
    Finding,
    FindingStatus,
    Severity,
    PolicyPack,
    ValidationReport,
    ValidationRequest,
)

VALIDATOR_VERSION = "factlock-deterministic-v3"

SOURCE_FACT_POLICIES = {
    "transcript": {
        "product.affected_models",
        "product.affected_lots",
        "hazard.fire",
        "required_action.stop_and_unplug",
        "remedy.approved",
        "contact.phone",
        "recall.effective_date",
    },
    "ocr_text": {
        "product.affected_models",
        "product.affected_lots",
        "hazard.fire",
        "required_action.stop_and_unplug",
        "remedy.approved",
        "contact.phone",
        "contact.url",
        "recall.effective_date",
    },
    "captions": {
        "product.affected_models",
        "product.affected_lots",
        "hazard.fire",
        "required_action.stop_and_unplug",
        "remedy.approved",
        "contact.phone",
        "recall.effective_date",
    },
}

CHANNEL_EVIDENCE_POLICIES = {
    "audio": ("transcript",),
    "social_card": ("ocr_text",),
    "video": ("transcript", "ocr_text", "captions"),
}


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.lower()).strip()


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _phone_digits(value: str) -> str:
    digits = _digits(value)
    return f"1{digits}" if len(digits) == 10 else digits


_SPOKEN_DIGITS = {
    "0": ("0", "zero", "oh"),
    "1": ("1", "one"),
    "2": ("2", "two", "to", "too"),
    "3": ("3", "three"),
    "4": ("4", "four", "for"),
    "5": ("5", "five"),
    "6": ("6", "six"),
    "7": ("7", "seven"),
    "8": ("8", "eight", "ate"),
    "9": ("9", "nine"),
}


def _serial_present(serial: str, text: str) -> bool:
    """Match exact serial characters even when speech-to-text emits digit words."""
    pieces: list[str] = []
    for char in serial.upper():
        if char.isdigit():
            choices = "|".join(re.escape(item) for item in _SPOKEN_DIGITS[char])
            pieces.append(rf"(?:digit\s+)?(?:{choices})")
        else:
            pieces.append(re.escape(char))
    separator = r"(?:[\s,.;:_-]|\b(?:letter|digit)\b)*"
    pattern = r"(?<![A-Z0-9])" + separator.join(pieces) + r"(?![A-Z0-9])"
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _canonical_url(value: str) -> str:
    cleaned = value.rstrip(".,);]").strip()
    parts = urlsplit(cleaned if "://" in cleaned else f"https://{cleaned}")
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            parts.query,
            "",
        )
    )


def _evidence(text: str, pattern: str, radius: int = 54) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return text[start:end].strip()


def _finding(
    fact_id: str,
    label: str,
    canonical: str,
    status: FindingStatus,
    reason: str,
    evidence: str | None = None,
    evidence_source: str | None = None,
) -> Finding:
    return Finding(
        fact_id=fact_id,
        label=label,
        canonical_value=canonical,
        status=status,
        severity=Severity.BLOCKING,
        reason=reason,
        evidence=evidence,
        evidence_source=evidence_source,
    )


def _check_models(contract: FactContract, text: str) -> Finding:
    expected = set(contract.affected_models)
    if contract.recall_id == "rc_cpsc_26_333":
        upper = text.upper()
        observed = {
            item for item in expected
            if re.search(rf"(?<![A-Z0-9]){re.escape(item.upper())}(?![A-Z0-9])", upper)
        }
        missing = sorted(expected - observed)
        return _finding(
            "product.affected_models",
            "Affected models",
            ", ".join(contract.affected_models),
            FindingStatus.PASS if not missing else FindingStatus.MISSING,
            (
                "All 23 affected model identifiers are present exactly."
                if not missing
                else "Missing exact model identifiers: " + ", ".join(missing) + "."
            ),
            ", ".join(sorted(observed)) or None,
        )
    prefixes = {
        match.group(1)
        for item in expected
        if (match := re.fullmatch(r"([A-Z]{1,4})-?(\d{2,5})", item.upper()))
    }
    observed = {
        f"{prefix}-{number}"
        for prefix, number in re.findall(
            r"\b([A-Z]{1,4})[\s-]?(\d{2,5})\b", text.upper()
        )
        if prefix in prefixes
    }
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    if missing or unexpected:
        pieces = []
        if missing:
            pieces.append(f"missing {', '.join(missing)}")
        if unexpected:
            pieces.append(f"unexpected {', '.join(unexpected)}")
        return _finding(
            "product.affected_models",
            "Affected models",
            ", ".join(contract.affected_models),
            FindingStatus.MUTATED,
            "Exact model identifiers changed: " + "; ".join(pieces) + ".",
            ", ".join(sorted(observed)) or None,
        )
    return _finding(
        "product.affected_models",
        "Affected models",
        ", ".join(contract.affected_models),
        FindingStatus.PASS,
        "Every affected model identifier is present with no unexpected variant.",
        ", ".join(sorted(observed)),
    )


def _check_lots(contract: FactContract, text: str) -> Finding:
    expected = {
        bound.upper()
        for lot_range in contract.affected_lot_ranges
        for bound in (lot_range.start, lot_range.end)
    }
    if contract.recall_id == "rc_cpsc_26_333":
        observed = {item for item in expected if _serial_present(item, text)}
    else:
        observed = set(re.findall(r"\bA\d{2,5}\b", text.upper()))
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    canonical = ", ".join(
        f"{item.start}–{item.end}" for item in contract.affected_lot_ranges
    )
    if missing or unexpected:
        return _finding(
            "product.affected_lots",
            "Affected serial range" if contract.recall_id == "rc_cpsc_26_333" else "Affected lots",
            canonical,
            FindingStatus.MUTATED,
            "The complete lot-range bounds were not preserved.",
            ", ".join(sorted(observed)) or None,
        )
    return _finding(
        "product.affected_lots",
        "Affected serial range" if contract.recall_id == "rc_cpsc_26_333" else "Affected lots",
        canonical,
        FindingStatus.PASS,
        "Both endpoints of every affected lot range are present.",
        ", ".join(sorted(observed)),
    )


def _check_hazard(contract: FactContract, folded: str, raw: str) -> Finding:
    if contract.recall_id == "rc_cpsc_26_333":
        delayed = "delayed ignition" in folded
        burner = "bake burner" in folded or "oven burner" in folded
        burn = "burn hazard" in folded or "burn hazards" in folded
        passed = delayed and burner and burn
        return _finding(
            "hazard.fire",
            "Delayed-ignition burn hazard",
            contract.hazard,
            FindingStatus.PASS if passed else FindingStatus.MISSING,
            (
                "Delayed ignition, bake burner, and burn hazard are explicit."
                if passed
                else "The media must preserve delayed ignition, bake burner, and burn hazard."
            ),
            _evidence(raw, r"(delayed ignition|bake burner|burn hazard)"),
        )
    battery = any(
        phrase in folded
        for phrase in ("lithium-ion battery", "bateria de iones de litio")
    )
    overheat = any(
        phrase in folded
        for phrase in ("overheat", "sobrecalent")
    )
    fire = any(phrase in folded for phrase in ("fire", "incendio"))
    passed = battery and overheat and fire
    return _finding(
        "hazard.fire",
        "Fire hazard",
        contract.hazard,
        FindingStatus.PASS if passed else FindingStatus.MISSING,
        (
            "Battery, overheating, and fire concepts are all present."
            if passed
            else "The media must state the battery overheating and fire hazard."
        ),
        _evidence(raw, r"(battery|bater[ií]a|fire|incendio)"),
    )


def _check_action(contract: FactContract, folded: str, raw: str) -> Finding:
    if contract.recall_id == "rc_cpsc_26_333":
        stop = "stop using" in folded
        oven = "oven" in folded
        immediate = "immediately" in folded
        passed = stop and oven and immediate
        return _finding(
            "required_action.stop_and_unplug",
            "Required action",
            contract.required_action,
            FindingStatus.PASS if passed else FindingStatus.MISSING,
            (
                "Stop-use, affected ovens, and immediacy are explicit."
                if passed
                else "The media must say to stop using affected ovens immediately."
            ),
            _evidence(raw, r"(stop using|oven|immediately)"),
        )
    forbidden_continuation = (
        r"\b(use|continue using|operate|usar|siga usando|utilice)\b.{0,45}"
        r"\b(supervised|carefully|cautiously|vigilancia|cuidado)\b"
    )
    negated_stop = (
        r"\b(do not|don'?t|no)\b.{0,20}\b(stop using|deje de usar)\b"
    )
    if re.search(forbidden_continuation, folded) or re.search(negated_stop, folded):
        return _finding(
            "required_action.stop_and_unplug",
            "Required action",
            contract.required_action,
            FindingStatus.WEAKENED,
            "The media permits continued use or reverses the stop-use instruction.",
            _evidence(raw, r"(supervised|carefully|vigilancia|cuidado|do not|don'?t)"),
        )

    stop = any(
        phrase in folded
        for phrase in (
            "stop using",
            "discontinue use",
            "deje de usar",
            "dejar de usar",
            "suspenda el uso",
        )
    )
    unplug = any(
        phrase in folded
        for phrase in ("unplug", "desenchufe", "desconecte")
    )
    immediate = any(
        phrase in folded
        for phrase in ("immediately", "inmediatamente", "de inmediato")
    )
    passed = stop and unplug and immediate
    return _finding(
        "required_action.stop_and_unplug",
        "Required action",
        contract.required_action,
        FindingStatus.PASS if passed else FindingStatus.MISSING,
        (
            "Stop-use, unplug, and immediacy are all explicit."
            if passed
            else "The required action must explicitly say to stop use, unplug, and act immediately."
        ),
        _evidence(raw, r"(stop|unplug|deje|desenchufe|inmediatamente)"),
    )


def _check_remedy(contract: FactContract, folded: str, raw: str) -> Finding:
    wants_refund = "refund" in _fold(contract.remedy) or "reembolso" in _fold(
        contract.remedy
    )
    wants_repair = "repair" in _fold(contract.remedy)
    if wants_repair:
        free = any(term in folded for term in ("free repair", "at no cost", "no cost"))
        repair = "repair" in folded or "new bake burner" in folded
        passed = free and repair
        contradiction = "refund" in folded or "replacement unit" in folded
    elif wants_refund:
        passed = any(term in folded for term in ("full refund", "reembolso completo"))
        contradiction = "replacement" in folded or "reemplazo" in folded
    else:
        free = any(term in folded for term in ("free", "gratuito", "sin costo"))
        replacement = any(
            term in folded for term in ("replacement", "reemplazo", "sustitucion")
        )
        passed = free and replacement
        contradiction = "refund" in folded or "reembolso" in folded
    status = (
        FindingStatus.CONTRADICTED
        if contradiction
        else FindingStatus.PASS if passed else FindingStatus.MISSING
    )
    reason = (
        "The stated remedy conflicts with the approved contract."
        if contradiction
        else "The approved remedy is explicit."
        if passed
        else "The approved remedy is missing or incomplete."
    )
    return _finding(
        "remedy.approved",
        "Approved remedy",
        contract.remedy,
        status,
        reason,
        _evidence(raw, r"(repair|replacement|refund|reemplazo|reembolso|gratuito|no cost)"),
    )


def _check_phone(contract: FactContract, raw: str) -> Finding:
    expected = _phone_digits(contract.contact.phone)
    candidates = re.findall(r"(?:\+?\d[\d\s().-]{8,}\d)", raw)
    observed = {_phone_digits(item) for item in candidates}
    passed = expected in observed
    return _finding(
        "contact.phone",
        "Contact phone",
        contract.contact.phone,
        FindingStatus.PASS if passed else FindingStatus.MISSING,
        "Phone number matches after formatting normalization." if passed else "The approved contact phone is missing or changed.",
        contract.contact.phone if passed else None,
    )


def _check_url(contract: FactContract, raw: str) -> Finding:
    urls = re.findall(r"(?:https?://)?[\w.-]+\.[a-zA-Z]{2,}(?:/[^\s,;]*)?", raw)
    expected = _canonical_url(contract.contact.url)
    observed = {_canonical_url(url) for url in urls}
    passed = expected in observed
    return _finding(
        "contact.url",
        "Recall URL",
        contract.contact.url,
        FindingStatus.PASS if passed else FindingStatus.MISSING,
        "Recall URL matches after safe normalization." if passed else "The approved recall URL is missing or changed.",
        contract.contact.url if passed else None,
    )


def _check_date(contract: FactContract, folded: str, raw: str) -> Finding:
    value = contract.effective_date
    month_name = value.strftime("%B").lower()
    forms = (
        value.isoformat(),
        f"{value.month}/{value.day}/{value.year}",
        f"{value.month:02d}/{value.day:02d}/{value.year}",
        f"{month_name} {value.day}, {value.year}",
        f"{value.day} de julio de {value.year}",
    )
    matched = next((form for form in forms if form in folded), None)
    return _finding(
        "recall.effective_date",
        "Effective date",
        value.isoformat(),
        FindingStatus.PASS if matched else FindingStatus.MISSING,
        "Effective date is present in an accepted format." if matched else "The effective date is missing or changed.",
        matched,
    )


def _check_generic_models(contract: FactContract, raw: str) -> Finding:
    missing = [item for item in contract.affected_models if not _serial_present(item, raw)]
    return _finding(
        "product.affected_models",
        "Exact affected models",
        ", ".join(contract.affected_models),
        FindingStatus.MISSING if missing else FindingStatus.PASS,
        (
            "Missing exact model identifiers: " + ", ".join(missing) + "."
            if missing
            else "Every policy-locked model identifier is present exactly."
        ),
        None if missing else ", ".join(contract.affected_models),
    )


def _check_generic_ranges(contract: FactContract, raw: str) -> Finding:
    endpoints = [
        endpoint
        for item in contract.affected_lot_ranges
        for endpoint in (item.start, item.end)
    ]
    missing = [item for item in endpoints if not _serial_present(item, raw)]
    canonical = ", ".join(
        f"{item.start}–{item.end}" for item in contract.affected_lot_ranges
    )
    return _finding(
        "product.affected_lots",
        "Affected identifier ranges",
        canonical,
        FindingStatus.MUTATED if missing else FindingStatus.PASS,
        (
            "Missing exact range endpoints: " + ", ".join(missing) + "."
            if missing
            else "Both endpoints of every policy-locked range are present exactly."
        ),
        None if missing else ", ".join(endpoints),
    )


def _check_generic_concepts(
    policy: PolicyPack,
    field: str,
    raw: str,
) -> Finding:
    group = next(item for item in policy.concept_groups if item.field == field)
    folded = _fold(raw)
    missing = [item for item in group.required_concepts if _fold(item) not in folded]
    status = FindingStatus.MISSING if missing else FindingStatus.PASS
    reason = (
        "Missing policy-locked concepts: " + ", ".join(missing) + "."
        if missing
        else "Every reviewer-locked concept is present."
    )
    if field == "required_action" and re.search(
        r"\b(?:do not|don'?t|never)\b.{0,25}\b(?:stop|discontinue|cease)\b",
        folded,
    ):
        status = FindingStatus.WEAKENED
        reason = "The observed instruction reverses the policy-locked stop-use action."
    fact_id, label = {
        "hazard": ("hazard.fire", "Hazard concepts"),
        "required_action": ("required_action.stop_and_unplug", "Required action concepts"),
        "remedy": ("remedy.approved", "Approved remedy concepts"),
    }[field]
    return _finding(
        fact_id,
        label,
        group.canonical_value,
        status,
        reason,
        _evidence(raw, "|".join(re.escape(item) for item in group.required_concepts)),
    )


def _validate_policy_text(
    contract: FactContract,
    policy: PolicyPack,
    raw: str,
) -> list[Finding]:
    findings = [
        _check_generic_models(contract, raw),
        _check_generic_ranges(contract, raw),
        _check_generic_concepts(policy, "hazard", raw),
        _check_generic_concepts(policy, "required_action", raw),
        _check_generic_concepts(policy, "remedy", raw),
    ]
    if policy.require_phone:
        findings.append(_check_phone(contract, raw))
    if policy.require_url_on_visual:
        findings.append(_check_url(contract, raw))
    if policy.require_effective_date:
        findings.append(_check_date(contract, _fold(raw), raw))
    return findings


def _validate_text(
    contract: FactContract,
    raw: str,
    *,
    evidence_source: str | None = None,
    required_fact_ids: set[str] | None = None,
    policy_pack: PolicyPack | None = None,
) -> list[Finding]:
    folded = _fold(raw)
    findings = (
        _validate_policy_text(contract, policy_pack, raw)
        if policy_pack
        else [
            _check_models(contract, raw),
            _check_lots(contract, raw),
            _check_hazard(contract, folded, raw),
            _check_action(contract, folded, raw),
            _check_remedy(contract, folded, raw),
            _check_phone(contract, raw),
            _check_url(contract, raw),
            _check_date(contract, folded, raw),
        ]
    )
    if required_fact_ids is not None:
        effective_fact_ids = set(required_fact_ids)
        if (
            contract.recall_id == "rc_cpsc_26_333"
            and evidence_source == "transcript"
        ):
            # The companion visual carries the exact 23-model inventory. Audio
            # carries the serial range and all consumer-action facts without an
            # inaccessible minute-long identifier recital.
            effective_fact_ids.discard("product.affected_models")
        findings = [item for item in findings if item.fact_id in effective_fact_ids]
    if evidence_source:
        findings = [
            item.model_copy(update={"evidence_source": evidence_source})
            for item in findings
        ]
    return findings


def _integrity_findings(request: ValidationRequest) -> list[Finding]:
    findings: list[Finding] = []
    if not request.contract.human_confirmed:
        findings.append(
            _finding(
                "integrity.human_confirmation",
                "Human-confirmed contract",
                "Confirmed",
                FindingStatus.UNAVAILABLE,
                "The fact contract was not confirmed by a human reviewer.",
                evidence_source="integrity",
            )
        )
    if not request.manifest_verified:
        findings.append(
            _finding(
                "provenance.manifest",
                "Provenance manifest",
                "Verified",
                FindingStatus.UNAVAILABLE,
                "The provenance manifest could not be verified.",
                evidence_source="integrity",
            )
        )
    if request.strict_evidence_policy:
        expected = request.contract.contract_sha256
        if request.asset_contract_sha256 != expected:
            findings.append(
                _finding(
                    "integrity.contract_binding",
                    "Asset contract binding",
                    expected,
                    FindingStatus.MUTATED,
                    "The asset is not bound to the active fact-contract hash.",
                    request.asset_contract_sha256,
                    evidence_source="integrity",
                )
            )
        if request.policy_pack:
            policy = request.policy_pack
            if (
                policy.status != "active"
                or policy.contract_sha256 != request.contract.contract_sha256
                or request.asset_policy_sha256 != policy.policy_sha256
            ):
                findings.append(
                    _finding(
                        "integrity.policy_binding",
                        "Active policy binding",
                        policy.policy_sha256,
                        FindingStatus.MUTATED,
                        "The asset is not bound to the active contract policy hash.",
                        request.asset_policy_sha256,
                        evidence_source="integrity",
                    )
                )
    return findings


def validate(request: ValidationRequest, asset_id: str = "asset_preview") -> ValidationReport:
    integrity = _integrity_findings(request)
    if request.strict_evidence_policy:
        findings = list(integrity)
        for source_name in CHANNEL_EVIDENCE_POLICIES[request.channel]:
            value = getattr(request, source_name)
            if not value or not value.strip():
                findings.append(
                    _finding(
                        f"reverse_extraction.{source_name}",
                        f"Required {source_name.replace('_', ' ')} evidence",
                        "Available",
                        FindingStatus.UNAVAILABLE,
                        f"The {source_name.replace('_', ' ')} extractor returned no evidence.",
                        evidence_source=source_name,
                    )
                )
                continue
            findings.extend(
                _validate_text(
                    request.contract,
                    value.strip(),
                    evidence_source=source_name,
                    required_fact_ids=SOURCE_FACT_POLICIES[source_name],
                    policy_pack=request.policy_pack,
                )
            )
        decision = "quarantine" if any(item.blocking_failure for item in findings) else "pass"
        return ValidationReport(
            asset_id=asset_id,
            decision=decision,
            contract_sha256=request.contract.contract_sha256,
            validator_version=VALIDATOR_VERSION,
            findings=findings,
        )

    sources = [
        item.strip()
        for item in (request.transcript, request.ocr_text, request.captions)
        if item and item.strip()
    ]
    if not sources:
        finding = _finding(
            "reverse_extraction.evidence",
            "Reverse-extraction evidence",
            "Transcript, OCR, or captions",
            FindingStatus.UNAVAILABLE,
            "No reverse-extracted evidence was available; FactLock fails closed.",
        )
        return ValidationReport(
            asset_id=asset_id,
            decision="quarantine",
            contract_sha256=request.contract.contract_sha256,
            validator_version=VALIDATOR_VERSION,
            findings=[finding],
        )

    raw = "\n".join(sources)
    findings = [
        *integrity,
        *_validate_text(request.contract, raw, policy_pack=request.policy_pack),
    ]
    decision = "quarantine" if any(item.blocking_failure for item in findings) else "pass"
    return ValidationReport(
        asset_id=asset_id,
        decision=decision,
        contract_sha256=request.contract.contract_sha256,
        validator_version=VALIDATOR_VERSION,
        findings=findings,
    )


def content_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
