"""FHIR export is structurally valid R4 (checked with fhir.resources models)."""
from pathlib import Path

import pytest

from backend.fhir import bundle

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def b():
    return bundle(DATA, "2026-10-16", {"SYN-000001": {"journey": [{"stage": "sent", "date": "2026-10-16", "channel": "sms"}]}})


def test_bundle_shape(b):
    kinds = {}
    for e in b["entry"]:
        kinds[e["resource"]["resourceType"]] = kinds.get(e["resource"]["resourceType"], 0) + 1
        assert e["request"]["method"] == "PUT"
    assert kinds["Patient"] == 300
    assert kinds["Task"] == 101 + 50  # ELIGIBLE + NEEDS_REVIEW
    assert {"Organization", "Observation", "ImagingStudy", "Communication"} <= set(kinds)


def test_no_nulls_and_valid_r4(b):
    fr = pytest.importorskip("fhir.resources.R4B.bundle")
    fr.Bundle.model_validate(b) if hasattr(fr.Bundle, "model_validate") else fr.Bundle.parse_obj(b)
    assert "None" not in str([e["resource"] for e in b["entry"][:50]])


def test_our_invitation_is_a_communication(b):
    ids = [e["resource"]["id"] for e in b["entry"] if e["resource"]["resourceType"] == "Communication"]
    assert "pv-SYN-000001-0" in ids


def test_filter_by_practice():
    small = bundle(DATA, "2026-10-16", gp="VPL-0142")
    pats = [e for e in small["entry"] if e["resource"]["resourceType"] == "Patient"]
    assert len(pats) == 22
