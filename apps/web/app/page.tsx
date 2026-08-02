"use client";

import { useEffect, useMemo, useState } from "react";

type Scenario = "approved" | "identifier_mutation" | "action_weakening";
type RunState = "idle" | "running" | "quarantined" | "review" | "approved" | "stale";
type GenerationState = "idle" | "running" | "generated" | "error";
type NavigationView = "workspace" | "intake" | "packages" | "lineage" | "policy";
type IntakeState = "idle" | "extracting" | "review" | "confirming" | "confirmed" | "error";
type WorkspaceCase = "demo" | "cpsc";

type IntakeExtraction = {
  issuer: string;
  product_name: string;
  affected_models: string[];
  affected_lot_ranges: Array<{ start: string; end: string }>;
  hazard: string;
  required_action: string;
  remedy: string;
  contact_phone: string;
  contact_url: string;
  effective_date: string;
  supported_locales: string[];
  extraction_warnings: string[];
};

type IntakeDraft = {
  draft_id: string;
  status: "needs_review" | "incomplete" | "confirmed";
  source_name: string;
  source_sha256: string;
  extraction_model: string;
  extraction: IntakeExtraction;
  validation_warnings: string[];
  storage_objects: Array<{ key: string }>;
};

type PolicyConceptGroup = {
  field: "hazard" | "required_action" | "remedy";
  canonical_value: string;
  required_concepts: string[];
};

type PolicyPack = {
  policy_id: string;
  template: "stop-use-product-recall-v1";
  status: "draft" | "active";
  draft_id: string;
  contract_sha256: string;
  policy_sha256: string;
  exact_identifiers: string[];
  range_endpoints: string[];
  concept_groups: PolicyConceptGroup[];
  require_phone: boolean;
  require_url_on_visual: boolean;
  require_effective_date: boolean;
  reviewer: string | null;
};

type PackageFinding = {
  fact_id: string;
  label: string;
  status: string;
  canonical_value: string;
  evidence: string | null;
  evidence_source: string | null;
  reason: string;
  blocking_failure: boolean;
};

type PackageArtifact = {
  kind: "background" | "consumer_card" | "social_card" | "narration";
  key: string;
  sha256: string;
  provider: string;
  model: string;
  manifest_verified: boolean;
  run_id: string | null;
  parent_run_id: string | null;
  attempt: number;
  accepted: boolean;
  preview_url: string | null;
};

type PackageAttempt = {
  attempt: number;
  script: string;
  observed_transcript: string;
  report: EvidencePackage["report"];
  accepted: boolean;
  run_id: string | null;
  parent_run_id: string | null;
};

type PackageReview = {
  schema_version: "recallcast-package-review-v1";
  package_id: string;
  recall_id: string;
  decision: "approved" | "rejected";
  status: "approved" | "rejected";
  reviewer: string;
  rationale: string;
  reviewed_at: string;
  contract_sha256: string;
  validation_report_sha256: string;
  artifact_sha256s: string[];
  attestation: string;
};

type EvidencePackage = {
  package_id: string;
  recall_id: string;
  locale: "en-US" | "es-US";
  status: string;
  contract_sha256: string;
  policy_sha256: string | null;
  observed_transcript: string;
  observed_ocr: string;
  ai_voice_disclosure: string;
  report: {
    decision: "pass" | "quarantine";
    validator_version: string;
    passed_count: number;
    blocking_failure_count: number;
    findings: PackageFinding[];
  };
  events: Array<{
    stage: string;
    label: string;
    status: string;
    provider: string;
    model: string;
    latency_ms: number;
    attempt: number;
  }>;
  artifacts: PackageArtifact[];
  attempts?: PackageAttempt[];
  review: PackageReview | null;
};

type Finding = {
  id: string;
  label: string;
  canonical: string;
  evidence: string;
  pass: boolean;
  status?: string;
  reason: string;
};

type DemoRunPayload = {
  run_id: string;
  parent_run_id: string | null;
  asset_id: string;
  status: "quarantined" | "needs_review" | "approved" | "stale";
  asset_sha256: string;
  report: {
    decision: "pass" | "quarantine";
    findings: PackageFinding[];
    blocking_failure_count: number;
  };
  events: EvidencePackage["events"];
  storage_objects: Array<{ key: string }>;
};

type RealCasePayload = {
  case_type: "public_source";
  source_authority: string;
  source_url: string;
  recall_number: string;
  contract: {
    recall_id: string;
    version: number;
    contract_sha256: string;
    issuer: string;
    product_name: string;
    affected_models: string[];
    affected_lot_ranges: Array<{ start: string; end: string }>;
    hazard: string;
    required_action: string;
    remedy: string;
    contact: { phone: string; url: string };
    effective_date: string;
    human_confirmed: boolean;
  };
  stats: {
    units_us: number;
    reported_incidents: number;
    reported_injuries: number;
    affected_models: number;
  };
  release_status: string;
  reviewer: string | null;
  package: {
    package_id: string;
    status: string;
    review: PackageReview | null;
  } | null;
  disclaimer: string;
};

const demoContract = [
  ["Product", "Northstar Glow Mini Heater", "product.identity"],
  ["Models", "NG-100 · NG-110", "product.affected_models"],
  ["Lot range", "A71 → A94", "product.affected_lots"],
  ["Hazard", "Battery can overheat and cause a fire", "hazard.fire"],
  ["Required action", "Stop using and unplug immediately", "required_action.stop_and_unplug"],
  ["Remedy", "Free replacement", "remedy.approved"],
  ["Contact", "1-800-555-0147", "contact.phone"],
  ["Effective", "July 29, 2026", "recall.effective_date"],
] as const;
const supportedPackageLocales = ["en-US", "es-US"] as const;

const fixturePipeline = [
  ["Contract locked", "RecallCast", "contract-v1"],
  ["Bulletin composed", "RecallCast demo", "fixture-v1"],
  ["Narration loaded", "RecallCast", "precomputed-v1"],
  ["Transcript loaded", "RecallCast", "golden-v1"],
  ["FactLock verified", "RecallCast", "deterministic-v2"],
  ["Evidence persisted", "Backblaze B2", "hierarchical-sink"],
] as const;

