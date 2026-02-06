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
]

# High-confidence patterns (checkbox selections, explicit designations)
_DATE_PHRASES_HIGH_CONFIDENCE = [
    # Checkbox pattern: "on November 7, 2025 pursuant to paragraph"
    r"on\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})\s+pursuant\s+to\s+paragraph",
    # Explicit designation: "designating November 7, 2025 as the new effective date"
    r"designating\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})\s+as\s+the\s+new\s+effective\s+date",
    # Direct statement: "effective date of November 7, 2025"
    r"effective\s+date\s+(?:of|is)\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})",
]

# Medium-confidence patterns
_DATE_PHRASES_MEDIUM = [
    r"(?:become|becomes|shall become|will become|will be)\s+effective\s+(?:on|as of)\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})",
    r"effective\s+(?:on|as of)\s+(\d{1,2}/\d{1,2}/\d{2,4})",
    r"effective\s+on\s+or\s+about\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})",
]

def _parse_date_string(date_str: str) -> str | None:
    """Parse various date formats and return YYYY-MM-DD or None."""
    if not date_str:
        return None
    date_str = date_str.strip().replace(",", "")
    formats = [
        "%B %d %Y",    # November 7 2025
        "%B %d, %Y",   # November 7, 2025
        "%m/%d/%Y",    # 11/07/2025
        "%m/%d/%y",    # 11/07/25
        "%Y-%m-%d",    # 2025-11-07
    ]
    for fmt in formats:
        try:
            dt = pd.to_datetime(date_str, format=fmt)
            if not pd.isna(dt):
                return dt.strftime("%Y-%m-%d")
        except Exception:
            continue
    # Fallback: let pandas try to parse it
    try:
        dt = pd.to_datetime(date_str, errors="coerce")
        if not pd.isna(dt):
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None

def _find_effective_date_in_text(txt: str) -> tuple[str, str, bool]:
    """
    Extract effective date from filing text.

    Returns: (date_str, confidence, is_delaying)
        - date_str: YYYY-MM-DD or empty
        - confidence: 'HIGH', 'MEDIUM', or ''
        - is_delaying: True if delaying amendment detected
    """
    if not isinstance(txt, str) or not txt.strip():
        return "", "", False

    lower = txt.lower()
    delaying = any(p in lower for p in _DELAYING_PHRASES)

    # Normalize whitespace for pattern matching
    t = re.sub(r"\s+", " ", txt)

    # Try high-confidence patterns first
    for pat in _DATE_PHRASES_HIGH_CONFIDENCE:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            date_str = _parse_date_string(m.group(1))
            if date_str:
                return date_str, "HIGH", delaying

    # Try medium-confidence patterns
    for pat in _DATE_PHRASES_MEDIUM:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            date_str = _parse_date_string(m.group(1))
            if date_str:
                return date_str, "MEDIUM", delaying

    return "", "", delaying

def _extract_fund_names_from_html(html_text: str) -> list[str]:
    """
    Extract fund names from HTML body text.
    Returns list of potential fund names found in the prospectus.
    """
    if not html_text:
        return []

    names = []
    # Pattern for fund names in tables or text (ETF, Fund, Trust suffix)
    patterns = [
        r"([A-Z][A-Za-z0-9\s\-\.]+(?:ETF|Fund|Trust))",
        r"T-REX\s+[A-Z0-9][A-Za-z0-9\s\-\.]+(?:ETF|Fund)",
        r"Tuttle\s+Capital\s+[A-Za-z0-9\s\-\.]+(?:ETF|Fund)",
        r"REX\s+[A-Za-z0-9\s\-\.]+(?:ETF|Fund)",
    ]

    for pat in patterns:
        for m in re.finditer(pat, html_text):
            name = re.sub(r"\s+", " ", m.group(0)).strip()
            if len(name) > 10 and name not in names:
                names.append(name)

    return names[:50]  # Limit to prevent excessive results


