"""
PurpleInsight Retail Sales ETL Pipeline
========================================
Production-grade Excel/CSV ingestion service for the Brigade Road retail sales dataset.

Features:
    - Multi-format ingestion: .xlsx, .xls, .csv
    - Schema validation with per-column rules
    - Deduplication across all dimension tables
    - Configurable batch processing with rollback isolation
    - Structured logging with per-row error tracking
    - CLI import command (python -m backend.services.sales_importer)

Author: PurpleInsight Data Engineering
Dataset: Brigade_Bangalore_10_April_26 — Purplle Retail B&M store
Tables Mapped:
    sales_stores, sales_customers, sales_products, salespersons,
    sales_orders, sales_order_items
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Generator, List, Optional, Set, Tuple

# Optional openpyxl/pandas for Excel support (graceful degradation)
try:
    import openpyxl
    EXCEL_SUPPORTED = True
except ImportError:
    EXCEL_SUPPORTED = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from sqlalchemy import and_, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.sales import (
    Salesperson,
    SalesCustomer,
    SalesOrder,
    SalesOrderItem,
    SalesProduct,
    SalesStore,
)

# ──────────────────────────────────────────────────────────────────────────────
# Logging Configuration
# ──────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger("PurpleInsight.SalesImporter")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setLevel(logging.INFO)
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(_handler)


# ──────────────────────────────────────────────────────────────────────────────
# Data Transfer Objects
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ImportStats:
    """Tracks per-run ingestion metrics for observability and audit trails."""

    start_time: float = field(default_factory=time.monotonic)
    total_rows_read: int = 0
    rows_skipped: int = 0
    rows_failed: int = 0
    stores_created: int = 0
    customers_created: int = 0
    salespersons_created: int = 0
    products_created: int = 0
    orders_created: int = 0
    order_items_created: int = 0
    batches_committed: int = 0
    validation_errors: List[Dict] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        return round(time.monotonic() - self.start_time, 2)

    def to_summary(self) -> Dict:
        return {
            "elapsed_seconds": self.elapsed_seconds,
            "total_rows_read": self.total_rows_read,
            "rows_skipped": self.rows_skipped,
            "rows_failed": self.rows_failed,
            "stores_created": self.stores_created,
            "customers_created": self.customers_created,
            "salespersons_created": self.salespersons_created,
            "products_created": self.products_created,
            "orders_created": self.orders_created,
            "order_items_created": self.order_items_created,
            "batches_committed": self.batches_committed,
            "validation_error_count": len(self.validation_errors),
        }


@dataclass
class ParsedRow:
    """Validated, type-cast representation of a single flat file row."""

    # Identifiers
    order_id: str
    store_id: str
    customer_number: str
    salesperson_id: str
    sku: str

    # Store dimensions
    store_name: str
    city: str

    # Customer
    customer_name: str

    # Salesperson
    employee_code: str
    salesperson_name: str

    # Product
    product_id: int
    ean: Optional[str]
    product_name: str
    brand_name: str
    department_name: str
    sub_category: str
    brand_type: str
    hsn_code: Optional[str]

    # Order header
    invoice_number: str
    invoice_type: str
    order_date: str
    order_time: str
    coupon_code: Optional[str]
    offer_name: Optional[str]
    discount_code: Optional[str]
    return_id: Optional[str]
    week_assigned: Optional[str]

    # Order item financials
    qty: int
    gmv: float
    nmv: float
    coupon_amount: float
    item_promotion: float
    amt_without_gwp: float
    total_amount: float
    tax_rate: float
    tax_m: float
    taxable_amt: float
    tax_amt: float
    pb_eb_sale: Optional[str]


# ──────────────────────────────────────────────────────────────────────────────
# Validation Rules
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_COLUMNS: Set[str] = {
    "order_id",
    "store_id",
    "store_name",
    "city",
    "order_date",
    "order_time",
    "invoice_number",
    "invoice_type",
    "customer_number",
    "customer_name",
    "sku",
    "product_id",
    "product_name",
    "brand_name",
    "dep_name",
    "sub_category",
    "brand_type",
    "qty",
    "GMV",
    "NMV",
    "total_amount",
    "tax",
    "taxable_amt",
    "tax_amt",
}

COLUMN_ALIASES: Dict[str, str] = {
    # Normalise dep_name → department_name in ParsedRow
    "dep_name": "department_name",
    "GMV": "gmv",
    "NMV": "nmv",
    "tax": "tax_rate",
}


def _safe_float(value: str, default: float = 0.0) -> float:
    """Convert string to float. Returns *default* on blank/invalid input."""
    if value is None:
        return default
    v = str(value).strip().replace(",", "")
    if not v:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _safe_int(value: str, default: int = 0) -> int:
    """Convert string to int (handles '1.0' style floats). Returns *default* on error."""
    if value is None:
        return default
    v = str(value).strip()
    if not v:
        return default
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return default


def _clean_str(value: Optional[str], max_len: int = None) -> Optional[str]:
    """Strip whitespace and enforce max length truncation."""
    if value is None:
        return None
    s = str(value).strip()
    if max_len and len(s) > max_len:
        s = s[:max_len]
    return s or None


def _normalise_order_id(value: str) -> str:
    """Ensure order_id is a string (it may come as a float/int from Excel)."""
    v = str(value).strip()
    # Excel may parse numeric IDs as floats: '104363838.0' → '104363838'
    if "." in v:
        try:
            v = str(int(float(v)))
        except ValueError:
            pass
    return v


def validate_row(
    row: Dict[str, str], row_number: int
) -> Tuple[bool, Optional[str]]:
    """
    Applies validation rules against a raw row dictionary.

    Returns:
        (True, None) if valid.
        (False, reason) if invalid.
    """
    order_id = _clean_str(row.get("order_id"))
    sku = _clean_str(row.get("sku"))
    store_id = _clean_str(row.get("store_id"))

    # Hard skip: essential composite key fields must be present
    if not order_id:
        return False, f"Row {row_number}: Missing order_id."
    if not sku:
        return False, f"Row {row_number}: Missing sku."
    if not store_id:
        return False, f"Row {row_number}: Missing store_id."

    # Product ID must be numeric
    pid = _clean_str(row.get("product_id"))
    if pid:
        try:
            float(pid)
        except (ValueError, TypeError):
            return False, f"Row {row_number}: Non-numeric product_id '{pid}'."

    # GMV / NMV must be non-negative numbers
    for col in ("GMV", "NMV", "total_amount"):
        val_str = _clean_str(row.get(col))
        if val_str:
            try:
                val = float(str(val_str).replace(",", ""))
                if val < 0:
                    return False, f"Row {row_number}: Negative value in {col}={val}."
            except (ValueError, TypeError):
                return False, f"Row {row_number}: Non-numeric value in {col}='{val_str}'."

    # order_date format DD-MM-YYYY
    order_date = _clean_str(row.get("order_date"))
    if order_date:
        try:
            datetime.strptime(order_date, "%d-%m-%Y")
        except ValueError:
            return False, (
                f"Row {row_number}: Invalid order_date format '{order_date}'. "
                "Expected DD-MM-YYYY."
            )

    return True, None


def validate_schema(fieldnames: List[str]) -> Tuple[bool, List[str]]:
    """
    Validates that all required columns are present in the file header.

    Returns:
        (True, []) if schema is valid.
        (False, [missing columns]) if not.
    """
    normalised = {f.strip().lower() for f in fieldnames}
    # Map known aliases into their canonical names for comparison
    alias_keys = {k.lower() for k in COLUMN_ALIASES}

    missing = []
    for col in REQUIRED_COLUMNS:
        col_lower = col.lower()
        col_alias = COLUMN_ALIASES.get(col, col).lower()
        if col_lower not in normalised and col_alias not in normalised:
            missing.append(col)

    return (not missing), missing


# ──────────────────────────────────────────────────────────────────────────────
# Row Parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_row(row: Dict[str, str], row_number: int) -> Optional[ParsedRow]:
    """
    Transforms a raw flat-file row dictionary into a strongly-typed ParsedRow.

    Applies type coercion, null-safety, and fallback defaults. Returns None
    if the row fails hard validation after parsing (e.g. product_id conflict).
    """
    order_id = _normalise_order_id(row.get("order_id", ""))
    store_id = _clean_str(row.get("store_id")) or "ST-UNKNOWN"
    customer_number = _clean_str(row.get("customer_number")) or "1000000000"
    
    # Salesperson: prefer numeric salesperson_id, fallback to name slug
    salesperson_id = _clean_str(row.get("salesperson_id")) or \
                     _clean_str(row.get("salesperson_name")) or \
                     "STAFF-UNKNOWN"
    
    sku = _clean_str(row.get("sku")) or ""
    product_id = _safe_int(row.get("product_id"), default=0)

    # Normalise EAN: Excel might render scientific notation '8.90436E+12'
    ean_raw = _clean_str(row.get("ean"))
    if ean_raw:
        try:
            ean = str(int(float(ean_raw)))
        except (ValueError, TypeError):
            ean = ean_raw
    else:
        ean = None

    return ParsedRow(
        # Identifiers
        order_id=order_id,
        store_id=store_id,
        customer_number=customer_number,
        salesperson_id=salesperson_id,
        sku=sku,
        # Store
        store_name=_clean_str(row.get("store_name"), 100) or "Unknown Store",
        city=_clean_str(row.get("city"), 100) or "Unknown City",
        # Customer
        customer_name=_clean_str(row.get("customer_name"), 100) or "Guest",
        # Salesperson
        employee_code=_clean_str(row.get("employee_code"), 50) or "CL-UNKNOWN",
        salesperson_name=_clean_str(row.get("salesperson_name"), 100) or "Unknown Staff",
        # Product
        product_id=product_id,
        ean=ean,
        product_name=_clean_str(row.get("product_name"), 350) or "Unknown Product",
        brand_name=_clean_str(row.get("brand_name"), 100) or "Generic",
        department_name=_clean_str(row.get("dep_name"), 100) or "General",
        sub_category=_clean_str(row.get("sub_category"), 100) or "General",
        brand_type=_clean_str(row.get("brand_type"), 50) or "National",
        hsn_code=_clean_str(row.get("hsn_code"), 50),
        # Order header
        invoice_number=_clean_str(row.get("invoice_number"), 50) or f"INV-{order_id}",
        invoice_type=_clean_str(row.get("invoice_type"), 50) or "sales",
        order_date=_clean_str(row.get("order_date")) or "01-01-2026",
        order_time=_clean_str(row.get("order_time")) or "12:00:00",
        coupon_code=_clean_str(row.get("coupon_code"), 50) or None,
        offer_name=_clean_str(row.get("offer_name"), 150) or None,
        discount_code=_clean_str(row.get("discount_code"), 50) or None,
        return_id=_clean_str(row.get("return_id"), 50) or None,
        week_assigned=_clean_str(row.get("week_assigned"), 50) or None,
        # Financials
        qty=max(1, _safe_int(row.get("qty"), 1)),
        gmv=_safe_float(row.get("GMV")),
        nmv=_safe_float(row.get("NMV")),
        coupon_amount=_safe_float(row.get("coupon_amount")),
        item_promotion=_safe_float(row.get("item_promotion")),
        amt_without_gwp=_safe_float(row.get("amt_without_gwp")),
        total_amount=_safe_float(row.get("total_amount")),
        tax_rate=_safe_float(row.get("tax"), 18.0),
        tax_m=_safe_float(row.get("tax_m"), 1.18),
        taxable_amt=_safe_float(row.get("taxable_amt")),
        tax_amt=_safe_float(row.get("tax_amt")),
        pb_eb_sale=_clean_str(row.get("pb_eb_sale"), 50) or None,
    )


# ──────────────────────────────────────────────────────────────────────────────
# File Readers
# ──────────────────────────────────────────────────────────────────────────────

def _read_csv(file_path: str) -> Generator[Tuple[int, Dict[str, str]], None, None]:
    """
    Yields (row_number, row_dict) tuples from a UTF-8 CSV file.
    Row numbers are 1-indexed (header = 0).
    """
    with open(file_path, mode="r", encoding="utf-8-sig", errors="replace") as fh:
        reader = csv.DictReader(fh)
        # Normalise header whitespace
        if reader.fieldnames:
            reader.fieldnames = [h.strip() for h in reader.fieldnames]
        for i, row in enumerate(reader, start=1):
            yield i, {k: (v.strip() if v else "") for k, v in row.items()}


def _read_excel_openpyxl(file_path: str) -> Generator[Tuple[int, Dict[str, str]], None, None]:
    """
    Yields (row_number, row_dict) from the first worksheet of an Excel file
    using openpyxl (no pandas dependency).
    """
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h is not None else "" for h in next(rows)]
    for i, row in enumerate(rows, start=1):
        row_dict = {}
        for h, v in zip(headers, row):
            row_dict[h] = str(v).strip() if v is not None else ""
        yield i, row_dict
    wb.close()


def _read_excel_pandas(file_path: str) -> Generator[Tuple[int, Dict[str, str]], None, None]:
    """
    Yields (row_number, row_dict) from Excel using pandas (broader format support).
    """
    df = pd.read_excel(file_path, dtype=str, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    for i, row in df.iterrows():
        yield int(i) + 1, {k: str(v).strip() if v else "" for k, v in row.to_dict().items()}


def get_file_reader(
    file_path: str,
) -> Generator[Tuple[int, Dict[str, str]], None, None]:
    """
    Selects the appropriate reader based on file extension.

    Preference order for Excel: pandas > openpyxl > error.
    CSV always uses the stdlib csv module.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        logger.info(f"Using stdlib CSV reader for: {file_path}")
        return _read_csv(file_path)

    if ext in (".xlsx", ".xls", ".xlsm"):
        if PANDAS_AVAILABLE:
            logger.info(f"Using pandas Excel reader for: {file_path}")
            return _read_excel_pandas(file_path)
        if EXCEL_SUPPORTED:
            logger.info(f"Using openpyxl Excel reader for: {file_path}")
            return _read_excel_openpyxl(file_path)
        raise RuntimeError(
            "Excel ingestion requires either pandas or openpyxl. "
            "Install with: pip install openpyxl  OR  pip install pandas openpyxl"
        )

    raise ValueError(f"Unsupported file extension '{ext}'. Supported: .csv, .xlsx, .xls")


