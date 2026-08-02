# RecallCast product strategy

## Executive assessment

RecallCast is a strong hackathon idea because the value is in the exact area
the challenge emphasizes: orchestration, retries, evaluation, storage, and
proof—not a thin interface around a media model.

The concept becomes more defensible when positioned as a **safety compiler**
rather than a recall-media generator:

> RecallCast compiles one approved safety source into accessible channel
> variants and produces release evidence that the invariants survived.

The generated media is the visible output. The contract, validation graph,
lineage, and update invalidation are the product.

## Current strengths

1. **A painful, legible problem.** A changed model number or weakened action is
   instantly understandable to judges.
2. **B2 is structurally necessary.** The system needs durable versions,
   rejected outputs, evidence, manifests, and dependency history.
3. **Genblaze has real responsibility.** It coordinates real image and audio
   generation, B2 transfer, verified manifests, and parent-linked retry
   provenance; RecallCast owns reverse extraction and evaluation.
4. **The demo has conflict.** A plausible but dangerous asset is caught,
   quarantined, corrected, and traced.
5. **The scope is controlled.** Fictional data, two languages, three channels,
   and no automatic publication are credible for a four-day build.

## Where differentiation can be sharper

### 1. Use a typed invariant graph, not a fact checklist

Facts should encode dependencies and policy:

- `NG-110` is required in every visual identification card.
- “Stop using” must coexist with “unplug” and immediacy.
- A remedy change invalidates every consumer-facing asset.
- A phone-only audio asset may omit the URL, but a social card may not.

This makes FactLock a policy engine with explainable invalidation, not another
LLM fact checker.

### 2. Add a dual-artifact proof

For each asset, save:

- what was intended: the approved script and overlay manifest;
- what was observed: transcript, OCR, and media metadata.

Pass only when intended and observed evidence independently conform to the same
contract. This closes the gap where a correct script is paired with an
incorrect render or narration.

### 3. Make fail-closed behavior visible

The most novel user experience is not a confidence score. It is:

- exact blocking reason;
- canonical fact;
- observed evidence;
- affected channel;
- retry correction;
- lineage to the failed parent.

“We have no transcript” must be a red blocked state, not a low score.

### 4. Expand policy packs after the hackathon

The horizontal product is “fact-locked regulated media.” Recall notices are
the first policy family. The MVP now includes a bounded Policy Pack Builder
for English stop-use recalls: exact identifiers and ranges are auto-locked,
reviewers confirm source-grounded hazard/action/remedy concepts, and activation
is hash-bound and persisted before generation. Later packs could cover other
recall action types, medication instructions, financial disclosures, emergency
alerts, or equipment safety procedures. Each needs an explicit deterministic
template; a language model must never invent release rules at runtime.

### 5. Prove comprehension, not only fidelity

The best post-MVP extension is a comprehension check: generate three simple
questions from the contract and evaluate whether a viewer can identify the
affected product, required action, and remedy. Fidelity answers “did we
preserve the source?” Comprehension answers “will the message work?”

## Novelty claim

Avoid claiming that provenance, recall management, translation, or media
generation is individually new. The defensible combination is:

> Contract-driven, closed-world conformance testing for regenerated
> multimodal safety communications, with reverse extraction, fail-closed
> release policy, parent-linked corrective retries, and dependency-based
> invalidation.

## Product value

### User value

- Shorter time from approved notice to accessible channel package
- Less manual side-by-side checking
- One review surface for transcript, visual text, and locked facts
- Immediate knowledge of which assets became stale after a source change

### Business value

- Reduced rework across safety, localization, and communications teams
- A reusable audit package per released asset
- Faster multilingual response without removing human authority
- A path to enterprise retention, roles, approval policies, and integrations

### Hackathon value

- Clear “before and after” story in under three minutes
- Visible multiple-modality pipeline
- Content-aware corrective retry
- B2 as a versioned evidence store
- Genblaze provenance and retry lineage shown in-product

## Highest-risk assumptions

1. **Buyer urgency:** recall teams may have low event frequency. Validate
   willingness to pay per incident and the broader regulated-media wedge.
2. **Liability posture:** customers will demand clear responsibility and may
   require deterministic templates for critical text.
3. **Spanish evaluation quality:** deterministic glossaries and human review
   are required; do not claim certified translation.
4. **OCR/transcription reliability:** a missing extractor must block release,
   and deterministic overlay metadata should supplement—but never impersonate—
   observed OCR.
5. **Provider latency during judging:** preload one complete B2 package and
   keep live validation and deterministic retry paths available.

## Recommended three-minute narrative

1. Load the fictional approved notice and confirm typed invariants.
2. Generate/show English and Spanish assets.
3. Select the plausible “use only when supervised” version.
4. Show FactLock’s exact blocking evidence and quarantine.
5. Retry with a contract-derived correction and show the parent-linked output.
6. Approve it, then change the remedy and show the asset become stale.
7. End on the B2 evidence graph and verified Genblaze manifest.

The line to repeat is:

> Generation is easy. Proving that regenerated safety media stayed true is the
> product.

## Agentic architecture decision

RecallCast uses a **bounded agentic workflow**, not a general autonomous agent:

- Genblaze orchestrates provider steps, durable assets, manifests, and
  parent-linked corrective runs.
- OpenAI models generate narration/backgrounds and independently observe the
  resulting audio and pixels.
- FactLock deterministically selects pass, quarantine, or one corrective retry.
- A human owns the terminal approve/reject transition.

The project does not currently use LangGraph. There is no open-ended planning,
dynamic tool selection, or conversational memory in the safety-critical path.
Adding an agent framework solely for the label would make the release policy
harder to explain and test. A graph runtime becomes useful later for resumable
multi-team review tasks, policy-pack authoring, and long-running integrations;
it should not replace deterministic release gates.
