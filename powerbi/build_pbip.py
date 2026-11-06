"""Generate the Power BI project (PBIP: TMDL semantic model + PBIR report) from code.

    python powerbi/build_pbip.py

Writes powerbi/RetailInventory.pbip and its .SemanticModel and .Report folders. Open the .pbip
file in Power BI Desktop. By default the model loads the CSVs from this repo on GitHub; to load
local files instead, change the DataFolder parameter (Transform data > Manage parameters) to a
folder path ending in a backslash, e.g. C:\\Users\\you\\retail-inventory-decisions\\data\\processed\\
"""
import hashlib
import json
import shutil
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "RetailInventory"
DATA_URL = "https://raw.githubusercontent.com/rrvelmineti/retail-inventory-decisions/main/data/processed/"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
VISUAL_SCHEMA = f"{SCHEMA}/item/report/definition/visualContainer/2.2.0/schema.json"
T = "\t"


def stable_id(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "retail-inventory/" + "/".join(parts)))


def q(name):
    """Quote a TMDL object name when it contains anything but letters, digits and underscores."""
    return name if name.replace("_", "").isalnum() else "'" + name.replace("'", "''") + "'"


# ---------------------------------------------------------------- semantic model (TMDL)

# Each imported table: CSV file, columns (name, TMDL dataType, Power Query type, format), extra M steps.
CSV_TABLES = {
    "Products": ("products.csv", [
        ("product_code", "string", "type text", None),
        ("description", "string", "type text", None),
        ("median_price", "double", "type number", "£#,0.00"),
    ], []),
    "Sales": ("daily_sales.csv", [
        ("product_code", "string", "type text", None),
        ("date", "dateTime", "type date", "dd mmm yyyy"),
        ("units", "int64", "Int64.Type", "#,0"),
        ("revenue", "double", "type number", "£#,0.00"),
        ("bulk_units", "int64", "Int64.Type", "#,0"),
        ("bulk_revenue", "double", "type number", "£#,0.00"),
    ], []),
    "Policy": ("policy.csv", [
        ("product_code", "string", "type text", None),
        ("service_level", "double", "type number", "0%"),
        ("avg_daily", "double", "type number", "#,0.0"),
        ("sd_daily", "double", "type number", "#,0.0"),
        ("lead_time_days", "int64", "Int64.Type", "0"),
        ("z", "double", "type number", "0.000"),
        ("unit_cost", "double", "type number", "£#,0.00"),
        ("safety_stock", "int64", "Int64.Type", "#,0"),
        ("reorder_point", "int64", "Int64.Type", "#,0"),
        ("order_qty", "int64", "Int64.Type", "#,0"),
    ], ["level_pct"]),
    "Stock Simulation": ("simulation_daily.csv", [
        ("product_code", "string", "type text", None),
        ("service_level", "double", "type number", "0%"),
        ("date", "dateTime", "type date", "dd mmm yyyy"),
        ("demand", "int64", "Int64.Type", "#,0"),
        ("sold", "int64", "Int64.Type", "#,0"),
        ("lost", "int64", "Int64.Type", "#,0"),
        ("on_hand", "int64", "Int64.Type", "#,0"),
        ("on_order", "int64", "Int64.Type", "#,0"),
        ("ordered", "int64", "Int64.Type", "#,0"),
    ], ["level_pct"]),
    "Backtest Summary": ("simulation_summary.csv", [
        ("product_code", "string", "type text", None),
        ("service_level", "double", "type number", "0%"),
        ("days", "int64", "Int64.Type", "#,0"),
        ("demand_units", "int64", "Int64.Type", "#,0"),
        ("sold_units", "int64", "Int64.Type", "#,0"),
        ("lost_units", "int64", "Int64.Type", "#,0"),
        ("stockout_days", "int64", "Int64.Type", "#,0"),
        ("fill_rate", "double", "type number", "0.0%"),
        ("avg_on_hand", "double", "type number", "#,0"),
        ("avg_stock_value", "double", "type number", "£#,0"),
        ("holding_cost", "double", "type number", "£#,0"),
        ("lost_margin", "double", "type number", "£#,0"),
        ("orders_placed", "int64", "Int64.Type", "#,0"),
    ], ["level_pct"]),
    "Reorder Status": ("reorder_status.csv", [
        ("product_code", "string", "type text", None),
        ("date", "dateTime", "type date", "dd mmm yyyy"),
        ("on_hand", "int64", "Int64.Type", "#,0"),
        ("on_order", "int64", "Int64.Type", "#,0"),
        ("position", "int64", "Int64.Type", "#,0"),
        ("reorder_point", "int64", "Int64.Type", "#,0"),
        ("safety_stock", "int64", "Int64.Type", "#,0"),
        ("order_qty", "int64", "Int64.Type", "#,0"),
        ("below_reorder_point", "boolean", "type logical", None),
    ], ["status"]),
}
# Columns added in Power Query: integer service-level key (exact joins) and a readable status.
DERIVED = {
    "level_pct": ("int64", "0", '#"Added level key" = Table.AddColumn({prev}, "level_pct", '
                  'each Int64.From(Number.Round([service_level] * 100)), Int64.Type)', "Added level key"),
    "status": ("string", None, '#"Added status" = Table.AddColumn({prev}, "status", '
               'each if [below_reorder_point] then "Reorder now" else "OK", type text)', "Added status"),
}
DESCRIPTIONS = {
    "Products": "The 50 regularly sold products analysed, with their median selling price.",
    "Sales": "Real daily sales per product per trading day (UCI Online Retail II). Bulk orders are kept separate.",
    "Policy": "Reorder policy per product and service level, set from 2010 demand.",
    "Stock Simulation": "Day-by-day 2011 backtest of each policy on real demand. Stock levels are simulated.",
    "Backtest Summary": "2011 backtest totals per product and service level.",
    "Reorder Status": "Position of each product on 9 December 2011 at the 95% service level.",
    "Calendar": "One row per calendar day, December 2009 to December 2011.",
    "Service Level": "Target service levels compared in the backtest.",
    "Key Measures": "All report measures.",
}

