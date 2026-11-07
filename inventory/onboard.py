"""Client data onboarding: take a new retailer's sales export, map it, check every row, load only clean data.

    python -m inventory.onboard examples/client/sales_export.csv
    python -m inventory.onboard export.csv --date-format "%m/%d/%Y" --mapping mapping.json --out data/onboarding/acme

Steps:
1. Map the client's column names to the platform's fields by name. A heading that matches no field, or
   matches two, is left for the analyst to set in a mapping file. Nothing is guessed from the data.
2. Check every row. Rows with a blocking problem are rejected with their line number and the reason.
3. Write the clean rows in the platform's sales format (the format inventory.prepare reads), the
   rejected rows, the mapping used (to reuse on next month's file), and a report with a load decision.

No AI is used. The decision is "Ready to load" only when every required field is mapped and rejected
rows are at or below the agreed share (1% by default).
"""
import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "onboarding"
DEFAULT_DATE_FORMAT = "%d/%m/%Y %H:%M"
MAX_REJECT_SHARE = 0.01

# Platform field -> (column name in the platform's sales format, required, headings that mean it)
FIELDS = {
    "invoice": ("Invoice", True, ["invoice", "invoice no", "invoice number", "order", "order no", "order number",
                                 "order id", "receipt", "receipt no", "transaction id"]),
    "invoice_date": ("InvoiceDate", True, ["invoice date", "order date", "date", "sale date", "transaction date",
                                           "order datetime"]),
    "product_code": ("StockCode", True, ["stock code", "stockcode", "sku", "product code", "item code", "product id",
                                         "item no", "item number"]),
    "description": ("Description", False, ["description", "item name", "product name", "item description",
                                           "product description"]),
    "quantity": ("Quantity", True, ["quantity", "qty", "units", "qty sold", "units sold"]),
    "unit_price": ("Price", True, ["price", "unit price", "unit price gbp", "price each", "selling price",
                                   "unit price usd", "unit price eur"]),
    "customer_id": ("Customer ID", False, ["customer id", "customer", "cust", "cust no", "customer no",
                                           "account", "account no"]),
    "country": ("Country", False, ["country", "ship country", "shipping country", "delivery country"]),
}
PLATFORM_COLUMNS = [FIELDS[f][0] for f in FIELDS]
BLOCKING, WARNING = "blocking", "warning"


def normalise(heading):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", heading.lower()).split())


def suggest_mapping(headers):
    """Platform field -> client heading, by name only. Ambiguous or unknown headings are left out."""
    matches = {f: [h for h in headers if normalise(h) in FIELDS[f][2]] for f in FIELDS}
    mapping = {f: hs[0] for f, hs in matches.items() if len(hs) == 1}
    used = Counter(mapping.values())
    return {f: h for f, h in mapping.items() if used[h] == 1}      # one heading cannot feed two fields


def parse_date(text, fmt):
    for f in (fmt, fmt.split(" ")[0]) if " " in fmt else (fmt,):
        try:
            return datetime.strptime(text, f)
        except ValueError:
            continue
    return None


