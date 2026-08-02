# RecallCast implementation gap audit

This audit reconciles the original 1,752-line product specification with the
code and the official challenge requirements as of August 1, 2026.

## Outcome

The strongest submission is a **verified image + audio safety package**, not a
generic video generator. The official challenge accepts image, audio, and
multimodal workflows; an MP4 is not mandatory. RecallCast already demonstrates
two generated modalities through Genblaze, durable B2 orchestration, reverse
extraction, a fail-closed policy engine, corrective lineage, and human review.

The deadline risk is now distribution—not core engineering: a working public
URL, repository, and demo video still need owner accounts and publishing.

## Original “must build” reconciliation

| Capability | Status | Evidence / decision |
|---|---|---|
| Preloaded recall | Complete | Fictional source and typed contract |
| Arbitrary pasted/uploaded-source intake | Complete for text | `.txt`, `.md`, and `.json` up to 200 KB; PDF/image parsing remains deferred |
| Contract extraction and editing | Complete for intake | OpenAI schema-constrained draft, editable review, deterministic source grounding, explicit confirmation |
| Language selection | Complete | English and Spanish package selector |
| Channel selection | Partial | Final package is social card + MP3; video deferred |
| Script generation | Partial | Contract-bound localized scripts, not open-ended generation |
| Generative background | Complete | `gpt-image-2` through Genblaze, verified in B2 |
| TTS narration | Complete | `gpt-4o-mini-tts` through Genblaze |
| Deterministic composition | Complete | Unicode-safe 1080×1080 locked compositor |
| Reverse transcription | Complete | Final MP3 read with `gpt-transcribe` |
| Final-pixel OCR | Complete | Social card read with `gpt-5.6-sol` vision |
| Critical-fact validation | Complete | Per-source deterministic FactLock v3, including spoken serial normalization |
| Independent semantic validator | Deferred | Deterministic blocking checks are safer for this closed demo contract |
| Quarantine and corrective retry | Complete | One bounded, content-aware parent-linked retry |
| Second provider fallback | Deferred | Not required by Devpost; deterministic fallback remains in controlled demo |
| Human approval | Complete | Passing demo and public-case assets require explicit accountable approval |
| Human rejection | Complete | Public-case reviewer can terminally reject a FactLock-passing draft |
| Source update invalidation | Complete | Remedy update marks dependent assets stale |
| B2 evidence graph | Complete | Sources, assets, attempts, OCR, transcripts, reports, decisions, manifests |
| Live pipeline evidence | Partial | Actual provider/model/latency events returned after synchronous completion; no SSE |
| Standalone lineage explorer | Partial | Lineage is exposed in package proof and demo retry; no dedicated graph screen |
| Judge-facing guided proof | Complete | One click opens the real caught-mutation, correction, media-kit, B2, and review story |
| Public judge mode | Code complete | No login, but deployment URL is still missing |

## Acceptance criteria status

### Strong and demonstrated

- CPSC recall 26-333 is available as a distinctly labeled real public-source
  case with 23 models, a serial range, source attribution, B2 evidence, and no
  implied affiliation. Generation stays disabled until operator confirmation;
  the assigned serial policy then validates voice and final-pixel evidence.
- Fictional English and Spanish image/audio packages and one English
  public-source draft are precomputed in private B2.
- The fictional packages pass 15 checks; the public-source package passes its
  14 policy-specific audio and visual checks and still requires human review.
- Two media modalities use real Genblaze pipelines.
- Provider and model identifiers, latency, hashes, and verification appear in
  the returned package and UI.
- A real failed narration and its passing corrective child are durable and
  parent-linked.
- The rejected and accepted audio attempts are playable side-by-side with the
  exact serial diff and provider run lineage visible in Judge Mode.
- Consumer communication and identifier eligibility are separate companion
  assets within one reviewable package.
- A named reviewer can approve or reject the public package; B2 retains a
  terminal decision bound to package, contract, validation, and artifact hashes.
- Controlled identifier mutation and action weakening always quarantine.
- The UI demonstrates approval and source-update invalidation.
- Paid force-regeneration paths fail closed behind an admin token; cache misses
  are serialized and ordinary requests are idempotent.
- API tests, TypeScript checks, and the Next.js production build pass.
- Desktop and mobile navigation, policy/package modals, file upload, extraction
  review, and contract confirmation pass browser-level Playwright tests.

### Remaining launch blockers

1. Rotate the Backblaze credential exposed during setup and replace it with a
   bucket-restricted application key.
2. Initialize and publish the repository; select a project license.
3. Deploy both containers and set final CORS/origin values.
4. Test the deployed URL in a private browser on desktop and mobile.
5. Record the public demo video and complete the Devpost form.
6. Validate a clean-clone install. Docker Compose syntax is valid, but the
   local image build could not be completed because Docker Desktop stalled
   fetching uncached base images.

## Deliberate non-goals for this submission

- MP4 composition and captions
- PDF/image recall uploads
- Additional custom templates beyond the shipped English stop-use Policy Pack
- Automatic policy activation or media generation without reviewer attestation
- Certified translation
- Automated publishing
- Enterprise authentication or roles
- A model-based score that could override deterministic safety failures

These are product-roadmap items, not hidden claims. Keeping them out makes the
demo more reliable and the novelty easier to understand.