MEASURES = [  # name, DAX, format, description
    ("Units Sold", "SUM ( Sales[units] ) + SUM ( Sales[bulk_units] )", "#,0",
     "All units sold, regular plus bulk orders."),
    ("Revenue", "SUM ( Sales[revenue] ) + SUM ( Sales[bulk_revenue] )", "£#,0",
     "All sales revenue in GBP, regular plus bulk orders."),
    ("Products Tracked", "DISTINCTCOUNT ( Products[product_code] )", "#,0",
     "Number of products in the analysis."),
    ("Stockout Days", "SUM ( 'Backtest Summary'[stockout_days] )", "#,0",
     "Product-days in the 2011 backtest when demand could not be fully met."),
    ("Lost Units", "SUM ( 'Backtest Summary'[lost_units] )", "#,0",
     "Units of demand lost to stockouts in the 2011 backtest."),
    ("Fill Rate", "DIVIDE ( SUM ( 'Backtest Summary'[sold_units] ), SUM ( 'Backtest Summary'[demand_units] ) )",
     "0.0%", "Share of 2011 demand served from stock."),
    ("Holding Cost", "SUM ( 'Backtest Summary'[holding_cost] )", "£#,0",
     "Cost of holding stock during 2011, at 25% of stock value per year."),
    ("Lost Margin", "SUM ( 'Backtest Summary'[lost_margin] )", "£#,0",
     "Margin lost on units that could not be sold because of stockouts."),
    ("Total Cost", "[Holding Cost] + [Lost Margin]", "£#,0",
     "Holding cost plus lost margin: the number to minimise."),
    ("Avg Stock Value", "SUM ( 'Backtest Summary'[avg_stock_value] )", "£#,0",
     "Average value of stock on hand during 2011, at unit cost."),
    ("Products Below Reorder Point",
     "CALCULATE ( COUNTROWS ( 'Reorder Status' ), 'Reorder Status'[status] = \"Reorder now\" ) + 0", "#,0",
     "Products at or below their reorder point on 9 December 2011 (95% service level)."),
    ("Shortfall Units",
     "SUMX ( 'Reorder Status', MAX ( 0, 'Reorder Status'[reorder_point] - 'Reorder Status'[on_hand] ) )", "#,0",
     "Units by which stock on hand is below the reorder point, summed over products."),
    ("On Hand", "SUM ( 'Stock Simulation'[on_hand] )", "#,0",
     "Simulated stock on hand at the end of each day."),
    ("Reorder Point", "IF ( NOT ISBLANK ( [On Hand] ), SUM ( Policy[reorder_point] ) )", "#,0",
     "Reorder point of the selected product and service level, shown on days with simulated stock."),
    ("Lost Sales Units", "SUM ( 'Stock Simulation'[lost] )", "#,0",
     "Units of demand lost on each day of the backtest."),
]
MEASURE_TABLE = "Key Measures"