def check_rows(rows, header, mapping, date_format):
    """Check each data row. Returns (clean rows in platform format, findings)."""
    col = {f: header.index(h) for f, h in mapping.items()}
    clean, findings, seen = [], [], {}
    for line, row in rows:
        problems = []

        def add(field, severity, value, message):
            problems.append({"line": line, "field": field, "client_column": mapping.get(field, ""),
                             "severity": severity, "value": value, "problem": message})

        if len(row) != len(header):
            add("(row)", BLOCKING, "", f"has {len(row)} columns; the header has {len(header)}")
            findings += problems
            continue
        get = {f: row[i].strip() for f, i in col.items()}
        for f, (_, required, _) in FIELDS.items():
            if required and f in get and get[f] == "":
                add(f, BLOCKING, "", "missing")
        when = None
        if get.get("invoice_date"):
            when = parse_date(get["invoice_date"], date_format)
            if when is None:
                add("invoice_date", BLOCKING, get["invoice_date"], f"not a valid date in the agreed format {date_format}")
        qty = None
        if get.get("quantity"):
            try:
                qty_f = float(get["quantity"].replace(",", ""))
                if not qty_f.is_integer():
                    add("quantity", BLOCKING, get["quantity"], "not a whole number of units")
                elif qty_f == 0:
                    add("quantity", BLOCKING, get["quantity"], "zero units")
                else:
                    qty = int(qty_f)
            except ValueError:
                add("quantity", BLOCKING, get["quantity"], "not a number")
        price = None
        if get.get("unit_price"):
            try:
                price = float(get["unit_price"].replace(",", "").lstrip("£$€"))
                if price < 0:
                    add("unit_price", BLOCKING, get["unit_price"], "negative price")
                    price = None
                elif price == 0:
                    add("unit_price", WARNING, get["unit_price"], "zero price (free item); loaded, excluded from sales")
            except ValueError:
                add("unit_price", BLOCKING, get["unit_price"], "not a number")
        code = get.get("product_code", "")
        if code and " " in code:
            add("product_code", BLOCKING, code, "contains a space")
        if qty is not None and qty < 0:
            add("quantity", WARNING, get["quantity"], "negative quantity: loaded as a return (cancellation line)")
        key = tuple(row)
        if key in seen:
            add("(row)", WARNING, f"same as line {seen[key]}", "exact copy of an earlier line (possible double export)")
        else:
            seen[key] = line
        findings += problems
        if any(p["severity"] == BLOCKING for p in problems):
            continue
        invoice = get["invoice"]
        clean.append({
            "Invoice": ("C" + invoice) if qty < 0 and not invoice.startswith("C") else invoice,
            "StockCode": code.upper(),
            "Description": get.get("description", ""),
            "Quantity": qty,
            "InvoiceDate": when.strftime("%Y-%m-%d %H:%M:%S"),
            "Price": round(price, 4),
            "Customer ID": get.get("customer_id", ""),
            "Country": get.get("country", ""),
        })
    return clean, findings


def onboard(raw_bytes, mapping=None, date_format=DEFAULT_DATE_FORMAT, max_reject_share=MAX_REJECT_SHARE):
    """Run the whole check on one export. Returns a result dict; writes nothing."""
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        raise ValueError("The file is empty.") from None
    rows = [(i, r) for i, r in enumerate(reader, start=2) if any(c.strip() for c in r)]
    suggested = suggest_mapping(header)
    chosen = {**suggested, **(mapping or {})}
    unknown = {f: h for f, h in chosen.items() if f not in FIELDS or (h and h not in header)}
    if unknown:
        raise ValueError("Mapping refers to unknown fields or columns: " +
                         ", ".join(f"{f} -> {h!r}" for f, h in unknown.items()))
    chosen = {f: h for f, h in chosen.items() if h}
    missing_required = [f for f, (_, req, _) in FIELDS.items() if req and f not in chosen]
    unmapped_columns = [h for h in header if h not in chosen.values()]
    if missing_required:
        clean, findings = [], []
    else:
        clean, findings = check_rows(rows, header, chosen, date_format)
    rejected_lines = sorted({f["line"] for f in findings if f["severity"] == BLOCKING})
    share = len(rejected_lines) / len(rows) if rows else 0
    reasons = []
    if missing_required:
        reasons.append("Required fields are not mapped: " + ", ".join(missing_required) +
                       ". Set them in a mapping file and run again.")
    if not rows:
        reasons.append("The file has no data rows.")
    if rows and not missing_required and share > max_reject_share:
        reasons.append(f"{len(rejected_lines)} of {len(rows)} rows ({share:.1%}) were rejected, above the agreed "
                       f"{max_reject_share:.0%}. Send the rejected rows back to the client to fix and resend.")
    by_problem = Counter((f["field"], f["client_column"], f["severity"], f["problem"].split(";")[0].split(" in the")[0])
                         for f in findings)
    return {
        "decision": "Ready to load" if not reasons else "Not ready",
        "reasons": reasons,
        "rows": len(rows),
        "loaded": len(clean),
        "rejected": len(rejected_lines),
        "reject_share": round(share, 4),
        "max_reject_share": max_reject_share,
        "warnings": sum(f["severity"] == WARNING for f in findings),
        "returns": sum(1 for c in clean if c["Quantity"] < 0),
        "mapping": chosen,
        "suggested_by_name": suggested,
        "missing_required": missing_required,
        "unmapped_columns": unmapped_columns,
        "date_format": date_format,
        "problems": [{"field": k[0], "client_column": k[1], "severity": k[2], "problem": k[3], "rows": n}
                     for k, n in sorted(by_problem.items(), key=lambda kv: (kv[0][2] != BLOCKING, -kv[1]))],
        "clean": clean,
        "findings": findings,
    }


