# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import os, io
from datetime import datetime, date, time as dtime
import uuid

# PDF tools
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

# -----------------------
# Paths & constants
# -----------------------
APP_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(APP_DIR, "data")                # repo folder
DEFAULT_INVENTORY_PATH = os.path.join(DATA_DIR, "inventory.csv")

REQUIRED_COLS = ["S.No", "Item Category", "Item Name", "Quantity available in stock", "Price"]

# -----------------------
# Utilities
# -----------------------
def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    df["S.No"] = pd.to_numeric(df["S.No"], errors="coerce").astype("Int64")
    df["Quantity available in stock"] = pd.to_numeric(
        df["Quantity available in stock"], errors="coerce"
    ).fillna(0).astype(int)
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce").fillna(0.0).astype(float)
    df = df.dropna(subset=["Item Name"]).copy()
    return df

def read_inventory_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return normalize_inventory(df)

def add_to_cart(item_row: pd.Series, qty: int):
    key = int(item_row["S.No"]) if pd.notna(item_row["S.No"]) else hash(item_row["Item Name"])
    cart = st.session_state.cart
    if key in cart:
        cart[key]["qty"] += qty
        cart[key]["line_total"] = round(cart[key]["qty"] * cart[key]["unit_price"], 2)
    else:
        cart[key] = {
            "S.No": int(item_row["S.No"]) if pd.notna(item_row["S.No"]) else None,
            "Item Category": item_row["Item Category"],
            "Item Name": item_row["Item Name"],
            "qty": qty,
            "unit_price": float(item_row["Price"]),
            "line_total": round(qty * float(item_row["Price"]), 2),
        }

def cart_to_dataframe():
    if not st.session_state.cart:
        return pd.DataFrame(columns=["Item Category", "Item Name", "Qty", "Unit Price", "Line Total"])
    rows = []
    for v in st.session_state.cart.values():
        rows.append([v["Item Category"], v["Item Name"], v["qty"], v["unit_price"], v["line_total"]])
    return pd.DataFrame(rows, columns=["Item Category", "Item Name", "Qty", "Unit Price", "Line Total"])

def cart_total():
    return round(sum(v["line_total"] for v in st.session_state.cart.values()), 2)

def reset_cart():
    st.session_state.cart = {}

