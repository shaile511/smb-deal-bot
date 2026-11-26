# Fake data rules

Everything in this repo is invented. No exceptions.

- Companies, people, emails and phone numbers are generated with [Faker](https://faker.readthedocs.io/) or written by hand.
- The provider in every demo is "Northwind Connect", a fictional company.
- The price book uses made-up products and round prices. It is not based on any real provider's pricing.
- No real employer names, logos, prices, product codes, internal tools, email templates or customer details, even paraphrased.

The generator script arrives with Lead Radar.

## How realistic is it?

The generator is fake row by row but shaped like real Canadian small businesses:

| What | Matches | Source |
| --- | --- | --- |
| Staff size | 59% have 1-4 employees, 18% 5-9, 11% 10-19, 7% 20-49, 2.5% 50-99 | [ISED Key Small Business Statistics 2025](https://ised-isde.canada.ca/site/sme-research-statistics/en/key-small-business-statistics/key-small-business-statistics-2025), Table 2 (Dec 2024) |
| Industry mix | Construction, professional services and health care are the largest groups | Same source, Table 3 |
| Contract end | When a fixed term ends, service rolls to month-to-month, so "contract ended" means "can switch now" | [Rogers Small Business Terms of Service](https://rogers.com/support/terms/rogers-small-business-terms-of-service-and-other-important-information), section 2 |
| Locations per business | **Guess.** No public Canadian figure found | n/a |
| Share on consumer plans | **Guess:** about 1 in 4 under 10 staff, none above 20. No Canadian figure found; an Australian NBN Co report puts it at 83% of small businesses | [WhistleOut, Sept 2026](https://www.whistleout.com.au/Broadband/News/Most-small-businesses-are-using-consumer-NBN-plans) |

Only the ten industries the tool models are generated, so each one's share is higher than in the full economy.
