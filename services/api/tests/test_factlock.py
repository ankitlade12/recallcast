from app.demo import (
    ACTION_WEAKENING,
    APPROVED_EN,
    APPROVED_ES,
    IDENTIFIER_MUTATION,
    demo_contract,
)
from app.domain.models import FactContract, FindingStatus, ValidationRequest
from app.policy import activate_policy, build_policy_draft
from app.real_case import (
    real_case_contract,
    real_case_corrective_narration_script,
    real_case_narration_script,
)
from app.validation.factlock import validate


def request(text: str | None, locale: str = "en-US", **kwargs):
    return ValidationRequest(
        contract=demo_contract(),
        locale=locale,
        transcript=text,
        **kwargs,
    )


def finding(report, fact_id):
    return next(item for item in report.findings if item.fact_id == fact_id)


def custom_policy_fixture():
    contract = FactContract(
        recall_id="rc_ember_policy_test",
        source_sha256="a" * 64,
        issuer="Acme Safety",
        product_name="Ember Fan",
        affected_models=("EF-20",),
        affected_lot_ranges=({"start": "B10", "end": "B12"},),
        hazard="The motor can overheat and cause a fire.",
        required_action="Stop using the fan immediately.",
        remedy="A full refund is available.",
        contact={"phone": "1-800-555-0100", "url": "https://example.invalid/ember"},
        effective_date="2026-08-01",
        supported_locales=("en-US",),
    )
    draft = build_policy_draft("draft_policy_test", contract)
    return contract, activate_policy(
        draft, contract, draft.concept_groups, "Safety reviewer"
    )


def test_approved_english_passes():
    report = validate(request(APPROVED_EN))
    assert report.decision == "pass"
    assert report.blocking_failure_count == 0


def test_approved_spanish_passes():
    report = validate(request(APPROVED_ES, "es-US"))
    assert report.decision == "pass"


def test_identifier_mutation_is_blocking():
    report = validate(request(IDENTIFIER_MUTATION))
    result = finding(report, "product.affected_models")
    assert report.decision == "quarantine"
    assert result.status == FindingStatus.MUTATED
    assert "NG-110" in result.reason
    assert "NG-101" in result.reason


def test_spoken_identifier_without_hyphen_is_normalized():
    spoken = APPROVED_EN.replace("NG-100", "NG100").replace("NG-110", "NG110")
    report = validate(request(spoken))
    assert finding(report, "product.affected_models").status == FindingStatus.PASS


def test_spoken_identifier_mutation_without_hyphen_is_blocking():
    spoken = APPROVED_EN.replace("NG-110", "NG101")
    report = validate(request(spoken))
    result = finding(report, "product.affected_models")
    assert result.status == FindingStatus.MUTATED
    assert "NG-101" in result.reason


def test_action_weakening_is_blocking():
    report = validate(request(ACTION_WEAKENING))
    result = finding(report, "required_action.stop_and_unplug")
    assert report.decision == "quarantine"
    assert result.status == FindingStatus.WEAKENED


def test_phone_formatting_is_normalized():
    changed = APPROVED_EN.replace("1-800-555-0147", "(800) 555-0147")
    report = validate(request(changed))
    assert finding(report, "contact.phone").status == FindingStatus.PASS


def test_missing_reverse_evidence_fails_closed():
    report = validate(request(None))
    assert report.decision == "quarantine"
    assert report.findings[0].status == FindingStatus.UNAVAILABLE


def test_manifest_failure_quarantines_otherwise_valid_asset():
    report = validate(request(APPROVED_EN, manifest_verified=False))
    assert report.decision == "quarantine"
    assert finding(report, "provenance.manifest").status == FindingStatus.UNAVAILABLE


def test_remedy_change_invalidates_old_message():
    contract = demo_contract(version=2, remedy="Full refund.")
    report = validate(
        ValidationRequest(contract=contract, transcript=APPROVED_EN)
    )
    assert report.decision == "quarantine"
    assert finding(report, "remedy.approved").status == FindingStatus.CONTRADICTED


def test_strict_audio_does_not_require_visual_url():
    spoken = APPROVED_EN.replace(
        " or visit https://example.invalid/northstar-recall", ""
    )
    contract = demo_contract()
    report = validate(
        ValidationRequest(
            contract=contract,
            channel="audio",
            transcript=spoken,
            strict_evidence_policy=True,
            asset_contract_sha256=contract.contract_sha256,
        )
    )
    assert report.decision == "pass"
    assert all(item.evidence_source == "transcript" for item in report.findings)


def test_strict_video_blocks_missing_visual_evidence():
    contract = demo_contract()
    report = validate(
        ValidationRequest(
            contract=contract,
            channel="video",
            transcript=APPROVED_EN,
            captions=APPROVED_EN,
            strict_evidence_policy=True,
            asset_contract_sha256=contract.contract_sha256,
        )
    )
    assert report.decision == "quarantine"
    missing = finding(report, "reverse_extraction.ocr_text")
    assert missing.status == FindingStatus.UNAVAILABLE
    assert missing.evidence_source == "ocr_text"


