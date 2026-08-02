from __future__ import annotations

import os
from hashlib import sha256
from hmac import compare_digest
from typing import Annotated, Literal
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.demo import APPROVED_EN, APPROVED_ES, NOTICE, SCENARIOS, demo_contract
from app.domain.models import (
    ApproveResponse,
    ActivatePolicyPackRequest,
    AssetStatus,
    ConfirmedIntake,
    ConfirmIntakeRequest,
    DemoRun,
    EvidencePackage,
    FactContract,
    IntakeDraft,
    IntakeRequest,
    PackageGenerateRequest,
    PackageReviewRequest,
    PipelineEvent,
    PolicyPack,
    StorageObjectReference,
    ValidationRequest,
    ValidationReport,
)
from app.intake import (
    contract_from_extraction,
    extract_recall,
    extraction_warnings,
    validate_source,
)
from app.media.package_pipeline import (
    contract_narration_script,
    generate_evidence_package,
    load_evidence_package,
    revalidate_evidence_package,
    review_evidence_package,
)
from app.policy import activate_policy, build_policy_draft
from app.providers.genblaze_pipeline import (
    live_generation_available,
    run_live_background_generation,
    run_sdk_storage_smoke,
)
from app.real_case import (
    CPSC_RECALL_NUMBER,
    CPSC_SOURCE_URL,
    REAL_CASE_NOTICE,
    real_case_contract,
    real_case_narration_script,
)
from app.storage.b2 import (
    asset_prefix,
    get_b2_storage,
    quarantine_prefix,
    source_prefix,
    storage_mode,
)
from app.validation.factlock import content_hash, validate

