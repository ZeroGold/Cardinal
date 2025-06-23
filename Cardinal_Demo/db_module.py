# db_module.py
import mysql.connector
from mysql.connector import Error
import logging # Use logging instead of print
from config import DB_CONFIG # Import database connection details

# Configure logging for the database module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class InventoryDB:
    def __init__(self):
        self.connection = None
        self.connect()

    def connect(self):
        """Establishes connection to MySQL database."""
        if self.connection and self.connection.is_connected():
            return
        
        try:
            # self.connection = mysql.connector.connect(**DB_CONFIG) 
            self.connection = mysql.connector.connect(
                autocommit=True,          # ← every statement is its own transaction
                **DB_CONFIG
            )
            if self.connection.is_connected():
                logging.info(f"Successfully connected to MySQL database: {DB_CONFIG['database']}")
            else:
                logging.error("Failed to connect to MySQL database.")
        except Error as e:
            logging.error(f"Error connecting to MySQL database: {e}")
            self.connection = None # Ensure connection is None on failure

    def close(self):
        """Closes the database connection."""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            logging.info("MySQL connection closed.")

    def initialize_schema(self):
        """Creates necessary tables if they don't exist."""
        if not self.connection or not self.connection.is_connected():
            logging.error("Cannot initialize schema: No database connection.")
            return

        cursor = self.connection.cursor()
        try:
            # Table for current inventory state
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventory_current_state (
                    item_type VARCHAR(255) NOT NULL,
                    location_id VARCHAR(255) NOT NULL,
                    count INT NOT NULL DEFAULT 0,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (item_type, location_id)
                )
            """)
            logging.info("Table 'inventory_current_state' ensured to exist.")

            # Table for detailed transaction log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transaction_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    item_type VARCHAR(255) NOT NULL,
                    event_type ENUM('IN', 'OUT', 'DISCREPANCY', 'SCALE_UPDATE', 'MANUAL_ADJUSTMENT') NOT NULL,
                    quantity_change INT NOT NULL,
                    object_id VARCHAR(255), -- Unique ID for tracked objects
                    confidence REAL,
                    location_id VARCHAR(255) NOT NULL,
                    associated_sensor_data_id VARCHAR(255), -- For linking to scale data, etc.
                    description TEXT
                )
            """)
            logging.info("Table 'transaction_log' ensured to exist.")
            self.connection.commit()
        except Error as e:
            logging.error(f"Error initializing database schema: {e}")
            self.connection.rollback() # Rollback in case of error
        finally:
            cursor.close()

    def get_all_inventory_counts(self, location_id):
        """Retrieves current inventory counts for a specific location."""
        if not self.connection or not self.connection.is_connected():
            logging.error("Cannot get inventory: No database connection.")
            return {}
        
        counts = {}
        cursor = self.connection.cursor(dictionary=True) # Return rows as dictionaries
        try:
            cursor.execute("SELECT item_type, count FROM inventory_current_state WHERE location_id = %s", (location_id,))
            for row in cursor:
                counts[row['item_type']] = row['count']
            logging.info(f"Retrieved inventory for {location_id}: {counts}")
        except Error as e:
            logging.error(f"Error retrieving inventory counts for {location_id}: {e}")
        finally:
            cursor.close()
        return counts

    def update_inventory_count(self, item_type, change, location_id, absolute_set=False):
        """Updates an item's count in inventory_current_state. Can add/subtract or set absolutely."""
        if not self.connection or not self.connection.is_connected():
            logging.error("Cannot update inventory: No database connection.")
            return False

        cursor = self.connection.cursor()
        try:
            if absolute_set:
                query = """
                    INSERT INTO inventory_current_state (item_type, location_id, count)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE count = %s
                """
                params = (item_type, location_id, change, change)
            else:
                query = """
                    INSERT INTO inventory_current_state (item_type, location_id, count)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE count = count + %s
                """
                params = (item_type, location_id, change, change)
            
            cursor.execute(query, params)
            self.connection.commit()
            logging.debug(f"Updated inventory: {item_type} by {change} in {location_id}")
            return True
        except Error as e:
            logging.error(f"Error updating inventory count for {item_type} in {location_id}: {e}")
            self.connection.rollback()
            return False
        finally:
            cursor.close()

    def log_transaction(self, item_type, event_type, quantity_change, object_id, confidence, location_id, associated_sensor_data_id=None, description=None):
        """Logs a transaction event to the transaction_log table."""
        if not self.connection or not self.connection.is_connected():
            logging.error("Cannot log transaction: No database connection.")
            return False

        cursor = self.connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO transaction_log (item_type, event_type, quantity_change, object_id, confidence, location_id, associated_sensor_data_id, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (item_type, event_type, quantity_change, object_id, confidence, location_id, associated_sensor_data_id, description))
            self.connection.commit()
            logging.debug(f"Logged transaction: {event_type} {quantity_change}x {item_type} (ID: {object_id}) at {location_id}")
            return True
        except Error as e:
            logging.error(f"Error logging transaction for {item_type} at {location_id}: {e}")
            self.connection.rollback()
            return False
        finally:
            cursor.close()

    # ------------------------------------------------------------------ #
    #  NEW: pull recent change-log rows, needed for live GUI updates
    # ------------------------------------------------------------------ #
    def get_change_log(self, location_id, limit=1_000):
        """
        Returns the most-recent `limit` rows for one location.
        Order: newest → oldest.
        """
        if not self.connection or not self.connection.is_connected():
            logging.error("Cannot fetch change log: No database connection.")
            return []

        sql = """
            SELECT timestamp,
                   item_type,
                   event_type,
                   quantity_change,
                   object_id,
                   confidence
              FROM transaction_log
             WHERE location_id = %s
          ORDER BY timestamp DESC
             LIMIT %s
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, (location_id, limit))
            rows = cursor.fetchall()
            return rows
        except Error as e:
            logging.error(f"Error reading change-log for {location_id}: {e}")
            return []
        finally:
            cursor.close()
