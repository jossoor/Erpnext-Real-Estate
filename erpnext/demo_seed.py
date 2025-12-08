# apps/erpnext/erpnext/demo_seed.py

import random
import string

import frappe
from frappe.utils import nowdate, now


# -----------------------------
# Utility: random helpers
# -----------------------------


def _random_code(prefix: str = "") -> str:
    return f"{prefix}{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}"


def _random_sentence(label: str = "") -> str:
    base = "Demo"
    if label:
        base += f" {label}"
    return f"{base} {_random_code()}"


# -----------------------------
# Introspection utilities
# -----------------------------


def count_docs_by_module(module: str):
    """Print counts for all *normal* doctypes in a given module.

    - Skips child tables (istable=1)
    - Skips Single doctypes (issingle=1) because they don't have their own tables
    """
    print(f"DocType counts for module '{module}':")

    doctypes = frappe.get_all(
        "DocType",
        filters={"module": module},
        fields=["name", "istable", "issingle"],
        order_by="name asc",
    )

    for d in doctypes:
        dt = d.name

        # Skip child tables + singles to avoid bogus table errors
        if d.istable:
            print(f"{dt:40} child table (skipped)")
            continue

        if d.issingle:
            print(f"{dt:40} single (skipped)")
            continue

        try:
            cnt = frappe.db.count(dt)
            print(f"{dt:40} {cnt}")
        except Exception as e:  # includes TableMissingError / ProgrammingError
            frappe.db.rollback()
            print(f"{dt:40} COUNT ERROR (skipped): {repr(e)}")


def count_all_docs_all_modules():
    """Print counts for all doctypes, grouped by module."""
    doctypes = frappe.get_all(
        "DocType", fields=["name", "module"], order_by="module asc, name asc"
    )

    current_module = None
    for d in doctypes:
        module = d.module or "Misc"

        if module != current_module:
            current_module = module
            print(f"\n=== Module: {module} ===")

        dt = d.name
        try:
            cnt = frappe.db.count(dt)
            print(f"{dt:40} {cnt}")
        except Exception as e:
            frappe.db.rollback()
            print(f"{dt:40} COUNT ERROR (skipped): {repr(e)}")


# -----------------------------
# Demo seed: basic entry point
# -----------------------------


def make_demo():
    """
    Minimal placeholder.

    You already used a previous version of this script to populate demo data
    (Sales Invoices, Purchase Invoices, Items, etc.), so we don't recreate it
    to avoid duplicates.

    This function is kept only so:
        bench --site demo3.local execute erpnext.demo_seed.make_demo
    still works without error.
    """
    frappe.msgprint("Demo seed: no additional base data created (already populated).")


# -----------------------------
# Generic value generator
# -----------------------------


def _generate_value_for_field(df, company: str | None = None):
    """Generate a simple demo value for a given DocField."""

    fieldtype = (df.fieldtype or "").strip()
    label = (df.label or df.fieldname or "").strip()

    # Basic text-ish types
    if fieldtype in ("Data", "Small Text"):
        return _random_sentence(label)

    if fieldtype in ("Long Text", "Text", "Text Editor", "HTML Editor"):
        return f"Demo {label or df.fieldname} content."

    if fieldtype == "Int":
        return random.randint(1, 10)

    if fieldtype in ("Float", "Currency", "Percent"):
        return 1.0

    if fieldtype == "Check":
        # make required checks true, others random
        return 1 if df.reqd else random.choice([0, 1])

    if fieldtype == "Date":
        return nowdate()

    if fieldtype in ("Datetime", "DateTime"):
        return now()

    if fieldtype == "Time":
        return "09:00:00"

    if fieldtype == "Select":
        if not df.options:
            return None
        # options may be "A\nB\nC" or "Link:DocType"
        opts = [o.strip() for o in str(df.options).split("\n") if o.strip()]
        if not opts:
            return None
        # ignore "Link:" etc. here, treat only simple options
        simple = [o for o in opts if not o.lower().startswith("link:")]
        return (simple or opts)[0]

    if fieldtype == "Link":
        target = (df.options or "").strip()
        if not target:
            return None

        # Some special-cases for common links
        if target == "Company":
            if company:
                return company
            comp = frappe.get_all("Company", limit=1, pluck="name")
            return comp[0] if comp else None

        if target == "User":
            # Administrator always exists
            return "Administrator"

        if target == "Currency":
            # try company default currency
            if company:
                try:
                    cur = frappe.db.get_value(
                        "Company", company, "default_currency"
                    )
                    if cur:
                        return cur
                except Exception:
                    pass
            existing = frappe.get_all("Currency", limit=1, pluck="name")
            return existing[0] if existing else "USD"

        # generic link: try to pick any existing doc
        try:
            existing = frappe.get_all(target, limit=1, pluck="name")
            if existing:
                return existing[0]
        except Exception:
            # table might not exist or be a single; just give up
            return None

        # no existing target; for non-required links we can leave it None
        return None

    # We don't try to auto-fill Table / Dynamic Link here
    if fieldtype in ("Table", "Dynamic Link", "Table MultiSelect"):
        return None

    return None


