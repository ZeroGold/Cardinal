# generate_sample_report.py

import os
from datetime import datetime, timedelta
import logging

# Ensure logging is set up for this script as well
def setup_logging(log_file="sample_report_generation.log", level=logging.INFO):
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

# --- Sample Data Definitions ---
# These simulate the data that would normally come from your database

SAMPLE_LOCATION_ID = "DEMO_SITE_A"

SAMPLE_CURRENT_INVENTORY = {
    "Widget A": 15,
    "Gadget B": 8,
    "Thingamajig C": 3,
    "Doodad D": 0,
    "Unit E": 20
}

# Simulate transactions over the last few days
now = datetime.now()
SAMPLE_TRANSACTIONS = [
    # Recent INs
    {"timestamp": now - timedelta(hours=1), "item_type": "Widget A", "transaction_type": "IN", "quantity": 1, "object_id": "obj101", "confidence": 0.95, "location_id": SAMPLE_LOCATION_ID},
    {"timestamp": now - timedelta(hours=2), "item_type": "Gadget B", "transaction_type": "IN", "quantity": 1, "object_id": "obj102", "confidence": 0.92, "location_id": SAMPLE_LOCATION_ID},
    {"timestamp": now - timedelta(hours=3), "item_type": "Widget A", "transaction_type": "IN", "quantity": 1, "object_id": "obj103", "confidence": 0.96, "location_id": SAMPLE_LOCATION_ID},
    # Recent OUTs
    {"timestamp": now - timedelta(hours=4), "item_type": "Thingamajig C", "transaction_type": "OUT", "quantity": 1, "object_id": "obj104", "confidence": 0.88, "location_id": SAMPLE_LOCATION_ID},
    {"timestamp": now - timedelta(hours=5), "item_type": "Gadget B", "transaction_type": "OUT", "quantity": 1, "object_id": "obj105", "confidence": 0.90, "location_id": SAMPLE_LOCATION_ID},
    # A discrepancy
    {"timestamp": now - timedelta(days=1, hours=6), "item_type": "Doodad D", "transaction_type": "DISCREPANCY", "quantity": 1, "object_id": "obj106", "confidence": 0.75, "location_id": SAMPLE_LOCATION_ID, "description": "Item disappeared from view without explicit OUT event."},
    # Older transactions
    {"timestamp": now - timedelta(days=2, hours=10), "item_type": "Unit E", "transaction_type": "IN", "quantity": 1, "object_id": "obj107", "confidence": 0.98, "location_id": SAMPLE_LOCATION_ID},
    {"timestamp": now - timedelta(days=3, hours=15), "item_type": "Widget A", "transaction_type": "IN", "quantity": 1, "object_id": "obj108", "confidence": 0.94, "location_id": SAMPLE_LOCATION_ID},
    {"timestamp": now - timedelta(days=6, hours=20), "item_type": "Thingamajig C", "transaction_type": "IN", "quantity": 1, "object_id": "obj109", "confidence": 0.89, "location_id": SAMPLE_LOCATION_ID},
]