app = FastAPI(
    title="RecallCast API",
    version="0.1.0",
    description="FactLock validation and recall media orchestration.",
)
allowed_origins = sorted(
    {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        *{
            origin.strip()
            for origin in os.getenv("WEB_ORIGINS", "").split(",")
            if origin.strip()
        },
    }
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_runs: dict[str, DemoRun] = {}
_intakes: dict[str, tuple[IntakeDraft, str]] = {}
_confirmed_intakes: dict[str, FactContract] = {}
_policy_packs: dict[str, PolicyPack] = {}
_lock = Lock()
_package_lock = Lock()
_current_version = 1
_current_remedy = "Free replacement."
_real_case_confirmed = False
_real_case_reviewer: str | None = None


class DemoRunRequest(BaseModel):
    scenario: Literal["approved", "identifier_mutation", "action_weakening"] = (
        "approved"
    )
    locale: Literal["en-US", "es-US"] = "en-US"
    channel: Literal["video", "audio", "social_card"] = "video"


class SourceUpdateRequest(BaseModel):
    remedy: Literal["Full refund."] = "Full refund."


class RealCaseConfirmationRequest(BaseModel):
    reviewer: str = Field(min_length=2, max_length=80)
    acknowledgment: bool


def _admin_authorized(supplied_token: str | None) -> bool:
    expected = os.getenv("RECALLCAST_ADMIN_TOKEN", "")
    return bool(
        expected
        and supplied_token
        and compare_digest(supplied_token, expected)
    )


def _require_admin(supplied_token: str | None) -> None:
    if not _admin_authorized(supplied_token):
        raise HTTPException(
            status_code=403,
            detail="This provider-spend operation requires an admin token.",
        )


def _contract():
    return demo_contract(_current_version, _current_remedy)


def _notice() -> str:
    if _current_remedy.lower().startswith("full refund"):
        return NOTICE.replace(
            "Consumers will\nreceive a free replacement.",
            "Consumers will\nreceive a full refund.",
        )
    return NOTICE


def _as_references(objects) -> list[StorageObjectReference]:
    return [StorageObjectReference(**item.as_dict()) for item in objects]


def _persist_intake(
    draft: IntakeDraft,
    source_text: str,
) -> list[StorageObjectReference]:
    storage = get_b2_storage()
    if not storage:
        return []
    prefix = f"recallcast/intake/{draft.draft_id}"
    metadata = {
        "draft-id": draft.draft_id,
        "source-sha256": draft.source_sha256,
        "intake-status": draft.status,
    }
    objects = [
        storage.put_text(
            f"{prefix}/source/{draft.source_name}",
            source_text,
            metadata=metadata,
            overwrite=False,
        ),
        storage.put_json(
            f"{prefix}/extraction-draft.json",
            draft.model_dump(mode="json", exclude={"storage_objects"}),
            metadata=metadata,
            overwrite=False,
        ),
    ]
    return _as_references(objects)


def _persist_real_case() -> list[StorageObjectReference]:
    storage = get_b2_storage()
    if not storage:
        return []
    contract = real_case_contract()
    prefix = source_prefix(contract.recall_id, contract.version)
    metadata = {
        "recall-id": contract.recall_id,
        "source-version": str(contract.version),
        "source-authority": "cpsc",
        "cpsc-recall-number": CPSC_RECALL_NUMBER,
    }
    objects = [
        storage.put_text(
            f"{prefix}/official-source-excerpt.txt",
            REAL_CASE_NOTICE,
            metadata=metadata,
            overwrite=False,
        ),
        storage.put_json(
            f"{prefix}/fact-contract.json",
            contract.model_dump(mode="json"),
            metadata={
                **metadata,
                "contract-sha256": contract.contract_sha256,
                "human-confirmed": "false",
            },
            overwrite=False,
        ),
        storage.put_json(
            f"{prefix}/source-attribution.json",
            {
                "authority": "U.S. Consumer Product Safety Commission",
                "recall_number": CPSC_RECALL_NUMBER,
                "source_url": CPSC_SOURCE_URL,
                "retrieved_on": "2026-08-01",
                "affiliation": "RecallCast is not affiliated with CPSC or Electrolux Group.",
            },
            metadata=metadata,
            overwrite=False,
        ),
    ]
    return _as_references(objects)


def _restore_real_case_state() -> EvidencePackage | None:
    """Restore acknowledgment and package review state from durable B2 heads."""
    global _real_case_confirmed, _real_case_reviewer
    storage = get_b2_storage()
    if not storage:
        return None
    contract = real_case_contract(human_confirmed=True)
    prefix = source_prefix(contract.recall_id, contract.version)
    try:
        if not _real_case_confirmed:
            contract_key = f"{prefix}/operator-confirmed-contract.json"
            confirmation_key = f"{prefix}/operator-confirmation.json"
            if storage.exists(contract_key) and storage.exists(confirmation_key):
                stored_contract = storage.get_json(contract_key)
                confirmation = storage.get_json(confirmation_key)
                if stored_contract.get("contract_sha256") == contract.contract_sha256:
                    _real_case_confirmed = True
                    _real_case_reviewer = str(confirmation.get("reviewer") or "").strip() or None
        if _real_case_confirmed:
            return load_evidence_package(storage, contract, "en-US")
    except Exception:
        # The public case can still render from its compiled source if B2 is
        # temporarily unavailable; generation/review endpoints remain strict.
        return None
    return None


def _persist_source_contract() -> list[StorageObjectReference]:
    storage = get_b2_storage()
    if not storage:
        return []
    contract = _contract()
    prefix = source_prefix(contract.recall_id, contract.version)
    metadata = {
        "recall-id": contract.recall_id,
        "source-version": str(contract.version),
    }
    objects = [
        storage.put_text(
            f"{prefix}/notice.txt",
            _notice(),
            metadata=metadata,
            overwrite=False,
        ),
        storage.put_json(
            f"{prefix}/fact-contract.json",
            contract.model_dump(mode="json"),
            metadata={
                **metadata,
                "contract-sha256": contract.contract_sha256,
            },
            overwrite=False,
        ),
    ]
    return _as_references(objects)


def _persist_run(run: DemoRun) -> None:
    storage = get_b2_storage()
    if not storage:
        return
    contract = _contract()
    _persist_source_contract()
    if run.status == AssetStatus.QUARANTINED:
        prefix = quarantine_prefix(contract.recall_id, run.run_id)
    else:
        prefix = asset_prefix(
            contract.recall_id,
            run.locale,
            run.channel,
            run.asset_id,
        )
    metadata = {
        "recall-id": contract.recall_id,
        "run-id": run.run_id,
        "asset-id": run.asset_id,
        "source-version": str(run.source_version),
        "contract-sha256": contract.contract_sha256,
    }
    manifest = {
        "schema": "recallcast-run-manifest-v1",
        "run_id": run.run_id,
        "parent_run_id": run.parent_run_id,
        "asset_id": run.asset_id,
        "recall_id": contract.recall_id,
        "source_version": run.source_version,
        "contract_sha256": contract.contract_sha256,
        "asset_sha256": run.asset_sha256,
        "provider": run.provider,
        "model": run.model,
        "manifest_verified": run.manifest_verified,
        "created_at": run.created_at.isoformat(),
    }
    objects = [
        storage.put_text(
            f"{prefix}/transcript.txt",
            run.transcript,
            metadata=metadata,
        ),
        storage.put_json(
            f"{prefix}/validation.json",
            run.report.model_dump(mode="json"),
            metadata=metadata,
        ),
        storage.put_json(
            f"{prefix}/run.json",
            run.model_dump(mode="json", exclude={"storage_objects"}),
            metadata=metadata,
        ),
        storage.put_json(
            f"{prefix}/recallcast-manifest.json",
            manifest,
            metadata=metadata,
        ),
    ]
    run.storage_objects = _as_references(objects)


def _events(passed: bool, attempt: int = 1, fallback: bool = False) -> list[PipelineEvent]:
    common = [
        PipelineEvent(stage="plan", label="Fact contract locked", status="completed", provider="RecallCast", model="contract-v1", latency_ms=84, attempt=attempt),
        PipelineEvent(stage="generate", label="Safety bulletin composed", status="fallback" if fallback else "completed", provider="Deterministic fallback" if fallback else "RecallCast demo renderer", model="bulletin-v1" if fallback else "fixture-v1", latency_ms=710 if fallback else 180, attempt=attempt),
        PipelineEvent(stage="narrate", label="Narration fixture loaded", status="completed", provider="RecallCast", model="precomputed-v1", latency_ms=32, attempt=attempt),
        PipelineEvent(stage="extract", label="Fixture transcript loaded", status="completed", provider="RecallCast", model="golden-transcript-v1", latency_ms=18, attempt=attempt),
        PipelineEvent(stage="validate", label="FactLock checks complete", status="completed" if passed else "blocked", provider="RecallCast", model="factlock-deterministic-v2", latency_ms=43, attempt=attempt),
    ]
    common.append(
        PipelineEvent(
            stage="store",
            label=(
                "Asset and manifest persisted"
                if passed
                else "Quarantine evidence persisted"
            ),
            status="completed",
            provider="Backblaze B2",
            model="hierarchical-sink",
            latency_ms=310,
            attempt=attempt,
        )
    )
    return common


def _create_run(
    scenario: str,
    locale: str,
    channel: str,
    parent_run_id: str | None = None,
    force_approved: bool = False,
) -> DemoRun:
    if scenario not in SCENARIOS:
        raise HTTPException(status_code=404, detail="Unknown demo scenario")
    approved_transcript = APPROVED_ES if locale == "es-US" else APPROVED_EN
    if _current_remedy.lower().startswith("full refund"):
        approved_transcript = approved_transcript.replace(
            "A free replacement is available.",
            "A full refund is available.",
        ).replace(
            "Hay un reemplazo gratuito disponible.",
            "Hay un reembolso completo disponible.",
        )
    transcript = approved_transcript if scenario == "approved" else SCENARIOS[scenario]["transcript"]
    if force_approved:
        transcript = approved_transcript
    run_id = f"run_{uuid4().hex[:10]}"
    asset_id = f"asset_{uuid4().hex[:10]}"
    request = ValidationRequest(
        contract=_contract(),
        locale=locale,
        channel=channel,
        transcript=transcript,
        ocr_text=transcript if channel in {"video", "social_card"} else None,
        manifest_verified=True,
    )
    report = validate(request, asset_id=asset_id)
    passed = report.decision == "pass"
    attempt = 2 if parent_run_id else 1
    run = DemoRun(
        run_id=run_id,
        parent_run_id=parent_run_id,
        asset_id=asset_id,
        scenario="corrected_retry" if force_approved else scenario,
        locale=locale,
        channel=channel,
        status=AssetStatus.NEEDS_REVIEW if passed else AssetStatus.QUARANTINED,
        transcript=transcript,
        report=report,
        events=_events(passed, attempt, fallback=bool(parent_run_id)),
        provider="Deterministic fallback" if parent_run_id else "RecallCast demo renderer",
        model="bulletin-v1" if parent_run_id else "fixture-v1",
        asset_sha256=content_hash(transcript),
        manifest_verified=True,
        source_version=_current_version,
    )
    try:
        _persist_run(run)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Durable B2 persistence failed: {type(error).__name__}",
        ) from error
    with _lock:
        _runs[run_id] = run
    return run


