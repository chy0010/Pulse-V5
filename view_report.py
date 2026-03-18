import os
import sys
from datetime import date

REPORTS_DIR = "reports"


def view(target_date):
    md_path = os.path.join(REPORTS_DIR, f"{target_date}.md")

    if not os.path.exists(md_path):
        print(f"No report found for {target_date}")
        print(f"Expected: {md_path}")
        return

    with open(md_path) as f:
        print(f.read())


def main():
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
    else:
        target_date = date.today().isoformat()

    view(target_date)


if __name__ == "__main__":
    main()
