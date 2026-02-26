"""
HDB Assist AI — Streamlit UI (Flowise-only orchestration)

This file uses Streamlit ONLY for UI:
- Collect user input
- Send input to Flowise Cloud Prediction API
- Parse structured JSON result
- Render recommendation + downloadable report summary

Prereqs:
- .env with:
  FLOWISE_BASE_URL=https://cloud.flowiseai.com
  FLOWISE_CHATFLOW_ID=28bddf08-01dc-4472-aa7f-e6f7e2c0297f
  FLOWISE_API_KEY=YOUR_REAL_API_KEY   (if your flow requires auth)
Run:
  source .venv/bin/activate
  pip install streamlit python-dotenv requests
  streamlit run app1_ui_updated.py
"""

import os
import json
import re
import uuid
import requests
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv


# -------------------------------
# PAGE CONFIG (FIRST STREAMLIT CALL)
# -------------------------------
st.set_page_config(
    page_title="HDB Assist AI",
    page_icon="🏙️",
    layout="wide",
)

# -------------------------------
# STYLES
# -------------------------------
st.markdown(
    """
<style>
:root{
  --primary:#0B5ED7;
  --muted:#6B7280;
  --bg:#F6F8FB;
  --card:#FFFFFF;
  --border:#E7EEF6;
  --danger:#D92D20;
  --warn:#F79009;
  --success:#12B76A;
}
html, body, [class*="css"]{
  font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial;
}
.block-container{padding-top: 1.5rem;}
.hero{
  background: linear-gradient(180deg, #FFFFFF 0%, var(--bg) 100%);
  border:1px solid var(--border);
  border-radius: 18px;
  padding: 18px 20px;
  margin-bottom: 14px;
}
.h1{font-size: 40px; font-weight: 850; color: var(--primary); margin: 0;}
.sub{color: var(--muted); margin-top: 6px; font-size: 14px;}
.badge{
  display:inline-block; padding: 4px 10px; border-radius:999px;
  background:#EEF4FF; color:var(--primary); font-weight:700; font-size:12px;
  border:1px solid #DCE8FF;
}
.card{
  background:var(--card);
  border:1px solid var(--border);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 2px 10px rgba(16,24,40,.06);
}
.kpi{display:flex; gap:10px; flex-wrap:wrap; margin-bottom: 8px;}
.kpi .pill{
  padding: 6px 10px; border-radius: 999px; font-size: 12px; font-weight: 700;
  border:1px solid var(--border); background:#fff;
}
.pill.ok{border-color:rgba(18,183,106,.35); color:var(--success); background:rgba(18,183,106,.06);}
.pill.warn{border-color:rgba(247,144,9,.35); color:var(--warn); background:rgba(247,144,9,.06);}
.pill.danger{border-color:rgba(217,45,32,.35); color:var(--danger); background:rgba(217,45,32,.06);}
.small{color:var(--muted); font-size: 12px;}
hr{border:0;border-top:1px solid var(--border); margin: 10px 0;}
.section-title{font-size: 16px; font-weight: 800; margin: 0 0 6px;}
</style>
""",
    unsafe_allow_html=True,
)

# -------------------------------
# HEADER
# -------------------------------
st.markdown(
    """
<div class="hero">
  <div class="badge">Decision-support • Flowise-orchestrated • Singapore-specific</div>
  <div class="h1">🏙️ HDB Assist AI</div>
  <div class="sub">Streamlit UI → Flowise AgentFlow (logic/RAG) → Streamlit renders structured report.</div>
</div>
""",
    unsafe_allow_html=True,
)

# -------------------------------
# ENV + FLOWISE CONFIG
# -------------------------------
load_dotenv()

FLOWISE_BASE_URL = os.getenv("FLOWISE_BASE_URL", "https://cloud.flowiseai.com").rstrip("/")
FLOWISE_CHATFLOW_ID = os.getenv("FLOWISE_CHATFLOW_ID", "28bddf08-01dc-4472-aa7f-e6f7e2c0297f")
FLOWISE_API_KEY = os.getenv("FLOWISE_API_KEY", "")

# -------------------------------
# SESSION STATE
# -------------------------------
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "sid" not in st.session_state:
    st.session_state.sid = str(uuid.uuid4())

