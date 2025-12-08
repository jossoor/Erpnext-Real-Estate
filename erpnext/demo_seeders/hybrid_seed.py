
import random
from datetime import date, timedelta, datetime
import frappe

MODULES = ["Selling","Buying","Accounts","Stock"]
SEED_DAYS_PAST = 90
MAX_PER_FLOW = 3     # how many SO/DN/SI and PO/PR/PI flows

def d_past(n=SEED_DAYS_PAST): 
    return date.today() - timedelta(days=random.randint(0,n))

def has_table(dt): 
    try: 
        return frappe.db.table_exists(f"tab{dt}")
    except: 
        return False

def first(dt, filters=None):
    if not has_table(dt): 
        return None
    try:
        rows = frappe.get_all(dt, filters=filters or {}, pluck="name", limit=1)
        return rows[0] if rows else None
    except: 
        return None

def ensure(dt, **fields):
    if not has_table(dt): 
        return frappe._dict(name=None)
    name = fields.get("name")
    try:
        if name and frappe.db.exists(dt, name):
            return frappe.get_doc(dt, name)
        ex = first(dt, fields) if fields else None
        if ex:
            return frappe.get_doc(dt, ex)
        doc = frappe.get_doc({"doctype": dt, **fields})
        doc.insert(ignore_permissions=True)
        return doc
    except:
        frappe.log_error(frappe.get_traceback(), f"ensure failed: {dt}")
        return frappe._dict(name=None)

def bootstrap():
    companies = frappe.get_all("Company", pluck="name")
    if not companies: 
        frappe.throw("No Company on this site.")
    company = companies[0]
    abbr = frappe.db.get_value("Company", company, "abbr") or "CMP"

    # Masters
    ensure("Territory", name="All Territories", is_group=1)
    ensure("Customer Group", customer_group_name="Commercial", is_group=0)
    ensure("Supplier Group", supplier_group_name="All Supplier Groups", is_group=1)
    ensure("UOM", uom_name="Nos", must_be_whole_number=1)
    ensure("UOM", uom_name="Hour", must_be_whole_number=0)

    root = ensure("Item Group", item_group_name="All Item Groups", is_group=1)
    prod = ensure("Item Group", item_group_name="Products", parent_item_group=getattr(root,"name",None), is_group=0)
    serv = ensure("Item Group", item_group_name="Services", parent_item_group=getattr(root,"name",None), is_group=0)

    stores = ensure("Warehouse", warehouse_name=f"Stores - {abbr}", company=company)
    fg     = ensure("Warehouse", warehouse_name=f"Finished Goods - {abbr}", company=company)

    ensure("Price List", price_list_name="Standard Selling", selling=1, buying=0, currency="EGP")
    ensure("Price List", price_list_name="Standard Buying",  selling=0, buying=1, currency="EGP")

    for i in range(1,6):
        ensure("Customer", customer_name=f"Demo Customer {i}", customer_group="Commercial", territory="All Territories")
        ensure("Supplier", supplier_name=f"Demo Supplier {i}", supplier_group="All Supplier Groups")

    for i in range(1,7):
        ensure("Item", item_code=f"ITEM-{i:03d}", item_name=f"Demo Stock Item {i}",
               stock_uom="Nos", is_stock_item=1, item_group=getattr(prod,"name",None), standard_rate=random.randint(50,400))
    for i in range(1,3):
        ensure("Item", item_code=f"SVC-{i:03d}", item_name=f"Demo Service {i}",
               stock_uom="Hour", is_stock_item=0, item_group=getattr(serv,"name",None), standard_rate=random.randint(200,700))

    # Accounts / Cost Center fallbacks (tolerant)
    cc = first("Cost Center", {"company": company}) or (ensure("Cost Center", cost_center_name=f"Main - {abbr}", company=company).name if has_table("Cost Center") else None)
    bank = first("Account", {"company": company, "account_type": "Bank"}) or first("Account", {"company": company, "root_type": "Asset"})
    ar   = first("Account", {"company": company, "account_type": "Receivable"}) or first("Account", {"company": company, "root_type": "Asset"})
    ap   = first("Account", {"company": company, "account_type": "Payable"})   or first("Account", {"company": company, "root_type": "Liability"})
    income = first("Account", {"company": company, "root_type": "Income"}) or first("Account", {"company": company})
    expense= first("Account", {"company": company, "root_type": "Expense"}) or first("Account", {"company": company})

    return {
        "company": company, "abbr": abbr,
        "stores": getattr(stores,"name","") or "",
        "fg": getattr(fg,"name","") or "",
        "cc": cc, "bank": bank, "ar": ar, "ap": ap, "income": income, "expense": expense
    }

def opening_stock(ctx):
    items = frappe.get_all("Item", filters={"is_stock_item":1}, pluck="name")
    if not items or not ctx["stores"]: 
        return
    se = frappe.get_doc({
        "doctype":"Stock Entry",
        "stock_entry_type":"Material Receipt",
        "company": ctx["company"],
        "posting_date": d_past(120),
    })
    for it in items[:6]:
        se.append("items", {
            "item_code": it,
            "t_warehouse": ctx["stores"],
            "qty": random.randint(10,80),
            "basic_rate": random.randint(50,300),
        })
    se.insert(ignore_permissions=True); se.submit()