def test_strict_video_does_not_allow_captions_to_mask_bad_audio():
    contract = demo_contract()
    report = validate(
        ValidationRequest(
            contract=contract,
            channel="video",
            transcript=ACTION_WEAKENING,
            ocr_text=APPROVED_EN,
            captions=APPROVED_EN,
            strict_evidence_policy=True,
            asset_contract_sha256=contract.contract_sha256,
        )
    )
    assert report.decision == "quarantine"
    action_findings = [
        item
        for item in report.findings
        if item.fact_id == "required_action.stop_and_unplug"
    ]
    transcript = next(item for item in action_findings if item.evidence_source == "transcript")
    captions = next(item for item in action_findings if item.evidence_source == "captions")
    assert transcript.status == FindingStatus.WEAKENED
    assert captions.status == FindingStatus.PASS


def test_strict_evidence_requires_contract_hash_binding():
    contract = demo_contract()
    report = validate(
        ValidationRequest(
            contract=contract,
            channel="audio",
            transcript=APPROVED_EN,
            strict_evidence_policy=True,
            asset_contract_sha256="wrong-contract-hash",
        )
    )
    assert report.decision == "quarantine"
    assert finding(report, "integrity.contract_binding").status == FindingStatus.MUTATED


def test_real_case_audio_policy_passes_without_reciting_23_models():
    contract = real_case_contract(human_confirmed=True)
    report = validate(
        ValidationRequest(
            contract=contract,
            channel="audio",
            transcript=real_case_narration_script(),
            strict_evidence_policy=True,
            asset_contract_sha256=contract.contract_sha256,
        )
    )
    assert report.decision == "pass"
    assert not any(
        item.fact_id == "product.affected_models" for item in report.findings
    )


def test_real_case_audio_accepts_exact_serials_spoken_character_by_character():
    contract = real_case_contract(human_confirmed=True)
    report = validate(
        ValidationRequest(
            contract=contract,
            channel="audio",
            transcript=real_case_corrective_narration_script(),
            strict_evidence_policy=True,
            asset_contract_sha256=contract.contract_sha256,
        )
    )
    assert report.decision == "pass"
    assert finding(report, "product.affected_lots").status == FindingStatus.PASS


def test_real_case_audio_rejects_dropped_serial_digit():
    contract = real_case_contract(human_confirmed=True)
    report = validate(
        ValidationRequest(
            contract=contract,
            channel="audio",
            transcript=real_case_narration_script().replace(
                "VF54399999", "VF5499999"
            ),
            strict_evidence_policy=True,
            asset_contract_sha256=contract.contract_sha256,
        )
    )
    assert report.decision == "quarantine"
    assert finding(report, "product.affected_lots").status == FindingStatus.MUTATED


def test_real_case_visual_requires_every_exact_model():
    contract = real_case_contract(human_confirmed=True)
    evidence = " ".join(
        (
            *contract.affected_models,
            "VF52200000 through VF54399999",
            contract.hazard,
            "Stop using ovens in the recalled ranges immediately.",
            "Free repair with professional in-home installation at no cost.",
            contract.contact.phone,
            contract.contact.url,
            "March 19, 2026",
        )
    )
    passed = validate(
        ValidationRequest(
            contract=contract,
            channel="social_card",
            ocr_text=evidence,
            strict_evidence_policy=True,
            asset_contract_sha256=contract.contract_sha256,
        )
    )
    assert passed.decision == "pass"

    missing = evidence.replace(contract.affected_models[-1], "")
    blocked = validate(
        ValidationRequest(
            contract=contract,
            channel="social_card",
            ocr_text=missing,
            strict_evidence_policy=True,
            asset_contract_sha256=contract.contract_sha256,
        )
    )
    assert blocked.decision == "quarantine"
    assert finding(blocked, "product.affected_models").status == FindingStatus.MISSING


def test_custom_policy_passes_and_is_bound_to_the_asset():
    contract, policy = custom_policy_fixture()
    transcript = (
        "Effective August 1, 2026. Recall for Ember Fan model EF-20, lots B10 "
        "through B12. The motor can overheat and cause a fire. Stop using the fan "
        "immediately. A full refund is available. Call 1-800-555-0100."
    )
    report = validate(
        ValidationRequest(
            contract=contract,
            channel="audio",
            transcript=transcript,
            strict_evidence_policy=True,
            asset_contract_sha256=contract.contract_sha256,
            policy_pack=policy,
            asset_policy_sha256=policy.policy_sha256,
        )
    )
    assert report.decision == "pass"
    assert finding(report, "product.affected_models").status == FindingStatus.PASS


def test_custom_policy_blocks_identifier_mutation_and_action_reversal():
    contract, policy = custom_policy_fixture()
    unsafe = (
        "Effective August 1, 2026. Recall for Ember Fan model EF-21, lots B10 "
        "through B12. The motor can overheat and cause a fire. Do not stop using "
        "the fan immediately. A full refund is available. Call 1-800-555-0100."
    )
    report = validate(
        ValidationRequest(
            contract=contract,
            channel="audio",
            transcript=unsafe,
            strict_evidence_policy=True,
            asset_contract_sha256=contract.contract_sha256,
            policy_pack=policy,
            asset_policy_sha256=policy.policy_sha256,
        )
    )
    assert report.decision == "quarantine"
    assert finding(report, "product.affected_models").status == FindingStatus.MISSING
    assert finding(report, "required_action.stop_and_unplug").status == FindingStatus.WEAKENED
