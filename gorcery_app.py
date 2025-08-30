# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time as dtime
import uuid

# -----------------------
# Paths & constants
# -----------------------
APP_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(APP_DIR, "data")        # repo folder
DEFAULT_INVENTORY_PATH = os.path.join(DATA_DIR, "inventory.csv")

REQUIRED_COLS = ["S.No", "Item Category", "Item Name", "Quantity available in stock", "Price"]

# -----------------------
# Utilities
# -----------------------
def read_inventory_csv(path: str) -> pd.DataFrame:
    """Read CSV from path and normalize."""
    df = pd.read_csv(path)
    return normalize_inventory(df)

def read_inventory_from_filelike(upload) -> pd.DataFrame:
    """Read uploaded CSV/Excel and normalize."""
    name = upload.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(upload)
    else:
        df = pd.read_csv(upload)
    return normalize_inventory(df)

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

# -----------------------
# Streamlit App
# -----------------------
st.set_page_config(page_title="Grocery Pickup (No Online Payment)", page_icon="🛒", layout="wide")

# Init session state
if "cart" not in st.session_state:
    st.session_state.cart = {}
if "inventory" not in st.session_state:
    # Try to load default inventory from the repo first
    if os.path.exists(DEFAULT_INVENTORY_PATH):
        try:
            st.session_state.inventory = read_inventory_csv(DEFAULT_INVENTORY_PATH)
        except Exception as e:
            st.session_state.inventory = None
            st.error(f"Failed to read default inventory at data/inventory.csv: {e}")
    else:
        st.session_state.inventory = None

st.title("🛒 Grocery Pickup — Order Online, Pay In-Store")

with st.sidebar:
    st.header("Inventory")
    st.caption("The app loads `data/inventory.csv` from the repo by default. You may upload a file to override it at runtime (read-only).")
    uploaded = st.file_uploader("Upload CSV or Excel (optional override)", type=["csv", "xlsx", "xls"])
    if uploaded is not None:
        try:
            st.session_state.inventory = read_inventory_from_filelike(uploaded)
            st.success("Inventory loaded from uploaded file (read-only).")
        except Exception as e:
            st.error(f"Failed to read uploaded inventory: {e}")

# Require inventory
if st.session_state.inventory is None:
    st.info("No inventory found. Please add `data/inventory.csv` to the repo or upload a file.")
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
        if len(item_names) == 0:
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

# A placeholder to show confirmation & the download button after submit
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
                total = cart_total()

                # Build a receipt and stash it for download OUTSIDE the form
                receipt_df = pd.DataFrame({
                    "Field": ["Order ID", "Name", "Phone", "Pickup Date", "Pickup Time", "Total"],
                    "Value": [oid, customer_name, phone, str(p_date), p_time.strftime("%H:%M"), f"${total:,.2f}"]
                })
                st.session_state["last_order_id"] = oid
                st.session_state["receipt_csv"] = receipt_df.to_csv(index=False).encode("utf-8")

                st.success(f"Order placed! Your order ID is {oid}. Please pay at pickup.")
                reset_cart()

# Outside the form: show download button if we have a receipt
with confirm_area:
    if st.session_state.get("receipt_csv"):
        st.download_button(
            "Download Receipt (CSV)",
            data=st.session_state["receipt_csv"],
            file_name=f"{st.session_state['last_order_id']}_receipt.csv",
            mime="text/csv"
        )

st.caption("Inventory is read-only. The app never modifies your file.")
