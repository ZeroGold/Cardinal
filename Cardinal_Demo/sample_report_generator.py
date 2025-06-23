import pandas as pd
from fpdf import FPDF
import matplotlib.pyplot as plt
import io
import base64
import os
from datetime import datetime, timedelta
import random
import logging
from collections import defaultdict
import tempfile # Import tempfile for temporary file handling

# --- Configuration for Output Folder ---
OUTPUT_FOLDER = "inventory_reports" # Define the desired output folder name
# --- End Configuration ---

# Setup logging for the sample report
def setup_logging(log_file="sample_report_generation.log", level=logging.INFO):
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

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


class PDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_auto_page_break(auto=True, margin=15)
        self.alias_nb_pages()

        # Define colors using RGB tuples
        self.PRIMARY_COLOR = (72, 120, 166)  # A shade of blue for headers/borders
        self.ACCENT_COLOR = (240, 180, 50)   # An orange/gold for highlights
        self.TEXT_COLOR = (50, 50, 50)       # Dark grey for general text
        self.HEADER_BG_COLOR = (220, 230, 240) # Light blue-grey for table headers
        self.ROW_EVEN_COLOR = (248, 248, 248) # Very light grey for even rows
        self.ROW_ODD_COLOR = (255, 255, 255) # White for odd rows
        self.BORDER_COLOR = (200, 200, 200)  # Light grey for table borders

    def header(self):
        self.set_fill_color(*self.PRIMARY_COLOR)
        self.rect(0, 0, self.w, 20, 'F')
        self.set_text_color(255, 255, 255) # White text for header
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Sample Inventory Report', 0, 1, 'C') # Changed title for sample report
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(*self.TEXT_COLOR)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.set_text_color(*self.PRIMARY_COLOR)
        self.cell(0, 10, title, 0, 1, 'L')
        self.set_text_color(*self.TEXT_COLOR) # Reset text color
        self.ln(4)

    def section_title(self, title, level=1):
        if level == 1:
            self.set_font('Arial', 'B', 14)
            self.set_text_color(*self.PRIMARY_COLOR)
            self.ln(8)
            self.cell(0, 10, title, 0, 1, 'L')
            self.set_text_color(*self.TEXT_COLOR)
            self.ln(2)
        elif level == 2:
            self.set_font('Arial', 'B', 12)
            self.set_text_color(*self.ACCENT_COLOR)
            self.ln(5)
            self.cell(0, 7, title, 0, 1, 'L')
            self.set_text_color(*self.TEXT_COLOR)
            self.ln(2)

    def chapter_body(self, body):
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 5, body)
        self.ln()

    def add_table(self, headers, data, col_widths, header_bg_color, row_even_color, row_odd_color, border_color):
        self.set_font('Arial', 'B', 9)
        self.set_fill_color(*header_bg_color)
        self.set_text_color(255, 255, 255) # White text for header
        self.set_draw_color(*border_color)

        # Print header
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 7, header, 1, 0, 'C', fill=True)
        self.ln()

        # Print data
        self.set_font('Arial', '', 8)
        self.set_text_color(*self.TEXT_COLOR)

        row_counter = 0
        for row in data:
            if row_counter % 2 == 0:
                self.set_fill_color(*row_even_color)
            else:
                self.set_fill_color(*row_odd_color)
            
            # Check for page break before drawing a new row
            if self.get_y() > (self.h - 30):
                self.add_page()
                self.set_font('Arial', 'B', 9)
                self.set_fill_color(*header_bg_color)
                self.set_text_color(255, 255, 255) # White text for header
                for i, header in enumerate(headers):
                    self.cell(col_widths[i], 7, header, 1, 0, 'C', fill=True)
                self.ln()
                self.set_font('Arial', '', 8)
                self.set_text_color(*self.TEXT_COLOR)
                row_counter = 0 # Reset row counter for new page for alternating colors
                if row_counter % 2 == 0:
                    self.set_fill_color(*row_even_color)
                else:
                    self.set_fill_color(*row_odd_color)

            for i, item in enumerate(row):
                self.cell(col_widths[i], 7, str(item), 1, 0, 'L', fill=True)
            self.ln()
            row_counter += 1
        self.ln(5)


