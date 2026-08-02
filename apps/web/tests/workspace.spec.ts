import { expect, test, type Page } from "@playwright/test";

const extraction = {
  issuer: "Harbor Home Safety",
  product_name: "Harbor Community Breeze Fan",
  affected_models: ["HCB-20"],
  affected_lot_ranges: [{ start: "C10", end: "C18" }],
  hazard: "The motor can overheat and cause a fire.",
  required_action: "Stop using the fan and unplug it immediately.",
  remedy: "Consumers will receive a full refund.",
  contact_phone: "1-800-555-0199",
  contact_url: "https://example.invalid/harbor-recall",
  effective_date: "2026-08-01",
  supported_locales: ["en-US"],
  extraction_warnings: [],
};

const pixelImage = "data:image/gif;base64,R0lGODlhAQABAAAAACw=";
const publicAttempts = [
  {
    attempt: 1,
    script: "Serial range VF52200000 through VF54399999.",
    observed_transcript: "Serial range VF5220000000 through VF5439999.",
    accepted: false,
    run_id: "run_rejected_browser_test",
    parent_run_id: null,
    report: {
      decision: "quarantine",
      validator_version: "factlock-deterministic-v3",
      passed_count: 6,
      blocking_failure_count: 1,
      findings: [{ fact_id: "product.affected_lots", blocking_failure: true, reason: "The complete serial-range bounds were not preserved." }],
    },
  },
  {
    attempt: 2,
    script: "The ending serial is spelled character by character.",
    observed_transcript: "It ends with letter V, letter F, digit 5, digit 4, digit 3, digit 9, digit 9, digit 9, digit 9, digit 9.",
    accepted: true,
    run_id: "run_corrected_browser_test",
    parent_run_id: "run_rejected_browser_test",
    report: { decision: "pass", validator_version: "factlock-deterministic-v3", passed_count: 7, blocking_failure_count: 0, findings: [] },
  },
];

const publicArtifacts = [
  { kind: "consumer_card", key: "consumer-alert.png", sha256: "1".repeat(64), provider: "RecallCast", model: "consumer-alert-v1", manifest_verified: true, run_id: null, parent_run_id: null, attempt: 1, accepted: true, preview_url: pixelImage },
  { kind: "social_card", key: "eligibility-card.png", sha256: "2".repeat(64), provider: "RecallCast", model: "social-card-v4", manifest_verified: true, run_id: null, parent_run_id: null, attempt: 1, accepted: true, preview_url: pixelImage },
  { kind: "narration", key: "rejected.mp3", sha256: "3".repeat(64), provider: "openai-tts", model: "gpt-4o-mini-tts", manifest_verified: true, run_id: "run_rejected_browser_test", parent_run_id: null, attempt: 1, accepted: false, preview_url: null },
  { kind: "narration", key: "corrected.mp3", sha256: "4".repeat(64), provider: "openai-tts", model: "gpt-4o-mini-tts", manifest_verified: true, run_id: "run_corrected_browser_test", parent_run_id: "run_rejected_browser_test", attempt: 2, accepted: true, preview_url: null },
];

