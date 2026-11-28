"""Turn confirmed customer needs into a priced quote, using the rules in price_book.py.

Order of rules, so a reviewer can follow the maths:
1. List price for each line.
2. Volume: phone line credit, mobile percentage.
3. Bundle discount on everything that is left.
4. Term discount (12, 24 or 36 months) on what is left.
5. Optional extra rep discount, capped so the margin never drops below the floor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from . import price_book as pb

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Needs:
    company: str = ""
    contact_name: str = ""
    contact_email: str = ""
    staff: int = 0
    locations: int = 1
    internet_speed: int | None = 1000  # 300, 1000, 3000 or None for no internet
    phone_lines: int = 0
    mobile_lines: int = 0
    mobile_plan: str = "essential"  # "essential" or "unlimited"
    static_ip: bool = False
    managed_wifi: bool = False
    backup_internet: bool = False
    term_months: int = 36
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Needs":
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)


@dataclass
class Line:
    code: str
    description: str
    quantity: int
    unit_price: Decimal
    monthly: Decimal
    cost: Decimal


@dataclass
class Adjustment:
    label: str
    amount: Decimal  # negative = discount


@dataclass
class Quote:
    lines: list[Line]
    adjustments: list[Adjustment]
    list_monthly: Decimal
    monthly: Decimal
    monthly_cost: Decimal
    one_time: Decimal
    term_months: int
    extra_discount_requested: Decimal
    extra_discount_applied: Decimal
    warnings: list[str] = field(default_factory=list)

    @property
    def margin(self) -> Decimal:
        if self.monthly == 0:
            return Decimal("0")
        return (self.monthly - self.monthly_cost) / self.monthly

    @property
    def term_total(self) -> Decimal:
        return money(self.monthly * self.term_months + self.one_time)

    @property
    def savings(self) -> Decimal:
        return money(self.list_monthly - self.monthly)

    @property
    def max_extra_discount(self) -> Decimal:
        """Largest extra discount (as a fraction) that keeps the margin at the floor."""
        before = self.monthly / (1 - self.extra_discount_applied) if self.extra_discount_applied < 1 else self.monthly
        if before == 0:
            return Decimal("0")
        # (before*(1-x) - cost) / (before*(1-x)) >= floor  ->  x <= 1 - cost / (before*(1-floor))
        limit = 1 - self.monthly_cost / (before * (1 - pb.MARGIN_FLOOR))
        return max(Decimal("0"), limit.quantize(Decimal("0.0001"), rounding="ROUND_DOWN"))


def _lines(needs: Needs) -> list[Line]:
    lines: list[Line] = []
    locs = max(1, int(needs.locations))

    def add(product: pb.Product, qty: int, description: str | None = None) -> None:
        if qty <= 0:
            return
        lines.append(Line(product.code, description or product.name, qty, product.price,
                          money(product.price * qty), product.cost * qty))

    if needs.internet_speed:
        add(pb.INTERNET[int(needs.internet_speed)], locs)
        if needs.static_ip:
            add(pb.STATIC_IP, locs)
        if needs.managed_wifi:
            add(pb.MANAGED_WIFI, locs)
        if needs.backup_internet:
            add(pb.BACKUP_LTE, locs)
    add(pb.PHONE_LINE, int(needs.phone_lines))
    add(pb.MOBILE[needs.mobile_plan], int(needs.mobile_lines))
    return lines


def build_quote(needs: Needs, extra_discount: Decimal | float | str = 0) -> Quote:
    if needs.term_months not in pb.TERMS:
        raise ValueError(f"Term must be one of {sorted(pb.TERMS)} months")
    extra = Decimal(str(extra_discount))
    lines = _lines(needs)
    adjustments: list[Adjustment] = []
    warnings: list[str] = []

    list_monthly = sum((l.monthly for l in lines), Decimal("0"))
    cost = sum((l.cost for l in lines), Decimal("0"))
    running = list_monthly

    # 2. Volume
    phones = [l for l in lines if l.code == pb.PHONE_LINE.code]
    for threshold, credit in pb.PHONE_VOLUME_CREDIT:
        if phones and phones[0].quantity >= threshold:
            amount = money(credit * phones[0].quantity)
            adjustments.append(Adjustment(f"Multi-line credit: {phones[0].quantity} phone lines x ${credit}", -amount))
            running -= amount
            break
    mobiles = [l for l in lines if l.code.startswith("MOB")]
    for threshold, pct in pb.MOBILE_VOLUME_DISCOUNT:
        if mobiles and mobiles[0].quantity >= threshold:
            amount = money(mobiles[0].monthly * pct)
            adjustments.append(Adjustment(f"Multi-line discount: {mobiles[0].quantity} mobile plans, {pct:.0%}", -amount))
            running -= amount
            break

    # 3. Bundle
    families = sum([bool(needs.internet_speed), int(needs.phone_lines) > 0, int(needs.mobile_lines) > 0])
    bundle = pb.BUNDLE_DISCOUNT.get(families)
    if bundle:
        amount = money(running * bundle)
        adjustments.append(Adjustment(f"Bundle discount: {families} services, {bundle:.0%}", -amount))
        running -= amount

    # 4. Term
    term_pct = pb.TERMS[needs.term_months]
    if term_pct:
        amount = money(running * term_pct)
        adjustments.append(Adjustment(f"{needs.term_months}-month term, {term_pct:.0%}", -amount))
        running -= amount

    # 5. Extra rep discount, capped at the margin floor
    applied = Decimal("0")
    if extra > 0 and running > 0:
        limit = 1 - cost / (running * (1 - pb.MARGIN_FLOOR))
        limit = max(Decimal("0"), limit.quantize(Decimal("0.0001"), rounding="ROUND_DOWN"))
        applied = min(extra, limit)
        if applied < extra:
            warnings.append(
                f"Extra discount capped at {applied:.1%} (asked for {extra:.1%}) to keep the margin at "
                f"the {pb.MARGIN_FLOOR:.0%} floor."
            )
        if applied > 0:
            # Round the rep discount down to the cent: rounding it up could tip the margin a
            # fraction of a cent under the floor.
            amount = (running * applied).quantize(CENT, rounding=ROUND_DOWN)
            adjustments.append(Adjustment(f"Rep discount, {applied:.1%}", -amount))
            running -= amount

    monthly = money(running)
    if applied == 0 and monthly > 0 and (monthly - cost) / monthly < pb.MARGIN_FLOOR:
        warnings.append(f"Margin is below the {pb.MARGIN_FLOOR:.0%} floor even before any rep discount.")

    locs = max(1, int(needs.locations)) if needs.internet_speed else 0
    one_time = money(pb.INSTALL_FEE * locs)
    if one_time and needs.term_months == 36:
        adjustments.append(Adjustment(f"Installation waived on a 36-month term (was ${one_time})", Decimal("0")))
        one_time = Decimal("0.00")
    if not lines:
        warnings.append("Nothing to quote yet: add internet, phone lines or mobile plans.")

    return Quote(lines, adjustments, money(list_monthly), monthly, cost, one_time, needs.term_months,
                 extra, applied, warnings)
