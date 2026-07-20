import streamlit as st
import pandas as pd
import re
from pathlib import Path

# =====================================================================
# 1. PAGE CONFIGURATION & SETUP
# =====================================================================
st.set_page_config(
    page_title="Tawjih Guidance Dashboard",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🎓 Tunisian Baccalaureate Tawjih Explorer")
st.markdown("Your marks are loaded in the sidebar. Every filter below applies live — no search button needed.")

# Paths setup
PROJECT_ROOT = Path.cwd().parent
PROGRAMS_FILE = PROJECT_ROOT / "data" / "final" / "tawjih_scraped.csv"
FORMULAS_FILE = PROJECT_ROOT / "data" / "final" / "formulas.csv"
FICHE_FILE = PROJECT_ROOT / "data" / "final" / "fiche_details.csv"

# Configuration constants
PREFERRED_YEAR = 2026
BAC_TRACK_ARABIC = "علوم الإعلامية"
BAC_TRACK_ENGLISH = "Informatique"


# =====================================================================
# 2. DATA LOADING
# =====================================================================
@st.cache_data
def load_and_prep_data():
    if not all([PROGRAMS_FILE.exists(), FORMULAS_FILE.exists(), FICHE_FILE.exists()]):
        st.error("Missing data files! Please check your data folder for tawjih_scraped, formulas, and fiche_details.")
        return None, PREFERRED_YEAR

    programs = pd.read_csv(PROGRAMS_FILE, encoding="utf-8-sig")
    formulas = pd.read_csv(FORMULAS_FILE, encoding="utf-8-sig")
    fiche = pd.read_csv(FICHE_FILE, encoding="utf-8-sig")

    # Prevent empty dataframe by auto-falling back to the highest available year in your CSV
    available_years = programs["year"].unique()
    selected_year = PREFERRED_YEAR
    if selected_year not in available_years:
        selected_year = int(programs["year"].max())

    # Clean primary datasets
    filtered_programs = programs[
        (programs["year"] == selected_year) &
        (programs["bac_type"] == BAC_TRACK_ARABIC)
    ].copy()
    filtered_programs["is_new"] = filtered_programs["orientation_score"].fillna(0) <= 0

    bac_formulas = formulas[formulas["bac_type"] == BAC_TRACK_ENGLISH].copy()

    # Standardize string formatting for clean matching joins
    filtered_programs["program_code_3digit"] = filtered_programs["program_code"].astype(str).str[-3:].str.strip().str.zfill(3)
    bac_formulas["program_code_3digit"] = bac_formulas["program_code_3digit"].astype(str).str.strip().str.zfill(3)

    # First merge: Join programs with calculation formulas
    merged_df = filtered_programs.merge(
        bac_formulas[["program_code_3digit", "formula"]],
        on="program_code_3digit",
        how="left"
    )

    # Smart Merge for fiche_details
    if "fiche_id" in fiche.columns and "fiche_id" in merged_df.columns:
        # Cast both sides to str first -- int vs float fiche_id after a CSV round-trip
        # is a common silent-failure mode that makes every row miss the merge.
        fiche["fiche_id"] = fiche["fiche_id"].astype(str)
        merged_df["fiche_id"] = merged_df["fiche_id"].astype(str)
        merged_df = merged_df.merge(fiche, on="fiche_id", how="left", suffixes=('', '_fiche'))
    elif "program_code" in fiche.columns:
        fiche["program_code"] = fiche["program_code"].astype(str).str.strip()
        merged_df["program_code"] = merged_df["program_code"].astype(str).str.strip()
        merged_df = merged_df.merge(fiche, on="program_code", how="left", suffixes=('', '_fiche'))
    else:
        fiche = fiche.rename(columns={"fiche_id": "program_code"})
        fiche["program_code"] = fiche["program_code"].astype(str).str.strip()
        merged_df["program_code"] = merged_df["program_code"].astype(str).str.strip()
        merged_df = merged_df.merge(fiche, on="program_code", how="left", suffixes=('', '_fiche'))

    return merged_df, selected_year


results_df, YEAR_FILTER = load_and_prep_data()

# =====================================================================
# 3. YOUR MARKS -> FG -> T_score PER PROGRAM
# =====================================================================
YOUR_ACTUAL_MARKS = {
    "MG":   (9.16, 10.0), "M": (7.25, 8.0), "Algo": (8.5, 9.16),
    "SP":   (3.75, None), "STI": (10.4, 12.65), "F": (8.0, 6.25),
    "Ang":  (15.0, 17.5), "A": (9.75, 9.25), "PH": (6.25, None),
    "EP":   (18.67, None), "ESP": (13.0, None)
}

subjects_meta = {
    "MG": "Moyenne Générale", "M": "Mathématiques", "Algo": "Algorithmique",
    "SP": "Sciences Physiques", "STI": "Sciences & Tech de l'Info", "F": "Français",
    "Ang": "Anglais", "A": "Arabe", "PH": "Philosophie", "EP": "Éducation Physique",
    "ESP": "Espagnol"
}

st.sidebar.header("📊 Your Loaded Marks")
user_marks = {}

for code, name in subjects_meta.items():
    default_main, default_control = YOUR_ACTUAL_MARKS[code]
    has_control_session = default_control is not None

    with st.sidebar.expander(f"{name} ({code})", expanded=(code in ["MG", "M", "Algo", "STI"])):
        col1, col2 = st.columns([2, 1])
        with col1:
            main_val = st.number_input("Main", min_value=0.0, max_value=20.0, value=float(default_main), step=0.01, key=f"{code}_main")
        with col2:
            sat_control = st.checkbox("Control?", value=has_control_session, key=f"{code}_sat")

        control_val = None
        if sat_control:
            ctrl_initial = float(default_control) if has_control_session else 10.0
            control_val = st.number_input("Score", min_value=0.0, max_value=20.0, value=ctrl_initial, step=0.01, key=f"{code}_ctrl")

        user_marks[code] = (main_val, control_val)


def calculate_final_mark(main, control=None):
    return main if control is None else (2 * main + control) / 3


calculated_marks = {sub: calculate_final_mark(*marks) for sub, marks in user_marks.items()}

FG = (
    4 * calculated_marks["MG"] + 1.5 * calculated_marks["M"] + 1.5 * calculated_marks["Algo"]
    + 0.5 * calculated_marks["SP"] + 0.5 * calculated_marks["STI"] + calculated_marks["F"] + calculated_marks["Ang"]
)

eval_variables = {"FG": FG, **calculated_marks, "max": max}


def parse_and_eval_formula(formula, variables):
    if pd.isna(formula):
        return None
    f_str = str(formula).strip()
    f_str = re.sub(r'(\d+(?:\.\d+)?)([a-zA-Z])', r'\1*\2', f_str)
    f_str = f_str.replace("Max", "max").replace("|", ",")
    try:
        return eval(f_str, {"__builtins__": {}}, variables)
    except Exception:
        return None


if results_df is not None:
    results_df["T_score"] = results_df["formula"].apply(lambda f: parse_and_eval_formula(f, eval_variables))
    results_df["safety_margin"] = results_df["T_score"] - results_df["orientation_score"]
    results_df.loc[results_df["is_new"], "safety_margin"] = pd.NA

col_m1, _ = st.columns(2)
with col_m1:
    st.metric(label="Calculated Formule Globale (FG)", value=f"{FG:.2f}")

st.markdown("---")

# =====================================================================
# 4. SEARCH & FILTER -- fully reactive, no button, no staleness
# =====================================================================
if results_df is None:
    st.stop()

st.subheader("🔍 Search")

reset_clicked = st.button("↺ Reset all filters")
if reset_clicked:
    for key in [
        "above_input", "below_input", "keyword_input", "id_input",
        "university_filter", "institution_filter", "program_filter",
        "sort_col", "sort_dir",
    ]:
        st.session_state.pop(key, None)
    st.rerun()

col_id, col_kw = st.columns([1, 2])
with col_id:
    id_input = st.text_input("Program Code (ID)", value="", placeholder="e.g. 10101", key="id_input")
with col_kw:
    keyword_input = st.text_input("Keyword (searches every column)", value="", placeholder="e.g. 'سوسة', 'INSAT', 'الهندسة'", key="keyword_input")

col_above, col_below = st.columns(2)
with col_above:
    above_input = st.number_input(
        "Max points ABOVE your score (Reach) — 0 = no limit",
        min_value=0, max_value=50, value=5, key="above_input",
        disabled=bool(id_input),
    )
with col_below:
    below_input = st.number_input(
        "Max points BELOW your score (Safety) — 0 = no limit",
        min_value=0, max_value=100, value=15, key="below_input",
        disabled=bool(id_input),
    )

if id_input:
    st.caption("🔒 Program ID is set, so the score-range filters above are disabled — ID search looks for that exact program regardless of range.")

# ---- Apply search filters (id / keyword / score range) ----
base = results_df.dropna(subset=["T_score"]).copy()

if id_input:
    df_search = base[
        base["program_code"].astype(str).str.contains(id_input, case=False, na=False, regex=False)
    ]
else:
    df_established = base[~base["is_new"]]
    df_new = base[base["is_new"]]  # no prior cutoff -- range filters don't apply, always shown

    if above_input > 0:
        df_established = df_established[df_established["orientation_score"] <= df_established["T_score"] + above_input]
    if below_input > 0:
        df_established = df_established[df_established["orientation_score"] >= df_established["T_score"] - below_input]

    df_search = pd.concat([df_established, df_new])

if keyword_input:
    mask = pd.Series(False, index=df_search.index)
    for col in df_search.columns:
        mask |= df_search[col].astype(str).str.contains(keyword_input, case=False, na=False, regex=False)
    df_search = df_search[mask]

program_status_filter = st.multiselect(
    "Program status",
    options=["New (no prior cutoff)", "Established"],
    default=["New (no prior cutoff)", "Established"],
    key="status_filter",
)

if not program_status_filter:
    df_search = df_search.iloc[0:0]  # nothing selected -- show nothing rather than silently ignoring the filter
else:
    show_new = "New (no prior cutoff)" in program_status_filter
    show_established = "Established" in program_status_filter
    if show_new and not show_established:
        df_search = df_search[df_search["is_new"]]
    elif show_established and not show_new:
        df_search = df_search[~df_search["is_new"]]
    # both selected -> no filtering needed, that's "All"

new_count = int(df_search["is_new"].sum())
st.caption(f"**{len(df_search)}** programs match your search" + (f" — **{new_count}** of them new (no prior cutoff)." if new_count else "."))

st.markdown("---")
st.subheader("🎛️ Refine")
st.caption("These narrow the search results above, and cascade: picking a university narrows which institutions/programs show up next.")

col_r1, col_r2, col_r3 = st.columns(3)

with col_r1:
    university_options = sorted(df_search["university"].dropna().unique())
    selected_universities = st.multiselect("University", university_options, default=[], key="university_filter")

df_refine = df_search[df_search["university"].isin(selected_universities)] if selected_universities else df_search

with col_r2:
    institution_options = sorted(df_refine["institution"].dropna().unique())
    selected_institutions = st.multiselect("Institution", institution_options, default=[], key="institution_filter")

df_refine = df_refine[df_refine["institution"].isin(selected_institutions)] if selected_institutions else df_refine

with col_r3:
    program_options = sorted(df_refine["program_name"].dropna().unique())
    selected_programs = st.multiselect("Program", program_options, default=[], key="program_filter")

df_display = df_refine[df_refine["program_name"].isin(selected_programs)] if selected_programs else df_refine

st.markdown("---")

# =====================================================================
# 5. RESULTS TABLE
# =====================================================================
st.subheader(f"📋 Results ({len(df_display)})")

if df_display.empty:
    st.info("No programs match your current filters. Try widening the range, clearing a Refine filter, or hitting Reset.")
    st.stop()

col_sort1, col_sort2 = st.columns([2, 1])
with col_sort1:
    sort_col = st.selectbox(
        "Sort by",
        options=["Safety Margin", "your score", f"{YEAR_FILTER} Last Score", "Program Name"],
        index=0,
        key="sort_col",
    )
with col_sort2:
    sort_dir = st.radio("Order", options=["Descending", "Ascending"], horizontal=True, key="sort_dir")

table_cols = {
    "program_code": "Code",
    "program_name": "Program Name",
    "institution": "Institution",
    "university": "University",
    "formula": "Formula",
    "orientation_score": f"{YEAR_FILTER} Last Score",
    "T_score": "your score",
    "safety_margin": "Safety Margin",
}

master_view = df_display[list(table_cols.keys()) + ["is_new"]].rename(columns=table_cols)
master_view = master_view.sort_values(by=sort_col, ascending=(sort_dir == "Ascending")).reset_index(drop=True)

master_view[f"{YEAR_FILTER} Last Score"] = master_view.apply(
    lambda r: "🆕 NEW" if r["is_new"] else f"{r[f'{YEAR_FILTER} Last Score']:.2f}", axis=1
)
master_view["Safety Margin"] = master_view.apply(
    lambda r: "—" if r["is_new"] else f"{r['Safety Margin']:+.2f}", axis=1
)
master_view["Program Name"] = master_view.apply(
    lambda r: ("🆕 " if r["is_new"] else "") + r["Program Name"], axis=1
)
master_view = master_view.drop(columns=["is_new"])

def style_margin_cells(val):
    try:
        clean_val = float(str(val).replace('+', '').strip())
        return "color: #2ebd59; font-weight: bold;" if clean_val >= 0 else "color: #ff4b4b; font-weight: bold;"
    except Exception:
        return ""


styled_master = master_view.style.format({
    "your score": "{:.2f}",
}).map(style_margin_cells, subset=["Safety Margin"])

st.markdown("💡 *Click any row to load its fiche details and alternative locations below.*")

grid_response = st.dataframe(
    styled_master,
    use_container_width=True,
    hide_index=True,
    selection_mode="single-row",
    on_select="rerun",
)

selected_rows = grid_response.get("selection", {}).get("rows", [])

if selected_rows:
    selected_code = master_view.iloc[selected_rows[0]]["Code"]
    prog = df_display[df_display["program_code"].astype(str) == str(selected_code)].iloc[0]
else:
    prog = master_view.iloc[0]
    prog = df_display[df_display["program_code"].astype(str) == str(prog["Code"])].iloc[0]
    st.caption("No row selected — showing the top result. Click a row above to inspect a different program.")

# =====================================================================
# 6. DETAILED ARABIC FICHE INSPECTOR
# =====================================================================
st.markdown("---")
st.subheader("📄 بطاقة معلومات الشعبة التفصيلية (Program Fiche Details)")

with st.container(border=True):
    st.markdown(f"### {prog['program_name']}")
    st.markdown(f"**🏛️ المؤسسة الجامعية الحالية:** {prog['institution']} | {prog['university']}")
    st.markdown(f"**🧮 صيغة حساب السكور المعتمدة للشعبة (Score Formula):** `{prog.get('formula', 'FG')}`")
    st.markdown("---")

    is_eligible_7pc = False
    if "التنفيل الجغرافي 7%" in prog and not pd.isna(prog["التنفيل الجغرافي 7%"]):
        if "نعم" in str(prog["التنفيل الجغرافي 7%"]):
            is_eligible_7pc = True

    base_score = prog["T_score"]
    base_margin = prog["safety_margin"]

    col_info, col_base, col_bonus = st.columns([1.2, 2, 2])

    with col_info:
        st.metric(label="رمز التوجيه (Code)", value=prog["program_code"])
        st.metric(label=f"{YEAR_FILTER} Last Score", value=f"{prog['orientation_score']:.2f}")

    with col_base:
        st.markdown("**🔵 Standard Metrics (No Bonus)**")
        st.metric(label="your score (Base)", value=f"{base_score:.2f}")
        st.metric(label="Safety Margin (Base)", value=f"{base_margin:+.2f}")

    with col_bonus:
        st.markdown("**✨ Geographic Bonus Metrics (+7%)**")
        if is_eligible_7pc:
            bonus_score = base_score * 1.07
            bonus_margin = bonus_score - prog["orientation_score"]
            st.metric(label="your score (With +7%)", value=f"{bonus_score:.2f}")
            st.metric(label="Safety Margin (With +7%)", value=f"{bonus_margin:+.2f}")
        else:
            st.metric(label="your score (With +7%)", value="N/A")
            st.markdown("<span style='color:#ff4b4b; font-weight:bold;'>🔴 Not Eligible</span><br><small>This selection does not provide geographical bonuses.</small>", unsafe_allow_html=True)

    st.markdown("---")

    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("#### ℹ️ الهوية الأكاديمية")
        st.markdown(f"**🔹 نوع الشهادة الجامعية:** {prog.get('نوع الشهادة الجامعية', 'غير متوفر')}")
        st.markdown(f"**🔹 مدة الدراسة:** {prog.get('مدة الدراسة', 'غير متوفر')}")
        st.markdown(f"**🔹 المجال الرئيسي:** {prog.get('المجال', 'غير متوفر')}")
        st.markdown(f"**🔹 التخصصات المتاحة:** {prog.get('التخصصات', 'غير متوفر')}")

    with col_right:
        st.markdown("#### ⚠️ الشروط والتنفيل الجغرافي")

        def render_status(val):
            if pd.isna(val):
                return "⚪ غير محدد"
            return "🟢 نعم" if "نعم" in str(val) else "🔴 لا"

        st.markdown(f"**📍 التنفيل الجغرافي 7%:** {render_status(prog.get('التنفيل الجغرافي 7%'))}")
        st.markdown(f"**📝 تتطلب اجتياز اختبارات مسبقة:** {render_status(prog.get('تتطلب اجتياز اختبارات مسبقة'))}")
        st.markdown(f"**🔒 لها شروط قبول خاصة:** {render_status(prog.get('لها شروط خاصة'))}")
        st.markdown(f"**🧮 صيغة حساب النقاط التكميلية:** `{prog.get('صيغة حساب مجموع النقاط', 'غير متوفر')}`")

    st.markdown("---")
    col_fut1, col_fut2 = st.columns(2)
    with col_fut1:
        st.markdown("#### 🚀 الآفاق الجامعية (Academic Prospects)")
        st.info(prog.get('آفاق جامعية', 'لا توجد معلومات مضافة للمسار الأكاديمي.'))
    with col_fut2:
        st.markdown("#### 💼 الآفاق المهنية (Career Prospects)")
        st.success(prog.get('آفاق مهنية', 'لا توجد معلومات مضافة للوظائف المتاحة.'))

    st.markdown("---")
    st.markdown("#### 📍 مؤسسات أخرى توفر نفس هذه الشعبة (Alternative Locations)")

    # Search the FULL dataset here, not the filtered df_display -- an alternative
    # location shouldn't be hidden just because it falls outside the current
    # score range / keyword / refine filters.
    other_places = results_df[
        results_df["T_score"].notna() &
        (results_df["program_code_3digit"] == prog["program_code_3digit"]) &
        (results_df["program_code"] != prog["program_code"])
    ].copy()

    if not other_places.empty:
        st.markdown(f"The following options share the same program identifier (**{prog['program_code_3digit']}**) across other institutions:")

        alt_view = other_places[[
            "program_code", "institution", "university", "formula", "orientation_score", "T_score", "safety_margin"
        ]].rename(columns={
            "program_code": "Code",
            "institution": "Institution",
            "university": "University",
            "formula": "Formula",
            "orientation_score": f"{YEAR_FILTER} Last Score",
            "T_score": "your score",
            "safety_margin": "Safety Margin",
        }).sort_values(by="Safety Margin", ascending=False)

        styled_alt = alt_view.style.format({
            f"{YEAR_FILTER} Last Score": "{:.2f}",
            "your score": "{:.2f}",
            "Safety Margin": "{:+.2f}",
        }).map(style_margin_cells, subset=["Safety Margin"])

        st.dataframe(styled_alt, use_container_width=True, hide_index=True)
    else:
        st.markdown("ℹ️ *This program is unique to this institution. No other alternative locations share this 3-digit core code.*")