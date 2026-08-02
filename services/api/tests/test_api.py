from fastapi.testclient import TestClient

from app.domain.models import RecallExtraction
from app.main import _admin_authorized, app
from app.providers.genblaze_pipeline import _b2_object_key, live_generation_available

client = TestClient(app)


def test_admin_token_fails_closed(monkeypatch):
    monkeypatch.delenv("RECALLCAST_ADMIN_TOKEN", raising=False)
    assert not _admin_authorized(None)
    assert not _admin_authorized("anything")
    monkeypatch.setenv("RECALLCAST_ADMIN_TOKEN", "bounded-secret")
    assert not _admin_authorized(None)
    assert not _admin_authorized("wrong")
    assert _admin_authorized("bounded-secret")


def test_live_background_requires_admin_before_provider_call(monkeypatch):
    monkeypatch.delenv("RECALLCAST_ADMIN_TOKEN", raising=False)
    response = client.post("/api/genblaze/live-background")
    assert response.status_code == 403


def test_live_generation_requires_openai_and_b2(monkeypatch):
    required = ("B2_KEY_ID", "B2_APP_KEY", "B2_BUCKET", "OPENAI_API_KEY")
    for name in required:
        monkeypatch.setenv(name, "configured-for-test")
    assert live_generation_available()

    monkeypatch.delenv("OPENAI_API_KEY")
    assert not live_generation_available()


def test_genblaze_asset_url_maps_to_private_b2_key():
    key = _b2_object_key(
        "https://s3.us-east-005.backblazeb2.com/recallcast-private/"
        "recallcast/genblaze/runs/example/assets/background.png",
        "recallcast-private",
    )
    assert key == "recallcast/genblaze/runs/example/assets/background.png"


def test_demo_flow_quarantine_retry_approve_and_stale():
    demo = client.get("/api/demo")
    assert demo.status_code == 200
    assert demo.json()["contract"]["product_name"] == "Northstar Glow Mini Heater"

    failed = client.post(
        "/api/demo/run",
        json={
            "scenario": "action_weakening",
            "locale": "en-US",
            "channel": "video",
        },
    )
    assert failed.status_code == 200
    failed_run = failed.json()
    assert failed_run["status"] == "quarantined"

    retried = client.post(f"/api/demo/retry/{failed_run['run_id']}")
    assert retried.status_code == 200
    retry_run = retried.json()
    assert retry_run["parent_run_id"] == failed_run["run_id"]
    assert retry_run["status"] == "needs_review"

    approved = client.post(f"/api/assets/{retry_run['asset_id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    updated = client.post(
        "/api/demo/source-update",
        json={"remedy": "Full refund."},
    )
    assert updated.status_code == 200
    assert retry_run["asset_id"] in updated.json()["stale_assets"]

    regenerated = client.post(
        "/api/demo/run",
        json={"scenario": "approved", "locale": "en-US", "channel": "video"},
    )
    assert regenerated.status_code == 200
    assert regenerated.json()["status"] == "needs_review"
    assert "full refund" in regenerated.json()["transcript"].lower()

    repeated_update = client.post(
        "/api/demo/source-update",
        json={"remedy": "Full refund."},
    )
    assert repeated_update.status_code == 200
    assert repeated_update.json()["source_version"] == updated.json()["source_version"]
    assert repeated_update.json()["changed_fact_ids"] == []


def test_demo_request_rejects_unknown_channel():
    response = client.post(
        "/api/demo/run",
        json={"scenario": "approved", "locale": "en-US", "channel": "unknown"},
    )
    assert response.status_code == 422


