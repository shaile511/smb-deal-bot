"""The made-up price book for Northwind Connect, a fictional provider.

Every product, price and cost here is invented for the demo. Prices are monthly, in CAD.
`cost` is what the product costs the provider; it is used only for the margin floor check.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

PROVIDER = "Northwind Connect"
CURRENCY = "CAD"


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    price: Decimal  # per unit per month
    cost: Decimal  # per unit per month
    unit: str  # "location", "line" or "plan"


D = Decimal

INTERNET = {
    300: Product("NET-300", "Business Fibre 300", D("95.00"), D("52.00"), "location"),
    1000: Product("NET-1G", "Business Fibre 1 Gbps", D("145.00"), D("78.00"), "location"),
    3000: Product("NET-3G", "Business Fibre 3 Gbps", D("220.00"), D("125.00"), "location"),
}
PHONE_LINE = Product("VOIP-LINE", "Hosted phone line", D("28.00"), D("12.00"), "line")
MOBILE = {
    "essential": Product("MOB-50", "Mobile Essential 50 GB", D("55.00"), D("30.00"), "plan"),
    "unlimited": Product("MOB-UNL", "Mobile Unlimited", D("75.00"), D("41.00"), "plan"),
}
STATIC_IP = Product("ADD-IP", "Static IP address", D("15.00"), D("3.00"), "location")
MANAGED_WIFI = Product("ADD-WIFI", "Managed Wi-Fi", D("25.00"), D("10.00"), "location")
BACKUP_LTE = Product("ADD-LTE", "Backup LTE internet", D("30.00"), D("14.00"), "location")

INSTALL_FEE = D("199.00")  # one-time, per location; waived on 36-month terms

TERMS = {12: D("0"), 24: D("0.05"), 36: D("0.10")}  # discount on recurring charges

# Bundle: count how many of internet, phones and mobile are on the quote.
BUNDLE_DISCOUNT = {3: D("0.08"), 2: D("0.04")}

# Multi-line: per-line credit on phones, percentage off mobile.
PHONE_VOLUME_CREDIT = [(10, D("3.00"))]  # 10+ lines: $3 off each line
MOBILE_VOLUME_DISCOUNT = [(10, D("0.10")), (5, D("0.05"))]  # first matching tier wins

# The rep cannot discount below this gross margin on monthly charges.
MARGIN_FLOOR = D("0.25")
