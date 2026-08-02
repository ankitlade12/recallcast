from __future__ import annotations

from hashlib import sha256

from app.domain.models import FactContract


CPSC_SOURCE_URL = (
    "https://www.cpsc.gov/Recalls/2026/"
    "Electrolux-Group-Recalls-Frigidaire-Gas-Ranges-Due-to-Burn-Hazard"
)
CPSC_RECALL_NUMBER = "26-333"

FRIGIDAIRE_MODELS = (
    "FCFG3083AS",
    "FCRG3083AD",
    "FCRG3083AS",
    "GCFG3060BD",
    "GCFG3060BF",
    "GCFG3070BF",
    "GCRG3060BD",
    "GCRG3060BF",
    "PCFG3080AF",
    "FCFG3062AB",
    "FCFG3062AS",
    "FCFG3062AW",
    "FCRG3051BB",
    "FCRG3051BS",
    "FCRG3051BW",
    "FCRG3052BB",
    "FCRG3052BS",
    "FCRG3052BW",
    "FCRG3062AB",
    "FCRG3062AS",
    "FCRG3062AW",
    "FCRG306LAF",
    "GCFG3059BF",
)

REAL_CASE_NOTICE = """PUBLIC SOURCE CASE — CPSC RECALL 26-333

Electrolux Group recalls Frigidaire Gas Ranges. This recall covers models
FCFG3083AS, FCRG3083AD, FCRG3083AS, GCFG3060BD, GCFG3060BF, GCFG3070BF,
GCRG3060BD, GCRG3060BF, PCFG3080AF, FCFG3062AB, FCFG3062AS, FCFG3062AW,
FCRG3051BB, FCRG3051BS, FCRG3051BW, FCRG3052BB, FCRG3052BS, FCRG3052BW,
FCRG3062AB, FCRG3062AS, FCRG3062AW, FCRG306LAF, and GCFG3059BF, within
serial number range VF52200000 through VF54399999.

The ovens in the ranges can experience a delayed ignition of the oven's bake
burner, posing a risk of burn hazards to users. Consumers should stop using
ovens in the recalled ranges immediately and contact Electrolux Group for a
free repair. Consumers can continue to use the cooktop burners on the range.

Contact 866-291-7633 or https://www.gasovenburnerrecall.com.
Recall date: March 19, 2026. About 174,800 units in the United States.
CPSC and Electrolux Group report 62 delayed-ignition incidents, including 30
reported burn injuries.

Authoritative source:
https://www.cpsc.gov/Recalls/2026/Electrolux-Group-Recalls-Frigidaire-Gas-Ranges-Due-to-Burn-Hazard
"""


def real_case_contract(*, human_confirmed: bool = False) -> FactContract:
    return FactContract(
        recall_id="rc_cpsc_26_333",
        version=1,
        source_sha256=sha256(REAL_CASE_NOTICE.encode("utf-8")).hexdigest(),
        issuer="Electrolux Group",
        product_name="Frigidaire Gas Ranges",
        affected_models=FRIGIDAIRE_MODELS,
        affected_lot_ranges=(
            {"start": "VF52200000", "end": "VF54399999"},
        ),
        hazard=(
            "The ovens in the ranges can experience a delayed ignition of the "
            "oven's bake burner, posing a risk of burn hazards to users."
        ),
        required_action=(
            "Consumers should stop using ovens in the recalled ranges "
            "immediately and contact Electrolux Group for a free repair."
        ),
        remedy=(
            "Free repair with professional in-home installation of a new bake "
            "burner at no cost to consumers."
        ),
        contact={
            "phone": "866-291-7633",
            "url": "https://www.gasovenburnerrecall.com",
        },
        effective_date="2026-03-19",
        supported_locales=("en-US",),
        human_confirmed=human_confirmed,
    )


def real_case_narration_script() -> str:
    return (
        "Public-source safety draft for CPSC recall 26-333 concerning Frigidaire "
        "Gas Ranges. This recall covers 23 affected models listed on the companion "
        "card and official CPSC notice, within serial number range VF52200000 "
        "through VF54399999. The ovens can experience delayed ignition of the "
        "oven's bake burner, posing a burn hazard. Stop using ovens in the recalled "
        "ranges immediately. The cooktop burners can continue to be used. Contact "
        "Electrolux Group for a free repair with professional in-home installation "
        "of a new bake burner at no cost. Call 866-291-7633. Recall date March 19, "
        "2026. Verify affected models and current instructions at the official CPSC "
        "notice before taking action. This AI-generated narration is an unaffiliated "
        "RecallCast draft and not a message from CPSC or Electrolux Group."
    )


def real_case_corrective_narration_script() -> str:
    """A retry script that makes the serial bounds deliberately unambiguous."""
    return (
        "Public-source safety draft for CPSC recall 26-333 concerning Frigidaire "
        "Gas Ranges. This recall covers 23 affected models listed on the companion "
        "card and official CPSC notice. The affected serial number range begins "
        "with letter V, letter F, digit five, digit two, digit two, digit zero, "
        "digit zero, digit zero, digit zero, digit zero. It ends with letter V, "
        "letter F, digit five, digit four, digit three, digit nine, digit nine, "
        "digit nine, digit nine, digit nine. The ovens can experience delayed "
        "ignition of the oven's bake burner, posing a burn hazard. Stop using "
        "ovens in the recalled ranges immediately. The cooktop burners can "
        "continue to be used. Contact Electrolux Group for a free repair with "
        "professional in-home installation of a new bake burner at no cost. "
        "Call 866-291-7633. Recall date March 19, 2026. Verify affected models "
        "and current instructions at the official CPSC notice before taking "
        "action. This AI-generated narration is an unaffiliated RecallCast draft "
        "and not a message from CPSC or Electrolux Group."
    )
