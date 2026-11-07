"""Client settings: the business assumptions behind the reorder policy, kept out of the code.

Every client sets these differently: how much a unit costs, what holding stock costs, how long each
supplier takes, which service levels to compare. They live in config/client_settings.json, are agreed
with the store manager and finance, and are checked before any run so that a typo cannot quietly
change every reorder point.

    python -m inventory.settings                          # check config/client_settings.json
    python -m inventory.settings path/to/other_client.json
"""
import json
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "config" / "client_settings.json"
MAX_LEAD_TIME = 250            # trading days; anything longer is almost certainly a typo


class SettingsError(ValueError):
    """The settings file has problems. `problems` lists every one, so the client can fix them in one pass."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("Client settings have problems:\n" + "\n".join(f"  - {p}" for p in problems))


@dataclass(frozen=True)
class Settings:
    client: str = "UK online gift retailer (UCI Online Retail II)"
    currency: str = "GBP"
    service_levels: tuple = (0.80, 0.90, 0.95, 0.98, 0.99)
    default_service_level: float = 0.95
    unit_cost_share: float = 0.60
    holding_rate_year: float = 0.25
    trading_days_year: int = 302
    order_cover_days: int = 24
    min_return_on_extra_stock: float = 0.10    # finance's hurdle: yearly net saving per unit of extra cash in stock
    lead_time_range: tuple = (5, 20)
    lead_time_overrides: dict = field(default_factory=dict)
    sign_off: dict = field(default_factory=dict)

    def lead_time(self, code):
        """The client's lead time for a product, or a stable modelled one if the client gave none."""
        if code in self.lead_time_overrides:
            return self.lead_time_overrides[code]
        low, high = self.lead_time_range
        return low + zlib.crc32(code.encode()) % (high - low + 1)

    @property
    def signed_off(self):
        return all(self.sign_off.get(k) for k in ("store_manager", "finance", "date"))


def _number(problems, data, key, low, high, integer=False, low_inclusive=True):
    v = data.get(key)
    kind = "a whole number" if integer else "a number"
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (integer and not isinstance(v, int)):
        problems.append(f"{key}: must be {kind}, got {v!r}")
        return None
    too_low = v < low if low_inclusive else v <= low
    if too_low or v > high:
        bracket = "[" if low_inclusive else "("
        problems.append(f"{key}: {v} is outside the allowed range {bracket}{low}, {high}]")
        return None
    return v


