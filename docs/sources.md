# Sources

Every price, MSP, scheme amount, deadline and distance the app shows traces to a page listed here, or is marked
**assumed**. Research was done on 24-25 Oct 2026; official pages or APIs that could not be read are identified below.
Machine-readable versions live in `knowledge/` next to each value.

## Sell + Watch lane

| Item | Value | Source | Quality |
|---|---|---|---|
| Wheat MSP, marketing season 2026-27 (on sale now) | Rs 2,585 per quintal (up Rs 160 from 2,425) | [PIB, Cabinet approves MSP for Rabi 2026-27, 1 Oct 2025](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2173566&reg=48&lang=2) | official |
| Wheat MSP, 2027-28 (next harvest) | Rs 2,610 (up Rs 25) | [All India Radio, 1 Oct 2026](https://newsonair.gov.in/union-cabinet-hikes-minimum-support-prices-for-rabi-crops-for-2027-28-marketing-season/) says "+Rs 25"; the absolute figure is from several outlets. PIB release not located | secondary |
| Mustard Rs 6,200, gram Rs 5,875 (2026-27) | | same PIB release | official |
| Mandi price source | [Agmarknet 2.0 Daily Price and Arrival Report](https://agmarknet.gov.in/daily-price-and-arrival-report), official report page; [official SPA bundle](https://agmarknet.gov.in/static/js/main.c1f86740.js) identifies API base `https://api.agmarknet.gov.in/v1/`, `GET /daily-price-arrival/filters`, and `POST /daily-price-arrival/report` | `knowledge/mandi_costs.yaml` | official page; **automated access unverified** |
| Agmarknet API access (checked 25 Oct 2026) | Filters endpoint returned HTTP 500 with a database error. Empty report request returned HTTP 400 and required CAPTCHA credentials. The official UI submits date, commodity, state, district, market, variety, grade, page and limit; it also handles CAPTCHA or a report ticket. | [Official report UI chunk](https://agmarknet.gov.in/static/js/9617.a6249d86.chunk.js) | live automated retrieval blocked/unverified; do not bypass CAPTCHA |
| data.gov.in mandi dataset | dataset page was not accessible in this check; an API endpoint/key and usable current response were not verified | [data.gov.in](https://data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi) | official dataset; automated access unverified |
| IMD district warning page | home page only; the district nowcast page URL is **not confirmed** | `knowledge/weather.yaml` | unverified |
| Freight rate | Rs 0.4 per quintal per km | none | **assumed** |
| Distances Meerut to Hapur, Baghpat, Muzaffarnagar, Bulandshahr, Delhi (Azadpur) | 35, 50, 55, 65, 70 km | none, approximate | **assumed** |
| Demo district | Meerut, Uttar Pradesh | a wheat-belt placeholder near the Delhi mandis | **assumed** |

## Subsidy + Claim lane

| Scheme or fact | Source | Notes |
|---|---|---|
| PM-KISAN Rs 6,000 a year in three Rs 2,000 instalments | [India.gov.in](https://services.india.gov.in/service/detail/pm-kisan-samman-nidhi), [state page](https://wb.gov.in/government-schemes-details-pradhan-mantri-kisan-samman-nidhi.aspx) | exclusion list not in the profile |
| PMFBY, 72-hour loss intimation | [Parliament answer](https://eparlib.nic.in/bitstream/123456789/977813/1/AU3866.pdf) | pmfby.gov.in could not be read; confirm with the insurer |
| National crop-insurance helpline 14447 | [district government memo](https://udalguri.assam.gov.in/sites/default/files/public_utility/COs.pdf), [Parliament](https://eparlib.sansad.in/bitstream/123456789/2985398/1/AU2508_gdhK8C.pdf) | an insurer page lists 1800-209-5959 for claims: confirm which applies |
| KCC, 2% subvention plus 3% prompt repayment on loans to Rs 3 lakh | [Rajya Sabha, 18 Mar 2025](https://rsdebate.nic.in/bitstream/123456789/759195/1/PQ_267_18032025_U2012_p327_p327.pdf) | Rs 5 lakh limit announced, not confirmed in force |
| Soil Health Card | [PIB document](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/aug/doc2025816613501.pdf) | cycle conflicts: 2 years or 3 years |
| PM-KUSUM, 30% central assistance | [SBI](https://www.sbi.co.in/web/agri-rural/agriculture-banking/government-schemes/pm-kusum-scheme-b-and-c), [PIB FAQ](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2022/jun/doc202261766501.pdf) | state share differs by source |
| PM Kisan Maandhan, age 18 to 40, up to 2 ha | [operational guidelines](https://Pmkisan.Gov.In/Documents/PM-KMY%20-%20Operational%20Guidelines.pdf) | age is not in the farmer profile, so eligibility is "needs info" |
| UP Krishi Yantra Anudan | [directory, not official](https://schemesinindia.in/schemes/uttar-pradesh/up-krishi-yantra-anudan-yojana) | rates conflict, so no amount is shown |

Seven schemes are researched, not the playbook's eight to ten. More come from `python -m app.cli discover`
(candidates are written `reviewed: false`). No scheme ships reviewed: a person runs
`python -m app.cli review <id> --reviewer "<name>"` after reading its sources.

## Platform

| Item | Finding | Source |
|---|---|---|
| TinyFish SDK, event shapes, limits, webhooks, monitors | CLAUDE.md section 6 | [docs.tinyfish.ai](https://docs.tinyfish.ai/llms.txt), `tinyfish` 0.11.0 |
| Monitor webhook body | **not documented**; both flat and `data`-nested shapes are accepted | |
| Bhashini request shapes | public pipeline docs, **never run against a live key** | |