RELATIONSHIPS = [  # many side -> one side
    ("Sales", "product_code", "Products", "product_code"),
    ("Sales", "date", "Calendar", "Date"),
    ("Policy", "product_code", "Products", "product_code"),
    ("Policy", "level_pct", "Service Level", "level_pct"),
    ("Stock Simulation", "product_code", "Products", "product_code"),
    ("Stock Simulation", "date", "Calendar", "Date"),
    ("Stock Simulation", "level_pct", "Service Level", "level_pct"),
    ("Backtest Summary", "product_code", "Products", "product_code"),
    ("Backtest Summary", "level_pct", "Service Level", "level_pct"),
    ("Reorder Status", "product_code", "Products", "product_code"),
]


def describe(text, indent):
    return f"{indent}/// {text}\n"


def column_block(name, data_type, fmt=None, source=None, extra=(), indent=T):
    lines = [f"{indent}column {q(name)}", f"{indent}{T}dataType: {data_type}"]
    if fmt:
        lines.append(f"{indent}{T}formatString: {fmt}")
    lines += [f"{indent}{T}{x}" for x in extra]
    lines.append(f"{indent}{T}summarizeBy: none")
    lines.append(f"{indent}{T}sourceColumn: {source or name}")
    if data_type == "dateTime":
        lines += ["", f"{indent}{T}annotation UnderlyingDateTimeDataType = Date"]
    return "\n".join(lines) + "\n\n"


def m_partition(table, file, columns, derived):
    types = ", ".join(f'{{"{c}", {pq}}}' for c, _, pq, _ in columns)
    steps = [
        f'Raw = if Text.StartsWith(DataFolder, "http") then Web.Contents(DataFolder & "{file}") '
        f'else File.Contents(DataFolder & "{file}"),',
        'Source = Csv.Document(Raw, [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        '#"Promoted headers" = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),',
        f'#"Changed types" = Table.TransformColumnTypes(#"Promoted headers", {{{types}}}, "en-US")',
    ]
    last = "Changed types"
    for d in derived:
        steps[-1] += ","
        steps.append(DERIVED[d][2].format(prev=f'#"{last}"'))
        last = DERIVED[d][3]
    body = [f"{T*4}let"] + [f"{T*4}    {s}" for s in steps] + [f"{T*4}in", f'{T*4}    #"{last}"']
    return f"{T}partition {q(table)} = m\n{T*2}mode: import\n{T*2}source =\n" + "\n".join(body) + "\n\n"


def calc_partition(table, dax_lines):
    body = "\n".join(f"{T*4}{line}" for line in dax_lines)
    return f"{T}partition {q(table)} = calculated\n{T*2}mode: import\n{T*2}source = ```\n{body}\n{T*4}```\n\n"


def imported_table(name):
    file, columns, derived = CSV_TABLES[name]
    out = describe(DESCRIPTIONS[name], "") + f"table {q(name)}\n\n"
    for c, dt, _, fmt in columns:
        extra = ["isKey"] if (name == "Products" and c == "product_code") else []
        if c == "product_code" and name != "Products":
            extra.append("isHidden")
        out += column_block(c, dt, fmt, extra=extra)
    for d in derived:
        dt, fmt = DERIVED[d][:2]
        out += column_block(d, dt, fmt, extra=["isHidden"] if d == "level_pct" else [])
    out += m_partition(name, file, columns, derived)
    out += f"{T}annotation PBI_ResultType = Table\n"
    return out


