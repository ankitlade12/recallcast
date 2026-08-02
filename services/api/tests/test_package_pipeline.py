import io
import json
from hashlib import sha256

import pytest

from PIL import Image

from app.demo import demo_contract
from app.domain.models import AssetStatus, EvidencePackage, ValidationReport
from app.media.package_pipeline import (
    _corrective_narration_script,
    _font_path,
    _package_key,
    compose_consumer_alert_card,
    compose_social_card,
    package_idempotency_key,
    review_evidence_package,
)
from app.real_case import real_case_contract
from app.storage.b2 import StoredObject


class MemoryPackageStorage:
    def __init__(self):
        self.objects: dict[str, object] = {}

    def exists(self, key: str) -> bool:
        return key in self.objects

    def get_json(self, key: str):
        return self.objects[key]

    def presign_get(self, key: str, expires_in: int = 900) -> str:
        return f"https://storage.invalid/{key}"

    def put_json(self, key: str, payload, **_kwargs) -> StoredObject:
        normalized = json.loads(json.dumps(payload, default=str))
        self.objects[key] = normalized
        content = json.dumps(normalized, sort_keys=True).encode("utf-8")
        return StoredObject(
            key=key,
            uri=f"b2://test/{key}",
            sha256=sha256(content).hexdigest(),
            content_type="application/json",
            size=len(content),
        )


def reviewable_real_package() -> tuple[EvidencePackage, object]:
    contract = real_case_contract(human_confirmed=True)
    package = EvidencePackage(
        package_id="pkg_review_test",
        idempotency_key=package_idempotency_key(contract, "en-US"),
        recall_id=contract.recall_id,
        source_version=contract.version,
        contract_sha256=contract.contract_sha256,
        locale="en-US",
        status=AssetStatus.NEEDS_REVIEW,
        script="Approved script",
        observed_transcript="Observed narration",
        observed_ocr="Observed visual text",
        report=ValidationReport(
            asset_id="pkg_review_test",
            decision="pass",
            contract_sha256=contract.contract_sha256,
            findings=[],
        ),
        events=[],
        artifacts=[],
    )
    return package, contract


def test_package_idempotency_is_stable_and_locale_specific():
    contract = demo_contract()
    english = package_idempotency_key(contract, "en-US")
    assert english == package_idempotency_key(contract, "en-US")
    assert english != package_idempotency_key(contract, "es-US")


def test_social_card_compositor_renders_locked_copy():
    background = io.BytesIO()
    Image.new("RGB", (1024, 1536), "#1b2421").save(background, format="PNG")

    card, overlay_text = compose_social_card(
        background.getvalue(), demo_contract(), "en-US"
    )
    rendered = Image.open(io.BytesIO(card))

    assert rendered.size == (1080, 1080)
    assert rendered.format == "PNG"
    assert "NG-100 + NG-110" in overlay_text
    assert "A71-A94" in overlay_text
    assert "A71–A94" not in overlay_text
    assert "STOP USING AND UNPLUG" in overlay_text
    assert "1-800-555-0147" in overlay_text
    assert "https://example.invalid/northstar-recall" in overlay_text


def test_spanish_social_card_contains_localized_safety_action():
    background = io.BytesIO()
    Image.new("RGB", (1080, 1080), "#1b2421").save(background, format="PNG")
    _, overlay_text = compose_social_card(
        background.getvalue(), demo_contract(), "es-US"
    )
    assert "DEJE DE USAR Y DESENCHUFE" in overlay_text
    assert "Reemplazo gratuito" in overlay_text
    assert "batería" in overlay_text
    assert "�" not in overlay_text


def test_compositor_uses_a_unicode_capable_font():
    from PIL import ImageFont

    font = ImageFont.truetype(_font_path(), size=24)
    assert font.getmask("batería · aprobación").getbbox() is not None


def test_corrective_script_repeats_fragile_date_and_omits_spoken_url():
    script = _corrective_narration_script(demo_contract(), "en-US")
    assert script.count("July 29, 2026") == 2
    assert "NG-100" in script and "NG-110" in script
    assert "A71" in script and "A94" in script
    assert "models NG-100 and NG-110" in script
    assert "lots A71 through A94" in script
    assert "https://" not in script


def test_spanish_corrective_script_is_contract_derived():
    script = _corrective_narration_script(demo_contract(), "es-US")
    assert script.count("29 de julio de 2026") == 2
    assert "reemplazo gratuito" in script
    assert "1-800-555-0147" in script


def test_real_case_card_contains_all_models_serials_and_unaffiliated_draft_label():
    background = io.BytesIO()
    Image.new("RGB", (1080, 1080), "#15201d").save(background, format="PNG")
    contract = real_case_contract(human_confirmed=True)
    card, overlay_text = compose_social_card(
        background.getvalue(), contract, "en-US"
    )
    rendered = Image.open(io.BytesIO(card))

    assert rendered.size == (1080, 1080)
    assert all(model in overlay_text for model in contract.affected_models)
    assert "VF52200000" in overlay_text and "VF54399999" in overlay_text
    assert "UNAFFILIATED AI DRAFT" in overlay_text


def test_consumer_alert_is_simple_and_requires_eligibility_companion():
    background = io.BytesIO()
    Image.new("RGB", (1080, 1080), "#15201d").save(background, format="PNG")
    contract = real_case_contract(human_confirmed=True)

    card, overlay_text = compose_consumer_alert_card(
        background.getvalue(), contract
    )
    rendered = Image.open(io.BytesIO(card))

    assert rendered.size == (1080, 1080)
    assert "STOP USING THE OVEN IMMEDIATELY" in overlay_text
    assert "23 affected models" in overlay_text
    assert "companion eligibility card" in overlay_text
    assert "DISTRIBUTE WITH ELIGIBILITY CARD" in overlay_text


def test_human_approval_is_bound_to_package_contract_and_validation():
    package, contract = reviewable_real_package()
    storage = MemoryPackageStorage()
    storage.objects[_package_key(contract, "en-US")] = package.model_dump(mode="json")

    reviewed, stored = review_evidence_package(
        storage,
        contract,
        "en-US",
        expected_package_id=package.package_id,
        decision="approved",
        reviewer="Accountable reviewer",
        rationale="All source facts and final media evidence were reviewed.",
    )

    assert reviewed.status == AssetStatus.APPROVED
    assert reviewed.review is not None
    assert reviewed.review.contract_sha256 == contract.contract_sha256
    assert reviewed.review.validation_report_sha256
    assert reviewed.events[-1].stage == "human_review"
    assert len(stored) == 2
    assert any("/reviews/" in key for key in storage.objects)

    with pytest.raises(ValueError, match="terminal review decision"):
        review_evidence_package(
            storage,
            contract,
            "en-US",
            expected_package_id=package.package_id,
            decision="rejected",
            reviewer="Second reviewer",
            rationale="A terminal decision cannot be overwritten by another reviewer.",
        )


def test_human_rejection_blocks_release_even_after_factlock_passes():
    package, contract = reviewable_real_package()
    storage = MemoryPackageStorage()
    storage.objects[_package_key(contract, "en-US")] = package.model_dump(mode="json")

    reviewed, _ = review_evidence_package(
        storage,
        contract,
        "en-US",
        expected_package_id=package.package_id,
        decision="rejected",
        reviewer="Accountable reviewer",
        rationale="The communication needs editorial changes before release.",
    )

    assert reviewed.status == AssetStatus.REJECTED
    assert reviewed.review is not None
    assert reviewed.review.decision == "rejected"
    assert reviewed.events[-1].status == "blocked"
