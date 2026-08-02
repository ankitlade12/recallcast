from __future__ import annotations

import base64
import io
import os
import tempfile
import time
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from textwrap import wrap
from typing import Any
from uuid import uuid4

from app.domain.models import (
    AssetStatus,
    EvidencePackage,
    FactContract,
    MediaArtifact,
    PackageAttemptEvidence,
    PackageReviewRecord,
    PipelineEvent,
    PolicyPack,
    ValidationReport,
    ValidationRequest,
)
from app.providers.genblaze_pipeline import (
    _b2_object_key,
    build_storage,
    run_live_background_generation,
    verify_result,
)
from app.storage.b2 import B2Storage, StoredObject
from app.validation.factlock import validate

TEMPLATE_VERSION = "social-card-v4"
RETRY_POLICY_VERSION = "audio-corrective-v3"


def _configured(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def package_idempotency_key(
    contract: FactContract,
    locale: str,
    policy_pack: PolicyPack | None = None,
) -> str:
    profile = "|".join(
        (
            contract.recall_id,
            contract.contract_sha256,
            locale,
            TEMPLATE_VERSION,
            _configured("OPENAI_IMAGE_MODEL", "gpt-image-2"),
            _configured("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            _configured("OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe"),
            _configured("OPENAI_VISION_MODEL", "gpt-5.6-sol"),
            RETRY_POLICY_VERSION,
            policy_pack.policy_sha256 if policy_pack else "built-in-policy",
        )
    )
    return sha256(profile.encode("utf-8")).hexdigest()


def _package_prefix(contract: FactContract, locale: str) -> str:
    return (
        f"recallcast/recalls/{contract.recall_id}/packages/"
        f"{contract.contract_sha256[:16]}/{locale}"
    )


def _package_key(contract: FactContract, locale: str) -> str:
    return f"{_package_prefix(contract, locale)}/package.json"


def _with_previews(package: EvidencePackage, storage: B2Storage) -> EvidencePackage:
    result = package.model_copy(deep=True)
    for artifact in result.artifacts:
        artifact.preview_url = storage.presign_get(artifact.key, 900)
    return result


def _storage_payload(package: EvidencePackage) -> dict[str, Any]:
    payload = package.model_dump(mode="json")
    for artifact in payload["artifacts"]:
        artifact["preview_url"] = None
    return payload


def load_evidence_package(
    storage: B2Storage,
    contract: FactContract,
    locale: str,
    policy_pack: PolicyPack | None = None,
) -> EvidencePackage | None:
    key = _package_key(contract, locale)
    if not storage.exists(key):
        return None
    package = EvidencePackage.model_validate(storage.get_json(key))
    if package.idempotency_key != package_idempotency_key(contract, locale, policy_pack):
        return None
    if not package.attempts:
        prefix = _package_prefix(contract, locale)
        for artifact in sorted(
            (item for item in package.artifacts if item.kind == "narration"),
            key=lambda item: item.attempt,
        ):
            attempt_prefix = f"{prefix}/attempts/{artifact.attempt:03d}"
            try:
                package.attempts.append(
                    PackageAttemptEvidence(
                        attempt=artifact.attempt,
                        script=storage.get_bytes(
                            f"{attempt_prefix}/script.txt"
                        ).decode("utf-8"),
                        observed_transcript=storage.get_bytes(
                            f"{attempt_prefix}/observed-transcript.txt"
                        ).decode("utf-8"),
                        report=ValidationReport.model_validate(
                            storage.get_json(f"{attempt_prefix}/validation.json")
                        ),
                        accepted=artifact.accepted,
                        run_id=artifact.run_id,
                        parent_run_id=artifact.parent_run_id,
                    )
                )
            except Exception:
                # Older package heads remain readable even when per-attempt
                # evidence predates this response model.
                continue
    return _with_previews(package, storage)


def review_evidence_package(
    storage: B2Storage,
    contract: FactContract,
    locale: str,
    *,
    expected_package_id: str,
    decision: str,
    reviewer: str,
    rationale: str,
    policy_pack: PolicyPack | None = None,
) -> tuple[EvidencePackage, list[StoredObject]]:
    """Persist an immutable human decision and update the package head."""
    package = load_evidence_package(storage, contract, locale, policy_pack)
    if not package:
        raise FileNotFoundError("No generated package exists for review.")
    if package.package_id != expected_package_id:
        raise FileNotFoundError("The requested package is not the current package.")
    if package.status != AssetStatus.NEEDS_REVIEW:
        raise ValueError("The package already has a terminal review decision.")
    if package.report.decision != "pass" or package.report.blocking_failure_count:
        raise ValueError("Only a passing FactLock package is eligible for human review.")
    if decision not in {"approved", "rejected"}:
        raise ValueError("Unsupported human review decision.")

    reviewed_at = datetime.now(timezone.utc)
    status = (
        AssetStatus.APPROVED
        if decision == "approved"
        else AssetStatus.REJECTED
    )
    validation_report_sha256 = sha256(
        package.report.model_dump_json().encode("utf-8")
    ).hexdigest()
    record = PackageReviewRecord(
        package_id=package.package_id,
        recall_id=package.recall_id,
        decision=decision,
        status=status,
        reviewer=reviewer.strip(),
        rationale=rationale.strip(),
        reviewed_at=reviewed_at,
        contract_sha256=package.contract_sha256,
        validation_report_sha256=validation_report_sha256,
        artifact_sha256s=sorted(item.sha256 for item in package.artifacts),
        attestation=(
            (
                "Reviewer approved this unaffiliated RecallCast demo draft for demo "
                "release; this is not CPSC or Electrolux Group approval."
                if contract.recall_id == "rc_cpsc_26_333"
                else "Reviewer approved this contract-bound RecallCast draft for release."
            )
            if decision == "approved"
            else "Reviewer rejected this RecallCast draft; it must not be released."
        ),
    )
    package.status = status
    package.review = record
    package.events.append(
        PipelineEvent(
            stage="human_review",
            label=(
                "Human release decision approved"
                if decision == "approved"
                else "Human release decision rejected"
            ),
            status="completed" if decision == "approved" else "blocked",
            provider=record.reviewer,
            model="manual-release-gate-v1",
            latency_ms=1,
        )
    )

    prefix = _package_prefix(contract, locale)
    metadata = {
        "recall-id": contract.recall_id,
        "package-id": package.package_id,
        "contract-sha256": contract.contract_sha256,
        "decision": decision,
        "reviewer": record.reviewer,
    }
    decision_key = (
        f"{prefix}/reviews/"
        f"{reviewed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{decision}.json"
    )
    decision_object = storage.put_json(
        decision_key,
        record.model_dump(mode="json"),
        metadata=metadata,
        overwrite=False,
    )
    package_object = storage.put_json(
        _package_key(contract, locale),
        _storage_payload(package),
        metadata=metadata,
    )
    return _with_previews(package, storage), [decision_object, package_object]


def _duration_ms(started: float) -> int:
    return max(1, int((time.monotonic() - started) * 1000))


def _genblaze_manifest_key(asset_key: str) -> str:
    return f"{asset_key.rsplit('/assets/', 1)[0]}/manifest.json"


def _load_manifest(storage: B2Storage, asset_key: str) -> tuple[str, bool, dict[str, Any]]:
    from genblaze_core.models.manifest import Manifest

    payload = storage.get_json(_genblaze_manifest_key(asset_key))
    manifest = Manifest.model_validate(payload)
    return manifest.canonical_hash, manifest.verify(), payload


def _obtain_background(
    storage: B2Storage,
    contract: FactContract,
) -> tuple[MediaArtifact, bytes, int]:
    started = time.monotonic()
    if contract.recall_id == "rc_cpsc_26_333":
        from PIL import Image, ImageDraw

        key = f"{_package_prefix(contract, 'en-US')}/neutral-background.png"
        if storage.exists(key):
            content = storage.get_bytes(key)
        else:
            image = Image.new("RGB", (1080, 1080), "#15201d")
            draw = ImageDraw.Draw(image)
            for radius, color in (
                (900, "#24332e"),
                (680, "#392823"),
                (460, "#6f2920"),
                (250, "#c14331"),
            ):
                left = 760 - radius // 2
                top = 340 - radius // 2
                draw.ellipse((left, top, left + radius, top + radius), fill=color)
            draw.rectangle((0, 820, 1080, 1080), fill="#101916")
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
            content = output.getvalue()
            storage.put_bytes(
                key,
                content,
                "image/png",
                metadata={
                    "recall-id": contract.recall_id,
                    "contract-sha256": contract.contract_sha256,
                    "background-policy": "deterministic-neutral-v1",
                },
                overwrite=False,
            )
        artifact = MediaArtifact(
            kind="background",
            key=key,
            uri=f"b2://{storage.settings.bucket}/{key}",
            sha256=sha256(content).hexdigest(),
            content_type="image/png",
            size=len(content),
            provider="RecallCast deterministic compositor",
            model="neutral-background-v1",
            manifest_verified=True,
        )
        return artifact, content, _duration_ms(started)
    configured_key = os.getenv("RECALLCAST_BACKGROUND_KEY", "").strip()
    if configured_key and storage.exists(configured_key):
        content = storage.get_bytes(configured_key)
        manifest_hash, verified, payload = _load_manifest(storage, configured_key)
        step = payload["run"]["steps"][0]
        artifact = MediaArtifact(
            kind="background",
            key=configured_key,
            uri=f"b2://{storage.settings.bucket}/{configured_key}",
            sha256=sha256(content).hexdigest(),
            content_type="image/png",
            size=len(content),
            provider=step["provider"],
            model=step["model"],
            manifest_hash=manifest_hash,
            manifest_verified=verified,
        )
        return artifact, content, _duration_ms(started)

    generated = run_live_background_generation()
    key = generated["asset_key"]
    content = storage.get_bytes(key)
    artifact = MediaArtifact(
        kind="background",
        key=key,
        uri=f"b2://{storage.settings.bucket}/{key}",
        sha256=generated["asset_sha256"],
        content_type="image/png",
        size=len(content),
        provider=generated["provider"],
        model=generated["model"],
        manifest_hash=generated["manifest_hash"],
        manifest_verified=generated["manifest_verified"],
    )
    return artifact, content, _duration_ms(started)


def _date_label(value: date, locale: str) -> str:
    if locale == "es-US":
        months = (
            "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
        )
        return f"{value.day} de {months[value.month - 1]} de {value.year}"
    return value.strftime("%B %d, %Y").replace(" 0", " ")


def _localized_card_copy(contract: FactContract, locale: str) -> dict[str, str]:
    lots = ", ".join(
        f"{item.start}-{item.end}" for item in contract.affected_lot_ranges
    )
    if contract.recall_id == "rc_cpsc_26_333":
        serial = contract.affected_lot_ranges[0]
        return {
            "heading": "PUBLIC-SOURCE PRODUCT SAFETY RECALL",
            "models": (
                f"23 AFFECTED MODELS  |  SERIALS {serial.start}-{serial.end}"
            ),
            "hazard": contract.hazard,
            "action": "STOP USING OVENS IN THE RECALLED RANGES IMMEDIATELY.",
            "remedy": "Free repair with professional in-home installation at no cost",
            "contact": f"Call {contract.contact.phone}",
            "effective": f"Recall date: {_date_label(contract.effective_date, locale)}",
            "draft": "UNAFFILIATED AI DRAFT · VERIFY AT CPSC.GOV · HUMAN REVIEW REQUIRED",
        }
    if locale == "es-US":
        refund = "refund" in contract.remedy.lower()
        return {
            "heading": "RETIRO URGENTE DE SEGURIDAD",
            "models": f"MODELOS {' + '.join(contract.affected_models)}  |  LOTES {lots}",
            "hazard": "La batería de iones de litio puede sobrecalentarse y provocar un incendio.",
            "action": "DEJE DE USAR Y DESENCHUFE EL CALENTADOR INMEDIATAMENTE.",
            "remedy": "Reembolso completo disponible." if refund else "Reemplazo gratuito disponible.",
            "contact": f"Llame al {contract.contact.phone}",
            "effective": f"Vigente: {_date_label(contract.effective_date, locale)}",
            "draft": "BORRADOR · REQUIERE APROBACIÓN HUMANA",
        }
    return {
        "heading": "URGENT PRODUCT SAFETY RECALL",
        "models": f"MODELS {' + '.join(contract.affected_models)}  |  LOTS {lots}",
        "hazard": contract.hazard,
        "action": contract.required_action.upper(),
        "remedy": contract.remedy.rstrip("."),
        "contact": f"Call {contract.contact.phone}",
        "effective": f"Effective: {_date_label(contract.effective_date, locale)}",
        "draft": "DRAFT · HUMAN APPROVAL REQUIRED",
    }


def _font_path(*, bold: bool = False) -> str:
    configured = os.getenv("RECALLCAST_FONT_PATH", "").strip()
    candidates = [
        configured,
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError(
        "A Unicode-capable TrueType font is required for safe media composition."
    )


def compose_social_card(
    background: bytes,
    contract: FactContract,
    locale: str,
) -> tuple[bytes, str]:
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    if contract.recall_id == "rc_cpsc_26_333":
        return _compose_real_case_card(background, contract)

    image = Image.open(io.BytesIO(background)).convert("RGB")
    image = ImageOps.fit(image, (1080, 1080), method=Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, 1080, 1080), fill=(8, 16, 15, 168))
    draw.rectangle((0, 0, 1080, 118), fill=(214, 54, 38, 244))
    draw.rounded_rectangle((54, 470, 1026, 690), radius=24, fill=(145, 27, 20, 238))
    draw.rectangle((0, 990, 1080, 1080), fill=(12, 24, 22, 245))

    regular_font = _font_path()
    bold_font = _font_path(bold=True)
    fonts = {
        "heading": ImageFont.truetype(bold_font, size=42),
        "product": ImageFont.truetype(bold_font, size=66),
        "meta": ImageFont.truetype(bold_font, size=27),
        "body": ImageFont.truetype(regular_font, size=35),
        "action": ImageFont.truetype(bold_font, size=45),
        "small": ImageFont.truetype(regular_font, size=24),
    }
    copy = _localized_card_copy(contract, locale)

    def lines(text: str, width: int) -> str:
        return "\n".join(wrap(text, width=width, break_long_words=False))

    draw.text((58, 36), copy["heading"], font=fonts["heading"], fill="white")
    draw.multiline_text(
        (58, 160), lines(contract.product_name, 27),
        font=fonts["product"], fill="white", spacing=8,
    )
    draw.text((58, 330), copy["models"], font=fonts["meta"], fill=(255, 215, 204))
    draw.multiline_text(
        (58, 382), lines(copy["hazard"], 51),
        font=fonts["body"], fill="white", spacing=8,
    )
    draw.multiline_text(
        (82, 516), lines(copy["action"], 36),
        font=fonts["action"], fill="white", spacing=12,
    )
    draw.text((58, 728), copy["remedy"], font=fonts["body"], fill=(255, 229, 167))
    draw.text((58, 792), copy["contact"], font=fonts["body"], fill="white")
    draw.text((58, 850), contract.contact.url, font=fonts["meta"], fill=(207, 235, 226))
    draw.text((58, 910), copy["effective"], font=fonts["small"], fill=(223, 225, 220))
    draw.text((58, 1018), copy["draft"], font=fonts["small"], fill=(255, 196, 184))

    rendered = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    output = io.BytesIO()
    rendered.save(output, format="PNG", optimize=True)
    visible_text = "\n".join(
        (
            copy["heading"],
            contract.product_name,
            copy["models"],
            copy["hazard"],
            copy["action"],
            copy["remedy"],
            copy["contact"],
            contract.contact.url,
            copy["effective"],
            copy["draft"],
        )
    )
    return output.getvalue(), visible_text


def _compose_real_case_card(
    background: bytes,
    contract: FactContract,
) -> tuple[bytes, str]:
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    image = Image.open(io.BytesIO(background)).convert("RGB")
    image = ImageOps.fit(image, (1080, 1080), method=Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, 1080, 1080), fill=(8, 16, 15, 178))
    draw.rectangle((0, 0, 1080, 96), fill=(214, 54, 38, 246))
    draw.rounded_rectangle((48, 580, 1032, 720), radius=22, fill=(145, 27, 20, 242))
    draw.rectangle((0, 990, 1080, 1080), fill=(12, 24, 22, 248))

    regular = _font_path()
    bold = _font_path(bold=True)
    fonts = {
        "heading": ImageFont.truetype(bold, size=34),
        "product": ImageFont.truetype(bold, size=56),
        "serial": ImageFont.truetype(bold, size=25),
        "model": ImageFont.truetype(regular, size=18),
        "body": ImageFont.truetype(regular, size=29),
        "action": ImageFont.truetype(bold, size=38),
        "small": ImageFont.truetype(regular, size=21),
    }
    copy = _localized_card_copy(contract, "en-US")
    serial = contract.affected_lot_ranges[0]
    model_lines = "\n".join(
        "   ".join(contract.affected_models[index:index + 5])
        for index in range(0, len(contract.affected_models), 5)
    )

    def lines(text: str, width: int) -> str:
        return "\n".join(wrap(text, width=width, break_long_words=False))

    draw.text((48, 29), copy["heading"], font=fonts["heading"], fill="white")
    draw.text((48, 122), contract.product_name, font=fonts["product"], fill="white")
    draw.text(
        (48, 205),
        f"SERIAL RANGE  {serial.start} THROUGH {serial.end}",
        font=fonts["serial"],
        fill=(255, 211, 199),
    )
    draw.text((48, 260), "AFFECTED MODELS", font=fonts["serial"], fill=(255, 229, 167))
    draw.multiline_text(
        (48, 305), model_lines, font=fonts["model"], fill="white", spacing=9
    )
    draw.multiline_text(
        (48, 455), lines(copy["hazard"], 65),
        font=fonts["body"], fill="white", spacing=7,
    )
    draw.multiline_text(
        (72, 615), lines(copy["action"], 44),
        font=fonts["action"], fill="white", spacing=10,
    )
    draw.text((48, 750), copy["remedy"], font=fonts["body"], fill=(255, 229, 167))
    draw.text((48, 805), copy["contact"], font=fonts["body"], fill="white")
    draw.text((48, 852), contract.contact.url, font=fonts["serial"], fill=(207, 235, 226))
    draw.text((48, 902), copy["effective"], font=fonts["small"], fill=(223, 225, 220))
    draw.text((48, 1018), copy["draft"], font=fonts["small"], fill=(255, 196, 184))

    rendered = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    output = io.BytesIO()
    rendered.save(output, format="PNG", optimize=True)
    visible_text = "\n".join(
        (
            copy["heading"],
            contract.product_name,
            f"SERIAL RANGE {serial.start} THROUGH {serial.end}",
            "AFFECTED MODELS",
            *contract.affected_models,
            copy["hazard"],
            copy["action"],
            copy["remedy"],
            copy["contact"],
            contract.contact.url,
            copy["effective"],
            copy["draft"],
        )
    )
    return output.getvalue(), visible_text


def compose_consumer_alert_card(
    background: bytes,
    contract: FactContract,
) -> tuple[bytes, str]:
    """Compose the simple consumer alert shipped with the eligibility card."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    image = Image.open(io.BytesIO(background)).convert("RGB")
    image = ImageOps.fit(image, (1080, 1080), method=Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, 1080, 1080), fill=(6, 15, 13, 148))
    draw.rectangle((0, 0, 1080, 116), fill=(218, 54, 39, 250))
    draw.rounded_rectangle((48, 350, 1032, 590), radius=26, fill=(154, 28, 20, 246))
    draw.rounded_rectangle((48, 632, 1032, 895), radius=22, fill=(9, 25, 21, 230))
    draw.rectangle((0, 990, 1080, 1080), fill=(8, 19, 16, 250))

    regular = _font_path()
    bold = _font_path(bold=True)
    fonts = {
        "kicker": ImageFont.truetype(bold, size=32),
        "product": ImageFont.truetype(bold, size=68),
        "meta": ImageFont.truetype(bold, size=27),
        "action": ImageFont.truetype(bold, size=55),
        "body": ImageFont.truetype(regular, size=31),
        "body_bold": ImageFont.truetype(bold, size=31),
        "small": ImageFont.truetype(regular, size=22),
    }
    serial = contract.affected_lot_ranges[0]
    hazard = (
        "The oven's bake burner can ignite late and cause burn injuries."
    )
    action = "STOP USING THE OVEN\nIMMEDIATELY"
    eligibility = (
        f"23 affected models · serials {serial.start}–{serial.end}\n"
        "Check the companion eligibility card before taking action."
    )

    draw.text((48, 37), "URGENT PRODUCT SAFETY RECALL", font=fonts["kicker"], fill="white")
    draw.text((48, 160), "Frigidaire Gas Ranges", font=fonts["product"], fill="white")
    draw.text((48, 260), "CPSC RECALL 26-333 · MARCH 19, 2026", font=fonts["meta"], fill=(255, 217, 176))
    draw.multiline_text((78, 392), action, font=fonts["action"], fill="white", spacing=10)
    draw.text((70, 655), hazard, font=fonts["body"], fill="white")
    draw.multiline_text((70, 720), eligibility, font=fonts["body"], fill=(218, 235, 228), spacing=12)
    draw.text((70, 828), "Free in-home repair at no cost", font=fonts["body_bold"], fill=(255, 225, 153))
    draw.text((48, 925), f"Call {contract.contact.phone}  ·  gasovenburnerrecall.com", font=fonts["meta"], fill="white")
    draw.text((48, 1021), "UNAFFILIATED AI DRAFT · VERIFY AT CPSC.GOV · DISTRIBUTE WITH ELIGIBILITY CARD", font=fonts["small"], fill=(255, 195, 183))

    rendered = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    output = io.BytesIO()
    rendered.save(output, format="PNG", optimize=True)
    visible_text = "\n".join(
        (
            "URGENT PRODUCT SAFETY RECALL",
            contract.product_name,
            "CPSC RECALL 26-333",
            "MARCH 19, 2026",
            action.replace("\n", " "),
            hazard,
            eligibility.replace("\n", " "),
            "Free in-home repair at no cost",
            f"Call {contract.contact.phone}",
            "gasovenburnerrecall.com",
            "UNAFFILIATED AI DRAFT · VERIFY AT CPSC.GOV · DISTRIBUTE WITH ELIGIBILITY CARD",
        )
    )
    return output.getvalue(), visible_text


def _ensure_real_case_media_kit(
    storage: B2Storage,
    contract: FactContract,
    locale: str,
    package: EvidencePackage,
) -> EvidencePackage:
    if contract.recall_id != "rc_cpsc_26_333":
        return package
    if any(item.kind == "consumer_card" for item in package.artifacts):
        return package
    if package.status in {AssetStatus.APPROVED, AssetStatus.REJECTED}:
        # Never add an artifact after a terminal review hash binding.
        return package
    background = next(
        (item for item in package.artifacts if item.kind == "background"),
        None,
    )
    if not background:
        return package

    started = time.monotonic()
    content, overlay_text = compose_consumer_alert_card(
        storage.get_bytes(background.key), contract
    )
    prefix = _package_prefix(contract, locale)
    metadata = {
        "recall-id": contract.recall_id,
        "package-id": package.package_id,
        "contract-sha256": contract.contract_sha256,
        "locale": locale,
        "template-version": "consumer-alert-v1",
        "companion-required": "true",
    }
    stored = storage.put_bytes(
        f"{prefix}/consumer-alert.png",
        content,
        "image/png",
        metadata=metadata,
        overwrite=False,
    )
    storage.put_text(
        f"{prefix}/consumer-alert-overlay.txt",
        overlay_text,
        metadata=metadata,
        overwrite=False,
    )
    package.artifacts.insert(
        1,
        MediaArtifact(
            kind="consumer_card",
            key=stored.key,
            uri=stored.uri,
            sha256=stored.sha256,
            content_type=stored.content_type,
            size=stored.size,
            provider="RecallCast deterministic compositor",
            model="consumer-alert-v1",
            manifest_verified=True,
        ),
    )
    package.events.insert(
        2,
        PipelineEvent(
            stage="compose_consumer",
            label="Consumer alert paired with eligibility companion",
            status="completed",
            provider="RecallCast deterministic compositor",
            model="consumer-alert-v1",
            latency_ms=_duration_ms(started),
        ),
    )
    storage.put_json(
        _package_key(contract, locale),
        _storage_payload(package),
        metadata=metadata,
    )
    return _with_previews(package, storage)


def _extract_visible_text(card: bytes) -> tuple[str, str, int]:
    from openai import OpenAI

    started = time.monotonic()
    model = _configured("OPENAI_VISION_MODEL", "gpt-5.6-sol")
    encoded = base64.b64encode(card).decode("ascii")
    response = OpenAI(timeout=120).responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Transcribe every visible word, number, model code, lot code, "
                            "phone number, URL, and date in this safety card exactly. "
                            "Return only the transcription. Do not correct, summarize, "
                            "translate, infer, or add missing text."
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{encoded}",
                        "detail": "original",
                    },
                ],
            }
        ],
    )
    return response.output_text.strip(), model, _duration_ms(started)


def _generate_narration(
    script: str,
    locale: str,
    storage: B2Storage,
    output_dir: Path,
    *,
    prior_result: Any | None = None,
    attempt: int = 1,
) -> tuple[MediaArtifact, Path, int, Any]:
    from genblaze_core import Modality, Pipeline
    from genblaze_openai import OpenAITTSProvider

    started = time.monotonic()
    model = _configured("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    voice = _configured("OPENAI_TTS_VOICE", "coral")
    output_dir.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline(
        "recallcast-narration",
        project_id="recallcast",
        structured_log=True,
    ).metadata(
        locale=locale,
        ai_voice=True,
        attempt=attempt,
        retry_policy=RETRY_POLICY_VERSION,
    )
    if prior_result is not None:
        pipeline.from_result(prior_result)
    result = (
        pipeline.step(
            OpenAITTSProvider(http_timeout=120, output_dir=output_dir),
            model=model,
            prompt=script,
            modality=Modality.AUDIO,
            params={
                "voice": voice,
                "response_format": "mp3",
                "instructions": (
                    "Speak clearly in a calm, urgent public-safety tone. "
                    "Preserve every word and identifier exactly. Do not add or omit content."
                ),
            },
            metadata={
                "locale": locale,
                "approved_script": True,
                "attempt": attempt,
                "corrective_retry": prior_result is not None,
            },
        )
        .run(sink=build_storage(), timeout=180, max_retries=1)
    )
    verify_result(result)
    step = result.run.steps[0]
    asset = step.assets[0]
    audio_path = next(output_dir.glob("*.mp3"))
    key = _b2_object_key(asset.url, storage.settings.bucket)
    artifact = MediaArtifact(
        kind="narration",
        key=key,
        uri=f"b2://{storage.settings.bucket}/{key}",
        sha256=asset.sha256 or sha256(audio_path.read_bytes()).hexdigest(),
        content_type="audio/mpeg",
        size=asset.size_bytes or audio_path.stat().st_size,
        provider=step.provider or "openai-tts",
        model=step.model,
        manifest_hash=result.manifest.canonical_hash,
        manifest_verified=result.manifest.verify(),
        run_id=result.run.run_id,
        parent_run_id=result.run.parent_run_id,
        attempt=attempt,
    )
    return artifact, audio_path, _duration_ms(started), result


def _transcribe_narration(audio_path: Path) -> tuple[str, str, int]:
    from openai import OpenAI

    started = time.monotonic()
    model = _configured("OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe")
    with audio_path.open("rb") as audio:
        response = OpenAI(timeout=120).audio.transcriptions.create(
            model=model,
            file=audio,
            prompt=(
                "A product-safety recall announcement. Preserve model identifiers, "
                "lot codes, phone numbers, URLs, dates, negation, and action verbs exactly."
            ),
        )
    return response.text.strip(), model, _duration_ms(started)


def _corrective_narration_script(
    contract: FactContract,
    locale: str,
) -> str:
    """Rebuild narration from locked facts with fragile facts made redundant."""
    if contract.recall_id == "rc_cpsc_26_333":
        from app.real_case import real_case_corrective_narration_script

        return real_case_corrective_narration_script()
    effective = _date_label(contract.effective_date, locale)
    if locale == "es-US":
        lots = " y ".join(
            f"{item.start} a {item.end}" for item in contract.affected_lot_ranges
        )
        models = " y ".join(contract.affected_models)
        if contract.recall_id == "rc_demo_001":
            remedy = (
                "Hay un reembolso completo disponible."
                if "refund" in contract.remedy.lower()
                else "Hay un reemplazo gratuito disponible."
            )
            return (
                f"Vigente el {effective}. Retiro urgente del "
                f"{contract.product_name}, modelos {models}, lotes {lots}. "
                "La batería de iones de litio puede sobrecalentarse y provocar un "
                "incendio. Deje de usar y desenchufe el calentador inmediatamente. "
                f"{remedy} Llame al {contract.contact.phone}. "
                f"Repito: vigente el {effective}."
            )
        return (
            f"Vigente el {effective}. Retiro urgente del "
            f"{contract.product_name}, modelos {models}, lotes {lots}. "
            f"{contract.hazard} {contract.required_action} "
            f"{contract.remedy} Llame al {contract.contact.phone}. "
            f"Repito: vigente el {effective}."
        )
    lots = " and ".join(
        f"{item.start} through {item.end}"
        for item in contract.affected_lot_ranges
    )
    models = " and ".join(contract.affected_models)
    return (
        f"Effective {_date_label(contract.effective_date, locale)}. Urgent product "
        f"recall for the {contract.product_name}, models {models}, lots {lots}. "
        f"{contract.hazard} {contract.required_action} {contract.remedy} "
        f"Call {contract.contact.phone}. "
        f"I repeat: effective {_date_label(contract.effective_date, locale)}."
    )


def contract_narration_script(contract: FactContract, locale: str = "en-US") -> str:
    """Compose narration exclusively from locked contract values."""
    return _corrective_narration_script(contract, locale)


def _audio_report(
    contract: FactContract,
    package_id: str,
    transcript: str,
    manifest_verified: bool,
    attempt: int,
    policy_pack: PolicyPack | None = None,
) -> ValidationReport:
    return validate(
        ValidationRequest(
            contract=contract,
            channel="audio",
            transcript=transcript,
            manifest_verified=manifest_verified,
            asset_contract_sha256=contract.contract_sha256,
            strict_evidence_policy=True,
            policy_pack=policy_pack,
            asset_policy_sha256=(policy_pack.policy_sha256 if policy_pack else None),
        ),
        asset_id=f"{package_id}:narration:{attempt}",
    )


def _combined_report(
    contract: FactContract,
    package_id: str,
    transcript: str,
    ocr_text: str,
    manifests_verified: bool,
    policy_pack: PolicyPack | None = None,
) -> ValidationReport:
    audio = _audio_report(
        contract, package_id, transcript, manifests_verified, attempt=1,
        policy_pack=policy_pack,
    )
    card = validate(
        ValidationRequest(
            contract=contract,
            channel="social_card",
            ocr_text=ocr_text,
            manifest_verified=manifests_verified,
            asset_contract_sha256=contract.contract_sha256,
            strict_evidence_policy=True,
            policy_pack=policy_pack,
            asset_policy_sha256=(policy_pack.policy_sha256 if policy_pack else None),
        ),
        asset_id=f"{package_id}:social_card",
    )
    findings = [*audio.findings, *card.findings]
    return ValidationReport(
        asset_id=package_id,
        decision="quarantine" if any(item.blocking_failure for item in findings) else "pass",
        contract_sha256=contract.contract_sha256,
        validator_version=audio.validator_version,
        findings=findings,
    )


def revalidate_evidence_package(
    storage: B2Storage,
    contract: FactContract,
    locale: str,
    policy_pack: PolicyPack | None = None,
) -> EvidencePackage:
    package = load_evidence_package(storage, contract, locale, policy_pack)
    if not package:
        raise RuntimeError("No stored evidence package exists for this contract and locale.")
    started = time.monotonic()
    manifests_verified = all(
        item.manifest_verified
        for item in package.artifacts
        if item.kind == "background" or (item.kind == "narration" and item.accepted)
    )
    package.report = _combined_report(
        contract,
        package.package_id,
        package.observed_transcript,
        package.observed_ocr,
        manifests_verified,
        policy_pack,
    )
    package.status = (
        AssetStatus.NEEDS_REVIEW
        if package.report.decision == "pass"
        else AssetStatus.QUARANTINED
    )
    package.events = [item for item in package.events if item.stage != "validate"]
    package.events.append(
        PipelineEvent(
            stage="validate",
            label="Stored evidence revalidated per modality",
            status="completed" if package.report.decision == "pass" else "blocked",
            provider="RecallCast",
            model=package.report.validator_version,
            latency_ms=_duration_ms(started),
            attempt=2,
        )
    )
    prefix = _package_prefix(contract, locale)
    metadata = {
        "recall-id": contract.recall_id,
        "package-id": package.package_id,
        "contract-sha256": contract.contract_sha256,
        "locale": locale,
    }
    storage.put_json(
        f"{prefix}/validation.json",
        package.report.model_dump(mode="json"),
        metadata=metadata,
    )
    storage.put_json(
        _package_key(contract, locale),
        _storage_payload(package),
        metadata=metadata,
    )
    return _with_previews(package, storage)


def generate_evidence_package(
    storage: B2Storage,
    contract: FactContract,
    script: str,
    locale: str,
    *,
    force_regenerate: bool = False,
    policy_pack: PolicyPack | None = None,
) -> EvidencePackage:
    if not force_regenerate:
        existing = load_evidence_package(storage, contract, locale, policy_pack)
        if existing:
            return _ensure_real_case_media_kit(
                storage, contract, locale, existing
            )

    idempotency_key = package_idempotency_key(contract, locale, policy_pack)
    package_id = f"pkg_{idempotency_key[:16]}"
    if force_regenerate:
        package_id = f"{package_id}_{uuid4().hex[:6]}"
    events: list[PipelineEvent] = []

    background, background_bytes, latency = _obtain_background(storage, contract)
    events.append(
        PipelineEvent(
            stage="generate_background",
            label="Creative background generated and verified",
            status="completed",
            provider=background.provider,
            model=background.model,
            latency_ms=latency,
        )
    )

    started = time.monotonic()
    card_bytes, overlay_text = compose_social_card(
        background_bytes, contract, locale
    )
    prefix = _package_prefix(contract, locale)
    card_object = storage.put_bytes(
        f"{prefix}/social-card.png",
        card_bytes,
        "image/png",
        metadata={
            "recall-id": contract.recall_id,
            "contract-sha256": contract.contract_sha256,
            "locale": locale,
            "template-version": TEMPLATE_VERSION,
        },
    )
    card = MediaArtifact(
        kind="social_card",
        key=card_object.key,
        uri=card_object.uri,
        sha256=card_object.sha256,
        content_type=card_object.content_type,
        size=card_object.size,
        provider="RecallCast deterministic compositor",
        model=TEMPLATE_VERSION,
        manifest_verified=True,
    )
    events.append(
        PipelineEvent(
            stage="compose",
            label="Locked social card composed",
            status="completed",
            provider=card.provider,
            model=card.model,
            latency_ms=_duration_ms(started),
        )
    )

    narration_artifacts: list[MediaArtifact] = []
    attempt_evidence: list[tuple[int, str, str, ValidationReport]] = []
    final_script = script
    with tempfile.TemporaryDirectory(prefix="recallcast-package-") as directory:
        root = Path(directory)
        narration, audio_path, narration_ms, narration_result = _generate_narration(
            script, locale, storage, root / "attempt-1", attempt=1
        )
        events.append(
            PipelineEvent(
                stage="narrate",
                label="AI narration generated through Genblaze",
                status="completed",
                provider=narration.provider,
                model=narration.model,
                latency_ms=narration_ms,
                attempt=1,
            )
        )
        transcript, transcription_model, transcription_ms = _transcribe_narration(
            audio_path
        )
        events.append(
            PipelineEvent(
                stage="transcribe",
                label="Generated narration reverse-transcribed",
                status="completed",
                provider="OpenAI",
                model=transcription_model,
                latency_ms=transcription_ms,
                attempt=1,
            )
        )
        audio_report = _audio_report(
            contract,
            package_id,
            transcript,
            narration.manifest_verified,
            attempt=1,
            policy_pack=policy_pack,
        )
        narration.accepted = audio_report.decision == "pass"
        narration_artifacts.append(narration)
        attempt_evidence.append((1, script, transcript, audio_report))
        events.append(
            PipelineEvent(
                stage="validate_audio",
                label="Narration facts independently checked",
                status="completed" if narration.accepted else "blocked",
                provider="RecallCast",
                model=audio_report.validator_version,
                latency_ms=1,
                attempt=1,
            )
        )

        if not narration.accepted:
            final_script = _corrective_narration_script(contract, locale)
            retry, retry_path, retry_ms, _ = _generate_narration(
                final_script,
                locale,
                storage,
                root / "attempt-2",
                prior_result=narration_result,
                attempt=2,
            )
            events.append(
                PipelineEvent(
                    stage="narrate",
                    label="Contract-derived corrective narration generated",
                    status="fallback",
                    provider=retry.provider,
                    model=retry.model,
                    latency_ms=retry_ms,
                    attempt=2,
                )
            )
            transcript, transcription_model, transcription_ms = _transcribe_narration(
                retry_path
            )
            events.append(
                PipelineEvent(
                    stage="transcribe",
                    label="Corrective narration reverse-transcribed",
                    status="completed",
                    provider="OpenAI",
                    model=transcription_model,
                    latency_ms=transcription_ms,
                    attempt=2,
                )
            )
            audio_report = _audio_report(
                contract,
                package_id,
                transcript,
                retry.manifest_verified,
                attempt=2,
                policy_pack=policy_pack,
            )
            retry.accepted = audio_report.decision == "pass"
            narration_artifacts.append(retry)
            attempt_evidence.append((2, final_script, transcript, audio_report))
            events.append(
                PipelineEvent(
                    stage="validate_audio",
                    label="Corrective narration facts independently checked",
                    status="completed" if retry.accepted else "blocked",
                    provider="RecallCast",
                    model=audio_report.validator_version,
                    latency_ms=1,
                    attempt=2,
                )
            )

    ocr_text, vision_model, ocr_ms = _extract_visible_text(card_bytes)
    events.append(
        PipelineEvent(
            stage="extract_visual",
            label="Final social card independently read",
            status="completed",
            provider="OpenAI",
            model=vision_model,
            latency_ms=ocr_ms,
        )
    )

    started = time.monotonic()
    accepted_narration = next(
        (item for item in narration_artifacts if item.accepted),
        narration_artifacts[-1],
    )
    manifests_verified = (
        background.manifest_verified and accepted_narration.manifest_verified
    )
    report = _combined_report(
        contract, package_id, transcript, ocr_text, manifests_verified,
        policy_pack,
    )
    status = (
        AssetStatus.NEEDS_REVIEW
        if report.decision == "pass"
        else AssetStatus.QUARANTINED
    )
    events.append(
        PipelineEvent(
            stage="validate",
            label="Per-modality FactLock checks complete",
            status="completed" if report.decision == "pass" else "blocked",
            provider="RecallCast",
            model=report.validator_version,
            latency_ms=_duration_ms(started),
        )
    )

    metadata = {
        "recall-id": contract.recall_id,
        "package-id": package_id,
        "contract-sha256": contract.contract_sha256,
        "locale": locale,
    }
    for attempt, attempt_script, attempt_transcript, attempt_report in attempt_evidence:
        attempt_prefix = f"{prefix}/attempts/{attempt:03d}"
        storage.put_text(
            f"{attempt_prefix}/script.txt", attempt_script, metadata=metadata
        )
        storage.put_text(
            f"{attempt_prefix}/observed-transcript.txt",
            attempt_transcript,
            metadata=metadata,
        )
        storage.put_json(
            f"{attempt_prefix}/validation.json",
            attempt_report.model_dump(mode="json"),
            metadata=metadata,
        )
    storage.put_text(f"{prefix}/approved-script.txt", final_script, metadata=metadata)
    storage.put_text(f"{prefix}/observed-transcript.txt", transcript, metadata=metadata)
    storage.put_text(f"{prefix}/observed-ocr.txt", ocr_text, metadata=metadata)
    storage.put_text(f"{prefix}/overlay-manifest.txt", overlay_text, metadata=metadata)
    storage.put_json(
        f"{prefix}/validation.json",
        report.model_dump(mode="json"),
        metadata=metadata,
    )

    package = EvidencePackage(
        package_id=package_id,
        idempotency_key=idempotency_key,
        recall_id=contract.recall_id,
        source_version=contract.version,
        contract_sha256=contract.contract_sha256,
        policy_sha256=policy_pack.policy_sha256 if policy_pack else None,
        locale=locale,
        status=status,
        script=final_script,
        observed_transcript=transcript,
        observed_ocr=ocr_text,
        report=report,
        events=events,
        artifacts=[background, card, *narration_artifacts],
        attempts=[
            PackageAttemptEvidence(
                attempt=attempt,
                script=attempt_script,
                observed_transcript=attempt_transcript,
                report=attempt_report,
                accepted=next(
                    item.accepted
                    for item in narration_artifacts
                    if item.attempt == attempt
                ),
                run_id=next(
                    item.run_id
                    for item in narration_artifacts
                    if item.attempt == attempt
                ),
                parent_run_id=next(
                    item.parent_run_id
                    for item in narration_artifacts
                    if item.attempt == attempt
                ),
            )
            for attempt, attempt_script, attempt_transcript, attempt_report
            in attempt_evidence
        ],
    )
    storage.put_json(
        _package_key(contract, locale),
        _storage_payload(package),
        metadata=metadata,
    )
    return _ensure_real_case_media_kit(
        storage,
        contract,
        locale,
        _with_previews(package, storage),
    )
