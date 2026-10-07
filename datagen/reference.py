"""Static reference data for the fictional AutoSphere Analytics business.

Every brand, vehicle make, company and person name here is invented.
"""
from datetime import date

# Fixed business period so generated data is identical regardless of when it runs.
START_DATE = date(2024, 1, 1)
END_DATE = date(2026, 9, 30)

# Canonical city -> region. Customers may also live in smaller cities without a branch.
CITIES = {
    "Tbilisi": "Tbilisi",
    "Batumi": "Adjara",
    "Kutaisi": "Imereti",
    "Rustavi": "Kvemo Kartli",
    "Zugdidi": "Samegrelo-Zemo Svaneti",
    "Gori": "Shida Kartli",
    "Telavi": "Kakheti",
    "Poti": "Samegrelo-Zemo Svaneti",
}
CUSTOMER_CITY_WEIGHTS = {
    "Tbilisi": 0.48, "Batumi": 0.15, "Kutaisi": 0.12, "Rustavi": 0.10,
    "Zugdidi": 0.08, "Gori": 0.03, "Telavi": 0.02, "Poti": 0.02,
}

# Messy spellings seen in source systems (used by the DQ injector).
CITY_VARIANTS = {
    "Tbilisi": ["tbilisi", "TBILISI", "Tbilsi", " Tbilisi ", "Tiflis", "თბილისი"],
    "Batumi": ["batumi", "BATUMI", "Batum", "ბათუმი"],
    "Kutaisi": ["kutaisi", "KUTAISI", "Kutaissi", "ქუთაისი"],
    "Rustavi": ["rustavi", "RUSTAVI", "Rustavy"],
    "Zugdidi": ["zugdidi", "ZUGDIDI", "Zugdidy"],
}

# branch_id, name, city, type, opened, sales_weight, service_weight
BRANCHES = [
    ("BR01", "AutoSphere Tbilisi Vake",     "Tbilisi", "sales_and_service", date(2014, 4, 1),  0.22, 0.20),
    ("BR02", "AutoSphere Tbilisi Didube",   "Tbilisi", "sales_and_service", date(2016, 9, 15), 0.20, 0.18),
    ("BR03", "AutoSphere Tbilisi Gldani Service", "Tbilisi", "service_only", date(2019, 3, 1), 0.00, 0.17),
    ("BR04", "AutoSphere Batumi",           "Batumi",  "sales_and_service", date(2017, 6, 1),  0.15, 0.15),
    ("BR05", "AutoSphere Kutaisi",          "Kutaisi", "sales_and_service", date(2018, 2, 1),  0.12, 0.12),
    ("BR06", "AutoSphere Rustavi",          "Rustavi", "sales_and_service", date(2020, 5, 10), 0.11, 0.10),
    ("BR07", "AutoSphere Zugdidi",          "Zugdidi", "sales_and_service", date(2021, 8, 1),  0.08, 0.08),
    ("BR08", "AutoSphere Batumi Parts Store", "Batumi", "sales_only",      date(2022, 4, 1),  0.12, 0.00),
]

# Staffing per branch type: role -> (department, headcount range)
STAFFING = {
    "sales_and_service": {
        "branch_manager": ("management", (1, 1)), "sales_consultant": ("sales", (3, 5)),
        "service_advisor": ("service", (2, 3)), "technician": ("service", (3, 4)),
        "cashier": ("finance", (1, 1)),
    },
    "service_only": {
        "branch_manager": ("management", (1, 1)), "service_advisor": ("service", (2, 3)),
        "technician": ("service", (4, 5)), "cashier": ("finance", (1, 1)),
    },
    "sales_only": {
        "branch_manager": ("management", (1, 1)), "sales_consultant": ("sales", (3, 4)),
        "cashier": ("finance", (1, 1)),
    },
}

# category_id, name, business_line
CATEGORIES = [
    ("CAT01", "New Vehicles", "vehicles"),
    ("CAT02", "Used Vehicles", "vehicles"),
    ("CAT03", "Tires", "parts"),
    ("CAT04", "Batteries", "parts"),
    ("CAT05", "Brakes", "parts"),
    ("CAT06", "Filters", "parts"),
    ("CAT07", "Engine Oil & Fluids", "consumables"),
    ("CAT08", "Suspension", "parts"),
    ("CAT09", "Lighting & Electrical", "parts"),
    ("CAT10", "Car Care", "consumables"),
    ("CAT11", "Interior Accessories", "accessories"),
    ("CAT12", "Electronics & Multimedia", "accessories"),
]