def calendar_table():
    out = describe(DESCRIPTIONS["Calendar"], "") + "table Calendar\n" + f"{T}dataCategory: Time\n\n"
    out += column_block("Date", "dateTime", "dd mmm yyyy", "[Date]", ["isKey", "isNameInferred"])
    out += column_block("Month", "string", None, "[Month]", ["isNameInferred"])
    out += column_block("Year", "int64", "0", "[Year]", ["isNameInferred"])
    out += column_block("Month Start", "dateTime", "mmm yyyy", "[Month Start]", ["isNameInferred"])
    out += calc_partition("Calendar", [
        "ADDCOLUMNS (",
        "    CALENDAR ( DATE ( 2009, 12, 1 ), DATE ( 2011, 12, 31 ) ),",
        '    "Month", FORMAT ( [Date], "YYYY-MM" ),',
        '    "Year", YEAR ( [Date] ),',
        '    "Month Start", DATE ( YEAR ( [Date] ), MONTH ( [Date] ), 1 )',
        ")",
    ])
    return out


def service_level_table():
    out = describe(DESCRIPTIONS["Service Level"], "") + f"table {q('Service Level')}\n\n"
    out += column_block("level_pct", "int64", "0", "[level_pct]", ["isHidden", "isNameInferred"])
    out += column_block("Service level", "string", None, "[Service level]", ["isNameInferred", "sortByColumn: level_pct"])
    rows = ", ".join(f'{{ {p}, "{p}%" }}' for p in (80, 90, 95, 98, 99))
    out += calc_partition("Service Level", [
        f'DATATABLE ( "level_pct", INTEGER, "Service level", STRING, {{ {rows} }} )'])
    return out


def measure_table():
    out = describe(DESCRIPTIONS[MEASURE_TABLE], "") + f"table {q(MEASURE_TABLE)}\n\n"
    for name, dax, fmt, desc in MEASURES:
        out += describe(desc, T) + f"{T}measure {q(name)} = {dax}\n{T*2}formatString: {fmt}\n\n"
    out += column_block("Value", "int64", "0", "[Value]", ["isHidden", "isNameInferred"])
    out += calc_partition(MEASURE_TABLE, ["{ 0 }"])
    return out


def model_files():
    tables = {name: imported_table(name) for name in CSV_TABLES}
    tables["Calendar"] = calendar_table()
    tables["Service Level"] = service_level_table()
    tables[MEASURE_TABLE] = measure_table()
    order = ["DataFolder", *CSV_TABLES]
    model = (
        "model Model\n"
        f"{T}culture: en-US\n"
        f"{T}defaultPowerBIDataSourceVersion: powerBI_V3\n"
        f"{T}discourageImplicitMeasures\n"
        f"{T}sourceQueryCulture: en-US\n"
        f"{T}dataAccessOptions\n{T*2}legacyRedirects\n{T*2}returnErrorValuesAsNull\n\n"
        f"annotation PBI_QueryOrder = {json.dumps(order)}\n\n"
        + "".join(f"ref table {q(t)}\n" for t in tables)
    )
    expressions = (
        "/// Folder or web address holding the CSV files, ending in / or a backslash.\n"
        f'expression DataFolder = "{DATA_URL}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f"\n{T}annotation PBI_ResultType = Text\n"
    )
    relationships = ""
    for frm_t, frm_c, to_t, to_c in RELATIONSHIPS:
        relationships += (f"relationship {stable_id('rel', frm_t, frm_c, to_t)}\n"
                          f"{T}fromColumn: {q(frm_t)}.{q(frm_c)}\n{T}toColumn: {q(to_t)}.{q(to_c)}\n\n")
    return tables, model, expressions, relationships


def check_model_references(tables):
    """Fail early if a relationship or visual names a table or column that does not exist."""
    columns = {name: {c for c, *_ in cols} | set(derived) for name, (_, cols, derived) in CSV_TABLES.items()}
    columns["Calendar"] = {"Date", "Month", "Year", "Month Start"}
    columns["Service Level"] = {"level_pct", "Service level"}
    columns[MEASURE_TABLE] = {"Value"}
    for frm_t, frm_c, to_t, to_c in RELATIONSHIPS:
        assert frm_c in columns[frm_t] and to_c in columns[to_t], (frm_t, frm_c, to_t, to_c)
    measures = {m[0] for m in MEASURES}
    return columns, measures


# ---------------------------------------------------------------- report (PBIR)

def lit(value):
    return {"expr": {"Literal": {"Value": value}}}


