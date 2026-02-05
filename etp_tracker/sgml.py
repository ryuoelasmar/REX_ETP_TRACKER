# etp_tracker/sgml.py
from __future__ import annotations
import re
from .utils import normalize_spacing  # make sure utils.py has this helper (shown below)

def _grab(block: str, tag: str) -> str:
    """
    Return the text inside <TAG> ... for a given block. Whitespace is normalized.
    Works on the SGML header inside the SEC submission .txt.
    """
    m = re.search(fr"(?is)<{tag}>\s*([^<\r\n]+)", block or "")
    return normalize_spacing(m.group(1)) if m else ""

def parse_sgml_series_classes(txt: str) -> list[dict]:
    """
    Parse the SGML header in a submission .txt and enumerate all funds/classes.
    Handles BOTH <NEW-SERIES> ... </NEW-SERIES> and <SERIES> ... </SERIES>.
    Returns a list of dicts with Series/Class IDs and names.
    """
    out: list[dict] = []
    if not txt:
        return out

    def _emit(series_block: str):
        sid   = _grab(series_block, "SERIES-ID")
        sname = _grab(series_block, "SERIES-NAME")

        classes = list(re.finditer(r"(?is)<CLASS-CONTRACT>(.*?)</CLASS-CONTRACT>", series_block or ""))
        if classes:
            for cm in classes:
                cblk  = cm.group(1)
                cid   = _grab(cblk, "CLASS-CONTRACT-ID") or _grab(cblk, "CLASS-CONTRACTIDENTIFIER")
                cname = _grab(cblk, "CLASS-CONTRACT-NAME") or _grab(cblk, "CLASS-NAME")
                csym  = (_grab(cblk, "CLASS-CONTRACT-TICKER-SYMBOL")
                         or _grab(cblk, "CLASS-TICKER-SYMBOL")
                         or _grab(cblk, "CLASS-TICKER"))
                out.append({
                    "Series ID": sid,
                    "Series Name": sname,
                    "Class-Contract ID": cid,
                    "Class Contract Name": cname,
                    "Class Symbol": (csym or "").upper(),
                    "Extracted From": "SGML-TXT",
                })
        else:
            # Emit a row even if there is no explicit CLASS-CONTRACT block
            out.append({
                "Series ID": sid,
                "Series Name": sname,
                "Class-Contract ID": "",
                "Class Contract Name": "",
                "Class Symbol": "",
                "Extracted From": "SGML-TXT",
            })

    # Many APOS filings list funds under <NEW-SERIES>; others under <SERIES>.
    for m in re.finditer(r"(?is)<NEW-SERIES>(.*?)</NEW-SERIES>", txt):
        _emit(m.group(1))
    for m in re.finditer(r"(?is)<SERIES>(.*?)</SERIES>", txt):
        _emit(m.group(1))

    return out
