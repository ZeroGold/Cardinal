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

# --- Custom FPDF Class for Professional Report Styling (for Sample Data) ---
class SampleInventoryPDF(FPDF):
    def __init__(self, location_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.location_id = location_id
        self.report_title_text = "SAMPLE INVENTORY MANAGEMENT REPORT"

    def header(self):
        # Report Title
        self.set_font('Arial', 'B', 15)
        self.set_text_color(50, 50, 150) # Dark Blue
        self.cell(0, 10, self.report_title_text, 0, 1, 'C')
        
        # Location & Date
        self.set_font('Arial', '', 10)
        self.set_text_color(100, 100, 100) # Grey
        self.cell(0, 7, f'Location: {self.location_id} | Generated On: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'C')
        
        # Sample Data Warning
        self.set_font('Arial', 'B', 10)
        self.set_text_color(255, 0, 0) # Red
        self.cell(0, 7, '--- THIS REPORT USES SAMPLE DATA ---', 0, 1, 'C')
        
        # Line break and reset colors/font for content
        self.ln(5)
        self.set_draw_color(150, 150, 150) # Grey line
        self.line(10, self.get_y(), 200, self.get_y()) # Draw a line
        self.ln(5) # Space after line
        self.set_text_color(0, 0, 0) # Black
        
    def footer(self):
        self.set_y(-15) # Position 15mm from bottom
        self.set_font('Arial', 'I', 8) # Italic, 8pt
        self.set_text_color(100, 100, 100) # Grey
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C') # Page number

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
        pdf = SampleInventoryPDF(self.location_id, 'P', 'mm', 'A4') # Use our custom SAMPLE PDF class
        pdf.alias_nb_pages() # Required for {nb} in footer
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_margins(15, 15, 15) # Left, Top, Right margins
        
        # --- Cover Page ---
        pdf.add_page() # This page will have header/footer
        pdf.set_font('Arial', 'B', 36)
        pdf.set_text_color(0, 50, 100) # Darker Blue
        pdf.cell(0, 20, 'Smart Shelf Inventory', 0, 1, 'C')
        pdf.cell(0, 15, 'Automation System', 0, 1, 'C')
        
        pdf.ln(20)
        pdf.set_font('Arial', '', 18)
        pdf.set_text_color(50, 50, 50) # Dark Grey
        pdf.cell(0, 10, f'Detailed Inventory & Transaction Log', 0, 1, 'C')
        pdf.ln(10)
        pdf.cell(0, 10, f'Location: {self.location_id}', 0, 1, 'C')
        pdf.cell(0, 10, f'Report Date: {datetime.now().strftime("%B %d, %Y")}', 0, 1, 'C')
        pdf.ln(30)
        
        pdf.set_font('Arial', 'I', 12)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 10, 'Prepared for [Your Customer Name]', 0, 1, 'C')
        pdf.cell(0, 10, 'Confidential', 0, 1, 'C')
        pdf.set_text_color(0, 0, 0) # Reset color

        # --- Page 1: Executive Summary - Current Inventory Snapshot ---
        pdf.add_page() # This page will have header/footer
        pdf.set_font('Arial', 'B', 16)
        pdf.set_fill_color(220, 230, 240) # Light blue background for section title
        pdf.cell(0, 10, '1. Executive Summary - Current Inventory Snapshot (Sample Data)', 0, 1, 'L', fill=True)
        pdf.set_font('Arial', '', 12)
        pdf.ln(5)
        current_inventory = self._get_current_inventory()
        if current_inventory:
            for item, count in current_inventory.items():
                pdf.cell(50, 10, f'  - {item}:', 0, 0, 'L')
                pdf.cell(0, 10, str(count), 0, 1, 'L')
        else:
            pdf.cell(0, 10, '  No sample items currently in inventory.', 0, 1)
        pdf.ln(10)

        # --- Page 2: Detailed Current Inventory (Placeholder for future expansion) ---
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, '2. Detailed Current Inventory Breakdown (Sample Data)', 0, 1, 'L', fill=True)
        pdf.set_font('Arial', '', 12)
        pdf.ln(5)
        if current_inventory:
            for item, count in current_inventory.items():
                pdf.cell(0, 10, f'  - {item}: {count} units recorded at {self.location_id}', 0, 1)
        else:
            pdf.cell(0, 10, '  No detailed sample inventory data available.', 0, 1)
        pdf.ln(10)

        # --- Page 3: Recent Transactions Log ---
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, f'3. Recent Transactions (Last {days_for_transactions} Days - Sample Data)', 0, 1, 'L', fill=True)
        pdf.set_font('Arial', 'B', 9) # Smaller font for table headers
        pdf.ln(5)

        # Table Header
        col_widths = [32, 40, 20, 15, 25, 20] # Adjust column widths as needed
        # Set header background and text color
        pdf.set_fill_color(200, 220, 240) # Lighter blue for table header
        pdf.set_text_color(0, 0, 0) # Black text
        pdf.cell(col_widths[0], 7, 'Timestamp', 1, 0, 'C', fill=True)
        pdf.cell(col_widths[1], 7, 'Item Type', 1, 0, 'C', fill=True)
        pdf.cell(col_widths[2], 7, 'Type', 1, 0, 'C', fill=True)
        pdf.cell(col_widths[3], 7, 'Qty', 1, 0, 'C', fill=True)
        pdf.cell(col_widths[4], 7, 'Object ID', 1, 0, 'C', fill=True)
        pdf.cell(col_widths[5], 7, 'Conf.', 1, 1, 'C', fill=True) # 1 for newline

        pdf.set_font('Arial', '', 8) # Smaller font for table content
        transactions = self._get_transactions(days_for_transactions)
        if transactions:
            for tx in transactions:
                # Add a check for page break before adding new row
                if pdf.get_y() > (pdf.h - 30): # If near bottom of page (accounting for footer margin)
                    pdf.add_page()
                    pdf.set_font('Arial', 'B', 9) # Re-add headers on new page
                    pdf.set_fill_color(200, 220, 240) # Lighter blue for table header
                    pdf.cell(col_widths[0], 7, 'Timestamp', 1, 0, 'C', fill=True)
                    pdf.cell(col_widths[1], 7, 'Item Type', 1, 0, 'C', fill=True)
                    pdf.cell(col_widths[2], 7, 'Type', 1, 0, 'C', fill=True)
                    pdf.cell(col_widths[3], 7, 'Qty', 1, 0, 'C', fill=True)
                    pdf.cell(col_widths[4], 7, 'Object ID', 1, 0, 'C', fill=True)
                    pdf.cell(col_widths[5], 7, 'Conf.', 1, 1, 'C', fill=True)
                    pdf.set_font('Arial', '', 8) # Back to content font

                pdf.cell(col_widths[0], 7, str(tx['timestamp'].strftime('%Y-%m-%d %H:%M:%S')), 1, 0, 'L')
                pdf.cell(col_widths[1], 7, tx['item_type'], 1, 0, 'L')
                pdf.cell(col_widths[2], 7, tx['transaction_type'], 1, 0, 'C')
                pdf.cell(col_widths[3], 7, str(tx['quantity']), 1, 0, 'C')
                pdf.cell(col_widths[4], 7, tx['object_id'], 1, 0, 'L')
                pdf.cell(col_widths[5], 7, f"{tx['confidence']:.2f}", 1, 1, 'C')
        else:
            pdf.cell(0, 10, f'  No sample transactions recorded in the last {days_for_transactions} days.', 0, 1)
        pdf.ln(10)


        # --- Page 4: Discrepancy Overview ---
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, '4. Discrepancy Summary (Sample Data)', 0, 1, 'L', fill=True)
        pdf.set_font('Arial', 'B', 9)
        pdf.ln(5)

        # Table Header
        disc_col_widths = [32, 40, 25, 80] # Adjust as needed
        pdf.set_fill_color(200, 220, 240) # Lighter blue for table header
        pdf.cell(disc_col_widths[0], 7, 'Timestamp', 1, 0, 'C', fill=True)
        pdf.cell(disc_col_widths[1], 7, 'Item Type', 1, 0, 'C', fill=True)
        pdf.cell(disc_col_widths[2], 7, 'Object ID', 1, 0, 'C', fill=True)
        pdf.cell(disc_col_widths[3], 7, 'Description', 1, 1, 'C', fill=True)

        pdf.set_font('Arial', '', 8)
        discrepancies = [tx for tx in transactions if tx['transaction_type'] == 'DISCREPANCY']
        if discrepancies:
            for disc in discrepancies:
                if pdf.get_y() > (pdf.h - 30): # Check for page break
                    pdf.add_page()
                    pdf.set_font('Arial', 'B', 9)
                    pdf.set_fill_color(200, 220, 240) # Lighter blue for table header
                    pdf.cell(disc_col_widths[0], 7, 'Timestamp', 1, 0, 'C', fill=True)
                    pdf.cell(disc_col_widths[1], 7, 'Item Type', 1, 0, 'C', fill=True)
                    pdf.cell(disc_col_widths[2], 7, 'Object ID', 1, 0, 'C', fill=True)
                    pdf.cell(disc_col_widths[3], 7, 'Description', 1, 1, 'C', fill=True)
                    pdf.set_font('Arial', '', 8)

                # Store current Y for multi_cell alignment trick
                current_y = pdf.get_y() 
                pdf.cell(disc_col_widths[0], 7, str(disc['timestamp'].strftime('%Y-%m-%d %H:%M:%S')), 1, 0, 'L')
                pdf.cell(disc_col_widths[1], 7, disc['item_type'], 1, 0, 'L')
                pdf.cell(disc_col_widths[2], 7, disc['object_id'], 1, 0, 'L')
                
                # Use multi_cell for description to allow text wrapping
                # This requires careful handling of cursor position
                start_x_desc = pdf.get_x()
                pdf.multi_cell(disc_col_widths[3], 7, disc['description'], 1, 'L')
                pdf.set_xy(15, current_y + 7 * (int(pdf.get_string_width(disc['description']) / (disc_col_widths[3] - 2)) + 1)) # Approx height
                if pdf.get_x() != 15: # if the multi_cell didn't automatically go to the next line
                     pdf.ln(7) # Manually move to next line if multi_cell didn't advance far enough

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