def field(entity, prop, kind):
    return {kind: {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


class Fields:
    """Builds field references, checking each one against the model."""

    def __init__(self, columns, measures):
        self.columns, self.measures = columns, measures

    def col(self, entity, prop):
        assert prop in self.columns[entity], f"unknown column {entity}[{prop}]"
        return entity, prop, "Column"

    def m(self, name):
        assert name in self.measures, f"unknown measure {name}"
        return MEASURE_TABLE, name, "Measure"


def projection(ref, active=False, display=None):
    entity, prop, kind = ref
    p = {"field": field(entity, prop, kind), "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if active:
        p["active"] = True
    if display:
        p["displayName"] = display
    return p


def title_objects(text):
    if not text:
        return {"title": [{"properties": {"show": lit("false")}}]}
    return {"title": [{"properties": {"show": lit("true"), "text": lit("'" + text.replace("'", "''") + "'")}}]}


def visual(name, vtype, pos, roles=None, sort=None, objects=None, title=None, filters=None, z=0):
    v = {"visualType": vtype}
    if roles:
        active_roles = ("Category", "Values") if vtype != "tableEx" else ("Category",)
        v["query"] = {"queryState": {role: {"projections": [projection(r, active=(i == 0 and role in active_roles))
                                                             for i, r in enumerate(refs)]}
                                     for role, refs in roles.items()}}
        if sort:
            ref, direction = sort
            v["query"]["sortDefinition"] = {"sort": [{"field": field(ref[0], ref[1], ref[2]), "direction": direction}]}
    if objects:
        v["objects"] = objects
    v["visualContainerObjects"] = title_objects(title)
    v["drillFilterOtherVisuals"] = True
    x, y, w, h = pos
    out = {"$schema": VISUAL_SCHEMA, "name": name,
           "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}, "visual": v}
    if filters:
        out["filterConfig"] = {"filters": filters}
    return out


def textbox(name, pos, runs, z):
    paragraphs = [{"textRuns": [{"value": text, "textStyle": style}]} for text, style in runs]
    v = visual(name, "textbox", pos, objects={"general": [{"properties": {"paragraphs": paragraphs}}]}, z=z)
    v["visual"]["visualContainerObjects"] = {"background": [{"properties": {"show": lit("false")}}],
                                             "border": [{"properties": {"show": lit("false")}}]}
    return v


H1 = {"fontWeight": "bold", "fontSize": "22pt", "color": "#1B2A41"}
SUB = {"fontSize": "11pt", "color": "#5B6675"}
NOTE = {"fontSize": "11pt", "color": "#1B2A41"}

CARD_OBJECTS = {
    "layout": [{"properties": {"orientation": lit("0D"), "columnCount": lit("3L"), "alignment": lit("'middle'"),
                               "style": lit("'Cards'")}}],
    "value": [{"properties": {"fontSize": lit("28D")}, "selector": {"id": "default"}}],
}


def card(name, pos, refs, z):
    return visual(name, "cardVisual", pos, {"Data": refs}, objects=CARD_OBJECTS, z=z)


def slicer(name, pos, ref, title, z):
    objects = {"data": [{"properties": {"mode": lit("'Dropdown'")}}],
               "selection": [{"properties": {"singleSelect": lit("true")}}],
               "header": [{"properties": {"show": lit("true"), "text": lit("'" + title + "'")}}]}
    return visual(name, "slicer", pos, {"Values": [ref]}, objects=objects, z=z)


def categorical_filter(name, ref, value):
    entity, prop, _ = ref
    return {"name": name, "field": field(entity, prop, "Column"), "type": "Categorical",
            "filter": {"Version": 2, "From": [{"Name": "s", "Entity": entity, "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": prop}}],
                           "Values": [[{"Literal": {"Value": f"'{value}'"}}]]}}}]},
            "howCreated": "User", "isHiddenInViewMode": True}