function Icon({ name }: { name: "shield" | "cube" | "branch" | "pulse" | "check" | "lock" | "play" }) {
  const paths = {
    shield: <path d="M12 3 5 6v5c0 4.7 2.9 8.2 7 10 4.1-1.8 7-5.3 7-10V6l-7-3Zm-3 9 2 2 4-5" />,
    cube: <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 9 8-4.5M12 12 4 7.5M12 12v9" />,
    branch: <path d="M6 3v12a4 4 0 0 0 4 4h8M6 8h7a4 4 0 0 1 4 4v1M3 6l3 3 3-3m5 4 3 3 3-3" />,
    pulse: <path d="M3 12h4l2-5 4 10 2-5h6" />,
    check: <path d="m5 12 4 4L19 6" />,
    lock: <path d="M7 11V8a5 5 0 0 1 10 0v3m-11 0h12v10H6V11Z" />,
    play: <path d="m9 7 8 5-8 5V7Z" />,
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

function parseLotRanges(value: string): Array<{ start: string; end: string }> {
  return value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean).map((item) => {
    const match = item.match(/^(.+?)\s*(?:–|—|->|\bthrough\b|\bto\b)\s*(.+)$/i);
    return match ? { start: match[1].trim(), end: match[2].trim() } : { start: item, end: "" };
  });
}

function observedSerial(text: string): string {
  const compact = text.match(/\bVF\d+\b/gi)?.at(-1)?.toUpperCase();
  if (compact) return compact;
  const digitWords: Record<string, string> = {
    zero: "0", oh: "0", one: "1", two: "2", three: "3", four: "4",
    five: "5", six: "6", seven: "7", eight: "8", nine: "9",
  };
  const ending = text.slice(Math.max(0, text.toLowerCase().indexOf("ends with")));
  const spoken = Array.from(ending.matchAll(/digit\s+(\d|zero|oh|one|two|three|four|five|six|seven|eight|nine)/gi))
    .slice(0, 8)
    .map((match) => digitWords[match[1].toLowerCase()] ?? match[1]);
  return spoken.length === 8 ? `VF${spoken.join("")}` : "Serial not extracted";
}

export default function Home() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const [scenario, setScenario] = useState<Scenario>("action_weakening");
  const [workspaceCase, setWorkspaceCase] = useState<WorkspaceCase>("demo");
  const [realCase, setRealCase] = useState<RealCasePayload | null>(null);
  const [realCaseStored, setRealCaseStored] = useState(false);
  const [realCaseError, setRealCaseError] = useState<string | null>(null);
  const [realAcknowledged, setRealAcknowledged] = useState(false);
  const [realConfirming, setRealConfirming] = useState(false);
  const [realReviewReviewer, setRealReviewReviewer] = useState("AL · Local demo operator");
  const [realReviewRationale, setRealReviewRationale] = useState("");
  const [realReviewAttested, setRealReviewAttested] = useState(false);
  const [realReviewPending, setRealReviewPending] = useState(false);
  const [runState, setRunState] = useState<RunState>("idle");
  const [activeStage, setActiveStage] = useState(-1);
  const [showContract, setShowContract] = useState(false);
  const [activeNavigation, setActiveNavigation] = useState<NavigationView>("workspace");
  const [sourceVersion, setSourceVersion] = useState(1);
  const [contractHash, setContractHash] = useState<string | null>(null);
  const [parentLinked, setParentLinked] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [assetId, setAssetId] = useState<string | null>(null);
  const [demoRun, setDemoRun] = useState<DemoRunPayload | null>(null);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [storageStatus, setStorageStatus] = useState<"checking" | "connected" | "memory" | "offline">("checking");
  const [storageObjectCount, setStorageObjectCount] = useState(0);
  const [generationState, setGenerationState] = useState<GenerationState>("idle");
  const [evidencePackage, setEvidencePackage] = useState<EvidencePackage | null>(null);
  const [mediaKitView, setMediaKitView] = useState<"consumer" | "eligibility">("consumer");
  const [judgeMode, setJudgeMode] = useState(false);
  const [packageLocale, setPackageLocale] = useState<"en-US" | "es-US">("en-US");
  const [showGeneration, setShowGeneration] = useState(false);
  const [showIntake, setShowIntake] = useState(false);
  const [intakeText, setIntakeText] = useState("");
  const [intakeSourceName, setIntakeSourceName] = useState("pasted-recall.md");
  const [intakeState, setIntakeState] = useState<IntakeState>("idle");
  const [intakeDraft, setIntakeDraft] = useState<IntakeDraft | null>(null);
  const [intakeError, setIntakeError] = useState<string | null>(null);
  const [confirmedContractHash, setConfirmedContractHash] = useState<string | null>(null);
  const [intakePolicy, setIntakePolicy] = useState<PolicyPack | null>(null);
  const [policyReviewer, setPolicyReviewer] = useState("AL · Recall safety reviewer");
  const [policyAttested, setPolicyAttested] = useState(false);
  const [policyPending, setPolicyPending] = useState(false);
  const [customPackage, setCustomPackage] = useState<EvidencePackage | null>(null);
  const [customPackagePending, setCustomPackagePending] = useState(false);
  const [customReviewRationale, setCustomReviewRationale] = useState("");
  const [customReviewAttested, setCustomReviewAttested] = useState(false);
  const [customReviewPending, setCustomReviewPending] = useState(false);
  const findings = useMemo<Finding[]>(() => (
    demoRun?.report.findings.map((item) => ({
      id: item.fact_id,
      label: item.label,
      canonical: item.canonical_value,
      evidence: item.evidence ?? "No evidence extracted",
      pass: item.status === "pass",
      status: item.status.toUpperCase(),
      reason: item.reason,
    })) ?? []
  ), [demoRun]);
  const failedCount = findings.filter((item) => !item.pass).length;
  const realMediaEnabled = Boolean(realCase?.contract.human_confirmed);
  const realPackageStatus = evidencePackage?.recall_id === "rc_cpsc_26_333"
    ? evidencePackage.status
    : realCase?.package?.status;
  const realReleaseLabel = realPackageStatus === "approved"
    ? "APPROVED FOR DEMO RELEASE"
    : realPackageStatus === "rejected"
      ? "REJECTED — DO NOT RELEASE"
      : realPackageStatus === "needs_review"
        ? "HUMAN REVIEW REQUIRED"
        : realMediaEnabled
          ? "DRAFT GENERATION ENABLED"
          : "CONFIRMATION REQUIRED";
  const displayContract = useMemo(() => {
    if (workspaceCase !== "cpsc" || !realCase) return demoContract;
    const serial = realCase.contract.affected_lot_ranges[0];
    return [
      ["Product", realCase.contract.product_name, "product.identity"],
      ["Models", realCase.contract.affected_models.join(", "), "product.affected_models"],
      ["Serial range", serial ? `${serial.start} → ${serial.end}` : "Not specified", "product.affected_serials"],
      ["Hazard", realCase.contract.hazard, "hazard.burn"],
      ["Required action", realCase.contract.required_action, "required_action.stop_oven_use"],
      ["Remedy", realCase.contract.remedy, "remedy.approved"],
      ["Contact", `${realCase.contract.contact.phone} · ${realCase.contract.contact.url}`, "contact.official"],
      ["Recall date", "March 19, 2026", "recall.effective_date"],
    ] as const;
  }, [workspaceCase, realCase]);

  async function refreshStorage() {
    try {
      const health = await fetch(`${apiUrl}/api/storage/health`).then((response) => {
        if (!response.ok) throw new Error("Storage health failed");
        return response.json() as Promise<{ connected?: boolean; status?: string }>;
      });
      setStorageStatus(health.connected ? "connected" : health.status === "memory" ? "memory" : "offline");
      if (health.connected) {
        const listing = await fetch(`${apiUrl}/api/storage/objects?prefix=recallcast%2F&max_keys=100`).then((response) => {
          if (!response.ok) throw new Error("Storage listing failed");
          return response.json() as Promise<{ objects: unknown[] }>;
        });
        setStorageObjectCount(listing.objects.length);
      }
    } catch {
      setStorageStatus("offline");
    }
  }

  async function refreshContract() {
    const demo = await fetch(`${apiUrl}/api/demo`)
      .then((response) => {
        if (!response.ok) throw new Error("Demo contract failed");
        return response.json() as Promise<{
          contract: { version: number; contract_sha256: string };
        }>;
      })
      .catch(() => null);
    if (demo) {
      setSourceVersion(demo.contract.version);
      setContractHash(demo.contract.contract_sha256);
    }
  }

  async function refreshRealCase() {
    const loaded = await fetch(`${apiUrl}/api/cases/cpsc-26-333`)
      .then((response) => {
        if (!response.ok) throw new Error("Public case failed");
        return response.json() as Promise<RealCasePayload>;
      })
      .catch(() => null);
    if (loaded) setRealCase(loaded);
    return loaded;
  }

  useEffect(() => {
    void refreshStorage();
    void refreshContract();
    void refreshRealCase();
  }, []);

  async function selectWorkspaceCase(next: WorkspaceCase) {
    setWorkspaceCase(next);
    setActiveNavigation("workspace");
    setShowContract(false);
    setShowGeneration(false);
    setRunState("idle");
    setDemoRun(null);
    setEvidencePackage(null);
    setGenerationState("idle");
    setMediaKitView("consumer");
    setJudgeMode(false);
    setRealAcknowledged(false);
    setRealReviewRationale("");
    setRealReviewAttested(false);
    setRealCaseError(null);
    document.getElementById("workspace-top")?.scrollIntoView({ behavior: "smooth" });
    if (next !== "cpsc") return;
    const loaded = realCase ?? await refreshRealCase();
    if (!loaded) {
      setRealCaseError("The public CPSC case could not be loaded from the API.");
      return;
    }
    const stored = await fetch(`${apiUrl}/api/cases/cpsc-26-333/bootstrap`, {
      method: "POST",
    }).then((response) => response.ok).catch(() => false);
    setRealCaseStored(stored);
    if (stored) void refreshStorage();
  }

  async function animateRun(retry = false, scenarioOverride?: Scenario) {
    setRunState("running");
    setParentLinked(retry);
    setActiveStage(-1);
    setDemoError(null);
    const requestedScenario = scenarioOverride ?? scenario;
    const apiRequest = fetch(
      retry && runId
        ? `${apiUrl}/api/demo/retry/${runId}`
        : `${apiUrl}/api/demo/run`,
      retry && runId
        ? { method: "POST" }
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              scenario: requestedScenario,
              locale: "en-US",
              channel: "video",
            }),
          },
    )
      .then(async (response) => {
        if (!response.ok) throw new Error("API demo run failed");
        return response.json() as Promise<DemoRunPayload>;
      })
      .catch(() => null);
    const stopAt = fixturePipeline.length - 1;
    for (let index = 0; index <= stopAt; index += 1) {
      await new Promise((resolve) => setTimeout(resolve, 220));
      setActiveStage(index);
    }
    const backendRun = await apiRequest;
    if (backendRun) {
      setRunId(backendRun.run_id);
      setAssetId(backendRun.asset_id);
      setDemoRun(backendRun);
      setParentLinked(Boolean(backendRun.parent_run_id));
      setRunState(
        backendRun.status === "quarantined" ? "quarantined" : "review",
      );
      void refreshStorage();
      return;
    }
    setRunState("idle");
    setDemoError("The validation API did not return a run. Check the API connection and retry.");
  }

  function changeScenario(next: Scenario) {
    setScenario(next);
    setRunState("idle");
    setParentLinked(false);
    setActiveStage(-1);
    setRunId(null);
    setAssetId(null);
    setDemoRun(null);
    setDemoError(null);
  }

  async function approveAsset() {
    if (!assetId) return;
    const approved = await fetch(`${apiUrl}/api/assets/${assetId}/approve`, {
        method: "POST",
      }).catch(() => null);
    if (!approved?.ok) {
      setDemoError("Approval could not be persisted. The asset remains in review.");
      return;
    }
    void refreshStorage();
    setRunState("approved");
  }

  async function updateSource() {
    const response = await fetch(`${apiUrl}/api/demo/source-update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ remedy: "Full refund." }),
    }).catch(() => null);
    if (!response?.ok) {
      setDemoError("The source update could not be persisted.");
      return;
    }
    const update = await response.json() as {
      source_version: number;
      contract: { contract_sha256: string };
    };
    setSourceVersion(update.source_version);
    setContractHash(update.contract.contract_sha256);
    setRunState("stale");
  }

  async function generatePackage() {
    if (workspaceCase === "cpsc") {
      setActiveNavigation("packages");
      if (!realMediaEnabled) {
        document.getElementById("real-release")?.scrollIntoView({ behavior: "smooth" });
        return;
      }
      await generateRealCasePackage();
      return;
    }
    setActiveNavigation("packages");
    if (generationState === "generated" && evidencePackage?.locale === packageLocale) {
      setShowGeneration(true);
      return;
    }
    setGenerationState("running");
    try {
      const generated = await fetch(`${apiUrl}/api/packages/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ locale: packageLocale, force_regenerate: false }),
      }).then(async (response) => {
        if (!response.ok) throw new Error("Evidence package generation failed");
        return response.json() as Promise<EvidencePackage>;
      });
      setEvidencePackage(generated);
      setGenerationState("generated");
      setShowGeneration(true);
      void refreshStorage();
    } catch {
      setGenerationState("error");
      setShowGeneration(true);
    }
  }

  async function confirmRealCase() {
    if (!realAcknowledged) return;
    setRealConfirming(true);
    setRealCaseError(null);
    try {
      const response = await fetch(`${apiUrl}/api/cases/cpsc-26-333/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reviewer: "AL · Local demo operator",
          acknowledgment: true,
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(intakeDetail(payload, "Operator confirmation failed."));
      await refreshRealCase();
      void refreshStorage();
    } catch (error) {
      setRealCaseError(error instanceof Error ? error.message : "Operator confirmation failed.");
    } finally {
      setRealConfirming(false);
    }
  }

  async function generateRealCasePackage() {
    if (generationState === "generated" && evidencePackage?.recall_id === "rc_cpsc_26_333") {
      setShowGeneration(true);
      return;
    }
    setGenerationState("running");
    setRealCaseError(null);
    try {
      const response = await fetch(`${apiUrl}/api/cases/cpsc-26-333/packages/generate`, {
        method: "POST",
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(intakeDetail(payload, "Real-case media generation failed."));
      setEvidencePackage(payload as EvidencePackage);
      setMediaKitView("consumer");
      setGenerationState("generated");
      setShowGeneration(true);
      void refreshStorage();
    } catch (error) {
      setGenerationState("error");
      setRealCaseError(error instanceof Error ? error.message : "Real-case media generation failed.");
      setShowGeneration(true);
    }
  }

  async function runJudgeMode() {
    setJudgeMode(true);
    setWorkspaceCase("cpsc");
    setActiveNavigation("packages");
    setRealCaseError(null);
    const loaded = await refreshRealCase();
    if (!loaded?.contract.human_confirmed) {
      setGenerationState("idle");
      setRealCaseError("Judge Mode is ready. Verify and acknowledge the official source once to unlock the real package.");
      window.setTimeout(() => document.getElementById("real-release")?.scrollIntoView({ behavior: "smooth" }), 50);
      return;
    }
    await generateRealCasePackage();
  }

  async function submitRealPackageReview(decision: "approved" | "rejected") {
    if (!evidencePackage || evidencePackage.recall_id !== "rc_cpsc_26_333") return;
    setRealReviewPending(true);
    setRealCaseError(null);
    try {
      const response = await fetch(
        `${apiUrl}/api/cases/cpsc-26-333/packages/${evidencePackage.package_id}/review`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            decision,
            reviewer: realReviewReviewer.trim(),
            rationale: realReviewRationale.trim(),
            attestation: decision === "approved" && realReviewAttested,
          }),
        },
      );
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(intakeDetail(payload, "Review decision could not be persisted."));
      setEvidencePackage(payload as EvidencePackage);
      await refreshRealCase();
      void refreshStorage();
    } catch (error) {
      setRealCaseError(error instanceof Error ? error.message : "Review decision could not be persisted.");
    } finally {
      setRealReviewPending(false);
    }
  }

  function intakeDetail(payload: unknown, fallback: string): string {
    if (!payload || typeof payload !== "object" || !("detail" in payload)) return fallback;
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
    if (Array.isArray(detail) && detail.length && typeof detail[0] === "object" && detail[0] && "msg" in detail[0]) {
      return String((detail[0] as { msg: unknown }).msg);
    }
    return fallback;
  }

  async function selectIntakeFile(file: File | undefined) {
    if (!file) return;
    const suffix = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (![".txt", ".md", ".json"].includes(suffix)) {
      setIntakeError("Choose a UTF-8 .txt, .md, or .json file.");
      setIntakeState("error");
      return;
    }
    if (file.size > 200 * 1024) {
      setIntakeError("The source file must be 200 KB or smaller.");
      setIntakeState("error");
      return;
    }
    try {
      setIntakeText(await file.text());
      setIntakeSourceName(file.name);
      setIntakeDraft(null);
      setIntakeError(null);
      setIntakeState("idle");
    } catch {
      setIntakeError("The file could not be read as UTF-8 text.");
      setIntakeState("error");
    }
  }

  async function extractIntake() {
    setIntakeState("extracting");
    setIntakeError(null);
    setIntakeDraft(null);
    try {
      const response = await fetch(`${apiUrl}/api/intake/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_name: intakeSourceName || "pasted-recall.md",
          source_text: intakeText,
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(intakeDetail(payload, "Recall extraction failed."));
      setIntakeDraft(payload as IntakeDraft);
      setIntakeState("review");
      void refreshStorage();
    } catch (error) {
      setIntakeError(error instanceof Error ? error.message : "Recall extraction failed.");
      setIntakeState("error");
    }
  }

  function updateIntakeExtraction(patch: Partial<IntakeExtraction>) {
    setIntakeDraft((current) => current ? {
      ...current,
      extraction: { ...current.extraction, ...patch },
    } : current);
  }

  async function confirmIntake() {
    if (!intakeDraft) return;
    setIntakeState("confirming");
    setIntakeError(null);
    try {
      const response = await fetch(`${apiUrl}/api/intake/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draft_id: intakeDraft.draft_id,
          extraction: intakeDraft.extraction,
        }),
      });
      const payload = await response.json().catch(() => null) as {
        detail?: { warnings?: string[] } | string;
        contract?: { contract_sha256?: string };
        policy_pack?: PolicyPack;
      } | null;
      if (!response.ok) {
        if (payload?.detail && typeof payload.detail === "object" && payload.detail.warnings) {
          setIntakeDraft({ ...intakeDraft, validation_warnings: payload.detail.warnings });
        }
        throw new Error(intakeDetail(payload, "Contract confirmation failed."));
      }
      setConfirmedContractHash(payload?.contract?.contract_sha256 ?? null);
      setIntakePolicy(payload?.policy_pack ?? null);
      setIntakeState("confirmed");
      void refreshStorage();
    } catch (error) {
      setIntakeError(error instanceof Error ? error.message : "Contract confirmation failed.");
      setIntakeState("review");
    }
  }

  function updatePolicyConcepts(field: PolicyConceptGroup["field"], value: string) {
    setIntakePolicy((current) => current ? {
      ...current,
      concept_groups: current.concept_groups.map((group) => group.field === field ? {
        ...group,
        required_concepts: value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean),
      } : group),
    } : current);
  }

  async function activateIntakePolicy() {
    if (!intakeDraft || !intakePolicy) return;
    setPolicyPending(true);
    setIntakeError(null);
    try {
      const response = await fetch(`${apiUrl}/api/intake/${intakeDraft.draft_id}/policy/activate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          concept_groups: intakePolicy.concept_groups,
          reviewer: policyReviewer,
          attestation: policyAttested,
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(intakeDetail(payload, "Policy activation failed."));
      setIntakePolicy(payload as PolicyPack);
      void refreshStorage();
    } catch (error) {
      setIntakeError(error instanceof Error ? error.message : "Policy activation failed.");
    } finally {
      setPolicyPending(false);
    }
  }

  async function generateCustomPackage() {
    if (!intakeDraft || intakePolicy?.status !== "active") return;
    setCustomPackagePending(true);
    setIntakeError(null);
    try {
      const response = await fetch(`${apiUrl}/api/intake/${intakeDraft.draft_id}/packages/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ locale: "en-US", force_regenerate: false }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(intakeDetail(payload, "Custom package generation failed."));
      setCustomPackage(payload as EvidencePackage);
      void refreshStorage();
    } catch (error) {
      setIntakeError(error instanceof Error ? error.message : "Custom package generation failed.");
    } finally {
      setCustomPackagePending(false);
    }
  }

  async function reviewCustomPackage(decision: "approved" | "rejected") {
    if (!intakeDraft || !customPackage) return;
    setCustomReviewPending(true);
    setIntakeError(null);
    try {
      const response = await fetch(`${apiUrl}/api/intake/${intakeDraft.draft_id}/packages/${customPackage.package_id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision,
          reviewer: policyReviewer,
          rationale: customReviewRationale,
          attestation: decision === "approved" ? customReviewAttested : false,
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(intakeDetail(payload, "Human decision failed."));
      setCustomPackage(payload as EvidencePackage);
      void refreshStorage();
    } catch (error) {
      setIntakeError(error instanceof Error ? error.message : "Human decision failed.");
    } finally {
      setCustomReviewPending(false);
    }
  }

  function navigate(view: NavigationView) {
    setActiveNavigation(view);
    if (view === "intake") {
      setShowIntake(true);
      return;
    }
    if (view === "packages") {
      if (workspaceCase === "cpsc") {
        void generatePackage();
      } else {
        void generatePackage();
      }
      return;
    }
    if (view === "policy") {
      setShowContract(true);
      return;
    }
    document.getElementById(view === "lineage" ? (workspaceCase === "cpsc" ? "real-lineage" : "pipeline-evidence") : "workspace-top")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function closeIntake() {
    setShowIntake(false);
    setActiveNavigation("workspace");
  }

  const displayedPipeline = demoRun?.events ?? fixturePipeline.map(
    ([label, provider, model], index) => ({
      stage: `pending-${index}`,
      label,
      status: "completed",
      provider,
      model,
      latency_ms: 0,
      attempt: 1,
    }),
  );

  const visibleFindings =
    runState === "idle" || runState === "running" ? [] : findings;

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brandMark"><Icon name="shield" /></span>
          <span>RecallCast</span>
          <small>FACTLOCK</small>
        </div>

        <nav>
          <button className={`navItem ${activeNavigation === "workspace" ? "active" : ""}`} onClick={() => navigate("workspace")}><Icon name="pulse" /><span>Workspace</span></button>
          <button className={`navItem ${activeNavigation === "intake" ? "active" : ""}`} onClick={() => navigate("intake")}><Icon name="play" /><span>Import source</span><b>NEW</b></button>
          <button className={`navItem ${activeNavigation === "packages" ? "active" : ""}`} onClick={() => navigate("packages")}><Icon name="cube" /><span>Media packages</span><b>{supportedPackageLocales.length}</b></button>
          <button className={`navItem ${activeNavigation === "lineage" ? "active" : ""}`} onClick={() => navigate("lineage")}><Icon name="branch" /><span>Lineage</span></button>
          <button className={`navItem ${activeNavigation === "policy" ? "active" : ""}`} onClick={() => navigate("policy")}><Icon name="shield" /><span>Policy</span></button>
        </nav>

        <div className="sideSection">
          <p>RECALL CASES</p>
          <button className={`recallLink ${workspaceCase === "demo" ? "recallLinkActive" : ""}`} onClick={() => void selectWorkspaceCase("demo")}>
            <span className="productGlyph"><i /><i /><i /></span>
            <span><strong>Glow Mini Heater</strong><small>FICTIONAL · RC-DEMO-001</small></span>
          </button>
          <button className={`recallLink ${workspaceCase === "cpsc" ? "recallLinkActive" : ""}`} onClick={() => void selectWorkspaceCase("cpsc")}>
            <span className="productGlyph rangeGlyph"><i /><i /><i /></span>
            <span><strong>Frigidaire Gas Ranges</strong><small>PUBLIC · CPSC 26-333</small></span>
          </button>
        </div>

        <div className="systemCard">
          <div><span className="liveDot" /> Systems ready</div>
          <p>{workspaceCase === "cpsc" ? "Public-source review mode" : "Demo mode · fictional data"}</p>
          <div className="systemRow"><span>B2 storage</span><b>{storageStatus === "connected" ? `Connected · ${storageObjectCount}` : storageStatus}</b></div>
          <div className="systemRow"><span>Genblaze</span><b>SDK ready</b></div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="breadcrumbs">RECALLS <span>/</span> {workspaceCase === "cpsc" ? "CPSC 26-333" : "RC-DEMO-001"}</div>
          <div className="topActions">
            <select className="caseSelect" aria-label="Recall case" value={workspaceCase} onChange={(event) => void selectWorkspaceCase(event.target.value as WorkspaceCase)}>
              <option value="demo">Fictional heater demo</option>
              <option value="cpsc">Public CPSC 26-333</option>
            </select>
            <span className={`demoBadge ${workspaceCase === "cpsc" ? "publicBadge" : ""}`}>{workspaceCase === "cpsc" ? "PUBLIC CPSC SOURCE" : "FICTIONAL DEMO"}</span>
            <button className="ghostButton" onClick={() => navigate("intake")}>
              <Icon name="play" /> Import source
            </button>
            <select
              className="localeSelect"
              aria-label="Package language"
              value={packageLocale}
              disabled={workspaceCase === "cpsc"}
              onChange={(event) => {
                setPackageLocale(event.target.value as "en-US" | "es-US");
                setGenerationState("idle");
              }}
            >
              <option value="en-US">English</option>
              <option value="es-US">Español</option>
            </select>
            <button className="ghostButton" onClick={generatePackage} disabled={generationState === "running" || (workspaceCase === "cpsc" && !realMediaEnabled)}>
              <Icon name="play" /> {workspaceCase === "cpsc" ? !realMediaEnabled ? "Confirm source to generate" : generationState === "running" ? "Building voice + visual draft…" : generationState === "generated" ? "View public-source draft" : "Build voice + visual draft" : generationState === "running" ? "Building evidence package…" : generationState === "generated" ? "View verified package" : "Build verified package"}
            </button>
            <button className="ghostButton" onClick={() => navigate("policy")}>
              <Icon name="lock" /> View source contract
            </button>
            <span className="avatar">AL</span>
          </div>
        </header>

        <nav className="mobileNav" aria-label="Mobile navigation">
          <button className={activeNavigation === "workspace" ? "active" : ""} onClick={() => navigate("workspace")}><Icon name="pulse" /><span>Home</span></button>
          <button className={activeNavigation === "intake" ? "active" : ""} onClick={() => navigate("intake")}><Icon name="play" /><span>Import</span></button>
          <button className={activeNavigation === "packages" ? "active" : ""} onClick={() => navigate("packages")}><Icon name="cube" /><span>Media</span></button>
          <button className={activeNavigation === "lineage" ? "active" : ""} onClick={() => navigate("lineage")}><Icon name="branch" /><span>Lineage</span></button>
          <button className={activeNavigation === "policy" ? "active" : ""} onClick={() => navigate("policy")}><Icon name="shield" /><span>Policy</span></button>
        </nav>

        <div className="content" id="workspace-top">
          <section className="judgeLaunch" aria-label="Judge mode introduction">
            <span className="judgePulse"><Icon name="pulse" /></span>
            <div><small>ONE-CLICK JUDGE MODE</small><strong>Watch RecallCast catch a dangerous serial mutation and prove the correction.</strong><p>Real public source · two Genblaze voice runs · final-pixel evidence · durable B2 lineage</p></div>
            <button className="primaryButton" onClick={() => void runJudgeMode()} disabled={generationState === "running"}><Icon name="play" />{generationState === "running" && judgeMode ? "Loading verified story…" : "Run 60-second proof"}</button>
          </section>
          <section className="recallHeader">
            {workspaceCase === "cpsc" ? (
              <div className="productVisual rangeVisual"><div className="rangeTop"><i /><i /><i /><i /></div><div className="rangeBody"><span /><div className="ovenWindow"><i /><i /></div></div></div>
            ) : (
              <div className="productVisual">
                <div className="heatWave waveOne" />
                <div className="heatWave waveTwo" />
                <div className="heater">
                  <div className="grille">{Array.from({ length: 15 }).map((_, i) => <i key={i} />)}</div>
                  <div className="heaterFoot" />
                </div>
              </div>
            )}
            <div className="headline">
              <div className="eyebrow"><span>{workspaceCase === "cpsc" ? "PUBLIC PRODUCT RECALL" : "URGENT PRODUCT RECALL"}</span><b>{workspaceCase === "cpsc" ? "CPSC 26-333" : `Source v${sourceVersion}.0`}</b></div>
              <h1>{workspaceCase === "cpsc" ? <>Frigidaire<br />Gas Ranges</> : <>Northstar Glow<br />Mini Heater</>}</h1>
              <p>{workspaceCase === "cpsc" ? "Source-backed contract covering 23 exact models and one serial-number range." : "Fact-locked media package for affected models NG-100 and NG-110."}</p>
              <div className="headerMeta">
                <span><small>{workspaceCase === "cpsc" ? "SERIAL RANGE" : "AFFECTED LOTS"}</small><strong>{workspaceCase === "cpsc" ? "VF52200000 — VF54399999" : "A71 — A94"}</strong></span>
                <span><small>{workspaceCase === "cpsc" ? "RECALL DATE" : "EFFECTIVE"}</small><strong>{workspaceCase === "cpsc" ? "19 MAR 2026" : "29 JUL 2026"}</strong></span>
                <span><small>SEVERITY</small><strong className="critical">{workspaceCase === "cpsc" ? "BURN HAZARD" : "CRITICAL"}</strong></span>
              </div>
            </div>
            <div className="complianceRing">
              <div><strong>{workspaceCase === "cpsc" ? realPackageStatus === "approved" ? "100" : realPackageStatus === "rejected" ? "0" : "—" : runState === "stale" ? "0" : runState === "approved" ? "100" : "—"}</strong><small>RELEASE<br />STATUS</small></div>
              <p>{workspaceCase === "cpsc" ? realPackageStatus === "approved" ? "Approved for demo release" : realPackageStatus === "rejected" ? "Rejected by reviewer" : realPackageStatus === "needs_review" ? "Human decision required" : realMediaEnabled ? "Draft generation enabled" : "Operator review required" : runState === "approved" ? "Approved" : runState === "stale" ? "Stale" : "Human approval required"}</p>
            </div>
          </section>

          <section className="factBanner">
            <span className="bannerIcon"><Icon name="shield" /></span>
            <div>
              <strong>{workspaceCase === "cpsc" ? "8 source-backed fact groups" : "8 critical facts locked"}</strong>
              <p>{workspaceCase === "cpsc" ? realMediaEnabled ? "Operator acknowledgment recorded; the CPSC serial/model policy can now validate an unaffiliated media draft." : "Public facts are captured; acknowledge the source to activate the CPSC serial/model policy." : "Identifiers, hazard, required action, remedy, and contact cannot drift."}</p>
            </div>
            <div className="factTicks">{displayContract.slice(0, 5).map((item) => <span key={item[2]}><Icon name="check" /></span>)}</div>
            <button onClick={() => navigate("policy")}>Inspect contract <span>→</span></button>
          </section>

          {workspaceCase === "cpsc" ? (
            realCase ? (
              <section className="realCaseGrid">
                <article className="panel sourcePanel" id="real-lineage">
                  <div className="panelHeading">
                    <div><span className="stepNumber">01</span><div><h2>Official source evidence</h2><p>Traceable public facts, not a RecallCast-authored recall.</p></div></div>
                    <span className="sourceChip">CPSC.GOV</span>
                  </div>
                  <div className="sourceBody">
                    <div className="sourceIdentity"><Icon name="shield" /><span><small>AUTHORITATIVE SOURCE</small><strong>{realCase.source_authority}</strong><p>Recall {realCase.recall_number} · published March 19, 2026</p></span></div>
                    <div className="realMetrics">
                      <span><strong>{realCase.stats.units_us.toLocaleString()}</strong><small>U.S. UNITS</small></span>
                      <span><strong>{realCase.stats.reported_incidents}</strong><small>REPORTS</small></span>
                      <span><strong>{realCase.stats.reported_injuries}</strong><small>BURN INJURIES</small></span>
                      <span><strong>{realCase.stats.affected_models}</strong><small>MODELS</small></span>
                    </div>
                    <a className="sourceButton" href={realCase.source_url} target="_blank" rel="noreferrer">Open official CPSC notice <span>↗</span></a>
                    <p className="sourceDisclaimer">{realCase.disclaimer}</p>
                  </div>
                </article>

                <article className="panel coveragePanel">
                  <div className="panelHeading">
                    <div><span className="stepNumber">02</span><div><h2>Identifier coverage</h2><p>Every model remains exact-match blocking.</p></div></div>
                    <span className="policyChip">23 MODELS</span>
                  </div>
                  <div className="serialLock"><small>AFFECTED SERIAL RANGE</small><strong>VF52200000 <span>through</span> VF54399999</strong></div>
                  <div className="modelCloud">{realCase.contract.affected_models.map((model) => <code key={model}>{model}</code>)}</div>
                </article>

                <article className="panel releasePanel" id="real-release">
                  <div className="panelHeading">
                    <div><span className="stepNumber">03</span><div><h2>Release readiness</h2><p>Real data raises the assurance bar.</p></div></div>
                    <span className={`decision ${realPackageStatus === "rejected" || !realMediaEnabled ? "failed" : "passed"}`}>{realReleaseLabel}</span>
                  </div>
                  <div className="releaseChecks">
                    <div className="complete"><Icon name="check" /><span><strong>Public source captured</strong><small>CPSC URL, source hash, recall number, and retrieval date</small></span><em>{realCaseStored ? "B2 STORED" : "SOURCE READY"}</em></div>
                    <div className="complete"><Icon name="check" /><span><strong>Fact contract compiled</strong><small>23 models, serial range, hazard, action, remedy, and contact</small></span><em>LOCKED</em></div>
                    {realMediaEnabled ? <>
                      <div className="complete"><Icon name="check" /><span><strong>Operator acknowledgment recorded</strong><small>{realCase.reviewer ?? "Local demo operator"} confirmed the public-source facts for an unaffiliated draft.</small></span><em>RECORDED</em></div>
                      <div className="complete"><Icon name="check" /><span><strong>CPSC serial/model policy active</strong><small>Audio and visual modalities have separate deterministic coverage requirements.</small></span><em>FACTLOCK V3</em></div>
                      {realPackageStatus && <div className="complete"><Icon name="check" /><span><strong>Generated media independently verified</strong><small>Final pixels and reverse-transcribed narration passed the assigned public-case policy.</small></span><em>PASS</em></div>}
                      {realPackageStatus === "approved" && <div className="complete"><Icon name="check" /><span><strong>Accountable human approval recorded</strong><small>{realCase.package?.review?.reviewer ?? "Reviewer"} bound the decision to the package, contract, artifacts, and validation report.</small></span><em>APPROVED</em></div>}
                      {realPackageStatus === "rejected" && <div className="blocked"><b>!</b><span><strong>Human reviewer rejected this draft</strong><small>{realCase.package?.review?.rationale ?? "The asset must not be released."}</small></span><em>BLOCKED</em></div>}
                      {realPackageStatus === "needs_review" && <div className="blocked"><b>!</b><span><strong>Final human decision required</strong><small>FactLock can establish conformity, but it cannot assume release authority.</small></span><em>BLOCKING</em></div>}
                    </> : <>
                      <div className="blocked"><b>!</b><span><strong>Operator acknowledgment required</strong><small>Verify the official notice before enabling an unaffiliated AI media draft.</small></span><em>BLOCKING</em></div>
                      <div className="blocked"><b>!</b><span><strong>Policy and media generation paused</strong><small>The serial/model policy activates only after explicit acknowledgment.</small></span><em>BLOCKING</em></div>
                    </>}
                  </div>
                  {realMediaEnabled ? (
                    <div className="realGenerateBar">
                      <div><small>{realPackageStatus === "approved" ? "HUMAN-APPROVED DEMO DRAFT" : realPackageStatus === "rejected" ? "REJECTED DRAFT" : "UNAFFILIATED PUBLIC-SOURCE DRAFT"}</small><strong>{realPackageStatus ? "Open the media, evidence, and human decision" : "Generate deterministic visual + Genblaze/OpenAI voice"}</strong><p>{realPackageStatus ? "The package head and append-only review evidence are stored in B2." : "Final pixels and audio will be independently read, checked, and stored in B2."}</p></div>
                      <button className="primaryButton" onClick={() => void generateRealCasePackage()} disabled={generationState === "running"}><Icon name="play" />{generationState === "running" ? "Generating and validating…" : generationState === "generated" || realPackageStatus ? "View package proof" : "Build voice + visual draft"}</button>
                    </div>
                  ) : (
                    <div className="realConfirmation">
                      <label><input type="checkbox" checked={realAcknowledged} onChange={(event) => setRealAcknowledged(event.target.checked)} /><span><strong>I checked the official CPSC notice</strong><small>I understand this enables an unaffiliated demo draft—not a CPSC or Electrolux-approved message.</small></span></label>
                      <button className="primaryButton" onClick={() => void confirmRealCase()} disabled={!realAcknowledged || realConfirming}>{realConfirming ? "Recording acknowledgment…" : "Acknowledge & enable generation"}</button>
                    </div>
                  )}
                  {realCaseError && <p className="intakeError realCaseError" role="alert">{realCaseError}</p>}
                </article>
              </section>
            ) : (
              <section className="panel realLoading"><Icon name="pulse" /><strong>{realCaseError ?? "Loading public CPSC case…"}</strong></section>
            )
          ) : (
          <>
          <section className="workGrid">
            <div className="panel scenarioPanel">
              <div className="panelHeading">
                <div>
                  <span className="stepNumber">01</span>
                  <div><h2>Select validation case</h2><p>Choose an approved output or a controlled safety defect.</p></div>
                </div>
                <span className="policyChip">FAIL-CLOSED POLICY</span>
              </div>

              <div className="scenarioGrid">
                <button className={`scenario ${scenario === "approved" ? "selected" : ""}`} onClick={() => changeScenario("approved")}>
                  <span className="scenarioTop"><i className="statusDot pass" /> APPROVED FIXTURE <em>PASS</em></span>
                  <strong>Verified recall package</strong>
                  <p>Every critical fact survives generation.</p>
                  <span className="waveform">{Array.from({ length: 28 }).map((_, i) => <i key={i} style={{ height: `${7 + ((i * 11) % 18)}px` }} />)}</span>
                </button>
                <button className={`scenario ${scenario === "identifier_mutation" ? "selected danger" : ""}`} onClick={() => changeScenario("identifier_mutation")}>
                  <span className="scenarioTop"><i className="statusDot fail" /> CONTROLLED DEFECT <em>BLOCK</em></span>
                  <strong>Identifier mutation</strong>
                  <p><del>NG-110</del> changed to <mark>NG-101</mark></p>
                  <span className="diffLine"><span>EXACT MATCH</span><b>1 mutation</b></span>
                </button>
                <button className={`scenario ${scenario === "action_weakening" ? "selected danger" : ""}`} onClick={() => changeScenario("action_weakening")}>
                  <span className="scenarioTop"><i className="statusDot fail" /> CONTROLLED DEFECT <em>BLOCK</em></span>
                  <strong>Action weakening</strong>
                  <p>“Use only when supervised.”</p>
                  <span className="diffLine"><span>POLARITY CHECK</span><b>meaning changed</b></span>
                </button>
              </div>

              <div className="runBar">
                <div className="selectionSummary">
                  <span className="videoThumb"><Icon name="play" /></span>
                  <div><small>VALIDATION INPUT</small><strong>EN · Controlled transcript fixture</strong></div>
                  <span><small>CHANNEL</small><strong>VIDEO POLICY</strong></span>
                  <span><small>SOURCE</small><strong>v{sourceVersion}.0</strong></span>
                </div>
                <button className="primaryButton" onClick={() => animateRun(false)} disabled={runState === "running"}>
                  <Icon name="shield" /> {runState === "running" ? "Validating…" : "Run FactLock"}
                </button>
              </div>
            </div>

            <div className="panel pipelinePanel" id="pipeline-evidence">
              <div className="panelHeading compact">
                <div><span className="stepNumber">02</span><div><h2>Controlled validation evidence</h2><p>API events and B2 provenance</p></div></div>
                {parentLinked && <span className="parentChip">↳ Parent linked</span>}
              </div>
              <div className="pipeline">
                {displayedPipeline.map((stage, index) => {
                  const complete = index <= activeStage;
                  const blocked = complete && stage.status === "blocked";
                  const waiting = index > activeStage;
                  return (
                    <div className={`pipeStep ${complete ? "complete" : ""} ${blocked ? "blocked" : ""}`} key={`${stage.stage}-${stage.attempt}`}>
                      <span className="pipeNode">{complete && !blocked ? <Icon name="check" /> : blocked ? "!" : index + 1}</span>
                      <div><strong>{stage.label}</strong><small>{stage.provider} · {stage.model}</small></div>
                      <em>{blocked ? "BLOCKED" : complete && stage.latency_ms ? `${stage.latency_ms} ms` : waiting ? "WAITING" : complete ? "DONE" : ""}</em>
                    </div>
                  );
                })}
              </div>
              <div className="manifestStrip">
                <Icon name="lock" />
                <span><small>ASSET EVIDENCE HASH</small><strong>{demoRun ? `B2 persisted · ${demoRun.storage_objects.length} run objects` : "Awaiting run"}</strong></span>
                <code>{demoRun ? `${demoRun.asset_sha256.slice(0, 8)}…${demoRun.asset_sha256.slice(-4)}` : "—"}</code>
              </div>
            </div>
          </section>

          <section className={`panel findingsPanel ${runState === "idle" ? "empty" : ""}`}>
            <div className="panelHeading">
              <div>
                <span className="stepNumber">03</span>
                <div><h2>FactLock conformance report</h2><p>Canonical contract compared with reverse-extracted evidence.</p></div>
              </div>
              {runState !== "idle" && runState !== "running" && (
                <span className={`decision ${failedCount && !parentLinked ? "failed" : "passed"}`}>
                  {failedCount && !parentLinked ? `${failedCount} BLOCKING FAILURE` : "ALL BLOCKING CHECKS PASS"}
                </span>
              )}
            </div>

            {runState === "idle" ? (
              <div className="emptyState"><Icon name="pulse" /><strong>{demoError ? "Validation request failed" : "No validation evidence yet"}</strong><p>{demoError ?? "Select a case and run FactLock to reverse-extract and compare the media."}</p></div>
            ) : runState === "running" ? (
              <div className="scanning">
                <span className="scanLine" />
                <div className="scanGrid">{displayContract.slice(0, 6).map((item, i) => <i key={item[2]} style={{ animationDelay: `${i * 100}ms` }} />)}</div>
                <strong>Reverse-extracting media evidence…</strong>
              </div>
            ) : (
              <>
                <div className="findingHeader"><span>LOCKED FACT</span><span>OBSERVED EVIDENCE</span><span>DECISION</span></div>
                <div className="findingRows">
                  {visibleFindings.map((item) => (
                    <div className={`finding ${item.pass ? "" : "findingFail"}`} key={item.id}>
                      <div><small>{item.id}</small><strong>{item.canonical}</strong></div>
                      <div><q>{item.evidence}</q><small>{item.reason}</small></div>
                      <div><span className={item.pass ? "passPill" : "failPill"}>{item.pass ? <><Icon name="check" /> PASS</> : <>! {item.status}</>}</span></div>
                    </div>
                  ))}
                </div>
                <div className={`decisionBar ${runState === "quarantined" ? "quarantine" : runState}`}>
                  <div className="decisionIcon">{runState === "quarantined" ? "!" : <Icon name="check" />}</div>
                  <div>
                    <small>RELEASE GATE</small>
                    <strong>
                      {runState === "quarantined" && "Asset quarantined"}
                      {runState === "review" && "Validation passed — human review required"}
                      {runState === "approved" && "Asset approved for release"}
                      {runState === "stale" && "Asset invalidated by source v2.0"}
                    </strong>
                    <p>
                      {runState === "quarantined" && "A blocking fact changed. The failed artifact is preserved as evidence."}
                      {runState === "review" && "FactLock cannot release media automatically. A reviewer remains accountable."}
                      {runState === "approved" && "Reviewer decision, asset hash, and validation evidence are linked."}
                      {runState === "stale" && "The approved remedy changed from free replacement to full refund."}
                    </p>
                  </div>
                  <div className="decisionActions">
                    {runState === "quarantined" && <button className="primaryButton" onClick={() => animateRun(true)}>Correct & retry <span>→</span></button>}
                    {runState === "review" && <button className="primaryButton" onClick={approveAsset}><Icon name="check" /> Approve asset</button>}
                    {runState === "approved" && <button className="outlineButton" onClick={updateSource}>Demo source update</button>}
                    {runState === "stale" && <button className="primaryButton" onClick={() => { setScenario("approved"); void animateRun(false, "approved"); }}>Regenerate from v{sourceVersion}.0</button>}
                  </div>
                </div>
              </>
            )}
          </section>
          </>
          )}
        </div>
      </section>

      {showIntake && (
        <div className="modalBackdrop" onMouseDown={closeIntake}>
          <section className="contractModal intakeModal" onMouseDown={(event) => event.stopPropagation()} aria-label="Import recall source">
            <div className="modalHead">
              <div><span className="bannerIcon"><Icon name="play" /></span><div><small>BRING YOUR OWN DATA</small><h2>Import a recall source</h2></div></div>
              <button aria-label="Close import source" onClick={closeIntake}>×</button>
            </div>

            {intakeState === "confirmed" && intakeDraft ? (
              <div className="intakeConfirmed">
                <span className="confirmedMark"><Icon name="check" /></span>
                <small>HUMAN-CONFIRMED SOURCE CONTRACT</small>
                <h3>{intakeDraft.extraction.product_name}</h3>
                <p>The source and contract are preserved separately{storageStatus === "connected" ? " in private Backblaze B2" : ""}. Now bind deterministic FactLock rules before any provider can generate media.</p>
                <dl>
                  <div><dt>Draft</dt><dd>{intakeDraft.draft_id}</dd></div>
                  <div><dt>Contract</dt><dd>{confirmedContractHash ?? "created"}</dd></div>
                  <div><dt>Policy</dt><dd>{intakePolicy?.status === "active" ? `${intakePolicy.policy_sha256.slice(0, 16)}… · active` : "Draft · generation blocked"}</dd></div>
                </dl>

                {intakePolicy?.status === "draft" && (
                  <section className="policyBuilder" aria-label="Policy Pack Builder">
                    <div className="policyBuilderHead"><span>02 · POLICY PACK BUILDER</span><strong>Lock what generation may never change</strong><p>Every concept must come from the confirmed source. Unsupported templates fail closed.</p></div>
                    <div className="policyCoverage">
                      <span><b>{intakePolicy.exact_identifiers.length}</b><small>EXACT MODELS</small></span>
                      <span><b>{intakePolicy.range_endpoints.length}</b><small>RANGE ENDPOINTS</small></span>
                      <span><b>2</b><small>MODALITIES</small></span>
                      <span><b>1</b><small>HUMAN GATE</small></span>
                    </div>
                    <div className="lockedRules">
                      <p><Icon name="lock" /><span><strong>Exact identifier rule</strong><small>{intakePolicy.exact_identifiers.join(" · ")}</small></span><em>AUTO-LOCKED</em></p>
                      <p><Icon name="lock" /><span><strong>Exact range endpoints</strong><small>{intakePolicy.range_endpoints.join(" · ")}</small></span><em>AUTO-LOCKED</em></p>
                    </div>
                    <div className="policyConcepts">
                      {intakePolicy.concept_groups.map((group) => (
                        <label key={group.field}>
                          <span>{group.field.replace("_", " ")} concepts <em>comma separated · source-grounded only</em></span>
                          <textarea aria-label={`${group.field.replace("_", " ")} concepts`} value={group.required_concepts.join(", ")} onChange={(event) => updatePolicyConcepts(group.field, event.target.value)} />
                          <small>Canonical: {group.canonical_value}</small>
                        </label>
                      ))}
                    </div>
                    <div className="policyActivation">
                      <label><span>Accountable policy reviewer</span><input aria-label="Accountable policy reviewer" value={policyReviewer} onChange={(event) => setPolicyReviewer(event.target.value)} /></label>
                      <label className="attestation"><input type="checkbox" checked={policyAttested} onChange={(event) => setPolicyAttested(event.target.checked)} /><span>I verified these rules against the approved source and understand activation enables provider generation, never automatic release.</span></label>
                      <button className="primaryButton" onClick={() => void activateIntakePolicy()} disabled={policyPending || !policyAttested || policyReviewer.trim().length < 2}>{policyPending ? "Binding and persisting policy…" : "Activate deterministic policy"}</button>
                    </div>
                  </section>
                )}

                {intakePolicy?.status === "active" && !customPackage && (
                  <section className="policyReady">
                    <Icon name="shield" /><div><small>POLICY ACTIVE · GENERATION UNLOCKED</small><strong>Contract + policy are hash-bound</strong><p>RecallCast will generate voice and visual media, independently transcribe/read both, quarantine drift, retry once, and stop for human review.</p></div>
                    <button className="primaryButton" onClick={() => void generateCustomPackage()} disabled={customPackagePending}>{customPackagePending ? "Generating → observing → validating…" : "Build fact-locked media"}</button>
                  </section>
                )}

                {customPackage && (
                  <section className="customPackageProof">
                    <div className="customMedia">
                      {customPackage.artifacts.find((item) => item.kind === "social_card")?.preview_url && <img src={customPackage.artifacts.find((item) => item.kind === "social_card")?.preview_url ?? ""} alt={`Generated recall card for ${intakeDraft.extraction.product_name}`} />}
                      {customPackage.artifacts.find((item) => item.kind === "narration" && item.accepted)?.preview_url && <audio controls preload="metadata" src={customPackage.artifacts.find((item) => item.kind === "narration" && item.accepted)?.preview_url ?? ""} />}
                    </div>
                    <div className="customEvidence">
                      <small>{customPackage.report.decision === "pass" ? "FACTLOCK PASS" : "QUARANTINED"}</small>
                      <h4>{customPackage.report.passed_count} checks passed · {customPackage.report.blocking_failure_count} blocking</h4>
                      <p>Final pixels and reverse-transcribed narration were evaluated independently against policy <code>{customPackage.policy_sha256?.slice(0, 12) ?? "—"}…</code>.</p>
                      <div className="customFindingList">{customPackage.report.findings.map((finding, index) => <span className={finding.blocking_failure ? "blocked" : "passed"} key={`${finding.fact_id}-${finding.evidence_source}-${index}`}><b>{finding.blocking_failure ? "!" : "✓"}</b><em>{finding.evidence_source ?? "integrity"}</em><strong>{finding.label}</strong></span>)}</div>
                      {customPackage.status === "needs_review" && (
                        <div className="customReviewGate">
                          <strong>Final human release gate</strong>
                          <textarea aria-label="Custom package review rationale" placeholder="Document why this package should or should not be released…" value={customReviewRationale} onChange={(event) => setCustomReviewRationale(event.target.value)} />
                          <label><input type="checkbox" checked={customReviewAttested} onChange={(event) => setCustomReviewAttested(event.target.checked)} /><span>I accept accountability for approving this contract-bound media package.</span></label>
                          <div><button className="outlineButton dangerOutline" onClick={() => void reviewCustomPackage("rejected")} disabled={customReviewPending || customReviewRationale.trim().length < 8}>Reject</button><button className="primaryButton" onClick={() => void reviewCustomPackage("approved")} disabled={customReviewPending || customReviewRationale.trim().length < 8 || !customReviewAttested}>Approve package</button></div>
                        </div>
                      )}
                      {customPackage.review && <div className={`customDecision ${customPackage.review.decision}`}><strong>{customPackage.review.decision.toUpperCase()}</strong><span>{customPackage.review.reviewer} · {customPackage.review.rationale}</span></div>}
                    </div>
                  </section>
                )}
                {intakeError && <p className="intakeError" role="alert">{intakeError}</p>}
                <div className="intakeActions">
                  <button className="outlineButton" onClick={() => { setIntakeDraft(null); setIntakePolicy(null); setCustomPackage(null); setIntakeText(""); setIntakeSourceName("pasted-recall.md"); setIntakeState("idle"); }}>Import another</button>
                  <button className="outlineButton" onClick={closeIntake}>Return to workspace</button>
                </div>
              </div>
            ) : intakeDraft ? (
              <>
                <p className="modalIntro">Review every extracted value against the source. Edits are re-checked for source grounding before confirmation.</p>
                <div className="intakeReview">
                  <div className="intakeProvenance">
                    <span><small>SOURCE</small><strong>{intakeDraft.source_name}</strong></span>
                    <span><small>EXTRACTOR</small><strong>OpenAI · {intakeDraft.extraction_model}</strong></span>
                    <span><small>STATUS</small><strong className={intakeDraft.validation_warnings.length ? "warningText" : "safeText"}>{intakeDraft.validation_warnings.length ? "GAPS FOUND" : "REVIEW REQUIRED"}</strong></span>
                  </div>
                  {(intakeDraft.validation_warnings.length > 0 || intakeDraft.extraction.extraction_warnings.length > 0) && (
                    <div className="intakeWarnings">
                      <strong>Review before confirmation</strong>
                      <ul>{[...intakeDraft.validation_warnings, ...intakeDraft.extraction.extraction_warnings].map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul>
                    </div>
                  )}
                  <div className="intakeFields">
                    <label><span>Issuer</span><input value={intakeDraft.extraction.issuer} onChange={(event) => updateIntakeExtraction({ issuer: event.target.value })} /></label>
                    <label><span>Product name</span><input value={intakeDraft.extraction.product_name} onChange={(event) => updateIntakeExtraction({ product_name: event.target.value })} /></label>
                    <label><span>Affected models <em>comma separated</em></span><input value={intakeDraft.extraction.affected_models.join(", ")} onChange={(event) => updateIntakeExtraction({ affected_models: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} /></label>
                    <label><span>Lot ranges <em>for example B10–B12</em></span><input value={intakeDraft.extraction.affected_lot_ranges.map((item) => `${item.start}–${item.end}`).join(", ")} onChange={(event) => updateIntakeExtraction({ affected_lot_ranges: parseLotRanges(event.target.value) })} /></label>
                    <label className="wide"><span>Hazard</span><textarea value={intakeDraft.extraction.hazard} onChange={(event) => updateIntakeExtraction({ hazard: event.target.value })} /></label>
                    <label className="wide"><span>Required action</span><textarea value={intakeDraft.extraction.required_action} onChange={(event) => updateIntakeExtraction({ required_action: event.target.value })} /></label>
                    <label className="wide"><span>Remedy</span><input value={intakeDraft.extraction.remedy} onChange={(event) => updateIntakeExtraction({ remedy: event.target.value })} /></label>
                    <label><span>Contact phone</span><input value={intakeDraft.extraction.contact_phone} onChange={(event) => updateIntakeExtraction({ contact_phone: event.target.value })} /></label>
                    <label><span>Contact URL</span><input value={intakeDraft.extraction.contact_url} onChange={(event) => updateIntakeExtraction({ contact_url: event.target.value })} /></label>
                    <label><span>Effective date</span><input type="date" value={intakeDraft.extraction.effective_date} onChange={(event) => updateIntakeExtraction({ effective_date: event.target.value })} /></label>
                    <label><span>Source locale</span><select value={intakeDraft.extraction.supported_locales[0] ?? "en-US"} onChange={(event) => updateIntakeExtraction({ supported_locales: [event.target.value] })}><option value="en-US">English (US)</option><option value="es-US">Spanish (US)</option></select></label>
                  </div>
                </div>
                {intakeError && <p className="intakeError" role="alert">{intakeError}</p>}
                <div className="modalFoot intakeActions">
                  <span><Icon name="shield" /> AI drafts. A person confirms. FactLock still gates release.</span>
                  <div><button className="outlineButton" onClick={() => { setIntakeDraft(null); setIntakeState("idle"); setIntakeError(null); }}>Back</button><button className="primaryButton" onClick={confirmIntake} disabled={intakeState === "confirming"}>{intakeState === "confirming" ? "Confirming…" : "Confirm source contract"}</button></div>
                </div>
              </>
            ) : (
              <>
                <p className="modalIntro">Upload UTF-8 text, Markdown, or JSON up to 200 KB—or paste a notice. PDFs and images are deliberately rejected in this safe MVP.</p>
                <div className="intakeCompose">
                  <label className="fileDrop">
                    <Icon name="cube" />
                    <strong>Choose a source file</strong>
                    <span>.txt, .md, or .json · max 200 KB</span>
                    <input type="file" accept=".txt,.md,.json,text/plain,text/markdown,application/json" onChange={(event) => void selectIntakeFile(event.target.files?.[0])} />
                  </label>
                  <div className="pasteDivider"><span>OR PASTE SOURCE TEXT</span></div>
                  <label className="sourceEditor"><span>Source notice</span><textarea aria-label="Source notice" value={intakeText} onChange={(event) => { setIntakeText(event.target.value); setIntakeSourceName("pasted-recall.md"); setIntakeError(null); setIntakeState("idle"); }} placeholder="Paste the complete, approved recall notice here…" /></label>
                  {intakeSourceName !== "pasted-recall.md" && <p className="selectedFile">Selected: <strong>{intakeSourceName}</strong></p>}
                  {intakeError && <p className="intakeError" role="alert">{intakeError}</p>}
                  <div className="intakeGuard"><Icon name="shield" /><p><strong>Review-first by design.</strong> Extraction creates a draft only. It cannot replace the demo, generate media, or release an asset.</p></div>
                </div>
                <div className="modalFoot intakeActions">
                  <span>{intakeText.length.toLocaleString()} characters</span>
                  <button className="primaryButton" onClick={extractIntake} disabled={intakeState === "extracting" || intakeText.trim().length < 80}>{intakeState === "extracting" ? "Extracting structured facts…" : "Extract fact contract"}</button>
                </div>
              </>
            )}
          </section>
        </div>
      )}

      {showContract && (
        <div className="modalBackdrop" onMouseDown={() => { setShowContract(false); setActiveNavigation("workspace"); }}>
          <section className="contractModal" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modalHead">
              <div><span className="bannerIcon"><Icon name="lock" /></span><div><small>{workspaceCase === "cpsc" ? "PUBLIC SOURCE · CPSC 26-333" : `FACT CONTRACT · SOURCE V${sourceVersion}.0`}</small><h2>Release invariants</h2></div></div>
              <button aria-label="Close policy" onClick={() => { setShowContract(false); setActiveNavigation("workspace"); }}>×</button>
            </div>
            <p className="modalIntro">{workspaceCase === "cpsc" ? "These values were compiled from the public CPSC notice. They remain non-releaseable until an accountable operator confirms them." : "These values are human-confirmed and blocking. Creative presentation may change; these facts may not."}</p>
            <div className="contractTable">
              {displayContract.map((row, index) => (
                <div key={row[2]}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div><small>{row[0]}</small><strong>{workspaceCase === "demo" && sourceVersion === 2 && row[2] === "remedy.approved" ? "Full refund" : row[1]}</strong></div>
                  <code>{row[2]}</code>
                  <em>{workspaceCase === "cpsc" ? "UNCONFIRMED" : "BLOCKING"}</em>
                </div>
              ))}
            </div>
            <div className="modalFoot"><span><Icon name="shield" /> Contract hash <code>{workspaceCase === "cpsc" && realCase ? `${realCase.contract.contract_sha256.slice(0, 8)}…${realCase.contract.contract_sha256.slice(-4)}` : contractHash ? `${contractHash.slice(0, 8)}…${contractHash.slice(-4)}` : "loading…"}</code></span>{workspaceCase === "cpsc" && realCase ? <a className="sourceButton compactSourceButton" href={realCase.source_url} target="_blank" rel="noreferrer">Verify at CPSC.gov ↗</a> : <button className="primaryButton" onClick={() => { setShowContract(false); setActiveNavigation("workspace"); }}>Contract confirmed</button>}</div>
          </section>
        </div>
      )}

      {showGeneration && (
        <div className="modalBackdrop" onMouseDown={() => { setShowGeneration(false); setJudgeMode(false); setActiveNavigation("workspace"); }}>
          <section className={`contractModal generationModal ${judgeMode ? "judgeModeActive" : ""}`} onMouseDown={(event) => event.stopPropagation()}>
            <div className="modalHead">
              <div><span className="bannerIcon"><Icon name="cube" /></span><div><small>{judgeMode ? "60-SECOND JUDGE MODE · REAL PROVIDER PROOF" : workspaceCase === "cpsc" ? "UNAFFILIATED PUBLIC-SOURCE PROOF" : "LIVE PROVIDER PROOF"}</small><h2>{judgeMode ? "The mutation RecallCast refused to release" : workspaceCase === "cpsc" ? "Voice + visual safety draft" : "Verified media package"}</h2></div></div>
              <button aria-label="Close verified media package" onClick={() => { setShowGeneration(false); setJudgeMode(false); setActiveNavigation("workspace"); }}>×</button>
            </div>
            {generationState === "generated" && evidencePackage ? (
              <div className="generationBody">
                <div className="packageMedia">
                  {workspaceCase === "cpsc" && evidencePackage.artifacts.some((item) => item.kind === "consumer_card") && (
                    <div className="mediaKitTabs" role="tablist" aria-label="Public safety media kit">
                      <button role="tab" aria-selected={mediaKitView === "consumer"} className={mediaKitView === "consumer" ? "active" : ""} onClick={() => setMediaKitView("consumer")}>Consumer alert</button>
                      <button role="tab" aria-selected={mediaKitView === "eligibility"} className={mediaKitView === "eligibility" ? "active" : ""} onClick={() => setMediaKitView("eligibility")}>Eligibility companion</button>
                    </div>
                  )}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={(mediaKitView === "consumer" ? evidencePackage.artifacts.find((item) => item.kind === "consumer_card") : evidencePackage.artifacts.find((item) => item.kind === "social_card"))?.preview_url ?? evidencePackage.artifacts.find((item) => item.kind === "social_card")?.preview_url ?? ""}
                    alt={workspaceCase === "cpsc" ? mediaKitView === "consumer" ? "Consumer-facing public-source recall alert" : "Exact-model eligibility companion card" : "Fact-locked generated recall social card"}
                  />
                  {workspaceCase === "cpsc" && <div className="mediaKitCaption"><small>{mediaKitView === "consumer" ? "PUBLIC ALERT" : "ELIGIBILITY COMPANION"}</small><strong>{mediaKitView === "consumer" ? "Simple action-first communication" : "All 23 exact models remain visible and blocking"}</strong><span>These two assets are distributed and reviewed as one fact-locked media kit.</span></div>}
                  <audio
                    controls
                    src={(evidencePackage.artifacts.find((item) => item.kind === "narration" && item.accepted) ?? evidencePackage.artifacts.filter((item) => item.kind === "narration").at(-1))?.preview_url ?? undefined}
                  />
                  <small>{evidencePackage.ai_voice_disclosure}</small>
                </div>
                <div className="generationProof">
                  <span className={evidencePackage.report.decision === "pass" ? "passPill" : "failPill"}>
                    {evidencePackage.report.decision === "pass" ? <Icon name="check" /> : "!"} {evidencePackage.report.decision === "pass" ? `${evidencePackage.report.passed_count} CHECKS PASS` : `${evidencePackage.report.blocking_failure_count} BLOCKING`}
                  </span>
                  {workspaceCase === "cpsc" && (
                    <div className="winningMetrics">
                      <div><strong>23</strong><span>EXACT MODELS</span></div>
                      <div><strong>{evidencePackage.report.passed_count}</strong><span>CHECKS PASS</span></div>
                      <div><strong>{evidencePackage.attempts?.filter((item) => !item.accepted).length ?? 0}</strong><span>MUTATION CAUGHT</span></div>
                      <div><strong>{evidencePackage.attempts?.length ?? 1}</strong><span>LINKED RUNS</span></div>
                    </div>
                  )}
                  {workspaceCase === "cpsc" && evidencePackage.attempts?.some((item) => !item.accepted) && evidencePackage.attempts.some((item) => item.accepted) && (
                    <div className="attemptDiff">
                      <div className="attemptDiffHead"><span>THE WINNING MOMENT</span><strong>One missing digit was enough to stop release</strong><p>RecallCast independently heard the generated audio, rejected the mutation, and linked a contract-derived correction to its failed parent.</p></div>
                      <div className="attemptCompare">
                        <article className="rejectedAttempt">
                          <small>ATTEMPT 1 · QUARANTINED</small>
                          <strong>{observedSerial(evidencePackage.attempts.find((item) => !item.accepted)?.observed_transcript ?? "")}</strong>
                          <span>Expected VF54399999</span>
                          <p>{evidencePackage.attempts.find((item) => !item.accepted)?.report.findings.find((item) => item.blocking_failure)?.reason ?? "A blocking identifier mutation was detected."}</p>
                          <code>RUN {evidencePackage.attempts.find((item) => !item.accepted)?.run_id?.slice(0, 13)}…</code>
                          <audio aria-label="Rejected narration attempt" controls src={evidencePackage.artifacts.find((item) => item.kind === "narration" && !item.accepted)?.preview_url ?? undefined} />
                        </article>
                        <div className="correctionArrow"><span>→</span><small>CONTRACT-DERIVED<br />CORRECTION</small></div>
                        <article className="acceptedAttempt">
                          <small>ATTEMPT 2 · VERIFIED</small>
                          <strong>{observedSerial(evidencePackage.attempts.find((item) => item.accepted)?.observed_transcript ?? "")}</strong>
                          <span>Exact serial preserved</span>
                          <p>Character-by-character enunciation passed the public-case audio policy with no blocking failures.</p>
                          <code>PARENT {evidencePackage.attempts.find((item) => item.accepted)?.parent_run_id?.slice(0, 13)}…</code>
                          <audio aria-label="Corrected narration attempt" controls src={evidencePackage.artifacts.find((item) => item.kind === "narration" && item.accepted)?.preview_url ?? undefined} />
                        </article>
                      </div>
                    </div>
                  )}
                  <h3>{evidencePackage.report.decision === "pass" ? workspaceCase === "cpsc" ? "The draft survived independent media checks" : "Observed media matches the contract" : "Package quarantined by FactLock"}</h3>
                  <p>{evidencePackage.report.decision === "pass" ? workspaceCase === "cpsc" ? "The final card was read for all 23 models and the AI voice was reverse-transcribed for the serial range and safety instructions. This remains an unaffiliated draft requiring human review." : "The card was independently read and the generated MP3 was reverse-transcribed. Each modality passed its own required facts." : "At least one required fact was missing or changed in independently extracted evidence. Nothing can be released."}</p>
                  <div className="evidenceTwin">
                    <div><small>OBSERVED NARRATION</small><p>{evidencePackage.observed_transcript}</p></div>
                    <div><small>OBSERVED VISUAL TEXT</small><p>{evidencePackage.observed_ocr}</p></div>
                  </div>
                  <div className="liveEvents">
                    {evidencePackage.events.map((event) => (
                      <div key={`${event.stage}-${event.attempt}`}>
                        {event.status === "blocked" ? <b>!</b> : <Icon name="check" />}
                        <span><strong>{event.label}</strong><small>{event.provider} · {event.model}</small></span>
                        <code>{event.attempt > 1 ? `TRY ${event.attempt} · ` : ""}{event.latency_ms} ms</code>
                      </div>
                    ))}
                  </div>
                  {evidencePackage.artifacts.filter((item) => item.kind === "narration").length > 1 && (
                    <p className="retryProof">The rejected narration was preserved. The accepted retry is parent-linked to run {evidencePackage.artifacts.find((item) => item.kind === "narration" && item.accepted)?.parent_run_id?.slice(0, 8)}…</p>
                  )}
                  {workspaceCase === "cpsc" && evidencePackage.report.decision === "pass" && evidencePackage.status === "needs_review" && (
                    <div className="realReviewGate" role="group" aria-label="Human release decision">
                      <div><small>FINAL HUMAN RELEASE GATE</small><strong>Approve or reject this exact evidence package</strong><p>The decision is terminal and binds your identity and note to the package, contract, artifact hashes, and FactLock report in B2.</p></div>
                      <label><span>Reviewer name</span><input aria-label="Reviewer name" value={realReviewReviewer} onChange={(event) => setRealReviewReviewer(event.target.value)} /></label>
                      <label><span>Review rationale</span><textarea aria-label="Review rationale" value={realReviewRationale} onChange={(event) => setRealReviewRationale(event.target.value)} placeholder="Record what you checked and why this package should or should not be released…" /></label>
                      <label className="reviewAttestation"><input type="checkbox" checked={realReviewAttested} onChange={(event) => setRealReviewAttested(event.target.checked)} /><span>I accept accountability for approving this unaffiliated demo draft. This is not CPSC or Electrolux Group approval.</span></label>
                      <div className="realReviewActions">
                        <button className="outlineButton rejectButton" onClick={() => void submitRealPackageReview("rejected")} disabled={realReviewPending || realReviewReviewer.trim().length < 2 || realReviewRationale.trim().length < 8}>Reject draft</button>
                        <button className="primaryButton" onClick={() => void submitRealPackageReview("approved")} disabled={realReviewPending || !realReviewAttested || realReviewReviewer.trim().length < 2 || realReviewRationale.trim().length < 8}><Icon name="check" />{realReviewPending ? "Recording decision…" : "Approve demo release"}</button>
                      </div>
                      {realCaseError && <p className="intakeError realCaseError" role="alert">{realCaseError}</p>}
                    </div>
                  )}
                  {workspaceCase === "cpsc" && evidencePackage.review && (
                    <div className={`realReviewDecision ${evidencePackage.review.decision}`}>
                      <small>TERMINAL HUMAN DECISION</small>
                      <strong>{evidencePackage.review.decision === "approved" ? "APPROVED FOR DEMO RELEASE" : "REJECTED — DO NOT RELEASE"}</strong>
                      <p>{evidencePackage.review.rationale}</p>
                      <span>Recorded by {evidencePackage.review.reviewer} · {new Date(evidencePackage.review.reviewed_at).toLocaleString()}</span>
                      <code>Report {evidencePackage.review.validation_report_sha256.slice(0, 12)}… · {evidencePackage.review.artifact_sha256s.length} artifact hashes bound</code>
                    </div>
                  )}
                  <dl>
                    <div><dt>Package</dt><dd>{evidencePackage.package_id}</dd></div>
                    <div><dt>Validator</dt><dd>{evidencePackage.report.validator_version}</dd></div>
                    <div><dt>Contract</dt><dd>{evidencePackage.contract_sha256}</dd></div>
                    <div><dt>Storage</dt><dd>{evidencePackage.artifacts.length} assets + evidence in private Backblaze B2</dd></div>
                  </dl>
                </div>
              </div>
            ) : (
              <div className="generationError">
                <strong>Live generation could not complete.</strong>
                <p>Confirm the API is running with OpenAI and B2 credentials, then retry.</p>
                <button className="primaryButton" onClick={() => { setShowGeneration(false); void (workspaceCase === "cpsc" ? generateRealCasePackage() : generatePackage()); }}>Retry package</button>
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