def _find_prospectus_name_for_sgml(sgml_name: str, html_names: list[str]) -> str:
    """
    Try to find the corresponding name in the HTML prospectus body.
    This helps detect name changes (SGML may have old name, HTML has new name).

    Returns: The matching HTML name if found (and different), empty string otherwise.
    """
    if not sgml_name or not html_names:
        return ""

    sgml_norm = re.sub(r"\s+", " ", sgml_name).strip().upper()

    # Extract key words from SGML name for matching
    # Remove common suffixes and prefixes
    sgml_tokens = set(re.findall(r"[A-Z0-9]+", sgml_norm))
    sgml_tokens -= {"ETF", "FUND", "TRUST", "THE", "AND", "FOR", "WITH", "DAILY", "TARGET", "CAPITAL"}

    best_match = ""
    best_score = 0

    for html_name in html_names:
        html_norm = re.sub(r"\s+", " ", html_name).strip().upper()

        # Skip if identical (no name change)
        if sgml_norm == html_norm:
            continue

        html_tokens = set(re.findall(r"[A-Z0-9]+", html_norm))
        html_tokens -= {"ETF", "FUND", "TRUST", "THE", "AND", "FOR", "WITH", "DAILY", "TARGET", "CAPITAL"}

        # Calculate overlap
        if not sgml_tokens or not html_tokens:
            continue

        overlap = len(sgml_tokens & html_tokens)
        total = len(sgml_tokens | html_tokens)
        score = overlap / total if total > 0 else 0

        # Need at least 50% overlap to consider a match
        if score >= 0.5 and score > best_score:
            best_score = score
            best_match = html_name

    return best_match

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

        # Extract effective date from SGML header first
        eff_date_col = _extract_effectiveness_from_hdr(txt_text) if txt_text else ""
        eff_confidence = "HEADER" if eff_date_col else ""
        delaying = False

        # Try to extract from full txt text
        if txt_text:
            ed_txt, conf_txt, delay_txt = _find_effective_date_in_text(txt_text)
            if ed_txt and (not eff_date_col or conf_txt == "HIGH"):
                eff_date_col = ed_txt
                eff_confidence = conf_txt
            delaying = delay_txt

        # Collect all body texts for anchored ticker search AND HTML fund names
        all_plain_texts: list[str] = [txt_text] if txt_text else []
        html_fund_names: list[str] = []

        if txt_text:
            for doctype, fname, body_html in iter_txt_documents(txt_text):
                if doctype.upper().startswith(("485A","485B","497")):
                    _, html_plain2 = extract_from_html_string(body_html)
                    if html_plain2:
                        all_plain_texts.append(html_plain2)
                        # Extract fund names from HTML body
                        html_fund_names.extend(_extract_fund_names_from_html(html_plain2))
                        # Try to get effective date from embedded docs
                        if not eff_date_col or eff_confidence not in ("HIGH", "HEADER"):
                            ed2, conf2, d2 = _find_effective_date_in_text(html_plain2)
                            if ed2 and (not eff_date_col or conf2 == "HIGH"):
                                eff_date_col = ed2
                                eff_confidence = conf2
                            delaying = delaying or d2

        html_plain = ""
        if is_html_doc(prim_url):
            _, html_plain = extract_from_primary_html(client, prim_url)
            if html_plain:
                all_plain_texts.append(html_plain)
                html_fund_names.extend(_extract_fund_names_from_html(html_plain))
                if not eff_date_col or eff_confidence not in ("HIGH", "HEADER"):
                    ed_h, conf_h, d_h = _find_effective_date_in_text(html_plain)
                    if ed_h and (not eff_date_col or conf_h == "HIGH"):
                        eff_date_col = ed_h
                        eff_confidence = conf_h
                    delaying = delaying or d_h

        pdf_plain = ""
        if is_pdf_doc(prim_url):
            _, pdf_plain = extract_from_primary_pdf(client, prim_url)
            if pdf_plain:
                all_plain_texts.append(pdf_plain)
                html_fund_names.extend(_extract_fund_names_from_html(pdf_plain))
                if not eff_date_col or eff_confidence not in ("HIGH", "HEADER"):
                    ed_p, conf_p, d_p = _find_effective_date_in_text(pdf_plain)
                    if ed_p and (not eff_date_col or conf_p == "HIGH"):
                        eff_date_col = ed_p
                        eff_confidence = conf_p
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

                # Try to find matching prospectus name from HTML body
                prospectus_name = _find_prospectus_name_for_sgml(nm, html_fund_names)

                row.update({
                    "Form": form, "Filing Date": filing_dt, "Accession Number": accession,
                    "Primary Link": prim_url, "Full Submission TXT": txt_url,
                    "Registrant": registrant, "CIK": cik,
                    "Effective Date": eff_date_col,
                    "Effective Date Confidence": eff_confidence,
                    "Delaying Amendment": "Y" if delaying else "",
                    "Prospectus Name": prospectus_name,
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
                "Effective Date": eff_date_col,
                "Effective Date Confidence": eff_confidence,
                "Delaying Amendment": "Y" if delaying else "",
                "Prospectus Name": "",
            })

        rows_out.extend(extracted_rows)

    if not rows_out: return 0
    df_new = pd.DataFrame(rows_out)
    for col in [
        "Series ID","Series Name","Class-Contract ID","Class Contract Name","Class Symbol",
        "Form","Filing Date","Accession Number","Primary Link","Full Submission TXT",
        "Registrant","CIK","Extracted From","Effective Date","Effective Date Confidence",
        "Delaying Amendment","Prospectus Name"
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