# -------------------------------
# SIDEBAR
# -------------------------------
with st.sidebar:
    st.header("⚙️ Controls")
    show_debug = st.checkbox("Show debug payload", value=False)

    st.markdown("---")
    st.subheader("🔗 Flowise Cloud")
    st.caption(f"Base URL: {FLOWISE_BASE_URL}")
    st.caption(f"Chatflow ID: {FLOWISE_CHATFLOW_ID[:8]}…{FLOWISE_CHATFLOW_ID[-6:]}" if FLOWISE_CHATFLOW_ID else "Chatflow ID: (not set)")
    st.caption("Auth: ✅ API key set" if FLOWISE_API_KEY else "Auth: ⚠️ No API key in .env")

    st.markdown("---")
    st.subheader("🚨 Emergency")
    st.caption("If there is immediate danger, call **995 (SCDF)** or **999 (Police)**.")

    st.markdown("---")
    st.subheader("🛡 Responsible AI")
    st.caption("This is a decision-support prototype. It does **not** file reports to agencies. Verify urgent cases with official channels.")

# -------------------------------
# FLOWISE HELPERS
# -------------------------------
def _extract_json_anywhere(text: str):
    t = (text or "").strip()
    if not t:
        return None
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None

def extract_json_from_flowise_response(resp: dict) -> dict:
    parsed = _extract_json_anywhere(resp.get("text", ""))
    if parsed:
        return parsed

    executed = resp.get("agentFlowExecutedData") or []
    for node in reversed(executed):
        node_data = node.get("data") or {}
        out = node_data.get("output") or {}
        if isinstance(out, dict):
            parsed = _extract_json_anywhere(out.get("content", ""))
            if parsed:
                return parsed
            for v in out.values():
                if isinstance(v, str):
                    parsed = _extract_json_anywhere(v)
                    if parsed:
                        return parsed

    raise RuntimeError("Flowise response did not contain JSON. Ensure your final node returns JSON-only in the output.")

def call_flowise(question: str, extra: dict | None = None):
    if not FLOWISE_CHATFLOW_ID:
        raise RuntimeError("FLOWISE_CHATFLOW_ID is missing. Add it to .env")

    url = f"{FLOWISE_BASE_URL}/api/v1/prediction/{FLOWISE_CHATFLOW_ID}"
    payload = {"question": question, "sessionId": st.session_state.sid}
    if extra:
        payload["overrideConfig"] = extra

    headers = {"Content-Type": "application/json"}
    if FLOWISE_API_KEY:
        headers["Authorization"] = f"Bearer {FLOWISE_API_KEY}"

    r = requests.post(url, json=payload, headers=headers, timeout=180)
    r.raise_for_status()
    raw = r.json()
    data = extract_json_from_flowise_response(raw)
    return data, raw

# -------------------------------
# RENDERING
# ------------------------------
def render_decision(data: dict):
    urgency = data.get("urgency_level", "Normal")
    authority = data.get("recommended_authority", "Other")
    authority_details = data.get("recommended_authority_details", "")
    assessment = data.get("assessment", "")
    next_steps = data.get("next_steps", [])
    details_to_prepare = data.get("details_to_prepare", [])
    questions = data.get("questions_if_missing", [])

    pill_class = "ok"
    if urgency == "Emergency":
        pill_class = "danger"
    elif urgency == "High":
        pill_class = "warn"

    html_block = """
    <div class="card">
      <div class="kpi">
        <div class="pill {pill_class}">Urgency: {urgency}</div>
        <div class="pill">Recommended authority: {authority}</div>
      </div>
      <hr/>
      <div class="section-title">Assessment</div>
      {assessment_block}
      <hr/>
      <div class="section-title">Who to contact</div>
      {authority_block}
      <hr/>
      <div class="section-title">What to do now</div>
    </div>
    """

    assessment_block = assessment if assessment else "<span class='small'>(No assessment)</span>"
    authority_block = authority_details if authority_details else "<span class='small'>(Not enough info)</span>"

    html_block = html_block.format(
        pill_class=pill_class,
        urgency=urgency,
        authority=authority,
        assessment_block=assessment_block,
        authority_block=authority_block
    )

    st.markdown(html_block, unsafe_allow_html=True)

    if isinstance(next_steps, list) and next_steps:
        st.markdown("\n".join([f"- {s}" for s in next_steps]))

    st.markdown("**What details to prepare**")
    if isinstance(details_to_prepare, list) and details_to_prepare:
        st.markdown("\n".join([f"- {s}" for s in details_to_prepare]))

    if isinstance(questions, list) and questions:
        st.markdown("**Quick questions (if needed)**")
        st.markdown("\n".join([f"- {q}" for q in questions]))