def parse(data, known_products=None):
    """Check a settings dict and return Settings, or raise SettingsError listing every problem."""
    problems = []
    if not isinstance(data, dict):
        raise SettingsError(["the file must hold one JSON object"])
    known = {"_about", "client", "currency", "service_levels", "default_service_level", "unit_cost_share",
             "holding_rate_year", "trading_days_year", "order_cover_days", "min_return_on_extra_stock",
             "lead_time_days", "sign_off"}
    problems += [f"{k}: unknown setting (check the spelling)" for k in data if k not in known]

    levels = data.get("service_levels")
    if not isinstance(levels, list) or not levels:
        problems.append("service_levels: must be a non-empty list, such as [0.90, 0.95, 0.98]")
        levels = []
    else:
        for lv in levels:
            if isinstance(lv, bool) or not isinstance(lv, (int, float)) or not 0.5 <= lv < 1:
                problems.append(f"service_levels: {lv!r} must be a fraction from 0.5 up to (not including) 1, such as 0.95")
        if len(set(levels)) != len(levels):
            problems.append("service_levels: a level is listed twice")
    default = _number(problems, data, "default_service_level", 0.5, 0.999)
    if default is not None and levels and default not in levels:
        problems.append(f"default_service_level: {default} is not one of service_levels {levels}")

    share = _number(problems, data, "unit_cost_share", 0, 1, low_inclusive=False)
    holding = _number(problems, data, "holding_rate_year", 0, 1, low_inclusive=False)
    days = _number(problems, data, "trading_days_year", 200, 366, integer=True)
    cover = _number(problems, data, "order_cover_days", 1, 120, integer=True)
    hurdle = _number(problems, {"min_return_on_extra_stock": data.get("min_return_on_extra_stock", 0.10)},
                     "min_return_on_extra_stock", 0, 1)

    lt = data.get("lead_time_days")
    rng, overrides = None, {}
    if not isinstance(lt, dict):
        problems.append("lead_time_days: must hold default_range and overrides")
    else:
        r = lt.get("default_range")
        if (not isinstance(r, list) or len(r) != 2 or any(isinstance(x, bool) or not isinstance(x, int) for x in r)
                or not 1 <= r[0] <= r[1] <= MAX_LEAD_TIME):
            problems.append(f"lead_time_days.default_range: must be [low, high] whole trading days with "
                            f"1 <= low <= high <= {MAX_LEAD_TIME}, got {r!r}")
        else:
            rng = tuple(r)
        ov = lt.get("overrides", {})
        if not isinstance(ov, dict):
            problems.append("lead_time_days.overrides: must map product codes to whole trading days")
        else:
            for code, days_ in ov.items():
                if isinstance(days_, bool) or not isinstance(days_, int) or not 1 <= days_ <= MAX_LEAD_TIME:
                    problems.append(f"lead_time_days.overrides.{code}: {days_!r} must be whole trading days from 1 to {MAX_LEAD_TIME}")
                elif known_products is not None and code not in known_products:
                    problems.append(f"lead_time_days.overrides.{code}: not one of the products being planned")
                else:
                    overrides[code] = days_

    sign = data.get("sign_off", {})
    if not isinstance(sign, dict):
        problems.append("sign_off: must hold store_manager, finance and date")
        sign = {}
    currency = data.get("currency", "GBP")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        problems.append(f"currency: must be a three-letter code such as GBP or USD, got {currency!r}")
    if problems:
        raise SettingsError(problems)
    return Settings(client=str(data.get("client", "")), currency=currency.upper(),
                    service_levels=tuple(sorted(float(x) for x in levels)), default_service_level=float(default),
                    unit_cost_share=float(share), holding_rate_year=float(holding), trading_days_year=days,
                    order_cover_days=cover, min_return_on_extra_stock=float(hurdle), lead_time_range=rng, lead_time_overrides=overrides, sign_off=dict(sign))


def load(path=SETTINGS_PATH, known_products=None):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SettingsError([f"{path}: file not found"]) from None
    except json.JSONDecodeError as exc:
        raise SettingsError([f"{path.name}: not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg})"]) from None
    return parse(data, known_products)


def describe(s):
    sym = {"GBP": "£", "USD": "$", "EUR": "€"}.get(s.currency, s.currency + " ")
    lines = [f"Client: {s.client}",
             f"  Service levels: {', '.join(f'{x:.0%}' for x in s.service_levels)} (default {s.default_service_level:.0%})",
             f"  Unit cost: {s.unit_cost_share:.0%} of median selling price",
             f"  Holding cost: {s.holding_rate_year:.0%} of stock value per year, {s.trading_days_year} trading days",
             f"  Order size: about {s.order_cover_days} trading days of demand",
             f"  Extra stock must return at least {s.min_return_on_extra_stock:.0%} a year (finance's hurdle)",
             f"  Lead times: {s.lead_time_range[0]}-{s.lead_time_range[1]} trading days modelled, "
             f"{len(s.lead_time_overrides)} set by the client",
             f"  Currency: {s.currency} ({sym.strip()})",
             "  Sign-off: " + ("complete" if s.signed_off else "NOT YET SIGNED OFF by store manager and finance")]
    return "\n".join(lines)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else SETTINGS_PATH
    import pandas as pd
    products_csv = ROOT / "data" / "processed" / "products.csv"
    known = set(pd.read_csv(products_csv, dtype={"product_code": str})["product_code"]) if products_csv.exists() else None
    try:
        s = load(path, known)
    except SettingsError as exc:
        print(exc)
        return 1
    print("Settings OK.\n" + describe(s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
