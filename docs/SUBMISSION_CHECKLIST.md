# RecallCast submission checklist

The [Devpost challenge](https://backblaze-generative-media.devpost.com/) deadline
is **August 3, 2026 at 5:00 PM EDT**. The challenge asks
for a working app URL, a code repository with setup instructions, the provider
and model list, an explanation of B2 and Genblaze usage, and a short
approximately three-minute demo video.

## Ready

- [x] Functional Next.js review workspace
- [x] FastAPI validation and orchestration API
- [x] Real OpenAI image and narration generation through Genblaze
- [x] Real transcription and visual reverse extraction
- [x] Private encrypted B2 asset, metadata, evidence, and manifest storage
- [x] Deterministic per-modality FactLock release gate
- [x] Parent-linked corrective retry with rejected attempt retention
- [x] Human approval and source-version invalidation demo
- [x] Container definitions and local production compose path
- [x] Setup, B2, Genblaze, strategy, and demo documentation

## Still requires the project owner

- [ ] Rotate the Backblaze credential that was shared in chat, create a
  bucket-restricted `recallcast-app` key, and update the deployment secret.
- [ ] Choose the public GitHub repository and push this workspace.
- [ ] Deploy the API and web containers; set `WEB_ORIGINS` and the web build
  argument `NEXT_PUBLIC_API_URL` to the final HTTPS origins.
- [ ] Set a strong `RECALLCAST_ADMIN_TOKEN` in the API secret store. Do not
  expose it to the browser.
- [ ] Apply the final B2 CORS origin after the web URL exists.
- [ ] Record and upload the three-minute demo using `DEMO_SCRIPT.md`.
- [ ] Add the working URL, repository URL, and video URL to Devpost.
- [ ] Grant `https://github.com/b2genblaze` contributor access if the repo is
  private.
- [ ] Confirm the Genblaze repository has been starred, as requested by the
  challenge instructions.

## Provider and model disclosure

| Responsibility | Provider / model |
|---|---|
| Creative background | OpenAI `gpt-image-2` through Genblaze |
| Narration | OpenAI `gpt-4o-mini-tts` through Genblaze |
| Reverse transcription | OpenAI `gpt-transcribe` |
| Final-pixel visual reading | OpenAI `gpt-5.6-sol` vision |
| Durable object storage | Private Backblaze B2 via Genblaze S3 and boto3 |
| Critical copy composition | RecallCast deterministic Pillow compositor |
| Release validation | RecallCast FactLock deterministic policy engine |

## Submission positioning

**One sentence:** RecallCast compiles one approved product-safety notice into
accessible media and produces release evidence that every safety invariant
survived generation.

**Novelty:** contract-driven, closed-world conformance testing for regenerated
multimodal safety communications, combining reverse extraction, fail-closed
per-channel policies, content-aware parent-linked retries, and source-driven
invalidation.

**Community value:** public agencies, safety teams, manufacturers, and small
organizations can communicate urgent instructions in visual and audio formats
faster without treating a plausible AI output as trustworthy by default.