@app.get("/health")
def health():
    return {
        "status": "ok",
        "demo_mode": True,
        "storage_mode": storage_mode(),
        "live_generation_available": live_generation_available(),
    }


@app.get("/api/storage/health")
def storage_health():
    storage = get_b2_storage()
    if not storage:
        return {"status": "memory", "connected": False}
    try:
        return {**storage.health(), "connected": True}
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"B2 health check failed: {type(error).__name__}",
        ) from error


@app.post("/api/genblaze/sdk-storage-smoke")
def genblaze_sdk_storage_smoke():
    if storage_mode() != "b2":
        raise HTTPException(status_code=409, detail="B2 storage mode is not enabled")
    try:
        return run_sdk_storage_smoke()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Genblaze SDK storage smoke failed: {type(error).__name__}",
        ) from error


@app.post("/api/genblaze/live-background")
def genblaze_live_background(
    x_recallcast_admin_token: Annotated[str | None, Header()] = None,
):
    _require_admin(x_recallcast_admin_token)
    if not live_generation_available():
        raise HTTPException(
            status_code=409,
            detail="Live generation requires OPENAI_API_KEY and configured B2 storage.",
        )
    try:
        return run_live_background_generation()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Live Genblaze generation failed: {type(error).__name__}",
        ) from error


