"""Spectral-type → progenitor class inference (Yale BSC5 / catalog SpType)."""

from __future__ import annotations

from backend.candidates.catalog import (
    _parse_luminosity_class,
    infer_progenitor_class_from_spectral,
)


def test_parse_luminosity_does_not_misread_iiib_as_ib() -> None:
    # IIIb/IIIab are giant subclasses — must not collapse to Ib/Iab.
    assert _parse_luminosity_class("K0IIIbFe-2") in {"III", "IIIb"}
    assert _parse_luminosity_class("B2III") == "III"
    assert _parse_luminosity_class("M1IIIab") in {"III", "IIIa", "IIIb"}
    assert _parse_luminosity_class("M2 Iab") == "Iab"
    assert _parse_luminosity_class("M1.5Ia") == "Ia"
    assert _parse_luminosity_class("K3Ib") == "Ib"
    assert _parse_luminosity_class("A0V") == "V"


def test_infer_class_only_for_clear_progenitors() -> None:
    assert infer_progenitor_class_from_spectral("M2 Iab") == "RSG"
    assert infer_progenitor_class_from_spectral("M1 Ia") == "RSG"
    assert infer_progenitor_class_from_spectral("K3Ib") == "RSG"
    assert infer_progenitor_class_from_spectral("B8 Ia") == "BSG"
    assert infer_progenitor_class_from_spectral("G0 Iab") == "YSG"
    assert infer_progenitor_class_from_spectral("WN4") == "WR"
    assert infer_progenitor_class_from_spectral("WC5") == "WR"
    # Dwarfs / giants stay unclassified (UNK at catalog layer).
    assert infer_progenitor_class_from_spectral("A0V") is None
    assert infer_progenitor_class_from_spectral("K0.5III") is None
    assert infer_progenitor_class_from_spectral("B2III") is None
    assert infer_progenitor_class_from_spectral("M1IIIab") is None
    assert infer_progenitor_class_from_spectral("F5II") is None
    assert infer_progenitor_class_from_spectral("") is None
    assert infer_progenitor_class_from_spectral(None) is None
