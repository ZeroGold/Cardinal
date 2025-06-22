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
import tempfile
import mysql.connector
from mysql.connector import Error
from scipy.stats import linregress # Import for linear regression

# Import DB_CONFIG from config.py
# Make sure you have a 'config.py' file in the same directory with your DB_CONFIG dictionary
# Assuming config.py contains:
# DB_CONFIG = {
#     'host': os.getenv("DB_HOST", "localhost"),
#     'user': os.getenv("DB_USER", "sample"),
#     'password': os.getenv("DB_PASSWORD", "sample"), # <<<<<<< IMPORTANT: CHANGE THIS IN PRODUCTION!
#     'database': os.getenv("DB_NAME", "cardinal_inventory_db"),
#     'port': int(os.getenv("DB_PORT", 3306))
# }
from config import DB_CONFIG

# --- Configuration ---
OUTPUT_FOLDER = "inventory_reports"
# DB_CONFIG is now imported from config.py
# --- End Configuration ---

# Setup logging
def setup_logging(log_file="report_generation.log", level=logging.INFO):
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
    # Define colors as class attributes
    PRIMARY_COLOR = (72, 120, 166)
    ACCENT_COLOR = (240, 180, 50)
    TEXT_COLOR = (50, 50, 50)
    HEADER_BG_COLOR = (220, 230, 240)
    ROW_EVEN_COLOR = (248, 248, 248)
    ROW_ODD_COLOR = (255, 255, 255)
    BORDER_COLOR = (200, 200, 200)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_auto_page_break(auto=True, margin=15)
        self.alias_nb_pages()
        # No need to redefine self.COLOR = ... here as they are class attributes.
        # They can still be accessed via self.COLOR within PDF methods.


    def header(self):
        self.set_fill_color(*self.PRIMARY_COLOR) # Access via self for consistency in instance methods
        self.rect(0, 0, self.w, 20, 'F')
        self.set_text_color(255, 255, 255)
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Inventory Management Report', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(*self.TEXT_COLOR) # Access via self for consistency in instance methods
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.set_text_color(*self.PRIMARY_COLOR) # Access via self for consistency in instance methods
        self.cell(0, 10, title, 0, 1, 'L')
        self.set_text_color(*self.TEXT_COLOR) # Access via self for consistency in instance methods
        self.ln(4)

    def section_title(self, title, level=1):
        if level == 1:
            self.set_font('Arial', 'B', 14)
            self.set_text_color(*self.PRIMARY_COLOR) # Access via self for consistency in instance methods
            self.ln(8)
            self.cell(0, 10, title, 0, 1, 'L')
            self.set_text_color(*self.TEXT_COLOR) # Access via self for consistency in instance methods
            self.ln(2)
        elif level == 2:
            self.set_font('Arial', 'B', 12)
            self.set_text_color(*self.ACCENT_COLOR) # Access via self for consistency in instance methods
            self.ln(5)
            self.cell(0, 7, title, 0, 1, 'L')
            self.set_text_color(*self.TEXT_COLOR) # Access via self for consistency in instance methods
            self.ln(2)

    def chapter_body(self, body):
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 5, body)
        self.ln()

    def add_table(self, headers, data, col_widths, header_bg_color, row_even_color, row_odd_color, border_color):
        self.set_font('Arial', 'B', 9)
        self.set_fill_color(*header_bg_color)
        self.set_text_color(255, 255, 255)
        self.set_draw_color(*border_color)

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 7, header, 1, 0, 'C', fill=True)
        self.ln()

        self.set_font('Arial', '', 8)
        self.set_text_color(*self.TEXT_COLOR)

        row_counter = 0
        for row in data:
            if row_counter % 2 == 0:
                self.set_fill_color(*row_even_color)
            else:
                self.set_fill_color(*row_odd_color)
            
            if self.get_y() > (self.h - 30):
                self.add_page()
                self.set_font('Arial', 'B', 9)
                self.set_fill_color(*header_bg_color)
                self.set_text_color(255, 255, 255)
                for i, header in enumerate(headers):
                    self.cell(col_widths[i], 7, header, 1, 0, 'C', fill=True)
                self.ln()
                self.set_font('Arial', '', 8)
                self.set_text_color(*self.TEXT_COLOR)
                row_counter = 0
                if row_counter % 2 == 0:
                    self.set_fill_color(*row_even_color)
                else:
                    self.set_fill_color(*row_odd_color)

            for i, item in enumerate(row):
                self.cell(col_widths[i], 7, str(item), 1, 0, 'L', fill=True)
            self.ln()
            row_counter += 1
        self.ln(5)