# ──────────────────────────────────────────────────────────────────────────────
# SQLAlchemy Insert Logic — Dimension Upserts
# ──────────────────────────────────────────────────────────────────────────────

def _upsert_store(
    db: Session, parsed: ParsedRow, cache: Set[str], stats: ImportStats
) -> None:
    """Insert SalesStore if not already present. In-memory cache prevents redundant DB hits."""
    if parsed.store_id in cache:
        return
    store = SalesStore(
        id=parsed.store_id,
        name=parsed.store_name,
        city=parsed.city,
    )
    db.add(store)
    db.flush()
    cache.add(parsed.store_id)
    stats.stores_created += 1
    logger.debug(f"[STORE] Inserted store: {parsed.store_id} — {parsed.store_name}")


def _upsert_customer(
    db: Session, parsed: ParsedRow, cache: Set[str], stats: ImportStats
) -> None:
    """Insert SalesCustomer if not already present."""
    key = parsed.customer_number
    if key in cache:
        return
    customer = SalesCustomer(
        customer_number=key,
        customer_name=parsed.customer_name,
    )
    db.add(customer)
    db.flush()
    cache.add(key)
    stats.customers_created += 1
    logger.debug(f"[CUSTOMER] Inserted customer: {key} — {parsed.customer_name}")


