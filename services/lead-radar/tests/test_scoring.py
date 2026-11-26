from datetime import date

from lead_radar.generate import OUR_COMPANY, generate_leads
from lead_radar.scoring import months_until, rank_leads, score_lead

TODAY = date(2026, 11, 1)


def lead(**overrides):
    base = {
        "company": "Test Co",
        "industry": "Dental clinic",
        "employees": 25,
        "locations": 2,
        "current_provider": "Bluepeak Telecom",
        "contract_end": "2027-02",
    }
    return {**base, **overrides}


def test_months_until():
    assert months_until("2027-02", TODAY) == 3
    assert months_until("2026-10", TODAY) == -1
    assert months_until("", TODAY) is None


def test_ideal_lead_scores_high_with_reasons():
    s = score_lead(lead(), TODAY)
    # 20 size + 15 locations + 20 industry + 40 timing
    assert s.total == 95
    assert len(s.reasons) == 4
    assert any("best time to reach out" in r for r in s.reasons)


def test_timing_matters():
    soon = score_lead(lead(contract_end="2027-02"), TODAY).total
    late = score_lead(lead(contract_end="2028-06"), TODAY).total
    assert soon > late


def test_existing_customer_is_skipped():
    s = score_lead(lead(current_provider=OUR_COMPANY), TODAY)
    assert s.skip


def test_rank_is_sorted_and_drops_customers():
    leads = generate_leads(200, seed=7, today=TODAY)
    ranked = rank_leads(leads, TODAY)
    assert (ranked["current_provider"] != OUR_COMPANY).all()
    assert ranked["score"].is_monotonic_decreasing
    assert len(ranked) < len(leads)


def test_generator_is_repeatable_and_fake():
    a = generate_leads(50, seed=1, today=TODAY, include_featured=False)
    b = generate_leads(50, seed=1, today=TODAY, include_featured=False)
    assert a.equals(b)
    assert a["contact_email"].str.endswith("@example.com").all()


def test_featured_restaurants_are_in_the_list_and_rank_differently():
    leads = generate_leads(200, seed=42, today=TODAY)
    assert len(leads) == 200
    ranked = rank_leads(leads, TODAY).reset_index(drop=True)
    group = ranked.index[ranked["company"] == "Maple & Ember Bistro Group"][0]
    cafe = ranked.index[ranked["company"] == "Corner Lantern Cafe"][0]
    assert group < 10          # strong prospect lands in the top 10
    assert cafe > group        # small cafe on a home plan ranks lower
