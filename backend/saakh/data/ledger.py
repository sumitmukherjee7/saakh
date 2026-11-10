"""Synthetic bank-statement generator (SIMULATED Account Aggregator FIP).

Produces ReBIT-style DEPOSIT FI data, account summary + transactions with
realistic Indian narrations (UPI/NEFT/IMPS/ACH/BBPS/ATM), for demo personas.
Everything here is synthetic and clearly labelled as such in the product.
"""
from __future__ import annotations

import calendar
import random
from datetime import date, datetime, timedelta
from typing import Any

START = date(2025, 11, 1)
MONTHS = 12

FIRST = {
    "north": ["Priya", "Neha", "Pooja", "Anita", "Rekha", "Suman", "Kavita", "Meena", "Rahul", "Amit", "Sanjay", "Vikas",
              "Ravi", "Deepak", "Manoj", "Rajesh", "Sunil", "Asha", "Geeta", "Shabnam", "Farzana", "Arif", "Salman", "Nisha"],
    "west": ["Sachin", "Ganesh", "Prakash", "Mahesh", "Santosh", "Sunita", "Vaishali", "Swati", "Rohit", "Nitin", "Amol",
             "Pravin", "Snehal", "Yogesh", "Kiran", "Ashwini"],
    "south": ["Manjunath", "Lakshmi", "Shivakumar", "Nagaraj", "Kavya", "Ramesh", "Sowmya", "Mahadevi", "Basavaraj",
              "Rekha", "Chandru", "Girish", "Shilpa", "Puttaswamy"],
    "east": ["Sunita", "Phulmani", "Sushila", "Birsa", "Somra", "Mangal", "Karma", "Budhni", "Sanjay", "Rita", "Anil",
             "Jitendra", "Sarita", "Babita"],
    "central": ["Imran", "Ayaan", "Sajid", "Rizwan", "Ankit", "Rohit", "Pooja", "Shalini", "Arjun", "Vivek", "Sonu",
                "Faizan", "Neeraj", "Aakash"],
}
LAST = {
    "north": ["Verma", "Yadav", "Singh", "Gupta", "Maurya", "Kumar", "Devi", "Khan", "Ansari", "Pandey", "Mishra", "Rawat"],
    "west": ["Patil", "Pawar", "Jadhav", "Shinde", "Kulkarni", "Deshmukh", "More", "Gaikwad", "Bhosale", "Kale"],
    "south": ["Gowda", "Shetty", "Naik", "Reddy", "Hegde", "Kumar", "Swamy", "Rao", "Murthy", "Prasad"],
    "east": ["Munda", "Oraon", "Toppo", "Kujur", "Mahto", "Soren", "Lakra", "Tirkey", "Ekka", "Kumari"],
    "central": ["Shaikh", "Khan", "Sharma", "Rajput", "Tiwari", "Malviya", "Qureshi", "Saxena", "Jain", "Verma"],
}
BANKS = ["SBIN", "PUNB", "BARB", "UBIN", "CNRB", "HDFC", "ICIC", "BKID", "IOBA", "KKBK", "UTIB"]
VPA_SUFFIX = ["okaxis", "oksbi", "okhdfcbank", "okicici", "ybl", "paytm", "ibl", "axl"]


def month_starts() -> list[date]:
    out = []
    y, m = START.year, START.month
    for _ in range(MONTHS):
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


class _Gen:
    def __init__(self, seed: int, region: str):
        self.r = random.Random(seed)
        self.region = region
        self._ref = 500000000000 + self.r.randint(0, 10 ** 9)

    def ref(self) -> str:
        self._ref += self.r.randint(1, 99999)
        return str(self._ref)

    def person(self) -> str:
        return f"{self.r.choice(FIRST[self.region])} {self.r.choice(LAST[self.region])}".upper()

    def vpa(self, name: str) -> str:
        base = name.split()[0].lower() + str(self.r.randint(1, 999))
        return f"{base}@{self.r.choice(VPA_SUFFIX)}"

    def upi(self, direction: str, name: str, vpa: str | None = None, note: str = "UPI") -> str:
        vpa = vpa or self.vpa(name)
        return f"UPI/{direction}/{self.ref()}/{name}/{self.r.choice(BANKS)}/{vpa}/{note}"

    def when(self, d: date, hours=(8, 21)) -> datetime:
        return datetime(d.year, d.month, d.day, self.r.randint(*hours), self.r.randint(0, 59), self.r.randint(0, 59))