class DatabaseDataProcessor:
    def __init__(self, db_config):
        self.db_config = db_config
        self._initialize_db()

    def _get_db_connection(self):
        try:
            conn = mysql.connector.connect(**self.db_config)
            return conn
        except Error as e:
            logger.error(f"Error connecting to MySQL database: {e}")
            return None

    def _initialize_db(self):
        conn = None
        try:
            # Connect without specifying database first to create it if it doesn't exist
            temp_config = self.db_config.copy()
            db_name = temp_config.pop('database') # Temporarily remove db name
            conn = mysql.connector.connect(**temp_config)
            cursor = conn.cursor()
            
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
            conn.close() # Close connection to create db, then reconnect to the specific db

            # Reconnect to the newly created/existing database
            conn = self._get_db_connection()
            if conn:
                cursor = conn.cursor()
                
                # Create transaction_log table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transaction_log (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        timestamp DATETIME,
                        item_type VARCHAR(255),
                        event_type VARCHAR(50),
                        quantity_change INT,
                        object_id VARCHAR(255),
                        confidence DOUBLE,
                        location_id VARCHAR(255),
                        associated_sensor_data_id VARCHAR(255),
                        description TEXT
                    )
                ''')

                # Create inventory_current_state table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS inventory_current_state (
                        item_type VARCHAR(255),
                        location_id VARCHAR(255),
                        count INT,
                        last_updated DATETIME,
                        PRIMARY KEY (item_type, location_id)
                    )
                ''')
                conn.commit()
                logger.info(f"Database '{db_name}' and tables 'transaction_log', 'inventory_current_state' initialized successfully.")
        except Error as e:
            logger.error(f"Error initializing database or tables: {e}")
        finally:
            if conn:
                conn.close()

    def is_database_empty(self):
        conn = None
        try:
            conn = self._get_db_connection()
            if conn:
                cursor = conn.cursor()
                # Check if transaction_log (the main source of new data) is empty
                cursor.execute("SELECT COUNT(*) FROM transaction_log")
                count = cursor.fetchone()[0]
                return count == 0
            return True # If connection fails, assume empty or inaccessible
        except Error as e:
            logger.error(f"Error checking if database is empty: {e}")
            return True # Assume empty or error for safety
        finally:
            if conn:
                conn.close()

    # The populate_with_dummy_data method has been removed as per your request.
    # The system is now designed to work with real data generated externally.

    def load_transactions(self):
        conn = None
        transactions = []
        try:
            conn = self._get_db_connection()
            if conn:
                cursor = conn.cursor(dictionary=True) # Returns rows as dictionaries
                cursor.execute("SELECT * FROM transaction_log ORDER BY timestamp ASC")
                rows = cursor.fetchall()
                for row in rows:
                    transactions.append({
                        'timestamp': row['timestamp'],
                        'event_type': row['event_type'], 
                        'item_type': row['item_type'],
                        'quantity_change': row['quantity_change'], 
                        'object_id': row['object_id'],
                        'confidence': row['confidence'],
                        'location_id': row['location_id'], 
                        'associated_sensor_data_id': row['associated_sensor_data_id'], 
                        'description': row['description']
                    })
                logger.info(f"Loaded {len(transactions)} transactions from transaction_log.")
        except Error as e:
            logger.error(f"Error loading transactions from database: {e}")
        finally:
            if conn:
                conn.close()
        return transactions

    def get_current_inventory(self): 
        conn = None
        inventory = defaultdict(int) # Aggregating by item_type for report
        try:
            conn = self._get_db_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                # Summing counts by item_type across all locations from current_state
                cursor.execute("SELECT item_type, SUM(count) as total_count FROM inventory_current_state GROUP BY item_type")
                rows = cursor.fetchall()
                for row in rows:
                    inventory[row['item_type']] = row['total_count']
                logger.info(f"Loaded current inventory from inventory_current_state for {len(inventory)} item types.")
        except Error as e:
            logger.error(f"Error loading current inventory from database: {e}")
        finally:
            if conn:
                conn.close()
        return inventory

    def find_discrepancies(self, transactions):
        # Discrepancies are now based on event_type
        return [tx for tx in transactions if tx['event_type'] == 'DISCREPANCY']