def make_pdf(order_id: str, customer_name: str, phone: str,
             pickup_date: date, pickup_time: dtime,
             items_df: pd.DataFrame, total: float) -> bytes:
    """
    Build a simple, clean itemized PDF receipt and return bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, topMargin=36, bottomMargin=36, leftMargin=36, rightMargin=36)
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph("<b>Grocery Pickup – Order Receipt</b>", styles["Title"]))
    story.append(Spacer(1, 0.15*inch))

    # Order meta
    meta = [
        ["Order ID:", order_id],
        ["Customer:", customer_name],
        ["Phone:", phone],
        ["Pickup:", f"{pickup_date} at {pickup_time.strftime('%H:%M')}"],
        ["Payment:", "In-store only"],
    ]
    meta_table = Table(meta, hAlign="LEFT", colWidths=[1.2*inch, 4.8*inch])
    meta_table.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), "Helvetica", 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.25*inch))

    # Items table
    data = [["Item Category", "Item Name", "Qty", "Unit Price", "Line Total"]]
    for _, row in items_df.iterrows():
        data.append([
            str(row["Item Category"]),
            str(row["Item Name"]),
            int(row["Qty"]),
            f"${row['Unit Price']:.2f}",
            f"${row['Line Total']:.2f}",
        ])

    tbl = Table(data, hAlign="LEFT", colWidths=[1.5*inch, 2.7*inch, 0.7*inch, 1.0*inch, 1.0*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f0f0f0")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.black),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold", 10),
        ("FONT", (0,1), (-1,-1), "Helvetica", 10),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#cccccc")),
        ("ALIGN", (2,1), (2,-1), "RIGHT"),
        ("ALIGN", (3,1), (4,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fbfbfb")]),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.2*inch))

    # Total
    total_tbl = Table([["", "Total:", f"${total:,.2f}"]], colWidths=[4.2*inch, 1.0*inch, 1.0*inch])
    total_tbl.setStyle(TableStyle([
        ("FONT", (1,0), (1,0), "Helvetica-Bold", 11),
        ("FONT", (2,0), (2,0), "Helvetica-Bold", 11),
        ("ALIGN", (2,0), (2,0), "RIGHT"),
    ]))
    story.append(total_tbl)
    story.append(Spacer(1, 0.25*inch))
    story.append(Paragraph("Thank you! Please present this receipt when you come to pay and collect your order.", styles["Normal"]))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes

# -----------------------
# Streamlit App
# -----------------------
st.set_page_config(page_title="Grocery Pickup (No Online Payment)", page_icon="🛒", layout="wide")

# Init session state
if "cart" not in st.session_state:
    st.session_state.cart = {}
if "inventory" not in st.session_state:
    # Always load from repo (no upload UI)
    if os.path.exists(DEFAULT_INVENTORY_PATH):
        try:
            st.session_state.inventory = read_inventory_csv(DEFAULT_INVENTORY_PATH)
        except Exception as e:
            st.session_state.inventory = None
            st.error(f"Failed to read data/inventory.csv: {e}")
    else:
        st.session_state.inventory = None

st.title("🛒 Grocery Pickup — Order Online, Pay In-Store")

# No upload / override in Cloud. If no inventory, stop.
if st.session_state.inventory is None:
    st.error("Inventory not found. Please include `data/inventory.csv` in the repository.")
    st.stop()

# -----------------------
# Catalog & Add to Cart
# -----------------------
inv = st.session_state.inventory.copy()
left, right = st.columns([2, 1])

with left:
    st.subheader("Browse Items")
    categories = ["All"] + sorted(inv["Item Category"].dropna().unique().tolist())
    category = st.selectbox("Filter by category", categories, index=0)
    if category != "All":
        inv = inv[inv["Item Category"] == category]

    st.dataframe(
        inv[["S.No", "Item Category", "Item Name", "Quantity available in stock", "Price"]]
        .reset_index(drop=True),
        use_container_width=True
    )

    with st.form("add_to_cart_form", clear_on_submit=True):
        st.markdown("### Add to cart")
        item_names = inv["Item Name"].tolist()
        if not item_names:
            st.info("No items available in this category.")
        else:
            chosen_name = st.selectbox("Item", item_names)
            item_row = inv[inv["Item Name"] == chosen_name].iloc[0]
            max_qty = int(item_row["Quantity available in stock"])
            qty = st.number_input("Quantity", min_value=1, max_value=max(max_qty, 1), value=1, step=1)
            submitted = st.form_submit_button("Add")
            if submitted:
                if max_qty <= 0:
                    st.warning("Sorry, this item is out of stock (per your sheet).")
                else:
                    add_to_cart(item_row, int(qty))
                    st.success(f"Added {qty} × {chosen_name} to cart.")

with right:
    st.subheader("Your Cart")
    cart_df = cart_to_dataframe()
    st.dataframe(cart_df, use_container_width=True, hide_index=True)
    total = cart_total()
    st.metric("Total", f"${total:,.2f}")
    if st.button("Clear cart"):
        reset_cart()
        st.info("Cart cleared.")

# -----------------------
# Checkout (no payment online)
# -----------------------
st.markdown("---")
st.header("Confirm Order (Pay In-Store)")

# Placeholder for showing the PDF download AFTER submit
confirm_area = st.container()

with st.form("checkout_form", clear_on_submit=False):
    c1, c2 = st.columns(2)
    with c1:
        customer_name = st.text_input("Full Name")
        phone = st.text_input("Phone")
    with c2:
        p_date = st.date_input("Pickup Date", value=date.today())
        p_time = st.time_input("Pickup Time", value=dtime(17, 0))

    agree = st.checkbox("I understand that payment is in-store only (no online payment).")
    confirm = st.form_submit_button("Place Order")

    if confirm:
        if len(st.session_state.cart) == 0:
            st.warning("Your cart is empty.")
        elif not customer_name or not phone or not agree:
            st.warning("Please fill your details and acknowledge the no-online-payment policy.")
        else:
            # Validate against the uploaded (read-only) stock
            ok = True
            inv_now = st.session_state.inventory
            for _, item in st.session_state.cart.items():
                row = inv_now[inv_now["Item Name"] == item["Item Name"]]
                if row.empty or int(row["Quantity available in stock"].iloc[0]) < item["qty"]:
                    ok = False
                    st.error(f"Not enough stock for {item['Item Name']} per your sheet. Please adjust quantity.")
                    break
            if ok:
                oid = f"ORD-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8].upper()}"
                items_df = cart_to_dataframe()
                total_amt = cart_total()
                # Build PDF and stash for download outside the form
                st.session_state["last_order_id"] = oid
                st.session_state["receipt_pdf"] = make_pdf(
                    order_id=oid,
                    customer_name=customer_name,
                    phone=phone,
                    pickup_date=p_date,
                    pickup_time=p_time,
                    items_df=items_df,
                    total=total_amt
                )
                st.success(f"Order placed! Your order ID is {oid}. Please pay at pickup.")
                reset_cart()

# Show the PDF download button OUTSIDE the form
with confirm_area:
    pdf_bytes = st.session_state.get("receipt_pdf")
    if pdf_bytes:
        st.download_button(
            "Download Receipt (PDF)",
            data=pdf_bytes,
            file_name=f"{st.session_state['last_order_id']}_receipt.pdf",
            mime="application/pdf"
        )

st.caption("Inventory is read-only and loaded from the repository.")
