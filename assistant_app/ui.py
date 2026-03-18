import csv
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from .cli import build_agent


def _items_to_dataframe(items: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in items:
        rows.append(
            {
                "name": item.get("name", ""),
                "item_type": item.get("item_type", ""),
                "description": item.get("description", ""),
                "expression": item.get("expression", ""),
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


def run_ui() -> None:
    st.set_page_config(
        page_title="Power BI Semantic Model Assistant",
        page_icon="PB",
        layout="wide",
    )

    st.title("Power BI Semantic Model Assistant")
    st.caption("Generate and manage measures, flags, columns, and tables from one dashboard.")

    with st.sidebar:
        st.header("Session")
        api_key_input = st.text_input(
            "OpenAI API Key (optional override)",
            type="password",
            value="",
            help="Leave blank to use OPENAI_API_KEY from .env",
        )
        force_reload = st.button("Reload Data")

    if "agent" not in st.session_state or force_reload:
        st.session_state.agent = build_agent(api_key=api_key_input or None)

    agent = st.session_state.agent

    all_items = list(agent.registry.items.values())
    generated_items = [i for i in all_items if i.get("source") == "generated"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Items", len(all_items))
    col2.metric("Generated", len(generated_items))
    col3.metric("Flags", len(agent.registry.get_items_by_type("flag")))
    col4.metric("Tables", len(agent.registry.get_items_by_type("table")))

    tab_generate, tab_items, tab_schema, tab_exports, tab_demo = st.tabs(
        ["Generate", "Created Items", "Schema", "Exports", "Demo"]
    )

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

                st.success(f"Generated: {result['name']}")
                st.write("**Expression**")
                st.code(result["expression"], language="sql")
                st.write("**Explanation**")
                st.write(result["explanation"])

                if result["validation_errors"]:
                    st.warning("Validation issues found:")
                    for issue in result["validation_errors"]:
                        st.write(f"- {issue}")
                else:
                    st.info("Validation passed.")

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

    with tab_exports:
        st.subheader("Export Outputs")
        export_name = st.text_input("CSV file name", value="created_items.csv")

        if st.button("Export Generated Items to CSV"):
            path = _export_created_csv(all_items, export_name)
            st.success(f"Exported generated items to: {path}")

        json_payload = agent.metadata.as_json()
        st.download_button(
            label="Download Schema JSON",
            data=json_payload,
            file_name="semantic_model_schema.json",
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

            st.success("Demo completed.")
            for idx, result in enumerate(results, start=1):
                st.write(f"[{idx}] {result['name']} ({result['item_type']})")
                st.code(result["expression"], language="sql")


def main() -> None:
    run_ui()


if __name__ == "__main__":
    main()