def pages(f):
    desc = f.col("Products", "description")
    level = f.col("Service Level", "Service level")
    date = f.col("Calendar", "Date")
    status = f.col("Reorder Status", "status")
    return [
        ("reorderNow", "Reorder now", [
            textbox("title", (24, 16, 1232, 72), [
                ("Reorder now", H1),
                ("Products at or below their reorder point on 9 Dec 2011, 95% service level. "
                 "Sales are real; stock positions are simulated.", SUB)], 1000),
            card("summaryCards", (24, 100, 1232, 120),
                 [f.m("Products Below Reorder Point"), f.m("Shortfall Units"), f.m("Products Tracked")], 2000),
            visual("reorderTable", "tableEx", (24, 236, 1232, 460), {"Values": [
                desc, f.col("Reorder Status", "on_hand"), f.col("Reorder Status", "on_order"),
                f.col("Reorder Status", "reorder_point"), f.col("Reorder Status", "safety_stock"),
                f.col("Reorder Status", "order_qty"), f.m("Shortfall Units")]},
                sort=(f.m("Shortfall Units"), "Descending"), title="Products to check",
                filters=[categorical_filter("reorderOnly", status, "Reorder now")], z=3000),
        ]),
        ("tradeoff", "Stockouts vs holding cost", [
            textbox("title", (24, 16, 1232, 72), [
                ("Stockouts vs holding cost", H1),
                ("Policies set from 2010 demand, tested day by day on real 2011 demand. "
                 "Lower bars mean a cheaper policy overall.", SUB)], 1000),
            visual("costChart", "columnChart", (24, 100, 744, 330),
                   {"Category": [level], "Y": [f.m("Holding Cost"), f.m("Lost Margin")]},
                   sort=(level, "Ascending"), title="Holding cost + lost margin = total cost", z=2000),
            visual("stockoutChart", "lineChart", (784, 100, 472, 330),
                   {"Category": [level], "Y": [f.m("Stockout Days")]},
                   sort=(level, "Ascending"), title="Stockout days across 50 products", z=3000),
            visual("tradeoffTable", "tableEx", (24, 446, 880, 250), {"Values": [
                level, f.m("Fill Rate"), f.m("Stockout Days"), f.m("Lost Units"), f.m("Avg Stock Value"),
                f.m("Holding Cost"), f.m("Lost Margin"), f.m("Total Cost")]},
                sort=(level, "Ascending"), title="Trade-off by service level", z=4000),
            textbox("insight", (920, 446, 336, 250), [
                ("Recommendation: 98%", {"fontWeight": "bold", "fontSize": "14pt", "color": "#1B2A41"}),
                ("Total cost falls as the buffer grows, because a lost sale costs more than holding "
                 "an extra unit of these low-cost items.", NOTE),
                ("Moving from 95% to 98% cuts stockout days from 134 to 101 for about £1,200 more holding cost. "
                 "Beyond 98% the extra saving is about £50 a year.", NOTE)], 5000),
        ]),
        ("stockOverTime", "Stock over time", [
            textbox("title", (24, 16, 760, 72), [
                ("Stock over time", H1),
                ("Pick one product and one service level to see the policy at work in 2011.", SUB)], 1000),
            slicer("productSlicer", (800, 20, 272, 64), desc, "Product", 2000),
            slicer("levelSlicer", (1088, 20, 168, 64), level, "Service level", 3000),
            visual("stockChart", "lineChart", (24, 100, 1232, 360),
                   {"Category": [date], "Y": [f.m("On Hand"), f.m("Reorder Point")]},
                   title="Stock on hand vs reorder point", z=4000),
            visual("lostChart", "columnChart", (24, 476, 1232, 220),
                   {"Category": [date], "Y": [f.m("Lost Sales Units")]},
                   title="Units lost to stockouts", z=5000),
        ]),
        ("salesTrend", "Sales trend", [
            textbox("title", (24, 16, 900, 72), [
                ("Sales trend", H1),
                ("Real sales of the 50 products, December 2009 to December 2011, including bulk orders.", SUB)], 1000),
            slicer("yearSlicer", (1040, 20, 216, 64), f.col("Calendar", "Year"), "Year", 2000),
            card("salesCards", (24, 100, 1232, 110), [f.m("Revenue"), f.m("Units Sold"), f.m("Products Tracked")], 3000),
            visual("revenueChart", "lineChart", (24, 226, 744, 470),
                   {"Category": [f.col("Calendar", "Month")], "Y": [f.m("Revenue")]},
                   sort=(f.col("Calendar", "Month"), "Ascending"), title="Revenue by month", z=4000),
            visual("productChart", "barChart", (784, 226, 472, 470),
                   {"Category": [desc], "Y": [f.m("Units Sold")]},
                   sort=(f.m("Units Sold"), "Descending"), title="Units sold by product", z=5000),
        ]),
    ]