##def render_decision(data: dict):
##    urgency = data.get("urgency_level", "Normal")
##    authority = data.get("recommended_authority", "Other")
 ##   authority_details = data.get("recommended_authority_details", "")
  ##  assessment = data.get("assessment", "")
  ##  next_steps = data.get("next_steps", [])
  ##  details_to_prepare = data.get("details_to_prepare", [])
  ##  questions = data.get("questions_if_missing", [])

  ##  pill_class = "ok"
  ##  if urgency == "Emergency":
##        pill_class = "danger"
##    elif urgency == "High":
##        pill_class = "warn"
##
##    st.markdown(
##        f"""
####<div class="card">
##  <div class="kpi">
##    <div class="pill {pill_class}">Urgency: {urgency}</div>
##    <div class="pill">Recommended authority: {authority}</div>
##  </div>
##  <hr/>
##  <div class="section-title">Assessment</div>
##  {assessment if assessment else "<span class='small'>(No assessment)</span>"}
##  <hr/>
##  <div class="section-title">Who to contact</div>
##  {authority_details if authority_details else "<span class='small'>(Not enough info in Flowise output)</span>"}
##  <hr/>
##  <div class="section-title">What to do now</div>
##</div>
##""",
##        unsafe_allow_html=True,
##    )
##
##    if isinstance(next_steps, list) and next_steps:
##        st.markdown("\n".join([f"- {s}" for s in next_steps]))
##    else:
##        st.caption("No next steps returned.")

##    st.markdown("**What details to prepare**")
##    if isinstance(details_to_prepare, list) and details_to_prepare:
##        st.markdown("\n".join([f"- {s}" for s in details_to_prepare]))
##    else:
##        st.caption("No details checklist returned.")

##    if isinstance(questions, list) and questions:
##        st.markdown("**Quick questions (if needed)**")
##        st.markdown("\n".join([f"- {q}" for q in questions]))

##    report = {
##        "timestamp": datetime.now().isoformat(timespec="seconds"),
##        "urgency_level": urgency,
##        "recommended_authority": authority,
##        "recommended_authority_details": authority_details,
##        "assessment": assessment,
##        "next_steps": next_steps,
##        "details_to_prepare": details_to_prepare,
##        "questions_if_missing": questions,
##    }

##    st.markdown("### 📄 Report Summary (copy / download)")
##    st.code(json.dumps(report, indent=2, ensure_ascii=False), language="json")
##    st.download_button(
##        "📥 Download report summary (.txt)",
 ##       data=json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"),
##        file_name="hdb_assist_report_summary.txt",
##        mime="text/plain",
##        use_container_width=True,
##    )

# -------------------------------
# TABS
# -------------------------------
tab_report, tab_chat, tab_eval, tab_about = st.tabs(
    ["📝 Report Issue", "💬 Ask Question", "📊 Evaluation Mode", "ℹ️ About"]
)

# -------------------------------
# TAB: REPORT ISSUE (UI only)
# -------------------------------
with tab_report:
    st.markdown("#### Step 1: Describe your issue")
    with st.form("report_form"):
        issue_text = st.text_area(
            "Issue description",
            placeholder="e.g., The lift at Blk 210 has been down since yesterday. Elderly residents cannot go downstairs.",
            height=130,
        )
        col1, col2 = st.columns([1, 1])
        with col1:
            location = st.text_input("Location (town/estate, block, postal code)", placeholder="e.g., Tampines, Blk 210, 520210")
        with col2:
            issue_category = st.selectbox(
                "Issue category (optional)",
                ["Auto-detect", "Town Council", "Police", "Emergency", "General/Unsure"],
                index=0,
            )

        submitted = st.form_submit_button("🔎 Analyse & Recommend", use_container_width=True)

    if submitted:
        if not issue_text.strip():
            st.warning("Please enter a short issue description.")
        else:
            question = (
f"{issue_text}\n"
f"Location: {location}\n"
f"Category: {issue_category}"
)

            with st.spinner("Sending to Flowise for analysis…"):
                try:
                    data, raw = call_flowise(
                        question=question,
                        extra={"location": location, "issue_category": issue_category},
                    )
                except Exception as e:
                    st.error(f"Flowise call failed: {e}")
                    st.stop()

            st.markdown("### ✅ Recommendation")
            render_decision(data)

            if show_debug:
                with st.expander("🧪 Raw Flowise response (debug)"):
                    st.code(json.dumps(raw, indent=2, ensure_ascii=False))

