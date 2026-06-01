# Sales Dataset Analysis & Business Intelligence Blueprint

This document details the normalized relational database structures, database DDL scripts, Alembic migrations configurations, and premium business intelligence dashboard configurations derived from the Brigade Bangalore retail sales dataset.

---

## 1. Relational Entity Normalization

To eliminate data redundancy and enforce transactional integrity, the flat sales columns are normalized into 6 distinct entities:

1.  **SalesStore**: Represents the physical store node (PrimaryKey: `store_id`).
2.  **SalesCustomer**: Represents distinct shoppers, isolating customer names and phone numbers (PrimaryKey: `customer_number`).
3.  **Salesperson**: Maps shop staff assisting shoppers (PrimaryKey: `salesperson_id`).
4.  **SalesProduct**: Houses product definitions, pricing parameters, HSN codes, and branding taxonomy (PrimaryKey: `sku`).
5.  **SalesOrder**: Stores purchase receipts metadata, dates, times, and promotional codes (PrimaryKey: `order_id`).
6.  **SalesOrderItem**: Links receipts to products, capturing quantity and granular financial values (PrimaryKey: `id` autoincrement).

---

## 2. Production PostgreSQL Schema (DDL)

The following SQL script defines the complete, production-grade schema, establishing indices for high-frequency queries and cascading deletion rules:

```sql
-- Enable UUID extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Sales Stores Table
CREATE TABLE sales_stores (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL
);

-- 2. Sales Customers Table
CREATE TABLE sales_customers (
    customer_number VARCHAR(50) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
);

-- 3. Salespersons Table
CREATE TABLE salespersons (
    id VARCHAR(50) PRIMARY KEY,
    employee_code VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL
);

-- 4. Sales Products Table
CREATE TABLE sales_products (
    sku VARCHAR(50) PRIMARY KEY,
    product_id INTEGER NOT NULL UNIQUE,
    ean VARCHAR(50),
    product_name VARCHAR(350) NOT NULL,
    brand_name VARCHAR(100) NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    sub_category VARCHAR(100) NOT NULL,
    brand_type VARCHAR(50) NOT NULL, -- PB | Exclusive | National
    hsn_code VARCHAR(50)
);
CREATE INDEX idx_products_brand ON sales_products(brand_name);
CREATE INDEX idx_products_department ON sales_products(department_name);

-- 5. Sales Orders Table
CREATE TABLE sales_orders (
    id VARCHAR(50) PRIMARY KEY,
    store_id VARCHAR(50) NOT NULL REFERENCES sales_stores(id) ON DELETE CASCADE,
    customer_number VARCHAR(50) NOT NULL REFERENCES sales_customers(customer_number) ON DELETE CASCADE,
    salesperson_id VARCHAR(50) NOT NULL REFERENCES salespersons(id) ON DELETE CASCADE,
    invoice_number VARCHAR(50) NOT NULL,
    invoice_type VARCHAR(50) NOT NULL,
    order_date VARCHAR(50) NOT NULL,
    order_time VARCHAR(50) NOT NULL,
    coupon_code VARCHAR(50),
    offer_name VARCHAR(150),
    discount_code VARCHAR(50),
    return_id VARCHAR(50),
    week_assigned VARCHAR(50)
);
CREATE INDEX idx_orders_date ON sales_orders(order_date);

-- 6. Sales Order Items Table
CREATE TABLE sales_order_items (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL REFERENCES sales_orders(id) ON DELETE CASCADE,
    sku VARCHAR(50) NOT NULL REFERENCES sales_products(sku) ON DELETE CASCADE,
    qty INTEGER NOT NULL DEFAULT 1,
    gmv DOUBLE PRECISION NOT NULL,
    nmv DOUBLE PRECISION NOT NULL,
    coupon_amount DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    item_promotion DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    amt_without_gwp DOUBLE PRECISION NOT NULL,
    total_amount DOUBLE PRECISION NOT NULL,
    tax_rate DOUBLE PRECISION NOT NULL,
    tax_m DOUBLE PRECISION NOT NULL DEFAULT 1.18,
    taxable_amt DOUBLE PRECISION NOT NULL,
    tax_amt DOUBLE PRECISION NOT NULL,
    pb_eb_sale VARCHAR(50)
);
CREATE INDEX idx_items_order ON sales_order_items(order_id);
CREATE INDEX idx_items_sku ON sales_order_items(sku);
```

---

## 3. Alembic Migrations

Alembic utilizes python migration scripts to track and evolve database schemas. The migration file generated inside your database folder:
*   [migration_stub.py](file:///c:/Users/Maha%20Monisha/OneDrive/Desktop/purple/backend/database/connection.py)

To apply this migration in production:
```bash
alembic upgrade head
```

---

## 4. Premium Dashboard Widget Configurations

We define 5 premium, interactive dashboard widgets to visualize the analytics endpoints for store managers:

### Widget 1: Category Contribution Donut
*   **Query**: `GET /api/v1/sales-analytics/categories`
*   **Chart Type**: Semi-donut Chart (Harmonious purple HSL color scale)
*   **Business Value**: Displays sales and volume distributions by department. Highlights which aisle categories (e.g. Skin, Makeup, Bath) generate the highest true realized NMV.
*   **React Integration Stub**:
    ```javascript
    const CategoryWidget = ({ categories }) => (
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie data={categories} dataKey="revenue" nameKey="category_name" innerRadius={60} outerRadius={85} paddingAngle={4}>
            {categories.map((c, i) => <Cell key={i} fill={colors[i % colors.length]} />)}
          </Pie>
          <Tooltip formatter={(value) => `₹${value.toLocaleString()}`} />
        </PieChart>
      </ResponsiveContainer>
    );
    ```

### Widget 2: Brand Performance Funnel
*   **Query**: `GET /api/v1/sales-analytics/brands`
*   **Chart Type**: Horizontal Split Bar Chart (Comparing Private Label `PB` splits side-by-side)
*   **Business Value**: Visualizes realized revenue NMV per brand, highlighting the percentage contribution of Private Label (`PB`) vs National brand types.
*   **Metric Target**: Realized Brand Revenue splits.

### Widget 3: Realized Net Margins Trend
*   **Query**: `GET /api/v1/sales-analytics/revenue`
*   **Chart Type**: Stacked Area Chart over Time (Hourly Trend distribution)
*   **Business Value**: Plots Gross Merchandise Value (GMV) and Net Merchandise Value (NMV) hourly, illustrating the financial "leakage" caused by active coupons and promotions.

### Widget 4: Private Label Revenue Share
*   **Query**: `GET /api/v1/sales-analytics/conversion`
*   **Chart Type**: Circular Gauge Chart
*   **Business Value**: Measures the exact percentage contribution of Private Label (PB) items to the store's total NMV, demonstrating the effectiveness of the store's in-house branding strategies.

### Widget 5: Inventory Restocking Alerts
*   **Query**: `GET /api/v1/sales-analytics/products`
*   **Chart Type**: List Card grid with warning badges (filter on `slowest_moving`)
*   **Business Value**: Highlights the bottom 10 slowest-moving items by quantity, giving inventory operators instant alerts on what items need immediate promotions to clear shelf space.