@app.post("/api/packages/generate", response_model=EvidencePackage)
def generate_package(
    request: PackageGenerateRequest,
    x_recallcast_admin_token: Annotated[str | None, Header()] = None,
):
    storage = get_b2_storage()
    if not storage:
        raise HTTPException(status_code=409, detail="B2 storage mode is not enabled")
    if not live_generation_available():
        raise HTTPException(
            status_code=409,
            detail="Package generation requires OPENAI_API_KEY and configured B2 storage.",
        )
    if request.force_regenerate:
        _require_admin(x_recallcast_admin_token)
    script = APPROVED_ES if request.locale == "es-US" else APPROVED_EN
    if _current_remedy.lower().startswith("full refund"):
        script = script.replace(
            "A free replacement is available.",
            "A full refund is available.",
        ).replace(
            "Hay un reemplazo gratuito disponible.",
            "Hay un reembolso completo disponible.",
        )
    try:
        # Prevent concurrent cache misses from multiplying provider spend in
        # the single-worker hackathon deployment. B2 remains the durable cache.
        with _package_lock:
            return generate_evidence_package(
                storage,
                _contract(),
                script,
                request.locale,
                force_regenerate=request.force_regenerate,
            )
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Evidence package generation failed: {type(error).__name__}",
        ) from error


@app.post("/api/packages/revalidate", response_model=EvidencePackage)
def revalidate_package(request: PackageGenerateRequest):
    storage = get_b2_storage()
    if not storage:
        raise HTTPException(status_code=409, detail="B2 storage mode is not enabled")
    try:
        return revalidate_evidence_package(storage, _contract(), request.locale)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Evidence package revalidation failed: {type(error).__name__}",
        ) from error


@app.post("/api/storage/bootstrap")
def bootstrap_storage():
    if not get_b2_storage():
        raise HTTPException(status_code=409, detail="B2 storage mode is not enabled")
    try:
        objects = _persist_source_contract()
        return {
            "status": "stored",
            "recall_id": _contract().recall_id,
            "source_version": _current_version,
            "objects": objects,
        }
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"B2 bootstrap failed: {type(error).__name__}",
        ) from error


@app.get("/api/storage/objects")
def list_storage_objects(prefix: str = "recallcast/", max_keys: int = 100):
    storage = get_b2_storage()
    if not storage:
        raise HTTPException(status_code=409, detail="B2 storage mode is not enabled")
    if not prefix.startswith("recallcast/"):
        raise HTTPException(
            status_code=400,
            detail="Prefix must remain inside recallcast/",
        )
    return {
        "prefix": prefix,
        "objects": storage.list_prefix(prefix, min(max(max_keys, 1), 500)),
    }


@app.get("/api/storage/presign")
def presign_storage_object(key: str, expires_in: int = 900):
    storage = get_b2_storage()
    if not storage:
        raise HTTPException(status_code=409, detail="B2 storage mode is not enabled")
    if not key.startswith("recallcast/") or ".." in key:
        raise HTTPException(
            status_code=400,
            detail="Object key must remain inside recallcast/",
        )
    return {
        "key": key,
        "url": storage.presign_get(key, expires_in),
        "expires_in": min(max(expires_in, 60), 3600),
    }


