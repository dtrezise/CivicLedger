#!/usr/bin/env python3
"""Build curated presidential OGE disclosure document and transaction indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_OUTPUT = ROOT / "data" / "disclosures" / "presidential_oge_documents.json"
TRANSACTION_OUTPUT = ROOT / "data" / "disclosures" / "presidential_oge_transactions.json"

USER_AGENT = "CivicLedger disclosure research bot contact: https://github.com/dtrezise/CivicLedger"
OGE_COLLECTION_URL = (
    "https://www.oge.gov/web/oge.nsf/Officials%20Individual%20Disclosures%20Search%20Collection?OpenForm="
)
OGE_PRESIDENT_2025_NOTICE = (
    "https://extapps2.oge.gov/web/oge.nsf/Resources/Available%2BNow%3A%2BThe%2BPresident"
    "%E2%80%99s%2Band%2BVice%2BPresident%E2%80%99s%2Bcertified%2Bannual%2Bfinancial%2Bdisclosure%2Breports"
)


CURATED_DOCUMENTS = [
    {
        "document_id": "oge-obama-2009-annual-278",
        "official_id": "exec:barack-obama",
        "full_name": "Barack Obama",
        "presidential_term": "obama-44",
        "report_year": 2009,
        "filing_type": "annual_sf278",
        "filing_label": "2009 Annual SF 278",
        "reported_date": "2010-05-17",
        "source_url": "https://obamawhitehouse.archives.gov/sites/default/files/rss_viewer/potus-278-2009.pdf",
        "source_notice_url": "https://obamawhitehouse.archives.gov/blog/2010/05/17/president-vice-presidents-financial-disclosure-forms",
        "expected_transaction_activity": "transaction_report",
        "source_transaction_section_status": "source_reviewed_transactions_present",
    },
    {
        "document_id": "oge-obama-2010-annual-278",
        "official_id": "exec:barack-obama",
        "full_name": "Barack Obama",
        "presidential_term": "obama-44",
        "report_year": 2010,
        "filing_type": "annual_sf278",
        "filing_label": "2010 Annual SF 278",
        "reported_date": "2011-05-16",
        "source_url": "https://obamawhitehouse.archives.gov/sites/default/files/rss_viewer/POTUS_OGE278_CY2010.pdf",
        "source_notice_url": "https://obamawhitehouse.archives.gov/blog/2011/05/16/president-vice-presidents-2010-financial-disclosure-forms",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_transaction_section_status": "source_reviewed_no_reportable_transactions",
    },
    {
        "document_id": "oge-obama-2011-annual-278",
        "official_id": "exec:barack-obama",
        "full_name": "Barack Obama",
        "presidential_term": "obama-44",
        "report_year": 2011,
        "filing_type": "annual_sf278",
        "filing_label": "2011 Annual SF 278",
        "reported_date": "2012-05-15",
        "source_url": "https://obamawhitehouse.archives.gov/sites/default/files/president_obama_2011_oge_form_278_certified.pdf",
        "source_notice_url": "https://obamawhitehouse.archives.gov/blog/2012/05/15/president-and-vice-presidents-2011-financial-disclosure-forms",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_transaction_section_status": "source_reviewed_no_reportable_transactions",
    },
    {
        "document_id": "oge-obama-2012-annual-278",
        "official_id": "exec:barack-obama",
        "full_name": "Barack Obama",
        "presidential_term": "obama-44",
        "report_year": 2012,
        "filing_type": "annual_sf278",
        "filing_label": "2012 Annual SF 278",
        "reported_date": "2013-05-15",
        "source_url": "https://obamawhitehouse.archives.gov/sites/default/files/docs/potus_278_certified_may_15_2013.pdf",
        "source_notice_url": "https://obamawhitehouse.archives.gov/blog/2013/05/15/president-and-vice-presidents-2012-financial-disclosure-forms",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_transaction_section_status": "source_reviewed_no_reportable_transactions",
    },
    {
        "document_id": "oge-obama-2013-annual-278",
        "official_id": "exec:barack-obama",
        "full_name": "Barack Obama",
        "presidential_term": "obama-44",
        "report_year": 2013,
        "filing_type": "annual_sf278",
        "filing_label": "2013 Annual SF 278",
        "reported_date": "2014-05-15",
        "source_url": "https://obamawhitehouse.archives.gov/sites/default/files/docs/potus_certified_278_cy2013_0.pdf",
        "source_notice_url": "https://obamawhitehouse.archives.gov/blog/2014/05/15/president-and-vice-president-s-2013-financial-disclosure-forms",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_transaction_section_status": "source_reviewed_no_reportable_transactions",
    },
    {
        "document_id": "oge-obama-2014-annual-278",
        "official_id": "exec:barack-obama",
        "full_name": "Barack Obama",
        "presidential_term": "obama-44",
        "report_year": 2014,
        "filing_type": "annual_sf278",
        "filing_label": "2014 Annual SF 278",
        "reported_date": "2015-05-15",
        "source_url": "https://obamawhitehouse.archives.gov/sites/default/files/docs/oge_278_cy_2014_obama.pdf",
        "source_notice_url": "https://obamawhitehouse.archives.gov/blog/2015/05/15/president-and-vice-president-s-2014-financial-disclosure-forms",
        "expected_transaction_activity": "transaction_report",
        "source_transaction_section_status": "source_reviewed_transactions_present",
    },
    {
        "document_id": "oge-obama-2015-annual-278",
        "official_id": "exec:barack-obama",
        "full_name": "Barack Obama",
        "presidential_term": "obama-44",
        "report_year": 2015,
        "filing_type": "annual_sf278",
        "filing_label": "2015 Annual SF 278",
        "reported_date": "2016-05-16",
        "source_url": "https://obamawhitehouse.archives.gov/sites/whitehouse.gov/files/documents/oge_278_cy_2015_obama_051616.pdf",
        "source_notice_url": "https://obamawhitehouse.archives.gov/blog/2016/05/16/president-and-vice-presidents-2015-financial-disclosure-forms",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_transaction_section_status": "source_reviewed_no_reportable_transactions",
    },
    {
        "document_id": "oge-obama-2017-termination-278",
        "official_id": "exec:barack-obama",
        "full_name": "Barack Obama",
        "presidential_term": "obama-44",
        "report_year": 2016,
        "filing_type": "termination_278e",
        "filing_label": "2017 Termination OGE Form 278",
        "reported_date": "2017-01-20",
        "coverage_start": "2016-01-01",
        "coverage_end": "2017-01-20",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/579DA54DF8BE5F24852580B4006318A9/%24FILE/Obama%2C%20Barack%20H.%20%20%202017Termination.pdf",
        "source_notice_url": "https://extapps2.oge.gov/201/Presiden.nsf/President%20and%20Vice%20President%20Index",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_transaction_section_status": "source_reviewed_no_reportable_transactions",
        "source_reviewed_without_live_pdf": True,
        "source_review_note": (
            "Schedule B, Part I, pages 6-7 of the 10-page filing checks None and "
            "contains no reportable purchase, sale, or exchange rows. The original OGE "
            "PDF is no longer served under the agency's disclosure-retention schedule."
        ),
    },
    {
        "document_id": "oge-biden-2021-annual-278",
        "official_id": "exec:joseph-r-biden",
        "full_name": "Joseph R. Biden",
        "presidential_term": "biden-46",
        "report_year": 2021,
        "filing_type": "annual_278e",
        "filing_label": "2021 Annual OGE Form 278e",
        "reported_date": "2021-05-17",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/9A9B9318751632FA852586D9002EC0F9/%24FILE/Biden%2C%20Joseph%20R.%20%202021%20Annual%20278.pdf",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_transaction_section_status": "source_reviewed_no_reportable_transactions",
    },
    {
        "document_id": "oge-biden-2022-annual-278",
        "official_id": "exec:joseph-r-biden",
        "full_name": "Joseph R. Biden",
        "presidential_term": "biden-46",
        "report_year": 2022,
        "filing_type": "annual_278e",
        "filing_label": "2022 Annual OGE Form 278e",
        "reported_date": "2022-05-16",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/E53C72B0E534B2E7852588410074776C/%24FILE/Biden%2C%20Joseph%20R.%20%202022%20Annual%20278.pdf",
        "expected_transaction_activity": "transaction_report",
        "source_transaction_section_status": "source_reviewed_transactions_present",
    },
    {
        "document_id": "oge-biden-2023-annual-278",
        "official_id": "exec:joseph-r-biden",
        "full_name": "Joseph R. Biden",
        "presidential_term": "biden-46",
        "report_year": 2023,
        "filing_type": "annual_278e",
        "filing_label": "2023 Annual OGE Form 278e",
        "reported_date": "2023-05-15",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/E0E994CFA156D7CF852589B000789259/%24FILE/Biden%2C%20Joseph%20R.%202023%20Annual%20278.pdf",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_transaction_section_status": "source_reviewed_no_reportable_transactions",
    },
    {
        "document_id": "oge-biden-2024-annual-278",
        "official_id": "exec:joseph-r-biden",
        "full_name": "Joseph R. Biden",
        "presidential_term": "biden-46",
        "report_year": 2024,
        "filing_type": "annual_278e",
        "filing_label": "2024 Annual OGE Form 278e",
        "reported_date": "2024-05-15",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/F19EEDB6A75522E785258B1E007CDCC6/%24FILE/Biden%2C%20Joseph%20R.%20%202024%20Annual%20278.pdf",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_transaction_section_status": "source_reviewed_no_reportable_transactions",
    },
    {
        "document_id": "oge-biden-2025-termination-278",
        "official_id": "exec:joseph-r-biden",
        "full_name": "Joseph R. Biden",
        "presidential_term": "biden-46",
        "report_year": 2025,
        "filing_type": "termination_278e",
        "filing_label": "2025 Termination OGE Form 278e",
        "reported_date": "2025-01-20",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/34A58BA5A7439CA485258C1A00613D05/%24FILE/Biden%2C%20Joseph%20R.%20%202025%20Termination%20278.pdf",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_transaction_section_status": "source_reviewed_no_reportable_transactions",
    },
    {
        "document_id": "oge-trump-2020-annual-278",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-45",
        "report_year": 2020,
        "filing_type": "annual_278e",
        "filing_label": "2020 Annual OGE Form 278e",
        "reported_date": "2020-07-31",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/181BAF52E298FD70852585B70027E054/%24FILE/Trump%2C%20Donald%20J.%202020Annual%20278.pdf",
        "expected_transaction_activity": "annual_report_review_required",
    },
    {
        "document_id": "oge-trump-2021-termination-278",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-45",
        "report_year": 2021,
        "filing_type": "termination_278e",
        "filing_label": "2021 Termination OGE Form 278e",
        "reported_date": "2021-01-20",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/6E78B163F816EF6A852586630075291D/%24FILE/Trump%2C%20Donald%20J.%202021Termination%20278.pdf",
        "expected_transaction_activity": "annual_report_review_required",
    },
    {
        "document_id": "oge-trump-2025-annual-278",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-47",
        "report_year": 2025,
        "filing_type": "annual_278e",
        "filing_label": "2025 Annual OGE Form 278e",
        "reported_date": "2025-06-13",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/4EC9A8E6DD078F2985258CA9002C9377/%24FILE/Trump%2C%20Donald%20J.%202025%20Annual%20278.pdf",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_notice_url": OGE_PRESIDENT_2025_NOTICE,
    },
    {
        "document_id": "oge-trump-2025-278t-2025-10-17",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-47",
        "report_year": 2025,
        "filing_type": "periodic_transaction_278t",
        "filing_label": "October 17, 2025 OGE Form 278-T",
        "reported_date": "2025-10-28",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/AA799A2729B4D1BE85258D430031A320/%24FILE/Donald%20J.%20Trump%2010.17.2025%20278-T.pdf",
        "expected_transaction_activity": "transaction_report",
    },
    {
        "document_id": "oge-trump-2026-278t-2026-05-08",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-47",
        "report_year": 2026,
        "filing_type": "periodic_transaction_278t",
        "filing_label": "May 8, 2026 OGE Form 278-T",
        "reported_date": "2026-05-12",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/405E4EC4E27BE8D185258DF7002DD1C0/%24FILE/Trump%2C%20Donald%20J.-05.08.2026-278T%282%29.pdf",
        "expected_transaction_activity": "transaction_report",
    },
    {
        "document_id": "oge-trump-2026-annual-278",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-47",
        "report_year": 2026,
        "filing_type": "annual_278e",
        "filing_label": "2026 Annual OGE Form 278e",
        "reported_date": "2026-05-15",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/69AEAA9D7455ACD585258E27002DDEE1/%24FILE/Donald-J-Trump-2026-278ANNUAL.pdf",
        "expected_transaction_activity": "annual_report_review_required",
        "transaction_parser_enabled": True,
        "cross_filing_reconciliation_required": True,
    },
]

MANUALLY_REVIEWED_TRANSACTIONS = {
    "oge-obama-2009-annual-278": [
        {
            "source_page": 6,
            "source_sequence": 1,
            "trade_date": "2009-06-16",
            "action": "SELL",
            "asset_display_name": "Vanguard FTSE Social Index Fund",
            "value_range_label": "$50,001 - $100,000",
        },
        {
            "source_page": 6,
            "source_sequence": 2,
            "trade_date": "2009-06-15",
            "action": "BUY",
            "asset_display_name": "Vanguard 500 Index Fund",
            "value_range_label": "$50,001 - $100,000",
        },
        {
            "source_page": 6,
            "source_sequence": 3,
            "trade_date": "2009-07-09",
            "action": "SELL",
            "asset_display_name": "Vanguard FTSE Social Index Fund (S)",
            "value_range_label": "$50,001 - $100,000",
        },
        {
            "source_page": 6,
            "source_sequence": 4,
            "trade_date": "2009-07-09",
            "action": "BUY",
            "asset_display_name": "Vanguard 500 Index Fund (S)",
            "value_range_label": "$50,001 - $100,000",
        },
        {
            "source_page": 6,
            "source_sequence": 5,
            "trade_date": "2009-07-09",
            "action": "SELL",
            "asset_display_name": "Vanguard FTSE Social Index Fund (S)",
            "value_range_label": "$15,001 - $50,000",
        },
        {
            "source_page": 7,
            "source_sequence": 1,
            "trade_date": "2009-07-09",
            "action": "BUY",
            "asset_display_name": "Vanguard 500 Index Fund (S)",
            "value_range_label": "$15,001 - $50,000",
        },
        {
            "source_page": 7,
            "source_sequence": 2,
            "trade_date": "2009-01-05",
            "action": "SELL",
            "asset_display_name": "Hawaiian Tax-Free Trust Class A (inheritance from the Estate of Madelyn Dunham)",
            "value_range_label": "$15,001 - $50,000",
        },
        {
            "source_page": 7,
            "source_sequence": 3,
            "trade_date": "2009-01-29",
            "action": "SELL",
            "asset_display_name": "Bank Hawaii Corp. (inheritance from the Estate of Madelyn Dunham)",
            "value_range_label": "$250,001 - $500,000",
        },
    ],
    "oge-obama-2014-annual-278": [
        {
            "source_page": 5,
            "source_sequence": 1,
            "trade_date": "2014-11-18",
            "action": "SELL",
            "asset_display_name": "Bright Directions College Savings 529 Plan (DC) (PIMCO Total Return 529 Portfolio PTTRX)",
            "value_range_label": "$50,001 - $100,000",
        },
        {
            "source_page": 5,
            "source_sequence": 2,
            "trade_date": "2014-11-18",
            "action": "BUY",
            "asset_display_name": "Bright Directions College Savings 529 Plan (DC) (Mainstay Total Return Bond 529 Fund MTMCX)",
            "value_range_label": "$50,001 - $100,000",
        },
        {
            "source_page": 5,
            "source_sequence": 3,
            "trade_date": "2014-11-18",
            "action": "SELL",
            "asset_display_name": "Bright Directions College Savings 529 Plan (DC) (PIMCO Total Return 529 Portfolio PTTRX)",
            "value_range_label": "$50,001 - $100,000",
        },
        {
            "source_page": 5,
            "source_sequence": 4,
            "trade_date": "2014-11-18",
            "action": "BUY",
            "asset_display_name": "Bright Directions College Savings 529 Plan (DC) (Mainstay Total Return Bond 529 Fund MTMCX)",
            "value_range_label": "$50,001 - $100,000",
        },
        {
            "source_page": 5,
            "source_sequence": 5,
            "trade_date": "2014-12-15",
            "action": "SELL",
            "asset_display_name": "Vanguard 500 Index Fund (Retirement)",
            "value_range_label": "$100,001 - $250,000",
        },
        {
            "source_page": 6,
            "source_sequence": 1,
            "trade_date": "2014-12-15",
            "action": "BUY",
            "asset_display_name": "Vanguard Institutional Index Fund (Retirement)",
            "value_range_label": "$100,001 - $250,000",
        },
        {
            "source_page": 6,
            "source_sequence": 2,
            "trade_date": "2014-12-15",
            "action": "SELL",
            "asset_display_name": "Vanguard 500 Index Fund (Retirement) (S)",
            "value_range_label": "$100,001 - $250,000",
        },
        {
            "source_page": 6,
            "source_sequence": 3,
            "trade_date": "2014-12-15",
            "action": "BUY",
            "asset_display_name": "Vanguard Institutional Index Fund (Retirement) (S)",
            "value_range_label": "$100,001 - $250,000",
        },
    ],
}

UNAVAILABLE_DOCUMENTS = []

AMOUNT_RE = re.compile(
    r"[$S]\s*([0-9][0-9,\s.]*)\s*[-\u2022]\s*[$S]?\s*([0-9][0-9,\s.]*)",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
TEXT_DATE_RE = re.compile(r"\b(\d{1,2})-([A-Za-z]{3})-(\d{4})\b")
DATE_TOKEN_RE = re.compile(r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-[A-Za-z]{3}-\d{4})\b")
ACTION_RE = re.compile(
    r"\b(purchase|purchas[eo]|ourch\w+|du?rch\w+|nurch\w+|sales?|sold|exchange)\b",
    re.IGNORECASE,
)
ROW_PREFIX_RE = re.compile(r"^\s*(\d{1,4})[.)]?\s+")
TRUSTEE_DECISION_AUTHORITY_NOTE = (
    "J.P. Morgan is the sole Trustee. Donald J. Trump retains an income interest only in the "
    "Family Trusts and has no investment decision authority."
)
ACCOUNT_LABEL_RE = re.compile(r"INVESTMENT\s+ACCOUNT\s*#\s*([A-Za-z0-9.-]+)", re.IGNORECASE)

TICKER_HINTS = {
    "ADOBE": "ADBE",
    "ADVANCED MICRO DEVICES": "AMD",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "APPLE": "AAPL",
    "BANK OF AMERICA": "BAC",
    "BOEING": "BA",
    "BROADCOM": "AVGO",
    "CITIGROUP": "C",
    "COINBASE": "COIN",
    "COMCAST": "CMCSA",
    "COSTCO": "COST",
    "CVS HEALTH": "CVS",
    "GOLDMAN": "GS",
    "HOME DEPOT": "HD",
    "INTEL": "INTC",
    "ISHARES GOLD TRUST": "IAU",
    "JOHNSON & JOHNSON": "JNJ",
    "JPMORGAN": "JPM",
    "META PLATFORMS": "META",
    "MICROSOFT": "MSFT",
    "MORGAN STANLEY": "MS",
    "NETFLIX": "NFLX",
    "NVIDIA": "NVDA",
    "ORACLE": "ORCL",
    "PROCTER": "PG",
    "SALESFORCE": "CRM",
    "SERVICENOW": "NOW",
    "STATE STREET SPDR S&P 500 TRUST": "SPY",
    "TESLA": "TSLA",
    "THE BOEING": "BA",
    "THE HOME DEPOT": "HD",
    "VANGUARD S&P 500 ETF": "VOO",
    "VANGUARD TOTAL STOCK MARKET": "VTI",
    "VISA": "V",
    "WALMART": "WMT",
    "WELLS FARGO": "WFC",
}


def clean_amount(value: str) -> int | None:
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    return int(digits)


def normalize_amount_label(label: str) -> tuple[str, int | None, int | None]:
    match = AMOUNT_RE.search(label)
    if not match:
        return (label.strip(), None, None)
    low = clean_amount(match.group(1))
    high = clean_amount(match.group(2))
    if low is None or high is None:
        return (label.strip(), low, high)
    return (f"${low:,} - ${high:,}", low, high)


def normalize_trade_date(value: str, report_year: int) -> tuple[str | None, bool]:
    match = DATE_RE.search(value)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        if year < 100:
            year += 2000
    else:
        text_match = TEXT_DATE_RE.search(value)
        if not text_match:
            return (None, False)
        day = int(text_match.group(1))
        month_names = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        month = month_names[text_match.group(2).lower()]
        year = int(text_match.group(3))
    corrected = False
    if year > report_year:
        year = report_year
        corrected = True
    try:
        return (date(year, month, day).isoformat(), corrected)
    except ValueError:
        return (None, False)


def action_from_text(value: str) -> str:
    action = ACTION_RE.search(value)
    if not action:
        return "UNKNOWN"
    token = action.group(1).lower()
    if token in {"sale", "sales", "sold"}:
        return "SELL"
    if token == "exchange":
        return "EXCHANGE"
    return "BUY"


def asset_class_for(description: str) -> str:
    value = description.upper()
    if "BITCOIN" in value or "ETHEREUM" in value or "CRYPTO" in value:
        return "crypto"
    if "ETF" in value or "EXCHANGE" in value or "VANGUARD" in value or "ISHARES" in value or "SPDR" in value:
        return "etf"
    if "DUE" in value or "B/E" in value or "BOND" in value or "REV" in value or "MUNI" in value or "GO " in value:
        return "fixed_income"
    if "MONEY FUND" in value or "FUND" in value or re.search(r"\b(?:FD|VIF|VIT)\b", value):
        return "fund"
    return "equity"


def ticker_for(description: str, asset_class: str) -> str | None:
    value = description.upper()
    for needle, ticker in TICKER_HINTS.items():
        if needle in value:
            return ticker
    # Disclosure descriptions usually name issuers rather than publishing ticker
    # symbols. Do not infer a ticker from the word preceding INC/CORP/PLC: that
    # produces false symbols such as GROUP, FOODS, and TRUST.
    return None


def cleaned_description(value: str) -> str:
    value = ROW_PREFIX_RE.sub("", value)
    value = ACTION_RE.split(value, maxsplit=1)[0]
    value = re.sub(r"\s+", " ", value).strip(" -|")
    return value[:220]


def normalize_ocr_line(value: str) -> str:
    value = re.sub(r"(?i)pur\s*cha\s*se", "Purchase", value)
    value = re.sub(r"(?i)sa\s*le", "Sale", value)
    value = re.sub(r"(\d{1,2}/\d{1,2}/\d{3})\s+(\d)\b", r"\1\2", value)
    value = re.sub(r"(\d{1,2})\s*-\s*([A-Za-z]{3})\s*-\s*(\d{4})", r"\1-\2-\3", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_transaction_lines(document: dict, text_by_page: list[dict]) -> list[dict]:
    supported_types = {"periodic_transaction_278t", "annual_278e", "termination_278e"}
    if document["filing_type"] not in supported_types or document.get("transaction_parser_enabled") is False:
        return []
    rows = []
    seen = set()
    for page in text_by_page:
        page_text = page["text"]
        if document["filing_type"] != "periodic_transaction_278t" and not re.search(
            r"Part\s*7\s*:\s*Transactions", page_text, re.IGNORECASE
        ):
            continue
        decision_authority_note = (
            TRUSTEE_DECISION_AUTHORITY_NOTE
            if "has no investment decision authority" in page_text
            else None
        )
        account_match = ACCOUNT_LABEL_RE.search(page_text)
        source_account_label = (
            f"Investment account #{account_match.group(1)}" if account_match else None
        )
        for line in page["text"].splitlines():
            normalized_line = normalize_ocr_line(
                re.sub(r"(\d{1,2})/(\d)\.(\d)/(\d{4})", r"\1/\2\3/\4", line)
            )
            if "$" not in normalized_line and "S" not in normalized_line:
                continue
            amount = AMOUNT_RE.search(normalized_line)
            action = ACTION_RE.search(normalized_line)
            date_matches = (
                [match for match in DATE_TOKEN_RE.finditer(normalized_line) if match.start() < amount.start()]
                if amount
                else []
            )
            if not amount or not date_matches or not action:
                continue
            trade_date, corrected = normalize_trade_date(date_matches[-1].group(0), document["report_year"])
            if not trade_date:
                continue
            disclosure_lag_days = (
                date.fromisoformat(document["reported_date"]) - date.fromisoformat(trade_date)
            ).days
            amount_label, amount_min, amount_max = normalize_amount_label(amount.group(0))
            description = cleaned_description(normalized_line)
            if not description:
                continue
            asset_class = asset_class_for(description)
            ticker = ticker_for(description, asset_class)
            source_sequence = None
            prefix = ROW_PREFIX_RE.search(line)
            if prefix:
                source_sequence = int(prefix.group(1))
            dedupe_key = (
                document["document_id"],
                page["page"],
                source_sequence,
                description,
                trade_date,
                amount_label,
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            sequence = len(rows) + 1
            rows.append(
                {
                    "id": f"{document['document_id']}:tx-{sequence:04d}",
                    "document_id": document["document_id"],
                    "official_id": document["official_id"],
                    "full_name": document["full_name"],
                    "presidential_term": document["presidential_term"],
                    "filing_type": document["filing_type"],
                    "filing_label": document["filing_label"],
                    "form_section": "Part 7: Transactions",
                    "source_account_label": source_account_label,
                    "source_sequence": source_sequence,
                    "trade_date": trade_date,
                    "reported_date": document["reported_date"],
                    "disclosure_lag_days": disclosure_lag_days,
                    "action": action_from_text(normalized_line),
                    "ticker": ticker,
                    "asset_display_name": description,
                    "asset_class": asset_class,
                    "value_range_label": amount_label,
                    "value_range_min": amount_min,
                    "value_range_max": amount_max,
                    "record_status": "official_oge_parser_preview_not_promoted",
                    "confidence_label": (
                        "Official OGE 278-T parser preview; review required"
                        if document["filing_type"] == "periodic_transaction_278t"
                        else "Official OGE annual/termination parser preview; review required"
                    ),
                    "parsing_confidence": 0.58 if corrected else 0.76,
                    "review_required_before_public_trade": True,
                    "public_production_trade": False,
                    "date_normalized_from_ocr": corrected,
                    "decision_authority_status": (
                        "report_states_no_investment_decision_authority"
                        if decision_authority_note
                        else "not_stated_in_transaction_page"
                    ),
                    "decision_authority_note": decision_authority_note,
                    "disclosure_attribution_note": (
                        "Reported on the official's public financial disclosure; ownership and "
                        "decision authority must be read from the source filing."
                    ),
                    "source_url": document["source_url"],
                    "source_page": page["page"],
                    "source_line_text": re.sub(r"\s+", " ", normalized_line).strip()[:350],
                }
            )
    return rows


ASSET_MATCH_STOP_WORDS = {
    "class",
    "co",
    "com",
    "common",
    "company",
    "corp",
    "corporation",
    "fund",
    "inc",
    "ltd",
    "new",
    "ordinary",
    "plc",
    "shares",
    "stock",
    "the",
    "trust",
}


def normalized_asset_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if token not in ASSET_MATCH_STOP_WORDS
    }


def asset_match_score(left: str, right: str) -> float:
    left_tokens = normalized_asset_tokens(left)
    right_tokens = normalized_asset_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    if left_tokens == right_tokens:
        return 1.0
    return len(left_tokens.intersection(right_tokens)) / len(left_tokens.union(right_tokens))


def cross_filing_key(row: dict) -> tuple:
    return (
        row.get("official_id"),
        row.get("trade_date"),
        row.get("action"),
        row.get("value_range_min"),
        row.get("value_range_max"),
    )


def reconcile_cross_filing_duplicates(transactions: list[dict]) -> dict:
    periodic_by_key: dict[tuple, list[dict]] = {}
    for row in transactions:
        row["timeline_inclusion"] = True
        row["cross_filing_duplicate"] = False
        if row.get("filing_type") == "periodic_transaction_278t":
            periodic_by_key.setdefault(cross_filing_key(row), []).append(row)

    duplicate_count = 0
    for row in transactions:
        if row.get("filing_type") not in {"annual_278e", "termination_278e"}:
            continue
        candidates = periodic_by_key.get(cross_filing_key(row), [])
        ranked = sorted(
            (
                (asset_match_score(row.get("asset_display_name", ""), candidate.get("asset_display_name", "")), candidate)
                for candidate in candidates
            ),
            key=lambda item: (item[0], item[1]["id"]),
            reverse=True,
        )
        if not ranked or ranked[0][0] < 0.85:
            continue
        score, duplicate_of = ranked[0]
        row["timeline_inclusion"] = False
        row["cross_filing_duplicate"] = True
        row["duplicate_of_transaction_id"] = duplicate_of["id"]
        row["cross_filing_match_score"] = round(score, 4)
        row["cross_filing_match_method"] = "date_action_amount_asset_tokens_v1"
        row["data_quality_flags"] = [
            *row.get("data_quality_flags", []),
            "cross_filing_duplicate_with_periodic_report",
        ]
        duplicate_count += 1

    return {
        "methodology_version": "oge-cross-filing-dedup-v1",
        "periodic_reference_transaction_count": sum(
            1 for row in transactions if row.get("filing_type") == "periodic_transaction_278t"
        ),
        "cross_filing_duplicate_count": duplicate_count,
        "timeline_included_transaction_count": sum(
            1 for row in transactions if row.get("timeline_inclusion") is True
        ),
    }


def manual_transaction_rows(document: dict) -> list[dict]:
    rows = []
    for sequence, source_row in enumerate(
        MANUALLY_REVIEWED_TRANSACTIONS.get(document["document_id"], []), start=1
    ):
        amount_label, amount_min, amount_max = normalize_amount_label(source_row["value_range_label"])
        asset_class = asset_class_for(source_row["asset_display_name"])
        rows.append(
            {
                "id": f"{document['document_id']}:tx-{sequence:04d}",
                "document_id": document["document_id"],
                "official_id": document["official_id"],
                "full_name": document["full_name"],
                "presidential_term": document["presidential_term"],
                "filing_type": document["filing_type"],
                "filing_label": document["filing_label"],
                "form_section": "Schedule B, Part I: Transactions",
                "source_sequence": source_row["source_sequence"],
                "trade_date": source_row["trade_date"],
                "reported_date": document["reported_date"],
                "disclosure_lag_days": (
                    date.fromisoformat(document["reported_date"])
                    - date.fromisoformat(source_row["trade_date"])
                ).days,
                "action": source_row["action"],
                "ticker": None,
                "asset_display_name": source_row["asset_display_name"],
                "asset_class": asset_class,
                "value_range_label": amount_label,
                "value_range_min": amount_min,
                "value_range_max": amount_max,
                "record_status": "official_archive_manual_review_preview_not_promoted",
                "confidence_label": (
                    "Official archive source-page transcription; second review required"
                ),
                "parsing_confidence": 0.95,
                "review_required_before_public_trade": True,
                "public_production_trade": False,
                "date_normalized_from_ocr": False,
                "decision_authority_status": "not_stated_in_transaction_page",
                "decision_authority_note": None,
                "disclosure_attribution_note": (
                    "Reported on the official's public financial disclosure; filer, spouse, or "
                    "dependent ownership is preserved where the source row identifies it."
                ),
                "source_url": document["source_url"],
                "source_page": source_row["source_page"],
                "source_line_text": None,
                "normalization_method": "manual_source_page_transcription",
            }
        )
    return rows


def fetch_pdf(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        return response.read()


def extract_pdf_text(content: bytes) -> tuple[list[dict], int]:
    reader = PdfReader(BytesIO(content))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": index, "text": text})
    return pages, len(reader.pages)


def transaction_section_status(
    document: dict,
    text_by_page: list[dict],
    transactions: list[dict],
) -> str:
    if document.get("transaction_parser_enabled") is False:
        return "deduplication_review_required"
    reviewed_status = document.get("source_transaction_section_status")
    if transactions:
        return "transactions_detected"
    if reviewed_status == "source_reviewed_no_reportable_transactions":
        return "no_reportable_transactions"
    if reviewed_status == "source_reviewed_transactions_present":
        return "reviewed_transactions_pending_normalization"

    for page in text_by_page:
        if re.search(
            r"(?:Part\s*7\s*:\s*Transactions|Schedule\s*B).{0,1200}\bNone\b",
            page["text"],
            re.IGNORECASE | re.DOTALL,
        ):
            return "no_reportable_transactions"
    if not any(page["text"].strip() for page in text_by_page):
        return "image_only_review_required"
    return "transaction_section_not_detected"


def document_from_pdf(document: dict, content: bytes) -> tuple[dict, list[dict]]:
    text_by_page, page_count = extract_pdf_text(content)
    text_sample = "\n".join(page["text"] for page in text_by_page[:3])
    transactions = parse_transaction_lines(document, text_by_page) + manual_transaction_rows(document)
    transaction_actions = Counter(row["action"] for row in transactions)
    asset_classes = Counter(row["asset_class"] for row in transactions)
    section_status = transaction_section_status(document, text_by_page, transactions)
    if transactions and any(row.get("normalization_method") for row in transactions):
        parser_status = "manual_review_preview"
    elif transactions:
        parser_status = "parsed_preview"
    elif section_status == "no_reportable_transactions":
        parser_status = "no_reportable_transactions"
    elif section_status == "image_only_review_required":
        parser_status = "ocr_review_required"
    elif section_status == "deduplication_review_required":
        parser_status = "deduplication_review_required"
    else:
        parser_status = "document_indexed"
    result = {
        **document,
        "source_tier": "official",
        "source_collection_url": OGE_COLLECTION_URL,
        "archive_status": "official_source_linked_not_committed",
        "content_type": "application/pdf",
        "byte_count": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "page_count": page_count,
        "parser_status": parser_status,
        "transaction_section_status": section_status,
        "review_status": "review_required_before_public_trade",
        "review_required_before_public_trade": True,
        "public_production_trade_count": 0,
        "transaction_summary": {
            "parser_preview_transaction_count": len(transactions),
            "parser_preview_actions": dict(sorted(transaction_actions.items())),
            "asset_class_counts": dict(sorted(asset_classes.items())),
            "source_account_counts": dict(
                sorted(
                    Counter(
                        row["source_account_label"]
                        for row in transactions
                        if row.get("source_account_label")
                    ).items()
                )
            ),
            "no_transaction_hint": section_status == "no_reportable_transactions",
        },
        "parser_preview": re.sub(r"\s+", " ", text_sample).strip()[:700],
    }
    return result, transactions


def load_existing_documents() -> tuple[dict, dict]:
    if DOCUMENT_OUTPUT.exists() and TRANSACTION_OUTPUT.exists():
        return (json.loads(DOCUMENT_OUTPUT.read_text()), json.loads(TRANSACTION_OUTPUT.read_text()))
    return ({}, {})


def build(refresh: bool) -> tuple[dict, dict]:
    existing_documents, existing_transactions = load_existing_documents()
    if not refresh and existing_documents and existing_transactions:
        return (existing_documents, existing_transactions)

    documents = []
    transactions = []
    failures = []
    for document in CURATED_DOCUMENTS:
        if document.get("source_reviewed_without_live_pdf"):
            documents.append(
                {
                    **document,
                    "source_tier": "official",
                    "source_collection_url": OGE_COLLECTION_URL,
                    "archive_status": "official_source_reviewed_retention_expired",
                    "content_type": "application/pdf",
                    "parser_status": "no_reportable_transactions",
                    "transaction_section_status": "no_reportable_transactions",
                    "review_status": "source_reviewed_no_reportable_transactions",
                    "review_required_before_public_trade": False,
                    "public_production_trade_count": 0,
                    "transaction_summary": {
                        "parser_preview_transaction_count": 0,
                        "parser_preview_actions": {},
                        "asset_class_counts": {},
                        "source_account_counts": {},
                        "no_transaction_hint": True,
                    },
                    "parser_preview": document.get("source_review_note", ""),
                }
            )
            continue
        try:
            content = fetch_pdf(document["source_url"])
            parsed_document, parsed_transactions = document_from_pdf(document, content)
            documents.append(parsed_document)
            transactions.extend(parsed_transactions)
        except Exception as exc:  # pragma: no cover - defensive for live source outages.
            failures.append({"document_id": document["document_id"], "error": f"{type(exc).__name__}: {exc}"})
            documents.append(
                {
                    **document,
                    "source_tier": "official",
                    "source_collection_url": OGE_COLLECTION_URL,
                    "archive_status": "official_source_linked_fetch_failed",
                    "parser_status": "fetch_failed",
                    "review_status": "review_required_before_public_trade",
                    "review_required_before_public_trade": True,
                    "public_production_trade_count": 0,
                    "transaction_summary": {"parser_preview_transaction_count": 0},
                }
            )

    reconciliation = reconcile_cross_filing_duplicates(transactions)
    transactions_by_document = Counter(row["document_id"] for row in transactions)
    timeline_transactions_by_document = Counter(
        row["document_id"] for row in transactions if row.get("timeline_inclusion") is True
    )
    duplicates_by_document = Counter(
        row["document_id"] for row in transactions if row.get("cross_filing_duplicate") is True
    )
    for document in documents:
        summary = document.setdefault("transaction_summary", {})
        document_id = document["document_id"]
        summary["parser_preview_transaction_count"] = transactions_by_document[document_id]
        summary["timeline_included_transaction_count"] = timeline_transactions_by_document[document_id]
        summary["cross_filing_duplicate_count"] = duplicates_by_document[document_id]

    document_counts = Counter(row["official_id"] for row in documents)
    term_counts = Counter(row["presidential_term"] for row in documents)
    transaction_counts = Counter(row["official_id"] for row in transactions)
    timeline_transactions = [row for row in transactions if row.get("timeline_inclusion") is True]
    timeline_transaction_counts = Counter(row["official_id"] for row in timeline_transactions)
    document_index = {
        "generated_at": date.today().isoformat(),
        "schema_version": "presidential-oge-documents-v1",
        "context_label": (
            "Curated official OGE presidential disclosure documents. Parsed transaction rows are previews "
            "and require review before public production promotion."
        ),
        "source": {
            "id": "oge-individual-disclosures",
            "name": "OGE Officials' Individual Disclosures",
            "collection_url": OGE_COLLECTION_URL,
            "source_tier": "official",
            "use_restrictions_preserved": True,
        },
        "summary": {
            "document_count": len(documents),
            "unavailable_official_count": len(UNAVAILABLE_DOCUMENTS),
            "parser_preview_transaction_count": len(transactions),
            "timeline_included_transaction_count": len(timeline_transactions),
            "cross_filing_duplicate_count": reconciliation["cross_filing_duplicate_count"],
            "public_production_trade_count": 0,
            "document_counts_by_official": dict(sorted(document_counts.items())),
            "document_counts_by_term": dict(sorted(term_counts.items())),
            "fetch_failure_count": len(failures),
        },
        "unavailable_documents": UNAVAILABLE_DOCUMENTS,
        "documents": sorted(documents, key=lambda row: (row["official_id"], row["report_year"], row["document_id"])),
        "failures": failures,
    }
    transaction_index = {
        "generated_at": date.today().isoformat(),
        "schema_version": "presidential-oge-transactions-v1",
        "context_label": (
            "Official OGE annual, termination, and periodic parser-preview transaction rows plus "
            "source-page transcriptions for timeline exploration only; review is required before "
            "production trade promotion."
        ),
        "summary": {
            "parser_preview_transaction_count": len(transactions),
            "public_production_trade_count": 0,
            "review_required_transaction_count": len(transactions),
            "transaction_counts_by_official": dict(sorted(transaction_counts.items())),
            "timeline_transaction_counts_by_official": dict(
                sorted(timeline_transaction_counts.items())
            ),
            "transaction_counts_by_document": dict(sorted(transactions_by_document.items())),
            "asset_class_counts": dict(sorted(Counter(row["asset_class"] for row in transactions).items())),
            **reconciliation,
        },
        "transactions": sorted(transactions, key=lambda row: (row["official_id"], row["trade_date"], row["id"])),
    }
    return (document_index, transaction_index)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Fetch official OGE PDFs and regenerate parser previews. Without this, existing JSON is reused.",
    )
    args = parser.parse_args()
    documents, transactions = build(refresh=args.refresh)
    DOCUMENT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DOCUMENT_OUTPUT.write_text(json.dumps(documents, indent=2, sort_keys=True) + "\n")
    TRANSACTION_OUTPUT.write_text(json.dumps(transactions, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {DOCUMENT_OUTPUT}")
    print(f"Wrote {TRANSACTION_OUTPUT}")


if __name__ == "__main__":
    main()