async function mockMutableFlows(page: Page) {
  let publicCaseConfirmed = false;
  let publicPackageStatus: "needs_review" | "approved" | "rejected" | null = null;
  let publicPackageReview: Record<string, unknown> | null = null;
  await page.route("**/api/cases/cpsc-26-333", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      case_type: "public_source",
      source_authority: "U.S. Consumer Product Safety Commission",
      source_url: "https://www.cpsc.gov/Recalls/2026/Electrolux-Group-Recalls-Frigidaire-Gas-Ranges-Due-to-Burn-Hazard",
      recall_number: "26-333",
      contract: {
        recall_id: "rc_cpsc_26_333",
        version: 1,
        contract_sha256: "d".repeat(64),
        issuer: "Electrolux Group",
        product_name: "Frigidaire Gas Ranges",
        affected_models: Array.from({ length: 23 }, (_, index) => `MODEL-${index + 1}`),
        affected_lot_ranges: [{ start: "VF52200000", end: "VF54399999" }],
        hazard: "Delayed ignition poses a burn hazard.",
        required_action: "Stop using ovens in recalled ranges immediately.",
        remedy: "Free repair.",
        contact: { phone: "866-291-7633", url: "https://www.gasovenburnerrecall.com" },
        effective_date: "2026-03-19",
        human_confirmed: publicCaseConfirmed,
      },
      stats: { units_us: 174800, reported_incidents: 62, reported_injuries: 30, affected_models: 23 },
      release_status: !publicCaseConfirmed ? "operator_review_required" : publicPackageStatus === "approved" ? "approved_for_demo_release" : publicPackageStatus === "rejected" ? "rejected_by_reviewer" : publicPackageStatus === "needs_review" ? "human_review_required" : "media_draft_enabled",
      reviewer: publicCaseConfirmed ? "AL · Local demo operator" : null,
      package: publicPackageStatus ? { package_id: "pkg_public_browser_test", status: publicPackageStatus, review: publicPackageReview } : null,
      disclaimer: "Public CPSC source; RecallCast is not affiliated with CPSC or Electrolux Group.",
    }),
  }));
  await page.route("**/api/cases/cpsc-26-333/bootstrap", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ status: "stored", recall_id: "rc_cpsc_26_333", objects: [] }),
  }));
  await page.route("**/api/cases/cpsc-26-333/confirm", (route) => {
    publicCaseConfirmed = true;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "confirmed_for_demo_draft", reviewer: "AL · Local demo operator", contract: { human_confirmed: true }, objects: [] }),
    });
  });
  await page.route("**/api/cases/cpsc-26-333/packages/generate", (route) => {
    publicPackageStatus ??= "needs_review";
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
      package_id: "pkg_public_browser_test",
      recall_id: "rc_cpsc_26_333",
      locale: "en-US",
      status: publicPackageStatus,
      contract_sha256: "e".repeat(64),
      observed_transcript: "Serial range and public safety instructions observed.",
      observed_ocr: "All 23 models and public safety instructions observed.",
      ai_voice_disclosure: "The narration is AI-generated and is not a human voice.",
      report: { decision: "pass", validator_version: "factlock-deterministic-v3", passed_count: 14, blocking_failure_count: 0, findings: [] },
      events: [{ stage: "validate", label: "Per-modality FactLock checks complete", status: "completed", provider: "RecallCast", model: "factlock-deterministic-v3", latency_ms: 1, attempt: 1 }],
      artifacts: publicArtifacts,
      attempts: publicAttempts,
      review: publicPackageReview,
      }),
    });
  });
  await page.route("**/api/cases/cpsc-26-333/packages/*/review", async (route) => {
    const request = route.request().postDataJSON() as { decision: "approved" | "rejected"; reviewer: string; rationale: string };
    publicPackageStatus = request.decision;
    publicPackageReview = {
      schema_version: "recallcast-package-review-v1",
      package_id: "pkg_public_browser_test",
      recall_id: "rc_cpsc_26_333",
      decision: request.decision,
      status: request.decision,
      reviewer: request.reviewer,
      rationale: request.rationale,
      reviewed_at: "2026-08-01T18:00:00Z",
      contract_sha256: "e".repeat(64),
      validation_report_sha256: "f".repeat(64),
      artifact_sha256s: ["a".repeat(64), "b".repeat(64)],
      attestation: "Human decision recorded.",
    };
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        package_id: "pkg_public_browser_test",
        recall_id: "rc_cpsc_26_333",
        locale: "en-US",
        status: publicPackageStatus,
        contract_sha256: "e".repeat(64),
        observed_transcript: "Serial range and public safety instructions observed.",
        observed_ocr: "All 23 models and public safety instructions observed.",
        ai_voice_disclosure: "The narration is AI-generated and is not a human voice.",
        report: { decision: "pass", validator_version: "factlock-deterministic-v3", passed_count: 14, blocking_failure_count: 0, findings: [] },
        events: [{ stage: "human_review", label: "Human release decision", status: request.decision === "approved" ? "completed" : "blocked", provider: request.reviewer, model: "manual-release-gate-v1", latency_ms: 1, attempt: 1 }],
        artifacts: publicArtifacts,
        attempts: publicAttempts,
        review: publicPackageReview,
      }),
    });
  });
  await page.route("**/api/packages/generate", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      package_id: "pkg_browser_test",
      recall_id: "rc_demo_001",
      locale: "en-US",
      status: "needs_review",
      contract_sha256: "b".repeat(64),
      observed_transcript: "All narration facts observed.",
      observed_ocr: "All visual facts observed.",
      ai_voice_disclosure: "The narration is AI-generated and is not a human voice.",
      report: { decision: "pass", validator_version: "factlock-test", passed_count: 15, blocking_failure_count: 0, findings: [] },
      events: [{ stage: "store", label: "Evidence persisted", status: "completed", provider: "Backblaze B2", model: "test", latency_ms: 1, attempt: 1 }],
      artifacts: [],
    }),
  }));
  await page.route("**/api/intake/extract", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      draft_id: "draft_browser_test",
      status: "needs_review",
      source_name: "harbor-recall.md",
      source_sha256: "a".repeat(64),
      extraction_model: "gpt-5.6-sol",
      extraction,
      validation_warnings: [],
      storage_objects: [{ key: "recallcast/intake/draft_browser_test/source/harbor-recall.md" }],
    }),
  }));
  await page.route("**/api/intake/confirm", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      draft_id: "draft_browser_test",
      status: "confirmed",
      contract: { contract_sha256: "c".repeat(64) },
      policy_pack: {
        policy_id: "policy_browser_test",
        template: "stop-use-product-recall-v1",
        status: "draft",
        draft_id: "draft_browser_test",
        contract_sha256: "c".repeat(64),
        policy_sha256: "d".repeat(64),
        exact_identifiers: ["HCB-20"],
        range_endpoints: ["C10", "C18"],
        concept_groups: [
          { field: "hazard", canonical_value: extraction.hazard, required_concepts: ["motor", "overheat", "fire"] },
          { field: "required_action", canonical_value: extraction.required_action, required_concepts: ["stop", "fan", "unplug", "immediately"] },
          { field: "remedy", canonical_value: extraction.remedy, required_concepts: ["full", "refund"] },
        ],
        require_phone: true,
        require_url_on_visual: true,
        require_effective_date: true,
        reviewer: null,
      },
      storage_objects: [{ key: "recallcast/intake/draft_browser_test/confirmed-contract.json" }],
    }),
  }));
  await page.route("**/api/intake/*/policy/activate", async (route) => {
    const request = route.request().postDataJSON();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        policy_id: "policy_browser_test",
        template: "stop-use-product-recall-v1",
        status: "active",
        draft_id: "draft_browser_test",
        contract_sha256: "c".repeat(64),
        policy_sha256: "e".repeat(64),
        exact_identifiers: ["HCB-20"],
        range_endpoints: ["C10", "C18"],
        concept_groups: request.concept_groups,
        require_phone: true,
        require_url_on_visual: true,
        require_effective_date: true,
        reviewer: request.reviewer,
      }),
    });
  });
  await page.route("**/api/intake/*/packages/generate", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      package_id: "pkg_custom_browser_test",
      recall_id: "rc_harbor_browser",
      locale: "en-US",
      status: "needs_review",
      contract_sha256: "c".repeat(64),
      policy_sha256: "e".repeat(64),
      observed_transcript: "HCB-20 C10 C18 motor overheat fire stop fan unplug immediately full refund 1-800-555-0199 August 1, 2026",
      observed_ocr: "All locked facts observed.",
      ai_voice_disclosure: "The narration is AI-generated and is not a human voice.",
      report: {
        decision: "pass", validator_version: "factlock-deterministic-v3", passed_count: 14, blocking_failure_count: 0,
        findings: [{ fact_id: "product.affected_models", label: "Exact affected models", status: "pass", canonical_value: "HCB-20", evidence: "HCB-20", evidence_source: "transcript", reason: "Exact", blocking_failure: false }],
      },
      events: [],
      artifacts: [{ kind: "social_card", key: "custom-card.png", sha256: "f".repeat(64), provider: "RecallCast", model: "social-card-v4", manifest_verified: true, run_id: null, parent_run_id: null, attempt: 1, accepted: true, preview_url: pixelImage }],
      attempts: [],
      review: null,
    }),
  }));
}

