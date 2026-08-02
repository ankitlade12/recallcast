from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class Severity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFORMATIONAL = "informational"


class MatchPolicy(StrEnum):
    EXACT = "exact"
    NORMALIZED_EXACT = "normalized_exact"
    RANGE_COMPLETE = "range_complete"
    REQUIRED_CONCEPT = "required_concept"
    SEMANTIC_AND_NEGATION = "semantic_and_negation"
    VISUAL_LOCK = "visual_lock"


class AssetStatus(StrEnum):
    DRAFT = "draft"
    GENERATING = "generating"
    VALIDATING = "validating"
    QUARANTINED = "quarantined"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    RELEASED = "released"
    STALE = "stale"
    FAILED = "failed"


class Contact(BaseModel):
    phone: str
    url: str


class LotRange(BaseModel):
    start: str
    end: str


class FactContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    recall_id: str
    version: int = 1
    source_sha256: str
    issuer: str
    product_name: str
    affected_models: tuple[str, ...]
    affected_lot_ranges: tuple[LotRange, ...]
    hazard: str
    required_action: str
    remedy: str
    contact: Contact
    effective_date: date
    supported_locales: tuple[str, ...] = ("en-US", "es-US")
    human_confirmed: bool = True

    @computed_field
    @property
    def contract_sha256(self) -> str:
        payload = self.model_dump_json(
            exclude={"contract_sha256"},
            by_alias=True,
        )
        return sha256(payload.encode("utf-8")).hexdigest()


class RecallExtraction(BaseModel):
    """Schema-constrained, still-untrusted facts extracted from a source notice."""

    issuer: str
    product_name: str
    affected_models: list[str]
    affected_lot_ranges: list[LotRange]
    hazard: str
    required_action: str
    remedy: str
    contact_phone: str
    contact_url: str
    effective_date: str
    supported_locales: list[str]
    extraction_warnings: list[str]


class AtomicFact(BaseModel):
    fact_id: str
    label: str
    canonical_value: str
    severity: Severity = Severity.BLOCKING
    match_policy: MatchPolicy
    required_channels: tuple[str, ...] = ("video", "audio", "social_card")
    required_locales: tuple[str, ...] = ("en-US", "es-US")


class FindingStatus(StrEnum):
    PASS = "pass"
    MISSING = "missing"
    MUTATED = "mutated"
    CONTRADICTED = "contradicted"
    WEAKENED = "weakened"
    UNAVAILABLE = "unavailable"


class Finding(BaseModel):
    fact_id: str
    label: str
    status: FindingStatus
    severity: Severity
    canonical_value: str
    evidence: str | None = None
    evidence_source: str | None = None
    reason: str

    @computed_field
    @property
    def blocking_failure(self) -> bool:
        return (
            self.severity == Severity.BLOCKING
            and self.status != FindingStatus.PASS
        )


class ValidationRequest(BaseModel):
    contract: FactContract
    locale: Literal["en-US", "es-US"] = "en-US"
    channel: Literal["video", "audio", "social_card"] = "video"
    transcript: str | None = None
    ocr_text: str | None = None
    captions: str | None = None
    manifest_verified: bool = True
    asset_contract_sha256: str | None = None
    asset_policy_sha256: str | None = None
    strict_evidence_policy: bool = False
    policy_pack: PolicyPack | None = None


class ValidationReport(BaseModel):
    asset_id: str
    decision: Literal["pass", "quarantine"]
    contract_sha256: str
    validator_version: str = "factlock-deterministic-v1"
    findings: list[Finding]
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @computed_field
    @property
    def passed_count(self) -> int:
        return sum(f.status == FindingStatus.PASS for f in self.findings)

    @computed_field
    @property
    def blocking_failure_count(self) -> int:
        return sum(f.blocking_failure for f in self.findings)


class PipelineEvent(BaseModel):
    stage: str
    label: str
    status: Literal["completed", "failed", "blocked", "fallback"]
    provider: str
    model: str
    latency_ms: int
    attempt: int = 1


class StorageObjectReference(BaseModel):
    key: str
    uri: str
    sha256: str
    content_type: str
    size: int
    version_id: str | None = None


class IntakeRequest(BaseModel):
    source_name: str = Field(min_length=1, max_length=180)
    source_text: str = Field(min_length=1, max_length=220_000)