@app.post("/api/intake/extract", response_model=IntakeDraft)
def extract_intake(request: IntakeRequest):
    """Create a review-only fact-contract draft from pasted or uploaded text."""

    try:
        source_name, source_text = validate_source(
            request.source_name,
            request.source_text,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=409,
            detail="Recall extraction requires OPENAI_API_KEY.",
        )
    try:
        extraction = extract_recall(source_text)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Structured recall extraction failed: {type(error).__name__}",
        ) from error
    warnings = extraction_warnings(source_text, extraction)
    source_digest = sha256(source_text.encode("utf-8")).hexdigest()
    draft = IntakeDraft(
        draft_id=f"draft_{uuid4().hex[:12]}",
        status="incomplete" if warnings else "needs_review",
        source_name=source_name,
        source_sha256=source_digest,
        extraction_model=os.getenv("OPENAI_EXTRACTION_MODEL", "gpt-5.6-sol"),
        extraction=extraction,
        validation_warnings=warnings,
    )
    try:
        draft.storage_objects = _persist_intake(draft, source_text)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Intake persistence failed: {type(error).__name__}",
        ) from error
    with _lock:
        _intakes[draft.draft_id] = (draft, source_text)
    return draft


@app.post("/api/intake/confirm", response_model=ConfirmedIntake)
def confirm_intake(request: ConfirmIntakeRequest):
    """Confirm an edited draft; this never auto-generates or releases media."""

    record = _intakes.get(request.draft_id)
    if not record:
        raise HTTPException(status_code=404, detail="Intake draft not found")
    draft, source_text = record
    try:
        contract = contract_from_extraction(
            source_text,
            request.extraction,
            human_confirmed=True,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "The draft still has blocking source-grounding gaps.",
                "warnings": extraction_warnings(source_text, request.extraction),
            },
        ) from error
    policy_pack = build_policy_draft(draft.draft_id, contract)
    objects: list[StorageObjectReference] = []
    storage = get_b2_storage()
    if storage:
        try:
            metadata = {
                "draft-id": draft.draft_id,
                "recall-id": contract.recall_id,
                "contract-sha256": contract.contract_sha256,
                "intake-status": "confirmed",
            }
            stored = [
                storage.put_json(
                    f"recallcast/intake/{draft.draft_id}/confirmed-contract.json",
                    contract.model_dump(mode="json"),
                    metadata=metadata,
                    overwrite=False,
                ),
                storage.put_json(
                    f"recallcast/intake/{draft.draft_id}/policy-draft.json",
                    policy_pack.model_dump(mode="json"),
                    metadata={**metadata, "policy-status": "draft"},
                    overwrite=False,
                ),
            ]
            objects = _as_references(stored)
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail=f"Confirmed contract persistence failed: {type(error).__name__}",
            ) from error
    confirmed_draft = draft.model_copy(
        update={
            "status": "confirmed",
            "extraction": request.extraction,
            "validation_warnings": [],
            "storage_objects": [*draft.storage_objects, *objects],
        }
    )
    with _lock:
        _intakes[draft.draft_id] = (confirmed_draft, source_text)
        _confirmed_intakes[draft.draft_id] = contract
        _policy_packs[draft.draft_id] = policy_pack
    return ConfirmedIntake(
        draft_id=draft.draft_id,
        contract=contract,
        policy_pack=policy_pack,
        storage_objects=objects,
    )


def _custom_intake(draft_id: str) -> tuple[FactContract, PolicyPack]:
    contract = _confirmed_intakes.get(draft_id)
    policy = _policy_packs.get(draft_id)
    if not contract or not policy:
        storage = get_b2_storage()
        prefix = f"recallcast/intake/{draft_id}"
        try:
            if storage and storage.exists(f"{prefix}/confirmed-contract.json"):
                contract = FactContract.model_validate(
                    storage.get_json(f"{prefix}/confirmed-contract.json")
                )
                policy_key = (
                    f"{prefix}/active-policy.json"
                    if storage.exists(f"{prefix}/active-policy.json")
                    else f"{prefix}/policy-draft.json"
                )
                if storage.exists(policy_key):
                    policy = PolicyPack.model_validate(storage.get_json(policy_key))
                    with _lock:
                        _confirmed_intakes[draft_id] = contract
                        _policy_packs[draft_id] = policy
        except Exception:
            contract = None
            policy = None
    if not contract or not policy:
        raise HTTPException(status_code=404, detail="Confirmed intake not found")
    return contract, policy


