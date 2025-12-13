import logging
import subprocess


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    logging.info("=== ScrappyStats startup init ===")
    logging.info("Running initial fetch_and_process.py")
    subprocess.run(["python3", "-m", "scrappystats.fetch_and_process"], check=False)
    logging.info("Running initial daily report")
    subprocess.run(["python3", "-m", "scrappystats.report_daily"], check=False)
    logging.info("Running initial weekly report")
    subprocess.run(["python3", "-m", "scrappystats.report_weekly"], check=False)
    logging.info("=== ScrappyStats startup init complete ===")

if __name__ == "__main__":
    main()
