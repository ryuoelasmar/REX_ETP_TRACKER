"""
ETP Trust CIK Registry

Each trust we monitor for filings. CIKs sourced from SEC EDGAR.
"""
from __future__ import annotations

# CIK -> Trust Name (override SEC's name if needed)
# Verified against SEC EDGAR on 2026-02-06
# To add a new trust:
#   1. Search https://efts.sec.gov/LATEST/search-index?q="Trust+Name"&forms=485BPOS
#   2. Get the CIK from the result
#   3. Verify at https://data.sec.gov/submissions/CIK{padded_10_digits}.json
#   4. Add entry below and re-run pipeline
TRUST_CIKS = {
    "2043954": "REX ETF Trust",
    "1424958": "Direxion Shares ETF Trust",
    "1040587": "Direxion Funds",
    "1174610": "ProShares Trust",
    "1689873": "GraniteShares ETF Trust",
    "1884021": "Volatility Shares Trust",
    "1976517": "Roundhill ETF Trust",
    "1924868": "Tidal Trust II",
    "1540305": "ETF Series Solutions",
    "1976322": "Themes ETF Trust",
    "1771146": "ETF Opportunities Trust",  # Tuttle/T-REX products
    "1452937": "Exchange Traded Concepts Trust",
    "1587982": "Investment Managers Series Trust II",
    "1547950": "Exchange Listed Funds Trust",
    "1579881": "Calamos ETF Trust",
    "826732": "Calamos Investment Trust",
    # Added 2026-02-12 via EDGAR search for leveraged ETF issuers
    "1782952": "Kurv ETF Trust",
    "1722388": "Tidal Trust III",  # Battle Shares and other leveraged products
    "1683471": "Listed Funds Trust",  # Teucrium 2x crypto products
    "1396092": "World Funds Trust",  # T-REX 2x products
    # Added 2026-02-17 - Leveraged & Inverse ETFs (verified against SEC submissions JSON)
    "1415726": "Innovator ETFs Trust",  # Buffer/defined outcome ETFs
    "1329377": "First Trust Exchange-Traded Fund",
    "1364608": "First Trust Exchange-Traded Fund II",
    "1424212": "First Trust Exchange-Traded Fund III",
    "1517936": "First Trust Exchange-Traded Fund IV",
    "1561785": "First Trust Exchange-Traded Fund VII",
    "1667919": "First Trust Exchange-Traded Fund VIII",
    "1742912": "Tidal Trust I",  # YieldMax and other Tidal products
    "1592900": "EA Series Trust",  # ARK/21Shares digital asset strategy ETFs
    "1378872": "Invesco Exchange-Traded Fund Trust II",
    "1418144": "Invesco Actively Managed Exchange-Traded Fund Trust",
    "1067839": "Invesco QQQ Trust Series 1",  # QQQ - Nasdaq 100
    # Covered Call / Income ETFs
    "1432353": "Global X Funds",  # QYLD, XYLD, RYLD covered call ETFs
    "1485894": "J.P. Morgan Exchange-Traded Fund Trust",  # JEPI, JEPQ
    "1479026": "Goldman Sachs ETF Trust",
    "1882879": "Goldman Sachs ETF Trust II",
    "1848758": "NEOS ETF Trust",  # Enhanced income ETFs
    "1810747": "Simplify Exchange Traded Funds",  # Options-based income
    # Multi-Strategy Platforms
    "1137360": "VanEck ETF Trust",
    "1350487": "WisdomTree Trust",
    "1579982": "ARK ETF Trust",  # ARK Innovation, Genomics, etc.
    "1655589": "Franklin Templeton ETF Trust",
    "1657201": "Invesco Exchange-Traded Self-Indexed Fund Trust",
    "1419139": "Invesco India Exchange-Traded Fund Trust",
    "1595386": "Invesco Actively Managed Exchange-Traded Commodity Fund Trust",
    # Crypto (485-series filers)
    "1976672": "Grayscale Funds Trust",  # Multi-ETF trust (BTC Covered Call etc.)
    "1928561": "Bitwise Funds Trust",  # Multiple Bitwise 485 ETFs
    "1877493": "Valkyrie ETF Trust II",  # CoinShares digital asset ETFs
    # Crypto Commodity Trusts (S-1/10-K filers - no 485 forms, tracked for completeness)
    "1588489": "Grayscale Bitcoin Trust ETF",  # GBTC
    "2015034": "Grayscale Bitcoin Mini Trust ETF",
    "1980994": "iShares Bitcoin Trust ETF",  # IBIT
    "1852317": "Fidelity Wise Origin Bitcoin Fund",  # FBTC
    "1838028": "VanEck Bitcoin ETF",  # HODL
    "1763415": "Bitwise Bitcoin ETF",  # BITB
    "1992870": "Franklin Templeton Digital Holdings Trust",  # EZBC
    "1869699": "Ark 21Shares Bitcoin ETF",  # ARKB
    "1841175": "CoinShares Bitcoin ETF",  # BRRR
    "1850391": "WisdomTree Bitcoin Fund",  # BTCW
    "1725210": "Grayscale Ethereum Staking ETF",  # ETHE
    "2020455": "Grayscale Ethereum Staking Mini ETF",
    "2000638": "iShares Ethereum Trust ETF",  # ETHA
    "2000046": "Fidelity Ethereum Fund",  # FETH
    "1860788": "VanEck Ethereum ETF",  # ETHV
    "2011535": "Franklin Ethereum Trust",  # EZET
    "1732409": "Grayscale Bitcoin Cash Trust",  # BCH
    "1705181": "Grayscale Ethereum Classic Trust",  # ETC
    "1732406": "Grayscale Litecoin Trust",  # LTC
    "1896677": "Grayscale Solana Staking ETF",  # SOL
    "2037427": "Grayscale XRP Trust ETF",  # XRP
    "1723788": "Bitwise 10 Crypto Index ETF",  # BITW
}

def get_all_ciks() -> list[str]:
    """Return list of all CIKs to track."""
    return list(TRUST_CIKS.keys())

def get_overrides() -> dict[str, str]:
    """Return CIK -> Trust Name overrides."""
    return TRUST_CIKS.copy()


def add_trust(cik: str, name: str) -> bool:
    """Add a trust to the registry file. Returns True if added, False if already exists."""
    cik = str(cik).strip()
    if cik in TRUST_CIKS:
        return False

    # Update in-memory dict
    TRUST_CIKS[cik] = name

    # Write to the file so it persists across restarts
    import pathlib
    trusts_file = pathlib.Path(__file__)
    content = trusts_file.read_text(encoding="utf-8")

    # Insert new entry before the closing brace of TRUST_CIKS
    new_entry = f'    "{cik}": "{name}",\n'
    content = content.replace("\n}\n", f"\n{new_entry}}}\n", 1)

    trusts_file.write_text(content, encoding="utf-8")
    return True
