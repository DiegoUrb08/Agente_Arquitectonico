"""Identidad visual: estilo "blueprint" (la paleta base está en .streamlit/config.toml)."""

import streamlit as st

CSS = """
<style>
.stApp {
    background-image:
        linear-gradient(rgba(56, 189, 248, 0.045) 1px, transparent 1px),
        linear-gradient(90deg, rgba(56, 189, 248, 0.045) 1px, transparent 1px);
    background-size: 32px 32px;
}
h1 {
    font-weight: 800;
    letter-spacing: -0.02em;
    background: linear-gradient(90deg, #38BDF8, #A78BFA 55%, #FBBF24);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}
[data-testid="stBaseButton-primary"] p {
    color: #04263A;
    font-weight: 700;
}
[data-testid="stMetricValue"] {
    font-variant-numeric: tabular-nums;
}
</style>
"""


def aplicar_tema() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
