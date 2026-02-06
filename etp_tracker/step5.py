"""
Step 5: Name History Tracking

Tracks all name changes for funds using the permanent Series ID.
Outputs a separate CSV with name history for each fund.
"""
from __future__ import annotations
import pandas as pd
from pathlib import Path
from .paths import output_paths_for_trust
from .utils import clean_fund_name_for_rollup


def step5_name_history_for_trust(output_root, trust_name: str) -> int:
    """
    Build name history for all funds in a trust.

    Uses Series ID as the permanent identifier to track name changes across filings.
    Outputs to {trust_name}_5_Name_History.csv

    Columns:
    - Series ID: Permanent SEC identifier
    - Name: Fund name at that point in time
    - First Seen Date: First filing with this name
    - Last Seen Date: Last filing with this name (or empty if current)
    - Is Current: Y if this is the most recent name
    - Source Form: Form type where name first appeared
    - Source Accession: Accession number of first filing with this name
    """
    paths = output_paths_for_trust(output_root, trust_name)
    p3 = paths["extracted_funds"]
    p5 = paths["name_history"]

    if not p3.exists() or p3.stat().st_size == 0:
        return 0

    df = pd.read_csv(p3, dtype=str)
    if df.empty:
        return 0

    # Need Series ID for tracking
    if "Series ID" not in df.columns:
        return 0

    # Parse filing date
    df["_fdt"] = pd.to_datetime(df.get("Filing Date", ""), errors="coerce")
    df = df.sort_values("_fdt", ascending=True)

    # Get name from Class Contract Name or Series Name
    df["_name"] = df.get("Class Contract Name", pd.Series("", index=df.index)).fillna("")
    df.loc[df["_name"] == "", "_name"] = df.get("Series Name", pd.Series("", index=df.index)).fillna("")

    # Clean names for comparison
    df["_name_clean"] = df["_name"].apply(clean_fund_name_for_rollup)
    df["_name_key"] = df["_name_clean"].str.casefold()

    # Also track prospectus names (from HTML body)
    if "Prospectus Name" in df.columns:
        df["_prosp_name"] = df["Prospectus Name"].fillna("")
        df["_prosp_name_clean"] = df["_prosp_name"].apply(clean_fund_name_for_rollup)
    else:
        df["_prosp_name"] = ""
        df["_prosp_name_clean"] = ""

    history_rows = []

    # Group by Series ID
    for series_id, group in df.groupby("Series ID", dropna=False):
        if not series_id or pd.isna(series_id):
            continue

        g = group.sort_values("_fdt", ascending=True)

        # Track unique names in order of appearance
        seen_names = {}  # name_key -> {name, first_date, last_date, first_form, first_accession}

        for _, row in g.iterrows():
            name_key = row["_name_key"]
            name_raw = row["_name"]
            filing_date = str(row.get("Filing Date", ""))
            form = str(row.get("Form", ""))
            accession = str(row.get("Accession Number", ""))

            if name_key and name_raw:
                if name_key not in seen_names:
                    seen_names[name_key] = {
                        "name": name_raw,
                        "first_date": filing_date,
                        "last_date": filing_date,
                        "first_form": form,
                        "first_accession": accession,
                    }
                else:
                    seen_names[name_key]["last_date"] = filing_date

            # Also track prospectus names if different
            prosp_name = row.get("_prosp_name_clean", "")
            prosp_raw = row.get("_prosp_name", "")
            if prosp_name and prosp_raw:
                prosp_key = prosp_name.casefold()
                if prosp_key and prosp_key not in seen_names:
                    seen_names[prosp_key] = {
                        "name": prosp_raw,
                        "first_date": filing_date,
                        "last_date": filing_date,
                        "first_form": form,
                        "first_accession": accession,
                        "source": "PROSPECTUS",
                    }
                elif prosp_key in seen_names:
                    seen_names[prosp_key]["last_date"] = filing_date

        # Determine which is current (latest by last_date)
        if seen_names:
            latest_key = max(seen_names.keys(), key=lambda k: seen_names[k]["last_date"])

            for name_key, info in seen_names.items():
                is_current = "Y" if name_key == latest_key else ""
                source = info.get("source", "SGML")

                history_rows.append({
                    "Series ID": series_id,
                    "Name": info["name"],
                    "Name Clean": clean_fund_name_for_rollup(info["name"]),
                    "First Seen Date": info["first_date"],
                    "Last Seen Date": info["last_date"] if not is_current else "",
                    "Is Current": is_current,
                    "Source Form": info["first_form"],
                    "Source Accession": info["first_accession"],
                    "Name Source": source,
                })

    if not history_rows:
        return 0

    df_hist = pd.DataFrame(history_rows)

    # Sort by Series ID, then by first seen date
    df_hist = df_hist.sort_values(["Series ID", "First Seen Date"], ascending=[True, True])

    df_hist.to_csv(p5, index=False)
    return len(df_hist)


def get_name_changes_for_series(output_root, trust_name: str, series_id: str) -> list[dict]:
    """
    Get name history for a specific Series ID.

    Returns list of dicts with name change history, ordered chronologically.
    """
    paths = output_paths_for_trust(output_root, trust_name)
    p5 = paths["name_history"]

    if not p5.exists():
        return []

    df = pd.read_csv(p5, dtype=str)
    df_series = df[df["Series ID"] == series_id]

    if df_series.empty:
        return []

    return df_series.to_dict(orient="records")


def find_series_by_name(output_root, trust_name: str, name_search: str) -> list[dict]:
    """
    Find Series IDs by searching historical names.

    Useful when user searches by an old name that has since changed.
    Returns list of matching series with their current and historical names.
    """
    paths = output_paths_for_trust(output_root, trust_name)
    p5 = paths["name_history"]

    if not p5.exists():
        return []

    df = pd.read_csv(p5, dtype=str)

    # Search in both Name and Name Clean columns
    search_lower = name_search.lower()
    mask = (
        df["Name"].fillna("").str.lower().str.contains(search_lower, regex=False) |
        df["Name Clean"].fillna("").str.lower().str.contains(search_lower, regex=False)
    )

    matches = df[mask]
    if matches.empty:
        return []

    # Group by Series ID and return summary
    results = []
    for series_id in matches["Series ID"].unique():
        series_rows = df[df["Series ID"] == series_id]
        current_row = series_rows[series_rows["Is Current"] == "Y"]
        current_name = current_row.iloc[0]["Name"] if not current_row.empty else ""

        all_names = series_rows["Name"].tolist()

        results.append({
            "Series ID": series_id,
            "Current Name": current_name,
            "All Names": all_names,
            "Name Count": len(all_names),
        })

    return results