test("desktop navigation, policy, package, and upload-confirm flow are operable", async ({ page }) => {
  await mockMutableFlows(page);
  await page.goto("/");

  const desktopNav = page.locator(".sidebar nav");
  await expect(desktopNav.getByRole("button", { name: "Workspace" })).toBeVisible();

  await desktopNav.getByRole("button", { name: "Lineage" }).click();
  await expect(desktopNav.getByRole("button", { name: "Lineage" })).toHaveClass(/active/);
  await expect(page.locator("#pipeline-evidence")).toBeInViewport();

  await desktopNav.getByRole("button", { name: "Policy" }).click();
  await expect(page.getByRole("heading", { name: "Release invariants" })).toBeVisible();
  await page.getByRole("button", { name: "Close policy" }).click();

  await desktopNav.getByRole("button", { name: /Media packages/ }).click();
  await expect(page.getByRole("heading", { name: "Verified media package" })).toBeVisible();
  await expect(page.getByText("Observed media matches the contract")).toBeVisible();
  await page.getByRole("button", { name: "Close verified media package" }).click();

  await desktopNav.getByRole("button", { name: /Import source/ }).click();
  await expect(page.getByRole("heading", { name: "Import a recall source" })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: "harbor-recall.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("Harbor Home Safety recalls Harbor Community Breeze Fan model HCB-20, lots C10 through C18. The motor can overheat and cause a fire. Stop using the fan and unplug it immediately. A full refund is available. Call 1-800-555-0199."),
  });
  await expect(page.getByText("Selected:")).toBeVisible();
  await page.getByRole("button", { name: "Extract fact contract" }).click();
  await expect(page.locator('input[value="Harbor Community Breeze Fan"]')).toBeVisible();
  await page.getByRole("button", { name: "Confirm source contract" }).click();
  await expect(page.getByText("HUMAN-CONFIRMED SOURCE CONTRACT")).toBeVisible();
  await expect(page.getByRole("region", { name: "Policy Pack Builder" })).toBeVisible();
  await expect(page.getByText("HCB-20")).toBeVisible();
  await page.getByRole("checkbox", { name: /I verified these rules/ }).check();
  await page.getByRole("button", { name: "Activate deterministic policy" }).click();
  await expect(page.getByText("POLICY ACTIVE · GENERATION UNLOCKED")).toBeVisible();
  await page.getByRole("button", { name: "Build fact-locked media" }).click();
  await expect(page.getByText("FACTLOCK PASS")).toBeVisible();
  await expect(page.getByRole("heading", { name: "14 checks passed · 0 blocking" })).toBeVisible();
});