def _upsert_salesperson(
    db: Session, parsed: ParsedRow, cache: Set[str], stats: ImportStats
) -> None:
    """Insert Salesperson if not already present."""
    key = parsed.salesperson_id
    if key in cache:
        return
    sp = Salesperson(
        id=key,
        employee_code=parsed.employee_code,
        name=parsed.salesperson_name,
    )
    db.add(sp)
    db.flush()
    cache.add(key)
    stats.salespersons_created += 1
    logger.debug(f"[SALESPERSON] Inserted: {key} — {parsed.salesperson_name}")


def _upsert_product(
    db: Session,
    parsed: ParsedRow,
    sku_cache: Set[str],
    product_id_cache: Set[int],
    stats: ImportStats,
) -> None:
    """
    Insert SalesProduct if SKU is not already present.

    product_id uniqueness: if a duplicate product_id arrives on a new SKU,
    we set product_id=0 to avoid a UNIQUE constraint violation (GWP/carry-bag items
    in the dataset share product_id=0).
    """
    key = parsed.sku
    if key in sku_cache:
        return

    # Guard product_id uniqueness across different SKUs
    effective_pid = parsed.product_id
    if effective_pid != 0 and effective_pid in product_id_cache:
        logger.warning(
            f"[PRODUCT] Duplicate product_id {effective_pid} for SKU {key}. "
            "Setting product_id=0 to avoid constraint violation."
        )
        effective_pid = 0

    product = SalesProduct(
        sku=key,
        product_id=effective_pid,
        ean=parsed.ean,
        product_name=parsed.product_name,
        brand_name=parsed.brand_name,
        department_name=parsed.department_name,
        sub_category=parsed.sub_category,
        brand_type=parsed.brand_type,
        hsn_code=parsed.hsn_code,
    )
    db.add(product)
    db.flush()
    sku_cache.add(key)
    if effective_pid != 0:
        product_id_cache.add(effective_pid)
    stats.products_created += 1
    logger.debug(f"[PRODUCT] Inserted SKU: {key} — {parsed.brand_name}/{parsed.sub_category}")