def report_markdown(result, source):
    r = result
    lines = ["# Client data onboarding report", "", f"File: `{source}`. Date format agreed with the client: "
             f"`{r['date_format']}`.", "", f"**Decision: {r['decision']}**", ""]
    lines += [f"- {reason}" for reason in r["reasons"]] or [
        f"Every required field is mapped and {r['rejected']} of {r['rows']} rows ({r['reject_share']:.1%}) were "
        f"rejected, within the agreed {r['max_reject_share']:.0%}."]
    lines += ["", "| Rows in file | Loaded | Rejected | Warnings (loaded) | Returns loaded as cancellations |",
              "| ---: | ---: | ---: | ---: | ---: |",
              f"| {r['rows']:,} | {r['loaded']:,} | {r['rejected']:,} | {r['warnings']:,} | {r['returns']:,} |",
              "", "## Column mapping", "", "| Platform field | Client column | Required | How |", "| --- | --- | --- | --- |"]
    for f, (_, req, _) in FIELDS.items():
        h = r["mapping"].get(f)
        how = "name match" if h and r["suggested_by_name"].get(f) == h else ("analyst" if h else "**not mapped**")
        lines.append(f"| {f} | {h or '-'} | {'yes' if req else 'no'} | {how} |")
    if r["unmapped_columns"]:
        lines += ["", "Client columns not used: " + ", ".join(f"`{h}`" for h in r["unmapped_columns"]) + "."]
    if r["problems"]:
        lines += ["", "## Problems found", "", "| Client column | Problem | Severity | Rows |", "| --- | --- | --- | ---: |"]
        lines += [f"| {p['client_column'] or p['field']} | {p['problem']} | {p['severity']} | {p['rows']} |"
                  for p in r["problems"]]
        lines += ["", "Every rejected row is listed with its line number and value in `rejected.csv`, ready to "
                      "send back to the client. Line numbers count the header as line 1."]
    lines += ["", "Rejected rows are never corrected or guessed. Loaded rows are written in the platform's sales "
                  "format (`clean.csv`), and the mapping is saved (`mapping.json`) for next month's file.", ""]
    return "\n".join(lines)


def write_outputs(result, out, source):
    out.mkdir(parents=True, exist_ok=True)
    with (out / "clean.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PLATFORM_COLUMNS)
        w.writeheader()
        w.writerows(result["clean"])
    with (out / "rejected.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["line", "client_column", "field", "value", "problem"], extrasaction="ignore")
        w.writeheader()
        w.writerows(x for x in result["findings"] if x["severity"] == BLOCKING)
    (out / "mapping.json").write_text(json.dumps({"date_format": result["date_format"], "mapping": result["mapping"]},
                                                 indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(report_markdown(result, source), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("export", type=Path, help="the client's sales export (CSV)")
    parser.add_argument("--mapping", type=Path, help="mapping.json from an earlier run, or one the analyst wrote")
    parser.add_argument("--date-format", help=f"the client's date format (default {DEFAULT_DATE_FORMAT})")
    parser.add_argument("--max-reject-share", type=float, default=MAX_REJECT_SHARE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    mapping, date_format = None, args.date_format
    if args.mapping:
        saved = json.loads(args.mapping.read_text(encoding="utf-8"))
        mapping, date_format = saved.get("mapping", saved), date_format or saved.get("date_format")
    try:
        result = onboard(args.export.read_bytes(), mapping, date_format or DEFAULT_DATE_FORMAT, args.max_reject_share)
    except ValueError as exc:
        print(exc)
        return 1
    write_outputs(result, args.out, args.export.name)
    print(f"{result['decision']}: {result['loaded']:,} of {result['rows']:,} rows loaded, {result['rejected']} rejected, "
          f"{result['warnings']} warnings.")
    for reason in result["reasons"]:
        print("  " + reason)
    print(f"Wrote clean.csv, rejected.csv, mapping.json and report.md to {args.out}")
    return 0 if result["decision"] == "Ready to load" else 2


if __name__ == "__main__":
    sys.exit(main())