def test_intake_rejects_unsupported_upload_before_provider_call(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    response = client.post(
        "/api/intake/extract",
        json={
            "source_name": "notice.pdf",
            "source_text": "This intentionally long recall source is not accepted as a PDF. " * 3,
        },
    )
    assert response.status_code == 400
    assert ".txt, .md, and .json" in response.json()["detail"]


def test_intake_extract_review_confirm_flow(monkeypatch):
    source = (
        "Acme Safety recalls the Ember Fan EF-20, lots B10 through B12. "
        "The motor can overheat and cause a fire. Stop using the fan immediately. "
        "A full refund is available. Call 1-800-555-0100 or visit "
        "https://example.invalid/ember. Effective August 1, 2026."
    )
    extracted = RecallExtraction(
        issuer="Acme Safety",
        product_name="Ember Fan",
        affected_models=["EF-20"],
        affected_lot_ranges=[{"start": "B10", "end": "B12"}],
        hazard="The motor can overheat and cause a fire.",
        required_action="Stop using the fan immediately.",
        remedy="A full refund is available.",
        contact_phone="1-800-555-0100",
        contact_url="https://example.invalid/ember",
        effective_date="2026-08-01",
        supported_locales=["en-US"],
        extraction_warnings=[],
    )
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    monkeypatch.setattr("app.main.extract_recall", lambda _: extracted)
    monkeypatch.setattr("app.main.get_b2_storage", lambda: None)

    created = client.post(
        "/api/intake/extract",
        json={"source_name": "ember-recall.md", "source_text": source},
    )
    assert created.status_code == 200
    draft = created.json()
    assert draft["status"] == "needs_review"
    assert draft["extraction"]["affected_models"] == ["EF-20"]
    assert draft["storage_objects"] == []

    confirmed = client.post(
        "/api/intake/confirm",
        json={"draft_id": draft["draft_id"], "extraction": draft["extraction"]},
    )
    assert confirmed.status_code == 200
    payload = confirmed.json()
    assert payload["status"] == "confirmed"
    assert payload["contract"]["human_confirmed"] is True
    assert payload["contract"]["product_name"] == "Ember Fan"
    assert payload["policy_pack"]["status"] == "draft"
    assert payload["policy_pack"]["exact_identifiers"] == ["EF-20"]

    blocked = client.post(
        f"/api/intake/{draft['draft_id']}/policy/activate",
        json={
            "concept_groups": payload["policy_pack"]["concept_groups"],
            "reviewer": "Safety reviewer",
            "attestation": False,
        },
    )
    assert blocked.status_code == 422

    activated = client.post(
        f"/api/intake/{draft['draft_id']}/policy/activate",
        json={
            "concept_groups": payload["policy_pack"]["concept_groups"],
            "reviewer": "Safety reviewer",
            "attestation": True,
        },
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    assert activated.json()["contract_sha256"] == payload["contract"]["contract_sha256"]


def test_public_cpsc_case_exposes_source_attribution_and_unconfirmed_contract(monkeypatch):
    monkeypatch.setattr("app.main._real_case_confirmed", False)
    monkeypatch.setattr("app.main._real_case_reviewer", None)
    response = client.get("/api/cases/cpsc-26-333")
    assert response.status_code == 200
    payload = response.json()
    assert payload["case_type"] == "public_source"
    assert payload["recall_number"] == "26-333"
    assert payload["source_url"].startswith("https://www.cpsc.gov/Recalls/2026/")
    assert payload["contract"]["human_confirmed"] is False
    assert len(payload["contract"]["affected_models"]) == 23
    assert payload["contract"]["affected_lot_ranges"] == [
        {"start": "VF52200000", "end": "VF54399999"}
    ]
    assert payload["stats"]["reported_injuries"] == 30


def test_public_case_confirmation_is_explicit_and_enables_draft(monkeypatch):
    monkeypatch.setattr("app.main._real_case_confirmed", False)
    monkeypatch.setattr("app.main._real_case_reviewer", None)
    monkeypatch.setattr("app.main.get_b2_storage", lambda: None)

    rejected = client.post(
        "/api/cases/cpsc-26-333/confirm",
        json={"reviewer": "Local reviewer", "acknowledgment": False},
    )
    assert rejected.status_code == 422

    confirmed = client.post(
        "/api/cases/cpsc-26-333/confirm",
        json={"reviewer": "Local reviewer", "acknowledgment": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["contract"]["human_confirmed"] is True

    current = client.get("/api/cases/cpsc-26-333")
    assert current.json()["release_status"] == "media_draft_enabled"
    assert current.json()["reviewer"] == "Local reviewer"


def test_public_case_generation_fails_closed_before_confirmation(monkeypatch):
    monkeypatch.setattr("app.main._real_case_confirmed", False)
    response = client.post("/api/cases/cpsc-26-333/packages/generate")
    assert response.status_code == 409


def test_public_case_approval_requires_accountability_attestation(monkeypatch):
    monkeypatch.setattr("app.main._real_case_confirmed", True)
    response = client.post(
        "/api/cases/cpsc-26-333/packages/pkg_review_test/review",
        json={
            "decision": "approved",
            "reviewer": "Accountable reviewer",
            "rationale": "I reviewed the source and all final media evidence.",
            "attestation": False,
        },
    )
    assert response.status_code == 422
    assert "accountability attestation" in response.json()["detail"]
