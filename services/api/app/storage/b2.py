from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


@dataclass(frozen=True)
class StoredObject:
    key: str
    uri: str
    sha256: str
    content_type: str
    size: int
    version_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "uri": self.uri,
            "sha256": self.sha256,
            "content_type": self.content_type,
            "size": self.size,
            "version_id": self.version_id,
        }


@dataclass(frozen=True)
class B2Settings:
    bucket: str
    region: str
    endpoint: str
    key_id: str
    app_key: str

    @classmethod
    def from_environment(cls) -> "B2Settings":
        required = {
            "bucket": os.getenv("B2_BUCKET", ""),
            "region": os.getenv("B2_REGION", ""),
            "key_id": os.getenv("B2_KEY_ID", ""),
            "app_key": os.getenv("B2_APP_KEY", ""),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "B2 storage mode is enabled but these settings are missing: "
                + ", ".join(missing)
            )
        endpoint = os.getenv(
            "B2_ENDPOINT",
            f"https://s3.{required['region']}.backblazeb2.com",
        )
        return cls(endpoint=endpoint, **required)


class B2Storage:
    def __init__(self, settings: B2Settings):
        self.settings = settings
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint,
            region_name=settings.region,
            aws_access_key_id=settings.key_id,
            aws_secret_access_key=settings.app_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
        )

    def health(self) -> dict[str, Any]:
        self.client.head_bucket(Bucket=self.settings.bucket)
        encryption = self.client.get_bucket_encryption(
            Bucket=self.settings.bucket
        )
        algorithm = (
            encryption["ServerSideEncryptionConfiguration"]["Rules"][0]
            ["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
        )
        return {
            "status": "connected",
            "bucket": self.settings.bucket,
            "region": self.settings.region,
            "endpoint": self.settings.endpoint,
            "encryption": algorithm,
        }

    def _reference_from_head(
        self,
        key: str,
        content_type: str,
        digest: str,
        response: dict[str, Any],
    ) -> StoredObject:
        return StoredObject(
            key=key,
            uri=f"b2://{self.settings.bucket}/{key}",
            sha256=digest,
            content_type=content_type,
            size=response.get("ContentLength", 0),
            version_id=response.get("VersionId"),
        )

    def put_bytes(
        self,
        key: str,
        content: bytes,
        content_type: str,
        *,
        metadata: dict[str, str] | None = None,
        overwrite: bool = True,
    ) -> StoredObject:
        digest = sha256(content).hexdigest()
        if not overwrite:
            try:
                existing = self.client.head_object(
                    Bucket=self.settings.bucket,
                    Key=key,
                )
                existing_digest = existing.get("Metadata", {}).get("sha256")
                if existing_digest == digest:
                    return self._reference_from_head(
                        key, content_type, digest, existing
                    )
            except ClientError as error:
                status = error.response.get("ResponseMetadata", {}).get(
                    "HTTPStatusCode"
                )
                if status not in {404}:
                    raise

        object_metadata = {"sha256": digest, **(metadata or {})}
        response = self.client.put_object(
            Bucket=self.settings.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            Metadata=object_metadata,
            ServerSideEncryption="AES256",
        )
        return StoredObject(
            key=key,
            uri=f"b2://{self.settings.bucket}/{key}",
            sha256=digest,
            content_type=content_type,
            size=len(content),
            version_id=response.get("VersionId"),
        )

    def put_text(
        self,
        key: str,
        content: str,
        *,
        content_type: str = "text/plain; charset=utf-8",
        metadata: dict[str, str] | None = None,
        overwrite: bool = True,
    ) -> StoredObject:
        return self.put_bytes(
            key,
            content.encode("utf-8"),
            content_type,
            metadata=metadata,
            overwrite=overwrite,
        )

    def put_json(
        self,
        key: str,
        payload: Any,
        *,
        metadata: dict[str, str] | None = None,
        overwrite: bool = True,
    ) -> StoredObject:
        content = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        return self.put_bytes(
            key,
            content,
            "application/json",
            metadata=metadata,
            overwrite=overwrite,
        )

    def list_prefix(self, prefix: str, max_keys: int = 100) -> list[dict[str, Any]]:
        response = self.client.list_objects_v2(
            Bucket=self.settings.bucket,
            Prefix=prefix,
            MaxKeys=max_keys,
        )
        return [
            {
                "key": item["Key"],
                "size": item["Size"],
                "last_modified": item["LastModified"].isoformat(),
                "etag": item["ETag"].strip('"'),
            }
            for item in response.get("Contents", [])
        ]

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.settings.bucket, Key=key)
        return response["Body"].read()

    def get_json(self, key: str) -> Any:
        return json.loads(self.get_bytes(key).decode("utf-8"))

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.settings.bucket, Key=key)
            return True
        except ClientError as error:
            status = error.response.get("ResponseMetadata", {}).get(
                "HTTPStatusCode"
            )
            if status == 404:
                return False
            raise

    def presign_get(self, key: str, expires_in: int = 900) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.settings.bucket,
                "Key": key,
            },
            ExpiresIn=min(max(expires_in, 60), 3600),
        )


def storage_mode() -> str:
    return os.getenv("APP_STORAGE_MODE", "memory").lower()


@lru_cache(maxsize=1)
def get_b2_storage() -> B2Storage | None:
    if storage_mode() != "b2":
        return None
    return B2Storage(B2Settings.from_environment())


def source_prefix(recall_id: str, version: int) -> str:
    return f"recallcast/recalls/{recall_id}/source/v{version:03d}"


def asset_prefix(
    recall_id: str,
    locale: str,
    channel: str,
    asset_id: str,
) -> str:
    return (
        f"recallcast/recalls/{recall_id}/assets/"
        f"{locale}/{channel}/{asset_id}"
    )


def quarantine_prefix(recall_id: str, run_id: str) -> str:
    return f"recallcast/quarantine/{recall_id}/{run_id}"