def buying_flow(ctx, supplier):
    txn = d_past(35); sch = txn + timedelta(days=random.randint(0,10))
    stock_items = frappe.get_all("Item", filters={"is_stock_item":1}, pluck="name")[:5]
    if not stock_items: 
        return
    po = frappe.get_doc({
        "doctype":"Purchase Order",
        "company": ctx["company"],
        "supplier": supplier,
        "transaction_date": txn,
        "schedule_date": sch,
        "buying_price_list":"Standard Buying",
        "items": [{
            "item_code": it,
            "qty": random.randint(2,10),
            "rate": random.randint(50,300),
            "schedule_date": sch,
            "warehouse": ctx["stores"] or ctx["fg"],
        } for it in random.sample(stock_items, k=min(3,len(stock_items)))]
    })
    po.insert(ignore_permissions=True); po.submit()

    pr = frappe.new_doc("Purchase Receipt")
    pr.company = ctx["company"]; pr.supplier = supplier; pr.posting_date = sch + timedelta(days=random.randint(0,5))
    for r in po.items:
        pr.append("items", {
            "item_code": r.item_code, "qty": r.qty, "rate": r.rate,
            "po_detail": r.name, "purchase_order": po.name,
            "warehouse": ctx["stores"] or ctx["fg"],
        })
    pr.insert(ignore_permissions=True); pr.submit()

    pi = frappe.new_doc("Purchase Invoice")
    pi.company = ctx["company"]; pi.supplier = supplier; pi.posting_date = pr.posting_date + timedelta(days=random.randint(0,5))
    for r in pr.items:
        row = {
            "item_code": r.item_code, "qty": r.qty, "rate": r.rate,
            "purchase_receipt": pr.name, "pr_detail": r.name
        }
        pim = frappe.get_meta("Purchase Invoice Item")
        fn = {f.fieldname for f in pim.fields if f.fieldname}
        if "expense_account" in fn and ctx["expense"]:
            row["expense_account"] = ctx["expense"]
        if "cost_center" in fn and ctx["cc"]:
            row["cost_center"] = ctx["cc"]
        pi.append("items", row)
    pi.insert(ignore_permissions=True); pi.submit()

def selling_flow(ctx, customer):
    txn = d_past(25); deliv = txn + timedelta(days=random.randint(0,10))
    items = frappe.get_all("Item", pluck="name")
    if not items: 
        return
    so = frappe.get_doc({
        "doctype":"Sales Order",
        "company": ctx["company"],
        "customer": customer,
        "transaction_date": txn,
        "delivery_date": deliv,
        "selling_price_list": "Standard Selling",
        "items":[]
    })
    for it in random.sample(items, k=min(3,len(items))):
        is_stock = frappe.db.get_value("Item", it, "is_stock_item")
        row = {"item_code": it, "qty": random.randint(1,6), "rate": random.randint(100,600), "delivery_date": deliv}
        if is_stock and ctx["stores"]:
            row["warehouse"] = ctx["stores"]
        so.append("items", row)
    so.insert(ignore_permissions=True); so.submit()

    dn = frappe.new_doc("Delivery Note")
    dn.company = ctx["company"]; dn.customer = customer; dn.posting_date = deliv + timedelta(days=random.randint(0,5))
    for r in so.items:
        if frappe.db.get_value("Item", r.item_code, "is_stock_item"):
            dn.append("items", {
                "item_code": r.item_code, "qty": r.qty, "rate": r.rate,
                "against_sales_order": so.name, "so_detail": r.name,
                "warehouse": ctx["stores"] or ctx["fg"]
            })
    if dn.items:
        dn.insert(ignore_permissions=True); dn.submit()

    si = frappe.new_doc("Sales Invoice")
    si.company = ctx["company"]; si.customer = customer; si.posting_date = deliv + timedelta(days=random.randint(0,7))
    sim = frappe.get_meta("Sales Invoice Item"); fn = {f.fieldname for f in sim.fields if f.fieldname}
    for r in so.items:
        row = {"item_code": r.item_code, "qty": r.qty, "rate": r.rate, "sales_order": so.name, "so_detail": r.name}
        if "income_account" in fn and ctx["income"]:
            row["income_account"] = ctx["income"]
        if "cost_center" in fn and ctx["cc"]:
            row["cost_center"] = ctx["cc"]
        si.append("items", row)
    si.insert(ignore_permissions=True); si.submit()

    if has_table("Payment Entry") and ctx["ar"] and ctx["bank"]:
        pe = frappe.get_doc({
            "doctype":"Payment Entry",
            "payment_type":"Receive",
            "company": ctx["company"],
            "party_type":"Customer",
            "party": customer,
            "posting_date": d_past(5),
            "paid_from": ctx["ar"],
            "paid_to": ctx["bank"],
            "references": []
        })
        pe.append("references", {"reference_doctype":"Sales Invoice", "reference_name": si.name, "allocated_amount": si.rounded_total or si.grand_total})
        pe.insert(ignore_permissions=True); pe.submit()

def run():
    ctx = bootstrap()

    # If core tables still missing (rare), abort early with a readable message
    core = ["Customer","Supplier","Item","Warehouse","Sales Order","Delivery Note","Sales Invoice","Purchase Order","Purchase Receipt","Purchase Invoice","Stock Entry"]
    missing = [dt for dt in core if not has_table(dt)]
    if missing:
        return "Cannot seed: missing tables: " + ", ".join(missing)

    # seed opening stock
    try: opening_stock(ctx)
    except: frappe.log_error(frappe.get_traceback(), "opening_stock failed")

    customers = frappe.get_all("Customer", pluck="name")
    suppliers = frappe.get_all("Supplier", pluck="name")

    for s in random.sample(suppliers, k=min(MAX_PER_FLOW, len(suppliers))):
        try: buying_flow(ctx, s)
        except: frappe.log_error(frappe.get_traceback(), "buying_flow failed")

    for c in random.sample(customers, k=min(MAX_PER_FLOW, len(customers))):
        try: selling_flow(ctx, c)
        except: frappe.log_error(frappe.get_traceback(), "selling_flow failed")

    return "Hybrid seeding complete."