# -------------------------------
# TAB: ASK QUESTION (Chat UI only)
# -------------------------------
with tab_chat:
    st.caption("Ask questions like: “Who should I contact for lift breakdown in Tampines?” or “How do I report a scam?”")

    for m in st.session_state.chat_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    user_msg = st.chat_input("Type your question about an HDB/estate issue…")

    if user_msg:
        st.session_state.chat_messages.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.markdown(user_msg)

        with st.spinner("Sending to Flowise…"):
            try:
                data, raw = call_flowise(question=user_msg)
            except Exception as e:
                st.session_state.chat_messages.append({"role": "assistant", "content": f"Flowise call failed: {e}"})
                with st.chat_message("assistant"):
                    st.error(f"Flowise call failed: {e}")
                st.stop()

        pretty = f"""**Urgency:** {data.get('urgency_level','Normal')}

**Recommended authority:** {data.get('recommended_authority','Other')}

**Assessment:** {data.get('assessment','')}

**Next steps:**
"""
        steps = data.get("next_steps", [])
        if isinstance(steps, list) and steps:
            pretty += "\n".join([f"- {s}" for s in steps])
        else:
            pretty += "- (No steps returned)"

        details = data.get("recommended_authority_details", "")
        if details:
            pretty += f"\n\n**Who to contact:** {details}"

        st.session_state.chat_messages.append({"role": "assistant", "content": pretty})
        with st.chat_message("assistant"):
            st.markdown(pretty)

        if show_debug:
            with st.expander("🧪 Raw Flowise response (debug)"):
                st.code(json.dumps(raw, indent=2, ensure_ascii=False))

# -------------------------------
# TAB: EVALUATION MODE (UI only)
# -------------------------------
with tab_eval:
    st.markdown("#### Scenario testing (for demo/evaluation)")
    scenarios = {
        "Lift breakdown (Town Council)": {
            "issue": "The lift at Blk 210 has been down since yesterday. Elderly residents cannot go downstairs.",
            "location": "Tampines, Blk 210",
        },
        "Suspected theft (Police)": {
            "issue": "My bicycle was stolen from the void deck bicycle rack. There is CCTV nearby.",
            "location": "Bedok, Blk 123",
        },
        "Fire / smoke smell (Emergency)": {
            "issue": "Strong smoke smell coming from a unit and people are coughing in the corridor.",
            "location": "Jurong West, Blk 45",
        },
        "Unsure / general query": {
            "issue": "Where can I report repeated loud noise late at night in my block?",
            "location": "Sengkang, Blk 88",
        },
    }

    selected = st.selectbox("Select test scenario", list(scenarios.keys()))
    s = scenarios[selected]

    colA, colB = st.columns([2, 1])
    with colA:
        st.text_area("Scenario issue", value=s["issue"], height=110, disabled=True)
        st.text_input("Scenario location", value=s["location"], disabled=True)
    with colB:
        run = st.button("▶ Run evaluation", use_container_width=True)

    if run:
        question = "\n".join([
            s["issue"],
            f"Location: {s['location']}"
        ]).strip()

        with st.spinner("Sending to Flowise for analysis…"):
            try:
                data, raw = call_flowise(question=question, extra={"location": s["location"]})
            except Exception as e:
                st.error(f"Flowise call failed: {e}")
                st.stop()

        st.markdown("### ✅ Recommendation")
        render_decision(data)

        if show_debug:
            with st.expander("🧪 Raw Flowise response (debug)"):
                st.code(json.dumps(raw, indent=2, ensure_ascii=False))

# -------------------------------
# TAB: ABOUT
# -------------------------------
with tab_about:
    st.markdown(
        """
<div class="card">
<b>What this UI does</b><br/>
This Streamlit app is UI-only. It sends the user's text to a Flowise Cloud AgentFlow for:
routing, RAG retrieval, and structured decision output (JSON). Then it renders the result
and provides a downloadable report summary.<br/><br/>

<b>Environment variables</b>
<ul>
<li><code>FLOWISE_BASE_URL</code> (default: https://cloud.flowiseai.com)</li>
<li><code>FLOWISE_CHATFLOW_ID</code> (your agentflow id)</li>
<li><code>FLOWISE_API_KEY</code> (if your flow is protected)</li>
</ul>

<b>Run</b><br/>
<code>streamlit run app1_ui_updated.py</code>
</div>
""",
        unsafe_allow_html=True,
    )
