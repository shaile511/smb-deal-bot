from datetime import date

import pytest

from account_watch import importer, sample, store

TODAY = date(2026, 11, 28)


@pytest.fixture
def engine(tmp_path):
    return store.get_engine(f"sqlite:///{tmp_path / 'aw.db'}")


def account(**overrides):
    base = {"company": "Harbour Bakery", "contact_email": "sam@harbour.example.com", "contact_name": "Sam",
            "closed_on": date(2026, 11, 20), "contract_end": date(2028, 11, 20), "internet": True}
    return {**base, **overrides}


def test_codes_come_from_the_row_id_once(engine):
    saved, _ = store.add_accounts(engine, [account(), account(company="Juniper Florist")], TODAY)
    assert [a["code"] for a in saved] == ["A-0001", "A-0002"]
    with engine.begin() as conn:  # removing a row never frees its code for reuse
        conn.execute(store.steps.delete())
        conn.execute(store.accounts.delete().where(store.accounts.c.id == saved[1]["id"]))
    again, _ = store.add_accounts(engine, [account(company="Cedar Florist")], TODAY)
    assert again[0]["code"] == "A-0003"


def test_same_company_and_email_is_skipped_in_any_case(engine):
    store.add_accounts(engine, [account()], TODAY)
    saved, skipped = store.add_accounts(engine, [account(company=" harbour bakery ",
                                                         contact_email="SAM@harbour.example.com")], TODAY)
    assert (saved, skipped) == ([], 1)
    assert store.count_accounts(engine) == 1


def test_new_account_gets_its_checklist_old_one_does_not(engine):
    new, _ = store.add_accounts(engine, [account()], TODAY)
    old, _ = store.add_accounts(engine, [account(company="Old Co", closed_on=date(2025, 1, 1))], TODAY)
    assert [s["key"] for s in store.list_steps(engine, new[0]["id"])] == ["welcome", "internet", "training", "checkin"]
    assert store.list_steps(engine, old[0]["id"]) == []


def test_sample_book_loads_and_tells_a_story(engine):
    saved, skipped = store.add_accounts(engine, sample.book(TODAY), TODAY)
    assert (len(saved), skipped) == (16, 0)
    names = {a["company"] for a in saved}
    assert {"Maple Ridge Dental", "Maple & Ember Bistro Group", "Corner Lantern Cafe"} <= names
    assert all(a["contact_email"].endswith("example.com") for a in saved)
    # Loading it again adds nothing.
    assert store.add_accounts(engine, sample.book(TODAY), TODAY) == ([], 16)


CSV = ("company,contact_email,closed_on,contract_end,monthly_value,internet,phone,mobile,tickets_90d,usage_change_pct\n"
       "Juniper Florist,ava@juniper.example.com,2026-11-20,2028-11-20,\"$1,310.50\",yes,Y,no,2,-5\n")


def test_csv_reads_values_and_yes_no():
    [row] = importer.parse(CSV.encode())
    assert row["monthly_value"] == 1310.5
    assert (row["internet"], row["phone"], row["mobile"]) == (True, True, False)
    assert row["closed_on"] == date(2026, 11, 20) and row["last_contact_on"] is None
    assert (row["tickets_90d"], row["usage_change_pct"]) == (2, -5)


def test_csv_from_excel_with_a_byte_order_mark_and_odd_headers():
    data = "﻿Company , Contact_Email,CLOSED_ON,contract_end\nA Co,a@a.example.com,2026-01-01,2027-01-01\n"
    assert importer.parse(data.encode("utf-8"))[0]["company"] == "A Co"


def test_template_parses():
    assert importer.parse(importer.TEMPLATE)[0]["company"] == "Juniper Florist"


def problems(text):
    with pytest.raises(importer.ImportProblem) as exc:
        importer.parse(text.encode() if isinstance(text, str) else text)
    return exc.value.problems


def test_missing_columns_named():
    assert problems("company,closed_on\nA,2026-01-01\n") == [
        "Missing columns: contact_email, contract_end. The first row must name the columns: company, "
        "contact_email, closed_on, contract_end (and optionally contact_name, industry, monthly_value, internet, "
        "phone, mobile, tickets_90d, usage_change_pct, last_contact_on)."]


def test_every_row_problem_is_listed_and_nothing_is_imported():
    text = ("company,contact_email,closed_on,contract_end,internet,tickets_90d,usage_change_pct,monthly_value\n"
            "A,a@a.example.com,2026-13-01,2027-01-01,yes,1,0,10\n"
            ",nobody,2026-01-01,2025-01-01,maybe,-1,-150,ten\n")
    assert problems(text) == [
        "Row 2: closed_on '2026-13-01' is not a date. Use YYYY-MM-DD, like 2027-03-31.",
        "Row 3: company is empty.",
        "Row 3: contact_email 'nobody' is not an email address.",
        "Row 3: contract_end 2025-01-01 must be after closed_on 2026-01-01.",
        "Row 3: internet 'maybe' should be yes or no.",
        "Row 3: monthly_value 'ten' is not a number.",
        "Row 3: tickets_90d -1 is outside 0 to 999.",
        "Row 3: usage_change_pct -150 is outside -100 to 1000.",
    ]


def test_empty_and_non_utf8_files():
    assert problems("company,contact_email,closed_on,contract_end\n\n") == ["The file has a header but no accounts."]
    assert problems("company\n".encode() + b"\xff\xfe\xfa") == ["The file is not UTF-8 text. In Excel, save it as 'CSV UTF-8'."]


def test_too_many_rows():
    rows = "".join(f"C{i},c{i}@x.example.com,2026-01-01,2027-01-01\n" for i in range(501))
    assert problems("company,contact_email,closed_on,contract_end\n" + rows) == ["More than 500 accounts. Split the file."]
