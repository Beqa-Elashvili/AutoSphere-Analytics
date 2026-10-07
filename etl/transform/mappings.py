"""Reference mappings used for normalization.

Allowed values mirror the CHECK constraints in database/schemas/02_staging.sql.
Synonyms were built by profiling the raw files: each maps an observed
variant (after lowercasing and replacing spaces/hyphens with '_') to its
canonical value.
"""

ALLOWED: dict[str, set[str]] = {
    "branch_type": {"sales_and_service", "sales_only", "service_only"},
    "business_line": {"vehicles", "parts", "accessories", "consumables"},
    "role": {"branch_manager", "sales_consultant", "service_advisor", "technician", "cashier"},
    "department": {"management", "sales", "service", "finance"},
    "customer_type": {"individual", "corporate"},
    "loyalty_tier": {"standard", "silver", "gold", "platinum"},
    "fuel_type": {"petrol", "diesel", "hybrid", "electric", "lpg"},
    "transmission": {"manual", "automatic"},
    "sales_channel": {"in_store", "online", "phone"},
    "sales_order_status": {"completed", "cancelled", "returned"},
    "service_type": {"maintenance", "repair", "diagnostics", "tire_service", "body_work", "warranty"},
    "service_order_status": {"completed", "cancelled", "in_progress"},
    "item_type": {"labor", "part"},
    "source_type": {"sale", "service"},
    "payment_method": {"cash", "card", "bank_transfer", "installment"},
    "payment_status": {"completed", "failed", "refunded"},
    "feedback_channel": {"sms_survey", "email_survey", "website", "call_center"},
}

SYNONYMS: dict[str, dict[str, str]] = {
    "fuel_type": {"gasoline": "petrol", "gas": "petrol", "benzine": "petrol", "ev": "electric"},
    "transmission": {"auto": "automatic", "at": "automatic", "mt": "manual"},
    "sales_channel": {"instore": "in_store", "store": "in_store", "web": "online", "telephone": "phone"},
    "sales_order_status": {"canceled": "cancelled", "complete": "completed", "done": "completed"},
    "service_order_status": {"canceled": "cancelled", "complete": "completed", "done": "completed",
                             "inprogress": "in_progress", "open": "in_progress"},
    "service_type": {"tire": "tire_service", "tyre_service": "tire_service", "bodywork": "body_work"},
    "item_type": {"labour": "labor", "parts": "part"},
    "payment_method": {"credit_card": "card", "debit_card": "card", "bank": "bank_transfer",
                       "transfer": "bank_transfer"},
    "payment_status": {"success": "completed", "successful": "completed", "paid": "completed",
                       "declined": "failed", "refund": "refunded"},
    "feedback_channel": {"sms": "sms_survey", "email": "email_survey", "web": "website", "phone": "call_center"},
}

CANONICAL_CITIES = {"Tbilisi", "Batumi", "Kutaisi", "Rustavi", "Zugdidi", "Gori", "Telavi", "Poti"}
UNKNOWN_CITY = "Unknown"

# Lowercased variant -> canonical city (misspellings, historic names, Georgian script).
CITY_SYNONYMS: dict[str, str] = {
    "tbilsi": "Tbilisi", "tiflis": "Tbilisi", "თბილისი": "Tbilisi",
    "batum": "Batumi", "ბათუმი": "Batumi",
    "kutaissi": "Kutaisi", "ქუთაისი": "Kutaisi",
    "rustavy": "Rustavi", "რუსთავი": "Rustavi",
    "zugdidy": "Zugdidi", "ზუგდიდი": "Zugdidi",
    "გორი": "Gori", "თელავი": "Telavi", "ფოთი": "Poti",
    **{c.lower(): c for c in CANONICAL_CITIES},
}

TRUE_VALUES = {"true", "t", "yes", "y", "1"}
FALSE_VALUES = {"false", "f", "no", "n", "0"}
