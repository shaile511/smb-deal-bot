from decimal import Decimal

import pytest

from quote_desk import price_book as pb
from quote_desk.quote import Needs, build_quote


def dental():
    return Needs(company="Maple Ridge Dental", locations=2, internet_speed=1000, phone_lines=12,
                 mobile_lines=6, managed_wifi=True, backup_internet=True, term_months=36)


def test_list_price_is_sum_of_lines():
    q = build_quote(dental())
    assert q.list_monthly == sum(l.monthly for l in q.lines)


def test_three_families_get_bundle_and_term_discounts():
    q = build_quote(dental())
    labels = " ".join(a.label.lower() for a in q.adjustments)
    assert "bundle" in labels and "36" in labels
    assert q.monthly < q.list_monthly
    assert q.margin >= pb.MARGIN_FLOOR


def test_install_waived_on_36_months_only():
    assert build_quote(dental()).one_time == 0
    twelve = dental()
    twelve.term_months = 12
    assert build_quote(twelve).one_time == pb.INSTALL_FEE * 2


def test_extra_discount_is_capped_at_margin_floor():
    q = build_quote(dental(), Decimal("0.60"))
    assert q.extra_discount_applied < Decimal("0.60")
    assert q.margin >= pb.MARGIN_FLOOR - Decimal("0.001")
    assert any("cap" in w.lower() for w in q.warnings)


def test_small_extra_discount_is_applied_in_full():
    q = build_quote(dental(), Decimal("0.02"))
    assert q.extra_discount_applied == Decimal("0.02")


def test_bad_term_rejected():
    n = dental()
    n.term_months = 18
    with pytest.raises(ValueError):
        build_quote(n)


def test_nothing_to_quote_warns():
    q = build_quote(Needs(internet_speed=None))
    assert not q.lines and q.warnings
