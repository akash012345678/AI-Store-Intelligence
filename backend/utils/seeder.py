import csv
import os
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_
from backend.models.sales import (
    SalesStore,
    SalesCustomer,
    Salesperson,
    SalesProduct,
    SalesOrder,
    SalesOrderItem
)

logger = logging.getLogger("PurpleInsight.Seeder")
logger.setLevel(logging.INFO)

def safe_float(value: str) -> float:
    """Helper to convert string parameters to float safely, returning 0.0 on blank or exception."""
    if not value or value.strip() == "":
        return 0.0
    try:
        return float(value.strip())
    except Exception:
        return 0.0

def safe_int(value: str) -> int:
    """Helper to convert string parameters to integer safely, returning 0 on blank or exception."""
    if not value or value.strip() == "":
        return 0
    try:
        return int(float(value.strip())) # handle floating strings like '2.0'
    except Exception:
        return 0

def seed_database_from_csv(db: Session, csv_path: str) -> int:
    """Parses flat retail sales CSV rows and seeds the normalized relational database structures."""
    if not os.path.exists(csv_path):
        logger.error(f"Seeder CSV dataset not found at path: {csv_path}")
        return 0

    logger.info(f"Beginning CSV seeder parsing from: {csv_path}")
    
    # Track cache records to prevent redundant SELECT queries inside ingestion loops (huge performance gain!)
    store_ids = set()
    customer_numbers = set()
    salesperson_ids = set()
    product_skus = set()
    order_ids = set()

    # Load existing in DB
    for s in db.query(SalesStore.id).all(): store_ids.add(s[0])
    for c in db.query(SalesCustomer.customer_number).all(): customer_numbers.add(c[0])
    for sp in db.query(Salesperson.id).all(): salesperson_ids.add(sp[0])
    for p in db.query(SalesProduct.sku).all(): product_skus.add(p[0])
    for o in db.query(SalesOrder.id).all(): order_ids.add(o[0])

    row_count = 0
    item_count = 0

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        
        # Clean headers (strip spaces)
        reader.fieldnames = [name.strip() for name in reader.fieldnames] if reader.fieldnames else []

        for row in reader:
            row_count += 1
            # Clean values
            row = {k: v.strip() if v else "" for k, v in row.items()}
            
            store_id = row.get("store_id")
            customer_number = row.get("customer_number")
            salesperson_id = row.get("salesperson_id") or row.get("salesperson_name") or "STAF-UNKNOWN"
            sku = row.get("sku")
            order_id = row.get("order_id")

            if not store_id or not sku or not order_id:
                continue

            # 1. Seed Stores
            if store_id not in store_ids:
                store_obj = SalesStore(
                    id=store_id,
                    name=row.get("store_name", "Unknown Store"),
                    city=row.get("city", "Unknown City")
                )
                db.add(store_obj)
                db.flush()
                store_ids.add(store_id)

            # 2. Seed Customers
            # If customer_number is blank, create default fallback Guest key
            if not customer_number:
                customer_number = "GUEST-UNKNOWN"
            if customer_number not in customer_numbers:
                customer_obj = SalesCustomer(
                    customer_number=customer_number,
                    customer_name=row.get("customer_name") or "Guest"
                )
                db.add(customer_obj)
                db.flush()
                customer_numbers.add(customer_number)

            # 3. Seed Salespersons
            if salesperson_id not in salesperson_ids:
                salesperson_obj = Salesperson(
                    id=salesperson_id,
                    employee_code=row.get("employee_code") or "CL-UNKNOWN",
                    name=row.get("salesperson_name") or "Kasthuri V"
                )
                db.add(salesperson_obj)
                db.flush()
                salesperson_ids.add(salesperson_id)

            # 4. Seed Products
            if sku not in product_skus:
                product_obj = SalesProduct(
                    sku=sku,
                    product_id=safe_int(row.get("product_id", "0")),
                    ean=row.get("ean", ""),
                    product_name=row.get("product_name", "Unknown Product"),
                    brand_name=row.get("brand_name", "Generic"),
                    department_name=row.get("dep_name", "General"),
                    sub_category=row.get("sub_category", "General"),
                    brand_type=row.get("brand_type", "National"),
                    hsn_code=row.get("hsn_code", "")
                )
                db.add(product_obj)
                db.flush()
                product_skus.add(sku)

            # 5. Seed Orders
            if order_id not in order_ids:
                order_obj = SalesOrder(
                    id=order_id,
                    store_id=store_id,
                    customer_number=customer_number,
                    salesperson_id=salesperson_id,
                    invoice_number=row.get("invoice_number", f"INV-{order_id}"),
                    invoice_type=row.get("invoice_type", "sales"),
                    order_date=row.get("order_date", "10-04-2026"),
                    order_time=row.get("order_time", "12:00:00"),
                    coupon_code=row.get("coupon_code", ""),
                    offer_name=row.get("offer_name", ""),
                    discount_code=row.get("discount_code", ""),
                    return_id=row.get("return_id", ""),
                    week_assigned=row.get("week_assigned", "")
                )
                db.add(order_obj)
                db.flush()
                order_ids.add(order_id)

            # 6. Seed Order Items
            item_obj = SalesOrderItem(
                order_id=order_id,
                sku=sku,
                qty=safe_int(row.get("qty", "1")),
                gmv=safe_float(row.get("GMV", "0.0")),
                nmv=safe_float(row.get("NMV", "0.0")),
                coupon_amount=safe_float(row.get("coupon_amount", "0.0")),
                item_promotion=safe_float(row.get("item_promotion", "0.0")),
                amt_without_gwp=safe_float(row.get("amt_without_gwp", "0.0")),
                total_amount=safe_float(row.get("total_amount", "0.0")),
                tax_rate=safe_float(row.get("tax", "18.0")),
                tax_m=safe_float(row.get("tax_m", "1.18")),
                taxable_amt=safe_float(row.get("taxable_amt", "0.0")),
                tax_amt=safe_float(row.get("tax_amt", "0.0")),
                pb_eb_sale=row.get("pb_eb_sale", "")
            )
            db.add(item_obj)
            item_count += 1

            # Batch commit to prevent high memory usage
            if item_count % 200 == 0:
                db.commit()

    db.commit()
    logger.info(f"Database seeder complete. Ingested {row_count} rows, created {item_count} relational order items.")
    return item_count
