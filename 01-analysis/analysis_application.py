import streamlit as st
from pathlib import Path
import re

# ────────────────────────────────────────────────
# Page config
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="GenApp Legacy Modernization",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ────────────────────────────────────────────────
# Custom CSS
# ────────────────────────────────────────────────
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}
    
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1100px;
    }
    
    section[data-testid="stSidebar"] {
        background-color: #1a365d;
    }
    section[data-testid="stSidebar"] * {
        color: #e2e8f0 !important;
    }
    section[data-testid="stSidebar"] .stRadio label {
        font-size: 0.95rem;
        padding: 0.3rem 0;
    }
    
    h1 {
        color: #1a365d;
        border-bottom: 3px solid #3182ce;
        padding-bottom: 0.4rem;
        margin-top: 1rem !important;
    }
    h2 {
        color: #2b6cb0;
        border-bottom: 2px solid #bee3f8;
        padding-bottom: 0.3rem;
        margin-top: 1.8rem !important;
    }
    h3 {
        color: #2c5282;
        margin-top: 1.4rem !important;
    }
    h4 {
        color: #2a4365;
    }
    
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 1rem 0 1.5rem 0;
        font-size: 0.92rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    th {
        background-color: #2b6cb0;
        color: white;
        font-weight: 600;
        padding: 0.6rem 0.8rem;
        text-align: left;
    }
    td {
        padding: 0.5rem 0.8rem;
        border-bottom: 1px solid #e2e8f0;
        vertical-align: top;
    }
    tr:nth-child(even) { background-color: #f7fafc; }
    tr:hover { background-color: #ebf8ff; }
    
    code {
        background-color: #edf2f7;
        color: #c53030;
        padding: 0.15rem 0.4rem;
        border-radius: 4px;
        font-size: 0.9em;
    }
    
    pre {
        background-color: #1a202c;
        color: #e2e8f0;
        padding: 1rem 1.2rem;
        border-radius: 8px;
        overflow-x: auto;
        font-size: 0.9rem;
        line-height: 1.5;
    }
    pre code {
        background: transparent;
        color: inherit;
        padding: 0;
    }
    
    hr {
        border: none;
        border-top: 2px solid #e2e8f0;
        margin: 2rem 0;
    }
    
    ul, ol {
        padding-left: 1.5rem;
        line-height: 1.65;
    }
    
    blockquote {
        border-left: 4px solid #3182ce;
        background-color: #ebf8ff;
        padding: 0.8rem 1.2rem;
        margin: 1rem 0;
        color: #2c5282;
        border-radius: 0 6px 6px 0;
    }
    
    p, li {
        line-height: 1.65;
        color: #2d3748;
    }
    
    strong { color: #1a202c; }
</style>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────
# Document catalog
# ────────────────────────────────────────────────
DOCS = {
    "Application Inventory": {
        "file": "01_inventory/GenApp_Application_Inventory.md",
        "icon": "📦"
    },
    "Dependency Reference": {
        "file": "02_dependencies/GenApp_Dependency_Reference.md",
        "icon": "🔗"
    },
    "Business Rules": {
        "file": "03_business_rules/GenApp_Business_Rules.md",
        "icon": "📜"
    },
    "Complexity Analysis": {
        "file": "04_complexity/GenApp_Complexity_Analysis.md",
        "icon": "📊"
    },
    "Database Analysis": {
        "file": "GenApp_Database_Analysis.md",
        "icon": "🗄️"
    },
    "Transaction Matrix": {
        "file": "06_transaction_matrix/GenApp_Transaction_Matrix.md",
        "icon": "📜"
    },
    "CRUD Matrix": {
        "file": "07_CRUD_Matrix/GenApp_CRUD_Matrix.md",
        "icon": "📊"
    },
    "Legacy to Modern Mapping": {
        "file": "08_Legacy_to_Modern_Mapping/GenApp_Legacy_Modern_Mapping.md",
        "icon": "🔗"
    },
}

# All MD files are in the same folder as this app.py
BASE_PATH = Path(__file__).parent

# ────────────────────────────────────────────────
# Sidebar navigation
# ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## GenApp Reports")
    st.markdown("---")
    
    choice = st.radio(
        "Select a document",
        options=list(DOCS.keys()),
        format_func=lambda x: f"{DOCS[x]['icon']}  {x}",
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.caption("Legacy Modernization Assessment")

# ────────────────────────────────────────────────
# Load & render selected document
# ────────────────────────────────────────────────
selected = DOCS[choice]
md_path = BASE_PATH / selected["file"]

if not md_path.exists():
    st.error(f"File not found: `{selected['file']}`")
    st.stop()

content = md_path.read_text(encoding="utf-8")

# Special handling for Database Analysis – replace missing ERD image
if selected["file"] == "GenApp_Database_Analysis.md":
    parts = re.split(
        r'!\[GenApp Db2 Entity Relationship Diagram\]\(genapp_db2_erd\.png\)',
        content,
        maxsplit=1
    )
    
    # Content before the image
    if parts:
        st.markdown(parts[0], unsafe_allow_html=False)
    
    # Inject Graphviz ERD
    erd_dot = """
    digraph GenApp_ERD {
        rankdir=TB;
        node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11];
        edge [fontname="Helvetica", fontsize=10];

        customer        [label="customer\\n─────────────\\nPK customerNumber (IDENTITY)", fillcolor="#BEE3F8"];
        customer_secure [label="customer_secure\\n─────────────\\nPK customerNumber", fillcolor="#E2E8F0"];
        policy          [label="policy\\n─────────────\\nPK policyNumber (IDENTITY)\\nFK customerNumber\\npolicyType (M/E/H/C)", fillcolor="#BEE3F8"];
        endowment       [label="endowment\\n(type = E)\\n─────────────\\nPK/FK policyNumber", fillcolor="#C6F6D5"];
        house           [label="house\\n(type = H)\\n─────────────\\nPK/FK policyNumber", fillcolor="#C6F6D5"];
        motor           [label="motor\\n(type = M)\\n─────────────\\nPK/FK policyNumber", fillcolor="#C6F6D5"];
        commercial      [label="commercial\\n(type = C)\\n─────────────\\nPK/FK PolicyNumber", fillcolor="#C6F6D5"];
        claim           [label="claim\\n─────────────\\nPK ClaimNumber (IDENTITY)\\nFK PolicyNumber", fillcolor="#FED7D7"];

        customer        -> customer_secure [label="1 : 0..1\\nON DELETE CASCADE"];
        customer        -> policy          [label="1 : N\\nON DELETE CASCADE"];
        policy          -> endowment       [label="1 : 0..1  (type=E)\\nON DELETE CASCADE"];
        policy          -> house           [label="1 : 0..1  (type=H)\\nON DELETE CASCADE"];
        policy          -> motor           [label="1 : 0..1  (type=M)\\nON DELETE CASCADE"];
        policy          -> commercial      [label="1 : 0..1  (type=C)\\nON DELETE CASCADE"];
        policy          -> claim           [label="1 : N\\nON DELETE CASCADE"];
    }
    """
    try:
        st.graphviz_chart(erd_dot, use_container_width=True)
    except Exception:
        st.code(erd_dot, language="dot")
    
    # Content after the image
    if len(parts) > 1:
        st.markdown(parts[1], unsafe_allow_html=False)

else:
    # All other documents
    st.markdown(content, unsafe_allow_html=False)