class ReportGenerator:
    def __init__(self, data_processor):
        self.data_processor = data_processor

    def _get_top_active_item_types(self, transactions_data, top_n=3):
        item_activity = {}
        for tx in transactions_data:
            # Use absolute value of quantity_change for activity, as both IN/OUT/DISCREPANCY contribute to activity
            if tx['event_type'] in ['IN', 'OUT', 'DISCREPANCY']:
                item_type = tx['item_type']
                quantity = abs(tx['quantity_change'])
                item_activity[item_type] = item_activity.get(item_type, 0) + quantity
        
        sorted_items = sorted(item_activity.items(), key=lambda item: item[1], reverse=True)
        return [item[0] for item in sorted_items[:top_n]]

    def _get_most_active_item_type(self, transactions):
        item_activity = defaultdict(int)
        for tx in transactions:
            item_activity[tx['item_type']] += abs(tx['quantity_change']) # Use absolute value for activity
        
        if item_activity:
            return max(item_activity, key=item_activity.get)
        return None

    def _generate_daily_transaction_chart(self, transactions, output_path):
        daily_in = defaultdict(int)
        daily_out = defaultdict(int)

        for tx in transactions:
            date = tx['timestamp'].date()
            if tx['event_type'] == 'IN':
                daily_in[date] += tx['quantity_change']
            elif tx['event_type'] == 'OUT':
                daily_out[date] += abs(tx['quantity_change']) # Absolute value for 'OUT' quantity count

        all_dates = sorted(list(set(daily_in.keys()) | set(daily_out.keys())))
        in_counts = [daily_in.get(date, 0) for date in all_dates]
        out_counts = [daily_out.get(date, 0) for date in all_dates]

        if not all_dates:
            logger.info("No transaction data to generate daily transaction chart.")
            return None

        fig, ax = plt.subplots(figsize=(10, 6))
        bar_width = 0.35
        index = range(len(all_dates))

        in_color_rgba = [(c / 255.0) for c in (100, 180, 220)] + [0.8]
        out_color_rgba = [(c / 255.0) for c in (180, 80, 80)] + [0.8]

        ax.bar([i - bar_width/2 for i in index], in_counts, bar_width, label='Items In', color=in_color_rgba)
        ax.bar([i + bar_width/2 for i in index], out_counts, bar_width, label='Items Out', color=out_color_rgba)

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

    def _generate_most_active_items_chart(self, transactions, output_path, top_n=5):
        item_counts = defaultdict(int)
        for tx in transactions:
            item_counts[(tx['item_type'], tx['event_type'])] += abs(tx['quantity_change']) # Use abs for activity

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
        bar_color_rgba = [(c / 255.0) for c in PDF.PRIMARY_COLOR] + [0.8] # Use PDF.PRIMARY_COLOR directly
        ax.bar(items, counts, color=bar_color_rgba)
        ax.set_xlabel('Item Type')
        ax.set_ylabel('Total Transactions (Absolute Quantity Change)')
        ax.set_title(f'Top {top_n} Most Active Items')
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path

    def _generate_inventory_level_over_time_chart(self, transactions, start_date, end_date, item_type_to_track=None, output_path="inventory_level_over_time.png"):
        # The current inventory calculation is now more complex as we need to derive the historical levels.
        # This function will still calculate from transaction_log to show historical trend.
        
        # Load ALL transactions to get a true starting point for the specified item_type
        all_transactions_data = self.data_processor.load_transactions()

        if not all_transactions_data: # If no transactions, no item to track
            logger.info("No transactions to determine most active item for inventory level chart.")
            return None

        if not item_type_to_track:
            item_type_to_track = self._get_most_active_item_type(all_transactions_data)
            if not item_type_to_track:
                logger.info("No transactions or specific item type to track for inventory level chart.")
                return None
            logger.info(f"Tracking inventory level for most active item: {item_type_to_track}")
        else:
            logger.info(f"Tracking inventory level for specified item: {item_type_to_track}")

        # Filter transactions relevant to the item and before/during the report period
        relevant_transactions = [
            tx for tx in all_transactions_data 
            if tx['item_type'] == item_type_to_track and tx['timestamp'] <= end_date
        ]
        relevant_transactions.sort(key=lambda x: x['timestamp'])

        # Calculate initial stock before the start_date
        current_level_tracker = 0
        for tx in relevant_transactions:
            if tx['timestamp'] < start_date:
                current_level_tracker += tx['quantity_change']
            else:
                break # Transactions are sorted, so we've passed the start_date

        daily_levels = {}
        end_date_for_range = end_date
        if end_date.time() == datetime.min.time():
            end_date_for_range = end_date.replace(hour=23, minute=59, second=59)

        date_range = [start_date.date() + timedelta(days=i) for i in range((end_date_for_range.date() - start_date.date()).days + 1)]
        
        transactions_by_date = defaultdict(list)
        for tx in relevant_transactions:
            if tx['timestamp'].date() >= start_date.date() and tx['timestamp'].date() <= end_date_for_range.date():
                transactions_by_date[tx['timestamp'].date()].append(tx)

        for day in date_range:
            for tx in transactions_by_date[day]:
                current_level_tracker += tx['quantity_change']
            daily_levels[day] = max(0, current_level_tracker) # Ensure non-negative stock

        if not daily_levels:
            logger.info(f"No daily inventory level data for {item_type_to_track} to generate chart within the specified range.")
            return None

        dates = sorted(daily_levels.keys())
        levels = [daily_levels[d] for d in dates]

        fig, ax = plt.subplots(figsize=(10, 6))
        line_color_rgba = [(c / 255.0) for c in PDF.PRIMARY_COLOR] + [0.8] # Use PDF.PRIMARY_COLOR
        ax.plot(dates, levels, marker='o', linestyle='-', color=line_color_rgba, label='Inventory Level')
        
        # --- Add Trend Line Logic ---
        if len(dates) > 1: # Need at least 2 points for a line
            # Convert dates to numerical format (days since the first date)
            x_numeric = [(d - dates[0]).days for d in dates]
            
            # Perform linear regression
            slope, intercept, r_value, p_value, std_err = linregress(x_numeric, levels)
            
            # Calculate trend line values
            trend_line = [slope * x + intercept for x in x_numeric]

            trend_color_rgba = [(c / 255.0) for c in PDF.ACCENT_COLOR] + [0.8] # Use PDF.ACCENT_COLOR
            ax.plot(dates, trend_line, linestyle='--', color=trend_color_rgba, label='Trend Line')
            
            trend_direction = "Increasing" if slope > 0.01 else ("Decreasing" if slope < -0.01 else "Stable")
            ax.set_title(f'Inventory Level for {item_type_to_track} Over Time (Trend: {trend_direction})')
            logger.info(f"Trend for {item_type_to_track}: Slope={slope:.2f}, R-squared={r_value**2:.2f}")
        else:
            ax.set_title(f'Inventory Level for {item_type_to_track} Over Time')
        # --- End Trend Line Logic ---

        ax.set_xlabel('Date')
        ax.set_ylabel(f'Inventory Level of {item_type_to_track}')
        ax.grid(True)
        ax.legend() # Show legend for inventory level and trend line
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path


    def generate_full_report(self, start_date=None, end_date=None, item_type=None, output_filename="inventory_report.pdf", output_base_dir=None):
        # Determine the full output path including the subfolder
        if output_base_dir:
            # Ensure the specific output_base_dir exists
            os.makedirs(output_base_dir, exist_ok=True)
            full_output_path = os.path.join(output_base_dir, output_filename)
        else:
            # Fallback to the main OUTPUT_FOLDER if no specific subfolder is provided
            full_output_path = os.path.join(OUTPUT_FOLDER, output_filename)


        current_datetime = datetime.now()

        # Check if transaction_log (main source of truth for history) is empty
        if self.data_processor.is_database_empty():
            logger.warning("Database 'transaction_log' is empty. Generating an empty data report.")
            pdf = PDF()
            pdf.add_page()
            pdf.set_font('Arial', 'B', 24)
            pdf.set_text_color(*PDF.PRIMARY_COLOR) # Use PDF.PRIMARY_COLOR
            pdf.cell(0, 80, 'Inventory Management Report', 0, 1, 'C')
            pdf.set_font('Arial', '', 14)
            pdf.set_text_color(*PDF.TEXT_COLOR) # Use PDF.TEXT_COLOR
            pdf.ln(20)
            pdf.multi_cell(0, 10, 'No inventory data available to generate a detailed report.', 0, 'C')
            pdf.multi_cell(0, 10, 'Please ensure transaction data is loaded into the system via your application.', 0, 'C')
            pdf.ln(30)
            pdf.set_font('Arial', 'I', 10)
            pdf.cell(0, 10, f'Generated on: {current_datetime.strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'C')
            pdf.output(full_output_path)
            logger.info(f"Empty data report generated: {full_output_path}")
            return

        report_period_str = ""
        
        if start_date:
            start_date_obj = pd.to_datetime(start_date)
        else:
            start_date_obj = current_datetime - timedelta(days=30)

        if end_date:
            end_date_obj = pd.to_datetime(end_date)
            if end_date_obj.hour == 0 and end_date_obj.minute == 0 and end_date_obj.second == 0:
                end_date_obj = end_date_obj.replace(hour=23, minute=59, second=59)
        else:
            end_date_obj = current_datetime

        report_period_str = f"{start_date_obj.strftime('%Y-%m-%d %H:%M:%S')} to {end_date_obj.strftime('%Y-%m-%d %H:%M:%S')}"
        if start_date_obj.date() == end_date_obj.date():
             report_period_str = f"On {start_date_obj.strftime('%Y-%m-%d')}"
        elif (end_date_obj - start_date_obj).days == 6:
             report_period_str = f"Last 7 Days (up to {end_date_obj.strftime('%Y-%m-%d')})"
        elif (end_date_obj - start_date_obj).days >= 29 and (end_date_obj - start_date_obj).days <= 31:
             report_period_str = f"Last 30 Days (up to {end_date_obj.strftime('%Y-%m-%d')})"


        pdf = PDF()
        pdf.add_page()

        # Use PDF class attributes directly for consistency
        PRIMARY_COLOR = PDF.PRIMARY_COLOR
        ACCENT_COLOR = PDF.ACCENT_COLOR
        TEXT_COLOR = PDF.TEXT_COLOR
        HEADER_BG_COLOR = PDF.HEADER_BG_COLOR
        ROW_EVEN_COLOR = PDF.ROW_EVEN_COLOR
        ROW_ODD_COLOR = PDF.ROW_ODD_COLOR
        BORDER_COLOR = PDF.BORDER_COLOR

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

        transactions_data_raw = self.data_processor.load_transactions()
        transactions_data_filtered = []
        for tx in transactions_data_raw:
            tx_timestamp = tx['timestamp']
            if start_date_obj <= tx_timestamp <= end_date_obj:
                if item_type is None or tx['item_type'].lower() == item_type.lower():
                    transactions_data_filtered.append(tx)

        # Get current inventory directly from inventory_current_state table
        current_inventory_data = self.data_processor.get_current_inventory()
        discrepancies = self.data_processor.find_discrepancies(transactions_data_filtered)
        
        transactions_data_filtered.sort(key=lambda x: x['timestamp'])

        pdf.section_title('1. Executive Summary')
        total_transactions = len(transactions_data_filtered)
        total_in = sum(tx['quantity_change'] for tx in transactions_data_filtered if tx['event_type'] == 'IN')
        total_out = sum(abs(tx['quantity_change']) for tx in transactions_data_filtered if tx['event_type'] == 'OUT') 
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

        if current_inventory_data:
            item_types_chart = list(current_inventory_data.keys())
            quantities_chart = list(current_inventory_data.values())

            sorted_pairs = sorted(zip(quantities_chart, item_types_chart), reverse=True)
            quantities_chart = [q for q, _ in sorted_pairs]
            item_types_chart = [it for _, it in sorted_pairs]

            if item_types_chart:
                plt.figure(figsize=(10, 6))
                bar_color_rgba = [(c / 255.0) for c in PRIMARY_COLOR] + [0.8]
                plt.bar(item_types_chart, quantities_chart, color=bar_color_rgba)
                plt.xlabel('Item Type')
                plt.ylabel('Quantity in Stock')
                plt.title('Current Inventory Distribution by Item Type')
                plt.xticks(rotation=45, ha='right')
                plt.tight_layout()

                temp_img_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                        temp_img_path = tmp_file.name
                        plt.savefig(temp_img_path, format='png')
                    plt.close()

                    pdf.image(temp_img_path, x=pdf.get_x(), y=pdf.get_y(), w=180)
                finally:
                    if temp_img_path and os.path.exists(temp_img_path):
                        os.remove(temp_img_path)
            else:
                pdf.cell(0, 10, 'No current inventory data to display chart for the selected filters.', 0, 1)
        else:
            pdf.cell(0, 10, 'No current inventory data to display chart.', 0, 1)
        pdf.ln(10)


        pdf.add_page()
        pdf.section_title('2. Current Inventory Levels')
        
        inventory_table_data = [[item, qty] for item, qty in current_inventory_data.items()]
        
        if inventory_table_data:
            inventory_headers = ['Item Type', 'Current Quantity']
            inventory_col_widths = [pdf.w / 2 - 15, pdf.w / 2 - 15]
            pdf.add_table(inventory_headers, inventory_table_data, inventory_col_widths, HEADER_BG_COLOR, ROW_EVEN_COLOR, ROW_ODD_COLOR, BORDER_COLOR)
        else:
            pdf.cell(0, 10, 'No current inventory data available.', 0, 1)
        pdf.ln(10)

        pdf.add_page()
        pdf.section_title('3. Transaction History')

        transaction_table_data = []
        for tx in transactions_data_filtered:
            transaction_table_data.append([
                tx['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                tx['event_type'], 
                tx['item_type'],
                tx['quantity_change'], 
                tx['object_id'],
                f"{tx['confidence']:.2f}"
            ])
        
        if transaction_table_data:
            transaction_headers = ['Timestamp', 'Event Type', 'Item Type', 'Qty Change', 'Object ID', 'Confidence'] 
            transaction_col_widths = [32, 20, 30, 20, 40, 25]
            pdf.add_table(transaction_headers, transaction_table_data, transaction_col_widths, HEADER_BG_COLOR, ROW_EVEN_COLOR, ROW_ODD_COLOR, BORDER_COLOR)
        else:
            pdf.cell(0, 10, 'No transaction data available for the selected period/filters.', 0, 1)
        pdf.ln(10)

        pdf.add_page()
        pdf.section_title('4. Discrepancy Overview')

        discrepancy_table_data = []
        for disc in discrepancies:
            discrepancy_table_data.append([
                disc['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                disc['item_type'],
                disc['object_id'],
                disc['description'],
                disc['quantity_change'] 
            ])
        
        if discrepancy_table_data:
            discrepancy_headers = ['Timestamp', 'Item Type', 'Object ID', 'Description', 'Qty Change'] 
            discrepancy_col_widths = [32, 30, 40, 60, 25]
            pdf.add_table(discrepancy_headers, discrepancy_table_data, discrepancy_col_widths, HEADER_BG_COLOR, ROW_EVEN_COLOR, ROW_ODD_COLOR, BORDER_COLOR)
        else:
            pdf.cell(0, 10, 'No discrepancies reported in the period or matching filter.', 0, 1)
        pdf.ln(5)

        total_discrepancy_quantity = sum(abs(d['quantity_change']) for d in discrepancies) 
        unique_discrepancy_items = set(d['item_type'] for d in discrepancies)
        num_unique_discrepancy_items = len(unique_discrepancy_items)

        total_in_out_quantity = sum(abs(tx['quantity_change']) for tx in transactions_data_filtered if tx['event_type'] in ['IN', 'OUT']) 
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

        pdf.add_page()
        pdf.section_title('5. Confidence Score Analysis')
        pdf.chapter_body('This section would detail system performance, such as processing speed, uptime, and resource utilization, if a complete system was being monitored.')
        pdf.ln(10) # Changed from `pdf.chapter_body`

        if transactions_data_filtered:
            confidences = [tx['confidence'] for tx in transactions_data_filtered if tx['event_type'] != 'DISCREPANCY'] 
            if confidences:
                plt.figure(figsize=(10, 6))
                hist_color_rgba = [(c / 255.0) for c in ACCENT_COLOR] + [0.8]
                plt.hist(confidences, bins=10, edgecolor='black', color=hist_color_rgba)
                plt.xlabel('Confidence Score')
                plt.ylabel('Number of Transactions')
                plt.title('Distribution of Confidence Scores')
                plt.grid(axis='y', alpha=0.75)
                plt.tight_layout()

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
            else:
                pdf.cell(0, 10, 'No confidence score data to plot.', 0, 1)
        else:
            pdf.cell(0, 10, 'No transaction data available for confidence score analysis.', 0, 1)
        pdf.ln(10)

        # Generate Inventory Level Over Time Chart for the most active item
        temp_inv_level_chart_path = None
        try:
            temp_inv_level_chart_path = self._generate_inventory_level_over_time_chart(
                transactions_data_raw, # Pass raw data for proper trend calculation from start of time
                start_date_obj, 
                end_date_obj, 
                item_type_to_track=item_type # Use specified item_type, or it will find most active
            )

            if temp_inv_level_chart_path:
                pdf.add_page()
                pdf.section_title('6. Inventory Level Trend')
                pdf.chapter_body(f'This chart illustrates the historical inventory level and its trend for the most active item (or the filtered item) within the reporting period. A trend line indicates whether the stock is generally increasing, decreasing, or stable.')
                pdf.image(temp_inv_level_chart_path, x=pdf.get_x(), y=pdf.get_y(), w=180)
                pdf.ln(10)
            else:
                pdf.add_page()
                pdf.section_title('6. Inventory Level Trend')
                pdf.cell(0, 10, 'No sufficient data to generate Inventory Level Trend chart for an active item.', 0, 1)
                pdf.ln(10)
        finally:
            if temp_inv_level_chart_path and os.path.exists(temp_inv_level_chart_path):
                os.remove(temp_inv_level_chart_path)


        pdf.add_page()
        pdf.section_title('7. System Performance Metrics')
        pdf.chapter_body('This section would detail system performance, such as processing speed, uptime, and resource utilization, if a complete system was being monitored.')
        pdf.ln(10)

        pdf.add_page()
        pdf.section_title('8. Recommendations')
        pdf.chapter_body('Based on the analysis, here are some recommendations:')
        pdf.ln(5)
        pdf.set_font('Arial', '', 10)
        pdf.multi_cell(0, 6, '- Review high-discrepancy items for potential process improvements or training needs.')
        pdf.multi_cell(0, 6, '- Investigate consistently low confidence scores to improve image quality or model accuracy.')
        pdf.multi_cell(0, 6, '- Implement regular inventory audits to cross-reference with reported discrepancies.')
        pdf.multi_cell(0, 6, '- Ensure clear labeling and consistent lighting for optimal object detection.')
        pdf.ln(10)

        top_active_items_for_appendix = []
        if item_type:
            top_active_items_for_appendix = [item_type]
        else:
            top_active_items_for_appendix = self._get_top_active_item_types(transactions_data_filtered, top_n=3)

        if top_active_items_for_appendix:
            pdf.add_page()
            pdf.section_title('9. Appendix - Item-Specific Summaries')
            pdf.ln(5)

            for i, item_type_appendix in enumerate(top_active_items_for_appendix):
                pdf.add_page()
                pdf.section_title(f'9.{i+1} Item Summary: {item_type_appendix}', level=2)
                
                # Get current quantity for this specific item type from the pre-calculated inventory_current_state
                current_qty = current_inventory_data.get(item_type_appendix, 0)
                pdf.set_font('Arial', 'B', 10)
                pdf.cell(0, 7, f'Current Stock: {current_qty} units', 0, 1)
                pdf.set_font('Arial', '', 10)
                pdf.ln(3)

                pdf.set_font('Arial', 'B', 10)
                pdf.cell(0, 7, 'Recent Transactions:', 0, 1)
                pdf.set_font('Arial', '', 8)
                pdf.ln(2)

                item_tx_col_widths = [32, 20, 15, 25, 20]
                pdf.set_fill_color(*HEADER_BG_COLOR)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(item_tx_col_widths[0], 7, 'Timestamp', 1, 0, 'C', fill=True)
                pdf.cell(item_tx_col_widths[1], 7, 'Event Type', 1, 0, 'C', fill=True) 
                pdf.cell(item_tx_col_widths[2], 7, 'Qty Change', 1, 0, 'C', fill=True) 
                pdf.cell(item_tx_col_widths[3], 7, 'Object ID', 1, 0, 'C', fill=True)
                pdf.cell(item_tx_col_widths[4], 7, 'Conf.', 1, 1, 'C', fill=True)
                pdf.set_font('Arial', '', 8)
                pdf.set_text_color(*TEXT_COLOR)


                item_transactions = [tx for tx in transactions_data_filtered if tx['item_type'] == item_type_appendix]
                item_transactions.sort(key=lambda x: x['timestamp'])

                row_counter = 0
                if item_transactions:
                    for tx in item_transactions:
                        current_row_fill_color_tuple = None
                        if row_counter % 2 == 0:
                            pdf.set_fill_color(*ROW_EVEN_COLOR)
                            current_row_fill_color_tuple = ROW_EVEN_COLOR
                        else:
                            pdf.set_fill_color(*ROW_ODD_COLOR)
                            current_row_fill_color_tuple = ROW_ODD_COLOR
                        
                        if pdf.get_y() > (pdf.h - 30):
                            pdf.add_page()
                            pdf.set_font('Arial', 'B', 9)
                            pdf.set_fill_color(*HEADER_BG_COLOR)
                            pdf.set_text_color(255, 255, 255)
                            pdf.cell(item_tx_col_widths[0], 7, 'Timestamp', 1, 0, 'C', fill=True)
                            pdf.cell(item_tx_col_widths[1], 7, 'Event Type', 1, 0, 'C', fill=True)
                            pdf.cell(item_tx_col_widths[2], 7, 'Qty Change', 1, 0, 'C', fill=True)
                            pdf.cell(item_tx_col_widths[3], 7, 'Object ID', 1, 0, 'C', fill=True)
                            pdf.cell(item_tx_col_widths[4], 7, 'Conf.', 1, 1, 'C', fill=True)
                            pdf.set_font('Arial', '', 8)
                            pdf.set_text_color(*TEXT_COLOR)
                            row_counter = 0
                            if row_counter % 2 == 0:
                                pdf.set_fill_color(*ROW_EVEN_COLOR)
                                current_row_fill_color_tuple = ROW_EVEN_COLOR
                            else:
                                pdf.set_fill_color(*ROW_ODD_COLOR)
                                current_row_fill_color_tuple = ROW_ODD_COLOR


                        pdf.cell(item_tx_col_widths[0], 7, str(tx['timestamp'].strftime('%Y-%m-%d %H:%M:%S')), 1, 0, 'L', fill=True)
                        pdf.cell(item_tx_col_widths[1], 7, tx['event_type'], 1, 0, 'C', fill=True)
                        pdf.cell(item_tx_col_widths[2], 7, str(tx['quantity_change']), 1, 0, 'C', fill=True)
                        pdf.cell(item_tx_col_widths[3], 7, tx['object_id'], 1, 0, 'L', fill=True)
                        pdf.cell(item_tx_col_widths[4], 7, f"{tx['confidence']:.2f}", 1, 1, 'C', fill=True)
                        row_counter += 1
                else:
                    pdf.cell(0, 10, '  No transactions recorded for this item in the period.', 0, 1)
                pdf.ln(5)

                item_discrepancies = [tx for tx in discrepancies if tx['item_type'] == item_type_appendix]
                if item_discrepancies:
                    pdf.set_font('Arial', 'B', 10)
                    pdf.cell(0, 7, 'Related Discrepancies:', 0, 1)
                    pdf.set_font('Arial', '', 8)
                    pdf.ln(2)

                    item_disc_col_widths = [32, 25, 100]
                    pdf.set_fill_color(*HEADER_BG_COLOR)
                    pdf.set_text_color(255, 255, 255)
                    pdf.cell(item_disc_col_widths[0], 7, 'Timestamp', 1, 0, 'C', fill=True)
                    pdf.cell(item_disc_col_widths[1], 7, 'Object ID', 1, 0, 'C', fill=True)
                    pdf.cell(item_disc_col_widths[2], 7, 'Description', 1, 1, 'C', fill=True)
                    pdf.set_font('Arial', '', 8)
                    pdf.set_text_color(*TEXT_COLOR)

                    row_counter = 0
                    for disc in item_discrepancies:
                        current_row_fill_color_tuple = None
                        if row_counter % 2 == 0:
                            pdf.set_fill_color(*ROW_EVEN_COLOR)
                            current_row_fill_color_tuple = ROW_EVEN_COLOR
                        else:
                            pdf.set_fill_color(*ROW_ODD_COLOR)
                            current_row_fill_color_tuple = ROW_ODD_COLOR

                        if pdf.get_y() > (pdf.h - 30):
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

                        temp_pdf_for_height = FPDF('P', 'mm', 'A4')
                        temp_pdf_for_height.set_font('Arial', '', 8)
                        multiline_height = temp_pdf_for_height.get_string_width(disc['description']) / (item_disc_col_widths[2] - 2) * 7
                        num_lines = int(multiline_height / 7) + 1 if multiline_height > 7 else 1

                        pdf.set_xy(start_x + item_disc_col_widths[0] + item_disc_col_widths[1], start_y)
                        pdf.set_fill_color(*current_row_fill_color_tuple)
                        pdf.rect(pdf.get_x(), pdf.get_y(), item_disc_col_widths[2], num_lines * 7, 'F')

                        pdf.set_draw_color(*BORDER_COLOR)
                        pdf.rect(pdf.get_x(), pdf.get_y(), item_disc_col_widths[2], num_lines * 7, 'D')

                        pdf.set_xy(start_x + item_disc_col_widths[0] + item_disc_col_widths[1], start_y)
                        pdf.multi_cell(item_disc_col_widths[2], 7, disc['description'], 0, 'L', fill=False)

                        pdf.set_xy(15, start_y + (num_lines * 7))

                        row_counter += 1
                else:
                    pdf.cell(0, 10, '  No discrepancies recorded for this item in the period.', 0, 1)
                pdf.ln(10)

        pdf.output(full_output_path)
        logger.info(f"Report generated: {full_output_path}")


# Helper function for day suffix (st, nd, rd, th)
def get_day_suffix(day):
    if 10 <= day % 100 <= 20:
        return 'th'
    else:
        return {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')


if __name__ == '__main__':
    # Ensure the base output folder exists
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        logger.info(f"Created base output directory: {OUTPUT_FOLDER}")

    # Generate the subfolder name based on current date and time
    current_datetime_for_folder = datetime.now()
    month_abbr = current_datetime_for_folder.strftime('%b')
    day_with_suffix = f"{current_datetime_for_folder.day}{get_day_suffix(current_datetime_for_folder.day)}"
    year = current_datetime_for_folder.year
    # Format hour to remove leading zero if any, and convert AM/PM to lowercase
    hour = current_datetime_for_folder.strftime('%I').lstrip('0') 
    ampm = current_datetime_for_folder.strftime('%p').lower()

    subfolder_name = f"{month_abbr} {day_with_suffix} {year} - Reports - {hour}{ampm}"
    reports_output_base_path = os.path.join(OUTPUT_FOLDER, subfolder_name)

    # Ensure the new subfolder exists
    if not os.path.exists(reports_output_base_path):
        os.makedirs(reports_output_base_path)
        logger.info(f"Created daily report directory: {reports_output_base_path}")

    # Initialize the data processor with the MySQL DB_CONFIG
    data_processor = DatabaseDataProcessor(DB_CONFIG)
    
    # In a real business scenario, data would be populated by the application
    # connecting to the database, not by this report generator.
    # The 'is_database_empty' check now serves to gracefully handle cases
    # where no data has been generated yet by the customer's application.

    # Instantiate the report generator
    report_generator = ReportGenerator(data_processor)

    logger.info("Attempting to generate inventory reports...")

    # Example report generation calls, now saving into the new subfolder:

    # 1. Full report for all data (last 30 days by default if no dates specified)
    report_generator.generate_full_report(
        output_filename="full_inventory_report.pdf",
        output_base_dir=reports_output_base_path
    )

    # 2. Report for a specific item type (e.g., "Laptop")
    report_generator.generate_full_report(
        item_type="Laptop",
        output_filename="laptop_report.pdf",
        output_base_dir=reports_output_base_path
    )

    # 3. Report for a specific date range (e.g., last 90 days)
    today = datetime.now()
    ninety_days_ago = today - timedelta(days=90)
    report_generator.generate_full_report(
        start_date=ninety_days_ago.strftime("%Y-%m-%d"),
        end_date=today.strftime("%Y-%m-%d"),
        output_filename="last_90_days_report.pdf",
        output_base_dir=reports_output_base_path
    )

    # 4. Report for another specific item type and a custom short range
    two_weeks_ago = today - timedelta(days=14)
    report_generator.generate_full_report(
        start_date=two_weeks_ago.strftime("%Y-%m-%d"),
        end_date=today.strftime("%Y-%m-%d"),
        item_type="Monitor",
        output_filename="monitor_last_2weeks_report.pdf",
        output_base_dir=reports_output_base_path
    )

    logger.info(f"\nReport generation attempts complete. Check the PDF files in the '{reports_output_base_path}' folder and the log file.")
