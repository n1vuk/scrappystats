import logging
import subprocess
from scrappystats.config_loader import load_alliances

from .log import configure_logging

configure_logging()

def main():
    logging.info("=== ScrappyStats startup init ===")
    load_alliances()  # ← fatal if missing
    logging.info("Alliances config loaded successfully")
    logging.info("Running initial fetch_and_process.py")
    subprocess.run(["python3", "-m", "scrappystats.fetch_and_process"], check=False)
    logging.info("Running initial daily report")
    subprocess.run(["python3", "-m", "scrappystats.report_daily"], check=False)
    logging.info("Running initial weekly report")
    subprocess.run(["python3", "-m", "scrappystats.report_weekly"], check=False)
    logging.info("=== ScrappyStats startup init complete ===")

if __name__ == "__main__":
    main()
