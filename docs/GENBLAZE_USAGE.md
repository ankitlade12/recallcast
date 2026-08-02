# Genblaze integration

## Verified

The project has executed Genblaze Core `0.3.8` with Genblaze S3 `0.3.6`
against the live private Backblaze bucket.

The SDK verification path proves:

- `Pipeline` execution
- Hierarchical B2 `ObjectStorageSink`
- Local media asset transfer
- Asset SHA-256
- Canonical provenance manifest
- `manifest.verify()`
- Durable asset and manifest objects in B2
- OpenAI image generation through `DalleProvider`
- OpenAI narration through `OpenAITTSProvider`
- Corrective iteration lineage through `Pipeline.from_result(...)`

The storage smoke endpoint separately uses Genblaze's named `MockProvider`
with a deterministic fixture. Its response explicitly labels that asset
non-generative; the image and narration runs below use real OpenAI providers.

## Live OpenAI path

`POST /api/genblaze/live-background` is implemented with
`DalleProvider` from `genblaze-openai==0.3.4`. Despite the compatibility class
name, the installed adapter explicitly supports OpenAI's `gpt-image-2` model.

The prompt can generate only the creative background layer:

- no words
- no numbers
- no model IDs
- no logos or trademarks
- negative space for deterministic overlays

The product identity, models, lots, hazard, required action, remedy, and
contact remain locked compositor layers.

Required environment:

```text
OPENAI_API_KEY=
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_FALLBACK_MODELS=
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=coral
OPENAI_TRANSCRIPTION_MODEL=gpt-transcribe
OPENAI_VISION_MODEL=gpt-5.6-sol
RECALLCAST_BACKGROUND_KEY=<verified Genblaze PNG object key>
```

The request generates one low-quality 1024x1536 PNG to keep the live proof
bounded, then transfers it to the private B2 bucket and verifies its manifest.

## Verified live run

- Date: August 1, 2026
- Run: `59d1f1b6-f355-4638-93a3-7c13f51881a5`
- Provider/model: `openai-dalle` / `gpt-image-2`
- Provider latency: 20.5 seconds
- Asset size: 2,203,049 bytes
- Asset SHA-256: `aca9d67aa1d96e2001e958afe4c75349171b84f6a19ad28bccd323bdb280e869`
- Manifest hash: `ac16d4bb67e365900596412f9c921bddc448a49665765679134629367dc4a52c`
- Manifest verification: passed
- Durable objects: one PNG plus `manifest.json` in private B2

Visual review confirmed there are no words, numbers, logos, trademarks, or
product identifiers. The composition leaves a large clean region for
deterministic fact overlays.

## Verified narration and evidence package

Package `pkg_fe230c3fab0424ca` completed the connected media path:

1. Load and verify the background's Genblaze manifest from B2.
2. Compose locked critical copy into a 1080×1080 PNG.
3. Generate the MP3 using Genblaze and `gpt-4o-mini-tts`.
4. Reverse-transcribe the MP3 using `gpt-transcribe`.
5. Read the final PNG pixels using `gpt-5.6-sol` vision.
6. Validate audio and visual evidence independently against one contract.
7. Store the approved script, observed transcript, observed OCR, reports,
   assets, and package record in private B2.

The promoted package passed 15 checks and remains `needs_review`. Its
narration run is `e39e439b-cb0a-4a3d-92dc-1f3aefa15184`; its verified
manifest hash is
`93c68f02c6c01eb66714828ffdd06d9d70667f4cd8398090d4b0dd3deeabffa0`.

Spanish package `pkg_495ddb0b8a5419cc` also passed all 15 checks. Its
narration run is `e5f7d533-eec5-427b-9fe5-15ce068cfa1a`; its manifest hash is
`f06cf9e0b2639f84b8265ffa7b93baf6078fd357101c95c73e0682f56a4a0f09`.

## Verified corrective retry

A live attempt omitted the effective date during speech generation. FactLock
quarantined it and retained run `9b9540fe-bc9f-49a9-9c45-c118b5797b0e`.
RecallCast rebuilt the script from the contract, moved the fragile date to the
front and repeated it, then called `Pipeline.from_result(...)`. Corrective run
`56b977e5-f975-4112-953c-367fb2a010ce` records the first run as
`parent_run_id`, verifies its own manifest, and passed all 15 checks.

This is a content-aware retry, not a blind provider retry: the failed evidence
determines whether a new attempt is allowed, while the validator policy stays
unchanged.
