"""One-time bulk loader: downloads SEC submissions.zip and discovers all ETF trusts."""
import sys
sys.path.insert(0, ".")
from etp_tracker.bulk_loader import bulk_load

if __name__ == "__main__":
    result = bulk_load()
    print(f"\nDiscovered {len(result)} ETF trust CIKs")
    for r in sorted(result, key=lambda x: x["name"]):
        print(f"  {r['cik']:>10}  {r['name']}")