class IntakeDraft(BaseModel):
    draft_id: str
    status: Literal["needs_review", "incomplete", "confirmed"]
    source_name: str
    source_sha256: str
    extraction_model: str
    extraction: RecallExtraction
    validation_warnings: list[str]
    storage_objects: list[StorageObjectReference] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ConfirmIntakeRequest(BaseModel):
    draft_id: str
    extraction: RecallExtraction


class PolicyConceptGroup(BaseModel):
    field: Literal["hazard", "required_action", "remedy"]
    canonical_value: str
    required_concepts: tuple[str, ...] = Field(min_length=2, max_length=12)


class PolicyPack(BaseModel):
    """Human-authored deterministic rules bound to one confirmed contract."""

    schema_version: Literal["recallcast-policy-pack-v1"] = (
        "recallcast-policy-pack-v1"
    )
    policy_id: str
    template: Literal["stop-use-product-recall-v1"] = (
        "stop-use-product-recall-v1"
    )
    status: Literal["draft", "active"] = "draft"
    draft_id: str
    recall_id: str
    contract_sha256: str
    exact_identifiers: tuple[str, ...]
    range_endpoints: tuple[str, ...]
    concept_groups: tuple[PolicyConceptGroup, ...]
    require_phone: bool = True
    require_url_on_visual: bool = True
    require_effective_date: bool = True
    reviewer: str | None = None
    activated_at: datetime | None = None

    @computed_field
    @property
    def policy_sha256(self) -> str:
        payload = self.model_dump_json(exclude={"policy_sha256"})
        return sha256(payload.encode("utf-8")).hexdigest()


class ActivatePolicyPackRequest(BaseModel):
    concept_groups: tuple[PolicyConceptGroup, ...]
    reviewer: str = Field(min_length=2, max_length=100)
    attestation: bool = False


class ConfirmedIntake(BaseModel):
    draft_id: str
    status: Literal["confirmed"] = "confirmed"
    contract: FactContract
    policy_pack: PolicyPack
    storage_objects: list[StorageObjectReference] = Field(default_factory=list)


class DemoRun(BaseModel):
    run_id: str
    parent_run_id: str | None = None
    asset_id: str
    scenario: str
    locale: str
    channel: str
    status: AssetStatus
    transcript: str
    report: ValidationReport
    events: list[PipelineEvent]
    provider: str
    model: str
    asset_sha256: str
    manifest_verified: bool
    source_version: int
    storage_objects: list[StorageObjectReference] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ApproveResponse(BaseModel):
    asset_id: str
    status: AssetStatus
    reviewer: str
    approved_at: datetime


class PackageGenerateRequest(BaseModel):
    locale: Literal["en-US", "es-US"] = "en-US"
    force_regenerate: bool = False


class PackageReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reviewer: str = Field(min_length=2, max_length=100)
    rationale: str = Field(min_length=8, max_length=1000)
    attestation: bool = False


class PackageReviewRecord(BaseModel):
    schema_version: Literal["recallcast-package-review-v1"] = (
        "recallcast-package-review-v1"
    )
    package_id: str
    recall_id: str
    decision: Literal["approved", "rejected"]
    status: AssetStatus
    reviewer: str
    rationale: str
    reviewed_at: datetime
    contract_sha256: str
    validation_report_sha256: str
    artifact_sha256s: list[str]
    attestation: str


class MediaArtifact(BaseModel):
    kind: Literal["background", "consumer_card", "social_card", "narration"]
    key: str
    uri: str
    sha256: str
    content_type: str
    size: int
    provider: str
    model: str
    manifest_hash: str | None = None
    manifest_verified: bool = False
    run_id: str | None = None
    parent_run_id: str | None = None
    attempt: int = 1
    accepted: bool = True
    preview_url: str | None = None


class PackageAttemptEvidence(BaseModel):
    attempt: int
    script: str
    observed_transcript: str
    report: ValidationReport
    accepted: bool
    run_id: str | None = None
    parent_run_id: str | None = None


class EvidencePackage(BaseModel):
    package_id: str
    idempotency_key: str
    recall_id: str
    source_version: int
    contract_sha256: str
    policy_sha256: str | None = None
    locale: Literal["en-US", "es-US"]
    status: AssetStatus
    script: str
    observed_transcript: str
    observed_ocr: str
    report: ValidationReport
    events: list[PipelineEvent]
    artifacts: list[MediaArtifact]
    attempts: list[PackageAttemptEvidence] = Field(default_factory=list)
    review: PackageReviewRecord | None = None
    ai_voice_disclosure: str = (
        "The narration is AI-generated and is not a human voice."
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