def _days(ms: date) -> list[date]:
    n = calendar.monthrange(ms.year, ms.month)[1]
    return [ms + timedelta(days=i) for i in range(n)]


def generate(cfg: dict[str, Any], seed: int) -> dict:
    """cfg keys: holder, region, opening, streams (inflows), outflow (dict)."""
    g = _Gen(seed, cfg["region"])
    r = g.r
    season = cfg["seasonality"]  # 12 multipliers Jan..Dec
    trend = cfg.get("trend", 0.0)  # monthly growth
    cands: list[dict] = []
    monthly_in: dict[str, float] = {}

    customers = [(g.person(), None) for _ in range(cfg.get("customer_pool", 150))]
    customers = [(n, g.vpa(n)) for n, _ in customers]
    regulars = customers[: max(5, len(customers) // 6)]

    for mi, ms in enumerate(month_starts()):
        key = ms.strftime("%Y-%m")
        mult = season[ms.month - 1] * (1 + trend) ** mi * r.uniform(0.93, 1.07)
        for d in _days(ms):
            wd = d.weekday()
            for st in cfg["streams"]:
                k = st["kind"]
                if k == "upi_retail":
                    lam = st["per_day"] * mult * (st.get("weekend", 1.25) if wd >= 5 else 1.0)
                    n = _poisson(r, lam)
                    for _ in range(n):
                        name, vpa = r.choice(regulars) if r.random() < 0.45 else r.choice(customers)
                        amt = round(r.lognormvariate(st["ln_mu"], st["ln_sigma"]) / 10) * 10
                        amt = max(st.get("min", 20), min(amt, st.get("max", 20000)))
                        cands.append(dict(t=g.when(d), type="CREDIT", mode="UPI", amount=amt,
                                          narration=g.upi("CR", name, vpa, r.choice(["Payment", "UPI", "Pay", "stitching", "order"] if st.get("tailor") else ["Payment", "UPI", "Pay"])),
                                          cat="sales"))
                        monthly_in[key] = monthly_in.get(key, 0) + amt
                elif k == "b2b":
                    if r.random() < st["p_per_day"] * mult:
                        buyer = r.choice(st["buyers"])
                        amt = round(r.lognormvariate(st["ln_mu"], st["ln_sigma"]) / 100) * 100
                        mode = r.choice(["NEFT", "NEFT", "IMPS", "RTGS"]) if amt >= 200000 else r.choice(["NEFT", "IMPS"])
                        cands.append(dict(t=g.when(d, (10, 17)), type="CREDIT", mode=mode if mode != "RTGS" else "NEFT",
                                          amount=amt, narration=f"{mode}/CR/{g.ref()}/{buyer}/INV PAYMENT", cat="sales"))
                        monthly_in[key] = monthly_in.get(key, 0) + amt
                elif k == "coop":
                    if d.day in st["days"]:
                        amt = round(st["base"] * mult * r.uniform(0.9, 1.1))
                        cands.append(dict(t=g.when(d, (11, 16)), type="CREDIT", mode="NEFT", amount=amt,
                                          narration=f"NEFT/CR/{g.ref()}/{st['payer']}/MILK BILL", cat="sales"))
                        monthly_in[key] = monthly_in.get(key, 0) + amt
                elif k == "cash_dep":
                    if wd == st.get("weekday", 0) and r.random() < st.get("p", 0.8):
                        amt = round(st["base"] * mult * r.uniform(0.6, 1.4) / 100) * 100
                        cands.append(dict(t=g.when(d, (11, 15)), type="CREDIT", mode="CASH", amount=amt,
                                          narration=f"CASH DEP/{cfg['branch']}", cat="sales"))
                        monthly_in[key] = monthly_in.get(key, 0) + amt
            for ev in cfg.get("one_off_in", []):
                if ev["date"] == d.isoformat():
                    cands.append(dict(t=g.when(d, (11, 15)), type="CREDIT", mode="NEFT", amount=ev["amount"],
                                      narration=f"NEFT/CR/{g.ref()}/{ev['payer']}", cat="other"))

    # ---- outflows, driven by realised monthly inflow ----
    out = cfg["outflow"]
    suppliers = out.get("suppliers", [])
    workers = [g.person() for _ in range(out.get("workers", 0))]
    lender_name = out.get("moneylender")
    ml_vpa = g.vpa(lender_name) if lender_name else None
    for mi, ms in enumerate(month_starts()):
        key = ms.strftime("%Y-%m")
        inflow = monthly_in.get(key, 0)
        days = _days(ms)
        # input purchases (2–6 per month) proportional to inflow
        if suppliers:
            total = inflow * out["input_ratio"] * r.uniform(0.9, 1.1)
            k = r.randint(3, 6)
            w = [r.random() + 0.3 for _ in range(k)]
            for share in w:
                amt = round(total * share / sum(w) / 10) * 10
                sup = r.choice(suppliers)
                d = r.choice(days)
                if sup.get("mode") == "UPI":
                    nar = g.upi("DR", sup["name"], sup.get("vpa"), "purchase")
                    mode = "UPI"
                else:
                    nar = f"IMPS/P2A/{g.ref()}/{sup['name']}/purchase"
                    mode = "IMPS"
                cands.append(dict(t=g.when(d), type="DEBIT", mode=mode, amount=amt, narration=nar, cat="inputs"))
        for fx in out.get("fixed", []):
            d = days[min(fx["day"], len(days)) - 1]
            amt = round(fx["amount"] * r.uniform(*fx.get("jitter", (1, 1))))
            if fx["kind"] == "rent":
                nar = g.upi("DR", fx["payee"], None, "shop rent")
                mode = "UPI"
            elif fx["kind"] == "electricity":
                nar = f"BBPS/DR/{g.ref()}/{fx['payee']} ELECTRICITY BILL"
                mode = "OTHERS"
            elif fx["kind"] == "mobile":
                nar = f"UPI/DR/{g.ref()}/{fx['payee']}/RECHARGE"
                mode = "UPI"
            elif fx["kind"] == "emi":
                nar = f"ACH/DR/{fx['payee']}/EMI {g.ref()[-6:]}"
                mode = "ACH"
            elif fx["kind"] == "shg_saving":
                nar = g.upi("DR", fx["payee"], None, "SHG saving")
                mode = "UPI"
            else:
                nar = f"{fx['payee']}"
                mode = "OTHERS"
            cands.append(dict(t=g.when(d, (9, 12)), type="DEBIT", mode=mode, amount=amt, narration=nar, cat=fx["kind"],
                              essential=fx["kind"] == "emi"))
        for wk in workers:
            for d in days:
                if d.weekday() == 5:
                    amt = round(out["weekly_wage"] * r.uniform(0.9, 1.1) / 10) * 10
                    cands.append(dict(t=g.when(d, (18, 20)), type="DEBIT", mode="UPI", amount=amt,
                                      narration=g.upi("DR", wk, None, "wages"), cat="wages"))
        hh = out["household"] * r.uniform(0.85, 1.15)
        for _ in range(r.randint(8, 14)):
            d = r.choice(days)
            amt = round(hh / 11 * r.uniform(0.4, 1.8) / 10) * 10
            payee = r.choice(["SHREE KIRANA STORE", "APNA PHARMACY", "SARASWATI SCHOOL FEES", "RELIANCE SMART",
                              "LOCAL VEGETABLE", "JIO RECHARGE", "DMART", "MEDICAL STORE"])
            cands.append(dict(t=g.when(d), type="DEBIT", mode="UPI", amount=amt, narration=g.upi("DR", payee, None, "Payment"),
                              cat="household", discretionary=True))
        for _ in range(out.get("atm_per_month", 2)):
            d = r.choice(days)
            amt = r.choice([1000, 2000, 2000, 3000, 5000])
            cands.append(dict(t=g.when(d), type="DEBIT", mode="ATM", amount=amt,
                              narration=f"ATM WDL/{cfg['branch'][:12]}/{g.ref()[-6:]}", cat="atm", discretionary=True))
        if lender_name:
            for d in days:
                if d.weekday() == out.get("ml_weekday", 0):
                    cands.append(dict(t=g.when(d, (7, 9)), type="DEBIT", mode="UPI", amount=out["ml_amount"],
                                      narration=g.upi("DR", lender_name, ml_vpa, "UPI"), cat="informal"))

    # ---- post with running balance; EMI bounces when funds are short ----
    cands.sort(key=lambda c: c["t"])
    bal = float(cfg["opening"])
    txns = []
    bounce_lenders = {tuple(x) for x in cfg.get("force_bounce", [])}
    sweep_target = cfg.get("sweep_target")  # owner drawings keep balances realistic
    cur_month = None
    for c in cands:
        mk = c["t"].strftime("%Y-%m")
        if sweep_target and cur_month and mk != cur_month and bal > sweep_target:
            amt = round((bal - sweep_target) * r.uniform(0.75, 0.95) / 100) * 100
            if amt > 0:
                bal -= amt
                t0 = c["t"].replace(hour=7, minute=5)
                payee = r.choice(cfg.get("drawings_payees", ["SELF TRANSFER", "FAMILY EXPENSES"]))
                txns.append(_txn(t0, "DEBIT", "IMPS", amt, bal, f"IMPS/P2A/{g.ref()}/{payee}/drawings", g.ref()))
        cur_month = mk
        if c["type"] == "DEBIT":
            forced = c.get("cat") == "emi" and (c["t"].strftime("%Y-%m"), c["narration"].split("/")[2]) in bounce_lenders
            if bal - c["amount"] < cfg.get("min_balance", 200) or forced:
                if c.get("cat") == "emi":
                    lender = c["narration"].split("/")[2]
                    for nar, amt in ((f"ACH/DR RTN/{lender}/INSUFFICIENT FUNDS", 0.0), ("ACH RTN CHGS INCL GST", 590.0)):
                        bal -= amt
                        txns.append(_txn(c["t"], "DEBIT", "ACH" if amt == 0 else "OTHERS", amt or c["amount"], bal, nar,
                                         g.ref(), zero=amt == 0))
                    continue
                if c.get("discretionary") or c.get("cat") in ("inputs", "wages", "informal", "household"):
                    continue
            bal -= c["amount"]
        else:
            bal += c["amount"]
        txns.append(_txn(c["t"], c["type"], c["mode"], c["amount"], bal, c["narration"], g.ref()))
    end = month_starts()[-1]
    last_day = date(end.year, end.month, calendar.monthrange(end.year, end.month)[1])
    return {
        "simulated": True,
        "fiType": "DEPOSIT",
        "account": {
            "type": "deposit", "maskedAccNumber": "XXXXXXXX" + str(seed % 10000).zfill(4),
            "profile": {"holders": {"type": "SINGLE", "holder": [{"name": cfg["holder"], "nominee": "REGISTERED",
                                                                 "ckycCompliance": True}]}},
            "summary": {"currentBalance": round(bal, 2), "currency": "INR", "branch": cfg["branch"],
                        "type": cfg.get("acc_type", "SAVINGS"), "status": "ACTIVE", "ifscCode": cfg.get("ifsc", "SBIN0001234")},
            "transactions": {"startDate": START.isoformat(), "endDate": last_day.isoformat(), "transaction": txns},
        },
    }


def _txn(t: datetime, typ: str, mode: str, amount: float, bal: float, nar: str, ref: str, zero: bool = False) -> dict:
    return {
        "txnId": f"S{ref}", "type": typ, "mode": mode, "amount": round(float(amount), 2),
        "currentBalance": round(bal, 2), "transactionTimestamp": t.isoformat() + "+05:30",
        "valueDate": t.date().isoformat(), "narration": nar, "reference": ref,
        **({"returned": True} if zero else {}),
    }


def _poisson(r: random.Random, lam: float) -> int:
    # Knuth; fine for small lambda
    import math
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(r.gauss(lam, math.sqrt(lam)))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= r.random()
        if p <= L:
            return k - 1