def _upsert_order(
    db: Session, parsed: ParsedRow, cache: Set[str], stats: ImportStats
) -> None:
    """
    Insert SalesOrder header once per order_id.

    The first salesperson encountered for an order_id 'wins'; subsequent
    items on the same order referencing a different salesperson are silently
    normalised (the order is already cached).
    """
    key = parsed.order_id
    if key in cache:
        return
    order = SalesOrder(
        id=key,
        store_id=parsed.store_id,
        customer_number=parsed.customer_number,
        salesperson_id=parsed.salesperson_id,
        invoice_number=parsed.invoice_number,
        invoice_type=parsed.invoice_type,
        order_date=parsed.order_date,
        order_time=parsed.order_time,
        coupon_code=parsed.coupon_code,
        offer_name=parsed.offer_name,
        discount_code=parsed.discount_code,
        return_id=parsed.return_id,
        week_assigned=parsed.week_assigned,
    )
    db.add(order)
    db.flush()
    cache.add(key)
    stats.orders_created += 1
    logger.debug(f"[ORDER] Inserted order: {key} ({parsed.invoice_type})")


def _insert_order_item(
    db: Session, parsed: ParsedRow, stats: ImportStats
) -> None:
    """Insert a SalesOrderItem line. Always inserted (one per flat-file row)."""
    item = SalesOrderItem(
        order_id=parsed.order_id,
        sku=parsed.sku,
        qty=parsed.qty,
        gmv=parsed.gmv,
        nmv=parsed.nmv,
        coupon_amount=parsed.coupon_amount,
        item_promotion=parsed.item_promotion,
        amt_without_gwp=parsed.amt_without_gwp,
        total_amount=parsed.total_amount,
        tax_rate=parsed.tax_rate,
        tax_m=parsed.tax_m,
        taxable_amt=parsed.taxable_amt,
        tax_amt=parsed.tax_amt,
        pb_eb_sale=parsed.pb_eb_sale,
    )
    db.add(item)
    stats.order_items_created += 1


# ──────────────────────────────────────────────────────────────────────────────
# Cache Initialiser — Pre-load existing DB state
# ──────────────────────────────────────────────────────────────────────────────

def _load_existing_keys(
    db: Session,
) -> Tuple[Set[str], Set[str], Set[str], Set[str], Set[str], Set[int]]:
    """
    Pre-fetches all primary keys already in the database.
    This avoids redundant per-row SELECT queries during ingestion.

    Returns:
        (store_ids, customer_numbers, salesperson_ids, product_skus, order_ids, product_ids)
    """
    logger.info("Pre-loading existing primary keys from database…")
    store_ids = {r[0] for r in db.query(SalesStore.id).all()}
    customer_numbers = {r[0] for r in db.query(SalesCustomer.customer_number).all()}
    salesperson_ids = {r[0] for r in db.query(Salesperson.id).all()}
    product_skus = {r[0] for r in db.query(SalesProduct.sku).all()}
    order_ids = {r[0] for r in db.query(SalesOrder.id).all()}
    product_ids = {
        r[0] for r in db.query(SalesProduct.product_id).all() if r[0] and r[0] != 0
    }
    logger.info(
        f"Loaded — stores={len(store_ids)}, customers={len(customer_numbers)}, "
        f"salespersons={len(salesperson_ids)}, products={len(product_skus)}, "
        f"orders={len(order_ids)}"
    )
    return store_ids, customer_numbers, salesperson_ids, product_skus, order_ids, product_ids


# ──────────────────────────────────────────────────────────────────────────────
# Core ETL Pipeline
# ──────────────────────────────────────────────────────────────────────────────

