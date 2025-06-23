# generate_report.py

import os
from datetime import datetime, timedelta
import logging

# Ensure logging is set up for this script as well
def setup_logging(log_file="report_generation.log", level=logging.INFO):
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers to prevent duplicate output if run multiple times in same session
    if root_logger.handlers:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)

setup_logging()
logger = logging.getLogger(__name__)

# Import necessary modules from our project
try:
    from config import LOCATION_ID, DB_CONFIG
    from db_module import InventoryDB
except ImportError as e:
    logger.critical(f"Failed to import project modules. Ensure 'config.py' and 'db_module.py' are in the same directory. Error: {e}")
    exit()

class InventoryReporter:
    def __init__(self):
        self.db = InventoryDB()
        self.db.initialize_schema() # Ensure schema is ready
        self.location_id = LOCATION_ID
        logger.info(f"Report generator initialized for location: {self.location_id}")

    def _get_current_inventory(self):
        """Fetches the current inventory state for the defined location."""
        logger.info(f"Fetching current inventory for {self.location_id}...")
        return self.db.get_all_inventory_counts(self.location_id)

    def _get_transactions(self, days_ago=7):
        """Fetches transactions from the last N days for the defined location."""
        logger.info(f"Fetching transactions for the last {days_ago} days for {self.location_id}...")
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days_ago)
        return self.db.get_transactions_in_range(start_time, end_time, self.location_id)

    def generate_full_report(self, days_for_transactions=7, output_filename="inventory_report.txt"):
        """Generates a multi-page inventory report and saves it to a file."""
        report_content = []

        # --- Report Header / Cover Page ---
        report_content.append("="*80)
        report_content.append(f"               INVENTORY REPORT FOR LOCATION: {self.location_id}")
        report_content.append(f"               Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_content.append("="*80)
        report_content.append("\n\n")

        # --- Page 1: Executive Summary - Current Inventory Snapshot ---
        report_content.append("### PAGE 1: CURRENT INVENTORY SNAPSHOT ###")
        report_content.append("-" * 40)
        current_inventory = self._get_current_inventory()
        if current_inventory:
            for item, count in current_inventory.items():
                report_content.append(f"  - {item.ljust(25)} : {count}")
        else:
            report_content.append("  No items currently in inventory.")
        report_content.append("\n\n")

        # --- Page 2: Detailed Current Inventory (Placeholder for future expansion) ---
        # If we had per-ROI counts in DB, this would be expanded here.
        report_content.append("### PAGE 2: DETAILED INVENTORY BREAKDOWN (Summarized by Item Type) ###")
        report_content.append("-" * 40)
        if current_inventory:
            for item, count in current_inventory.items():
                report_content.append(f"  - {item.ljust(25)} : {count} (Across all ROIs in {self.location_id})")
        else:
            report_content.append("  No detailed inventory data available.")
        report_content.append("\n\n")


        # --- Page 3: Recent Transactions Log ---
        report_content.append(f"### PAGE 3: RECENT TRANSACTIONS (Last {days_for_transactions} Days) ###")
        report_content.append("-" * 80)
        transactions = self._get_transactions(days_for_transactions)
        if transactions:
            report_content.append(f"{'Timestamp'.ljust(22)} | {'Item'.ljust(15)} | {'Type'.ljust(8)} | {'Quantity'.ljust(8)} | {'Object ID'.ljust(10)} | {'Confidence'.ljust(10)}")
            report_content.append("-" * 80)
            for tx in transactions:
                report_content.append(
                    f"{str(tx['timestamp']).ljust(22)} | "
                    f"{tx['item_type'].ljust(15)} | "
                    f"{tx['transaction_type'].ljust(8)} | "
                    f"{str(tx['quantity']).ljust(8)} | "
                    f"{tx['object_id'].ljust(10)} | "
                    f"{tx['confidence']:.2f}".ljust(10)
                )
        else:
            report_content.append(f"  No transactions recorded in the last {days_for_transactions} days.")
        report_content.append("\n\n")


        # --- Page 4: Discrepancy Overview ---
        report_content.append("### PAGE 4: DISCREPANCY SUMMARY ###")
        report_content.append("-" * 40)
        discrepancies = [tx for tx in transactions if tx['transaction_type'] == 'DISCREPANCY']
        if discrepancies:
            report_content.append(f"{'Timestamp'.ljust(22)} | {'Item'.ljust(15)} | {'Object ID'.ljust(10)} | {'Description'}")
            report_content.append("-" * 80)
            for disc in discrepancies:
                report_content.append(
                    f"{str(disc['timestamp']).ljust(22)} | "
                    f"{disc['item_type'].ljust(15)} | "
                    f"{disc['object_id'].ljust(10)} | "
                    f"{disc['description']}"
                )
        else:
            report_content.append("  No discrepancies reported in the last year or period selected.")
        report_content.append("\n\n")

        # Save the report to a file
        try:
            with open(output_filename, "w") as f:
                f.write("\n".join(report_content))
            logger.info(f"Report successfully generated and saved to '{output_filename}'")
        except IOError as e:
            logger.error(f"Failed to write report to file '{output_filename}': {e}")
        finally:
            self.db.close() # Close DB connection after report generation

if __name__ == "__main__":
    reporter = InventoryReporter()
    # You can customize the number of days for transaction history here
    reporter.generate_full_report(days_for_transactions=7) # Reports transactions from the last 7 days
