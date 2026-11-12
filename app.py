import streamlit as st
import pandas as pd
import requests
import re
import io

st.set_page_config(page_title="Bulk ASIN to ISBN-13 Converter", page_icon="📚", layout="wide")

def calculate_isbn13_from_isbn10(asin):
    """Calculates ISBN-13 mathematically from a 10-digit print ASIN (ISBN-10)."""
    clean_asin = re.sub(r'[^0-9X]', '', str(asin).upper().strip())
    if len(clean_asin) != 10 or not clean_asin[:9].isdigit():
        return None
    
    core = "978" + clean_asin[:9]
    total = sum(int(digit) * (1 if idx % 2 == 0 else 3) for idx, digit in enumerate(core))
    remainder = total % 10
    check_digit = 0 if remainder == 0 else 10 - remainder
    return core + str(check_digit)

@st.cache_data(show_spinner=False)
def lookup_b0_asin(asin):
    """Queries Open Library API, with a fallback to Google Books API for B0 ASINs."""
    # 1. Try Open Library
    ol_url = f"https://openlibrary.org:{asin}&format=json&jscmd=data"
    try:
        res = requests.get(ol_url, timeout=5).json()
        key = f"ASIN:{asin}"
        if key in res and "identifiers" in res[key]:
            isbn_13_list = res[key]["identifiers"].get("isbn_13", [])
            if isbn_13_list:
                return isbn_13_list[0]
    except Exception:
        pass

    # 2. Fallback to Google Books
    gb_url = f"https://googleapis.com{asin}"
    try:
        res = requests.get(gb_url, timeout=5).json()
        if "items" in res:
            for item in res["items"]:
                identifiers = item.get("volumeInfo", {}).get("industryIdentifiers", [])
                for ident in identifiers:
                    if ident.get("type") == "ISBN_13":
                        return ident.get("identifier")
    except Exception:
        pass

    return "Not Found"

def convert_single(asin):
    if pd.isna(asin) or not str(asin).strip():
        return "Empty"
    clean = str(asin).strip().upper()
    if clean.startswith("B0"):
        return lookup_b0_asin(clean)
    result = calculate_isbn13_from_isbn10(clean)
    return result if result else "Invalid Format"

# --- UI ---
st.title("📚 Bulk ASIN to ISBN-13 Converter")
st.write("Upload a CSV or Excel spreadsheet, or paste hundreds of ASINs at once.")

tab1, tab2 = st.tabs(["📁 Bulk File Upload (CSV / Excel)", "📋 Paste Bulk List"])

with tab1:
    uploaded_file = st.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx", "xls"])
    
    if uploaded_file is not None:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        st.write(f"**Loaded {len(df):,} rows.** Select the column containing your ASINs:")
        
        default_idx = next((i for i, c in enumerate(df.columns) if c.strip().upper() == "ASIN"), 0)
        selected_col = st.selectbox("ASIN Column:", df.columns, index=default_idx)
        
        if st.button("🚀 Start Bulk Conversion", type="primary"):
            progress_bar = st.progress(0, text="Starting conversion...")
            results = []
            total_rows = len(df)
            
            for idx, val in enumerate(df[selected_col]):
                results.append(convert_single(val))
                if idx % max(1, total_rows // 100) == 0 or idx == total_rows - 1:
                    progress_bar.progress((idx + 1) / total_rows, text=f"Processed {idx + 1:,} of {total_rows:,} rows...")
            
            df["ISBN-13"] = results
            progress_bar.empty()
            
            # Summary Metrics
            found_count = sum(1 for r in results if r not in ["Not Found", "Invalid Format", "Empty"])
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Rows", f"{total_rows:,}")
            col2.metric("Successfully Converted", f"{found_count:,}")
            col3.metric("Not Found / Invalid", f"{total_rows - found_count:,}")
            
            st.dataframe(df, use_container_width=True)
            
            # Download Buttons (CSV and Excel)
            dl_col1, dl_col2 = st.columns(2)
            csv_data = df.to_csv(index=False).encode("utf-8")
            dl_col1.download_button("⬇️ Download as CSV", data=csv_data, file_name="bulk_isbn13.csv", mime="text/csv")
            
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Converted")
            dl_col2.download_button("⬇️ Download as Excel (.xlsx)", data=excel_buffer.getvalue(), file_name="bulk_isbn13.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab2:
    raw_text = st.text_area("Paste ASINs (one per line, or separated by commas):", height=200, placeholder="0451524934\nB000FC1TG2\n0140449132")
    if st.button("Convert Pasted List", type="primary"):
        items = [x.strip() for x in re.split(r'[\n,]+', raw_text) if x.strip()]
        if items:
            progress = st.progress(0, text="Converting...")
            out = []
            for i, item in enumerate(items):
                out.append({"ASIN": item, "ISBN-13": convert_single(item)})
                progress.progress((i + 1) / len(items))
            progress.empty()
            
            res_df = pd.DataFrame(out)
            st.dataframe(res_df, use_container_width=True)
            st.download_button("⬇️ Download CSV", data=res_df.to_csv(index=False).encode("utf-8"), file_name="pasted_isbn13.csv", mime="text/csv")
        else:
            st.warning("Please paste at least one ASIN.")
