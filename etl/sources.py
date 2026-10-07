"""Source registry: expected raw columns, business keys and processing order.

This is the single definition of the raw file contract. Column lists match the
staging tables (database/schemas/02_staging.sql) minus the `loaded_at` audit column.
"""

SOURCE_COLUMNS: dict[str, list[str]] = {
    "branches": ["branch_id", "branch_name", "city", "region", "branch_type", "opened_date", "is_active"],
    "product_categories": ["category_id", "category_name", "business_line"],
    "products": ["product_id", "product_name", "category_id", "brand", "unit_cost", "list_price",
                 "launch_date", "is_active"],
    "employees": ["employee_id", "first_name", "last_name", "role", "department", "branch_id",
                  "hire_date", "is_active"],
    "customers": ["customer_id", "customer_type", "first_name", "last_name", "company_name", "email",
                  "phone", "city", "registration_date", "loyalty_tier"],
    "vehicles": ["vehicle_id", "vin", "make", "model", "model_year", "fuel_type", "transmission",
                 "customer_id", "registration_date"],
    "sales": ["sale_line_id", "invoice_number", "sale_datetime", "customer_id", "product_id", "branch_id",
              "employee_id", "quantity", "unit_price", "unit_cost", "discount_amount", "sales_channel",
              "order_status"],
    "service_orders": ["service_order_id", "vehicle_id", "customer_id", "branch_id", "employee_id",
                       "service_type", "opened_at", "closed_at", "order_status", "odometer_km"],
    "service_items": ["service_item_id", "service_order_id", "item_type", "product_id", "description",
                      "quantity", "unit_price", "unit_cost"],
    "payments": ["payment_id", "source_type", "source_reference", "customer_id", "payment_datetime",
                 "amount", "payment_method", "payment_status", "currency"],
    "customer_feedback": ["feedback_id", "customer_id", "branch_id", "service_order_id", "invoice_number",
                          "feedback_date", "channel", "rating", "feedback_text"],
}

BUSINESS_KEYS: dict[str, str] = {
    "branches": "branch_id",
    "product_categories": "category_id",
    "products": "product_id",
    "employees": "employee_id",
    "customers": "customer_id",
    "vehicles": "vehicle_id",
    "sales": "sale_line_id",
    "service_orders": "service_order_id",
    "service_items": "service_item_id",
    "payments": "payment_id",
    "customer_feedback": "feedback_id",
}

# Parents before children, so referential checks can use already-cleaned keys.
LOAD_ORDER: list[str] = list(SOURCE_COLUMNS)

MASTER_TABLES = {"branches", "product_categories", "products", "employees", "customers", "vehicles"}
