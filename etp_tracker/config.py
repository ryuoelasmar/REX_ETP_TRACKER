from __future__ import annotations

# Default/fallback user agent (you should override in the notebook CONFIG cell)
USER_AGENT_DEFAULT = "REX-ETP-FilingTracker/1.0 (contact: set USER_AGENT)"

# SEC endpoints
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{CIK_PADDED}.json"
SEC_ARCHIVES_BASE   = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}"

# Forms we consider 'prospectus-related'
PROSPECTUS_EXACT    = {"EFFECT"}
PROSPECTUS_PREFIXES = ("485A", "485B", "497", "N-1A", "S-1", "S-3")