@app.get("/api/intake/{draft_id}/policy", response_model=PolicyPack)
def get_intake_policy(draft_id: str):
    return _custom_intake(draft_id)[1]


@app.post("/api/intake/{draft_id}/policy/activate", response_model=PolicyPack)
def activate_intake_policy(
    draft_id: str,
    request: ActivatePolicyPackRequest,
):
    if not request.attestation:
        raise HTTPException(
            status_code=422,
            detail="Policy activation requires reviewer accountability attestation.",
        )
    contract, draft = _custom_intake(draft_id)
    if draft.status == "active":
        raise HTTPException(status_code=409, detail="The policy is already active.")
    try:
        active = activate_policy(
            draft,
            contract,
            request.concept_groups,
            request.reviewer,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    storage = get_b2_storage()
    if storage:
        try:
            storage.put_json(
                f"recallcast/intake/{draft_id}/active-policy.json",
                active.model_dump(mode="json"),
                metadata={
                    "draft-id": draft_id,
                    "recall-id": contract.recall_id,
                    "contract-sha256": contract.contract_sha256,
                    "policy-sha256": active.policy_sha256,
                    "policy-status": "active",
                },
                overwrite=False,
            )
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail=f"Active policy persistence failed: {type(error).__name__}",
            ) from error
    with _lock:
        _policy_packs[draft_id] = active
    return active


@app.post(
    "/api/intake/{draft_id}/packages/generate",
    response_model=EvidencePackage,
)
def generate_intake_package(
    draft_id: str,
    request: PackageGenerateRequest = PackageGenerateRequest(),
    x_recallcast_admin_token: Annotated[str | None, Header()] = None,
):
    contract, policy = _custom_intake(draft_id)
    if policy.status != "active":
        raise HTTPException(status_code=409, detail="Activate the policy before generation.")
    storage = get_b2_storage()
    if not storage:
        raise HTTPException(status_code=409, detail="B2 storage mode is not enabled")
    if not live_generation_available():
        raise HTTPException(
            status_code=409,
            detail="Package generation requires OPENAI_API_KEY and configured B2 storage.",
        )
    if request.force_regenerate:
        _require_admin(x_recallcast_admin_token)
    if request.locale not in contract.supported_locales:
        raise HTTPException(status_code=422, detail="Locale is not contract-approved.")
    try:
        with _package_lock:
            return generate_evidence_package(
                storage,
                contract,
                contract_narration_script(contract, request.locale),
                request.locale,
                force_regenerate=request.force_regenerate,
                policy_pack=policy,
            )
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Custom evidence package generation failed: {type(error).__name__}",
        ) from error


@app.post(
    "/api/intake/{draft_id}/packages/{package_id}/review",
    response_model=EvidencePackage,
)
def review_intake_package(
    draft_id: str,
    package_id: str,
    request: PackageReviewRequest,
):
    contract, policy = _custom_intake(draft_id)
    if request.decision == "approved" and not request.attestation:
        raise HTTPException(
            status_code=422,
            detail="Approval requires the accountability attestation.",
        )
    storage = get_b2_storage()
    if not storage:
        raise HTTPException(status_code=409, detail="B2 storage mode is not enabled")
    try:
        with _package_lock:
            package, _ = review_evidence_package(
                storage,
                contract,
                "en-US",
                expected_package_id=package_id,
                decision=request.decision,
                reviewer=request.reviewer,
                rationale=request.rationale,
                policy_pack=policy,
            )
            return package
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Custom review persistence failed: {type(error).__name__}",
        ) from error


