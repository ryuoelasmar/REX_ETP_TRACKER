from __future__ import annotations
import re
import pandas as pd
from .sec_client import SECClient
from .utils import safe_str, is_html_doc, is_pdf_doc, norm_key
from .csvio import append_dedupe_csv
from .paths import output_paths_for_trust
from .sgml import parse_sgml_series_classes
from .body_extractors import iter_txt_documents, extract_from_html_string, extract_from_primary_html, extract_from_primary_pdf

_TICKER_STOPWORDS = {"THE","AND","FOR","WITH","ETF","FUND","RISK","USD","MEMBER"}
def _valid_ticker(tok: str) -> bool:
    t = (tok or "").strip().upper()
    if not (1 <= len(t) <= 6): return False
    if t in _TICKER_STOPWORDS: return False
    return any(c.isalpha() for c in t)

def _extract_ticker_for_series_from_texts(series_name: str, texts: list[str]) -> tuple[str, str]:
    if not series_name: return "", ""
    s_norm = re.sub(r"\s+", " ", series_name).strip()
    s_pat = re.escape(s_norm)
    rx_paren = re.compile(fr"{s_pat}\s*\(\s*([A-Z0-9]{{1,6}})\s*\)", flags=re.IGNORECASE)
    for t in texts:
        m = rx_paren.search(t or "")
        if m:
            cand = m.group(1).upper()
            if _valid_ticker(cand): return cand, "TITLE-PAREN"
    label_rx = re.compile(r"(?i)(Ticker|Trading\s*Symbol)\s*[:\-–]\s*([A-Z0-9]{1,6})")
    for t in texts:
        if not t: continue
        for m in re.finditer(s_pat, t, flags=re.IGNORECASE):
            start = max(0, m.start() - 600); end = min(len(t), m.end() + 600)
            window = t[start:end]
            lm = label_rx.search(window)
            if lm:
                cand = lm.group(2).upper()
                if _valid_ticker(cand): return cand, "LABEL-WINDOW"
    return "", ""

def _extract_effectiveness_from_hdr(txt: str) -> str:
    m = re.search(r"EFFECTIVENESS\s+DATE:\s*(\d{8})", txt or "", flags=re.IGNORECASE)
    if m:
        s = m.group(1)
        try:
            return pd.to_datetime(s, format="%Y%m%d").strftime("%Y-%m-%d")
        except Exception:
            pass
    return ""

_DELAYING_PHRASES = [
    "delaying amendment",
    "delay its effective date",
    "delay the effective date",
    "rule 485(a)",
    "rule 473",
    "designates a new effective date",
]

_DATE_PHRASES = [
    r"(?:become|becomes|shall become|will become|will be)\s+effective\s+(?:on|as of)\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
    r"effective\s+(?:on|as of)\s+(\d{1,2}/\d{1,2}/\d{2,4})",
    r"effective\s+on\s+or\s+about\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
]

def _find_effective_date_in_text(txt: str) -> tuple[str, bool]:
    if not isinstance(txt, str) or not txt.strip():
        return "", False
    lower = txt.lower()
    delaying = any(p in lower for p in _DELAYING_PHRASES)
    t = re.sub(r"\s+", " ", txt)
    for pat in _DATE_PHRASES:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            s = m.group(1)
            try:
                dt = pd.to_datetime(s, errors="coerce")
                if not pd.isna(dt):
                    return dt.strftime("%Y-%m-%d"), delaying
            except Exception:
                pass
    return "", delaying

