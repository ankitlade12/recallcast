# RecallCast Backblaze B2 setup

RecallCast uses one private B2 bucket as its durable system of record. Browser
clients never receive B2 credentials; the API produces short-lived access URLs
when media needs to be reviewed.

## Recommended bucket

- **Name:** globally unique, for example `recallcast-<team>-2026`
- **Access:** private
- **Default encryption:** SSE-B2 / AES-256
- **Object Lock:** optional for the hackathon; enable only if the retention
  consequences are understood
- **Lifecycle rules:** apply `lifecycle.json`
- **CORS:** `cors.json` includes localhost and the default RecallCast Render
  origin; update it if the deployed service slug changes

Do not place company names, consumer details, PHI, or PII in bucket names or
object keys.

## Object layout

```text
recallcast/
  recalls/<recall-id>/
    source/v001/
    assets/<locale>/<channel>/<asset-id>/
    releases/
    audit/
  quarantine/<recall-id>/<attempt-id>/
  intermediate/
  tmp/frames/
```

Source versions, released assets, validation reports, and manifests have no
automatic expiration. Temporary frames, intermediates, and hackathon
quarantine fixtures use lifecycle cleanup.

## Least-privilege application key

Create a bucket-restricted key named `recallcast-app` with:

- `listAllBucketNames`
- `listFiles`
- `readFiles`
- `writeFiles`

Add `deleteFiles` only if the deployed app actually performs cleanup. The
current application does not need it because B2 lifecycle rules own cleanup.

The master application key is not supported by the S3-compatible API and
should never be used by RecallCast.

Save the new key values directly in the local `.env` file or deployment secret
store:

```text
B2_KEY_ID=<application key ID>
B2_APP_KEY=<application key secret>
B2_BUCKET=<bucket name>
B2_REGION=<region from the endpoint, such as us-east-005>
B2_ENDPOINT=https://s3.<region>.backblazeb2.com
```

Never commit `.env`, paste the secret into chat, or expose it with a
`NEXT_PUBLIC_` prefix.

## Console configuration order

1. Create the private bucket.
2. Record its S3 endpoint and region.
3. Enable default SSE-B2 encryption.
4. Add the lifecycle rules from `lifecycle.json`.
5. Confirm the deployed web origin in `cors.json`.
6. Add the CORS configuration from `cors.json`.
7. Create the bucket-restricted application key.
8. Populate `.env` locally.
9. Run `./infra/b2/verify.sh`.

## Why lifecycle configuration is separate

A key restricted to one bucket cannot receive the broad `writeBuckets`
capability required to alter CORS and lifecycle configuration. Configure those
policies once through the authenticated console, then use the restricted
runtime key for object access.