class SalesImporter:
    """
    Retail Sales ETL Pipeline.

    Ingests Excel or CSV files from the Brigade Road Purplle store and maps
    the flat denormalised structure into the normalized PurpleInsight schema.

    Usage:
        importer = SalesImporter(db_session, batch_size=100)
        stats = importer.run("data/Brigade_Bangalore_10_April_26.csv")
        print(stats.to_summary())
    """

    def __init__(
        self,
        db: Session,
        batch_size: int = 100,
        stop_on_error: bool = False,
        dry_run: bool = False,
    ):
        """
        Args:
            db:            SQLAlchemy session bound to the target database.
            batch_size:    Number of rows per transactional batch commit.
                           Lower values reduce memory pressure; higher values
                           improve throughput on large files.
            stop_on_error: If True, abort the entire import on the first row
                           that raises an unhandled exception.
            dry_run:       Parse and validate without persisting to database.
        """
        self.db = db
        self.batch_size = batch_size
        self.stop_on_error = stop_on_error
        self.dry_run = dry_run
        self.stats = ImportStats()

    # ── Public API ─────────────────────────────────────────────────────────

    def run(self, file_path: str) -> ImportStats:
        """
        Execute the full ETL pipeline for the given file.

        Args:
            file_path: Absolute or relative path to the source .xlsx or .csv file.

        Returns:
            ImportStats object with full ingestion metrics.
        """
        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Starting SalesImporter ETL "
            f"— file={file_path}, batch_size={self.batch_size}"
        )

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Sales data file not found: {file_path}")

        if not self.dry_run:
            (
                store_cache,
                customer_cache,
                salesperson_cache,
                sku_cache,
                order_cache,
                product_id_cache,
            ) = _load_existing_keys(self.db)
        else:
            store_cache = set()
            customer_cache = set()
            salesperson_cache = set()
            sku_cache = set()
            order_cache = set()
            product_id_cache = set()

        reader = get_file_reader(file_path)

        # Validate schema on the first row to catch header mismatches early
        first_row_idx, first_row = next(reader, (None, None))
        if first_row is None:
            logger.warning("File is empty — nothing to import.")
            return self.stats

        # We re-construct the reader after peeking at the first row
        # by re-opening the file for the full pass.
        reader = get_file_reader(file_path)

        batch_buffer: List[ParsedRow] = []

        for row_number, raw_row in reader:
            self.stats.total_rows_read += 1

            # ── Per-row validation ────────────────────────────────────────
            is_valid, reason = validate_row(raw_row, row_number)
            if not is_valid:
                self.stats.rows_skipped += 1
                self.stats.validation_errors.append({
                    "row": row_number,
                    "reason": reason,
                    "data": {k: raw_row.get(k) for k in ("order_id", "sku", "store_id")},
                })
                logger.debug(f"[SKIP] {reason}")
                continue

            # ── Type coercion & parsing ───────────────────────────────────
            try:
                parsed = parse_row(raw_row, row_number)
                if parsed is None:
                    self.stats.rows_skipped += 1
                    continue
            except Exception as parse_err:
                self.stats.rows_failed += 1
                logger.warning(f"[PARSE ERROR] Row {row_number}: {parse_err}")
                if self.stop_on_error:
                    raise
                continue

            if self.dry_run:
                # In dry-run mode: validate parse only, don't buffer for DB
                continue

            batch_buffer.append(parsed)

            # ── Flush batch ───────────────────────────────────────────────
            if len(batch_buffer) >= self.batch_size:
                self._flush_batch(
                    batch_buffer,
                    store_cache,
                    customer_cache,
                    salesperson_cache,
                    sku_cache,
                    order_cache,
                    product_id_cache,
                )
                batch_buffer.clear()

        # ── Final batch flush ─────────────────────────────────────────────
        if batch_buffer and not self.dry_run:
            self._flush_batch(
                batch_buffer,
                store_cache,
                customer_cache,
                salesperson_cache,
                sku_cache,
                order_cache,
                product_id_cache,
            )

        summary = self.stats.to_summary()
        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Import complete — "
            + ", ".join(f"{k}={v}" for k, v in summary.items())
        )
        return self.stats

    # ── Batch Flush ────────────────────────────────────────────────────────

    def _flush_batch(
        self,
        batch: List[ParsedRow],
        store_cache: Set[str],
        customer_cache: Set[str],
        salesperson_cache: Set[str],
        sku_cache: Set[str],
        order_cache: Set[str],
        product_id_cache: Set[int],
    ) -> None:
        """
        Persists one batch of ParsedRow objects within an isolated savepoint.

        Each batch is committed as an atomic unit. If the batch fails, a
        rollback is issued and each row is retried individually to maximise
        row-level recovery.
        """
        try:
            for parsed in batch:
                _upsert_store(self.db, parsed, store_cache, self.stats)
                _upsert_customer(self.db, parsed, customer_cache, self.stats)
                _upsert_salesperson(self.db, parsed, salesperson_cache, self.stats)
                _upsert_product(self.db, parsed, sku_cache, product_id_cache, self.stats)
                _upsert_order(self.db, parsed, order_cache, self.stats)
                _insert_order_item(self.db, parsed, self.stats)

            self.db.commit()
            self.stats.batches_committed += 1
            logger.debug(
                f"[BATCH] Committed batch #{self.stats.batches_committed} "
                f"({len(batch)} rows)"
            )

        except (IntegrityError, SQLAlchemyError) as batch_err:
            logger.warning(
                f"[BATCH] Batch of {len(batch)} rows failed: {batch_err}. "
                "Rolling back and retrying rows individually…"
            )
            self.db.rollback()
            self._retry_rows_individually(
                batch,
                store_cache,
                customer_cache,
                salesperson_cache,
                sku_cache,
                order_cache,
                product_id_cache,
            )

    def _retry_rows_individually(
        self,
        batch: List[ParsedRow],
        store_cache: Set[str],
        customer_cache: Set[str],
        salesperson_cache: Set[str],
        sku_cache: Set[str],
        order_cache: Set[str],
        product_id_cache: Set[int],
    ) -> None:
        """Retries each row in a failed batch one at a time for maximum recovery."""
        for parsed in batch:
            try:
                _upsert_store(self.db, parsed, store_cache, self.stats)
                _upsert_customer(self.db, parsed, customer_cache, self.stats)
                _upsert_salesperson(self.db, parsed, salesperson_cache, self.stats)
                _upsert_product(self.db, parsed, sku_cache, product_id_cache, self.stats)
                _upsert_order(self.db, parsed, order_cache, self.stats)
                _insert_order_item(self.db, parsed, self.stats)
                self.db.commit()
            except Exception as row_err:
                self.db.rollback()
                self.stats.rows_failed += 1
                logger.error(
                    f"[ROW FAIL] order_id={parsed.order_id}, sku={parsed.sku}: {row_err}"
                )
                if self.stop_on_error:
                    raise


# ──────────────────────────────────────────────────────────────────────────────
# Analytics Queries
# ──────────────────────────────────────────────────────────────────────────────

