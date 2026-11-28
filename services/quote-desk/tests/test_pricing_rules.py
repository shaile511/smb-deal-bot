"""One test per row of the "Pricing rules" table in the README, with exact dollar amounts.

The amounts are typed out by hand, not read from price_book.py, so changing a price or a
discount in the price book without updating this file makes a test fail.
"""

from decimal import Decimal as D

import pytest

from quote_desk.quote import Needs, build_quote


def quote(extra="0", **needs):
    base = dict(internet_speed=None, term_months=12)
    base.update(needs)
    return build_quote(Needs(**base), D(extra))


def adjustment(q, word):
    return next(a.amount for a in q.adjustments if word in a.label.lower())


@pytest.mark.parametrize("speed, price", [(300, "95.00"), (1000, "145.00"), (3000, "220.00")])
def test_internet_price_per_site(speed, price):
    assert quote(internet_speed=speed).monthly == D(price)
    assert quote(internet_speed=speed, locations=3).list_monthly == D(price) * 3


def test_phone_line_price_and_credit_from_ten_lines():
    nine = quote(phone_lines=9)
    assert nine.monthly == D("252.00") and not nine.adjustments
    ten = quote(phone_lines=10)
    assert adjustment(ten, "multi-line credit") == D("-30.00")
    assert ten.monthly == D("250.00")


def test_mobile_prices_and_volume_tiers():
    assert quote(mobile_lines=4).monthly == D("220.00")  # 4 x 55, no discount
    five = quote(mobile_lines=5)
    assert adjustment(five, "multi-line discount") == D("-13.75") and five.monthly == D("261.25")  # 5%
    ten = quote(mobile_lines=10, mobile_plan="unlimited")
    assert adjustment(ten, "multi-line discount") == D("-75.00") and ten.monthly == D("675.00")  # 10% of 750


def test_add_ons_per_site():
    one = quote(internet_speed=1000, static_ip=True, managed_wifi=True, backup_internet=True)
    assert one.monthly == D("215.00")  # 145 + 15 + 25 + 30
    two = quote(internet_speed=1000, static_ip=True, managed_wifi=True, backup_internet=True, locations=2)
    assert two.monthly == D("430.00")


def test_bundle_discount_for_two_and_three_families():
    two = quote(internet_speed=1000, phone_lines=1)  # 145 + 28 = 173
    assert adjustment(two, "bundle") == D("-6.92") and two.monthly == D("166.08")  # 4%
    three = quote(internet_speed=1000, phone_lines=1, mobile_lines=1)  # 173 + 55 = 228
    assert adjustment(three, "bundle") == D("-18.24") and three.monthly == D("209.76")  # 8%
    assert not any("bundle" in a.label.lower() for a in quote(internet_speed=1000).adjustments)


def test_term_discount_and_install_fee():
    assert quote(internet_speed=1000, term_months=12).monthly == D("145.00")
    assert quote(internet_speed=1000, term_months=24).monthly == D("137.75")  # 5% off
    assert quote(internet_speed=1000, term_months=36).monthly == D("130.50")  # 10% off
    assert quote(internet_speed=1000, term_months=12).one_time == D("199.00")
    assert quote(internet_speed=1000, term_months=24, locations=2).one_time == D("398.00")
    assert quote(internet_speed=1000, term_months=36, locations=2).one_time == D("0.00")
    assert quote(phone_lines=3, term_months=12).one_time == D("0.00")  # no install without internet


def dental(extra="0"):
    return quote(extra, company="Maple Ridge Dental", locations=2, internet_speed=1000, phone_lines=12,
                 mobile_lines=6, managed_wifi=True, backup_internet=True, term_months=36)


def test_dental_quote_adds_up_exactly():
    q = dental()
    assert q.list_monthly == D("1066.00")
    assert [a.amount for a in q.adjustments] == [D("-36.00"), D("-16.50"), D("-81.08"), D("-93.24"), D("0")]
    assert q.monthly == D("839.18")
    assert q.monthly_cost == D("528.00")
    assert q.one_time == D("0.00")
    assert q.term_total == D("30210.48")  # 839.18 x 36


def test_rep_discount_rounds_down_to_the_cent():
    q = dental("0.02")
    assert adjustment(q, "rep discount") == D("-16.78")  # 2% of 839.18 is 16.7836
    assert q.monthly == D("822.40")


def test_margin_floor_caps_the_rep_discount():
    q = dental("0.60")
    assert q.extra_discount_applied == D("0.1610")
    assert q.monthly == D("704.08")
    assert q.margin >= D("0.25")  # no slack: the floor holds exactly
    assert not any("even before" in w for w in q.warnings)
