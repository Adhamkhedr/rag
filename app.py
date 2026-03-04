import streamlit as st
from graph import run_pipeline
from config import CONFIDENCE_THRESHOLD

st.set_page_config(page_title="DocuGen AI", page_icon="📋", layout="wide")

st.title("DocuGen AI")
st.caption("Audit-ready incident reports from AWS CloudTrail logs")

query = st.text_input(
    "Ask about AWS activity:",
    placeholder="e.g., What IAM changes happened yesterday?",
)

if st.button("Generate Report", type="primary", disabled=not query):
    with st.spinner("Analyzing CloudTrail logs and generating report..."):
        try:
            result = run_pipeline(query)

            st.markdown("---")
            st.markdown(result["final_report"])

            # Confidence indicator
            confidence = result["retrieval_confidence"]
            if confidence >= CONFIDENCE_THRESHOLD:
                st.success(f"Retrieval confidence: {confidence:.2f} — well-grounded in documentation")
            else:
                st.warning(
                    f"Low retrieval confidence: {confidence:.2f} — "
                    "report may have limited documentation grounding"
                )

            # Metadata
            with st.expander("Report Metadata"):
                st.json(result["metadata"])

            # Download
            st.download_button(
                label="Download Report (.md)",
                data=result["final_report"],
                file_name=f"{result['metadata']['report_id']}-report.md",
                mime="text/markdown",
            )

        except Exception as e:
            st.error(f"Error generating report: {e}")