def step3_extract_for_trust(client: SECClient, output_root, trust_name: str,
                            since: str | None = None, until: str | None = None, forms: list[str] | None = None) -> int:
    paths = output_paths_for_trust(output_root, trust_name)
    p2 = paths["prospectus_base"]; p3 = paths["extracted_funds"]
    if not p2.exists() or p2.stat().st_size == 0: return 0
    df2 = pd.read_csv(p2, dtype=str)
    if df2.empty: return 0

    if since or until or forms:
        d2 = df2.copy()
        d2["_fdt"] = pd.to_datetime(d2.get("Filing Date", ""), errors="coerce")
        if since: d2 = d2[d2["_fdt"] >= pd.to_datetime(since, errors="coerce")]
        if until: d2 = d2[d2["_fdt"] <= pd.to_datetime(until, errors="coerce")]
        if forms:
            upp = d2.get("Form", pd.Series("", index=d2.index)).fillna("").str.upper()
            d2 = d2[upp.str.startswith(tuple([f.upper() for f in forms]))]
        df2 = d2.drop(columns=["_fdt"], errors="ignore")

    rows_out: list[dict] = []

    for _, r in df2.iterrows():
        form      = safe_str(r.get("Form",""))
        filing_dt = safe_str(r.get("Filing Date",""))
        cik       = safe_str(r.get("CIK",""))
        registrant= safe_str(r.get("Registrant",""))
        accession = safe_str(r.get("Accession Number",""))
        prim_url  = safe_str(r.get("Primary Link",""))
        txt_url   = safe_str(r.get("Full Submission TXT",""))
        if (form or "").strip().upper() == "EFFECT": continue

        # fetch TXT
        txt_text = ""
        try:
            if txt_url: txt_text = client.fetch_text(txt_url)
        except Exception:
            txt_text = ""

        sgml_rows = parse_sgml_series_classes(txt_text) if txt_text else []

        eff_date_col = _extract_effectiveness_from_hdr(txt_text) if txt_text else ""
        if txt_text:
            ed_txt, delay_txt = _find_effective_date_in_text(txt_text)
        else:
            ed_txt, delay_txt = ("", False)
        if (not eff_date_col) and ed_txt: eff_date_col = ed_txt
        delaying = bool(delay_txt)

        # collect all body texts for anchored ticker search
        all_plain_texts: list[str] = [txt_text] if txt_text else []
        if txt_text:
            for doctype, fname, body_html in iter_txt_documents(txt_text):
                if doctype.upper().startswith(("485A","485B","497")):
                    _, html_plain2 = extract_from_html_string(body_html)
                    if html_plain2:
                        all_plain_texts.append(html_plain2)
                        if not eff_date_col:
                            ed2, d2 = _find_effective_date_in_text(html_plain2)
                            if ed2: eff_date_col = ed2
                            delaying = delaying or d2

        html_plain = ""
        if is_html_doc(prim_url):
            _, html_plain = extract_from_primary_html(client, prim_url)
            if html_plain:
                all_plain_texts.append(html_plain)
                if not eff_date_col:
                    ed_h, d_h = _find_effective_date_in_text(html_plain)
                    if ed_h: eff_date_col = ed_h
                    delaying = delaying or d_h

        pdf_plain = ""
        if is_pdf_doc(prim_url):
            _, pdf_plain = extract_from_primary_pdf(client, prim_url)
            if pdf_plain:
                all_plain_texts.append(pdf_plain)
                if not eff_date_col:
                    ed_p, d_p = _find_effective_date_in_text(pdf_plain)
                    if ed_p: eff_date_col = ed_p
                    delaying = delaying or d_p

        extracted_rows: list[dict] = []
        if sgml_rows:
            for base in sgml_rows:
                nm = base.get("Class Contract Name") or base.get("Series Name") or ""
                tkr, tkr_src = _extract_ticker_for_series_from_texts(nm, all_plain_texts)
                row = dict(base)
                if tkr:
                    row["Class Symbol"] = tkr
                    src = row.get("Extracted From") or "SGML-TXT"
                    row["Extracted From"] = f"{src}|{tkr_src}"
                row.update({
                    "Form": form, "Filing Date": filing_dt, "Accession Number": accession,
                    "Primary Link": prim_url, "Full Submission TXT": txt_url,
                    "Registrant": registrant, "CIK": cik,
                    "Effective Date": eff_date_col, "Delaying Amendment": "Y" if delaying else "",
                })
                extracted_rows.append(row)
        else:
            extracted_rows.append({
                "Series ID": "", "Series Name": "",
                "Class-Contract ID": "", "Class Contract Name": "", "Class Symbol": "",
                "Form": form, "Filing Date": filing_dt, "Accession Number": accession,
                "Primary Link": prim_url, "Full Submission TXT": txt_url,
                "Registrant": registrant, "CIK": cik,
                "Extracted From": "NONE",
                "Effective Date": eff_date_col, "Delaying Amendment": "Y" if delaying else "",
            })

        rows_out.extend(extracted_rows)

    if not rows_out: return 0
    df_new = pd.DataFrame(rows_out)
    for col in [
        "Series ID","Series Name","Class-Contract ID","Class Contract Name","Class Symbol",
        "Form","Filing Date","Accession Number","Primary Link","Full Submission TXT",
        "Registrant","CIK","Extracted From","Effective Date","Delaying Amendment"
    ]:
        if col not in df_new.columns: df_new[col] = ""

    df_new["__key"] = (
        df_new["Accession Number"].fillna("") + "|" +
        df_new["Class-Contract ID"].fillna("") + "|" +
        df_new["Class Contract Name"].fillna("") + "|" +
        df_new["Class Symbol"].fillna("")
    )
    df_new = df_new.drop_duplicates(subset=["__key"], keep="last").drop(columns=["__key"])
    append_dedupe_csv(paths["extracted_funds"], df_new,
                      key_cols=["Accession Number","Class-Contract ID","Class Contract Name","Class Symbol"])
    return len(df_new)
