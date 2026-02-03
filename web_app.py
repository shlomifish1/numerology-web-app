
import streamlit as st
import datetime
import os
import sys
from io import BytesIO
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Add current directory to path so imports work correctly if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from numerology_calculator import NumerologyCalculator
from config_manager import ConfigManager
from gpt_report import generate_person_report
import personal_y

# --- Page Config ---
st.set_page_config(
    page_title="מחשבון נומרולוגי - Web",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- RTL Styling ---
st.markdown("""
<style>
    .stApp {
        direction: rtl;
        text-align: right;
    }
    /* Reverse alignment for inputs/labels to feel natural in RTL */
    .stTextInput > label, .stDateInput > label, .stSelectbox > label, .stNumberInput > label {
        display: -webkit-box;
        display: -ms-flexbox;
        display: flex;
        flex-direction: row-reverse;
        justify-content: flex-start;
        width: 100%;
        margin-left: auto;
    }
    /* Fix for markdown headers alignment */
    h1, h2, h3, h4, h5, h6, p, div {
        text-align: right;
    }
    
    /* Hide some default Streamlit hamburger menu/footer for cleaner look */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
</style>
""", unsafe_allow_html=True)

def _set_rtl_paragraph(paragraph):
    """ Helper function to set paragraph to RTL and right-aligned. """
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    paragraph.paragraph_format.rtl = True

def generate_docx_bytes(calc, gender_key, ai_report_text=None):
    """Generates the Word document in memory and returns a BytesIO object."""
    document = Document()
    
    # Title
    heading = document.add_heading(f'דוח נומרולוגי עבור: {calc.full_name}', level=0)
    _set_rtl_paragraph(heading)
    
    # Info
    p = document.add_paragraph(f"תאריך לידה: {calc.p_day}/{calc.p_month}/{calc.p_year} (מקורי: {calc.full_date_short})") 
    _set_rtl_paragraph(p)
    p = document.add_paragraph(f"מין: {'זכר' if gender_key == 'male' else 'נקבה'}")
    _set_rtl_paragraph(p)
    p = document.add_paragraph(f"תאריך הפקת הדוח: {datetime.date.today().strftime('%d/%m/%Y')}")
    _set_rtl_paragraph(p)
    document.add_paragraph()

    # AI Report Section (if available)
    if ai_report_text:
        h = document.add_heading('המלצת עומק (AI)', level=1)
        _set_rtl_paragraph(h)
        p = document.add_paragraph(ai_report_text)
        _set_rtl_paragraph(p)
        document.add_paragraph()

    # Destiny
    if calc.final_number_destiny is not None:
        h = document.add_heading('מספר ייעוד (דרך חיים)', level=1)
        _set_rtl_paragraph(h)
        p = document.add_paragraph(f"המספר המחושב: {calc.final_number_destiny}")
        _set_rtl_paragraph(p)
        interpretation = calc.get_interpretation("destiny", calc.final_number_destiny, gender_key)
        p = document.add_paragraph(interpretation)
        _set_rtl_paragraph(p)
        document.add_paragraph()

    # Personal Year
    if calc.shana_ishit is not None:
        h = document.add_heading('שנה אישית', level=1)
        _set_rtl_paragraph(h)
        p = document.add_paragraph(f"השנה האישית שלך: {calc.shana_ishit}")
        _set_rtl_paragraph(p)
        interpretation = calc.get_interpretation("personal_year", calc.shana_ishit, gender_key)
        p = document.add_paragraph(interpretation)
        _set_rtl_paragraph(p)
        document.add_paragraph()
    
    # Birth Day
    if calc.p_day is not None:
        h = document.add_heading('יום לידה', level=1)
        _set_rtl_paragraph(h)
        p = document.add_paragraph(f"יום הלידה המצומצם: {calc.p_day}")
        _set_rtl_paragraph(p)
        interpretation = calc.get_interpretation("birth_day", calc.p_day, gender_key)
        p = document.add_paragraph(interpretation)
        _set_rtl_paragraph(p)
        document.add_paragraph()

    # Peaks and Challenges
    h_main_peaks = document.add_heading('פסגות ואתגרים', level=1)
    _set_rtl_paragraph(h_main_peaks)
    
    peaks_data = [
        ("תקופה ראשונה", calc.peak1_reduced, calc.challenge1_reduced, f"עד גיל {calc.first_pick_start}"),
        ("תקופה שנייה", calc.peak2_reduced, calc.challenge2_reduced, f"מגיל {calc.first_pick_start + 1} עד {calc.second_pick_start - 1}"),
        ("תקופה שלישית", calc.peak3_reduced, calc.challenge3_reduced, f"מגיל {calc.second_pick_start} עד {calc.third_pick_start - 1}"),
        ("תקופה רביעית", calc.peak4_reduced, calc.challenge4_reduced, f"מגיל {calc.third_pick_start} ואילך")
    ]
    
    for period_name, peak, challenge, age_range in peaks_data:
        h_period = document.add_heading(f"{period_name} ({age_range})", level=2)
        _set_rtl_paragraph(h_period)
        
        p = document.add_paragraph(f"פסגה: {peak}")
        _set_rtl_paragraph(p)
        interp_peak = calc.get_interpretation("peaks_interpretation", peak, gender_key)
        p = document.add_paragraph(interp_peak)
        _set_rtl_paragraph(p)
        
        p = document.add_paragraph(f"אתגר: {challenge}")
        _set_rtl_paragraph(p)
        interp_challenge = calc.get_interpretation("challenges_interpretation", challenge, gender_key)
        p = document.add_paragraph(interp_challenge)
        _set_rtl_paragraph(p)
        
        document.add_paragraph()

    # Save to IO
    bio = BytesIO()
    document.save(bio)
    bio.seek(0)
    return bio

def main():
    st.title("🔮 מערכת דוחות נומרולוגית (גרסת WEB)")
    st.markdown("---")

    # Initialize Config
    config_manager = ConfigManager()
    
    # Initialize Session State
    if "calc_done" not in st.session_state:
        st.session_state["calc_done"] = False
    if "calc_obj" not in st.session_state:
        st.session_state["calc_obj"] = None
    if "gender_key" not in st.session_state:
        st.session_state["gender_key"] = None
    if "ai_report_text" not in st.session_state:
        st.session_state["ai_report_text"] = None

    # --- Sidebar Inputs ---
    with st.sidebar:
        st.header("פרטים אישיים")
        
        first_name = st.text_input("שם פרטי")
        last_name = st.text_input("שם משפחה")
        
        # Date Input: Starts empty (None) for better UX
        dob = st.date_input(
            "תאריך לידה",
            min_value=datetime.date(1920, 1, 1),
            max_value=datetime.date.today(),
            value=None,  # Empty initial value
            format="DD/MM/YYYY" 
        )
        
        gender = st.selectbox("מין", ["זכר", "נקבה"])
        
        calculate_btn = st.button("בצע חישוב", type="primary", use_container_width=True)

    # --- Calculations ---
    if calculate_btn:
        if not first_name or not last_name or dob is None:
            st.error("אנא מלא את כל השדות, כולל תאריך לידה.")
        else:
            # Prepare data for calculator
            day_str = str(dob.day).zfill(2)
            month_str = str(dob.month).zfill(2)
            year_str = str(dob.year)
            gender_key = "male" if gender == "זכר" else "female"

            # Initialize Calculator
            calc = NumerologyCalculator()
            
            try:
                with st.spinner("מבצע חישוב וניתוח נתונים..."):
                    calc.calculate(day_str, month_str, year_str, first_name, last_name, gender_key)
                
                # Save to Session State
                st.session_state["calc_done"] = True
                st.session_state["calc_obj"] = calc
                st.session_state["gender_key"] = gender_key
                st.session_state["ai_report_text"] = None # Reset AI report on new calculation
                
            except Exception as e:
                st.error(f"אירעה שגיאה בעת חישוב הנתונים: {e}")
                st.exception(e)
                st.session_state["calc_done"] = False

    # --- Display Results ---
    if st.session_state.get("calc_done"):
        calc = st.session_state["calc_obj"]
        gender_key = st.session_state["gender_key"]
        
        st.success(f"הדוח הופק עבור: {calc.full_name}")
        
        # --- AI Section ---
        with st.expander("✨ שאל את ה-AI (המלצה אישית)", expanded=False):
            if st.button("קבל המלצת עומק מה-AI"):
                api_key = config_manager.get_api_key("google_ai")
                if not api_key:
                    st.error("לא נמצא מפתח API חוקי בהגדרות. אנא בדוק את הקובץ config.json.")
                else:
                    with st.spinner("ה-AI מנתח את כל המפה... זה עשוי לקחת רגע..."):
                        # Prepare Data Dict
                        ai_data = {
                            "full_name": calc.full_name,
                            "birth_date": f"{calc.p_day}{calc.p_month}{calc.p_year}", # Using original params might be safer if stored, but let's use calc props
                            "personal_day": calc.p_day,
                            "personal_month": calc.p_month,
                            "personal_year": calc.p_year,
                            "destiny_number": calc.final_number_destiny,
                            "personal_year_number": calc.shana_ishit,
                            "hidden_year": calc.shana_nisteret,
                            "age": calc.age,
                            "life_peaks": [calc.peak1_reduced, calc.peak2_reduced, calc.peak3_reduced, calc.peak4_reduced],
                            "challenges": [calc.challenge1_reduced, calc.challenge2_reduced, calc.challenge3_reduced, calc.challenge4_reduced],
                            "quarters": [calc.first_quarter_reduced, calc.second_quarter_reduced, calc.third_quarter_reduced, calc.forth_quarter_reduced],
                            "gender": "זכר" if gender_key == "male" else "נקבה"
                        }
                        # Call AI
                        report = generate_person_report(ai_data, model_name=config_manager.get("active_model", "gemini-flash-latest"), api_key=api_key)
                        st.session_state["ai_report_text"] = report
        
        # Display cached AI report if exists
        if st.session_state["ai_report_text"]:
            st.info(st.session_state["ai_report_text"])

        # --- Export Options (Top) ---
        col_dl, col_blank = st.columns([1, 4])
        with col_dl:
                # Pass AI text to DOCX generator
                docx_file = generate_docx_bytes(calc, gender_key, ai_report_text=st.session_state["ai_report_text"])
                st.download_button(
                    label="📄 הורד דוח Word",
                    data=docx_file,
                    file_name=f"Numerology_Report_{calc.full_name}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary"
                )

        # Tabs for organization
        tab1, tab2, tab3 = st.tabs(["ראשי", "פסגות ואתגרים", "משמעויות מורחבות"])
        
        with tab1:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.image("https://img.icons8.com/color/96/numerology.png", width=64)
                st.metric("מספר ייעוד (גורל)", calc.final_number_destiny)
                with st.expander("פירוש מספר ייעוד"):
                    st.write(calc.get_interpretation("destiny", calc.final_number_destiny, gender_key))

            with col2:
                st.metric("שנה אישית", calc.shana_ishit)
                with st.expander("פירוש שנה אישית"):
                    st.write(calc.get_interpretation("personal_year", calc.shana_ishit, gender_key))

            with col3:
                st.metric("יום לידה", calc.p_day)
                with st.expander("פירוש יום לידה"):
                    # Original Day isn't stored in calc object directly as public generic prop easily,
                    # but we can infer or simpler just show reduced or remove "Original" text if not crucial for now.
                    # Or we can recalculate/store it. Let's stick to reduced or what we have.
                    st.write(f"יום לידה/צמצום: {calc.p_day}")
                    st.write(calc.get_interpretation("birth_day", calc.p_day, gender_key))

            st.markdown("### מפה אישית")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("שם פרטי", calc.first_name_val)
            c2.metric("שם מלא (שאיפה)", calc.full_name_val)
            c3.metric("עיצורים (רושם)", calc.itzurim_val)
            c4.metric("תנועות (נשמה)", calc.aiv_val)

        with tab2:
            st.subheader("פסגות ואתגרים בחיי האדם")
            
            peaks_data = [
                ("תקופה ראשונה", calc.peak1_reduced, calc.challenge1_reduced, f"עד גיל {calc.first_pick_start}"),
                ("תקופה שנייה", calc.peak2_reduced, calc.challenge2_reduced, f"מגיל {calc.first_pick_start+1} עד {calc.second_pick_start-1}"),
                ("תקופה שלישית", calc.peak3_reduced, calc.challenge3_reduced, f"מגיל {calc.second_pick_start} עד {calc.third_pick_start-1}"),
                ("תקופה רביעית", calc.peak4_reduced, calc.challenge4_reduced, f"מגיל {calc.third_pick_start} ואילך"),
            ]
            
            for title, peak, challenge, age in peaks_data:
                with st.container():
                    st.markdown(f"#### {title} ({age})")
                    pc1, pc2 = st.columns(2)
                    pc1.info(f"**פסגה {peak}**")
                    
                    pc2.error(f"**אתגר {challenge}**")
                    st.divider()

        with tab3:
            st.info("כאן יופיעו ניתוחי עומק נוספים (ריבוע פיתגורס, רבעונים ועוד).")
            if calc.shana_nisteret:
                st.write(f"**שנה נסתרת:** {calc.shana_nisteret}")
                st.write(calc.get_interpretation("hidden_year", str(calc.shana_nisteret), gender_key, is_hidden_year=True))
    
    else:
        st.info("הזן פרטים בצד ימין ולחץ על 'בצע חישוב' כדי להתחיל.")

if __name__ == "__main__":
    main()
