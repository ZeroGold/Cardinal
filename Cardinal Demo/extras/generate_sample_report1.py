# generate_sample_report.py

import os
from datetime import datetime, timedelta
import logging
from fpdf import FPDF # Import FPDF

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
# NO DATABASE CONNECTION IS MADE OR REQUIRED FOR THIS SCRIPT

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
    {"timestamp": now - timedelta(hours=1), "item_type": "Widget A", "transaction_type": "IN", "quantity": 1, "object_id": "obj101", "confidence": 0.95, "location_id": SAMPLE_LOCATION_ID, "description": "N/A"},
    {"timestamp": now - timedelta(hours=2), "item_type": "Gadget B", "transaction_type": "IN", "quantity": 1, "object_id": "obj102", "confidence": 0.92, "location_id": SAMPLE_LOCATION_ID, "description": "N/A"},
    {"timestamp": now - timedelta(hours=3), "item_type": "Widget A", "transaction_type": "IN", "quantity": 1, "object_id": "obj103", "confidence": 0.96, "location_id": SAMPLE_LOCATION_ID, "description": "N/A"},
    # Recent OUTs
    {"timestamp": now - timedelta(hours=4), "item_type": "Thingamajig C", "transaction_type": "OUT", "quantity": 1, "object_id": "obj104", "confidence": 0.88, "location_id": SAMPLE_LOCATION_ID, "description": "N/A"},
    {"timestamp": now - timedelta(hours=5), "item_type": "Gadget B", "transaction_type": "OUT", "quantity": 1, "object_id": "obj105", "confidence": 0.90, "location_id": SAMPLE_LOCATION_ID, "description": "N/A"},
    # A discrepancy
    {"timestamp": now - timedelta(days=1, hours=6), "item_type": "Doodad D", "transaction_type": "DISCREPANCY", "quantity": 1, "object_id": "obj106", "confidence": 0.75, "location_id": SAMPLE_LOCATION_ID, "description": "Item disappeared from view without explicit OUT event."},
    # Older transactions
    {"timestamp": now - timedelta(days=2, hours=10), "item_type": "Unit E", "transaction_type": "IN", "quantity": 1, "object_id": "obj107", "confidence": 0.98, "location_id": SAMPLE_LOCATION_ID, "description": "N/A"},
    {"timestamp": now - timedelta(days=3, hours=15), "item_type": "Widget A", "transaction_type": "IN", "quantity": 1, "object_id": "obj108", "confidence": 0.94, "location_id": SAMPLE_LOCATION_ID, "description": "N/A"},
    {"timestamp": now - timedelta(days=6, hours=20), "item_type": "Thingamajig C", "transaction_type": "IN", "quantity": 1, "object_id": "obj109", "confidence": 0.89, "location_id": SAMPLE_LOCATION_ID, "description": "N/A"},
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

    def generate_full_report(self, days_for_transactions=7, output_filename="sample_inventory_report.pdf"):
        """Generates a multi-page sample inventory report and saves it to a PDF file."""
        pdf = FPDF('P', 'mm', 'A4') # Portrait, millimeters, A4 size
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # --- Report Header / Cover Page ---
        pdf.add_page()
        pdf.set_font('Arial', 'B', 24)
        pdf.cell(0, 10, 'SAMPLE INVENTORY REPORT', 0, 1, 'C')
        pdf.set_font('Arial', '', 12)
        pdf.cell(0, 10, f'For Location: {self.location_id}', 0, 1, 'C')
        pdf.cell(0, 10, f'Generated On: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'C')
        pdf.ln(20) # Line break
        pdf.set_font('Arial', 'B', 14)
        pdf.set_text_color(255, 0, 0) # Red color for warning
        pdf.cell(0, 10, '!!! THIS IS A SAMPLE REPORT - DATA IS FOR DEMONSTRATION PURPOSES ONLY !!!', 0, 1, 'C')
        pdf.set_text_color(0, 0, 0) # Reset color to black
        pdf.ln(10)

        # --- Page 1: Executive Summary - Current Inventory Snapshot ---
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, 'PAGE 1: CURRENT INVENTORY SNAPSHOT (Sample Data)', 0, 1, 'L')
        pdf.set_font('Arial', '', 12)
        pdf.ln(5)
        current_inventory = self._get_current_inventory()
        if current_inventory:
            for item, count in current_inventory.items():
                pdf.cell(0, 10, f'  - {item}: {count}', 0, 1)
        else:
            pdf.cell(0, 10, '  No sample items currently in inventory.', 0, 1)
        pdf.ln(10)

        # --- Page 2: Detailed Current Inventory (Placeholder for future expansion) ---
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, 'PAGE 2: DETAILED INVENTORY BREAKDOWN (Sample Data)', 0, 1, 'L')
        pdf.set_font('Arial', '', 12)
        pdf.ln(5)
        if current_inventory:
            for item, count in current_inventory.items():
                pdf.cell(0, 10, f'  - {item}: {count} (Across all ROIs in {self.location_id})', 0, 1)
        else:
            pdf.cell(0, 10, '  No detailed sample inventory data available.', 0, 1)
        pdf.ln(10)

        # --- Page 3: Recent Transactions Log ---
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, f'PAGE 3: RECENT TRANSACTIONS (Last {days_for_transactions} Days - Sample Data)', 0, 1, 'L')
        pdf.set_font('Arial', 'B', 10) # Smaller font for table headers
        pdf.ln(5)

        # Table Header
        col_widths = [30, 40, 20, 20, 25, 20] # Adjust column widths as needed
        pdf.cell(col_widths[0], 7, 'Timestamp', 1, 0, 'C')
        pdf.cell(col_widths[1], 7, 'Item', 1, 0, 'C')
        pdf.cell(col_widths[2], 7, 'Type', 1, 0, 'C')
        pdf.cell(col_widths[3], 7, 'Qty', 1, 0, 'C')
        pdf.cell(col_widths[4], 7, 'Object ID', 1, 0, 'C')
        pdf.cell(col_widths[5], 7, 'Conf', 1, 1, 'C') # 1 for newline

        pdf.set_font('Arial', '', 9) # Smaller font for table content
        transactions = self._get_transactions(days_for_transactions)
        if transactions:
            for tx in transactions:
                # Add a check for page break before adding new row
                if pdf.get_y() > 270: # If near bottom of page (A4 height is ~297mm, 15mm margin from top/bottom)
                    pdf.add_page()
                    pdf.set_font('Arial', 'B', 10) # Re-add headers on new page
                    pdf.cell(col_widths[0], 7, 'Timestamp', 1, 0, 'C')
                    pdf.cell(col_widths[1], 7, 'Item', 1, 0, 'C')
                    pdf.cell(col_widths[2], 7, 'Type', 1, 0, 'C')
                    pdf.cell(col_widths[3], 7, 'Qty', 1, 0, 'C')
                    pdf.cell(col_widths[4], 7, 'Object ID', 1, 0, 'C')
                    pdf.cell(col_widths[5], 7, 'Conf', 1, 1, 'C')
                    pdf.set_font('Arial', '', 9) # Back to content font

                pdf.cell(col_widths[0], 7, str(tx['timestamp'].strftime('%Y-%m-%d %H:%M:%S')), 1, 0)
                pdf.cell(col_widths[1], 7, tx['item_type'], 1, 0)
                pdf.cell(col_widths[2], 7, tx['transaction_type'], 1, 0, 'C')
                pdf.cell(col_widths[3], 7, str(tx['quantity']), 1, 0, 'C')
                pdf.cell(col_widths[4], 7, tx['object_id'], 1, 0)
                pdf.cell(col_widths[5], 7, f"{tx['confidence']:.2f}", 1, 1, 'C')
        else:
            pdf.cell(0, 10, f'  No sample transactions recorded in the last {days_for_transactions} days.', 0, 1)
        pdf.ln(10)


        # --- Page 4: Discrepancy Overview ---
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, 'PAGE 4: DISCREPANCY SUMMARY (Sample Data)', 0, 1, 'L')
        pdf.set_font('Arial', 'B', 10)
        pdf.ln(5)

        # Table Header
        disc_col_widths = [30, 40, 25, 80] # Adjust as needed
        pdf.cell(disc_col_widths[0], 7, 'Timestamp', 1, 0, 'C')
        pdf.cell(disc_col_widths[1], 7, 'Item', 1, 0, 'C')
        pdf.cell(disc_col_widths[2], 7, 'Object ID', 1, 0, 'C')
        pdf.cell(disc_col_widths[3], 7, 'Description', 1, 1, 'C')

        pdf.set_font('Arial', '', 9)
        discrepancies = [tx for tx in transactions if tx['transaction_type'] == 'DISCREPANCY']
        if discrepancies:
            for disc in discrepancies:
                if pdf.get_y() > 270: # Check for page break
                    pdf.add_page()
                    pdf.set_font('Arial', 'B', 10)
                    pdf.cell(disc_col_widths[0], 7, 'Timestamp', 1, 0, 'C')
                    pdf.cell(disc_col_widths[1], 7, 'Item', 1, 0, 'C')
                    pdf.cell(disc_col_widths[2], 7, 'Object ID', 1, 0, 'C')
                    pdf.cell(disc_col_widths[3], 7, 'Description', 1, 1, 'C')
                    pdf.set_font('Arial', '', 9)

                pdf.cell(disc_col_widths[0], 7, str(disc['timestamp'].strftime('%Y-%m-%d %H:%M:%S')), 1, 0)
                pdf.cell(disc_col_widths[1], 7, disc['item_type'], 1, 0)
                pdf.cell(disc_col_widths[2], 7, disc['object_id'], 1, 0)
                
                # Multi-line cell for description if needed
                x, y = pdf.get_x(), pdf.get_y()
                pdf.multi_cell(disc_col_widths[3], 7, disc['description'], 1, 'L')
                pdf.set_xy(x + disc_col_widths[3], y) # Move cursor back after multi_cell
                pdf.ln() # Move to next line for next row

        else:
            pdf.cell(0, 10, '  No sample discrepancies reported.', 0, 1)
        pdf.ln(10)

        # Save the PDF
        try:
            pdf.output(output_filename)
            logger.info(f"Sample report successfully generated and saved to '{output_filename}'")
        except Exception as e:
            logger.error(f"Failed to write sample report to PDF file '{output_filename}': {e}")


if __name__ == "__main__":
    reporter = SampleInventoryReporter()
    reporter.generate_full_report(days_for_transactions=7)
