import logging
import subprocess

from .log import configure_logging

configure_logging()

def main():
    logging.info("=== ScrappyStats startup init ===")
    logging.info("Running initial daily report")
    subprocess.run(["python3", "-m", "scrappystats.report_daily"], check=False)
    logging.info("Running initial weekly report")
    subprocess.run(["python3", "-m", "scrappystats.report_weekly"], check=False)
    logging.info("=== ScrappyStats startup init complete ===")

if __name__ == "__main__":
    main()
