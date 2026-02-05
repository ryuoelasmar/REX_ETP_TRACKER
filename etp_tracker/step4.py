from __future__ import annotations
import pandas as pd
from .paths import output_paths_for_trust
from .utils import clean_fund_name_for_rollup, titlecase_safe, date_plus_days

def step4_rollup_for_trust(output_root, trust_name: str) -> int:
    paths = output_paths_for_trust(output_root, trust_name)
    p3 = paths["extracted_funds"]; p4 = paths["latest_record"]
    if not p3.exists() or p3.stat().st_size == 0: return 0
    df = pd.read_csv(p3, dtype=str)
    if df.empty: return 0
    df["_fdt"] = pd.to_datetime(df.get("Filing Date", ""), errors="coerce")
    df["FormU"] = df.get("Form", "").fillna("").str.upper()
    df["TickerU"] = df.get("Class Symbol", "").fillna("").str.upper()

    disp_raw = df["Class Contract Name"].fillna("")
    disp_raw = disp_raw.mask(disp_raw.eq(""), df["Series Name"].fillna(""))
    df["Display Name Raw"]   = disp_raw
    df["Display Name Clean"] = df["Display Name Raw"].apply(clean_fund_name_for_rollup)
    df["Display Name Key"]   = df["Display Name Clean"].apply(lambda s: s.casefold())

    class_id  = df.get("Class-Contract ID") if "Class-Contract ID" in df.columns else df.get("Class Contract ID")
    if class_id is None: class_id = pd.Series("", index=df.index)
    series_id = df.get("Series ID", pd.Series("", index=df.index))

    df["__gkey"] = (class_id.fillna("").mask(class_id.fillna("") == "", None).apply(lambda x: f"C:{x}" if x else None))
    df.loc[df["__gkey"].isna(), "__gkey"] = series_id.fillna("").mask(series_id.fillna("") == "", None).apply(lambda x: f"S:{x}" if x else None)
    df.loc[df["__gkey"].isna(), "__gkey"] = df["Display Name Key"] + "|T:" + df["TickerU"]

    def _latest_nonempty(series: pd.Series) -> str:
        s = series.fillna("").astype(str); s = s[s != ""]
        return s.iloc[-1] if len(s) else ""

    def _pick_latest(g: pd.DataFrame, key: str) -> pd.Series:
        gg = g.sort_values("_fdt", kind="stable")
        gB   = gg[gg["FormU"].str.startswith("485B")]
        gA   = gg[gg["FormU"].str.startswith("485A")]
        g497 = gg[gg["FormU"].str.startswith("497")]
        first = gg.iloc[[0]] if len(gg) else pd.DataFrame(columns=gg.columns)
        latestB = gB.tail(1); latestA = gA.tail(1); latestS = g497.tail(1)

        if len(latestB):
            row = latestB.iloc[0]
            lp_form = row.get("Form", ""); lp_date = row.get("Filing Date", ""); lp_link = row.get("Primary Link", "")
            eff_parsed = row.get("Effective Date", "") or row.get("Effective Date (derived)", "") or ""
            lp_eff  = eff_parsed if eff_parsed else lp_date
            lp_src  = "485B"; status  = "BPOS chosen"
        elif len(latestA):
            row = latestA.iloc[0]
            lp_form = row.get("Form", ""); lp_date = row.get("Filing Date", ""); lp_link = row.get("Primary Link", "")
            eff_parsed = row.get("Effective Date", "") or row.get("Effective Date (derived)", "") or ""
            lp_eff  = eff_parsed if eff_parsed else date_plus_days(lp_date, 75)
            lp_src  = "485A"; status  = "APOS chosen (eff=parsed)" if eff_parsed else "APOS chosen (eff=+75d)"
        else:
            lp_form = ""; lp_date = ""; lp_link = ""; lp_eff  = ""; lp_src  = ""; status  = "Supplements only" if len(latestS) else "No prospectus form found"

        disp_clean = _latest_nonempty(gg["Display Name Clean"]); canonical  = titlecase_safe(disp_clean)
        tkr        = _latest_nonempty(gg["TickerU"])

        apos_date = str(latestA.iloc[0]["Filing Date"]) if len(latestA) else ""
        apos_link = str(latestA.iloc[0]["Primary Link"]) if len(latestA) else ""
        bpos_date = str(latestB.iloc[0]["Filing Date"]) if len(latestB) else ""
        bpos_link = str(latestB.iloc[0]["Primary Link"]) if len(latestB) else ""
        s497_date = str(latestS.iloc[0]["Filing Date"]) if len(latestS) else ""
        s497_link = str(latestS.iloc[0]["Primary Link"]) if len(latestS) else ""

        fs_date = str(first.iloc[0]["Filing Date"]) if len(first) else ""
        fs_form = str(first.iloc[0]["Form"])        if len(first) else ""
        fs_link = str(first.iloc[0]["Primary Link"])if len(first) else ""

        registrant = _latest_nonempty(gg.get("Registrant", pd.Series("", index=gg.index)))
        cik_val    = _latest_nonempty(gg.get("CIK", pd.Series("", index=gg.index)).astype(str))

        return pd.Series({
            "Fund Key": key,
            "Registrant": registrant,
            "CIK": cik_val,
            "Canonical Fund Name": canonical,
            "Ticker (if any)": tkr,
            "First Seen Date": fs_date,
            "First Seen Form": fs_form,
            "First Seen Link": fs_link,
            "Latest APOS Date": apos_date,
            "Latest APOS Link": apos_link,
            "Latest BPOS Date": bpos_date,
            "Latest BPOS Link": bpos_link,
            "Latest 497/497K Date": s497_date,
            "Latest 497/497K Link": s497_link,
            "Latest Prospectus Form": lp_form,
            "Latest Prospectus Date": lp_date,
            "Latest Prospectus Effective (derived)": lp_eff,
            "Latest Prospectus Link": lp_link,
            "Latest Prospectus Source": lp_src,
            "Status": status,
        })

    roll = (df.groupby("__gkey", dropna=False).apply(lambda g: _pick_latest(g.drop(columns=["__gkey"], errors="ignore"), key=g.name)).reset_index(drop=True))
    roll.sort_values(["Registrant","Canonical Fund Name","Latest Prospectus Date"], ascending=[True,True,False], inplace=True)
    roll["_name_key"] = roll["Canonical Fund Name"].fillna("").str.casefold()
    roll["_tkr_key"]  = roll["Ticker (if any)"].fillna("").str.upper()
    roll = roll.drop_duplicates(subset=["_name_key","_tkr_key"], keep="last").drop(columns=["_name_key","_tkr_key"])
    roll.to_csv(p4, index=False)
    return len(roll)