# product_id, name, category_id, brand, list_price (current, GEL), unit_cost, popularity weight
# Fictional brands. Popularity drives sales frequency; margins differ by business line.
PRODUCTS = [
    ("PRD001", "Veloria Sena 1.6 Sedan",          "CAT01", "Veloria",  58900.00, 54200.00, 0.6),
    ("PRD002", "Veloria Terra 2.0 SUV",           "CAT01", "Veloria",  89500.00, 82300.00, 0.5),
    ("PRD003", "Kestrel Volt EV Hatchback",       "CAT01", "Kestrel", 112000.00, 103500.00, 0.3),
    ("PRD004", "Nordvik Aero Hybrid Crossover",   "CAT01", "Nordvik",  96400.00, 88700.00, 0.4),
    ("PRD005", "Certified Pre-Owned Sedan",       "CAT02", "AutoSphere Certified", 32500.00, 28100.00, 0.5),
    ("PRD006", "Certified Pre-Owned SUV",         "CAT02", "AutoSphere Certified", 45800.00, 39600.00, 0.4),
    ("PRD007", "Telvar AllSeason 205/55 R16",     "CAT03", "Telvar",     245.00, 168.00, 6.0),
    ("PRD008", "Telvar WinterGrip 215/60 R17",    "CAT03", "Telvar",     310.00, 214.00, 5.0),
    ("PRD009", "Monzaro Sport 225/45 R18",        "CAT03", "Monzaro",    420.00, 281.00, 2.5),
    ("PRD010", "Monzaro SUV Terrain 235/65 R17",  "CAT03", "Monzaro",    395.00, 270.00, 2.5),
    ("PRD011", "Voltaris 60Ah Battery",           "CAT04", "Voltaris",   285.00, 192.00, 4.0),
    ("PRD012", "Voltaris 74Ah AGM Battery",       "CAT04", "Voltaris",   465.00, 318.00, 2.0),
    ("PRD013", "Brakova Front Brake Pad Set",     "CAT05", "Brakova",    135.00,  74.00, 5.0),
    ("PRD014", "Brakova Rear Brake Pad Set",      "CAT05", "Brakova",    115.00,  63.00, 4.0),
    ("PRD015", "Brakova Brake Disc (pair)",       "CAT05", "Brakova",    290.00, 176.00, 2.0),
    ("PRD016", "Quellis Oil Filter",              "CAT06", "Quellis",     28.00,  13.00, 9.0),
    ("PRD017", "Quellis Air Filter",              "CAT06", "Quellis",     45.00,  22.00, 6.0),
    ("PRD018", "Quellis Cabin Pollen Filter",     "CAT06", "Quellis",     39.00,  18.00, 5.0),
    ("PRD019", "Quellis Fuel Filter",             "CAT06", "Quellis",     62.00,  33.00, 3.0),
    ("PRD020", "Arvio Synthetic 5W-30 (4L)",      "CAT07", "Arvio",      118.00,  71.00, 9.0),
    ("PRD021", "Arvio Synthetic 0W-20 (4L)",      "CAT07", "Arvio",      132.00,  80.00, 5.0),
    ("PRD022", "Arvio Coolant Antifreeze (5L)",   "CAT07", "Arvio",       48.00,  27.00, 4.0),
    ("PRD023", "Arvio DOT4 Brake Fluid (1L)",     "CAT07", "Arvio",       26.00,  13.00, 3.0),
    ("PRD024", "Arvio Winter Washer Fluid (4L)",  "CAT07", "Arvio",       15.00,   7.00, 6.0),
    ("PRD025", "Oktavo Front Shock Absorber",     "CAT08", "Oktavo",     260.00, 165.00, 1.8),
    ("PRD026", "Oktavo Control Arm",              "CAT08", "Oktavo",     185.00, 112.00, 1.5),
    ("PRD027", "Oktavo Stabilizer Link",          "CAT08", "Oktavo",      55.00,  29.00, 2.0),
    ("PRD028", "Lumetra LED Headlight Bulb Set",  "CAT09", "Lumetra",     95.00,  46.00, 3.0),
    ("PRD029", "Lumetra Spark Plug Set (4)",      "CAT09", "Lumetra",     88.00,  47.00, 3.5),
    ("PRD030", "Lumetra Wiper Blade Set",         "CAT09", "Lumetra",     42.00,  19.00, 5.0),
    ("PRD031", "Lumetra Alternator",              "CAT09", "Lumetra",    540.00, 365.00, 0.8),
    ("PRD032", "Brillo Car Shampoo (1L)",         "CAT10", "Brillo",      19.00,   8.00, 4.0),
    ("PRD033", "Brillo Ceramic Coating Kit",      "CAT10", "Brillo",     320.00,  92.00, 0.6),
    ("PRD034", "Brillo Interior Cleaner",         "CAT10", "Brillo",      24.00,  10.00, 3.0),
    ("PRD035", "Comfora All-Weather Floor Mats",  "CAT11", "Comfora",     89.00,  34.00, 3.0),
    ("PRD036", "Comfora Leather Seat Covers",     "CAT11", "Comfora",    360.00, 128.00, 0.9),
    ("PRD037", "Comfora Trunk Organizer",         "CAT11", "Comfora",     65.00,  24.00, 1.5),
    ("PRD038", "Sonaro Dash Camera HD",           "CAT12", "Sonaro",     230.00,  98.00, 1.6),
    ("PRD039", "Sonaro Parking Sensor Kit",       "CAT12", "Sonaro",     280.00, 121.00, 1.0),
    ("PRD040", "Sonaro Wireless CarPlay Adapter", "CAT12", "Sonaro",     175.00,  66.00, 1.3),
]
DISCONTINUED_PRODUCTS = {"PRD019", "PRD031"}

