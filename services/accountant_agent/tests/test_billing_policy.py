import pytest

from src.billing_policy import BillingPolicyError, default_bank_charge, select_product


@pytest.mark.parametrize("kind,expected", [
    ("Speaker", "Speaker Registration"),
    ("Delegate", "Delegate Registration"),
    ("Exhibitor", "Exhibitor"),
])
def test_event_type_mapping(kind, expected):
    assert select_product("IIPLA", kind, "IIPLA 2026 USA", "Example") == expected


def test_wlf_uses_same_audited_event_products():
    assert select_product("IIPLA", "Speaker", "WLF 2026 Europe", "Example") == "Speaker Registration"


@pytest.mark.parametrize("deal,expected", [
    ("Client - Utility Patent Drawing", "Utility Patent Drawing"),
    ("Client - Design Patent Drawing", "Design Patent Drawing"),
    ("Patentability Search for invention", "Patentability Search"),
    ("Complete Specification - Patent Application Drafting and Filing", "Patent Application Drafting and Filing"),
])
def test_menteso_service_mapping(deal, expected):
    assert select_product("MENTESO", "Services", "Menteso Services", deal) == expected


def test_unknown_product_is_blocked_not_guessed():
    with pytest.raises(BillingPolicyError):
        select_product("MENTESO", "Services", "LexMom Services", "Unclassified work")


def test_unpaid_event_gets_bank_charge_but_paid_does_not():
    assert default_bank_charge("IIPLA", "IIPLA 2026 USA", "unpaid", "") == 25
    assert default_bank_charge("IIPLA", "WLF 2026 Europe", "paid", "Fully Paid") == 0
