from __future__ import annotations
import pandas as pd
from datetime import datetime
from .paths import output_paths_for_trust
from .utils import clean_fund_name_for_rollup, titlecase_safe

def _determine_status(row: pd.Series) -> tuple[str, str]:
    """
    Determine fund status based on filing type and dates.

    Returns: (status, status_reason)
        Status values:
        - EFFECTIVE: Fund has launched (485BPOS filed)
        - PENDING: Initial filing, waiting for effectiveness
        - DELAYED: Has delaying amendment
        - UNKNOWN: Cannot determine
    """
    form = str(row.get("Form", "")).upper()
    eff_date = str(row.get("Effective Date", "")).strip()
    delaying = str(row.get("Delaying Amendment", "")).upper() == "Y"
    filing_date = str(row.get("Filing Date", "")).strip()

    # Parse effective date if present
    eff_dt = None
    if eff_date:
        try:
            eff_dt = pd.to_datetime(eff_date, errors="coerce")
            if pd.isna(eff_dt):
                eff_dt = None
        except Exception:
            pass

    today = datetime.now()

    # 485BPOS = Post-effective amendment (fund is trading)
    if form.startswith("485B") and "POS" in form:
        return "EFFECTIVE", "485BPOS filed (fund trading)"

    # 485BXT = Extension of time with new effective date
    if form.startswith("485B") and "XT" in form:
        if delaying:
            return "DELAYED", "485BXT with delaying amendment"
        if eff_dt:
            if eff_dt.date() <= today.date():
                return "EFFECTIVE", f"485BXT effective as of {eff_date}"
            else:
                return "PENDING", f"485BXT effective date {eff_date} is future"
        return "PENDING", "485BXT filed (awaiting effectiveness)"

    # 485APOS = Initial filing
    if form.startswith("485A"):
        if delaying:
            return "DELAYED", "485APOS with delaying amendment"
        if eff_dt:
            if eff_dt.date() <= today.date():
                return "EFFECTIVE", f"485APOS effective as of {eff_date}"
            else:
                return "PENDING", f"485APOS effective date {eff_date} is future"
        # Default: 75 days from filing
        if filing_date:
            try:
                fdt = pd.to_datetime(filing_date, errors="coerce")
                if not pd.isna(fdt):
                    default_eff = fdt + pd.Timedelta(days=75)
                    if default_eff.date() <= today.date():
                        return "EFFECTIVE", f"485APOS presumed effective (+75 days)"
                    else:
                        return "PENDING", f"485APOS +75 day period not elapsed"
            except Exception:
                pass
        return "PENDING", "485APOS filed (awaiting effectiveness)"

    # 497/497K = Supplement (fund must already be effective to file these)
    if form.startswith("497"):
        return "EFFECTIVE", "497/497K filed (fund is trading)"

    return "UNKNOWN", f"Unrecognized form type: {form}"


