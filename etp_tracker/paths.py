from __future__ import annotations
from pathlib import Path
from .utils import slugify_name
try:
    from .config import SEC_ARCHIVES_BASE
except Exception:
    SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}"

CSV1_NAME = "{trust}_1_All_Trust_Filings.csv"
CSV2_NAME = "{trust}_2_All_Prospectus_Related_Filings.csv"
CSV3_NAME = "{trust}_3_Prospectus_Fund_Extraction.csv"
CSV4_NAME = "{trust}_4_Fund_Status.csv"
CSV5_NAME = "{trust}_5_Name_History.csv"

def output_paths_for_trust(output_root: Path | str, trust_name: str) -> dict[str, Path]:
    trust_folder = Path(output_root) / slugify_name(trust_name)
    trust_folder.mkdir(parents=True, exist_ok=True)
    return {
        "folder": trust_folder,
        "all_filings": trust_folder / CSV1_NAME.format(trust=slugify_name(trust_name)),
        "prospectus_base": trust_folder / CSV2_NAME.format(trust=slugify_name(trust_name)),
        "extracted_funds": trust_folder / CSV3_NAME.format(trust=slugify_name(trust_name)),
        "latest_record": trust_folder / CSV4_NAME.format(trust=slugify_name(trust_name)),
        "name_history": trust_folder / CSV5_NAME.format(trust=slugify_name(trust_name)),
    }

def edgar_base_url(cik: str, accession: str) -> str:
    cik_int = int(str(cik))
    nodash = accession.replace("-", "")
    return SEC_ARCHIVES_BASE.format(cik=cik_int, accession_nodash=nodash)

def build_primary_link(cik: str, accession: str, primary_doc: str) -> str:
    if not primary_doc:
        return ""
    return f"{edgar_base_url(cik, accession)}/{primary_doc}"

def build_submission_txt_link(cik: str, accession: str) -> str:
    return f"{edgar_base_url(cik, accession)}/{accession}.txt"
