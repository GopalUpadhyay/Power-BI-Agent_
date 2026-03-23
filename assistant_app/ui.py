import csv
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from .cli import build_agent
from .fabric_universal import (
    ContextBuilder,
    DataIngestionLayer,
    DuplicateDetectionEngine,
    ExecutionEngine,
    IntentDetectionEngine,
    MetadataStore,
    ModelDiscoveryEngine,
    MultiLanguageGenerationEngine,
    UniversalFabricAssistant,
    configure_openai_client as configure_universal_client,
)
from .model_store import ModelStore
from .training_engine import FabricModelTrainer

logger = logging.getLogger(__name__)


def _context_fingerprint(summary: Dict[str, Any], context: str) -> str:
    """Create a short, stable fingerprint for model context parity checks."""
    try:
        table_count = int(summary.get("table_count", 0))
        col_count = int(summary.get("total_columns", 0))
        rel_count = int(summary.get("relationship_count", 0))
        payload = f"{table_count}|{col_count}|{rel_count}|{context}".encode("utf-8", errors="ignore")
        return hashlib.sha256(payload).hexdigest()[:12]
    except Exception:
        return "unavailable"


def _items_to_dataframe(items: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in items:
        rows.append(
            {
                "name": item.get("name", ""),
                "type": item.get("item_type", ""),
                "description": item.get("description", ""),
                "source": item.get("source", ""),
                "created_at": item.get("created_at", ""),
            }
        )
    return pd.DataFrame(rows)


def _export_created_csv(items: List[Dict[str, Any]], output_path: str) -> str:
    fieldnames = ["name", "item_type", "expression", "description", "source", "created_at"]
    path = Path(output_path).expanduser()

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            if item.get("source") != "generated":
                continue
            writer.writerow(
                {
                    "name": item.get("name", ""),
                    "item_type": item.get("item_type", ""),
                    "expression": item.get("expression", ""),
                    "description": item.get("description", ""),
                    "source": item.get("source", ""),
                    "created_at": item.get("created_at", ""),
                }
            )

    return str(path)


def _registry_path_for_model(model_id: str) -> str:
    return str(Path(__file__).resolve().parents[1] / f".assistant_registry_{model_id}.json")


def _build_agent_for_model(api_key: str, metadata: Dict[str, Any], model_id: str):
    return build_agent(
        api_key=api_key or None,
        metadata_override=metadata,
        registry_path=_registry_path_for_model(model_id),
    )


def _run_field_tests(agent) -> pd.DataFrame:
    rows = []
    created_items = [i for i in agent.registry.items.values() if i.get("source") == "generated"]
    for item in created_items:
        valid, issues = agent.validator.validate_expression(item.get("expression", ""))
        rows.append(
            {
                "name": item.get("name", ""),
                "item_type": item.get("item_type", ""),
                "status": "PASS" if valid else "FAIL",
                "issues": " | ".join(issues) if issues else "",
            }
        )
    return pd.DataFrame(rows)


def _train_active_model(model_store: ModelStore, model_id: str, agent) -> Dict[str, Any]:
    metadata = model_store.load_metadata(model_id)
    expressions: List[str] = []

    # Learn from both existing and generated items currently in registry.
    for item in agent.registry.items.values():
        expr = item.get("expression", "")
        if expr:
            expressions.append(expr)

    # Also learn from stored measures in metadata.
    measures = metadata.get("measures", {}) if isinstance(metadata.get("measures", {}), dict) else {}
    for measure in measures.values():
        if isinstance(measure, dict):
            expr = measure.get("expression", "")
            if expr:
                expressions.append(expr)

    profile = FabricModelTrainer.train(metadata=metadata, expressions=expressions)
    metadata["training_profile"] = profile
    notes = metadata.setdefault("ingestion_notes", [])
    notes.append(
        f"Training completed at {profile.get('trained_at', '')} "
        f"with {profile.get('observed_expression_count', 0)} expressions"
    )
    model_store.save_metadata(model_id, metadata)
    return profile


def _refresh_model_context_automatically(active_model: Dict[str, Any], model_store: ModelStore) -> None:
    """Automatically generate and cache comprehensive model context.
    
    This runs in the background whenever the model is loaded/reloaded,
    so Groq always has fresh complete context without user clicks.
    """
    try:
        from .fabric_universal import ContextBuilder
        
        active_metadata = model_store.load_metadata(active_model["id"])
        
        if not isinstance(active_metadata, dict):
            return
        
        if not active_metadata.get("tables"):
            # No tables yet - clear cached context
            st.session_state.model_context_cache = None
            st.session_state.model_context_summary = None
            st.session_state.model_context_fingerprint = None
            return
        
        # Build comprehensive context
        context_builder = ContextBuilder(active_metadata)
        comprehensive_context = context_builder.build_context()
        summary = context_builder.get_model_summary()
        
        # Cache in session state (persists across reruns)
        st.session_state.model_context_cache = comprehensive_context
        st.session_state.model_context_summary = summary
        st.session_state.model_context_fingerprint = _context_fingerprint(summary, comprehensive_context)
        st.session_state.model_context_model_id = active_model["id"]
        
    except Exception as e:
        # Silently fail - don't block UI if context generation fails
        st.session_state.model_context_cache = None
        st.session_state.model_context_summary = None
        st.session_state.model_context_fingerprint = None


def _display_model_context_automatically(context_title: str = "🧠 LLM Context (What Groq will see)") -> bool:
    """Display cached model context if available.
    
    Returns True if context was displayed, False otherwise.
    """
    try:
        summary = st.session_state.get("model_context_summary")
        context = st.session_state.get("model_context_cache")
        fingerprint = st.session_state.get("model_context_fingerprint")
        
        if not summary or not context:
            return False
        
        # Display context using cached values
        with st.expander(context_title, expanded=False):
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("📊 Tables", summary["table_count"])
            with col2:
                st.metric("🔤 Columns", summary["total_columns"])
            with col3:
                st.metric("📐 Measures", summary["measure_count"])
            with col4:
                st.metric("🔗 Relationships", summary["relationship_count"])
            with col5:
                st.metric("⚙️  Calc Columns", summary["calculated_column_count"])

            if fingerprint:
                st.caption(f"Context fingerprint: {fingerprint}")
            
            st.write("**Available tables:**")
            table_info = ", ".join([f"{t} ({len(cols)} cols)" for t, cols in summary["tables"].items()])
            st.markdown(f"`{table_info}`")
            
            st.write("**Full context:** (Shown below)")
            st.code(context, language="text")
        
        return True
    except Exception as e:
        return False


def _display_generation_packet(item_type: str, output_language: str, usage_target: str, item_name: str, description: str, conditions: str = "") -> None:
    """Display the comprehensive generation packet that will be sent to the LLM provider.
    
    This shows users exactly what information Groq will see for generating code.
    """
    try:
        summary = st.session_state.get("model_context_summary")
        context = st.session_state.get("model_context_cache")
        fingerprint = st.session_state.get("model_context_fingerprint")
        
        if not summary or not context:
            return
        
        with st.expander("📦 **GENERATION PACKET** (All Information Being Sent to Groq)", expanded=True):
            st.write("This packet contains **everything** Groq will see to generate your code:")
            st.divider()
            
            # Part 1: Context
            st.write("### 📊 **Part 1: Model Context (Groq Sees Full Schema)**")
            with st.expander("View Full Model Context"):
                st.code(context, language="text")
            
            # Part 2: Parameters
            st.write("### ⚙️ **Part 2: Your Request Parameters**")
            params_df = pd.DataFrame([
                {"Parameter": "Item Type", "Value": item_type},
                {"Parameter": "Output Language", "Value": output_language},
                {"Parameter": "Usage Target", "Value": usage_target},
                {"Parameter": "Item Name", "Value": item_name},
                {"Parameter": "Description", "Value": description},
                {"Parameter": "Conditions", "Value": conditions if conditions else "(none)"},
            ])
            st.dataframe(params_df, use_container_width=True, hide_index=True)
            
            # Part 3: Model Stats
            st.write("### 📈 **Part 3: Model Summary (Easy Reference)**")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Tables", summary["table_count"])
            with col2:
                st.metric("Columns", summary["total_columns"])
            with col3:
                st.metric("Relationships", summary["relationship_count"])
            with col4:
                st.metric("Measures", summary["measure_count"])
            with col5:
                st.metric("Calc Cols", summary["calculated_column_count"])

            if fingerprint:
                st.caption(f"Context fingerprint: {fingerprint}")
            
            # Part 4: Available Tables
            st.write("### 📋 **Part 4: Available Tables in Model**")
            tables = summary.get("tables", {})
            for table_name, cols in tables.items():
                st.write(f"**{table_name}** ({len(cols)} columns)")
                st.code(", ".join(cols), language="text")
            
            st.divider()
            st.info("✅ **When you click 'Generate', ALL the above information will be sent to Groq** to ensure accurate code generation matching your model schema and request.")
    
    except Exception as e:
        pass  # Silently fail - don't block generation


def _build_universal_assistant(api_key: str, metadata: Optional[Dict[str, Any]] = None):
    store = MetadataStore(metadata=metadata)
    client = configure_universal_client(api_key=api_key or None)
    return UniversalFabricAssistant(
        store=store,
        ingestion=DataIngestionLayer(store),
        discovery=ModelDiscoveryEngine(store),
        detector=IntentDetectionEngine(),
        generator=MultiLanguageGenerationEngine(client=client, context_builder=ContextBuilder(store.metadata)),
        executor=ExecutionEngine(),
        duplicate=DuplicateDetectionEngine(store),
    )


def run_ui() -> None:
    st.set_page_config(
        page_title="Power BI Semantic Model Assistant",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Apply custom theme CSS to ensure colors display correctly
    st.markdown(
        """
        <style>
        /* Root HTML and body - ensure continuous styling */
        html, body {
            margin: 0;
            padding: 0;
        }
        
        /* Main theme colors */
        :root {
            --primary-color: #FF6B35;
            --secondary-color: #F7931E;
            --danger-color: #C1272D;
        }
        
        /* Streamlit app container - continuous background */
        .stApp {
            background-color: #1a1a1a;
            color: #E0E0E0;
        }
        
        /* Main content area - ensure no gaps */
        .main {
            background-color: #1a1a1a;
            padding: 0;
        }
        
        /* Sidebar styling - DARK background like local version */
        [data-testid="stSidebar"] {
            background-color: #262626 !important;
        }
        
        /* Sidebar section - proper padding */
        [data-testid="stSidebar"] section {
            background-color: #262626 !important;
        }
        
        /* Sidebar text, labels, and headers - ALL WHITE */
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] h4,
        [data-testid="stSidebar"] h5,
        [data-testid="stSidebar"] h6,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] div,
        [data-testid="stSidebar"] .stTextInput label,
        [data-testid="stSidebar"] .stSelectbox label,
        [data-testid="stSidebar"] .stCheckbox label,
        [data-testid="stSidebar"] .stRadio label {
            color: #FFFFFF !important;
        }
        
        /* Sidebar input fields - darker background */
        [data-testid="stSidebar"] .stTextInput input,
        [data-testid="stSidebar"] .stNumberInput input,
        [data-testid="stSidebar"] .stSelectbox,
        [data-testid="stSidebar"] input {
            background-color: #1a1a1a !important;
            color: #FFFFFF !important;
            border-color: #444 !important;
            border: 1px solid #444 !important;
        }
        
        [data-testid="stSidebar"] input::placeholder {
            color: #999 !important;
        }
        
        /* Sidebar select dropdown */
        [data-testid="stSidebar"] select,
        [data-testid="stSidebar"] .stSelectbox select {
            background-color: #1a1a1a !important;
            color: #FFFFFF !important;
            border: 1px solid #444 !important;
        }
        
        /* Sidebar buttons - orange with dark theme */
        [data-testid="stSidebar"] .stButton > button {
            background-color: #FF6B35 !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 4px !important;
            font-weight: bold !important;
            width: 100% !important;
            padding: 0.5rem 1rem !important;
        }
        
        [data-testid="stSidebar"] .stButton > button:hover {
            background-color: #F7931E !important;
            color: #FFFFFF !important;
            transform: translateY(-2px);
        }
        
        /* Sidebar checkboxes and radio buttons */
        [data-testid="stSidebar"] .stCheckbox label,
        [data-testid="stSidebar"] .stRadio label {
            color: #FFFFFF !important;
        }
        
        [data-testid="stSidebar"] .stCheckbox {
            color: #FFFFFF !important;
        }
        
        /* Sidebar divider */
        [data-testid="stSidebar"] hr {
            border-color: #444 !important;
        }
        
        /* Main content area - button styling */
        .stButton > button {
            background-color: #FF6B35 !important;
            color: white !important;
            border: none !important;
            border-radius: 4px !important;
            font-weight: bold !important;
            padding: 0.5rem 1rem !important;
        }
        
        .stButton > button:hover {
            background-color: #F7931E !important;
            color: white !important;
        }
        
        /* Title and header styling */
        h1, h2, h3, h4, h5, h6 {
            color: #FF6B35 !important;
        }
        
        /* Main content text color */
        p, span, label {
            color: #E0E0E0 !important;
        }
        
        /* Input field styling - main area */
        input {
            background-color: #2d2d2d !important;
            color: #FFFFFF !important;
            border-color: #444 !important;
        }
        
        select {
            background-color: #2d2d2d !important;
            color: #FFFFFF !important;
            border-color: #444 !important;
        }
        
        /* Tab styling */
        [data-testid="stTabs"] {
            background-color: transparent !important;
        }
        
        .stTabs > button {
            color: #FAFBFC !important;
            background-color: transparent !important;
        }
        
        .stTabs > button[aria-selected="true"] {
            color: #FF6B35 !important;
            border-bottom-color: #FF6B35 !important;
            background-color: transparent !important;
        }
        
        /* Metric containers */
        [data-testid="metric-container"] {
            background-color: #2d2d2d !important;
            border-radius: 8px !important;
            padding: 1rem !important;
        }
        
        /* Cards and containers */
        .stCard {
            background-color: #2d2d2d !important;
            border-color: #444 !important;
            border-radius: 8px !important;
        }
        
        [data-testid="stVerticalBlock"] {
            background-color: #2d2d2d !important;
            border-color: #444 !important;
        }
        
        /* Column styling */
        [data-testid="column"] {
            background-color: transparent !important;
        }
        
        /* Expandable sections */
        .streamlit-expanderHeader {
            background-color: #2d2d2d !important;
            color: #FFFFFF !important;
        }
        
        /* Subheader styling */
        .stSubheader {
            color: #FF6B35 !important;
        }
        
        /* Form styling */
        .stForm {
            border: 1px solid #444 !important;
            border-radius: 8px !important;
            padding: 1rem !important;
            background-color: #262626 !important;
        }
        
        /* Overall layout continuity - remove any gaps */
        #root, [role="main"] {
            background-color: #1a1a1a !important;
        }
        
        /* Ensure full height */
        html, body, #root {
            height: 100%;
            width: 100%;
            margin: 0;
            padding: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Power BI Semantic Model Assistant")
    st.caption(
        "Upload model metadata/files, manage multiple models with cards, and generate artifacts in real time."
    )

    if "model_store" not in st.session_state:
        st.session_state.model_store = ModelStore()

    model_store: ModelStore = st.session_state.model_store
    models = model_store.list_models()

    if not models:
        model_store.create_model("Default Model", "Starter model for quick testing")
        models = model_store.list_models()

    model_map = {m["id"]: m for m in models}
    if "active_model_id" not in st.session_state or st.session_state.active_model_id not in model_map:
        st.session_state.active_model_id = models[0]["id"]

    with st.sidebar:
        st.header("Session")
        api_key_input = st.text_input(
            "Groq API Key (optional override)",
            type="password",
            value="",
            help="Leave blank to use GROQ_API_KEY from .env",
        )
        
        # ===== NEW: Display API Key Status =====
        import os
        env_api_key = os.getenv("GROQ_API_KEY", "").strip()
        effective_key = api_key_input.strip() if api_key_input else env_api_key
        
        # Show visual indicator
        if api_key_input.strip():
            # User provided a key
            st.success("✅ **API Key Added** (from input)")
            key_source = "input field"
        elif env_api_key:
            # Key from .env
            st.info("ℹ️ **API Key Loaded** (from .env)")
            key_source = ".env file"
        else:
            # No key available
            st.error("❌ **No API Key** (Groq features limited)")
            key_source = "not available"
        
        # Show key status in small text
        if effective_key:
            key_preview = effective_key[:8] + "..." + effective_key[-4:]
            st.caption(f"🔐 Key source: {key_source}\n📍 Preview: `{key_preview}`")
        else:
            st.caption("🔐 Key source: not configured\n⚠️ Set GROQ_API_KEY in .env or paste above")
        
        st.divider()
        
        selected_model_id = st.selectbox(
            "Active Model",
            options=list(model_map.keys()),
            format_func=lambda model_id: model_map[model_id]["name"],
            index=list(model_map.keys()).index(st.session_state.active_model_id),
        )
        force_reload = st.button("Reload Active Model")
        st.write("---")
        st.caption("Training Automation")
        auto_train_active = st.checkbox(
            "Auto-train active model on file upload",
            value=st.session_state.get("auto_train_active", True),
            key="auto_train_active",
        )
        auto_train_universal = st.checkbox(
            "Auto-train universal model on ingest/discovery",
            value=st.session_state.get("auto_train_universal", True),
            key="auto_train_universal",
        )

    if selected_model_id != st.session_state.active_model_id:
        st.session_state.active_model_id = selected_model_id
        force_reload = True

    active_model = model_map[st.session_state.active_model_id]
    active_metadata = model_store.load_metadata(active_model["id"])

    if "agent" not in st.session_state or force_reload or st.session_state.get("agent_model_id") != active_model["id"]:
        st.session_state.agent = _build_agent_for_model(
            api_key=api_key_input,
            metadata=active_metadata,
            model_id=active_model["id"],
        )
        st.session_state.agent_model_id = active_model["id"]

    if (
        "universal_assistant" not in st.session_state
        or force_reload
        or st.session_state.get("universal_api_key") != api_key_input
        or st.session_state.get("universal_model_id") != active_model["id"]
    ):
        st.session_state.universal_assistant = _build_universal_assistant(api_key_input, metadata=active_metadata)
        st.session_state.universal_api_key = api_key_input
        st.session_state.universal_model_id = active_model["id"]

    agent = st.session_state.agent
    universal_assistant = st.session_state.universal_assistant
    
    # ===== AUTO-REFRESH MODEL CONTEXT IN BACKGROUND =====
    # This runs automatically on every page load/reload to ensure Groq always has fresh context
    _refresh_model_context_automatically(active_model, model_store)

    all_items = list(agent.registry.items.values())
    generated_items = [i for i in all_items if i.get("source") == "generated"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Items", len(all_items))
    col2.metric("Generated", len(generated_items))
    col3.metric("Flags", len(agent.registry.get_items_by_type("flag")))
    col4.metric("Tables", len(agent.registry.get_items_by_type("table")))

    tab_models, tab_generate, tab_items, tab_schema, tab_tests, tab_exports, tab_fabric, tab_demo = st.tabs(
        [
            "Model Hub",
            "Generate",
            "Created Items",
            "Schema",
            "Field Tests",
            "Exports",
            "Universal Fabric",
            "Demo",
        ]
    )

    with tab_models:
        st.subheader("Model Hub")
        st.write("Create model cards, upload metadata files, and switch to a model-specific workspace.")

        if "relationship_result" not in st.session_state:
            st.session_state.relationship_result = None
        if "relationship_result_model_id" not in st.session_state:
            st.session_state.relationship_result_model_id = None

        with st.form("create_model_form"):
            model_name = st.text_input("New model name", placeholder="Retail Sales Model")
            model_desc = st.text_input("Description", placeholder="Model for North America sales")
            create_model_submit = st.form_submit_button("Create Model")

        if create_model_submit:
            if not model_name.strip():
                st.error("Model name is required.")
            else:
                created = model_store.create_model(model_name.strip(), model_desc.strip())
                st.session_state.active_model_id = created["id"]
                st.success(f"Created model card: {created['name']}")
                st.rerun()

        st.write("### Available Model Cards")
        for model in model_store.list_models():
            c1, c2, c3 = st.columns([3, 0.8, 0.8])
            with c1:
                st.markdown(f"**{model['name']}**")
                st.caption(model.get("description", ""))
                st.caption(f"Created: {model.get('created_at', '')}")
            with c2:
                if st.button("Open", key=f"open_{model['id']}"):
                    st.session_state.active_model_id = model["id"]
                    st.rerun()
            with c3:
                if st.button("🗑️", key=f"delete_{model['id']}", help="Delete this model"):
                    if st.session_state.get(f"confirm_delete_{model['id']}", False):
                        if model_store.delete_model(model["id"]):
                            st.success(f"Deleted model: {model['name']}")
                            if st.session_state.active_model_id == model["id"]:
                                st.session_state.active_model_id = None
                            st.rerun()
                        else:
                            st.error("Failed to delete model")
                    else:
                        st.session_state[f"confirm_delete_{model['id']}"] = True
                        st.warning(f"Click again to confirm deletion of '{model['name']}'")
                        st.rerun()

        st.write("---")
        st.write(f"### Active Model: {active_model['name']}")

        tc0, tc1, tc2, tc3 = st.columns([1, 1, 1, 2])
        with tc0:
            if st.button("📋 View Model", key="view_active_model", help="View full model schema and structure"):
                st.session_state.show_model_view = not st.session_state.get("show_model_view", False)
        with tc1:
            if st.button("🔄 Reload", key="reload_active_model", help="Reload metadata from files"):
                st.session_state.agent = _build_agent_for_model(
                    api_key=api_key_input,
                    metadata=model_store.load_metadata(active_model["id"]),
                    model_id=active_model["id"],
                )
                st.session_state.agent_model_id = active_model["id"]
                st.success("Model reloaded!")
                st.rerun()
        with tc2:
            if st.button("🎓 Train Model", key="train_active_model"):
                with st.spinner("Training on schema + usage patterns..."):
                    profile = _train_active_model(model_store, active_model["id"], agent)
                st.success("Training completed.")
                st.json(
                    {
                        "preferred_table": profile.get("preferred_table"),
                        "preferred_value_column": profile.get("preferred_value_column"),
                        "preferred_date_column": profile.get("preferred_date_column"),
                        "observed_expression_count": profile.get("observed_expression_count"),
                    }
                )
                st.session_state.agent = _build_agent_for_model(
                    api_key=api_key_input,
                    metadata=model_store.load_metadata(active_model["id"]),
                    model_id=active_model["id"],
                )
                st.session_state.agent_model_id = active_model["id"]
                st.rerun()
        with tc3:
            if st.button("🔗 Identify Relationships", key="identify_relationships"):
                with st.spinner("Detecting relationships..."):
                    rel_result = model_store.identify_relationships(active_model["id"])
                st.session_state.relationship_result = rel_result
                st.session_state.relationship_result_model_id = active_model["id"]
                
                # Show immediate feedback
                if rel_result.get("success"):
                    st.success(f"✓ Found {rel_result.get('total_detected', 0)} relationship(s)")
                else:
                    st.error(f"Error: {rel_result.get('message', 'Unknown error')}")
                
                st.session_state.agent = _build_agent_for_model(
                    api_key=api_key_input,
                    metadata=model_store.load_metadata(active_model["id"]),
                    model_id=active_model["id"],
                )
                st.session_state.agent_model_id = active_model["id"]
                st.rerun()
        with tc2:
            tp = active_metadata.get("training_profile", {}) if isinstance(active_metadata, dict) else {}
            if tp:
                st.caption(
                    "Last training profile: "
                    f"table={tp.get('preferred_table', 'n/a')}, "
                    f"value={tp.get('preferred_value_column', 'n/a')}, "
                    f"date={tp.get('preferred_date_column', 'n/a')}"
                )
            else:
                st.caption("No training profile yet. Click 'Train Active Model' to learn your model patterns.")

        if st.session_state.get("relationship_result_model_id") == active_model["id"]:
            rel_result = st.session_state.get("relationship_result") or {}
            relationship_rows = rel_result.get("relationships", []) if isinstance(rel_result, dict) else []
            
            # Display message
            total_count = rel_result.get("total_detected", len(relationship_rows))
            new_count = rel_result.get("new_relationships", 0)
            
            if total_count > 0:
                st.success(
                    f"✓ Identified {total_count} relationship(s) "
                    f"({rel_result.get('high_confidence', 0)} high-confidence)"
                )
            elif rel_result.get("success") is True:
                st.info("No relationships detected. Check your data or manually add them.")
            elif rel_result.get("success") is False:
                st.error(f"Error: {rel_result.get('message', 'Unknown error')}")

            if total_count > 0:
                st.write("### Relationship Validation & Editing")
                st.caption("Review detected relationships. Edit any row or delete rows (leave blank to remove). Click Save.")

                edit_df = pd.DataFrame(
                    [
                        {
                            "name": rel.get("name", ""),
                            "from_table": rel.get("from_table", ""),
                            "from_column": rel.get("from_column", ""),
                            "to_table": rel.get("to_table", ""),
                            "to_column": rel.get("to_column", ""),
                        }
                        for rel in relationship_rows
                    ]
                )

                edited_df = st.data_editor(
                    edit_df,
                    use_container_width=True,
                    num_rows="dynamic",
                    key=f"relationship_editor_{active_model['id']}",
                )

                ec1, ec2, ec3 = st.columns([1, 1, 1])
                with ec1:
                    if st.button("💾 Save Relationship Edits", key=f"save_relationship_edits_{active_model['id']}"):
                        cleaned_relationships = []
                        required_fields = ["from_table", "from_column", "to_table", "to_column"]

                        for _, row in edited_df.iterrows():
                            rel = {k: str(row.get(k, "")).strip() for k in ["name", *required_fields]}
                            if not all(rel.get(f) for f in required_fields):
                                continue
                            if not rel.get("name"):
                                rel["name"] = f"{rel['from_table']}_{rel['to_table']}_{rel['from_column']}"
                            cleaned_relationships.append(rel)

                        metadata = model_store.load_metadata(active_model["id"])
                        metadata["relationships"] = cleaned_relationships
                        notes = metadata.setdefault("ingestion_notes", [])
                        notes.append(
                            f"User validated/edited relationships: {len(cleaned_relationships)} active relationship(s)"
                        )
                        model_store.save_metadata(active_model["id"], metadata)

                        updated_result = {
                            "model_id": active_model["id"],
                            "total_detected": len(cleaned_relationships),
                            "new_relationships": 0,
                            "relationships": cleaned_relationships,
                        }
                        st.session_state.relationship_result = updated_result
                        st.session_state.relationship_result_model_id = active_model["id"]
                        st.session_state.agent = _build_agent_for_model(
                            api_key=api_key_input,
                            metadata=metadata,
                            model_id=active_model["id"],
                        )
                        st.session_state.agent_model_id = active_model["id"]
                        st.success("Relationship edits saved successfully.")
                        st.rerun()

                with ec2:
                    if st.button("🔁 Re-Detect Relationships", key=f"redetect_relationships_{active_model['id']}"):
                        refreshed = model_store.identify_relationships(active_model["id"])
                        st.session_state.relationship_result = refreshed
                        st.session_state.relationship_result_model_id = active_model["id"]
                        st.rerun()
                
                with ec3:
                    if st.button("🗑️ Clear All Relationships", key=f"clear_relationships_{active_model['id']}", help="Delete all relationships"):
                        if st.session_state.get(f"confirm_clear_rel_{active_model['id']}", False):
                            metadata = model_store.load_metadata(active_model["id"])
                            metadata["relationships"] = []
                            notes = metadata.setdefault("ingestion_notes", [])
                            notes.append("User cleared all relationships")
                            model_store.save_metadata(active_model["id"], metadata)
                            st.session_state.relationship_result = {
                                "model_id": active_model["id"],
                                "total_detected": 0,
                                "relationships": [],
                            }
                            st.session_state.relationship_result_model_id = active_model["id"]
                            st.success("All relationships cleared.")
                            st.rerun()
                        else:
                            st.session_state[f"confirm_clear_rel_{active_model['id']}"] = True
                            st.warning("Click again to confirm clearing all relationships")
                            st.rerun()

        # Show model view if button was clicked
        if st.session_state.get("show_model_view", False):
            st.write("### Model Schema View")
            with st.expander("📊 Tables", expanded=True):
                tables_in_model = active_metadata.get("tables", {}) if isinstance(active_metadata, dict) else {}
                if not tables_in_model:
                    st.info("No tables discovered yet. Upload a PBIX, CSV, or JSON metadata file.")
                else:
                    tables_rows = []
                    for table_name, info in tables_in_model.items():
                        tables_rows.append(
                            {
                                "Table": table_name,
                                "Columns": len(info.get("columns", {})),
                                "Column Names": ", ".join(info.get("columns", {}).keys()),
                            }
                        )
                    st.dataframe(pd.DataFrame(tables_rows), use_container_width=True)
            
            with st.expander("🔗 Relationships", expanded=True):
                rels = active_metadata.get("relationships", []) if isinstance(active_metadata, dict) else []
                if not rels:
                    st.info("No relationships discovered yet.")
                else:
                    rels_rows = []
                    for rel in rels:
                        rels_rows.append(
                            {
                                "From": f"{rel.get('from_table', '')}.{rel.get('from_column', '')}",
                                "To": f"{rel.get('to_table', '')}.{rel.get('to_column', '')}",
                            }
                        )
                    st.dataframe(pd.DataFrame(rels_rows), use_container_width=True)
            
            with st.expander("📝 Ingestion Notes", expanded=False):
                notes = active_metadata.get("ingestion_notes", []) if isinstance(active_metadata, dict) else []
                if notes:
                    for note in notes:
                        st.write(f"• {note}")
                else:
                    st.info("No ingestion notes yet.")

        # ===== PBIX/PBIT MODEL UPLOAD SECTION =====
        st.subheader("📊 Step 1: Upload Power BI Model (PBIX/PBIT)")
        st.write("Upload your Power BI semantic model file to train the agent on your actual model schema.")
        
        pbix_file = st.file_uploader(
            "Select a PBIX or PBIT file",
            type=["pbix", "pbit"],
            key="pbix_upload",
            help="Upload your Power BI model file to extract schema, tables, relationships, and measures"
        )
        
        if pbix_file is not None:
            st.info(f"📁 Selected: {pbix_file.name}")
            
            if st.button("🔍 Extract & Train from PBIX Model", key="extract_pbix"):
                with st.spinner("Extracting metadata from PBIX file..."):
                    try:
                        # Save uploaded file temporarily
                        pbix_path = Path(f"/tmp/{pbix_file.name}")
                        pbix_path.write_bytes(pbix_file.getvalue())
                        
                        # Import and use PBIX extractor
                        from .pbix_extractor import PBIXExtractor
                        
                        # Validate file
                        is_valid, validation_msg = PBIXExtractor.validate_pbix_file(str(pbix_path))
                        if not is_valid:
                            st.error(f"❌ Invalid PBIX file: {validation_msg}")
                        else:
                            # Extract metadata
                            metadata = PBIXExtractor.extract_metadata(str(pbix_path))
                            
                            if metadata and metadata.get("tables"):
                                # Save extracted metadata to model
                                extracted_metadata = model_store.load_metadata(active_model["id"])
                                
                                # Merge with existing metadata
                                extracted_metadata["tables"] = metadata.get("tables", {})
                                extracted_metadata["relationships"] = metadata.get("relationships", [])
                                extracted_metadata["measures"] = metadata.get("measures", {})
                                
                                # Add ingestion note
                                notes = extracted_metadata.setdefault("ingestion_notes", [])
                                notes.append(f"Trained on PBIX model: {pbix_file.name}")
                                
                                # Save updated metadata
                                model_store.save_metadata(active_model["id"], extracted_metadata)
                                
                                # Get file info
                                file_info = PBIXExtractor.get_file_info(str(pbix_path))
                                
                                st.success(f"✅ Successfully extracted model from {pbix_file.name}")
                                st.write(f"**File Info:** {file_info['model_type']} model (~{file_info['size_mb']}MB)")
                                
                                # Show extracted schema
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("📊 Tables Found", len(metadata.get("tables", {})))
                                with col2:
                                    st.metric("🔗 Relationships", len(metadata.get("relationships", [])))
                                with col3:
                                    st.metric("📐 Measures", len(metadata.get("measures", {})))
                                
                                # Show extracted tables
                                with st.expander("📋 Extracted Tables & Columns", expanded=True):
                                    tables_data = []
                                    for table_name, info in metadata.get("tables", {}).items():
                                        col_count = info.get("column_count", 0)
                                        columns = list(info.get("columns", {}).keys())
                                        tables_data.append({
                                            "Table": table_name,
                                            "Columns": col_count,
                                            "Column Names": ", ".join(columns[:5]) + ("..." if col_count > 5 else ""),
                                        })
                                    st.dataframe(pd.DataFrame(tables_data), use_container_width=True)
                                
                                # Show relationships
                                if metadata.get("relationships"):
                                    with st.expander("🔗 Detected Relationships", expanded=True):
                                        rel_data = []
                                        for rel in metadata.get("relationships", []):
                                            rel_data.append({
                                                "From": f"{rel.get('from_table')}.{rel.get('from_column')}",
                                                "To": f"{rel.get('to_table')}.{rel.get('to_column')}",
                                            })
                                        st.dataframe(pd.DataFrame(rel_data), use_container_width=True)
                                
                                # Show measures
                                if metadata.get("measures"):
                                    with st.expander("📐 Extracted Measures", expanded=False):
                                        for measure_name, measure_info in list(metadata.get("measures", {}).items())[:10]:
                                            st.write(f"**{measure_name}** (in {measure_info.get('table', 'Unknown')})")
                                            st.code(measure_info.get("expression", ""), language="sql")
                                
                                # ===== NEW: COMPREHENSIVE MODEL CONTEXT FOR GROQ =====
                                st.divider()
                                st.subheader("🧠 Model Context for Code Generation")
                                st.write("This is the **complete model context** that Groq will use to generate code. Groq will see all tables, columns, relationships, and measures:")
                                
                                # Build and display comprehensive context
                                from .fabric_universal import ContextBuilder
                                context_builder = ContextBuilder(extracted_metadata)
                                comprehensive_context = context_builder.build_context()
                                
                                # Display in a code block so user can verify
                                with st.expander("📋 Full Model Context (Sent to Groq)", expanded=False):
                                    st.code(comprehensive_context, language="text")
                                
                                # Display summary stats
                                summary = context_builder.get_model_summary()
                                col1, col2, col3, col4 = st.columns(4)
                                with col1:
                                    st.metric("📊 Tables", summary["table_count"])
                                with col2:
                                    st.metric("🔤 Total Columns", summary["total_columns"])
                                with col3:
                                    st.metric("📐 Measures", summary["measure_count"])
                                with col4:
                                    st.metric("⚙️  Calculated Columns", summary["calculated_column_count"])
                                
                                st.success("✅ Groq will now have complete access to your model structure!")
                                st.divider()
                                
                                # Train the agent
                                st.info("🤖 Training agent on extracted model schema...")
                                st.session_state.agent = _build_agent_for_model(
                                    api_key=api_key_input,
                                    metadata=extracted_metadata,
                                    model_id=active_model["id"],
                                )
                                st.session_state.agent_model_id = active_model["id"]
                                st.success("✅ Agent trained on your PBIX model! You can now generate code for this model.")
                                st.rerun()
                            else:
                                st.error("❌ Could not extract any tables from the PBIX file. File may be empty or corrupted.")
                    
                    except Exception as e:
                        st.error(f"❌ Error extracting PBIX: {str(e)}")
                        logger.error(f"PBIX extraction error: {str(e)}")

        st.divider()
        
        # ===== CSV FILE UPLOAD SECTION (EXISTING) =====
        st.subheader("📁 Step 2: Upload CSV Files (Optional)")
        st.write("Upload additional CSV files for relationship detection and combined table creation.")
        
        uploads = st.file_uploader(
            "Upload CSV files or metadata files",
            type=["csv", "json", "pbix", "pbit", "png", "jpg", "jpeg", "webp", "txt", "md"],
            accept_multiple_files=True,
            key="model_uploads",
        )

        if st.button("Store Uploaded Files", key="store_uploads"):
            if not uploads:
                st.warning("No files selected.")
            else:
                for up in uploads:
                    model_store.add_upload(active_model["id"], up.name, up.getvalue())

                # Reload metadata to show detected relationships
                updated_metadata = model_store.load_metadata(active_model["id"])
                
                profile = _train_active_model(model_store, active_model["id"], agent)
                trained_msg = (
                    " Model training applied"
                    f" (table={profile.get('preferred_table', 'n/a')},"
                    f" value={profile.get('preferred_value_column', 'n/a')})."
                )
                
                # Show relationship detection results
                relationships = updated_metadata.get("relationships", [])
                rel_count = len(relationships)
                rel_msg = f" Detected {rel_count} relationship(s)." if rel_count > 0 else ""

                st.success(f"Stored {len(uploads)} file(s) and updated model metadata.{rel_msg}{trained_msg}")
                
                # Display detected relationships if any
                if rel_count > 0:
                    with st.expander("🔗 Auto-Detected Relationships", expanded=True):
                        rel_rows = []
                        for rel in relationships:
                            rel_rows.append({
                                "From": f"{rel.get('from_table')}.{rel.get('from_column')}",
                                "To": f"{rel.get('to_table')}.{rel.get('to_column')}",
                            })
                        st.dataframe(pd.DataFrame(rel_rows), use_container_width=True)
                
                # ===== NEW: Display Comprehensive Model Context (same as PBIX) =====
                st.divider()
                st.subheader("🧠 Model Context for Code Generation")
                st.write("This is the **complete model context** that Groq will use to generate code. Groq will see all tables, columns, relationships, and measures:")
                
                # Build and display comprehensive context
                from .fabric_universal import ContextBuilder
                context_builder = ContextBuilder(updated_metadata)
                comprehensive_context = context_builder.build_context()
                
                # Display in a code block so user can verify
                with st.expander("📋 Full Model Context (Sent to Groq)", expanded=False):
                    st.code(comprehensive_context, language="text")
                
                # Display summary stats
                summary = context_builder.get_model_summary()
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📊 Tables", summary["table_count"])
                with col2:
                    st.metric("🔤 Total Columns", summary["total_columns"])
                with col3:
                    st.metric("📐 Measures", summary["measure_count"])
                with col4:
                    st.metric("⚙️  Calculated Columns", summary["calculated_column_count"])
                
                st.success("✅ Groq will now have complete access to your model structure!")
                st.divider()
                
                st.session_state.agent = _build_agent_for_model(
                    api_key=api_key_input,
                    metadata=updated_metadata,
                    model_id=active_model["id"],
                )
                st.session_state.agent_model_id = active_model["id"]
                st.rerun()

        refreshed_active = model_store.get_model(active_model["id"]) or active_model
        if refreshed_active.get("uploads"):
            with st.expander("📁 Uploaded Files", expanded=True):
                col1, col2, col3, col4 = st.columns([1.5, 1, 1, 0.5])
                with col1:
                    st.write("**Filename**")
                with col2:
                    st.write("**Uploaded At**")
                with col3:
                    st.write("**Path**")
                with col4:
                    st.write("**Action**")
                
                for idx, upload in enumerate(refreshed_active.get("uploads", [])):
                    c1, c2, c3, c4 = st.columns([1.5, 1, 1, 0.5])
                    with c1:
                        st.write(upload.get("filename", ""))
                    with c2:
                        st.write(upload.get("uploaded_at", "")[:10])  # Show only date
                    with c3:
                        st.caption(upload.get("stored_path", "")[-30:])  # Show last 30 chars
                    with c4:
                        if st.button("🗑️", key=f"delete_upload_{idx}_{active_model['id']}", help="Delete file"):
                            if model_store.delete_upload(active_model["id"], upload.get("filename")):
                                st.success(f"Deleted: {upload.get('filename')}")
                                st.rerun()
                            else:
                                st.error("Failed to delete file")
            
            # NEW: Preview uploaded CSV files in table format
            st.subheader("📊 Data Preview")
            preview_file = st.selectbox(
                "Select a file to preview",
                options=[u.get("filename", "") for u in refreshed_active.get("uploads", [])],
                key="preview_file_selector"
            )
            
            if preview_file:
                try:
                    # Find the selected upload
                    selected_upload = next((u for u in refreshed_active.get("uploads", []) if u.get("filename") == preview_file), None)
                    if selected_upload:
                        file_path = selected_upload.get("stored_path")
                        if file_path and Path(file_path).exists():
                            # Read CSV and display
                            preview_df = pd.read_csv(file_path)
                            st.write(f"**Rows:** {len(preview_df)} | **Columns:** {len(preview_df.columns)}")
                            st.dataframe(preview_df, use_container_width=True)
                            
                            # Show column info
                            with st.expander("📋 Column Information"):
                                col_info = []
                                for col in preview_df.columns:
                                    col_info.append({
                                        "Column": col,
                                        "Type": str(preview_df[col].dtype),
                                        "Non-Null Count": preview_df[col].count(),
                                        "Null Count": preview_df[col].isna().sum()
                                    })
                                st.dataframe(pd.DataFrame(col_info), use_container_width=True)
                        else:
                            st.warning(f"File not found: {file_path}")
                except Exception as e:
                    st.error(f"Error reading file: {str(e)}")

    with tab_generate:
        st.subheader("Generate New Item")
        st.info("💡 **Item Name is used as the name for all generated content** (DAX, SQL, PySpark, etc.)")
        
        # ===== AUTO-DISPLAY MODEL CONTEXT (Cached from background refresh) =====
        # Context is automatically refreshed in background on page load, just display it here
        _display_model_context_automatically("🧠 LLM Context (What Groq will see)")
        
        with st.form("generate_form"):
            item_type = st.selectbox("Item Type", ["measure", "flag", "column", "table"], index=0)
            output_language = st.selectbox("Output Language", ["DAX", "SQL", "PySpark", "Python"], index=0)
            usage_target = st.selectbox(
                "Where will this be used?",
                ["Semantic Model", "Warehouse", "Notebook", "Python Script"],
                index=0,
            )
            item_name = st.text_input("Item Name (Required - will be the name of generated content)", placeholder="e.g. Total Sales, Customer Count, Monthly Revenue")
            description = st.text_input("Description", placeholder="Create month over month sales growth")
            conditions = st.text_input("Conditions (optional)", placeholder="where Sales > 1000")
            auto_register = st.checkbox("Auto-register item", value=True)
            submit = st.form_submit_button("Generate")

        if submit:
            if not description.strip():
                st.error("Description is required.")
            elif not item_name.strip():
                st.error("Item Name is required - it will be used as the name for the generated content.")
            else:
                # CRITICAL: Validate metadata before generation
                active_metadata = model_store.load_metadata(active_model["id"])
                
                if not isinstance(active_metadata, dict):
                    st.error("❌ ERROR: No model metadata loaded! Please upload a PBIX file or define your schema first.")
                    st.info("📝 Steps to fix:\n1. Go to the 'Models' tab\n2. Upload a Power BI PBIX file\n3. Or manually add tables and columns\n4. Then come back to generate code")
                elif not active_metadata.get("tables"):
                    st.error("❌ ERROR: Model has no tables defined! Cannot generate code with incomplete schema.")
                    st.info("📝 Steps to fix:\n1. Upload a PBIX file with tables, OR\n2. Go to 'Schema' tab and manually add table definitions")
                else:
                    # Check if we have columns in at least one table
                    has_columns = any(
                        table_info.get("columns") 
                        for table_info in active_metadata.get("tables", {}).values()
                    )
                    if not has_columns:
                        st.error("❌ ERROR: Tables exist but have no columns defined!")
                        st.info("Make sure your schema includescolumn information before generating code.")
                    else:
                        # ===== DISPLAY GENERATION PACKET BEFORE GENERATING =====
                        st.divider()
                        _display_generation_packet(
                            item_type=item_type,
                            output_language=output_language,
                            usage_target=usage_target,
                            item_name=item_name,
                            description=description.strip(),
                            conditions=conditions.strip()
                        )
                        st.divider()
                        
                        # Now that user has seen the packet, proceed with generation
                        # UPDATED: Use Groq everywhere (removed old DAX-specific path)
                        # All code generation now uses universal_assistant with comprehensive packet
                        
                        target_map = {
                            "Semantic Model": "semantic",
                            "Warehouse": "warehouse",
                            "Notebook": "notebook",
                            "Python Script": "python",
                        }
                        target = target_map.get(usage_target, "semantic")

                        if output_language == "SQL":
                            target = "warehouse"
                        elif output_language == "PySpark":
                            target = "notebook"
                        elif output_language == "Python":
                            target = "python"
                        elif output_language == "DAX":
                            target = "semantic"

                        # ALWAYS use Groq for code generation (skip FormulaCorrector - it generates garbage)
                        u_result = {}
                        
                        # For all languages and types, use universal assistant with comprehensive packet
                        if True:  # Always use Groq path
                            # BUILD FOCUSED PROMPT - REQUEST FIRST, SCHEMA SECOND
                            # This ensures Groq sees the actual request before schema details
                            
                            # Build MINIMAL schema context (only what's needed)
                            minimal_schema = ""
                            active_metadata = model_store.load_metadata(active_model["id"])
                            if isinstance(active_metadata, dict):
                                tables = active_metadata.get("tables", {})
                                relationships = active_metadata.get("relationships", [])
                                
                                minimal_schema = "AVAILABLE TABLES AND COLUMNS:\n"
                                for table_name, info in tables.items():
                                    columns = info.get("columns", {})
                                    col_list = ", ".join(columns.keys()) if columns else "No columns"
                                    minimal_schema += f"  {table_name}: {col_list}\n"
                                
                                if relationships:
                                    minimal_schema += "\nRELATIONSHIP MAP (join using these):\n"
                                    for rel in relationships:
                                        from_table = rel.get('from_table', 'Unknown')
                                        from_col = rel.get('from_column', 'Unknown').replace('\ufeff', '').strip()
                                        to_table = rel.get('to_table', 'Unknown')
                                        to_col = rel.get('to_column', 'Unknown').replace('\ufeff', '').strip()
                                        minimal_schema += f"  {from_table}[{from_col}] → {to_table}[{to_col}]\n"
                            
                            # BUILD THE PROMPT WITH REQUEST FIRST
                            universal_prompt = f"""YOU ARE A {output_language} CODE GENERATION EXPERT.

YOUR TASK:
══════════════════════════════════════════════════════════════════════
Create a {output_language} {item_type} NAMED "{item_name}"

REQUEST: {description.strip()}
{f'CONDITIONS: {conditions.strip()}' if conditions.strip() else ''}

TARGET ENVIRONMENT: {usage_target}
══════════════════════════════════════════════════════════════════════

SCHEMA YOU HAVE ACCESS TO:
{minimal_schema}

RULES:
──────────────────────────────────────────────────────────────────────
✓ ONLY use tables and columns listed above
✓ ONLY use column names EXACTLY as shown (case-sensitive with special chars)
✓ For {output_language}: Use proper {output_language} syntax
✓ NEVER invent tables or columns
✓ NEVER average or sum ID/Key columns  
✓ For measures: Use IF, AND, OR, CALCULATE as needed
✓ Include ALL logic needed to match the request and conditions

OUTPUT FORMAT:
──────────────────────────────────────────────────────────────────────
Return ONLY the complete, valid {output_language} code.
For a measure named "{item_name}", return the full measure definition.
For SQL/PySpark, return the complete query.
NO explanations. NO markdown. Only the code.

NOW GENERATE THE {output_language} {item_type}:"""
                            
                            # Create user_params for comprehensive packet building
                            user_params = {
                                "item_type": item_type,
                                "output_language": output_language,
                                "usage_target": usage_target,
                                "item_name": item_name,
                                "description": description.strip(),
                                "conditions": conditions.strip()
                            }
                            # IMPORTANT: Use only the user's natural request for intent detection/object naming.
                            # The comprehensive schema packet is built separately from user_params in the backend.
                            intent_request = f"Create {item_type} named {item_name}. {description.strip()}"
                            if conditions.strip():
                                intent_request += f" Conditions: {conditions.strip()}"
                            u_result = universal_assistant.run_once(intent_request, target=target, user_params=user_params)
                            
                            # DEBUG: Check what we got back
                            if not u_result:
                                st.error("❌ ERROR: Groq returned no response. Check API key and limits.")
                                st.warning("Debugging info: u_result is empty or None")
                            elif u_result.get("type") == "ERROR":
                                st.error(f"❌ GENERATION ERROR: {u_result.get('explanation', 'Unknown error')}")
                                st.info(f"**Generated code that failed validation:**\n```\n{u_result.get('code', '')}\n```")
                            else:
                                st.success(f"✓ Generated {u_result.get('type', output_language)} for {usage_target}.")
                        
                        corrected_code = u_result.get("code", "") if u_result else ""

                        # Register the generated item in the registry so it appears in Created Items
                        if u_result and u_result.get("code") and u_result.get("type") != "ERROR":
                            # ALWAYS use the item_name field as the name for generated content
                            # This ensures the user's custom name is applied to whatever is generated
                            final_item_name = item_name.strip()
                            
                            agent.registry.register(
                                name=final_item_name,
                                item_type=item_type,
                                expression=u_result.get("code", ""),
                                description=description.strip() + f"\n({u_result.get('type', output_language)} for {usage_target})"
                            )
                            st.success(f"✓ Saved to Created Items as '{final_item_name}' ({item_type})")

                        if u_result and u_result.get("code"):
                            lang_map = {
                                "DAX": "sql",
                                "SQL": "sql",
                                "PySpark": "python",
                                "Python": "python",
                            }
                            st.write("### Generated Code")
                            st.code(u_result.get("code", ""), language=lang_map.get(u_result.get("type", "Python"), "text"))
                            st.write("**Explanation**")
                            st.write(u_result.get("explanation", ""))

                            model_used = u_result.get("model_used")
                            if model_used:
                                st.caption(f"Model used: {model_used} | Temperature: {os.getenv('GROQ_TEMPERATURE', '0')}")

                            st.write("**Paste-Ready Query/Script**")
                            st.code(
                                u_result.get("paste_ready_query", u_result.get("code", "")),
                                language=lang_map.get(u_result.get("type", "Python"), "text"),
                            )

                            # Display raw Groq response for verification
                            if u_result.get("raw_response"):
                                with st.expander("🔍 Raw Groq Response (Exact Output)", expanded=False):
                                    st.markdown("**This is the exact output from Groq API:**")
                                    st.code(u_result.get("raw_response"), language="text")
                        else:
                            st.error("❌ No code was generated. Check error messages above.")

                        if u_result.get("errors"):
                            st.write("**Validation Issues**")
                            for err in u_result.get("errors", []):
                                st.write(f"- {err}")

    with tab_items:
        st.subheader("Created and Existing Items")
        filter_type = st.selectbox(
            "Filter by type",
            ["all", "measure", "flag", "column", "table"],
            index=0,
            key="filter_type",
        )
        filter_source = st.selectbox(
            "Filter by source",
            ["all", "existing", "generated"],
            index=0,
            key="filter_source",
        )

        filtered = all_items
        if filter_type != "all":
            filtered = [i for i in filtered if i.get("item_type") == filter_type]
        if filter_source != "all":
            filtered = [i for i in filtered if i.get("source") == filter_source]

        df_items = _items_to_dataframe(filtered)
        if df_items.empty:
            st.info("No items match the selected filters.")
        else:
            st.dataframe(df_items, use_container_width=True)

            st.write("### Click an item to view definition and code")
            if "selected_created_item" not in st.session_state:
                st.session_state.selected_created_item = ""

            item_names = [str(i.get("name", "")).strip() for i in filtered if str(i.get("name", "")).strip()]
            item_names = sorted(list(dict.fromkeys(item_names)))

            if item_names:
                selected_name = st.selectbox(
                    "Select item",
                    options=item_names,
                    index=item_names.index(st.session_state.selected_created_item)
                    if st.session_state.selected_created_item in item_names
                    else 0,
                    key="selected_created_item_selectbox",
                )
                st.session_state.selected_created_item = selected_name

                selected_item = None
                for itm in filtered:
                    if str(itm.get("name", "")).strip() == selected_name:
                        selected_item = itm
                        break

                if selected_item:
                    st.write("#### Item Definition")
                    st.write(f"- Name: {selected_item.get('name', '')}")
                    st.write(f"- Type: {selected_item.get('item_type', '')}")
                    st.write(f"- Source: {selected_item.get('source', '')}")
                    st.write(f"- Definition: {selected_item.get('description', '') or 'No description available.'}")
                    if selected_item.get("created_at"):
                        st.write(f"- Created At: {selected_item.get('created_at', '')}")

                    st.write("#### Generated Code / Expression")
                    expr = selected_item.get("expression", "")
                    code_lang = "sql"
                    st.code(expr if expr else "No expression/code stored for this item.", language=code_lang)

    with tab_schema:
        st.subheader("Semantic Model Schema")
        st.text(agent.metadata.summary())

        tables_rows = []
        for table_name, info in agent.metadata.metadata["tables"].items():
            tables_rows.append(
                {
                    "table": table_name,
                    "column_count": info.get("column_count", 0),
                    "columns": ", ".join(info.get("columns", {}).keys()),
                }
            )
        st.write("**Tables**")
        st.dataframe(pd.DataFrame(tables_rows), use_container_width=True)

        relationships_rows = []
        for rel in agent.metadata.metadata["relationships"]:
            relationships_rows.append(
                {
                    "name": rel.get("name", ""),
                    "from": f"{rel.get('from_table', '')}.{rel.get('from_column', '')}",
                    "to": f"{rel.get('to_table', '')}.{rel.get('to_column', '')}",
                }
            )
        st.write("**Relationships**")
        st.dataframe(pd.DataFrame(relationships_rows), use_container_width=True)

        ingestion_notes = active_metadata.get("ingestion_notes", []) if isinstance(active_metadata, dict) else []
        if ingestion_notes:
            st.write("**Model Learning Notes**")
            for note in ingestion_notes:
                st.write(f"- {note}")

    with tab_tests:
        st.subheader("Backend Field Tests")
        st.write("Validate generated fields against the active model schema.")
        if st.button("Run Field Tests"):
            test_df = _run_field_tests(agent)
            if test_df.empty:
                st.info("No generated fields found for this model.")
            else:
                st.dataframe(test_df, use_container_width=True)
                passed = int((test_df["status"] == "PASS").sum())
                failed = int((test_df["status"] == "FAIL").sum())
                st.write(f"Passed: {passed} | Failed: {failed} | Total: {len(test_df)}")

    with tab_exports:
        st.subheader("Export Outputs")
        export_name = st.text_input("CSV file name", value=f"{active_model['id']}_created_items.csv")

        if st.button("Export Generated Items to CSV"):
            path = _export_created_csv(all_items, export_name)
            st.success(f"Exported generated items to: {path}")

        json_payload = agent.metadata.as_json()
        st.download_button(
            label="Download Schema JSON",
            data=json_payload,
            file_name=f"{active_model['id']}_semantic_model_schema.json",
            mime="application/json",
        )

    with tab_fabric:
        st.subheader("Universal Fabric Assistant")
        st.write(
            "Generate DAX, SQL, PySpark, and Python logic with model discovery, validation, and duplicate detection."
        )

        learned_tables = len(universal_assistant.store.metadata.get("tables", {}))
        learned_rels = len(universal_assistant.store.metadata.get("relationships", []))
        created_objects = len(universal_assistant.store.registry.get("objects", {}))
        f1, f2, f3 = st.columns(3)
        f1.metric("Learned Tables", learned_tables)
        f2.metric("Detected Relationships", learned_rels)
        f3.metric("Generated Objects", created_objects)

        tc1, tc2 = st.columns([1, 2])
        with tc1:
            if st.button("Train Universal Model", key="train_universal_model"):
                with st.spinner("Training universal assistant on learned model patterns..."):
                    profile = universal_assistant.train_model()
                st.success("Universal model training completed.")
                st.json(
                    {
                        "preferred_table": profile.get("preferred_table"),
                        "preferred_value_column": profile.get("preferred_value_column"),
                        "preferred_date_column": profile.get("preferred_date_column"),
                        "observed_expression_count": profile.get("observed_expression_count", 0),
                    }
                )
                # Preserve metadata from ingestion when rebuilding
                st.session_state.universal_assistant = _build_universal_assistant(
                    api_key_input, metadata=universal_assistant.store.metadata
                )
                st.rerun()
        with tc2:
            up = universal_assistant.store.metadata.get("training_profile", {})
            if isinstance(up, dict) and up:
                st.caption(
                    "Universal profile: "
                    f"table={up.get('preferred_table', 'n/a')}, "
                    f"value={up.get('preferred_value_column', 'n/a')}, "
                    f"date={up.get('preferred_date_column', 'n/a')}"
                )
            else:
                st.caption("No universal training profile yet. Click 'Train Universal Model'.")

        st.markdown("### 1) Data Ingestion")
        csv_upload = st.file_uploader(
            "Upload CSV for metadata learning",
            type=["csv"],
            key="fabric_csv_upload",
        )

        if st.button("Ingest CSV", key="fabric_ingest_csv"):
            if not csv_upload:
                st.warning("Please upload a CSV file first.")
            else:
                uploads_dir = universal_assistant.store.root / "uploads"
                uploads_dir.mkdir(parents=True, exist_ok=True)
                target_path = uploads_dir / csv_upload.name
                target_path.write_bytes(csv_upload.getvalue())
                ingest_result = universal_assistant.ingestion.load_data(csv_path=str(target_path))
                st.json(ingest_result)
                if auto_train_universal:
                    profile = universal_assistant.train_model()
                    st.info(
                        "Auto-training completed: "
                        f"table={profile.get('preferred_table', 'n/a')}, "
                        f"value={profile.get('preferred_value_column', 'n/a')}"
                    )
                
                # ===== NEW: Display Comprehensive Model Context for Fabric =====
                st.divider()
                st.subheader("🧠 Model Context for Code Generation")
                st.write("This is the **complete model context** that Groq will use to generate code:")
                
                try:
                    universal_metadata = universal_assistant.store.metadata
                    if universal_metadata.get("tables"):
                        from .fabric_universal import ContextBuilder
                        context_builder = ContextBuilder(universal_metadata)
                        comprehensive_context = context_builder.build_context()
                        
                        # Display in a code block
                        with st.expander("📋 Full Model Context (Sent to Groq)", expanded=False):
                            st.code(comprehensive_context, language="text")
                        
                        # Display summary stats
                        summary = context_builder.get_model_summary()
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("📊 Tables", summary["table_count"])
                        with col2:
                            st.metric("🔤 Total Columns", summary["total_columns"])
                        with col3:
                            st.metric("📐 Measures", summary["measure_count"])
                        with col4:
                            st.metric("⚙️  Relationships", summary["relationship_count"])
                        
                        st.success("✅ Groq will now have complete access to your data model!")
                except Exception as e:
                    st.warning(f"Could not display context: {str(e)}")
                
                st.divider()
                
                # Preserve metadata from ingestion when rebuilding
                st.session_state.universal_assistant = _build_universal_assistant(
                    api_key_input, metadata=universal_assistant.store.metadata
                )

        c1, c2 = st.columns([3, 1])
        with c1:
            fabric_table_name = st.text_input(
                "Spark/Lakehouse/Warehouse table name",
                placeholder="sales_fact",
                key="fabric_table_name",
            )
        with c2:
            if st.button("Register Table", key="fabric_register_table"):
                if not fabric_table_name.strip():
                    st.warning("Enter a table name.")
                else:
                    table_result = universal_assistant.ingestion.load_data(table_name=fabric_table_name.strip())
                    st.json(table_result)
                    if auto_train_universal:
                        profile = universal_assistant.train_model()
                        st.info(
                            "Auto-training completed: "
                            f"table={profile.get('preferred_table', 'n/a')}, "
                            f"value={profile.get('preferred_value_column', 'n/a')}"
                        )
                    # Preserve metadata from ingestion when rebuilding
                    st.session_state.universal_assistant = _build_universal_assistant(
                        api_key_input, metadata=universal_assistant.store.metadata
                    )

        st.markdown("### 2) Model Discovery")
        if st.button("Discover Model", key="fabric_discover"):
            discovery_result = universal_assistant.discovery.discover_model()
            st.json(discovery_result)
            if auto_train_universal:
                profile = universal_assistant.train_model()
                st.info(
                    "Auto-training completed: "
                    f"table={profile.get('preferred_table', 'n/a')}, "
                    f"value={profile.get('preferred_value_column', 'n/a')}"
                )
            # Preserve metadata from discovery when rebuilding
            st.session_state.universal_assistant = _build_universal_assistant(
                api_key_input, metadata=universal_assistant.store.metadata
            )

        with st.expander("View LLM Context", expanded=False):
            st.text(universal_assistant.build_context())

        st.markdown("### 3) Multi-Language Generation")
        with st.form("fabric_generate_form"):
            target = st.selectbox(
                "Target Layer",
                ["auto", "semantic", "warehouse", "notebook", "python"],
                index=3,
            )
            st.caption("Tip: choose `notebook` for long PySpark code, `warehouse` for SQL, `semantic` for DAX.")
            request = st.text_area(
                "Request",
                placeholder="Create total sales by customer and month",
                height=90,
            )
            submit_fabric = st.form_submit_button("Generate")

        if submit_fabric:
            if not request.strip():
                st.error("Request is required.")
            else:
                target_arg = None if target == "auto" else target
                result = universal_assistant.run_once(request.strip(), target=target_arg)

                status = result.get("validation", "failed")
                if status == "passed":
                    st.success(f"Generated {result.get('type', '')} code successfully.")
                else:
                    st.warning("Generated output has validation issues or duplicates.")

                lang_map = {
                    "DAX": "sql",
                    "SQL": "sql",
                    "PySpark": "python",
                    "Python": "python",
                }
                st.code(result.get("code", ""), language=lang_map.get(result.get("type", "Python"), "text"))
                st.write("**Explanation**")
                st.write(result.get("explanation", ""))

                st.write("**Paste-Ready Query/Script**")
                st.code(
                    result.get("paste_ready_query", result.get("code", "")),
                    language=lang_map.get(result.get("type", "Python"), "text"),
                )

                if result.get("errors"):
                    st.write("**Validation Issues**")
                    for err in result.get("errors", []):
                        st.write(f"- {err}")

                with st.expander("Detailed Response", expanded=False):
                    st.json(result)

                # Preserve metadata from generation when rebuilding
                st.session_state.universal_assistant = _build_universal_assistant(
                    api_key_input, metadata=universal_assistant.store.metadata
                )

        st.markdown("### 4) Learning Store")
        store_meta = universal_assistant.store.metadata
        tables_rows = []
        for table_name, info in store_meta.get("tables", {}).items():
            tables_rows.append(
                {
                    "table": table_name,
                    "column_count": info.get("column_count", 0),
                    "source": info.get("source", ""),
                }
            )

        if tables_rows:
            st.dataframe(pd.DataFrame(tables_rows), use_container_width=True)
        else:
            st.info("No learned tables yet. Ingest a CSV or register a table to begin learning.")

        with st.expander("Metadata JSON", expanded=False):
            st.code(json.dumps(store_meta, indent=2), language="json")

    with tab_demo:
        st.subheader("Run Demo Scenario")
        st.write("This will generate demo items (measure, flag, measure, table).")

        if "demo_results" not in st.session_state:
            st.session_state.demo_results = []

        if st.button("Run Demo"):
            demo_requests = [
                {"item_type": "measure", "description": "Create total sales measure"},
                {
                    "item_type": "flag",
                    "description": "Create AI pipeline flag",
                    "conditions": "where Sales > 1000",
                },
                {
                    "item_type": "measure",
                    "description": "Create month over month sales growth",
                },
                {
                    "item_type": "table",
                    "description": "Create top 5 products table by total sales",
                },
            ]

            results = []
            with st.spinner("Generating demo items..."):
                for req in demo_requests:
                    results.append(
                        agent.generate_item(
                            description=req["description"],
                            item_type=req["item_type"],
                            conditions=req.get("conditions", ""),
                            auto_register=True,
                        )
                    )

            st.session_state.demo_results = results
            st.success("✓ Demo completed. Items have been created and stored.")

        if st.session_state.demo_results:
            st.markdown("---")
            st.write("**Created Items:**")
            for idx, result in enumerate(st.session_state.demo_results, start=1):
                st.write(f"[{idx}] {result['name']} ({result['item_type']})")
                with st.expander(f"View Expression: {result['name']}", expanded=False):
                    st.code(result["expression"], language="sql")
                    st.write(result.get("explanation", ""))


def main() -> None:
    run_ui()


if __name__ == "__main__":
    main()