class SampleInventoryReporter:
    def __init__(self):
        self.location_id = SAMPLE_LOCATION_ID
        logger.info(f"Sample report generator initialized for location: {self.location_id}")

    def _get_current_inventory(self):
        """Returns the sample current inventory state."""
        logger.info(f"Using sample current inventory for {self.location_id}...")
        return SAMPLE_CURRENT_INVENTORY

    def _get_transactions(self, days_ago=7):
        """Returns sample transactions filtered by the last N days."""
        logger.info(f"Using sample transactions for the last {days_ago} days for {self.location_id}...")
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days_ago)
        
        # Filter sample transactions by time and location
        filtered_transactions = [
            tx for tx in SAMPLE_TRANSACTIONS 
            if start_time <= tx["timestamp"] <= end_time and tx["location_id"] == self.location_id
        ]
        # Sort by timestamp (most recent first for consistency in display)
        filtered_transactions.sort(key=lambda x: x["timestamp"], reverse=True)
        return filtered_transactions

    def generate_full_report(self, days_for_transactions=7, output_filename="sample_inventory_report.txt"):
        """Generates a multi-page sample inventory report and saves it to a file."""
        report_content = []

        # --- Report Header / Cover Page ---
        report_content.append("="*80)
        report_content.append(f"               SAMPLE INVENTORY REPORT FOR LOCATION: {self.location_id}")
        report_content.append(f"               Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_content.append("="*80)
        report_content.append("\n" * 2) # Add more newlines for a visual page break
        report_content.append("### THIS IS A SAMPLE REPORT - DATA IS FOR DEMONSTRATION PURPOSES ONLY ###")
        report_content.append("\n" * 3) # More newlines for visual separation

        # --- Page 1: Executive Summary - Current Inventory Snapshot ---
        report_content.append("### PAGE 1: CURRENT INVENTORY SNAPSHOT (Sample Data) ###")
        report_content.append("-" * 40)
        current_inventory = self._get_current_inventory()
        if current_inventory:
            for item, count in current_inventory.items():
                report_content.append(f"  - {item.ljust(25)} : {count}")
        else:
            report_content.append("  No sample items currently in inventory.")
        report_content.append("\n" * 2) # Visual page break

        # --- Page 2: Detailed Current Inventory (Placeholder for future expansion) ---
        report_content.append("### PAGE 2: DETAILED INVENTORY BREAKDOWN (Sample Data) ###")
        report_content.append("-" * 40)
        if current_inventory:
            for item, count in current_inventory.items():
                report_content.append(f"  - {item.ljust(25)} : {count} (Across all ROIs in {self.location_id})")
        else:
            report_content.append("  No detailed sample inventory data available.")
        report_content.append("\n" * 2) # Visual page break


        # --- Page 3: Recent Transactions Log ---
        report_content.append(f"### PAGE 3: RECENT TRANSACTIONS (Last {days_for_transactions} Days - Sample Data) ###")
        report_content.append("-" * 80)
        transactions = self._get_transactions(days_for_transactions)
        if transactions:
            report_content.append(f"{'Timestamp'.ljust(22)} | {'Item'.ljust(15)} | {'Type'.ljust(8)} | {'Qty'.ljust(4)} | {'Obj ID'.ljust(8)} | {'Conf'.ljust(4)}")
            report_content.append("-" * 80)
            for tx in transactions:
                report_content.append(
                    f"{tx['timestamp'].strftime('%Y-%m-%d %H:%M:%S').ljust(22)} | " # Format timestamp
                    f"{tx['item_type'].ljust(15)} | "
                    f"{tx['transaction_type'].ljust(8)} | "
                    f"{str(tx['quantity']).ljust(4)} | "
                    f"{tx['object_id'].ljust(8)} | "
                    f"{f'{tx['confidence']:.2f}'.ljust(4)}"
                )
        else:
            report_content.append(f"  No sample transactions recorded in the last {days_for_transactions} days.")
        report_content.append("\n" * 2) # Visual page break


        # --- Page 4: Discrepancy Overview ---
        report_content.append("### PAGE 4: DISCREPANCY SUMMARY (Sample Data) ###")
        report_content.append("-" * 40)
        discrepancies = [tx for tx in transactions if tx['transaction_type'] == 'DISCREPANCY']
        if discrepancies:
            report_content.append(f"{'Timestamp'.ljust(22)} | {'Item'.ljust(15)} | {'Object ID'.ljust(10)} | {'Description'}")
            report_content.append("-" * 80)
            for disc in discrepancies:
                report_content.append(
                    f"{disc['timestamp'].strftime('%Y-%m-%d %H:%M:%S').ljust(22)} | " # Format timestamp
                    f"{disc['item_type'].ljust(15)} | "
                    f"{disc['object_id'].ljust(10)} | "
                    f"{disc['description']}"
                )
        else:
            report_content.append("  No sample discrepancies reported.")
        report_content.append("\n" * 2)

        # Save the report to a file
        try:
            with open(output_filename, "w") as f:
                f.write("\n".join(report_content))
            logger.info(f"Sample report successfully generated and saved to '{output_filename}'")
        except IOError as e:
            logger.error(f"Failed to write sample report to file '{output_filename}': {e}")


if __name__ == "__main__":
    reporter = SampleInventoryReporter()
    # You can customize the number of days for sample transaction history here
    reporter.generate_full_report(days_for_transactions=7) # Reports sample transactions from the last 7 days
