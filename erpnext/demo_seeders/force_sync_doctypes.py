import frappe

MODULES = ["Selling", "Buying", "Accounts", "Stock"]

def run():
    doctypes = frappe.get_all(
        "DocType",
        filters={"module": ["in", MODULES]},
        fields=["name", "issingle", "istable", "module"],
        order_by="module asc, name asc",
    )

    created = []
    skipped = []
    errors = []

    for dt in doctypes:
        name = dt["name"]
        try:
            # Singles don’t have tables; skip with note.
            if int(dt.get("issingle") or 0):
                skipped.append((name, "single"))
                continue

            # If table already exists, skip quietly.
            if frappe.db.table_exists(f"tab{name}"):
                skipped.append((name, "exists"))
                continue

            # Re-save the DocType to force schema creation/sync
            doc = frappe.get_doc("DocType", name)
            doc.flags.ignore_permissions = True
            doc.save()  # triggers on_update → creates tab<doctype> if missing

            # Double-check table now exists
            if frappe.db.table_exists(f"tab{name}"):
                created.append(name)
            else:
                errors.append((name, "table still missing after save()"))
        except Exception as e:
            errors.append((name, str(e.__class__.__name__)))

    summary = [
        f"Force-sync summary:",
        f"  Created tables: {len(created)}",
        f"  Skipped (already exists or single): {len(skipped)}",
        f"  Errors: {len(errors)}",
    ]
    return "\n".join(summary + [
        "",
        "Created: " + ", ".join(created[:30]) + (" ..." if len(created) > 30 else ""),
        "Errors: " + ", ".join([f"{n}({m})" for n,m in errors[:30]]) + (" ..." if len(errors) > 30 else ""),
    ])