@app.get("/api/cases/cpsc-26-333")
def get_real_case():
    package = _restore_real_case_state()
    contract = real_case_contract(human_confirmed=_real_case_confirmed)
    package_status = package.status if package else None
    release_status = "operator_review_required"
    if _real_case_confirmed:
        release_status = {
            AssetStatus.NEEDS_REVIEW: "human_review_required",
            AssetStatus.APPROVED: "approved_for_demo_release",
            AssetStatus.REJECTED: "rejected_by_reviewer",
            AssetStatus.QUARANTINED: "factlock_quarantined",
        }.get(package_status, "media_draft_enabled")
    return {
        "case_type": "public_source",
        "source_authority": "U.S. Consumer Product Safety Commission",
        "source_url": CPSC_SOURCE_URL,
        "recall_number": CPSC_RECALL_NUMBER,
        "contract": contract,
        "stats": {
            "units_us": 174_800,
            "reported_incidents": 62,
            "reported_injuries": 30,
            "affected_models": len(contract.affected_models),
        },
        "release_status": release_status,
        "reviewer": _real_case_reviewer,
        "package": (
            {
                "package_id": package.package_id,
                "status": package.status,
                "review": package.review,
            }
            if package
            else None
        ),
        "disclaimer": (
            "Public CPSC source; RecallCast is not affiliated with CPSC or "
            "Electrolux Group. Verify the live regulator notice before action."
        ),
    }


@app.post("/api/cases/cpsc-26-333/bootstrap")
def bootstrap_real_case():
    if not get_b2_storage():
        raise HTTPException(status_code=409, detail="B2 storage mode is not enabled")
    try:
        objects = _persist_real_case()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Public case persistence failed: {type(error).__name__}",
        ) from error
    return {
        "status": "stored",
        "recall_id": real_case_contract().recall_id,
        "objects": objects,
    }


@app.post("/api/cases/cpsc-26-333/confirm")
def confirm_real_case(request: RealCaseConfirmationRequest):
    global _real_case_confirmed, _real_case_reviewer
    if not request.acknowledgment:
        raise HTTPException(
            status_code=422,
            detail="The public-source verification acknowledgment is required.",
        )
    contract = real_case_contract(human_confirmed=True)
    objects: list[StorageObjectReference] = []
    storage = get_b2_storage()
    if storage:
        prefix = source_prefix(contract.recall_id, contract.version)
        decision = {
            "decision": "confirmed_for_unaffiliated_demo_draft",
            "reviewer": request.reviewer.strip(),
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "source_url": CPSC_SOURCE_URL,
            "disclaimer": (
                "This enables an unaffiliated RecallCast media draft only; it is "
                "not CPSC or Electrolux approval."
            ),
        }
        try:
            stored = [
                storage.put_json(
                    f"{prefix}/operator-confirmed-contract.json",
                    contract.model_dump(mode="json"),
                    metadata={
                        "recall-id": contract.recall_id,
                        "contract-sha256": contract.contract_sha256,
                        "human-confirmed": "true",
                    },
                ),
                storage.put_json(
                    f"{prefix}/operator-confirmation.json",
                    decision,
                    metadata={
                        "recall-id": contract.recall_id,
                        "decision": "confirmed-for-demo-draft",
                    },
                ),
            ]
            objects = _as_references(stored)
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail=f"Operator confirmation persistence failed: {type(error).__name__}",
            ) from error
    _real_case_confirmed = True
    _real_case_reviewer = request.reviewer.strip()
    return {
        "status": "confirmed_for_demo_draft",
        "contract": contract,
        "reviewer": _real_case_reviewer,
        "objects": objects,
    }


@app.post(
    "/api/cases/cpsc-26-333/packages/generate",
    response_model=EvidencePackage,
)
def generate_real_case_package():
    if not _real_case_confirmed:
        _restore_real_case_state()
    if not _real_case_confirmed:
        raise HTTPException(
            status_code=409,
            detail="Operator confirmation is required before generating a real-case draft.",
        )
    storage = get_b2_storage()
    if not storage:
        raise HTTPException(status_code=409, detail="B2 storage mode is not enabled")
    if not live_generation_available():
        raise HTTPException(
            status_code=409,
            detail="Package generation requires OPENAI_API_KEY and configured B2 storage.",
        )
    try:
        with _package_lock:
            return generate_evidence_package(
                storage,
                real_case_contract(human_confirmed=True),
                real_case_narration_script(),
                "en-US",
            )
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Real-case package generation failed: {type(error).__name__}",
        ) from error


