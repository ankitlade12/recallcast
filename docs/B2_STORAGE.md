# Backblaze B2 storage

## Current verified state

- Private bucket in `us-east-005`
- Default AES-256 SSE-B2 encryption
- Restricted application key
- Upload, download, version-aware delete, and SHA-256 round-trip verified
- Source notice and typed contract persisted
- Quarantined attempt persisted with transcript, report, run, and manifest
- Corrected parent-linked attempt and human approval persisted
- Genblaze media fixture and verified Genblaze manifest persisted

## Evidence graph

```text
recallcast/
  recalls/rc_demo_001/
    source/v001/
      notice.txt
      fact-contract.json
    packages/<contract-hash>/<locale>/
      social-card.png
      approved-script.txt
      observed-transcript.txt
      observed-ocr.txt
      overlay-manifest.txt
      validation.json
      attempts/001/
        script.txt
        observed-transcript.txt
        validation.json
      package.json
    assets/en-US/video/<asset-id>/
      transcript.txt
      validation.json
      run.json
      recallcast-manifest.json
      review-decision.json
  quarantine/rc_demo_001/<run-id>/
    transcript.txt
    validation.json
    run.json
    recallcast-manifest.json
  genblaze/runs/<date>/<run-id>/
    assets/<asset-id>.png
    manifest.json
```

Every application-written object includes a SHA-256 metadata field. The
private bucket is accessed only from the API, and browser review uses bounded
short-lived presigned GET URLs.

Genblaze-owned narration and background assets live under their immutable run
IDs. Package records reference those objects and their canonical manifest
hashes rather than copying the media into an ambiguous flat folder. Rejected
narrations remain addressable and accepted retries include `parent_run_id`.

## Lifecycle policy

The live bucket has prefix-scoped lifecycle rules:

- `recallcast/tmp/frames/`: hide after 1 day and permanently remove the
  noncurrent version after 1 additional day
- `recallcast/intermediate/`: hide after 7 days and permanently remove after
  1 additional day
- `recallcast/quarantine/`: hide after 30 days and permanently remove after
  1 additional day

Source contracts, approved assets, review decisions, and Genblaze manifests
are not covered by automatic expiration.

Backblaze's S3-compatible lifecycle API requires each day-based expiration
rule to have a same-prefix expired-delete-marker rule. The checked-in policy
uses those required pairs.

## Failure behavior

When `APP_STORAGE_MODE=b2`, failure to persist a run results in HTTP 503.
Passing validation alone cannot advance an asset to review. Approval is rolled
back if its review decision cannot be stored.