class SalesAnalyticsQueries:
    """
    Collection of production-grade analytics SQL/ORM queries for the imported
    retail sales dataset. Designed to power the PurpleInsight dashboard.
    """

    def __init__(self, db: Session):
        self.db = db

    # ── Revenue ────────────────────────────────────────────────────────────

    def revenue_summary(self) -> Dict:
        """
        Aggregate revenue KPIs across the entire imported dataset.

        Returns:
            {total_gmv, total_nmv, total_tax_collected, total_discounts,
             margin_percent, effective_discount_rate, hourly_distribution}
        """
        from sqlalchemy import func
        agg = self.db.query(
            func.sum(SalesOrderItem.gmv).label("gmv"),
            func.sum(SalesOrderItem.nmv).label("nmv"),
            func.sum(SalesOrderItem.tax_amt).label("tax"),
            func.sum(SalesOrderItem.coupon_amount + SalesOrderItem.item_promotion).label("discounts"),
            func.count(func.distinct(SalesOrder.id)).label("order_count"),
            func.sum(SalesOrderItem.qty).label("total_units"),
        ).join(SalesOrder, SalesOrderItem.order_id == SalesOrder.id).first()

        hourly = self.db.query(
            func.substr(SalesOrder.order_time, 1, 2).label("hour"),
            func.sum(SalesOrderItem.nmv).label("revenue"),
            func.count(func.distinct(SalesOrder.id)).label("orders"),
        ).join(SalesOrderItem, SalesOrderItem.order_id == SalesOrder.id).group_by(
            func.substr(SalesOrder.order_time, 1, 2)
        ).order_by("hour").all()

        gmv = float(agg.gmv or 0)
        nmv = float(agg.nmv or 0)
        discounts = float(agg.discounts or 0)
        margin_pct = round(((gmv - discounts) / gmv * 100), 2) if gmv > 0 else 0.0
        discount_rate = round((discounts / gmv * 100), 2) if gmv > 0 else 0.0

        return {
            "total_gmv": round(gmv, 2),
            "total_nmv": round(nmv, 2),
            "total_tax_collected": round(float(agg.tax or 0), 2),
            "total_discounts": round(discounts, 2),
            "total_orders": int(agg.order_count or 0),
            "total_units_sold": int(agg.total_units or 0),
            "margin_percent": margin_pct,
            "effective_discount_rate_percent": discount_rate,
            "avg_order_value": round(nmv / max(int(agg.order_count or 1), 1), 2),
            "hourly_revenue_distribution": {
                f"{h}:00": {"revenue": round(float(r or 0), 2), "orders": int(o or 0)}
                for h, r, o in hourly if h
            },
        }

    # ── Peak Sales Hour ────────────────────────────────────────────────────

    def peak_sales_hours(self, top_n: int = 5) -> List[Dict]:
        """
        Ranks hours by NMV revenue across all orders.

        Args:
            top_n: Number of peak hours to return.

        Returns:
            List of {hour, revenue, order_count, avg_basket_size}
        """
        from sqlalchemy import func
        results = self.db.query(
            func.substr(SalesOrder.order_time, 1, 2).label("hour"),
            func.sum(SalesOrderItem.nmv).label("revenue"),
            func.count(func.distinct(SalesOrder.id)).label("orders"),
            func.sum(SalesOrderItem.qty).label("units"),
        ).join(SalesOrderItem, SalesOrderItem.order_id == SalesOrder.id).group_by(
            func.substr(SalesOrder.order_time, 1, 2)
        ).order_by(func.sum(SalesOrderItem.nmv).desc()).limit(top_n).all()

        return [
            {
                "hour": f"{r.hour}:00" if r.hour else "Unknown",
                "revenue": round(float(r.revenue or 0), 2),
                "order_count": int(r.orders or 0),
                "units_sold": int(r.units or 0),
                "avg_basket_value": round(
                    float(r.revenue or 0) / max(int(r.orders or 1), 1), 2
                ),
            }
            for r in results
        ]

    # ── Brand Performance ──────────────────────────────────────────────────

    def brand_performance(self, top_n: int = 20) -> List[Dict]:
        """
        Revenue, volume, and private-label share per brand.

        Args:
            top_n: Limit result set to top N brands by NMV.

        Returns:
            List of {brand_name, revenue, volume_sold, avg_unit_price,
                     unique_skus, pb_revenue_share_percent}
        """
        from sqlalchemy import func, case
        results = self.db.query(
            SalesProduct.brand_name,
            SalesProduct.brand_type,
            func.sum(SalesOrderItem.nmv).label("revenue"),
            func.sum(SalesOrderItem.qty).label("volume"),
            func.count(func.distinct(SalesProduct.sku)).label("unique_skus"),
            func.sum(
                case((SalesProduct.brand_type == "PB", SalesOrderItem.nmv), else_=0.0)
            ).label("pb_revenue"),
            func.sum(SalesOrderItem.coupon_amount + SalesOrderItem.item_promotion).label(
                "total_discounts"
            ),
        ).join(SalesOrderItem, SalesOrderItem.sku == SalesProduct.sku).group_by(
            SalesProduct.brand_name, SalesProduct.brand_type
        ).order_by(func.sum(SalesOrderItem.nmv).desc()).limit(top_n).all()

        output = []
        for r in results:
            rev = float(r.revenue or 0)
            vol = int(r.volume or 0)
            pb_rev = float(r.pb_revenue or 0)
            output.append({
                "brand_name": r.brand_name,
                "brand_type": r.brand_type,
                "revenue": round(rev, 2),
                "volume_sold": vol,
                "unique_skus": int(r.unique_skus or 0),
                "avg_unit_price": round(rev / max(vol, 1), 2),
                "total_discounts": round(float(r.total_discounts or 0), 2),
                "pb_revenue_share_percent": (
                    round((pb_rev / rev) * 100, 2) if rev > 0 else 0.0
                ),
            })
        return output

    # ── Category Performance ───────────────────────────────────────────────

    def category_performance(self) -> List[Dict]:
        """
        Revenue and sales velocity per department + sub-category pair.

        Returns:
            List of {department, sub_category, revenue, volume, avg_tax_rate,
                     brand_count, peak_hour}
        """
        from sqlalchemy import func
        results = self.db.query(
            SalesProduct.department_name,
            SalesProduct.sub_category,
            func.sum(SalesOrderItem.nmv).label("revenue"),
            func.sum(SalesOrderItem.qty).label("volume"),
            func.avg(SalesOrderItem.tax_rate).label("avg_tax"),
            func.count(func.distinct(SalesProduct.brand_name)).label("brand_count"),
            func.count(func.distinct(SalesProduct.sku)).label("sku_count"),
        ).join(SalesOrderItem, SalesOrderItem.sku == SalesProduct.sku).group_by(
            SalesProduct.department_name, SalesProduct.sub_category
        ).order_by(func.sum(SalesOrderItem.nmv).desc()).all()

        output = []
        for r in results:
            rev = float(r.revenue or 0)
            # Sub-query for peak hour per sub_category
            peak = self.db.query(
                func.substr(SalesOrder.order_time, 1, 2).label("hour"),
                func.count(func.distinct(SalesOrder.id)).label("cnt"),
            ).join(SalesOrderItem, SalesOrderItem.order_id == SalesOrder.id).join(
                SalesProduct, SalesProduct.sku == SalesOrderItem.sku
            ).filter(
                SalesProduct.sub_category == r.sub_category
            ).group_by(
                func.substr(SalesOrder.order_time, 1, 2)
            ).order_by(func.count(func.distinct(SalesOrder.id)).desc()).first()

            output.append({
                "department": r.department_name,
                "sub_category": r.sub_category,
                "revenue": round(rev, 2),
                "volume_sold": int(r.volume or 0),
                "avg_tax_rate": round(float(r.avg_tax or 18), 1),
                "brand_count": int(r.brand_count or 0),
                "sku_count": int(r.sku_count or 0),
                "peak_sales_hour": f"{peak[0]}:00" if peak else "N/A",
            })
        return output

    # ── Product Performance ────────────────────────────────────────────────

    def product_performance(
        self, top_n: int = 10
    ) -> Dict[str, List[Dict]]:
        """
        Top/bottom products by revenue and sales velocity.

        Returns:
            {top_by_revenue, top_by_volume, slowest_moving}
        """
        from sqlalchemy import func
        base = self.db.query(
            SalesProduct.sku,
            SalesProduct.product_name,
            SalesProduct.brand_name,
            SalesProduct.sub_category,
            func.sum(SalesOrderItem.nmv).label("revenue"),
            func.sum(SalesOrderItem.qty).label("qty"),
            func.count(func.distinct(SalesOrder.id)).label("order_frequency"),
        ).join(SalesOrderItem, SalesOrderItem.sku == SalesProduct.sku).join(
            SalesOrder, SalesOrder.id == SalesOrderItem.order_id
        ).group_by(
            SalesProduct.sku,
            SalesProduct.product_name,
            SalesProduct.brand_name,
            SalesProduct.sub_category,
        )

        def fmt(rows):
            return [
                {
                    "sku": r.sku,
                    "product_name": r.product_name,
                    "brand_name": r.brand_name,
                    "sub_category": r.sub_category,
                    "revenue": round(float(r.revenue or 0), 2),
                    "quantity_sold": int(r.qty or 0),
                    "order_frequency": int(r.order_frequency or 0),
                }
                for r in rows
            ]

        return {
            "top_by_revenue": fmt(
                base.order_by(func.sum(SalesOrderItem.nmv).desc()).limit(top_n).all()
            ),
            "top_by_volume": fmt(
                base.order_by(func.sum(SalesOrderItem.qty).desc()).limit(top_n).all()
            ),
            "slowest_moving": fmt(
                base.order_by(func.sum(SalesOrderItem.qty).asc()).limit(top_n).all()
            ),
        }

    # ── Customer Analytics ─────────────────────────────────────────────────

    def customer_analytics(self, top_n: int = 10) -> Dict:
        """
        Customer spend profiles, repeat purchase rates, and top spenders.

        Returns:
            {total_unique_customers, guest_transaction_ratio, top_spenders,
             avg_items_per_order}
        """
        from sqlalchemy import func
        total_customers = self.db.query(SalesCustomer.customer_number).count()
        guest_count = (
            self.db.query(SalesOrder.customer_number)
            .filter(SalesOrder.customer_number == "1000000000")
            .distinct()
            .count()
        )
        total_orders = self.db.query(SalesOrder.id).count()
        guest_orders = (
            self.db.query(SalesOrder.id)
            .filter(SalesOrder.customer_number == "1000000000")
            .count()
        )

        top_spenders = self.db.query(
            SalesCustomer.customer_number,
            SalesCustomer.customer_name,
            func.sum(SalesOrderItem.nmv).label("total_spend"),
            func.count(func.distinct(SalesOrder.id)).label("visit_count"),
            func.sum(SalesOrderItem.qty).label("units_bought"),
        ).join(SalesOrder, SalesOrder.customer_number == SalesCustomer.customer_number).join(
            SalesOrderItem, SalesOrderItem.order_id == SalesOrder.id
        ).filter(
            SalesCustomer.customer_number != "1000000000"
        ).group_by(
            SalesCustomer.customer_number, SalesCustomer.customer_name
        ).order_by(
            func.sum(SalesOrderItem.nmv).desc()
        ).limit(top_n).all()

        avg_items = self.db.query(
            func.avg(
                self.db.query(func.count(SalesOrderItem.id))
                .filter(SalesOrderItem.order_id == SalesOrder.id)
                .correlate(SalesOrder)
                .scalar_subquery()
            )
        ).scalar()

        return {
            "total_unique_customers": total_customers,
            "guest_customers": guest_count,
            "identified_customers": total_customers - guest_count,
            "total_orders": total_orders,
            "guest_order_count": guest_orders,
            "guest_transaction_ratio_percent": round(
                (guest_orders / max(total_orders, 1)) * 100, 2
            ),
            "top_spenders": [
                {
                    "customer_number": r.customer_number,
                    "customer_name": r.customer_name,
                    "total_spend": round(float(r.total_spend or 0), 2),
                    "visit_count": int(r.visit_count or 0),
                    "units_bought": int(r.units_bought or 0),
                    "avg_spend_per_visit": round(
                        float(r.total_spend or 0) / max(int(r.visit_count or 1), 1), 2
                    ),
                }
                for r in top_spenders
            ],
        }

    # ── Salesperson Performance ────────────────────────────────────────────

    def salesperson_performance(self) -> List[Dict]:
        """
        Revenue and basket metrics per salesperson.

        Returns:
            List of {salesperson_id, name, employee_code, revenue,
                     orders_handled, avg_basket}
        """
        from sqlalchemy import func
        results = self.db.query(
            Salesperson.id,
            Salesperson.name,
            Salesperson.employee_code,
            func.sum(SalesOrderItem.nmv).label("revenue"),
            func.count(func.distinct(SalesOrder.id)).label("orders"),
            func.sum(SalesOrderItem.qty).label("units"),
        ).join(SalesOrder, SalesOrder.salesperson_id == Salesperson.id).join(
            SalesOrderItem, SalesOrderItem.order_id == SalesOrder.id
        ).group_by(
            Salesperson.id, Salesperson.name, Salesperson.employee_code
        ).order_by(func.sum(SalesOrderItem.nmv).desc()).all()

        return [
            {
                "salesperson_id": r.id,
                "name": r.name,
                "employee_code": r.employee_code,
                "revenue": round(float(r.revenue or 0), 2),
                "orders_handled": int(r.orders or 0),
                "units_sold": int(r.units or 0),
                "avg_basket_value": round(
                    float(r.revenue or 0) / max(int(r.orders or 1), 1), 2
                ),
            }
            for r in results
        ]


