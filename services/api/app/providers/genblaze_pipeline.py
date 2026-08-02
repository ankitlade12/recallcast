"""Genblaze integration boundary.

The deterministic demo does not require paid provider credentials. This module
keeps provider imports isolated and documents the executable live path. It is
intentionally loaded only when a configured generation run is requested.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class GenblazeSettings:
    b2_bucket: str
    b2_region: str
    b2_key_id: str
    b2_app_key: str

    @classmethod
    def from_environment(cls) -> "GenblazeSettings":
        values = {
            "b2_bucket": os.getenv("B2_BUCKET", ""),
            "b2_region": os.getenv("B2_REGION", ""),
            "b2_key_id": os.getenv("B2_KEY_ID", ""),
            "b2_app_key": os.getenv("B2_APP_KEY", ""),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError(
                "Genblaze B2 storage requires: " + ", ".join(missing)
            )
        return cls(**values)


def build_storage(settings: GenblazeSettings | None = None) -> Any:
    from genblaze_core import KeyStrategy, ObjectStorageSink
    from genblaze_s3 import S3StorageBackend

    configured = settings or GenblazeSettings.from_environment()
    return ObjectStorageSink(
        S3StorageBackend.for_backblaze(
            configured.b2_bucket,
            region=configured.b2_region,
            key_id=configured.b2_key_id,
            app_key=configured.b2_app_key,
            auto_lifecycle=False,
        ),
        prefix="recallcast/genblaze",
        key_strategy=KeyStrategy.HIERARCHICAL,
    )


def verify_result(result: Any) -> None:
    if not result.manifest.verify():
        raise RuntimeError("Genblaze provenance manifest verification failed.")


def _b2_object_key(asset_url: str, bucket: str) -> str:
    path = unquote(urlparse(asset_url).path).lstrip("/")
    bucket_prefix = f"{bucket}/"
    return path[len(bucket_prefix):] if path.startswith(bucket_prefix) else path


def live_generation_available() -> bool:
    required = ("B2_KEY_ID", "B2_APP_KEY", "B2_BUCKET", "OPENAI_API_KEY")
    return all(os.getenv(name) for name in required)


def run_live_background_generation() -> dict[str, Any]:
    """Generate one creative-only recall background through OpenAI and Genblaze."""

    if not live_generation_available():
        raise RuntimeError(
            "Live background generation requires OPENAI_API_KEY and B2 settings."
        )

    from genblaze_core import Modality, Pipeline
    from genblaze_openai import DalleProvider

    model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
    fallback_models = [
        item.strip()
        for item in os.getenv("OPENAI_IMAGE_FALLBACK_MODELS", "").split(",")
        if item.strip()
    ]
    prompt = (
        "Create a premium vertical safety-bulletin background for a fictional "
        "compact home heater recall. Abstract warm red thermal waves against "
        "deep charcoal and warm ivory, strong negative space for deterministic "
        "text overlays, editorial product-safety design, high contrast, no "
        "words, no letters, no numbers, no logos, no trademarks, no QR codes, "
        "no product identifiers."
    )
    result = (
        Pipeline(
            "recallcast-creative-background",
            project_id="recallcast",
            structured_log=True,
        )
        .step(
            DalleProvider(http_timeout=180),
            model=model,
            fallback_models=fallback_models or None,
            prompt=prompt,
            modality=Modality.IMAGE,
            params={
                "size": "1024x1536",
                "quality": "low",
                "n": 1,
                "output_format": "png",
            },
            metadata={
                "recall_id": "rc_demo_001",
                "layer_policy": "creative_background_only",
                "critical_text_allowed": False,
                "generation_purpose": "hackathon_live_provider_proof",
            },
        )
        .run(
            sink=build_storage(),
            timeout=300,
            max_retries=1,
        )
    )
    verify_result(result)
    step = result.run.steps[0]
    asset = step.assets[0]
    settings = GenblazeSettings.from_environment()
    return {
        "status": "generated",
        "pipeline_id": result.run.run_id,
        "provider": step.provider,
        "model": step.model,
        "asset_url": asset.url,
        "asset_key": _b2_object_key(asset.url, settings.b2_bucket),
        "asset_sha256": asset.sha256,
        "manifest_hash": result.manifest.canonical_hash,
        "manifest_verified": result.manifest.verify(),
        "layer_policy": "creative_background_only",
    }


def run_sdk_storage_smoke() -> dict[str, Any]:
    """Exercise the real Genblaze pipeline, manifest, and B2 sink.

    This uses Genblaze's explicit MockProvider and a locally rendered fixture.
    It validates SDK/B2 integration only and is never represented as an AI
    generation provider.
    """

    from genblaze_core import Asset, Modality, Pipeline
    from genblaze_core.mocks import MockProvider
    from PIL import Image, ImageDraw

    with tempfile.TemporaryDirectory(prefix="recallcast-genblaze-") as directory:
        output_path = Path(directory) / "factlock-fixture.png"
        image = Image.new("RGB", (1080, 1080), "#18201e")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((70, 70, 1010, 1010), radius=38, fill="#f3f1eb")
        draw.rectangle((70, 70, 1010, 220), fill="#e7422f")
        draw.text((115, 120), "URGENT PRODUCT RECALL", fill="white")
        draw.text((115, 300), "Northstar Glow Mini Heater", fill="#18201e")
        draw.text((115, 390), "Models NG-100 + NG-110 | Lots A71-A94", fill="#18201e")
        draw.text((115, 520), "STOP USING AND UNPLUG IMMEDIATELY", fill="#a9281d")
        draw.text((115, 650), "Free replacement | 1-800-555-0147", fill="#18201e")
        draw.text((115, 880), "DRAFT - HUMAN APPROVAL REQUIRED", fill="#6c7471")
        image.save(output_path, format="PNG")
        content = output_path.read_bytes()
        asset = Asset(
            url=output_path.as_uri(),
            media_type="image/png",
            sha256=sha256(content).hexdigest(),
            size_bytes=len(content),
            width=1080,
            height=1080,
            metadata={"fixture": True, "purpose": "sdk-storage-smoke"},
        )
        provider = MockProvider(
            name="recallcast-sdk-smoke",
            assets=[asset],
        )
        result = (
            Pipeline(
                "recallcast-sdk-storage-smoke",
                project_id="recallcast",
                structured_log=True,
            )
            .step(
                provider,
                model="deterministic-fixture-v1",
                prompt=(
                    "SDK storage smoke only: render the locked Northstar "
                    "recall fixture."
                ),
                modality=Modality.IMAGE,
                metadata={"non_generative_fixture": True},
            )
            .run(sink=build_storage(), timeout=120)
        )
        verify_result(result)
        stored_asset = result.run.steps[0].assets[0]
        return {
            "status": "verified",
            "pipeline_id": result.run.run_id,
            "provider": provider.name,
            "model": "deterministic-fixture-v1",
            "asset_url": stored_asset.url,
            "asset_sha256": stored_asset.sha256,
            "manifest_hash": result.manifest.canonical_hash,
            "manifest_verified": result.manifest.verify(),
            "non_generative_fixture": True,
        }