def report_json():
    return {
        "$schema": f"{SCHEMA}/item/report/definition/report/3.0.0/schema.json",
        "themeCollection": {
            "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": {"visual": "1.8.97", "report": "2.0.97", "page": "1.3.97"},
                          "type": "SharedResources"},
            "customTheme": {"name": "RetailTheme.json", "reportVersionAtImport": {"visual": "1.8.97", "report": "2.0.97", "page": "1.3.97"},
                            "type": "RegisteredResources"},
        },
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "RetailTheme.json", "path": "RetailTheme.json", "type": "CustomTheme"}]},
        ],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                     "allowChangeFilterTypes": True, "useEnhancedTooltips": True},
    }


THEME = {"name": "Retail Inventory", "dataColors": ["#1F5F8B", "#E07A2F", "#2E8B57", "#8E6BB8", "#C94C4C",
                                                     "#6C7A89", "#D4A72C", "#4FA3C7"],
         "foreground": "#1B2A41", "background": "#FFFFFF", "tableAccent": "#1F5F8B"}


# ---------------------------------------------------------------- write everything

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = obj if isinstance(obj, str) else json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def platform(kind, display):
    return {"$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": kind, "displayName": display},
            "config": {"version": "2.0", "logicalId": stable_id("platform", kind)}}


def build(out=HERE):
    out = Path(out)
    model_dir, report_dir = out / f"{NAME}.SemanticModel", out / f"{NAME}.Report"
    for d in (model_dir, report_dir):
        if d.exists():
            for sub in ("definition", "StaticResources"):
                shutil.rmtree(d / sub, ignore_errors=True)
    tables, model, expressions, relationships = model_files()
    columns, measures = check_model_references(tables)
    defn = model_dir / "definition"
    dump(model_dir / "definition.pbism", {"$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
                                          "version": "4.1", "settings": {}})
    dump(model_dir / ".platform", platform("SemanticModel", NAME))
    dump(defn / "database.tmdl", f"database\n{T}compatibilityLevel: 1567\n")
    dump(defn / "model.tmdl", model)
    dump(defn / "expressions.tmdl", expressions)
    dump(defn / "relationships.tmdl", relationships)
    for name, text in tables.items():
        dump(defn / "tables" / f"{name}.tmdl", text)

    f = Fields(columns, measures)
    rdef = report_dir / "definition"
    dump(report_dir / "definition.pbir", {"$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
                                          "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    dump(report_dir / ".platform", platform("Report", NAME))
    dump(rdef / "version.json", {"$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json",
                                 "version": "2.0.0"})
    dump(rdef / "report.json", report_json())
    all_pages = pages(f)
    dump(rdef / "pages" / "pages.json", {"$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
                                         "pageOrder": [p[0] for p in all_pages], "activePageName": all_pages[0][0]})
    for page_name, display, visuals in all_pages:
        pdir = rdef / "pages" / page_name
        dump(pdir / "page.json", {"$schema": f"{SCHEMA}/item/report/definition/page/2.0.0/schema.json",
                                  "name": page_name, "displayName": display, "displayOption": "FitToPage",
                                  "height": 720, "width": 1280})
        for v in visuals:
            dump(pdir / "visuals" / v["name"] / "visual.json", v)
    static = report_dir / "StaticResources"
    base_themes = static / "SharedResources" / "BaseThemes"
    base_themes.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "assets" / "CY24SU10.json", base_themes / "CY24SU10.json")
    dump(static / "RegisteredResources" / "RetailTheme.json", THEME)
    dump(out / f"{NAME}.pbip", {"$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
                                 "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                 "settings": {"enableAutoRecovery": True}})
    n_visuals = sum(len(p[2]) for p in all_pages)
    print(f"Wrote {len(tables)} tables, {len(RELATIONSHIPS)} relationships, {len(MEASURES)} measures, "
          f"{len(all_pages)} pages and {n_visuals} visuals to {out}")


if __name__ == "__main__":
    build()