@app.post(
    "/api/cases/cpsc-26-333/packages/{package_id}/review",
    response_model=EvidencePackage,
)
def review_real_case_package(package_id: str, request: PackageReviewRequest):
    if not _real_case_confirmed:
        _restore_real_case_state()
    if not _real_case_confirmed:
        raise HTTPException(
            status_code=409,
            detail="Operator source acknowledgment is required before package review.",
        )
    if request.decision == "approved" and not request.attestation:
        raise HTTPException(
            status_code=422,
            detail="Approval requires the reviewer accountability attestation.",
        )
    storage = get_b2_storage()
    if not storage:
        raise HTTPException(status_code=409, detail="B2 storage mode is not enabled")
    try:
        with _package_lock:
            package, _ = review_evidence_package(
                storage,
                real_case_contract(human_confirmed=True),
                "en-US",
                expected_package_id=package_id,
                decision=request.decision,
                reviewer=request.reviewer,
                rationale=request.rationale,
            )
            return package
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Review decision persistence failed: {type(error).__name__}",
        ) from error


@app.get("/api/demo")
def get_demo():
    contract = _contract()
    return {
        "notice": NOTICE,
        "contract": contract,
        "scenarios": [
            {"id": key, **{k: v for k, v in value.items() if k != "transcript"}}
            for key, value in SCENARIOS.items()
        ],
        "stats": {
            "blocking_facts": 8,
            "languages": 2,
            "channels": 3,
        },
    }


@app.post("/api/validate", response_model=ValidationReport)
def validate_asset(request: ValidationRequest):
    return validate(request, asset_id=f"asset_{uuid4().hex[:10]}")


@app.post("/api/demo/run", response_model=DemoRun)
def run_demo(request: DemoRunRequest):
    return _create_run(request.scenario, request.locale, request.channel)


@app.get("/api/runs/{run_id}", response_model=DemoRun)
def get_run(run_id: str):
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="Run not found")
    return _runs[run_id]


@app.post("/api/demo/retry/{run_id}", response_model=DemoRun)
def retry_demo(run_id: str):
    parent = _runs.get(run_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent run not found")
    if parent.status != AssetStatus.QUARANTINED:
        raise HTTPException(status_code=409, detail="Only quarantined runs can be retried")
    return _create_run(
        "approved",
        parent.locale,
        parent.channel,
        parent_run_id=run_id,
        force_approved=True,
    )


@app.post("/api/assets/{asset_id}/approve", response_model=ApproveResponse)
def approve_asset(asset_id: str):
    run = next((item for item in _runs.values() if item.asset_id == asset_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Asset not found")
    if run.status != AssetStatus.NEEDS_REVIEW:
        raise HTTPException(status_code=409, detail="Asset is not eligible for approval")
    run.status = AssetStatus.APPROVED
    response = ApproveResponse(
        asset_id=asset_id,
        status=run.status,
        reviewer="Demo reviewer",
        approved_at=datetime.now(timezone.utc),
    )
    storage = get_b2_storage()
    if storage:
        prefix = asset_prefix(
            _contract().recall_id,
            run.locale,
            run.channel,
            run.asset_id,
        )
        try:
            stored = storage.put_json(
                f"{prefix}/review-decision.json",
                response.model_dump(mode="json"),
                metadata={
                    "recall-id": _contract().recall_id,
                    "asset-id": run.asset_id,
                    "decision": "approved",
                },
            )
            run.storage_objects.append(
                StorageObjectReference(**stored.as_dict())
            )
        except Exception as error:
            run.status = AssetStatus.NEEDS_REVIEW
            raise HTTPException(
                status_code=503,
                detail=f"Approval persistence failed: {type(error).__name__}",
            ) from error
    return response


@app.post("/api/demo/source-update")
def update_source(request: SourceUpdateRequest):
    global _current_version, _current_remedy
    stale_assets = []
    with _lock:
        if _current_remedy == request.remedy:
            return {
                "source_version": _current_version,
                "contract": _contract(),
                "changed_fact_ids": [],
                "stale_assets": [],
            }
        _current_version += 1
        _current_remedy = request.remedy
        for run in _runs.values():
            if run.source_version < _current_version and run.status in {
                AssetStatus.APPROVED,
                AssetStatus.NEEDS_REVIEW,
                AssetStatus.RELEASED,
            }:
                run.status = AssetStatus.STALE
                stale_assets.append(run.asset_id)
    if get_b2_storage():
        try:
            _persist_source_contract()
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail=f"Source-version persistence failed: {type(error).__name__}",
            ) from error
    return {
        "source_version": _current_version,
        "contract": _contract(),
        "changed_fact_ids": ["remedy.approved"],
        "stale_assets": stale_assets,
    }