test("mobile navigation exposes every core area", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockMutableFlows(page);
  await page.goto("/");

  const mobileNav = page.getByRole("navigation", { name: "Mobile navigation" });
  await expect(mobileNav).toBeVisible();
  for (const label of ["Home", "Import", "Media", "Lineage", "Policy"]) {
    await expect(mobileNav.getByRole("button", { name: label })).toBeVisible();
  }

  await mobileNav.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("heading", { name: "Import a recall source" })).toBeVisible();
  await page.getByRole("button", { name: "Close import source" }).click();
  await mobileNav.getByRole("button", { name: "Policy" }).click();
  await expect(page.getByRole("heading", { name: "Release invariants" })).toBeVisible();
});

test("public CPSC case is attributed, acknowledged, and generates a checked draft", async ({ page }) => {
  await mockMutableFlows(page);
  await page.goto("/");
  await page.getByLabel("Recall case").selectOption("cpsc");

  await expect(page.getByRole("heading", { name: /Frigidaire/ })).toBeVisible();
  await expect(page.getByText("U.S. Consumer Product Safety Commission")).toBeVisible();
  await expect(page.getByText("174,800")).toBeVisible();
  await expect(page.getByText("CONFIRMATION REQUIRED")).toBeVisible();
  await expect(page.getByText("Operator acknowledgment required")).toBeVisible();
  await expect(page.getByRole("button", { name: /Confirm source to generate/ })).toBeDisabled();
  await expect(page.getByRole("link", { name: /Open official CPSC notice/ })).toHaveAttribute("href", /cpsc\.gov/);

  await page.getByRole("checkbox", { name: /I checked the official CPSC notice/ }).check();
  await page.getByRole("button", { name: "Acknowledge & enable generation" }).click();
  await expect(page.getByText("DRAFT GENERATION ENABLED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Build voice \+ visual draft/ }).last().click();
  await expect(page.getByRole("heading", { name: "Voice + visual safety draft" })).toBeVisible();
  await expect(page.getByText("The draft survived independent media checks")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Consumer alert" })).toBeVisible();
  await page.getByRole("tab", { name: "Eligibility companion" }).click();
  await expect(page.getByAltText("Exact-model eligibility companion card")).toBeVisible();
  await expect(page.locator(".rejectedAttempt")).toContainText("VF5439999");
  await expect(page.locator(".acceptedAttempt")).toContainText("VF54399999");
  await expect(page.getByRole("group", { name: "Human release decision" })).toBeVisible();
  await page.getByLabel("Review rationale").fill("I checked the source, final card, narration, and FactLock evidence.");
  await page.getByLabel(/I accept accountability/).check();
  await page.getByRole("button", { name: "Approve demo release" }).click();
  await expect(page.locator(".realReviewDecision").getByText("APPROVED FOR DEMO RELEASE", { exact: true })).toBeVisible();
  await expect(page.locator(".realReviewDecision")).toContainText("AL · Local demo operator");
});

test("public package proof remains usable on a compact mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 490, height: 641 });
  await mockMutableFlows(page);
  await page.goto("/");
  await page.getByLabel("Recall case").selectOption("cpsc");
  await page.getByRole("checkbox", { name: /I checked the official CPSC notice/ }).check();
  await page.getByRole("button", { name: "Acknowledge & enable generation" }).click();
  await page.getByRole("button", { name: /Build voice \+ visual draft/ }).last().click();

  await expect(page.getByRole("button", { name: "Close verified media package" })).toBeVisible();
  const card = page.getByAltText("Consumer-facing public-source recall alert");
  const audio = page.locator(".packageMedia > audio");
  await expect(card).toBeVisible();
  await expect(audio).toBeVisible();
  const cardBox = await card.boundingBox();
  const audioBox = await audio.boundingBox();
  expect(cardBox?.height).toBeLessThanOrEqual(270);
  expect(audioBox?.height).toBeGreaterThanOrEqual(52);
  expect(audioBox?.x).toBeGreaterThanOrEqual(0);
  expect((audioBox?.x ?? 0) + (audioBox?.width ?? 0)).toBeLessThanOrEqual(490);
  await page.getByLabel("Review rationale").fill("Editorial review requires changes before this draft can be released.");
  await page.getByRole("button", { name: "Reject draft" }).click();
  await expect(page.locator(".realReviewDecision").getByText("REJECTED — DO NOT RELEASE", { exact: true })).toBeVisible();
});

test("judge mode leads with the caught mutation and corrective lineage", async ({ page }) => {
  await mockMutableFlows(page);
  await page.goto("/");
  await page.getByLabel("Recall case").selectOption("cpsc");
  await page.getByRole("checkbox", { name: /I checked the official CPSC notice/ }).check();
  await page.getByRole("button", { name: "Acknowledge & enable generation" }).click();
  await page.getByRole("button", { name: "Run 60-second proof" }).click();

  await expect(page.getByRole("heading", { name: "The mutation RecallCast refused to release" })).toBeVisible();
  await expect(page.getByText("One missing digit was enough to stop release")).toBeVisible();
  await expect(page.locator(".rejectedAttempt")).toContainText("QUARANTINED");
  await expect(page.locator(".acceptedAttempt")).toContainText("VERIFIED");
  await expect(page.locator(".winningMetrics")).toContainText("MUTATION CAUGHT");
});