# -----------------------------
# Generic Doctype seeder
# -----------------------------


def seed_one_doctype(
    doctype: str,
    company: str | None = None,
    ignore_existing: bool = False,
):
    """
    Try to create ONE demo record for the given doctype.

    - Skips Single doctypes (settings) and child tables.
    - If ignore_existing=False: only seed if count == 0.
    - If ignore_existing=True: will attempt to insert even if there is already data.
    """

    try:
        meta = frappe.get_meta(doctype)
    except Exception as e:
        print(f"{doctype:40} META ERROR (skipped): {repr(e)}")
        return

    if meta.istable:
        print(f"{doctype:40} child table (skipped)")
        return

    if meta.issingle:
        print(f"{doctype:40} single (skipped)")
        return

    try:
        existing_count = frappe.db.count(doctype)
    except Exception as e:
        frappe.db.rollback()
        print(f"{doctype:40} COUNT ERROR (skipped): {repr(e)}")
        return

    if not ignore_existing and existing_count > 0:
        print(f"{doctype:40} already has data (skipped)")
        return

    # Create new document
    doc = frappe.new_doc(doctype)

    for df in meta.get("fields"):
        # Skip non-field rows
        if not df.fieldname:
            continue

        # Skip layout / non-data fields
        if df.fieldtype in (
            "Section Break",
            "Column Break",
            "Tab Break",
            "HTML",
            "Button",
            "Image",
        ):
            continue

        # Skip naming series & auto fields
        if df.fieldname in ("naming_series", "amended_from"):
            continue

        if df.read_only:
            continue

        # We don't auto-build child tables here
        if df.fieldtype in ("Table", "Table MultiSelect"):
            continue

        if doc.get(df.fieldname):
            continue

        value = _generate_value_for_field(df, company=company)
        if value is not None:
            doc.set(df.fieldname, value)

    try:
        doc.insert(ignore_permissions=True)
        print(f"{doctype:40} created: {doc.name}")
    except Exception as e:
        frappe.db.rollback()
        print(f"{doctype:40} INSERT ERROR (skipped): {e}")


def _get_any_company() -> str | None:
    companies = frappe.get_all("Company", limit=1, pluck="name")
    return companies[0] if companies else None


def seed_all_empty_doctypes():
    """
    OLD behaviour: seed only doctypes with **zero** records (for completeness).

    You already used something like this earlier; kept here if you want to rerun.
    """
    company = _get_any_company()
    doctypes = frappe.get_all(
        "DocType", fields=["name", "module", "istable", "issingle"], order_by="module asc, name asc"
    )

    current_module = None
    for d in doctypes:
        module = d.module or "Misc"
        if module != current_module:
            current_module = module
            print(f"\n=== Seeding Module: {module} ===")

        dt = d.name

        try:
            cnt = frappe.db.count(dt)
        except Exception as e:
            frappe.db.rollback()
            print(f"{dt:40} COUNT ERROR (skipped): {repr(e)}")
            continue

        if cnt == 0:
            seed_one_doctype(dt, company=company, ignore_existing=False)
        else:
            print(f"{dt:40} already has data (skipped)")


def seed_zero_or_one_doctypes():
    """
    NEW behaviour you asked for:

    - For EVERY non-single, non-child DocType
    - If it has **0 or 1 records**, try to add ONE MORE record.

    This makes doctypes that were empty or had a single example
    look more realistic for demo / testing.
    """
    company = _get_any_company()
    doctypes = frappe.get_all(
        "DocType", fields=["name", "module", "istable", "issingle"], order_by="module asc, name asc"
    )

    current_module = None
    for d in doctypes:
        module = d.module or "Misc"
        if module != current_module:
            current_module = module
            print(f"\n=== Seeding Module: {module} ===")

        dt = d.name

        # Skip singles & child tables early
        if d.istable:
            print(f"{dt:40} child table (skipped)")
            continue
        if d.issingle:
            print(f"{dt:40} single (skipped)")
            continue

        try:
            cnt = frappe.db.count(dt)
        except Exception as e:
            frappe.db.rollback()
            print(f"{dt:40} COUNT ERROR (skipped): {repr(e)}")
            continue

        if cnt <= 1:
            # We explicitly ignore existing count inside seed_one_doctype
            seed_one_doctype(dt, company=company, ignore_existing=True)
        else:
            print(f"{dt:40} has {cnt} rows (skipped)")
