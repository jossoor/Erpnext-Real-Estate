
import frappe

MODULES = ["Selling", "Buying", "Accounts", "Stock"]

def _has_table(doctype: str) -> bool:
    try:
        return frappe.db.table_exists(f"tab{doctype}")
    except Exception:
        return False

def _count_rows(doctype: str, istable: int, issingle: int):
    """
    Returns (count:int, note:str)
    - Normal/child DocType: row count in tab<doctype> if table exists, else 0 with note.
    - Single: number of Singles rows (i.e., fields set for that Single); we’ll also treat >0 as “has data”.
    """
    if issingle:
        rows = frappe.db.count("Singles", {"doctype": doctype})
        note = "single: fields set" if rows else "single: no fields set"
        # For Singles, “data present” is whether any field rows exist.
        return rows, note

    # Non-single (regular or child)
    if not _has_table(doctype):
        return 0, "table missing (skipped by framework/app)"
    try:
        # frappe.db.count(doctype) → count(*)
        cnt = frappe.db.count(doctype)
        return cnt, ""
    except Exception as e:
        return 0, f"count error: {e.__class__.__name__}"

def run():
    # pull doctypes in target modules
    doctypes = frappe.get_all(
        "DocType",
        filters={"module": ["in", MODULES]},
        fields=["name", "module", "istable", "issingle"],
        order_by="module asc, name asc",
    )

    lines = []
    with_data = 0
    without_data = 0

    for dt in doctypes:
        name = dt["name"]
        module = dt["module"]
        istable = int(dt.get("istable") or 0)
        issingle = int(dt.get("issingle") or 0)

        cnt, note = _count_rows(name, istable, issingle)
        has = (cnt > 0) if not issingle else (cnt > 0)  # singles: any fields set counts as data
        if has:
            with_data += 1
        else:
            without_data += 1

        type_tag = "Single" if issingle else ("Child Table" if istable else "DocType")
        note_str = f" ({note})" if note else ""
        lines.append(f"{module:8} | {type_tag:11} | {name:40} | rows={cnt}{note_str}")

    total = len(doctypes)

    header = "Module   | Type        | DocType                                 | Rows"
    sep = "-" * 86
    body = "\n".join(lines)
    summary = (
        f"\n\nTotal DocTypes in target modules: {total}\n"
        f"With data: {with_data}\n"
        f"Without data: {without_data}\n"
    )

    # Return a multi-line string so bench prints it nicely
    return header + "\n" + sep + "\n" + body + summary