# Price/cost index relative to current master prices (2026 = 1.00): annual price increases.
PRICE_INDEX = {2024: 0.89, 2025: 0.94, 2026: 1.00}

# Monthly seasonality multipliers (Jan..Dec).
SALES_SEASONALITY = [0.85, 0.85, 1.00, 1.08, 1.00, 0.95, 0.93, 0.90, 1.00, 1.15, 1.22, 1.15]
SERVICE_SEASONALITY = [1.15, 1.10, 1.08, 1.05, 0.95, 0.90, 0.88, 0.88, 0.95, 1.02, 1.12, 1.15]

# Parts used per service type (categories to draw from).
SERVICE_PART_CATEGORIES = {
    "maintenance": ["CAT06", "CAT07", "CAT09"],
    "repair": ["CAT05", "CAT08", "CAT04", "CAT09"],
    "diagnostics": [],
    "tire_service": ["CAT03"],
    "body_work": ["CAT10"],
    "warranty": ["CAT05", "CAT08", "CAT09", "CAT04"],
}
SERVICE_TYPE_WEIGHTS = {
    "maintenance": 0.36, "repair": 0.22, "diagnostics": 0.14,
    "tire_service": 0.14, "body_work": 0.07, "warranty": 0.07,
}
# Median turnaround in hours per service type (used for durations and wait-time stories).
SERVICE_MEDIAN_HOURS = {
    "maintenance": 3.0, "repair": 26.0, "diagnostics": 1.5,
    "tire_service": 1.0, "body_work": 72.0, "warranty": 30.0,
}
LABOR_DESCRIPTIONS = {
    "maintenance": "Scheduled maintenance labour",
    "repair": "Mechanical repair labour",
    "diagnostics": "Computer diagnostics",
    "tire_service": "Tire fitting and balancing",
    "body_work": "Body repair and paint labour",
    "warranty": "Warranty repair labour",
}
LABOR_RATE = 95.0   # GEL per hour (2026), scaled by PRICE_INDEX
LABOR_COST = 40.0   # internal cost per hour

# Fictional vehicle makes and models for customer-owned vehicles.
VEHICLE_MODELS = {
    "Veloria": ["Sena", "Terra", "Corsa Line", "Mira"],
    "Kestrel": ["Volt", "Strata", "Ridge"],
    "Nordvik": ["Aero", "Fjell", "Polar"],
    "Altavia": ["Compact", "Grand", "Tourer"],
    "Brenna": ["City", "Cargo Van", "Explorer"],
}

# Transliterated Georgian names (synthetic combinations, no real individuals).
MALE_FIRST_NAMES = [
    "Giorgi", "Davit", "Luka", "Nikoloz", "Levan", "Irakli", "Zurab", "Tornike", "Lasha", "Sandro",
    "Beka", "Gela", "Mamuka", "Revaz", "Otar", "Archil", "Vakhtang", "Tamaz", "Shota", "Nika",
]
FEMALE_FIRST_NAMES = [
    "Nino", "Mariam", "Ana", "Tamar", "Salome", "Elene", "Natia", "Ketevan", "Maia", "Eka",
    "Tamta", "Lika", "Sopho", "Nana", "Khatia", "Mzia", "Teona", "Diana", "Irma", "Nato",
]
LAST_NAMES = [
    "Beridze", "Kapanadze", "Gelashvili", "Maisuradze", "Giorgadze", "Lomidze", "Tsiklauri",
    "Bolkvadze", "Kvaratskhelia", "Nozadze", "Abuladze", "Mikeladze", "Khutsishvili", "Tabatadze",
    "Japaridze", "Gogoladze", "Chikovani", "Shengelia", "Dolidze", "Kiknadze", "Gvaramia",
    "Jgerenaia", "Kakhidze", "Melikidze", "Svanidze", "Chkheidze", "Khachidze", "Todua",
    "Gabunia", "Kobakhidze", "Datunashvili", "Mchedlishvili",
]
COMPANY_PREFIXES = [
    "Kartli", "Rioni", "Mtkvari", "Kolkheti", "Iveria", "Aragvi", "Likhi", "Alazani",
    "Enguri", "Mtatsminda", "Kazbegi", "Tetnuldi", "Bakhmaro", "Sairme", "Martvili",
]
COMPANY_SUFFIXES = [
    "Logistics", "Construction", "Trans", "Agro", "Delivery", "Rent-a-Car", "Taxi Service",
    "Trade", "Tours", "Engineering",
]
