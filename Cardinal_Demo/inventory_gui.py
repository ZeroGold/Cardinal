"""
inventory_gui.py
Simple two-tab live-view GUI for the Cardinal inventory system.

• Tab 1  = initial DB snapshot (read-only)
• Tab 2  = live counts (top) + change-log (bottom), refreshed on a QTimer
---------------------------------------------------------------------------
Dependencies
  pip install PySide6 pandas
This file expects the existing `db_module.InventoryDB` class and the
LOCATION_ID constant from config.py (both already in your code-base).
"""
import sys
import pandas as pd

from PySide6.QtCore    import Qt, QAbstractTableModel, QModelIndex, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QTableView,
    QSplitter, QWidget, QVBoxLayout, QMessageBox
)

from db_module import InventoryDB      # already used by main.py :contentReference[oaicite:0]{index=0}
from config    import LOCATION_ID       # global site / camera identifier :contentReference[oaicite:1]{index=1}


# ---------------------------------------------------------------------------#
# 1. Minimal Qt model that wraps a pandas DataFrame
# ---------------------------------------------------------------------------#
class DataFrameTableModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame = pd.DataFrame(), parent=None):
        super().__init__(parent)
        self._df = df.copy()

    # --- Qt required overrides ---------------------------------------------
    def rowCount(self, parent=QModelIndex())    -> int: return len(self._df.index)
    def columnCount(self, parent=QModelIndex()) -> int: return len(self._df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        value = self._df.iat[index.row(), index.column()]
        return str(value)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        return str(self._df.index[section])

    # --- public helper for live updates ------------------------------------
    def update_from_dataframe(self, new_df: pd.DataFrame):
        self.beginResetModel()
        self._df = new_df.copy()
        self.endResetModel()


# ---------------------------------------------------------------------------#
# 2. Main window
# ---------------------------------------------------------------------------#
class InventoryWindow(QMainWindow):
    REFRESH_MS = 1_000     # 1 s poll-interval for live view

    def __init__(self, db: InventoryDB, location: str):
        super().__init__()
        self.setWindowTitle("Cardinal Inventory – Live View")
        self.db        = db
        self.location  = location

        # ---------- Tab 1  Initial snapshot ---------------------------------
        init_df         = self._dict_to_df(self.db.get_all_inventory_counts(location))
        self.init_model = DataFrameTableModel(init_df)
        init_table      = QTableView()
        init_table.setModel(self.init_model)
        init_table.setAlternatingRowColors(True)
        init_table.horizontalHeader().setStretchLastSection(True)
        init_table.setEditTriggers(QTableView.NoEditTriggers)

        # ---------- Tab 2  Live counts + log --------------------------------
        # top — live counts
        live_df           = self._dict_to_df(self.db.get_all_inventory_counts(location))
        self.live_model   = DataFrameTableModel(live_df)
        live_table        = QTableView()
        live_table.setModel(self.live_model)
        live_table.setAlternatingRowColors(True)
        live_table.horizontalHeader().setStretchLastSection(True)
        live_table.setEditTriggers(QTableView.NoEditTriggers)

        # bottom — change-log (latest first)
        log_df            = self._get_log_df()
        self.log_model    = DataFrameTableModel(log_df)
        log_table         = QTableView()
        log_table.setModel(self.log_model)
        log_table.setAlternatingRowColors(True)
        log_table.horizontalHeader().setStretchLastSection(True)
        log_table.setEditTriggers(QTableView.NoEditTriggers)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(live_table)
        splitter.addWidget(log_table)
        splitter.setSizes([400, 250])   # give live counts more space

        # ---------- Compose tabs --------------------------------------------
        tabs = QTabWidget()
        tabs.addTab(init_table, "Initial State")
        tabs.addTab(splitter, "Live View")

        central = QWidget()
        lay     = QVBoxLayout(central)
        lay.addWidget(tabs)
        self.setCentralWidget(central)

        # ---------- Live refresh timer --------------------------------------
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_live_tab)
        self._timer.start(self.REFRESH_MS)

    # ---------------- internal helpers -------------------------------------
    @staticmethod
    def _dict_to_df(d: dict) -> pd.DataFrame:
        """Convert {'item': count, ...} → DataFrame(Item, Count)."""
        return pd.DataFrame(
            [{"Item": k, "Count": v} for k, v in sorted(d.items())],
            columns=["Item", "Count"]
        )

    def _get_log_df(self, limit: int = 1_000) -> pd.DataFrame:
        """
        Pull most-recent change-log rows from DB.
        Falls back to an empty DF if the db_layer doesn’t expose `get_change_log`.
        Expected columns: timestamp, item, action, delta, source_id, confidence
        """
        rows = self.db.get_change_log(self.location, limit)
        return pd.DataFrame(rows, columns=[
            "Timestamp",   # 0
            "Item",        # 1
            "Action",      # 2  ('IN'/'OUT'/…)
            "Δ",           # 3  quantity_change
            "SourceID",    # 4  object_id
            "Conf."        # 5  confidence
        ])

    def _refresh_live_tab(self):
        """Slot: periodic poll → refresh live counts + log."""
        # live counts --------------------------------------------------------
        live_counts = self.db.get_all_inventory_counts(self.location)
        self.live_model.update_from_dataframe(self._dict_to_df(live_counts))

        # change-log ---------------------------------------------------------
        log_df = self._get_log_df()
        self.log_model.update_from_dataframe(log_df)


# ---------------------------------------------------------------------------#
# 3.  Entry-point
# ---------------------------------------------------------------------------#
def main() -> None:
    try:
        db = InventoryDB()
    except Exception as exc:
        QMessageBox.critical(None, "Database error", f"Failed to connect to DB:\n{exc}")
        raise SystemExit(1)

    app = QApplication(sys.argv)
    win = InventoryWindow(db, LOCATION_ID)
    win.resize(900, 650)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
