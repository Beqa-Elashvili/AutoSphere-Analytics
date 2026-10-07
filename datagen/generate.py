"""Generate clean, internally consistent synthetic datasets for AutoSphere Analytics.

This module produces *correct* data: every foreign key resolves, every invoice
total matches its payments, nobody buys before registering, etc. Data quality
problems are added afterwards by ``datagen.corrupt`` so that clean generation
and defect injection stay independent and testable.

Business stories embedded in the data (discoverable in the dashboards):
  * steady growth (~12%/year sales) with seasonality (tires in spring/autumn)
  * Kutaisi (BR05) sales decline from Q4 2025
  * Batumi (BR04) service turnaround slows down during 2026 -> waiting-time complaints
  * Zugdidi (BR07) customers complain about product availability
  * 2026 price increase -> more negative price feedback
  * Tbilisi Vake (BR01) service-quality feedback improves over time
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from datagen import reference as ref
from datagen.feedback_templates import (
    BASE_SENTIMENT, SALES_TOPIC_WEIGHTS, SERVICE_TOPIC_WEIGHTS, TEMPLATES,
)

# Target volumes at scale=1.0
VOLUMES = {"customers": 5000, "vehicles": 2000, "invoices": 13500, "service_orders": 11000, "feedback": 10500}

# Customers in cities without a branch shop in the nearest branch city.
NEAREST_BRANCH_CITY = {"Gori": "Tbilisi", "Telavi": "Tbilisi", "Poti": "Batumi"}

END_DT = datetime.combine(ref.END_DATE, time(23, 59))


def _weighted_choice(rng: np.random.Generator, options: list, weights) -> object:
    w = np.asarray(weights, dtype=float)
    return options[rng.choice(len(options), p=w / w.sum())]


def _months() -> list[tuple[int, int]]:
    return [(p.year, p.month) for p in pd.period_range(ref.START_DATE, ref.END_DATE, freq="M")]


def _random_datetime(rng, year: int, month: int, start_hour: float, end_hour: float) -> datetime:
    last_day = (pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)).day
    if (year, month) == (ref.END_DATE.year, ref.END_DATE.month):
        last_day = ref.END_DATE.day
    day = int(rng.integers(1, last_day + 1))
    minutes = int(rng.uniform(start_hour * 60, end_hour * 60))
    return datetime(year, month, day) + timedelta(minutes=minutes)


def _years_since_start(d: date) -> float:
    return (d - ref.START_DATE).days / 365.25


def _allocate(rng, total: int, weights: list[float]) -> np.ndarray:
    w = np.asarray(weights, dtype=float)
    return rng.multinomial(total, w / w.sum())


class _Generator:
    def __init__(self, seed: int, scale: float):
        self.rng = np.random.default_rng(seed)
        self.scale = scale
        self.n = {k: max(1, int(round(v * scale))) for k, v in VOLUMES.items()}

    # ------------------------------------------------------------------ master data
    def branches(self) -> pd.DataFrame:
        rows = [
            dict(branch_id=b, branch_name=name, city=city, region=ref.CITIES[city], branch_type=btype,
                 opened_date=opened, is_active=True)
            for b, name, city, btype, opened, _, _ in ref.BRANCHES
        ]
        return pd.DataFrame(rows)

    def categories(self) -> pd.DataFrame:
        return pd.DataFrame(ref.CATEGORIES, columns=["category_id", "category_name", "business_line"])

    def products(self) -> pd.DataFrame:
        rng = self.rng
        rows = []
        for pid, name, cat, brand, price, cost, _ in ref.PRODUCTS:
            launch = date(2015, 1, 1) + timedelta(days=int(rng.integers(0, 365 * 8)))
            rows.append(dict(product_id=pid, product_name=name, category_id=cat, brand=brand,
                             unit_cost=cost, list_price=price, launch_date=launch,
                             is_active=pid not in ref.DISCONTINUED_PRODUCTS))
        df = pd.DataFrame(rows)
        # Two recent launches: no sales may exist before these dates.
        df.loc[df.product_id == "PRD003", "launch_date"] = date(2024, 3, 1)
        df.loc[df.product_id == "PRD040", "launch_date"] = date(2025, 2, 1)
        return df

    def employees(self, branches: pd.DataFrame) -> pd.DataFrame:
        rng, rows, seq = self.rng, [], 1
        for b in branches.itertuples():
            for role, (dept, (lo, hi)) in ref.STAFFING[b.branch_type].items():
                for _ in range(int(rng.integers(lo, hi + 1))):
                    female = rng.random() < 0.45
                    first = rng.choice(ref.FEMALE_FIRST_NAMES if female else ref.MALE_FIRST_NAMES)
                    # 80% hired before the analysis period; the rest join during it.
                    if rng.random() < 0.8:
                        start = max(b.opened_date, date(2014, 1, 1))
                        hire = start + timedelta(days=int(rng.integers(0, (date(2023, 12, 31) - start).days)))
                    else:
                        hire = date(2024, 1, 1) + timedelta(days=int(rng.integers(0, 900)))
                    rows.append(dict(employee_id=f"EMP{seq:03d}", first_name=str(first),
                                     last_name=str(rng.choice(ref.LAST_NAMES)), role=role, department=dept,
                                     branch_id=b.branch_id, hire_date=hire, is_active=True))
                    seq += 1
        df = pd.DataFrame(rows)
        # A few leavers: inactive employees get no transactions in 2026.
        leavers = df[df.role.isin(["sales_consultant", "technician"])].sample(4, random_state=int(rng.integers(10**9))).index
        df.loc[leavers, "is_active"] = False
        return df

    def customers(self) -> pd.DataFrame:
        rng, n = self.rng, self.n["customers"]
        cities = list(ref.CUSTOMER_CITY_WEIGHTS)
        city_p = np.array(list(ref.CUSTOMER_CITY_WEIGHTS.values()))
        rows = []
        for i in range(1, n + 1):
            corporate = rng.random() < 0.08
            city = cities[rng.choice(len(cities), p=city_p / city_p.sum())]
            if rng.random() < 0.75:
                reg = date(2016, 1, 1) + timedelta(days=int(rng.integers(0, (date(2023, 12, 31) - date(2016, 1, 1)).days)))
            else:
                reg = date(2024, 1, 1) + timedelta(days=int(rng.integers(0, (ref.END_DATE - date(2024, 1, 1)).days - 14)))
            phone = f"+995 5{rng.integers(10, 100)} {rng.integers(10, 100)} {rng.integers(10, 100)} {rng.integers(10, 100)}"
            if corporate:
                company = f"{rng.choice(ref.COMPANY_PREFIXES)} {rng.choice(ref.COMPANY_SUFFIXES)} LLC"
                slug = company.lower().replace(" llc", "").replace(" ", "-")
                first = last = None
                email = f"office.{slug}{i}@example.com"
            else:
                female = rng.random() < 0.48
                first = str(rng.choice(ref.FEMALE_FIRST_NAMES if female else ref.MALE_FIRST_NAMES))
                last = str(rng.choice(ref.LAST_NAMES))
                company = None
                email = f"{first.lower()}.{last.lower()}{i}@example.com"
            rows.append(dict(customer_id=f"CUS{i:05d}", customer_type="corporate" if corporate else "individual",
                             first_name=first, last_name=last, company_name=company, email=email,
                             phone=phone, city=city, registration_date=reg, loyalty_tier="standard"))
        df = pd.DataFrame(rows)
        # Purchase propensity: a heavy-tailed distribution creates loyal repeat buyers.
        activity = rng.lognormal(0.0, 1.0, n) * np.where(df.customer_type == "corporate", 3.0, 1.0)
        self.customer_activity = activity
        return df

    def vehicles(self, customers: pd.DataFrame) -> pd.DataFrame:
        rng, n = self.rng, self.n["vehicles"]
        individuals = customers.index[customers.customer_type == "individual"].to_numpy()
        corporates = customers.index[customers.customer_type == "corporate"].to_numpy()
        owners = np.concatenate([
            rng.choice(individuals, size=int(n * 0.88), replace=False),
            rng.choice(corporates, size=n - int(n * 0.88), replace=True),  # fleets own several
        ])
        vin_chars = list("ABCDEFGHJKLMNPRSTUVWXYZ0123456789")  # VINs exclude I, O, Q
        fuels, fuel_p = ["petrol", "diesel", "hybrid", "electric", "lpg"], [0.45, 0.20, 0.17, 0.08, 0.10]
        rows, vins = [], set()
        for i, owner_idx in enumerate(owners, start=1):
            owner = customers.loc[owner_idx]
            make = str(rng.choice(list(ref.VEHICLE_MODELS)))
            while True:
                vin = "".join(rng.choice(vin_chars, 17))
                if vin not in vins:
                    vins.add(vin)
                    break
            reg = owner.registration_date + timedelta(days=int(rng.integers(0, 900)))
            reg = min(reg, ref.END_DATE - timedelta(days=30))
            rows.append(dict(vehicle_id=f"VEH{i:05d}", vin=vin, make=make,
                             model=str(rng.choice(ref.VEHICLE_MODELS[make])),
                             model_year=int(min(2026, max(2008, round(rng.normal(2018, 4))))),
                             fuel_type=fuels[rng.choice(5, p=fuel_p)],
                             transmission="automatic" if rng.random() < 0.7 else "manual",
                             customer_id=owner.customer_id, registration_date=reg))
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ helpers
    def _city_weights(self, customers: pd.DataFrame) -> dict[str, np.ndarray]:
        """Per branch city: propensity of each customer to shop there."""
        home = customers.city.map(lambda c: NEAREST_BRANCH_CITY.get(c, c)).to_numpy()
        return {city: self.customer_activity * np.where(home == city, 1.0, 0.04)
                for city in {b[2] for b in ref.BRANCHES}}

    def _pick_employee(self, employees: pd.DataFrame, branch_id: str, role: str, d: date) -> str:
        pool = employees[(employees.branch_id == branch_id) & (employees.role == role)]
        eligible = pool[(pool.hire_date <= d) & (pool.is_active | (d < date(2026, 1, 1)))]
        pool = eligible if not eligible.empty else pool
        return pool.employee_id.iloc[int(self.rng.integers(len(pool)))]

    @staticmethod
    def _sales_branch_weights(year: int, month: int) -> dict[str, float]:
        w = {b[0]: b[5] for b in ref.BRANCHES if b[5] > 0}
        if (year, month) >= (2026, 1):
            w["BR05"] *= 0.62            # Kutaisi decline
        elif (year, month) >= (2025, 10):
            w["BR05"] *= 0.82
        return w

    def _product_weights(self, products: pd.DataFrame, d: date) -> np.ndarray:
        w = products.popularity.to_numpy(dtype=float).copy()
        available = (products.launch_date <= d) & ~(
            products.product_id.isin(ref.DISCONTINUED_PRODUCTS) & (d > date(2025, 6, 30)))
        w[~available.to_numpy()] = 0
        m = d.month
        seasonal = {"PRD008": 3.0 if m in (10, 11, 12) else 0.4,     # winter tires
                    "PRD007": 2.0 if m in (3, 4, 5) else 1.0,        # all-season tires
                    "PRD024": 2.5 if m in (11, 12, 1, 2) else 0.6,   # winter washer fluid
                    "PRD011": 1.8 if m in (12, 1, 2) else 1.0,       # batteries die in winter
                    "PRD012": 1.8 if m in (12, 1, 2) else 1.0}
        for pid, factor in seasonal.items():
            w[(products.product_id == pid).to_numpy()] *= factor
        return w

    def _quantity(self, category_id: str) -> int:
        rng = self.rng
        if category_id == "CAT03":
            return int(rng.choice([2, 4], p=[0.3, 0.7]))
        if category_id in ("CAT07", "CAT10"):
            return int(rng.integers(1, 5))
        if category_id in ("CAT04", "CAT08", "CAT12"):
            return 1
        return int(rng.integers(1, 3))

    # ------------------------------------------------------------------ sales
    def sales(self, customers, employees, products) -> pd.DataFrame:
        rng = self.rng
        months = _months()
        month_w = [ref.SALES_SEASONALITY[m - 1] * (1 + 0.12 * _years_since_start(date(y, m, 1))) for y, m in months]
        counts = _allocate(rng, self.n["invoices"], month_w)
        city_w = self._city_weights(customers)
        branch_city = {b[0]: b[2] for b in ref.BRANCHES}
        reg = customers.registration_date.to_numpy()
        is_corp = (customers.customer_type == "corporate").to_numpy()

        headers = []
        for (y, m), cnt in zip(months, counts):
            bw = self._sales_branch_weights(y, m)
            bids = list(bw)
            for _ in range(cnt):
                b = _weighted_choice(rng, bids, list(bw.values()))
                dt = _random_datetime(rng, y, m, 9.5, 19.5)
                w = city_w[branch_city[b]] * (reg <= dt.date())
                c_idx = int(rng.choice(len(w), p=w / w.sum()))
                headers.append((dt, b, c_idx))
        headers.sort(key=lambda h: h[0])

        # Vehicle sales are few but very large, so a per-invoice coin flip makes branch
        # revenue swing randomly. Allocate them per branch-month by expected count
        # (error diffusion: the fractional remainder carries into the next month) so
        # revenue trends reflect the business stories, not sampling noise.
        groups: dict[tuple, list[int]] = {}
        for i, (dt, b, _) in enumerate(headers):
            if b != "BR08":
                groups.setdefault((b, dt.year, dt.month), []).append(i)
        vehicle_invoices, carry = set(), {}
        for (b, _, _), idxs in groups.items():
            expected = len(idxs) * 0.03 + carry.get(b, 0.0)
            k = min(len(idxs), int(np.floor(expected)))
            carry[b] = expected - k
            if k:
                w = np.array([3.0 if is_corp[headers[i][2]] else 1.0 for i in idxs])
                vehicle_invoices.update(rng.choice(idxs, size=k, replace=False, p=w / w.sum()).tolist())

        prod = products.set_index("product_id")
        vehicles_mask = products.category_id.isin(["CAT01", "CAT02"]).to_numpy()
        accessory_mask = products.category_id.isin(["CAT11", "CAT12"]).to_numpy()
        pids = products.product_id.to_numpy()
        rows, line_seq, inv_seq = [], 1, {}
        for h_idx, (dt, b, c_idx) in enumerate(headers):
            d = dt.date()
            inv_seq[d.year] = inv_seq.get(d.year, 0) + 1
            invoice = f"INV-{d.year}-{inv_seq[d.year]:06d}"
            customer_id = customers.customer_id.iat[c_idx]
            employee_id = self._pick_employee(employees, b, "sales_consultant", d)
            pw = self._product_weights(products, d)
            vehicle_sale = h_idx in vehicle_invoices
            if vehicle_sale:
                chosen = [_weighted_choice(rng, list(pids[vehicles_mask]), pw[vehicles_mask])]
                if rng.random() < 0.4:
                    chosen.append(_weighted_choice(rng, list(pids[accessory_mask]), pw[accessory_mask]))
            else:
                n_lines = int(rng.choice([1, 2, 3, 4, 5], p=[0.28, 0.30, 0.22, 0.13, 0.07]))
                w = pw * ~vehicles_mask
                n_lines = min(n_lines, int((w > 0).sum()))
                chosen = list(rng.choice(pids, size=n_lines, replace=False, p=w / w.sum()))
            status = str(rng.choice(["completed", "cancelled", "returned"], p=[0.94, 0.03, 0.03]))
            if status == "returned" and d > ref.END_DATE - timedelta(days=7):
                status = "completed"
            if b == "BR08":
                channel = str(rng.choice(["in_store", "online", "phone"], p=[0.65, 0.25, 0.10]))
            elif vehicle_sale:
                channel = "in_store"
            else:
                channel = str(rng.choice(["in_store", "online", "phone"], p=[0.82, 0.11, 0.07]))
            idx = ref.PRICE_INDEX[d.year]
            for pid in chosen:
                p = prod.loc[pid]
                is_vehicle = p.category_id in ("CAT01", "CAT02")
                qty = 1 if is_vehicle else self._quantity(p.category_id)
                price = round(p.list_price * idx * rng.uniform(0.98, 1.02), 2)
                cost = round(p.unit_cost * idx * rng.uniform(0.99, 1.01), 2)
                if is_vehicle:
                    pct = rng.choice([0, 0.01, 0.02, 0.03], p=[0.5, 0.2, 0.2, 0.1])
                else:
                    pct = rng.choice([0, 0.05, 0.10, 0.15], p=[0.75, 0.12, 0.09, 0.04])
                rows.append(dict(sale_line_id=f"SL{line_seq:07d}", invoice_number=invoice, sale_datetime=dt,
                                 customer_id=customer_id, product_id=pid, branch_id=b, employee_id=employee_id,
                                 quantity=qty, unit_price=price, unit_cost=cost,
                                 discount_amount=round(qty * price * pct, 2),
                                 sales_channel=channel, order_status=status))
                line_seq += 1
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ service
    def service_orders(self, vehicles, customers, employees) -> pd.DataFrame:
        rng = self.rng
        months = _months()
        month_w = [ref.SERVICE_SEASONALITY[m - 1] * (1 + 0.08 * _years_since_start(date(y, m, 1))) for y, m in months]
        counts = _allocate(rng, self.n["service_orders"], month_w)
        cust = customers.set_index("customer_id")
        owner_city = vehicles.customer_id.map(cust.city).map(lambda c: NEAREST_BRANCH_CITY.get(c, c)).to_numpy()
        v_reg = vehicles.registration_date.to_numpy()
        v_weight = rng.lognormal(0, 0.6, len(vehicles))
        bids = [b[0] for b in ref.BRANCHES if b[6] > 0]
        bweights = [b[6] for b in ref.BRANCHES if b[6] > 0]
        branch_city = {b[0]: b[2] for b in ref.BRANCHES}
        stypes, stype_p = list(ref.SERVICE_TYPE_WEIGHTS), list(ref.SERVICE_TYPE_WEIGHTS.values())

        headers = []
        for (y, m), cnt in zip(months, counts):
            for _ in range(cnt):
                b = _weighted_choice(rng, bids, bweights)
                headers.append((_random_datetime(rng, y, m, 8.5, 18.0), b))
        headers.sort(key=lambda h: h[0])

        rows = []
        for i, (opened, b) in enumerate(headers, start=1):
            d = opened.date()
            w = v_weight * np.where(owner_city == branch_city[b], 1.0, 0.03) * (v_reg <= d)
            v = vehicles.iloc[int(rng.choice(len(w), p=w / w.sum()))]
            stype = _weighted_choice(rng, stypes, stype_p)
            hours = ref.SERVICE_MEDIAN_HOURS[stype] * rng.lognormal(0, 0.45)
            if b == "BR04" and d >= date(2026, 1, 1):
                hours *= 1 + 1.5 * (d.month / 9)   # Batumi slowdown during 2026
            closed = opened + timedelta(hours=float(hours))
            status = "completed"
            if rng.random() < 0.04:
                status, closed = "cancelled", None
            elif closed > END_DT:
                status, closed = "in_progress", None
            odometer = int(max(500, (d.year - v.model_year + 0.5) * rng.uniform(9000, 22000)))
            rows.append(dict(service_order_id=f"SO{i:06d}", vehicle_id=v.vehicle_id, customer_id=v.customer_id,
                             branch_id=b, employee_id=self._pick_employee(employees, b, "service_advisor", d),
                             service_type=stype, opened_at=opened, closed_at=closed, order_status=status,
                             odometer_km=odometer))
        return pd.DataFrame(rows)

    def service_items(self, orders, products) -> pd.DataFrame:
        rng = self.rng
        labor_median = {"maintenance": 1.5, "repair": 3.5, "diagnostics": 1.0,
                        "tire_service": 0.8, "body_work": 9.0, "warranty": 3.0}
        by_cat = {c: products[products.category_id == c] for c in products.category_id.unique()}
        rows, seq = [], 1

        def add(order_id, item_type, product_id, desc, qty, price, cost):
            nonlocal seq
            rows.append(dict(service_item_id=f"SI{seq:07d}", service_order_id=order_id, item_type=item_type,
                             product_id=product_id, description=desc, quantity=qty,
                             unit_price=round(price, 2), unit_cost=round(cost, 2)))
            seq += 1

        for o in orders[orders.order_status != "cancelled"].itertuples():
            idx = ref.PRICE_INDEX[o.opened_at.year]
            warranty = o.service_type == "warranty"
            hours = max(0.25, round(labor_median[o.service_type] * rng.lognormal(0, 0.4) * 4) / 4)
            add(o.service_order_id, "labor", None, ref.LABOR_DESCRIPTIONS[o.service_type], hours,
                0.0 if warranty else ref.LABOR_RATE * idx, ref.LABOR_COST * idx)

            cats = ref.SERVICE_PART_CATEGORIES[o.service_type]
            if o.service_type == "maintenance":
                picks = [("CAT07", "PRD020" if rng.random() < 0.65 else "PRD021"), ("CAT06", "PRD016")]
                if rng.random() < 0.5:
                    picks.append(("CAT06", str(rng.choice(["PRD017", "PRD018"]))))
                if rng.random() < 0.2:
                    picks.append(("CAT09", "PRD029"))
            elif o.service_type == "tire_service":
                picks = [("CAT03", None)] if rng.random() < 0.6 else []
            elif not cats or (o.service_type == "body_work" and rng.random() < 0.5):
                picks = []
            else:
                picks = [(str(rng.choice(cats)), None) for _ in range(int(rng.integers(1, 3)))]

            for cat, pid in picks:
                pool = by_cat[cat]
                p = pool[pool.product_id == pid].iloc[0] if pid else pool.iloc[int(rng.integers(len(pool)))]
                qty = 1 if cat == "CAT07" else self._quantity(cat)
                price = 0.0 if warranty else p.list_price * idx * rng.uniform(0.98, 1.02)
                add(o.service_order_id, "part", p.product_id, p.product_name, qty, price, p.unit_cost * idx)
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ payments
    def payments(self, sales, orders, items, customers) -> pd.DataFrame:
        rng = self.rng
        corp = set(customers.customer_id[customers.customer_type == "corporate"])
        rows = []

        def pay(source_type, ref_id, cust, dt, amount, method, status):
            rows.append(dict(source_type=source_type, source_reference=ref_id, customer_id=cust,
                             payment_datetime=min(dt, END_DT), amount=round(float(amount), 2),
                             payment_method=method, payment_status=status, currency="GEL"))

        sales = sales.assign(net=sales.quantity * sales.unit_price - sales.discount_amount)
        invoices = sales.groupby("invoice_number").agg(
            dt=("sale_datetime", "first"), cust=("customer_id", "first"), status=("order_status", "first"),
            total=("net", "sum"), top_price=("unit_price", "max")).reset_index()
        for inv in invoices.itertuples():
            vehicle = inv.top_price > 20000
            if vehicle:
                method = str(rng.choice(["bank_transfer", "installment", "card"], p=[0.5, 0.4, 0.1]))
            elif inv.cust in corp:
                method = str(rng.choice(["bank_transfer", "card"], p=[0.7, 0.3]))
            else:
                method = str(rng.choice(["card", "cash", "bank_transfer"], p=[0.6, 0.35, 0.05]))
            t = inv.dt + timedelta(minutes=int(rng.integers(2, 20)))
            if inv.status == "cancelled":
                if rng.random() < 0.3:
                    pay("sale", inv.invoice_number, inv.cust, t, inv.total, "card", "failed")
                continue
            if rng.random() < 0.04:
                pay("sale", inv.invoice_number, inv.cust, t - timedelta(minutes=1), inv.total, "card", "failed")
            if not vehicle and rng.random() < 0.06 and inv.total > 50:
                first = round(inv.total * 0.6, 2)
                pay("sale", inv.invoice_number, inv.cust, t, first, "card", "completed")
                pay("sale", inv.invoice_number, inv.cust, t + timedelta(minutes=1), inv.total - first, "cash", "completed")
            else:
                pay("sale", inv.invoice_number, inv.cust, t, inv.total, method, "completed")
            if inv.status == "returned":
                pay("sale", inv.invoice_number, inv.cust, t + timedelta(days=int(rng.integers(3, 21))),
                    inv.total, method, "refunded")

        totals = (items.assign(v=items.quantity * items.unit_price)
                  .groupby("service_order_id").v.sum())
        for o in orders[orders.order_status == "completed"].itertuples():
            total = totals.get(o.service_order_id, 0.0)
            if total <= 0:          # fully covered by warranty
                continue
            t = o.closed_at + timedelta(minutes=int(rng.integers(5, 90)))
            method = "bank_transfer" if o.customer_id in corp else str(rng.choice(["card", "cash"], p=[0.65, 0.35]))
            if rng.random() < 0.03:
                pay("service", o.service_order_id, o.customer_id, t - timedelta(minutes=2), total, "card", "failed")
            pay("service", o.service_order_id, o.customer_id, t, total, method, "completed")

        df = pd.DataFrame(rows).sort_values("payment_datetime", kind="stable").reset_index(drop=True)
        df.insert(0, "payment_id", [f"PAY{i:07d}" for i in range(1, len(df) + 1)])
        return df

    # ------------------------------------------------------------------ feedback
    def feedback(self, sales, orders) -> tuple[pd.DataFrame, pd.DataFrame]:
        rng = self.rng
        n_total = self.n["feedback"]
        done = orders[orders.order_status == "completed"].copy()
        done["ratio"] = ((done.closed_at - done.opened_at).dt.total_seconds() / 3600
                         / done.service_type.map(ref.SERVICE_MEDIAN_HOURS))
        inv = (sales[sales.order_status == "completed"]
               .groupby("invoice_number")
               .agg(dt=("sale_datetime", "first"), customer_id=("customer_id", "first"),
                    branch_id=("branch_id", "first")).reset_index())
        n_service = min(int(n_total * 0.68), len(done))
        n_sales = min(n_total - n_service, len(inv))
        svc = done.iloc[rng.choice(len(done), n_service, replace=False)]
        sls = inv.iloc[rng.choice(len(inv), n_sales, replace=False)]

        events = [dict(kind="service", customer_id=r.customer_id, branch_id=r.branch_id,
                       service_order_id=r.service_order_id, invoice_number=None,
                       event_date=r.closed_at.date(), ratio=r.ratio) for r in svc.itertuples()]
        events += [dict(kind="sale", customer_id=r.customer_id, branch_id=r.branch_id, service_order_id=None,
                        invoice_number=r.invoice_number, event_date=r.dt.date(), ratio=None)
                   for r in sls.itertuples()]
        events.sort(key=lambda e: e["event_date"])

        rows, labels = [], []
        for i, e in enumerate(events, start=1):
            fdate = min(e["event_date"] + timedelta(days=int(rng.integers(0, 8))), ref.END_DATE)
            topic = self._feedback_topic(e)
            sentiment = self._feedback_sentiment(e, topic, fdate)
            lang = "ka" if rng.random() < 0.6 else "en"
            text = str(rng.choice(TEMPLATES[(topic, sentiment)][lang]))
            text = self._noisy(text, sentiment, lang)
            channel = (str(rng.choice(["sms_survey", "email_survey", "call_center", "website"], p=[0.5, 0.2, 0.15, 0.15]))
                       if e["kind"] == "service" else
                       str(rng.choice(["email_survey", "website", "sms_survey", "call_center"], p=[0.4, 0.3, 0.2, 0.1])))
            fid = f"FB{i:06d}"
            rows.append(dict(feedback_id=fid, customer_id=e["customer_id"], branch_id=e["branch_id"],
                             service_order_id=e["service_order_id"], invoice_number=e["invoice_number"],
                             feedback_date=fdate, channel=channel, rating=self._rating(sentiment),
                             feedback_text=text))
            labels.append(dict(feedback_id=fid, true_language=lang, true_sentiment=sentiment, true_topic=topic))
        feedback = pd.DataFrame(rows)
        feedback["rating"] = feedback["rating"].astype("Int64")
        return feedback, pd.DataFrame(labels)

    def _feedback_topic(self, e: dict) -> str:
        rng = self.rng
        if e["kind"] == "service":
            if e["ratio"] > 1.8 and rng.random() < 0.75:
                return "waiting_time"
            weights = dict(SERVICE_TOPIC_WEIGHTS)
        else:
            weights = dict(SALES_TOPIC_WEIGHTS)
            if e["branch_id"] == "BR07":
                weights["availability"] *= 4
        return _weighted_choice(rng, list(weights), list(weights.values()))

    def _feedback_sentiment(self, e: dict, topic: str, d: date) -> str:
        pos, neu, neg = BASE_SENTIMENT
        if topic == "complaint":
            return "negative"
        if topic == "other":
            return "neutral" if self.rng.random() < 0.75 else "positive"
        if topic == "waiting_time" and e["ratio"] is not None:
            if e["ratio"] > 1.8:
                pos, neu, neg = 0.03, 0.07, 0.90
            elif e["ratio"] < 0.7:
                pos, neu, neg = 0.75, 0.20, 0.05
        if topic == "price" and d.year == 2026:
            pos, neg = pos - 0.25, neg + 0.25
        if topic == "service_quality" and e["branch_id"] == "BR01":
            neg = max(0.08, 0.35 - 0.10 * _years_since_start(d))
            pos = 0.80 - neg
        if topic == "availability" and e["branch_id"] == "BR07":
            pos, neu, neg = 0.10, 0.15, 0.75
        if topic == "staff" and e["branch_id"] == "BR06":
            pos, neu, neg = 0.35, 0.20, 0.45
        return _weighted_choice(self.rng, ["positive", "neutral", "negative"], [pos, neu, neg])

    def _rating(self, sentiment: str):
        rng = self.rng
        if rng.random() < 0.15:
            return None                                   # rating not given
        if rng.random() < 0.03:                           # rating contradicts the text
            sentiment = {"positive": "negative", "negative": "positive", "neutral": "neutral"}[sentiment]
        if sentiment == "positive":
            return int(rng.choice([4, 5], p=[0.35, 0.65]))
        if sentiment == "neutral":
            return int(rng.choice([2, 3, 4], p=[0.2, 0.6, 0.2]))
        return int(rng.choice([1, 2, 3], p=[0.55, 0.35, 0.10]))

    def _noisy(self, text: str, sentiment: str, lang: str) -> str:
        r = self.rng.random()
        if lang == "en" and r < 0.08:
            return text.lower()
        if r < 0.12:
            return text.rstrip(".") + "!!"
        if sentiment == "positive" and r < 0.15:
            return text + " 👍"
        return text

    # ------------------------------------------------------------------ orchestration
    def run(self) -> dict[str, pd.DataFrame]:
        branches = self.branches()
        categories = self.categories()
        products = self.products()
        products["popularity"] = [p[6] for p in ref.PRODUCTS]
        employees = self.employees(branches)
        customers = self.customers()
        vehicles = self.vehicles(customers)
        sales = self.sales(customers, employees, products)
        orders = self.service_orders(vehicles, customers, employees)
        items = self.service_items(orders, products)
        payments = self.payments(sales, orders, items, customers)
        feedback, labels = self.feedback(sales, orders)

        # Loyalty tier reflects lifetime completed spend (current snapshot attribute).
        spend = (sales[sales.order_status == "completed"]
                 .assign(v=lambda s: s.quantity * s.unit_price - s.discount_amount)
                 .groupby("customer_id").v.sum())
        s = customers.customer_id.map(spend).fillna(0)
        customers["loyalty_tier"] = np.select(
            [s >= 50000, s >= 6000, s >= 1500], ["platinum", "gold", "silver"], "standard")

        return {
            "branches": branches,
            "product_categories": categories,
            "products": products.drop(columns="popularity"),
            "employees": employees,
            "customers": customers,
            "vehicles": vehicles,
            "sales": sales,
            "service_orders": orders,
            "service_items": items,
            "payments": payments,
            "customer_feedback": feedback,
            "_feedback_labels": labels,
        }


def generate_clean_datasets(seed: int = 42, scale: float = 1.0) -> dict[str, pd.DataFrame]:
    """Return clean datasets keyed by table name (plus '_feedback_labels' ground truth)."""
    return _Generator(seed, scale).run()
