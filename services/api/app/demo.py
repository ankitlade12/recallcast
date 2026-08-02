from __future__ import annotations

from hashlib import sha256

from app.domain.models import FactContract


NOTICE = """URGENT PRODUCT RECALL — Northstar Glow Mini Heater

Northstar Home Products is recalling Northstar Glow Mini Heater models NG-100
and NG-110, lots A71 through A94. The lithium-ion battery can overheat and
cause a fire. Stop using and unplug the heater immediately. Consumers will
receive a free replacement.

Contact 1-800-555-0147 or visit
https://example.invalid/northstar-recall. Effective July 29, 2026.
"""


def demo_contract(version: int = 1, remedy: str = "Free replacement.") -> FactContract:
    return FactContract(
        recall_id="rc_demo_001",
        version=version,
        source_sha256=sha256(NOTICE.encode("utf-8")).hexdigest(),
        issuer="Northstar Home Products",
        product_name="Northstar Glow Mini Heater",
        affected_models=("NG-100", "NG-110"),
        affected_lot_ranges=({"start": "A71", "end": "A94"},),
        hazard="The lithium-ion battery can overheat and cause a fire.",
        required_action="Stop using and unplug the heater immediately.",
        remedy=remedy,
        contact={
            "phone": "1-800-555-0147",
            "url": "https://example.invalid/northstar-recall",
        },
        effective_date="2026-07-29",
    )


APPROVED_EN = (
    "Urgent product recall for the Northstar Glow Mini Heater, models NG-100 "
    "and NG-110, lots A71 through A94. The lithium-ion battery can overheat "
    "and cause a fire. Stop using and unplug the heater immediately. A free "
    "replacement is available. Call 1-800-555-0147 or visit "
    "https://example.invalid/northstar-recall. Effective July 29, 2026."
)

APPROVED_ES = (
    "Retiro urgente del calentador Northstar Glow Mini Heater, modelos NG-100 "
    "y NG-110, lotes A71 a A94. La batería de iones de litio puede "
    "sobrecalentarse y provocar un incendio. Deje de usar y desenchufe el "
    "calentador inmediatamente. Hay un reemplazo gratuito disponible. Llame "
    "al 1-800-555-0147 o visite "
    "https://example.invalid/northstar-recall. Vigente el 29 de julio de 2026."
)

IDENTIFIER_MUTATION = APPROVED_EN.replace("NG-110", "NG-101")
ACTION_WEAKENING = APPROVED_EN.replace(
    "Stop using and unplug the heater immediately.",
    "Use the heater only when supervised.",
)

SCENARIOS = {
    "approved": {
        "label": "Verified package",
        "description": "All locked safety facts are preserved.",
        "transcript": APPROVED_EN,
    },
    "identifier_mutation": {
        "label": "Identifier mutation",
        "description": "The model number NG-110 was changed to NG-101.",
        "transcript": IDENTIFIER_MUTATION,
    },
    "action_weakening": {
        "label": "Action weakening",
        "description": "The message permits continued supervised use.",
        "transcript": ACTION_WEAKENING,
    },
}