def step4_rollup_for_trust(output_root, trust_name: str) -> int:
    """
    Roll up extracted fund data to show current status of each fund.

    Output columns (simplified):
    - Series ID: SEC permanent identifier
    - Fund Name: Current canonical name
    - Ticker: Trading symbol (if known)
    - Trust: Trust name (registrant)
    - Status: PENDING | EFFECTIVE | DELAYED
    - Effective Date: When fund became/becomes effective
    - Latest Form: Most recent filing type
    - Prospectus Link: Link to latest prospectus
    - Status Reason: Explanation of status determination
    """
    paths = output_paths_for_trust(output_root, trust_name)
    p3 = paths["extracted_funds"]
    p4 = paths["latest_record"]

    if not p3.exists() or p3.stat().st_size == 0:
        return 0

    df = pd.read_csv(p3, dtype=str)
    if df.empty:
        return 0

    # Parse filing date for sorting
    df["_fdt"] = pd.to_datetime(df.get("Filing Date", ""), errors="coerce")
    df = df.sort_values("_fdt", ascending=True)

    # Build grouping key (prefer Class-Contract ID, then Series ID, then name+ticker)
    class_id = df.get("Class-Contract ID", pd.Series("", index=df.index)).fillna("")
    series_id = df.get("Series ID", pd.Series("", index=df.index)).fillna("")
    name_col = df.get("Class Contract Name", pd.Series("", index=df.index)).fillna("")
    name_col = name_col.mask(name_col == "", df.get("Series Name", pd.Series("", index=df.index)).fillna(""))
    ticker_col = df.get("Class Symbol", pd.Series("", index=df.index)).fillna("").str.upper()

    # Create grouping key
    df["__gkey"] = class_id.mask(class_id == "", series_id)
    df.loc[df["__gkey"] == "", "__gkey"] = name_col + "|" + ticker_col

    results = []

    for gkey, group in df.groupby("__gkey", dropna=False):
        g = group.sort_values("_fdt", ascending=True)

        # Get latest record for each form type
        g_bpos = g[g["Form"].fillna("").str.upper().str.contains("485B", na=False)]
        g_apos = g[g["Form"].fillna("").str.upper().str.startswith("485A", na=False)]
        g_497 = g[g["Form"].fillna("").str.upper().str.startswith("497", na=False)]

        # Pick the most authoritative latest filing
        # Priority: 485BPOS > 485BXT > 497 > 485APOS
        if not g_bpos.empty:
            latest = g_bpos.iloc[-1]
        elif not g_497.empty:
            latest = g_497.iloc[-1]
        elif not g_apos.empty:
            latest = g_apos.iloc[-1]
        else:
            latest = g.iloc[-1]

        # Determine status
        status, status_reason = _determine_status(latest)

        # Get best available values
        series_id_val = g["Series ID"].dropna().iloc[-1] if not g["Series ID"].dropna().empty else ""
        class_id_val = g["Class-Contract ID"].dropna().iloc[-1] if "Class-Contract ID" in g.columns and not g["Class-Contract ID"].dropna().empty else ""

        # Get name - prefer Prospectus Name if available (indicates name change), else SGML name
        prospectus_name = ""
        if "Prospectus Name" in g.columns:
            pn = g["Prospectus Name"].dropna()
            pn = pn[pn != ""]
            if not pn.empty:
                prospectus_name = pn.iloc[-1]

        raw_name = g["Class Contract Name"].fillna("").iloc[-1]
        if not raw_name:
            raw_name = g["Series Name"].fillna("").iloc[-1]

        # Use prospectus name if different (indicates name change in progress)
        display_name = prospectus_name if prospectus_name else raw_name
        canonical_name = titlecase_safe(clean_fund_name_for_rollup(display_name))

        ticker = g["Class Symbol"].fillna("").str.upper()
        ticker = ticker[ticker != ""].iloc[-1] if not ticker[ticker != ""].empty else ""

        registrant = g["Registrant"].fillna("").iloc[-1] if "Registrant" in g.columns else trust_name
        cik = g["CIK"].fillna("").iloc[-1] if "CIK" in g.columns else ""

        eff_date = str(latest.get("Effective Date", "")).strip()
        eff_confidence = str(latest.get("Effective Date Confidence", "")).strip() if "Effective Date Confidence" in latest.index else ""

        results.append({
            "Series ID": series_id_val,
            "Class-Contract ID": class_id_val,
            "Fund Name": canonical_name,
            "SGML Name": raw_name,
            "Prospectus Name": prospectus_name,
            "Ticker": ticker,
            "Trust": registrant,
            "CIK": cik,
            "Status": status,
            "Status Reason": status_reason,
            "Effective Date": eff_date,
            "Effective Date Confidence": eff_confidence,
            "Latest Form": str(latest.get("Form", "")),
            "Latest Filing Date": str(latest.get("Filing Date", "")),
            "Prospectus Link": str(latest.get("Primary Link", "")),
        })

    if not results:
        return 0

    roll = pd.DataFrame(results)

    # Sort by trust, status, then name
    status_order = {"PENDING": 0, "DELAYED": 1, "EFFECTIVE": 2, "UNKNOWN": 3}
    roll["_status_sort"] = roll["Status"].map(status_order).fillna(3)
    roll = roll.sort_values(["Trust", "_status_sort", "Fund Name"], ascending=[True, True, True])
    roll = roll.drop(columns=["_status_sort"])

    # Deduplicate by Series ID + Ticker
    roll["_dedup_key"] = roll["Series ID"].fillna("") + "|" + roll["Ticker"].fillna("")
    roll = roll.drop_duplicates(subset=["_dedup_key"], keep="last")
    roll = roll.drop(columns=["_dedup_key"])

    roll.to_csv(p4, index=False)
    return len(roll)