# ------------------------------------------------------------------------------
# CLI Import Command
# ------------------------------------------------------------------------------

def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.services.sales_importer",
        description="PurpleInsight Retail Sales ETL - Import Excel/CSV into PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import CSV with default settings
  python -m backend.services.sales_importer data/sales.csv

  # Import Excel with batch size 50 and verbose logging
  python -m backend.services.sales_importer data/sales.xlsx --batch-size 50 --verbose

  # Dry run (validate only, no DB writes)
  python -m backend.services.sales_importer data/sales.csv --dry-run

  # Override database URL
  python -m backend.services.sales_importer data/sales.csv --db-url postgresql://user:pass@localhost/purpleinsight

  # Print analytics summary after import
  python -m backend.services.sales_importer data/sales.csv --analytics
        """,
    )
    parser.add_argument(
        "file",
        help="Path to the source Excel (.xlsx, .xls) or CSV (.csv) file.",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help=(
            "SQLAlchemy database URL. "
            "Defaults to DATABASE_URL env var or 'sqlite:///store_intelligence.db'."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of rows per commit batch (default: 100).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate file and parse rows without writing to the database.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Abort entire import on first unhandled row error.",
    )
    parser.add_argument(
        "--analytics",
        action="store_true",
        help="Print an analytics summary after import completes.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser


def main() -> None:
    """CLI entry point for the sales importer."""
    parser = _build_cli_parser()
    args = parser.parse_args()

    # Logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        for h in logger.handlers:
            h.setLevel(logging.DEBUG)

    # Database URL resolution
    db_url = args.db_url or os.getenv(
        "DATABASE_URL", "sqlite:///store_intelligence.db"
    )

    logger.info(f"Connecting to database: {db_url}")

    # Bootstrap DB engine
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.models.base import Base

    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_engine(db_url, connect_args=connect_args, echo=False)

    # Auto-create tables if missing
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        importer = SalesImporter(
            db=db,
            batch_size=args.batch_size,
            stop_on_error=args.stop_on_error,
            dry_run=args.dry_run,
        )
        stats = importer.run(args.file)

        # Print stats table
        print("\n" + "=" * 58)
        print("  PurpleInsight Sales Importer - Run Summary")
        print("=" * 58)
        for k, v in stats.to_summary().items():
            print(f"  {k:<38} {v}")
        print("=" * 58)

        if stats.validation_errors:
            print(f"\n  [!] {len(stats.validation_errors)} validation error(s) logged.")
            for err in stats.validation_errors[:10]:
                print(f"     Row {err['row']}: {err['reason']}")
            if len(stats.validation_errors) > 10:
                print(f"     ... and {len(stats.validation_errors) - 10} more.")

        # Optional analytics printout
        if args.analytics and not args.dry_run:
            print("\n" + "-" * 58)
            print("  Analytics Quick Summary")
            print("-" * 58)
            analytics = SalesAnalyticsQueries(db)
            rev = analytics.revenue_summary()
            print(f"  Total GMV:          Rs{rev['total_gmv']:>12,.2f}")
            print(f"  Total NMV:          Rs{rev['total_nmv']:>12,.2f}")
            print(f"  Total Discounts:    Rs{rev['total_discounts']:>12,.2f}")
            print(f"  Total Tax:          Rs{rev['total_tax_collected']:>12,.2f}")
            print(f"  Total Orders:        {rev['total_orders']:>12}")
            print(f"  Avg Order Value:    Rs{rev['avg_order_value']:>12,.2f}")
            print(f"  Effective Discount:  {rev['effective_discount_rate_percent']:>11.2f}%")

            peaks = analytics.peak_sales_hours(top_n=3)
            print("\n  Peak Sales Hours:")
            for p in peaks:
                print(
                    f"    {p['hour']}  Rs{p['revenue']:>10,.2f}  "
                    f"({p['order_count']} orders)"
                )
            print("-" * 58 + "\n")

    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Import interrupted by user.")
        sys.exit(130)
    finally:
        db.close()


if __name__ == "__main__":
    main()