class ReportGenerator:
    def __init__(self, data_processor):
        self.data_processor = data_processor

    def _get_top_active_item_types(self, transactions_data, top_n=3):
        # Calculate total quantity for IN and OUT transactions for each item type
        item_activity = {}
        for tx in transactions_data:
            if tx['transaction_type'] in ['IN', 'OUT']:
                item_type = tx['item_type']
                quantity = tx['quantity']
                item_activity[item_type] = item_activity.get(item_type, 0) + quantity
        
        # Sort items by their total activity (quantity) in descending order
        sorted_items = sorted(item_activity.items(), key=lambda item: item[1], reverse=True)
        
        # Return the top N item types
        return [item[0] for item in sorted_items[:top_n]]

    # Helper to get the most active item type for the line chart if not specified
    def _get_most_active_item_type(self, transactions):
        item_activity = defaultdict(int)
        for tx in transactions:
            item_activity[tx['item_type']] += tx['quantity'] # Sum quantities for overall activity
        
        if item_activity:
            return max(item_activity, key=item_activity.get)
        return None

    def _generate_daily_transaction_chart(self, transactions, output_path="daily_transactions.png"):
        """Generates a bar chart of daily in/out transactions."""
        daily_in = defaultdict(int)
        daily_out = defaultdict(int)

        for tx in transactions:
            date = tx['timestamp'].date()
            if tx['transaction_type'] == 'IN':
                daily_in[date] += tx['quantity']
            elif tx['transaction_type'] == 'OUT':
                daily_out[date] += tx['quantity']

        all_dates = sorted(list(set(daily_in.keys()) | set(daily_out.keys())))
        in_counts = [daily_in.get(date, 0) for date in all_dates]
        out_counts = [daily_out.get(date, 0) for date in all_dates]

        if not all_dates:
            logger.info("No transaction data to generate daily transaction chart.")
            return None

        fig, ax = plt.subplots(figsize=(10, 6))
        bar_width = 0.35
        index = range(len(all_dates))

        # FIX: Normalize colors for matplotlib when mixing with alpha
        in_color_rgba = [(c / 255.0) for c in (100, 180, 220)] + [0.8] # A lighter blue
        out_color_rgba = [(c / 255.0) for c in (180, 80, 80)] + [0.8] # A red shade for 'OUT'

        in_bars = ax.bar([i - bar_width/2 for i in index], in_counts, bar_width, label='Items In', color=in_color_rgba)
        out_bars = ax.bar([i + bar_width/2 for i in index], out_counts, bar_width, label='Items Out', color=out_color_rgba)

        ax.set_xlabel('Date')
        ax.set_ylabel('Number of Items')
        ax.set_title('Daily Inventory Transactions')
        ax.set_xticks(index)
        ax.set_xticklabels([date.strftime('%Y-%m-%d') for date in all_dates], rotation=45, ha="right")
        ax.legend()
        fig.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path

    def _generate_most_active_items_chart(self, transactions, output_path="most_active_items.png", top_n=5):
        """Generates a bar chart of the most frequently transacted items."""
        item_counts = defaultdict(int)
        for tx in transactions:
            item_counts[(tx['item_type'], tx['transaction_type'])] += tx['quantity']

        item_activity = defaultdict(int)
        for (item, _), count in item_counts.items():
            item_activity[item] += count

        sorted_items = sorted(item_activity.items(), key=lambda item: item[1], reverse=True)
        top_items = sorted_items[:top_n]

        if not top_items:
            logger.info("No item transaction data to generate most active items chart.")
            return None

        items = [item for item, _ in top_items]
        counts = [count for _, count in top_items]

        fig, ax = plt.subplots(figsize=(10, 6))
        # FIX: Normalize colors for matplotlib when mixing with alpha
        bar_color_rgba = [(c / 255.0) for c in PDF.PRIMARY_COLOR] + [0.8]
        ax.bar(items, counts, color=bar_color_rgba)
        ax.set_xlabel('Item Type')
        ax.set_ylabel('Total Transactions (In & Out)')
        ax.set_title(f'Top {top_n} Most Active Items')
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path

    def _generate_inventory_level_over_time_chart(self, transactions, current_inventory, start_date, end_date, item_type_to_track=None, output_path="inventory_level_over_time.png"):
        """Generates a line graph showing the inventory level of a specific item over time."""

        if not item_type_to_track:
            item_type_to_track = self._get_most_active_item_type(transactions)
            if not item_type_to_track:
                logger.info("No transactions or specific item type to track for inventory level chart.")
                return None
            logger.info(f"Tracking inventory level for most active item: {item_type_to_track}")
        else:
            logger.info(f"Tracking inventory level for specified item: {item_type_to_track}")

        # Filter transactions for the item type to track
        transactions_for_item = [
            tx for tx in transactions if tx['item_type'] == item_type_to_track and start_date <= tx['timestamp'] <= end_date
        ]
        transactions_for_item.sort(key=lambda x: x['timestamp'])

        # Get the inventory level at the very beginning of the report period (start_date)
        # To do this correctly, we need the initial stock BEFORE any transactions in the period.
        # This is a bit tricky with only IN/OUT transactions. A more robust system would have
        # a 'starting inventory' record. For this dummy data, we'll try to estimate by
        # working backwards from the *current* total inventory (which reflects all past transactions)
        # and adjusting for transactions *within* the filter period.
        
        # Calculate current total inventory based on all available transactions (not just filtered)
        all_transactions_data = self.data_processor.load_transactions()
        full_inventory_at_end = self.data_processor.get_current_inventory(all_transactions_data).get(item_type_to_track, 0)
        
        # Adjust 'full_inventory_at_end' by working backwards through transactions *after* end_date
        # (This is more accurate if you want initial stock *before* the filtered period begins)
        initial_stock_for_chart = full_inventory_at_end
        for tx in reversed(all_transactions_data):
            if tx['timestamp'] > end_date:
                if tx['item_type'] == item_type_to_track:
                    if tx['transaction_type'] == 'IN':
                        initial_stock_for_chart -= tx['quantity']
                    elif tx['transaction_type'] == 'OUT':
                        initial_stock_for_chart += tx['quantity']
                    elif tx['transaction_type'] == 'DISCREPANCY':
                        # Assuming positive quantity for DISCREPANCY means 'missing'/'reduction' from expected.
                        # So, going backward, we add it back.
                        initial_stock_for_chart += tx['quantity']


        # Now, simulate inventory level day by day within the report range
        daily_levels = {}
        current_level_tracker = initial_stock_for_chart

        # Adjust current_level_tracker for transactions that occurred *before* start_date but after the very beginning of dummy data
        for tx in all_transactions_data:
            if tx['timestamp'] < start_date and tx['item_type'] == item_type_to_track:
                 if tx['transaction_type'] == 'IN':
                    current_level_tracker += tx['quantity']
                 elif tx['transaction_type'] == 'OUT':
                    current_level_tracker -= tx['quantity']
                 elif tx['transaction_type'] == 'DISCREPANCY':
                    current_level_tracker -= tx['quantity']

        # Now track forward from the start_date of the report
        
        # Ensure end_date includes the current day (if it was set to start of day)
        end_date_for_range = end_date
        if end_date.time() == datetime.min.time():
            end_date_for_range = end_date.replace(hour=23, minute=59, second=59)

        date_range = [start_date.date() + timedelta(days=i) for i in range((end_date_for_range.date() - start_date.date()).days + 1)]
        
        # Create a dictionary for quick lookup of transactions by date
        transactions_by_date = defaultdict(list)
        for tx in transactions_for_item:
            transactions_by_date[tx['timestamp'].date()].append(tx)

        for day in date_range:
            # Apply all transactions that occurred on this specific day
            for tx in transactions_by_date[day]:
                if tx['transaction_type'] == 'IN':
                    current_level_tracker += tx['quantity']
                elif tx['transaction_type'] == 'OUT':
                    current_level_tracker -= tx['quantity']
                elif tx['transaction_type'] == 'DISCREPANCY':
                    current_level_tracker -= tx['quantity'] # Assuming positive quantity means a reduction/missing

            daily_levels[day] = current_level_tracker

        if not daily_levels:
            logger.info(f"No daily inventory level data for {item_type_to_track} to generate chart.")
            return None

        dates = sorted(daily_levels.keys())
        levels = [daily_levels[d] for d in dates]

        fig, ax = plt.subplots(figsize=(10, 6))
        # FIX: Normalize colors for matplotlib when mixing with alpha
        line_color_rgba = [(c / 255.0) for c in PDF.PRIMARY_COLOR] + [0.8]
        ax.plot(dates, levels, marker='o', linestyle='-', color=line_color_rgba)
        ax.set_xlabel('Date')
        ax.set_ylabel(f'Inventory Level of {item_type_to_track}')
        ax.set_title(f'Inventory Level for {item_type_to_track} Over Time')
        ax.grid(True)
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path


    def generate_full_report(self, start_date=None, end_date=None, item_type=None, output_filename="inventory_report.pdf"):
        # --- Determine the reporting period string for the header ---
        report_period_str = ""
        current_datetime = datetime.now()
        
        # Convert start/end dates to datetime objects, setting defaults if not provided
        if start_date:
            start_date_obj = pd.to_datetime(start_date)
        else:
            start_date_obj = current_datetime - timedelta(days=7) # Default to 7 days ago

        if end_date:
            end_date_obj = pd.to_datetime(end_date)
            # Ensure end_date includes the full day if only date is provided
            if end_date_obj.hour == 0 and end_date_obj.minute == 0 and end_date_obj.second == 0:
                end_date_obj = end_date_obj.replace(hour=23, minute=59, second=59)
        else:
            end_date_obj = current_datetime # Default to current datetime if no end_date

        report_period_str = f"{start_date_obj.strftime('%Y-%m-%d %H:%M:%S')} to {end_date_obj.strftime('%Y-%m-%d %H:%M:%S')}"
        if start_date_obj.date() == end_date_obj.date():
             report_period_str = f"On {start_date_obj.strftime('%Y-%m-%d')}"
        elif (end_date_obj - start_date_obj).days == 6: # Exactly 7 days range
             report_period_str = f"Last 7 Days (up to {end_date_obj.strftime('%Y-%m-%d')})"


        pdf = PDF()
        pdf.add_page()

        # Define colors for use in the PDF (from PDF class instance)
        PRIMARY_COLOR = pdf.PRIMARY_COLOR
        ACCENT_COLOR = pdf.ACCENT_COLOR
        TEXT_COLOR = pdf.TEXT_COLOR
        HEADER_BG_COLOR = pdf.HEADER_BG_COLOR
        ROW_EVEN_COLOR = pdf.ROW_EVEN_COLOR
        ROW_ODD_COLOR = pdf.ROW_ODD_COLOR
        BORDER_COLOR = pdf.BORDER_COLOR

        # Title Page
        pdf.set_font('Arial', 'B', 24)
        pdf.set_text_color(*PRIMARY_COLOR)
        pdf.cell(0, 80, 'Inventory Management Report', 0, 1, 'C')
        pdf.set_font('Arial', '', 12)
        pdf.set_text_color(*TEXT_COLOR)
        pdf.cell(0, 10, f'Reporting Period: {report_period_str}', 0, 1, 'C')

        if item_type:
            pdf.cell(0, 10, f'Filtered by Item Type: {item_type}', 0, 1, 'C')
        
        pdf.ln(20)
        pdf.set_font('Arial', 'I', 10)
        pdf.cell(0, 10, f'Generated on: {current_datetime.strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'C')
        pdf.add_page()

        # Load and filter data based on determined dates and item type
        transactions_data_raw = self.data_processor.load_transactions()
        transactions_data_filtered = []
        for tx in transactions_data_raw:
            tx_timestamp = pd.to_datetime(tx['timestamp'])
            if start_date_obj <= tx_timestamp <= end_date_obj:
                if item_type is None or tx['item_type'].lower() == item_type.lower():
                    transactions_data_filtered.append(tx)

        current_inventory_data = self.data_processor.get_current_inventory(transactions_data_raw) # Use raw data for full current inventory
        discrepancies = self.data_processor.find_discrepancies(transactions_data_filtered)
        
        # Sort transactions data by timestamp for chronological display
        transactions_data_filtered.sort(key=lambda x: x['timestamp'])

        # Page 1: Executive Summary
        pdf.section_title('1. Executive Summary')
        total_transactions = len(transactions_data_filtered)
        total_in = sum(tx['quantity'] for tx in transactions_data_filtered if tx['transaction_type'] == 'IN')
        total_out = sum(tx['quantity'] for tx in transactions_data_filtered if tx['transaction_type'] == 'OUT')
        total_discrepancy_records = len(discrepancies)

        summary_text = f"""
This report provides an overview of inventory activities for the selected period.
Total transactions recorded: {total_transactions}
Total quantity received (IN): {total_in} units
Total quantity dispatched (OUT): {total_out} units
Number of discrepancies identified: {total_discrepancy_records}
"""
        pdf.chapter_body(summary_text)
        pdf.ln(5)

        # Generate Inventory Distribution Chart
        if current_inventory_data:
            item_types_chart = list(current_inventory_data.keys())
            quantities_chart = list(current_inventory_data.values())

            # Sort by quantity to make the chart more readable
            sorted_pairs = sorted(zip(quantities_chart, item_types_chart), reverse=True)
            quantities_chart = [q for q, _ in sorted_pairs]
            item_types_chart = [it for _, it in sorted_pairs]

            if item_types_chart: # Only plot if there's data
                plt.figure(figsize=(10, 6))
                # FIX: Normalize colors for matplotlib when mixing with alpha
                bar_color_rgba = [(c / 255.0) for c in PRIMARY_COLOR] + [0.8]
                plt.bar(item_types_chart, quantities_chart, color=bar_color_rgba)
                plt.xlabel('Item Type')
                plt.ylabel('Quantity in Stock')
                plt.title('Current Inventory Distribution by Item Type')
                plt.xticks(rotation=45, ha='right')
                plt.tight_layout()

                # --- FIX: Save to temporary file and then load ---
                temp_img_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                        temp_img_path = tmp_file.name
                        plt.savefig(temp_img_path, format='png')
                    plt.close() # Close the plot to free memory

                    pdf.image(temp_img_path, x=pdf.get_x(), y=pdf.get_y(), w=180)
                finally:
                    if temp_img_path and os.path.exists(temp_img_path):
                        os.remove(temp_img_path)
                # --- END FIX ---

                pdf.ln(5)
            else:
                pdf.cell(0, 10, 'No current inventory data to display chart for the selected filters.', 0, 1)
        else:
            pdf.cell(0, 10, 'No current inventory data to display chart.', 0, 1)
        pdf.ln(10)


        # Page 2: Current Inventory Levels
        pdf.add_page()
        pdf.section_title('2. Current Inventory Levels')
        
        inventory_table_data = [[item, qty] for item, qty in current_inventory_data.items()]
        
        if inventory_table_data:
            inventory_headers = ['Item Type', 'Current Quantity']
            inventory_col_widths = [pdf.w / 2 - 15, pdf.w / 2 - 15] # Half width for each column
            pdf.add_table(inventory_headers, inventory_table_data, inventory_col_widths, HEADER_BG_COLOR, ROW_EVEN_COLOR, ROW_ODD_COLOR, BORDER_COLOR)
        else:
            pdf.cell(0, 10, 'No current inventory data available.', 0, 1)
        pdf.ln(10)

        # Page 3: Transaction History
        pdf.add_page()
        pdf.section_title('3. Transaction History')

        transaction_table_data = []
        for tx in transactions_data_filtered:
            transaction_table_data.append([
                tx['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                tx['transaction_type'],
                tx['item_type'],
                tx['quantity'],
                tx['object_id'],
                f"{tx['confidence']:.2f}"
            ])
        
        if transaction_table_data:
            transaction_headers = ['Timestamp', 'Type', 'Item Type', 'Quantity', 'Object ID', 'Confidence']
            transaction_col_widths = [32, 20, 30, 20, 40, 25]
            pdf.add_table(transaction_headers, transaction_table_data, transaction_col_widths, HEADER_BG_COLOR, ROW_EVEN_COLOR, ROW_ODD_COLOR, BORDER_COLOR)
        else:
            pdf.cell(0, 10, 'No transaction data available for the selected period/filters.', 0, 1)
        pdf.ln(10)

        # Page 4: Discrepancy Overview
        pdf.add_page()
        pdf.section_title('4. Discrepancy Overview')

        discrepancy_table_data = []
        for disc in discrepancies:
            discrepancy_table_data.append([
                disc['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                disc['item_type'],
                disc['object_id'],
                disc['description'],
                disc['quantity']
            ])
        
        if discrepancy_table_data:
            discrepancy_headers = ['Timestamp', 'Item Type', 'Object ID', 'Description', 'Quantity']
            discrepancy_col_widths = [32, 30, 40, 60, 25]
            pdf.add_table(discrepancy_headers, discrepancy_table_data, discrepancy_col_widths, HEADER_BG_COLOR, ROW_EVEN_COLOR, ROW_ODD_COLOR, BORDER_COLOR)
        else:
            pdf.cell(0, 10, 'No discrepancies reported in the period or matching filter.', 0, 1)
        pdf.ln(5)

        # --- Discrepancy Impact Analysis ---
        total_discrepancy_quantity = sum(d['quantity'] for d in discrepancies)
        unique_discrepancy_items = set(d['item_type'] for d in discrepancies)
        num_unique_discrepancy_items = len(unique_discrepancy_items)

        total_in_out_quantity = sum(tx['quantity'] for tx in transactions_data_filtered if tx['transaction_type'] in ['IN', 'OUT'])
        total_current_inventory_quantity = sum(current_inventory_data.values()) if current_inventory_data else 0

        pdf.set_text_color(*TEXT_COLOR)
        if discrepancies:
            pdf.cell(0, 7, f"Summary of Discrepancies:", 0, 1)
            pdf.cell(0, 7, f"  - Total quantity involved in discrepancies: {total_discrepancy_quantity} units", 0, 1)
            pdf.cell(0, 7, f"  - Number of unique item types with discrepancies: {num_unique_discrepancy_items}", 0, 1)
            
            if total_in_out_quantity > 0:
                perc_of_transactions = (total_discrepancy_quantity / total_in_out_quantity) * 100
                pdf.cell(0, 7, f"  - Represents {perc_of_transactions:.2f}% of total IN/OUT quantity in this period.", 0, 1)
            else:
                pdf.cell(0, 7, "  - No IN/OUT transactions recorded in this period for percentage comparison.", 0, 1)

            if total_current_inventory_quantity > 0:
                perc_of_current_stock = (total_discrepancy_quantity / total_current_inventory_quantity) * 100
                pdf.cell(0, 7, f"  - Represents {perc_of_current_stock:.2f}% of current total inventory quantity.", 0, 1)
            else:
                pdf.cell(0, 7, "  - No current inventory for percentage comparison.", 0, 1)
            pdf.ln(5)

        else:
            pdf.cell(0, 10, '  No discrepancies reported in the period or matching filter.', 0, 1)
        pdf.ln(5)

        # Page 5: Confidence Score Analysis (Placeholder, if a real ML model was used)
        pdf.add_page()
        pdf.section_title('5. Confidence Score Analysis')
        pdf.chapter_body('This section would provide insights into the confidence scores of object detection and classification, if an ML model was integrated. Analysis could include average confidence, distribution of scores, and low-confidence outliers.')
        
        # Example plot for confidence scores (placeholder data)
        if transactions_data_filtered:
            confidences = [tx['confidence'] for tx in transactions_data_filtered if tx['transaction_type'] != 'DISCREPANCY'] # Exclude 0.0 confidence from discrepancies
            if confidences:
                plt.figure(figsize=(10, 6))
                # FIX: Normalize colors for matplotlib when mixing with alpha
                hist_color_rgba = [(c / 255.0) for c in ACCENT_COLOR] + [0.8]
                plt.hist(confidences, bins=10, edgecolor='black', color=hist_color_rgba)
                plt.xlabel('Confidence Score')
                plt.ylabel('Number of Transactions')
                plt.title('Distribution of Confidence Scores')
                plt.grid(axis='y', alpha=0.75)
                plt.tight_layout()

                # --- FIX: Save to temporary file and then load ---
                temp_img_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                        temp_img_path = tmp_file.name
                        plt.savefig(temp_img_path, format='png')
                    plt.close()

                    pdf.image(temp_img_path, x=pdf.get_x(), y=pdf.get_y(), w=150)
                finally:
                    if temp_img_path and os.path.exists(temp_img_path):
                        os.remove(temp_img_path)
                # --- END FIX ---

                pdf.ln(5)
            else:
                pdf.cell(0, 10, 'No confidence score data to plot.', 0, 1)
        else:
            pdf.cell(0, 10, 'No transaction data available for confidence score analysis.', 0, 1)
        pdf.ln(10)

        # Page 6: System Performance (Placeholder)
        pdf.add_page()
        pdf.section_title('6. System Performance Metrics')
        pdf.chapter_body('This section would detail system performance, such as processing speed, uptime, and resource utilization, if a complete system was being monitored.')
        pdf.ln(10)

        # Page 7: Recommendations
        pdf.add_page()
        pdf.section_title('7. Recommendations')
        pdf.chapter_body('Based on the analysis, here are some recommendations:')
        pdf.ln(5)
        pdf.set_font('Arial', '', 10)
        pdf.multi_cell(0, 6, '- Review high-discrepancy items for potential process improvements or training needs.')
        pdf.multi_cell(0, 6, '- Investigate consistently low confidence scores to improve image quality or model accuracy.')
        pdf.multi_cell(0, 6, '- Implement regular inventory audits to cross-reference with reported discrepancies.')
        pdf.multi_cell(0, 6, '- Ensure clear labeling and consistent lighting for optimal object detection.')
        pdf.ln(10)

        # --- New Section: Appendix - Item-Specific Summaries ---
        top_active_items_for_appendix = []
        if item_type: # If a specific item was filtered, only include that in appendix
            top_active_items_for_appendix = [item_type]
        else: # Otherwise, list the top 3 most active items
            top_active_items_for_appendix = self._get_top_active_item_types(transactions_data_filtered, top_n=3)

        if top_active_items_for_appendix:
            pdf.add_page()
            pdf.section_title('8. Appendix - Item-Specific Summaries')
            pdf.ln(5)

            for i, item_type_appendix in enumerate(top_active_items_for_appendix):
                pdf.add_page() # Start each item summary on a new page for clarity
                pdf.section_title(f'8.{i+1} Item Summary: {item_type_appendix}', level=2)
                
                # Current Status for this item
                current_qty = current_inventory_data.get(item_type_appendix, 0)
                pdf.set_font('Arial', 'B', 10)
                pdf.cell(0, 7, f'Current Stock: {current_qty} units', 0, 1)
                pdf.set_font('Arial', '', 10)
                pdf.ln(3)

                # Transaction History for this item
                pdf.set_font('Arial', 'B', 10)
                pdf.cell(0, 7, 'Recent Transactions:', 0, 1)
                pdf.set_font('Arial', '', 8)
                pdf.ln(2)

                # Table Header for item-specific transactions
                item_tx_col_widths = [32, 20, 15, 25, 20] # No Item Type column
                pdf.set_fill_color(*HEADER_BG_COLOR)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(item_tx_col_widths[0], 7, 'Timestamp', 1, 0, 'C', fill=True)
                pdf.cell(item_tx_col_widths[1], 7, 'Type', 1, 0, 'C', fill=True)
                pdf.cell(item_tx_col_widths[2], 7, 'Qty', 1, 0, 'C', fill=True)
                pdf.cell(item_tx_col_widths[3], 7, 'Object ID', 1, 0, 'C', fill=True)
                pdf.cell(item_tx_col_widths[4], 7, 'Conf.', 1, 1, 'C', fill=True)
                pdf.set_font('Arial', '', 8)
                pdf.set_text_color(*TEXT_COLOR)


                item_transactions = [tx for tx in transactions_data_filtered if tx['item_type'] == item_type_appendix]
                item_transactions.sort(key=lambda x: x['timestamp']) # Ensure chronological order

                row_counter = 0
                if item_transactions:
                    for tx in item_transactions:
                        current_row_fill_color_tuple = None # Store the actual RGB tuple
                        if row_counter % 2 == 0:
                            pdf.set_fill_color(*ROW_EVEN_COLOR)
                            current_row_fill_color_tuple = ROW_EVEN_COLOR
                        else:
                            pdf.set_fill_color(*ROW_ODD_COLOR)
                            current_row_fill_color_tuple = ROW_ODD_COLOR
                        
                        # Check for page break before drawing a new row
                        if pdf.get_y() > (pdf.h - 30):
                            pdf.add_page()
                            pdf.set_font('Arial', 'B', 9)
                            pdf.set_fill_color(*HEADER_BG_COLOR)
                            pdf.set_text_color(255, 255, 255)
                            pdf.cell(item_tx_col_widths[0], 7, 'Timestamp', 1, 0, 'C', fill=True)
                            pdf.cell(item_tx_col_widths[1], 7, 'Type', 1, 0, 'C', fill=True)
                            pdf.cell(item_tx_col_widths[2], 7, 'Qty', 1, 0, 'C', fill=True)
                            pdf.cell(item_tx_col_widths[3], 7, 'Object ID', 1, 0, 'C', fill=True)
                            pdf.cell(item_tx_col_widths[4], 7, 'Conf.', 1, 1, 'C', fill=True)
                            pdf.set_font('Arial', '', 8)
                            pdf.set_text_color(*TEXT_COLOR)
                            row_counter = 0 # Reset row counter for new page for alternating colors
                            # Re-set the fill color based on the new row_counter for the page
                            if row_counter % 2 == 0:
                                pdf.set_fill_color(*ROW_EVEN_COLOR)
                                current_row_fill_color_tuple = ROW_EVEN_COLOR
                            else:
                                pdf.set_fill_color(*ROW_ODD_COLOR)
                                current_row_fill_color_tuple = ROW_ODD_COLOR


                        pdf.cell(item_tx_col_widths[0], 7, str(tx['timestamp'].strftime('%Y-%m-%d %H:%M:%S')), 1, 0, 'L', fill=True)
                        pdf.cell(item_tx_col_widths[1], 7, tx['transaction_type'], 1, 0, 'C', fill=True)
                        pdf.cell(item_tx_col_widths[2], 7, str(tx['quantity']), 1, 0, 'C', fill=True)
                        pdf.cell(item_tx_col_widths[3], 7, tx['object_id'], 1, 0, 'L', fill=True)
                        pdf.cell(item_tx_col_widths[4], 7, f"{tx['confidence']:.2f}", 1, 1, 'C', fill=True)
                        row_counter += 1
                else:
                    pdf.cell(0, 10, '  No transactions recorded for this item in the period.', 0, 1)
                pdf.ln(5)

                # Discrepancy History for this item
                item_discrepancies = [tx for tx in discrepancies if tx['item_type'] == item_type_appendix]
                if item_discrepancies:
                    pdf.set_font('Arial', 'B', 10)
                    pdf.cell(0, 7, 'Related Discrepancies:', 0, 1)
                    pdf.set_font('Arial', '', 8)
                    pdf.ln(2)

                    # Table Header for item-specific discrepancies
                    item_disc_col_widths = [32, 25, 100] # Timestamp, Object ID, Description
                    pdf.set_fill_color(*HEADER_BG_COLOR)
                    pdf.set_text_color(255, 255, 255)
                    pdf.cell(item_disc_col_widths[0], 7, 'Timestamp', 1, 0, 'C', fill=True)
                    pdf.cell(item_disc_col_widths[1], 7, 'Object ID', 1, 0, 'C', fill=True)
                    pdf.cell(item_disc_col_widths[2], 7, 'Description', 1, 1, 'C', fill=True)
                    pdf.set_font('Arial', '', 8)
                    pdf.set_text_color(*TEXT_COLOR)

                    row_counter = 0
                    for disc in item_discrepancies:
                        current_row_fill_color_tuple = None # Store the actual RGB tuple for this discrepancy row
                        if row_counter % 2 == 0:
                            pdf.set_fill_color(*ROW_EVEN_COLOR)
                            current_row_fill_color_tuple = ROW_EVEN_COLOR
                        else:
                            pdf.set_fill_color(*ROW_ODD_COLOR)
                            current_row_fill_color_tuple = ROW_ODD_COLOR

                        # Check for page break
                        if pdf.get_y() > (pdf.h - 30): # FIX: Changed self.h to pdf.h
                            pdf.add_page()
                            pdf.set_font('Arial', 'B', 9)
                            pdf.set_fill_color(*HEADER_BG_COLOR)
                            pdf.set_text_color(255, 255, 255)
                            pdf.cell(item_disc_col_widths[0], 7, 'Timestamp', 1, 0, 'C', fill=True)
                            pdf.cell(item_disc_col_widths[1], 7, 'Object ID', 1, 0, 'C', fill=True)
                            pdf.cell(item_disc_col_widths[2], 7, 'Description', 1, 1, 'C', fill=True)
                            pdf.set_font('Arial', '', 8)
                            pdf.set_text_color(*TEXT_COLOR)
                            row_counter = 0
                            # Re-set the fill color based on the new row_counter for the page
                            if row_counter % 2 == 0:
                                pdf.set_fill_color(*ROW_EVEN_COLOR)
                                current_row_fill_color_tuple = ROW_EVEN_COLOR
                            else:
                                pdf.set_fill_color(*ROW_ODD_COLOR)
                                current_row_fill_color_tuple = ROW_ODD_COLOR

                        start_x = pdf.get_x()
                        start_y = pdf.get_y()

                        pdf.cell(item_disc_col_widths[0], 7, str(disc['timestamp'].strftime('%Y-%m-%d %H:%M:%S')), 1, 0, 'L', fill=True)
                        pdf.cell(item_disc_col_widths[1], 7, disc['object_id'], 1, 0, 'L', fill=True)

                        # Calculate height needed for multi_cell
                        temp_pdf_for_height = FPDF('P', 'mm', 'A4')
                        temp_pdf_for_height.set_font('Arial', '', 8)
                        # This approximation might need refinement for very long texts, but generally works
                        multiline_height = temp_pdf_for_height.get_string_width(disc['description']) / (item_disc_col_widths[2] - 2) * 7
                        num_lines = int(multiline_height / 7) + 1 if multiline_height > 7 else 1

                        # Draw the filled rectangle behind the multi_cell content
                        pdf.set_xy(start_x + item_disc_col_widths[0] + item_disc_col_widths[1], start_y)
                        # FIX: Use the stored current_row_fill_color_tuple
                        pdf.set_fill_color(*current_row_fill_color_tuple)
                        pdf.rect(pdf.get_x(), pdf.get_y(), item_disc_col_widths[2], num_lines * 7, 'F')

                        # Draw the border around the multi_cell content
                        pdf.set_draw_color(*BORDER_COLOR)
                        pdf.rect(pdf.get_x(), pdf.get_y(), item_disc_col_widths[2], num_lines * 7, 'D')

                        # Set position and then print multi_cell
                        pdf.set_xy(start_x + item_disc_col_widths[0] + item_disc_col_widths[1], start_y)
                        pdf.multi_cell(item_disc_col_widths[2], 7, disc['description'], 0, 'L', fill=False)

                        # Reset y position for the next row after multi_cell
                        pdf.set_xy(15, start_y + (num_lines * 7))

                        row_counter += 1
                else:
                    pdf.cell(0, 10, '  No discrepancies recorded for this item in the period.', 0, 1)
                pdf.ln(10)

        # Prepend the output folder path to the filename
        full_output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        pdf.output(full_output_path)
        logger.info(f"Report generated: {full_output_path}")


if __name__ == '__main__':
    # Ensure the output folder exists
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        logger.info(f"Created output directory: {OUTPUT_FOLDER}")

    class DummyDataProcessor:
        def load_transactions(self):
            transactions = []
            item_types = ["Laptop", "Monitor", "Keyboard", "Mouse", "Webcam", "Headphones", "USB Drive", "SSD 1TB", "Printer", "Router", "External HDD 2TB", "Graphics Card"]
            start_date = datetime(2024, 1, 1)
            end_date = datetime.now() # Up to today's date

            current_obj_id = 1000

            for _ in range(300): # Generate more transactions for better data variety
                timestamp = start_date + timedelta(days=random.randint(0, (end_date - start_date).days),
                                                  hours=random.randint(0, 23),
                                                  minutes=random.randint(0, 59),
                                                  seconds=random.randint(0, 59))
                
                transaction_type = random.choice(['IN', 'OUT', 'DISCREPANCY'])
                item_type = random.choice(item_types)
                quantity = random.randint(1, 50) # More varied quantities
                
                object_id = f"OBJ-{current_obj_id:05d}"
                current_obj_id += 1

                confidence = round(random.uniform(0.75, 0.99), 2) if transaction_type != 'DISCREPANCY' else 0.0

                description = ""
                if transaction_type == 'DISCREPANCY':
                    discrepancy_types = [
                        "Quantity mismatch during inbound check.",
                        "Item found damaged in storage.",
                        "Reported missing from last inventory count.",
                        "Extra units discovered, not logged.",
                        "Wrong item type detected in location.",
                        "Serial number mismatch.",
                        "Expired warranty period noted.",
                        "Packaging integrity compromised."
                    ]
                    description = random.choice(discrepancy_types)
                    quantity = random.randint(1, 10) # Smaller quantities for discrepancies

                transactions.append({
                    'timestamp': timestamp,
                    'transaction_type': transaction_type,
                    'item_type': item_type,
                    'quantity': quantity,
                    'object_id': object_id,
                    'confidence': confidence,
                    'description': description
                })
            return transactions

        def get_current_inventory(self, transactions):
            inventory = {}
            for tx in transactions:
                item_type = tx['item_type']
                if tx['transaction_type'] == 'IN':
                    inventory[item_type] = inventory.get(item_type, 0) + tx['quantity']
                elif tx['transaction_type'] == 'OUT':
                    inventory[item_type] = inventory.get(item_type, 0) - tx['quantity']
                elif tx['transaction_type'] == 'DISCREPANCY':
                    # For simplicity in current inventory, treat discrepancies that imply loss as deductions
                    # assuming a positive quantity means items were missing.
                    inventory[item_type] = inventory.get(item_type, 0) - tx['quantity'] # Deduct for missing items
            return {item: max(0, qty) for item, qty in inventory.items() if qty > 0} # Ensure no negative/zero inventory in final view

        def find_discrepancies(self, transactions):
            return [tx for tx in transactions if tx['transaction_type'] == 'DISCREPANCY']

    # Create a dummy data processor instance
    data_processor = DummyDataProcessor()
    
    # Instantiate the report generator
    report_generator = ReportGenerator(data_processor)

    logger.info("Generating sample inventory reports with realistic data...")

    # 1. Full report for all data (last 7 days by default if no dates specified)
    report_generator.generate_full_report(output_filename="realistic_full_inventory_report.pdf")

    # 2. Report for a specific item type (e.g., "Laptop")
    report_generator.generate_full_report(item_type="Laptop", output_filename="realistic_laptop_report.pdf")

    # 3. Report for a specific date range (e.g., last month)
    today = datetime.now()
    one_month_ago = today - timedelta(days=30)
    report_generator.generate_full_report(
        start_date=one_month_ago.strftime("%Y-%m-%d"),
        end_date=today.strftime("%Y-%m-%d"),
        output_filename="realistic_last_month_report.pdf"
    )

    # 4. Report for another specific item type and a custom short range
    two_weeks_ago = today - timedelta(days=14)
    report_generator.generate_full_report(
        start_date=two_weeks_ago.strftime("%Y-%m-%d"),
        end_date=today.strftime("%Y-%m-%d"),
        item_type="Keyboard",
        output_filename="realistic_keyboard_last_2weeks_report.pdf"
    )

    logger.info("\nRealistic dummy reports generated. Check the PDF files in your directory.")
