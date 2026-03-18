import csv
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from .cli import build_agent
from .model_store import ModelStore


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


def run_ui() -> None:
    st.set_page_config(
        page_title="Power BI Semantic Model Assistant",
        page_icon="PB",
        layout="wide",
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
            "OpenAI API Key (optional override)",
            type="password",
            value="",
            help="Leave blank to use OPENAI_API_KEY from .env",
        )
        selected_model_id = st.selectbox(
            "Active Model",
            options=list(model_map.keys()),
            format_func=lambda model_id: model_map[model_id]["name"],
            index=list(model_map.keys()).index(st.session_state.active_model_id),
        )
        force_reload = st.button("Reload Active Model")

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

    agent = st.session_state.agent

    all_items = list(agent.registry.items.values())
    generated_items = [i for i in all_items if i.get("source") == "generated"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Items", len(all_items))
    col2.metric("Generated", len(generated_items))
    col3.metric("Flags", len(agent.registry.get_items_by_type("flag")))
    col4.metric("Tables", len(agent.registry.get_items_by_type("table")))

    tab_models, tab_generate, tab_items, tab_schema, tab_tests, tab_exports, tab_demo = st.tabs(
        ["Model Hub", "Generate", "Created Items", "Schema", "Field Tests", "Exports", "Demo"]
    )

    with tab_models:
        st.subheader("Model Hub")
        st.write("Create model cards, upload metadata files, and switch to a model-specific workspace.")

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
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**{model['name']}**")
                st.caption(model.get("description", ""))
                st.caption(f"Created: {model.get('created_at', '')}")
            with c2:
                if st.button("Open", key=f"open_{model['id']}"):
                    st.session_state.active_model_id = model["id"]
                    st.rerun()

        st.write("---")
        st.write(f"### Active Model: {active_model['name']}")

        uploads = st.file_uploader(
            "Upload PBIX / screenshot / metadata files",
            type=["pbix", "png", "jpg", "jpeg", "webp", "json", "csv", "tsv", "txt", "md"],
            accept_multiple_files=True,
            key="model_uploads",
        )

        if st.button("Store Uploaded Files", key="store_uploads"):
            if not uploads:
                st.warning("No files selected.")
            else:
                for up in uploads:
                    model_store.add_upload(active_model["id"], up.name, up.getvalue())
                st.success(f"Stored {len(uploads)} file(s) and updated model metadata.")
                st.session_state.agent = _build_agent_for_model(
                    api_key=api_key_input,
                    metadata=model_store.load_metadata(active_model["id"]),
                    model_id=active_model["id"],
                )
                st.session_state.agent_model_id = active_model["id"]

        refreshed_active = model_store.get_model(active_model["id"]) or active_model
        if refreshed_active.get("uploads"):
            st.write("Uploaded files")
            upload_rows = [
                {
                    "filename": u.get("filename", ""),
                    "uploaded_at": u.get("uploaded_at", ""),
                    "stored_path": u.get("stored_path", ""),
                }
                for u in refreshed_active.get("uploads", [])
            ]
            st.dataframe(pd.DataFrame(upload_rows), use_container_width=True)

    with tab_generate:
        st.subheader("Generate New Item")
        with st.form("generate_form"):
            item_type = st.selectbox("Item Type", ["measure", "flag", "column", "table"], index=0)
            description = st.text_input("Description", placeholder="Create month over month sales growth")
            conditions = st.text_input("Conditions (optional)", placeholder="where Sales > 1000")
            auto_register = st.checkbox("Auto-register item", value=True)
            submit = st.form_submit_button("Generate")

        if submit:
            if not description.strip():
                st.error("Description is required.")
            else:
                result = agent.generate_item(
                    description=description.strip(),
                    item_type=item_type,
                    conditions=conditions.strip(),
                    auto_register=auto_register,
                )

                st.success(f"✓ Generated: {result['name']} ({result['item_type']})")

                if result["validation_errors"]:
                    st.warning("Validation issues found:")
                    for issue in result["validation_errors"]:
                        st.write(f"- {issue}")
                else:
                    st.success("Validation passed.")

                # Show expression in expandable section
                with st.expander("📝 View Expression (DAX/Spark Query)", expanded=False):
                    st.code(result["expression"], language="sql")
                    st.write("**Explanation**")
                    st.write(result["explanation"])

                if result["similar_candidates"]:
                    st.write("**Similar candidates**")
                    for name, score in result["similar_candidates"]:
                        st.write(f"- {name} ({score:.2f})")

                st.write("**Optimization tips**")
                for tip in result["tips"]:
                    st.write(f"- {tip}")

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

    with tab_demo:
        st.subheader("Run Demo Scenario")
        st.write("This will generate demo items (measure, flag, measure, table).")
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

            st.success("✓ Demo completed. Items have been created and stored.")
            st.markdown("---")
            st.write("**Created Items:**")
            for idx, result in enumerate(results, start=1):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"[{idx}] {result['name']} ({result['item_type']})")
                with col2:
                    if st.button(f"View", key=f"demo_expr_{idx}"):
                        st.markdown("---")
                        with st.expander("📝 Expression", expanded=True):
                            st.code(result["expression"], language="sql")


def main() -> None:
    run_ui()


if __name__ == "__main__":
    main()
