import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from .training_engine import FabricModelTrainer

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

try:
    from groq import Groq
except Exception:  # pragma: no cover
    Groq = None


load_dotenv()
logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat()


def _safe_name(raw: str) -> str:
    value = re.sub(r"[^0-9A-Za-z_]+", "_", raw.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unnamed"


def _safe_col(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"[^0-9A-Za-z_ ]+", "", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_") or "column"


def configure_groq_client(api_key: Optional[str] = None):
    resolved = api_key or os.getenv("GROQ_API_KEY")
    if not resolved or Groq is None:
        return None
    try:
        return Groq(api_key=resolved, timeout=20.0)
    except Exception as exc:  # pragma: no cover
        logger.warning("Groq init failed, fallback mode: %s", exc)
        return None


def configure_openai_client(api_key: Optional[str] = None):
    """Backward-compatible alias used by existing imports.

    The runtime now prefers Groq, but several modules still import this symbol.
    """
    return configure_groq_client(api_key=api_key)


def _groq_model_candidates() -> List[str]:
    """Return preferred Groq models with safe fallbacks.

    Configure with:
    - GROQ_MODEL: primary model
    - GROQ_FALLBACK_MODELS: comma-separated fallback list
    """
    primary = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    fallback_env = os.getenv("GROQ_FALLBACK_MODELS", "llama-3.1-8b-instant").strip()
    fallbacks = [m.strip() for m in fallback_env.split(",") if m.strip()]

    models: List[str] = []
    for model in [primary, *fallbacks]:
        if model and model not in models:
            models.append(model)
    return models


def _groq_temperature() -> float:
    """Return Groq sampling temperature with safe defaults.

    Lower values reduce randomness and improve parity between environments.
    """
    raw_value = os.getenv("GROQ_TEMPERATURE", "0").strip()
    try:
        value = float(raw_value)
    except Exception:
        return 0.0
    return max(0.0, min(2.0, value))


class MetadataStore:
    """Persistent learning store for discovered model metadata."""

    def __init__(self, root: Optional[Path] = None, metadata: Optional[Dict[str, Any]] = None):
        self.root = root or (Path(__file__).resolve().parents[1] / ".fabric_assistant")
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.root / "metadata.json"
        self.registry_path = self.root / "registry.json"
        
        # If metadata is provided, use it; otherwise load from disk or use defaults
        if metadata is not None:
            self.metadata = metadata
        else:
            self.metadata = self._load_json(self.metadata_path, self._default_metadata())
        
        self.registry = self._load_json(self.registry_path, {"objects": {}})

    @staticmethod
    def _default_metadata() -> Dict[str, Any]:
        return {
            "tables": {},
            "relationships": [],
            "measures": {},
            "calculated_columns": {},
            "calculated_tables": {},
            "last_updated": _now(),
        }

    @staticmethod
    def _load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def save_metadata(self) -> None:
        self.metadata["last_updated"] = _now()
        self.metadata_path.write_text(json.dumps(self.metadata, indent=2), encoding="utf-8")

    def save_registry(self) -> None:
        self.registry["updated_at"] = _now()
        self.registry_path.write_text(json.dumps(self.registry, indent=2), encoding="utf-8")


class DataIngestionLayer:
    """Ingestion for CSV and Spark/Lakehouse/Warehouse-style tables."""

    def __init__(self, store: MetadataStore):
        self.store = store
        self.spark = None

    def _init_spark(self) -> None:
        if self.spark is not None:
            return
        try:
            self.spark = spark  # type: ignore[name-defined]
            return
        except NameError:
            pass
        if os.getenv("ENABLE_LOCAL_SPARK", "0") != "1":
            return
        try:
            from pyspark.sql import SparkSession

            self.spark = SparkSession.builder.appName("Universal_Fabric_Assistant").getOrCreate()
        except Exception:
            self.spark = None

    def load_data(self, csv_path: Optional[str] = None, table_name: Optional[str] = None) -> Dict[str, Any]:
        """load_data(): Load CSV/spark tables and keep Delta-ready metadata."""
        if csv_path:
            return self._load_csv(csv_path)
        if table_name:
            return self._load_table(table_name)
        return {"status": "noop", "message": "No data source provided."}

    def _load_csv(self, csv_path: str) -> Dict[str, Any]:
        path = Path(csv_path).expanduser()
        if not path.exists():
            return {"status": "error", "message": f"CSV not found: {path}"}
        if pd is None:
            return {"status": "error", "message": "pandas is required for CSV ingestion."}

        df = pd.read_csv(path)
        cleaned_columns = [_safe_col(c) for c in df.columns]
        df.columns = cleaned_columns

        table = _safe_name(path.stem)
        records_preview = df.head(5).to_dict(orient="records")

        columns_meta = {}
        for c in df.columns:
            dtype = str(df[c].dtype)
            if "int" in dtype:
                mapped = "int"
            elif "float" in dtype:
                mapped = "double"
            elif "datetime" in dtype:
                mapped = "timestamp"
            else:
                mapped = "string"
            columns_meta[c] = mapped

        self.store.metadata["tables"][table] = {
            "columns": columns_meta,
            "column_count": len(columns_meta),
            "source": "csv",
            "csv_path": str(path),
            "delta_target": f"{table}_delta",
            "loaded_at": _now(),
        }
        self.store.save_metadata()

        return {
            "status": "ok",
            "table": table,
            "rows": int(len(df)),
            "columns": cleaned_columns,
            "delta_target": f"{table}_delta",
            "preview": records_preview,
        }

    def _load_table(self, table_name: str) -> Dict[str, Any]:
        self._init_spark()
        tname = _safe_name(table_name)

        if self.spark is None:
            # Simulation mode for non-Spark local runs.
            if tname not in self.store.metadata["tables"]:
                self.store.metadata["tables"][tname] = {
                    "columns": {"id": "int", "value": "string"},
                    "column_count": 2,
                    "source": "table_reference",
                    "loaded_at": _now(),
                }
                self.store.save_metadata()
            return {
                "status": "ok",
                "table": tname,
                "mode": "simulated",
                "message": "Spark unavailable; table reference registered for metadata learning.",
            }

        try:
            sdf = self.spark.table(table_name)
            columns_meta = {f.name: str(f.dataType) for f in sdf.schema.fields}
            self.store.metadata["tables"][table_name] = {
                "columns": columns_meta,
                "column_count": len(columns_meta),
                "source": "spark",
                "loaded_at": _now(),
            }
            self.store.save_metadata()
            return {"status": "ok", "table": table_name, "mode": "spark", "columns": list(columns_meta.keys())}
        except Exception as exc:
            return {"status": "error", "message": f"Failed loading table {table_name}: {exc}"}


class ModelDiscoveryEngine:
    """Discover tables/columns/types and infer relationships."""

    def __init__(self, store: MetadataStore):
        self.store = store

    def discover_model(self) -> Dict[str, Any]:
        tables = self.store.metadata.get("tables", {})
        relationships = self.detect_relationships(tables)
        self.store.metadata["relationships"] = relationships
        self.store.save_metadata()
        return {
            "tables": tables,
            "relationships": relationships,
            "measures": self.store.metadata.get("measures", {}),
        }

    def detect_relationships(self, tables: Dict[str, Any]) -> List[Dict[str, str]]:
        rels: List[Dict[str, str]] = []
        # Heuristic key matching: shared id/key columns across tables.
        for left_name, left_info in tables.items():
            left_cols = set((left_info.get("columns") or {}).keys())
            for right_name, right_info in tables.items():
                if left_name == right_name:
                    continue
                right_cols = set((right_info.get("columns") or {}).keys())
                shared = left_cols.intersection(right_cols)
                for col in sorted(shared):
                    low = col.lower()
                    if low.endswith("id") or low.endswith("key"):
                        rels.append(
                            {
                                "name": f"{left_name}_{right_name}_{col}",
                                "from_table": left_name,
                                "from_column": col,
                                "to_table": right_name,
                                "to_column": col,
                            }
                        )
        # De-duplicate relationship signatures.
        seen = set()
        unique: List[Dict[str, str]] = []
        for r in rels:
            k = (r["from_table"], r["from_column"], r["to_table"], r["to_column"])
            rev = (r["to_table"], r["to_column"], r["from_table"], r["from_column"])
            if k in seen or rev in seen:
                continue
            seen.add(k)
            unique.append(r)
        return unique


class ContextBuilder:
    def __init__(self, metadata: Dict[str, Any]):
        self.metadata = metadata

    def build_context(self) -> str:
        """Build comprehensive context for Groq - detailed and structured."""
        lines = []
        lines.append("=" * 80)
        lines.append("POWER BI / MICROSOFT FABRIC MODEL CONTEXT")
        lines.append("=" * 80)
        
        # TABLES SECTION - Detailed
        lines.append("\n📊 TABLES AND COLUMNS:")
        lines.append("-" * 80)
        tables = self.metadata.get("tables", {})
        if not tables:
            lines.append("⚠️  No tables defined in the model")
        else:
            for table_name, info in tables.items():
                columns = info.get("columns", {})
                col_count = len(columns)
                lines.append(f"\n🔷 Table: {table_name} ({col_count} columns)")
                lines.append("  " + "─" * 76)
                
                if not columns:
                    lines.append("  ⚠️  No columns defined")
                else:
                    for col_name, col_type in sorted(columns.items()):
                        lines.append(f"    • {col_name:<40} → {col_type}")
        
        # RELATIONSHIPS SECTION
        lines.append("\n\n🔗 RELATIONSHIPS (Table Joins/Foreign Keys):")
        lines.append("-" * 80)
        relationships = self.metadata.get("relationships", [])
        if not relationships:
            lines.append("⚠️  No relationships defined")
        else:
            for rel in relationships:
                from_t = rel.get("from_table", "?")
                from_c = rel.get("from_column", "?")
                to_t = rel.get("to_table", "?")
                to_c = rel.get("to_column", "?")
                rel_name = rel.get("name", f"{from_t}_{to_t}")
                lines.append(f"\n  🔗 {rel_name}")
                lines.append(f"     {from_t}.{from_c} ════→ {to_t}.{to_c}")
        
        # MEASURES SECTION
        lines.append("\n\n📐 EXISTING MEASURES (Calculated Metrics):")
        lines.append("-" * 80)
        measures = self.metadata.get("measures", {})
        if not measures:
            lines.append("⚠️  No measures defined (you can create new ones)")
        else:
            for measure_name, measure_info in measures.items():
                expr = measure_info.get("expression", "")
                table = measure_info.get("table", "Unknown")
                lines.append(f"\n  📊 {measure_name} (in {table})")
                lines.append(f"     Expression: {expr}")
        
        # CALCULATED COLUMNS SECTION
        lines.append("\n\n⚙️  CALCULATED COLUMNS:")
        lines.append("-" * 80)
        calc_cols = self.metadata.get("calculated_columns", {})
        if not calc_cols:
            lines.append("⚠️  No calculated columns defined")
        else:
            for col_name, col_info in calc_cols.items():
                expr = col_info.get("expression", "")
                table = col_info.get("table", "Unknown")
                lines.append(f"\n  ⚙️  {col_name} (in {table})")
                lines.append(f"     Expression: {expr}")
        
        # CALCULATED TABLES SECTION
        lines.append("\n\n📋 CALCULATED TABLES:")
        lines.append("-" * 80)
        calc_tables = self.metadata.get("calculated_tables", {})
        if not calc_tables:
            lines.append("⚠️  No calculated tables defined")
        else:
            for table_name, table_info in calc_tables.items():
                expr = table_info.get("expression", "")
                lines.append(f"\n  📋 {table_name}")
                lines.append(f"     Expression: {expr}")
        
        lines.append("\n" + "=" * 80)
        lines.append("END OF MODEL CONTEXT")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def get_model_summary(self) -> Dict[str, Any]:
        """Return a machine-readable summary for UI display."""
        tables = self.metadata.get("tables", {})
        relationships = self.metadata.get("relationships", [])
        measures = self.metadata.get("measures", {})
        calc_cols = self.metadata.get("calculated_columns", {})
        calc_tables = self.metadata.get("calculated_tables", {})
        
        total_columns = sum(len(t.get("columns", {})) for t in tables.values())
        
        return {
            "table_count": len(tables),
            "total_columns": total_columns,
            "relationship_count": len(relationships),
            "measure_count": len(measures),
            "calculated_column_count": len(calc_cols),
            "calculated_table_count": len(calc_tables),
            "tables": {name: list(info.get("columns", {}).keys()) for name, info in tables.items()},
            "relationships": relationships,
            "measures": {name: info.get("expression", "") for name, info in measures.items()},
        }


class IntentDetectionEngine:
    def detect_intent(self, text: str, preferred_target: Optional[str] = None) -> Dict[str, Any]:
        q = text.strip()
        low = q.lower()

        # Universal/Fabric mode defaults to notebook-style code unless explicitly asking for DAX/semantic model.
        output_type = "pyspark_transformation"
        if preferred_target:
            t = preferred_target.lower()
            if t in {"semantic", "dax", "semantic_model"}:
                output_type = "dax_measure"
            elif t in {"warehouse", "sql", "sql_endpoint"}:
                output_type = "sql_query"
            elif t in {"notebook", "pyspark", "spark"}:
                output_type = "pyspark_transformation"
            elif t in {"python", "general"}:
                output_type = "python_logic"
        else:
            if any(k in low for k in ["measure", "dax", "semantic model", "calculated column", "calculated table"]):
                output_type = "dax_measure"
            elif any(k in low for k in ["sql", "warehouse", "select", "join"]):
                output_type = "sql_query"
            elif any(k in low for k in ["pyspark", "spark", "dataframe", "groupby"]):
                output_type = "pyspark_transformation"
            elif any(k in low for k in ["python", "script", "function"]):
                output_type = "python_logic"
            elif "column" in low:
                output_type = "dax_column"
            elif "table" in low:
                output_type = "dax_table"

        aggregations = [k for k in ["sum", "avg", "average", "count", "max", "min"] if k in low]
        time_logic = [k for k in ["month", "year", "yoy", "mom", "date", "quarter"] if k in low]
        conditions = self._extract_conditions(low)
        filters = self._extract_filters(low)

        action = "compute"
        if any(
            k in low
            for k in [
                "combine all tables",
                "join all tables",
                "full table",
                "denormalized table",
                "denormalized",
                "flatten",
                "wide table",
                "by joining",
            ]
        ):
            action = "denormalize_join"
        elif "create table" in low or ("create" in low and "table" in low):
            action = "create_table"
        elif any(k in low for k in ["group by", "groupby", "by customer", "by region", "by product"]):
            action = "group_aggregate"
        elif any(k in low for k in ["identify relationship", "detect relationship", "show relationship", "model relationship", "how tables connect"]):
            action = "identify_relationships"

        # For Fabric chat-style "full table/join all" asks, prefer notebook code in auto mode.
        if not preferred_target and action == "denormalize_join":
            if not any(k in low for k in ["sql", "warehouse", "dax", "semantic model"]):
                output_type = "pyspark_transformation"

        return {
            "output_type": output_type,
            "conditions": conditions,
            "filters": filters,
            "aggregations": aggregations,
            "time_logic": time_logic,
            "action": action,
            "raw": q,
        }

    @staticmethod
    def _extract_conditions(low: str) -> List[str]:
        conds = []
        m = re.search(r"where\s+(.+)", low)
        if m:
            conds.append(m.group(1).strip())
        return conds

    @staticmethod
    def _extract_filters(low: str) -> List[str]:
        return re.findall(r"(\w+\s*(?:=|>|<)\s*\w+)", low)


class MultiLanguageGenerationEngine:
    def __init__(self, client, context_builder: ContextBuilder):
        self.client = client
        self.context_builder = context_builder
        self.metadata = context_builder.metadata

    def build_generation_packet(self, intent: Dict[str, Any], user_params: Dict[str, Any]) -> str:
        """Build a comprehensive input packet with all context and parameters for Groq.
        
        This packet includes:
        - Full model context (tables, columns, relationships)
        - User parameters (item type, language, usage, name, description, conditions)
        - Requirements and validation rules
        
        This ensures every generation has complete information.
        """
        # Get model context
        context = self.context_builder.build_context()
        summary = self.context_builder.get_model_summary()
        
        # Extract user parameters
        item_type = user_params.get("item_type", "unknown")
        output_language = user_params.get("output_language", "unknown")
        usage_target = user_params.get("usage_target", "unknown")
        item_name = user_params.get("item_name", "")
        description = user_params.get("description", "")
        conditions = user_params.get("conditions", "")
        
        # Build the comprehensive packet
        packet = f"""
╔════════════════════════════════════════════════════════════════════════════════════════════════════╗
║                          🧠 COMPREHENSIVE CODE GENERATION PACKET                                  ║
╚════════════════════════════════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 PART 1: GROQ CONTEXT (CURRENT MODEL INFORMATION)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚙️  PART 2: MODEL SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 SCHEMA STATISTICS:
  • Total Tables: {summary.get('table_count', 0)}
  • Total Columns: {summary.get('total_columns', 0)}
  • Relationships: {summary.get('relationship_count', 0)}
  • Predefined Measures: {summary.get('measure_count', 0)}
  • Calculated Columns: {summary.get('calculated_column_count', 0)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 PART 3: USER REQUEST PARAMETERS (WHAT USER WANTS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 GENERATION CONFIGURATION:
  • Item Type: {item_type}
  • Output Language: {output_language}
  • Usage Target: {usage_target}
  • Item Name: {item_name!r}
  • Description: {description!r}
{f'  • Conditions: {conditions!r}' if conditions else '  • Conditions: (none)'}

🎯 USER INTENT:
  {intent.get('raw', 'Unknown')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ PART 4: STRICT REQUIREMENTS (WHAT GROQ MUST DO)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔒 MANDATORY RULES (DO NOT BREAK):
  1. ✓ Use ONLY tables shown in PART 1 schema
  2. ✓ Use ONLY columns shown for each table in PART 1
  3. ✓ Match user intent from PART 3 exactly
  4. ✓ Use user-provided item name: "{item_name}"
  5. ✓ Generate code for: {output_language}
  6. ✓ Code will be used in: {usage_target}
  7. ✓ NEVER invent, assume, or hallucinate any tables/columns
  8. ✓ Code must address the description: "{description}"
  {'✓ Code must satisfy condition: ' + conditions if conditions else ''}
  9. ✓ Provide output in exact format specified below

📍 AVAILABLE TABLES TO USE:
  {', '.join(summary.get('tables', {}).keys()) if summary.get('tables') else 'NONE - Schema is empty!'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 PART 5: OUTPUT FORMAT (REQUIRED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return EXACTLY in this format:

TYPE: <{output_language}>
CODE: <complete, working code that uses tables from line 'AVAILABLE TABLES' above>
EXPLANATION: <explain what this code does, which tables/columns it uses, and how it matches the intent>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Generate code NOW using only the schema and parameters above:
"""
        return packet

    def generate_code(self, intent: Dict[str, Any], user_params: Dict[str, Any] = None) -> Dict[str, str]:
        # Default to deterministic, schema-driven generation unless explicitly enabled.
        use_llm = os.getenv("FABRIC_ASSISTANT_USE_LLM", "0") == "1"

        if isinstance(user_params, dict):
            requested_name = str(user_params.get("item_name", "")).strip()
            if requested_name:
                intent["_item_name"] = requested_name
        
        # DEBUG: log what's happening
        print(f"🔵 generate_code: use_llm={use_llm}, client={self.client is not None}, has user_params={user_params is not None}", flush=True)
        
        if use_llm and self.client is not None:
            # Build comprehensive packet if user params provided
            if user_params:
                intent["_packet"] = self.build_generation_packet(intent, user_params)
            generated = self._generate_with_llm(intent)
            if generated:
                print(f"🟢 LLM generated result: type={generated.get('type')}", flush=True)
                return generated
            else:
                print("🔴 LLM returned None, falling back", flush=True)
        else:
            print(f"🟡 Skipping LLM: use_llm={use_llm}, client_ready={self.client is not None}", flush=True)
        
        return self._fallback(intent)

    def _validate_code_against_schema(self, code: str, intent: Dict[str, Any]) -> tuple[bool, str]:
        """Validate that generated code references only tables and columns that exist in the schema.
        
        Returns: (is_valid, error_message)
        """
        if not code or not code.strip():
            return False, "Generated code is empty"
        
        tables = self.context_builder.metadata.get("tables", {})
        if not tables:
            return False, "No tables defined in schema"
        
        # Extract table and column names from code
        code_lower = code.lower()
        all_tables = {t.lower(): t for t in tables.keys()}
        
        # Check if code references valid tables
        referenced_tables = []
        for table_lower, table_actual in all_tables.items():
            if table_lower in code_lower or f"[{table_actual}]" in code or f"{table_actual}[" in code:
                referenced_tables.append(table_actual)
        
        # If no tables referenced at all, that's suspicious
        if not referenced_tables and tables:
            return False, f"Generated code doesn't reference any tables. Available tables: {', '.join(tables.keys())}"
        
        # Validate referenced tables are in schema
        for ref_table in referenced_tables:
            if ref_table not in tables:
                return False, f"Generated code references table '{ref_table}' which doesn't exist in schema. Available: {', '.join(tables.keys())}"
            
            # Check columns in this table
            available_cols = list(tables[ref_table].get("columns", {}).keys())
            if not available_cols:
                return False, f"Table '{ref_table}' has no columns defined in schema"

        # Validate datatype usage before accepting generated output.
        dtype_ok, dtype_error = self._validate_datatype_usage(code, referenced_tables)
        if not dtype_ok:
            return False, dtype_error
        
        # Check intent alignment
        request_text = intent.get("raw", "").lower()
        code_content = code.lower()

        # Enforce aggregation only when request explicitly asks for aggregated output.
        # Do NOT treat generic "measure" requests as aggregation-only; boolean/flag measures are valid.
        aggregation_triggers = [
            "sum",
            "total",
            "aggregate",
            "avg",
            "average",
            "count",
            "distinct count",
            "distinctcount",
        ]
        if any(token in request_text for token in aggregation_triggers):
            if not any(
                kw in code_content
                for kw in [
                    "sum(",
                    "sumx(",
                    "avg(",
                    "average(",
                    "averagex(",
                    "count(",
                    "countx(",
                    "distinctcount(",
                    "min(",
                    "minx(",
                    "max(",
                    "maxx(",
                    "calculate(",
                    "divide(",
                ]
            ):
                return False, "Intent mentions aggregation but generated code doesn't use aggregation functions"
        
        return True, ""

    def _validate_datatype_usage(self, code: str, referenced_tables: List[str]) -> tuple[bool, str]:
        """Validate basic literal usage against schema datatypes."""
        if not code.strip():
            return False, "Generated code is empty"

        numeric_hints = ["int", "bigint", "double", "float", "decimal", "number"]
        bool_hints = ["bool", "boolean"]
        date_hints = ["date", "datetime", "timestamp", "time"]

        for table_name in referenced_tables:
            cols = (self.context_builder.metadata.get("tables", {}).get(table_name, {}) or {}).get("columns", {})
            if not isinstance(cols, dict):
                continue

            for col_name, dtype in cols.items():
                dtype_low = str(dtype).lower()
                col_escaped = re.escape(str(col_name))

                # Numeric columns should not be compared to quoted numbers.
                if any(h in dtype_low for h in numeric_hints):
                    bad_numeric_patterns = [
                        rf"\[{col_escaped}\]\s*(=|<>|!=|>|<|>=|<=)\s*['\"][-+]?\d+(?:\.\d+)?['\"]",
                        rf"\b{col_escaped}\b\s*(=|<>|!=|>|<|>=|<=)\s*['\"][-+]?\d+(?:\.\d+)?['\"]",
                    ]
                    if any(re.search(p, code, flags=re.IGNORECASE) for p in bad_numeric_patterns):
                        return False, f"Column '{col_name}' is numeric ({dtype}) but is compared with quoted numeric literal"

                # Boolean columns should not use quoted true/false values.
                if any(h in dtype_low for h in bool_hints):
                    bad_bool_patterns = [
                        rf"\[{col_escaped}\]\s*(=|<>|!=)\s*['\"](?:true|false|yes|no|0|1)['\"]",
                        rf"\b{col_escaped}\b\s*(=|<>|!=)\s*['\"](?:true|false|yes|no|0|1)['\"]",
                    ]
                    if any(re.search(p, code, flags=re.IGNORECASE) for p in bad_bool_patterns):
                        return False, f"Column '{col_name}' is boolean ({dtype}) but is compared with quoted boolean literal"

                # Date columns should not be compared to bare numerics.
                if any(h in dtype_low for h in date_hints):
                    bad_date_patterns = [
                        rf"\[{col_escaped}\]\s*(=|<>|!=|>|<|>=|<=)\s*\d+",
                        rf"\b{col_escaped}\b\s*(=|<>|!=|>|<|>=|<=)\s*\d+",
                    ]
                    if any(re.search(p, code, flags=re.IGNORECASE) for p in bad_date_patterns):
                        return False, f"Column '{col_name}' is date/time ({dtype}) but is compared with bare numeric literal"

        return True, ""
    
    def _generate_with_llm(self, intent: Dict[str, Any]) -> Optional[Dict[str, str]]:
        try:
            # Check if comprehensive packet exists (built by build_generation_packet)
            if "_packet" in intent:
                # Use the comprehensive packet with all context and parameters
                prompt = intent["_packet"]
            else:
                # Fall back to building prompt from context (legacy path)
                comprehensive_context = self.context_builder.build_context()
                metadata = self.context_builder.metadata
                tables = metadata.get("tables", {})
                relationships = metadata.get("relationships", [])
                
                table_list = ", ".join(tables.keys()) if tables else "NO TABLES"
                rel_list = ""
                if relationships:
                    rel_list = "\n".join([f"  • {r.get('from_table')}.{r.get('from_column')} → {r.get('to_table')}.{r.get('to_column')}" for r in relationships[:5]])
                
                prompt = (
                    f"{comprehensive_context}\n\n"
                    f"═══════════════════════════════════════════════════════════════════════════════════\n"
                    f"USER REQUEST (MUST GENERATE CODE MATCHING THIS):\n"
                    f"═══════════════════════════════════════════════════════════════════════════════════\n"
                    f"Question: {intent['raw']}\n"
                    f"Requested Output Type: {intent['output_type']}\n"
                    f"═══════════════════════════════════════════════════════════════════════════════════\n\n"
                    f"STRICT VALIDATION REQUIREMENTS:\n"
                    f"──────────────────────────────────────────────────────────────────────────────────\n"
                    f"✓ ONLY use these tables: {table_list}\n"
                    f"✓ ONLY use columns that exist in these tables (shown in schema above)\n"
                    f"✓ ALWAYS respect data types from schema (numeric/date/boolean must be used correctly)\n"
                    f"✓ ONLY use these relationships for joins:\n{rel_list if rel_list else '  (none defined)'}\n"
                    f"✓ NEVER invent, assume, or hallucinate table/column names\n"
                    f"✓ NEVER reference tables/columns not in the schema above\n"
                    f"✓ Code MUST match the user's request and use relevant data\n"
                    f"✓ If you cannot fulfill the request with available schema, REFUSE and explain why\n\n"
                    f"Return response in this exact format:\n"
                    f"TYPE: <DAX|SQL|PySpark|Python>\n"
                    f"CODE: <the complete, working code>\n"
                    f"EXPLANATION: <brief explanation of what this code does and which tables/columns it uses>\n"
                )
            
            res = None
            selected_model = ""
            last_error: Optional[Exception] = None
            for model_name in _groq_model_candidates():
                try:
                    res = self.client.chat.completions.create(
                        model=model_name,
                        temperature=_groq_temperature(),
                        max_tokens=2000,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are a code generation expert. "
                                    "Your ONLY job: Generate valid, complete code that directly fulfills the request. "
                                    "RULES: "
                                    "1) Use ONLY provided tables and columns "
                                    "2) Never invent or hallucinate entities "
                                    "3) Return ONLY the code - nothing else "
                                    "4) Code must be valid and production-ready "
                                    "5) Follow all requested conditions exactly "
                                    "6) For measures: include full definition with IF/AND/OR logic as needed "
                                    "7) For queries: return complete SELECT/CREATE statement "
                                    "If you cannot fulfill with available schema, say so."
                                )
                            },
                            {"role": "user", "content": prompt},
                        ],
                    )
                    selected_model = model_name
                    break
                except Exception as model_exc:
                    last_error = model_exc
                    model_msg = str(model_exc).lower()
                    # Retry on model lifecycle errors with next configured fallback model.
                    if any(k in model_msg for k in ["model_decommissioned", "does not exist", "not supported"]):
                        continue
                    raise

            if res is None:
                if last_error is not None:
                    raise last_error
                raise RuntimeError("No Groq response produced.")

            # Get the raw response from Groq
            raw_response = res.choices[0].message.content or ""
            
            if not raw_response.strip():
                print("🔴 Groq returned empty response", flush=True)
                return {
                    "type": "ERROR",
                    "code": "",
                    "explanation": "❌ Groq returned an empty response. This might be a provider-side filter issue.",
                    "raw_response": raw_response,
                    "model_used": selected_model,
                }
            
            # Extract code from the response. Some models may still return
            # TYPE/CODE/EXPLANATION wrappers despite instructions.
            c = raw_response.strip()
            
            # Remove markdown code fences if present
            c = re.sub(r'^```(?:dax|sql|python|pyspark)?\n', '', c, flags=re.I).lstrip()
            c = re.sub(r'\n```$', '', c).rstrip()

            # If wrapped format is returned, isolate only the CODE block.
            wrapped_match = re.search(r"(?is)\bCODE\s*:\s*(.*?)(?:\n\s*EXPLANATION\s*:|$)", c)
            if wrapped_match:
                c = wrapped_match.group(1).strip()

            # Strip stray TYPE/CODE labels if still present.
            c = re.sub(r"(?is)^\s*TYPE\s*:\s*[^\n]*\n", "", c).strip()
            c = re.sub(r"(?is)^\s*CODE\s*:\s*", "", c).strip()
            
            if not c:
                print(f"🔴 No code extracted from response: {raw_response[:100]}", flush=True)
                return {
                    "type": "ERROR",
                    "code": "",
                    "explanation": f"❌ Could not extract code from Groq response. Raw response:\n{raw_response}",
                    "raw_response": raw_response,
                    "model_used": selected_model,
                }
            
            # ===== Validate generated code against schema =====
            is_valid, error_msg = self._validate_code_against_schema(c, intent)
            if not is_valid:
                # Code doesn't match schema, return error instead
                return {
                    "type": "ERROR",
                    "code": c,
                    "explanation": f"⚠️ Generated code validation failed: {error_msg}\n\n**What was generated:** {c}",
                    "raw_response": raw_response,
                    "model_used": selected_model,
                }
            
            # Determine code type based on intent
            code_type = _map_intent_to_type(intent["output_type"])
            c = self._finalize_table_creation_output(c, code_type, intent)
            
            return {
                "type": code_type,
                "code": c,
                "explanation": f"Generated {code_type} {intent.get('item_type', 'code')} named '{intent.get('raw', 'item').split()[-1] if intent.get('raw') else 'item'}'.",
                "raw_response": raw_response,
                "model_used": selected_model,
            }
        except Exception as exc:
            # Report the actual error instead of silently returning None
            error_msg = str(exc)
            print(f"🔴 Groq API ERROR: {error_msg}", flush=True)
            
            # Check for specific API errors
            msg = error_msg.lower()
            if any(x in msg for x in ["insufficient_quota", "invalid_api_key", "401", "429"]):
                self.client = None
                return {
                    "type": "ERROR",
                    "code": "",
                    "explanation": f"❌ API Error: {error_msg}. Check your GROQ_API_KEY and Groq account limits.",
                    "raw_response": error_msg
                }
            elif "timeout" in msg or "deadline" in msg:
                return {
                    "type": "ERROR",
                    "code": "",
                    "explanation": f"❌ API Timeout: {error_msg}. Groq took too long to respond.",
                    "raw_response": error_msg
                }
            else:
                return {
                    "type": "ERROR",
                    "code": "",
                    "explanation": f"❌ Unexpected Error: {error_msg}",
                    "raw_response": error_msg
                }

    def _fallback(self, intent: Dict[str, Any]) -> Dict[str, str]:
        """Fallback generation - with error checking for invalid schemas."""
        try:
            # CRITICAL: Validate schema before attempting fallback generation
            table_name, value_col, date_col = self._pick_core_columns()
        except ValueError as e:
            # If schema validation fails, return error instead of invalid code
            return {
                "type": "ERROR",
                "code": str(e),
                "explanation": f"Cannot generate code: {str(e)}"
            }
        
        t = intent["output_type"]
        req = intent["raw"].lower()
        action = intent.get("action", "compute")

        group_col = self._pick_group_column(table_name, value_col, date_col)
        agg_kind = "avg" if any(k in req for k in ["average", "avg"]) else "sum"

        if t in {"dax_measure", "dax_column", "dax_table"}:
            if t == "dax_table" or action == "create_table":
                table_out_name = self._requested_item_name(intent) or "CalculatedTable"
                code = (
                    f"{table_out_name} = SUMMARIZE({table_name}, {table_name}[{group_col}], "
                    f"\"Metric\", {self._dax_agg(agg_kind, table_name, value_col)})"
                )
                return {"type": "DAX", "code": code, "explanation": "Creates a calculated table grouped by a business attribute."}

            if "month" in req and "growth" in req and date_col:
                code = (
                    f"VAR CurrentMonthValue = SUM({table_name}[{value_col}])\n"
                    f"VAR PrevMonthValue = CALCULATE(SUM({table_name}[{value_col}]), DATEADD({table_name}[{date_col}], -1, MONTH))\n"
                    "RETURN DIVIDE(CurrentMonthValue - PrevMonthValue, PrevMonthValue)"
                )
                return {"type": "DAX", "code": code, "explanation": "Computes month-over-month growth using time intelligence."}

            code = self._dax_agg(agg_kind, table_name, value_col)
            return {"type": "DAX", "code": code, "explanation": "Calculates an aggregate metric in the semantic model."}

        if t == "sql_query":
            if action == "denormalize_join":
                code, note = self._build_sql_join_query(req)
                return {
                    "type": "SQL",
                    "code": code,
                    "explanation": (
                        "Builds a denormalized table by joining model tables through detected/inferred relationships. "
                        + note
                    ).strip(),
                }
            if action in {"create_table", "group_aggregate"}:
                out_name = self._requested_item_name(intent)
                select_stmt = (
                    f"SELECT {group_col}, {self._sql_agg(agg_kind, value_col)} AS metric\n"
                    f"FROM {table_name}\n"
                    f"GROUP BY {group_col}"
                )
                if out_name:
                    code = f"CREATE OR REPLACE TABLE {out_name} AS\n{select_stmt};"
                else:
                    code = f"{select_stmt};"
            elif "total" in req or agg_kind in {"sum", "avg"}:
                code = f"SELECT {self._sql_agg(agg_kind, value_col)} AS metric FROM {table_name};"
            else:
                code = f"SELECT * FROM {table_name};"
            return {"type": "SQL", "code": code, "explanation": "Returns a warehouse/SQL endpoint query."}

        if t == "pyspark_transformation":
            if action == "denormalize_join":
                code, note = self._build_pyspark_join_code(req)
                return {
                    "type": "PySpark",
                    "code": code,
                    "explanation": (
                        "Builds a denormalized DataFrame by joining model tables through detected/inferred relationships. "
                        + note
                    ).strip(),
                }
            if action in {"create_table", "group_aggregate"}:
                out_name = self._requested_item_name(intent) or "result_table"
                code = (
                    f"result_df = df.groupBy('{group_col}').{self._pyspark_agg(agg_kind)}('{value_col}')"
                    f".withColumnRenamed('{self._spark_result_col(agg_kind, value_col)}', 'metric')\n"
                    f"result_df.createOrReplaceTempView('{out_name}')\n"
                    f"result_df.write.mode('overwrite').saveAsTable('{out_name}')"
                )
            elif "total" in req or agg_kind in {"sum", "avg"}:
                code = (
                    f"result_df = df.groupBy().{self._pyspark_agg(agg_kind)}('{value_col}')"
                    f".withColumnRenamed('{self._spark_result_col(agg_kind, value_col)}', 'metric')"
                )
            else:
                code = f"result_df = df.select('{group_col}', '{value_col}')"
            return {"type": "PySpark", "code": code, "explanation": "Returns a notebook PySpark transformation."}

        code = "def transform(records):\n    return records"
        return {"type": "Python", "code": code, "explanation": "Returns generic Python logic."}

    @staticmethod
    def _requested_item_name(intent: Dict[str, Any]) -> str:
        return str(intent.get("_item_name", "")).strip()

    def _is_table_creation_request(self, intent: Dict[str, Any]) -> bool:
        raw = str(intent.get("raw", "")).lower()
        action = str(intent.get("action", "")).lower()
        output_type = str(intent.get("output_type", "")).lower()
        return (
            action in {"create_table", "denormalize_join", "group_aggregate"}
            or output_type == "dax_table"
            or ("create" in raw and "table" in raw)
        )

    def _finalize_table_creation_output(self, code: str, generated_type: str, intent: Dict[str, Any]) -> str:
        """Append save/create statements for table outputs using requested item name."""
        item_name = self._requested_item_name(intent)
        if not item_name or not self._is_table_creation_request(intent):
            return code

        c = code.strip()
        gt = (generated_type or "").strip().lower()

        if gt == "pyspark":
            lowered = c.lower()
            if (
                f"saveastable('{item_name.lower()}')" in lowered
                or f'createorreplacetempview("{item_name.lower()}")' in lowered
                or f"createorreplacetempview('{item_name.lower()}')" in lowered
            ):
                return c

            vars_found = re.findall(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", c)
            df_var = vars_found[-1] if vars_found else "result_df"
            return (
                f"{c}\n\n"
                f"# Persist final table using requested item name\n"
                f"{df_var}.createOrReplaceTempView('{item_name}')\n"
                f"{df_var}.write.mode('overwrite').saveAsTable('{item_name}')"
            )

        if gt == "sql":
            lowered = c.lower()
            if "create table" in lowered and item_name.lower() in lowered:
                return c

            select_sql = c.rstrip(";")
            return f"CREATE OR REPLACE TABLE {item_name} AS\n{select_sql};"

        if gt == "dax":
            if c.lower().startswith(f"{item_name.lower()} "):
                return c
            return f"{item_name} = {c}"

        return c

    def _pick_core_columns(self) -> Tuple[str, str, Optional[str]]:
        tables = self.metadata.get("tables", {}) if isinstance(self.metadata, dict) else {}
        
        # CRITICAL: If no tables or no columns in any table, raise error instead of using placeholders
        if not tables:
            raise ValueError(
                "❌ GENERATION FAILED: No tables defined in schema. "
                "Upload a PBIX file or define your schema first."
            )
        
        # Check if any table has columns defined
        has_any_columns = any(
            t.get("columns") 
            for t in tables.values()
        )
        if not has_any_columns:
            raise ValueError(
                "❌ GENERATION FAILED: Tables exist but have no columns defined. "
                "Ensure your schema includes column information."
            )

        profile = self.metadata.get("training_profile", {}) if isinstance(self.metadata.get("training_profile", {}), dict) else {}
        preferred_table = profile.get("preferred_table")
        preferred_value = profile.get("preferred_value_column")
        preferred_date = profile.get("preferred_date_column")

        if preferred_table and preferred_table in tables:
            cols = list((tables.get(preferred_table, {}).get("columns") or {}).keys())
            if cols:
                value_col = cols[0]
                date_col = None
                if isinstance(preferred_value, str) and "." in preferred_value:
                    p_table, p_col = preferred_value.split(".", 1)
                    if p_table == preferred_table and p_col in cols:
                        value_col = p_col
                if isinstance(preferred_date, str) and "." in preferred_date:
                    p_table, p_col = preferred_date.split(".", 1)
                    if p_table == preferred_table and p_col in cols:
                        date_col = p_col
                return (preferred_table, value_col, date_col)

        # Prefer tables with finance-like value columns.
        candidates = []
        for tname, info in tables.items():
            cols = list((info.get("columns") or {}).keys())
            if not cols:  # Skip tables with no columns
                continue
            low_cols = [c.lower() for c in cols]
            value_idx = None
            for i, c in enumerate(low_cols):
                if any(k in c for k in ["sales", "amount", "revenue", "total", "value", "price"]):
                    value_idx = i
                    break
            date_idx = None
            for i, c in enumerate(low_cols):
                if any(k in c for k in ["date", "month", "year"]):
                    date_idx = i
                    break
            if value_idx is not None:
                value_col = cols[value_idx]
            elif cols:
                value_col = cols[0]
            else:
                value_col = "value"
            date_col = cols[date_idx] if date_idx is not None else None
            score = 1 if value_idx is not None else 0
            candidates.append((score, tname, value_col, date_col))

        if not candidates:
            raise ValueError(
                "❌ GENERATION FAILED: Could not find valid tables with columns. "
                "Please verify your schema has columns defined."
            )
        
        candidates.sort(key=lambda x: x[0], reverse=True)
        _, tname, value_col, date_col = candidates[0]
        return (tname, value_col, date_col)

    def _pick_group_column(self, table_name: str, value_col: str, date_col: Optional[str]) -> str:
        tables = self.metadata.get("tables", {}) if isinstance(self.metadata, dict) else {}
        cols = tables.get(table_name, {}).get("columns", {}) if table_name in tables else {}
        if not isinstance(cols, dict) or not cols:
            return value_col

        for col, dtype in cols.items():
            low = col.lower()
            if col == value_col or (date_col and col == date_col):
                continue
            if any(k in low for k in ["name", "category", "region", "segment", "product", "customer", "type"]):
                return col
            if "string" in str(dtype).lower():
                return col

        for col in cols.keys():
            if col != value_col:
                return col
        return value_col

    @staticmethod
    def _dax_agg(kind: str, table_name: str, value_col: str) -> str:
        if kind == "avg":
            return f"AVERAGE({table_name}[{value_col}])"
        if kind == "count":
            return f"COUNT({table_name}[{value_col}])"
        return f"SUM({table_name}[{value_col}])"

    @staticmethod
    def _sql_agg(kind: str, value_col: str) -> str:
        if kind == "avg":
            return f"AVG({value_col})"
        if kind == "count":
            return f"COUNT({value_col})"
        return f"SUM({value_col})"

    @staticmethod
    def _pyspark_agg(kind: str) -> str:
        if kind == "avg":
            return "avg"
        if kind == "count":
            return "count"
        return "sum"

    @staticmethod
    def _spark_result_col(kind: str, value_col: str) -> str:
        fn = "avg" if kind == "avg" else "count" if kind == "count" else "sum"
        return f"{fn}({value_col})"

    def _build_sql_join_query(self, req: str) -> Tuple[str, str]:
        tables = self.metadata.get("tables", {}) if isinstance(self.metadata, dict) else {}
        rels = self._effective_relationships()
        if not tables:
            return "SELECT * FROM Sales;", ""

        if not rels:
            first = next(iter(tables.keys()))
            return f"SELECT * FROM {first};", "No relationships found; returning base table only."

        requested_base = self._extract_requested_base_table(req, tables)
        base = requested_base or self._pick_base_table_from_relationships(rels, tables)
        aliases = {base: "t0"}
        joined = {base}
        lines = [f"SELECT t0.*", f"FROM {base} t0"]
        alias_count = 1

        progress = True
        while progress:
            progress = False
            for rel in rels:
                ft = rel.get("from_table", "")
                fc = rel.get("from_column", "")
                tt = rel.get("to_table", "")
                tc = rel.get("to_column", "")
                if not (ft and fc and tt and tc):
                    continue

                if ft in joined and tt not in joined:
                    aliases.setdefault(tt, f"t{alias_count}")
                    alias_count += 1
                    lines.append(
                        f"LEFT JOIN {tt} {aliases[tt]} ON {aliases[ft]}.{fc} = {aliases[tt]}.{tc}"
                    )
                    joined.add(tt)
                    progress = True
                elif tt in joined and ft not in joined:
                    aliases.setdefault(ft, f"t{alias_count}")
                    alias_count += 1
                    lines.append(
                        f"LEFT JOIN {ft} {aliases[ft]} ON {aliases[tt]}.{tc} = {aliases[ft]}.{fc}"
                    )
                    joined.add(ft)
                    progress = True

        unjoined = [t for t in tables.keys() if t not in joined]
        note = ""
        if unjoined:
            note = f"Unjoined tables (missing join keys): {', '.join(unjoined)}."

        return "\n".join(lines) + ";", note

    def _build_pyspark_join_code(self, req: str) -> Tuple[str, str]:
        tables = self.metadata.get("tables", {}) if isinstance(self.metadata, dict) else {}
        rels = self._effective_relationships()
        if not tables:
            return "result_df = df", ""

        if not rels:
            first = next(iter(tables.keys()))
            return (
                f"result_df = {first}\nresult_df.createOrReplaceTempView('full_model_table')",
                "No relationships found; returning base table only.",
            )

        requested_base = self._extract_requested_base_table(req, tables)
        base = requested_base or self._pick_base_table_from_relationships(rels, tables)
        joined = {base}
        lines = [f"result_df = {base}"]

        progress = True
        join_num = 1
        while progress:
            progress = False
            for rel in rels:
                ft = rel.get("from_table", "")
                fc = rel.get("from_column", "")
                tt = rel.get("to_table", "")
                tc = rel.get("to_column", "")
                if not (ft and fc and tt and tc):
                    continue

                # Clean column names (remove BOM and special chars)
                fc_clean = fc.replace('\ufeff', '').strip()
                tc_clean = tc.replace('\ufeff', '').strip()
                
                relationship_desc = rel.get("name", f"{ft}→{tt}")

                if ft in joined and tt not in joined:
                    lines.append("")
                    lines.append(f"# Join {join_num}: {tt} table")
                    lines.append(f"# Relationship: {relationship_desc}")
                    lines.append(
                        f"result_df = result_df.join(\n"
                        f"    {tt},\n"
                        f"    result_df['{fc_clean}'] == {tt}['{tc_clean}'],\n"
                        f"    'left'\n"
                        f")"
                    )
                    joined.add(tt)
                    progress = True
                    join_num += 1
                elif tt in joined and ft not in joined:
                    # Check if we can join through an intermediate table
                    lines.append("")
                    lines.append(f"# Join {join_num}: {ft} table (via {tt})")
                    lines.append(f"# Relationship: {relationship_desc}")
                    lines.append(
                        f"result_df = result_df.join(\n"
                        f"    {ft},\n"
                        f"    {tt}['{tc_clean}'] == {ft}['{fc_clean}'],\n"
                        f"    'left'\n"
                        f")"
                    )
                    joined.add(ft)
                    progress = True
                    join_num += 1

        lines.append("")
        lines.append("# Create final view")
        view_name = self._extract_requested_view_name(req) or "full_model_table"
        lines.append(f"result_df.createOrReplaceTempView('{view_name}')")
        
        unjoined = [t for t in tables.keys() if t not in joined]
        note = ""
        if unjoined:
            note = f"Unjoined tables (missing join keys): {', '.join(unjoined)}."
        return "\n".join(lines), note

    def _effective_relationships(self) -> List[Dict[str, str]]:
        rels = self.metadata.get("relationships", []) if isinstance(self.metadata, dict) else []
        table_map = self.metadata.get("tables", {}) if isinstance(self.metadata, dict) else {}
        if not isinstance(rels, list):
            rels = []
        inferred = self._infer_relationships_from_tables(table_map)

        seen = set()
        merged: List[Dict[str, str]] = []
        for rel in list(rels) + inferred:
            if not isinstance(rel, dict):
                continue
            ft = rel.get("from_table", "")
            fc = rel.get("from_column", "")
            tt = rel.get("to_table", "")
            tc = rel.get("to_column", "")
            if not (ft and fc and tt and tc):
                continue
            k = (ft, fc, tt, tc)
            rk = (tt, tc, ft, fc)
            if k in seen or rk in seen:
                continue
            seen.add(k)
            merged.append(
                {
                    "name": rel.get("name", f"{ft}_{tt}_{fc}"),
                    "from_table": ft,
                    "from_column": fc,
                    "to_table": tt,
                    "to_column": tc,
                }
            )
        return merged

    @staticmethod
    def _infer_relationships_from_tables(tables: Dict[str, Any]) -> List[Dict[str, str]]:
        if not isinstance(tables, dict):
            return []
        rels: List[Dict[str, str]] = []
        names = list(tables.keys())
        for i, left_name in enumerate(names):
            left_cols = set((tables.get(left_name, {}).get("columns") or {}).keys())
            for j, right_name in enumerate(names):
                if i >= j:
                    continue
                right_cols = set((tables.get(right_name, {}).get("columns") or {}).keys())
                shared = sorted(left_cols.intersection(right_cols))
                for col in shared:
                    low = col.lower()
                    if low.endswith("id") or low.endswith("key"):
                        rels.append(
                            {
                                "name": f"{left_name}_{right_name}_{col}",
                                "from_table": left_name,
                                "from_column": col,
                                "to_table": right_name,
                                "to_column": col,
                            }
                        )
        return rels

    @staticmethod
    def _extract_requested_base_table(req: str, tables: Dict[str, Any]) -> Optional[str]:
        low = req.lower()
        m = re.search(r"base\s+table\s*[:=]?\s*([a-zA-Z_][a-zA-Z0-9_]*)", low)
        if not m:
            m = re.search(r"use\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s+base", low)
        if not m:
            return None
        wanted = m.group(1).strip().lower()
        for t in tables.keys():
            if t.lower() == wanted:
                return t
        return None

    @staticmethod
    def _extract_requested_view_name(req: str) -> Optional[str]:
        """Extract requested view/table name from user request."""
        low = req.lower()
        # Try patterns like "createOrReplaceTempView('name')" or "create view name"
        m = re.search(r"(?:create.*view|temp.*view)\s*['\"]?([a-zA-Z_][a-zA-Z0-9_]*)['\"]?", low)
        if not m:
            # Try "as 'name'" pattern
            m = re.search(r"as\s*['\"]([a-zA-Z_][a-zA-Z0-9_]*)['\"]", low)
        if not m:
            # Try "call it 'name'" or "name it"
            m = re.search(r"(?:call|name)\s+(?:it\s+)?['\"]?([a-zA-Z_][a-zA-Z0-9_]*)['\"]?", low)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _pick_base_table_from_relationships(rels: List[Dict[str, str]], tables: Dict[str, Any]) -> str:
        degree: Dict[str, int] = {t: 0 for t in tables.keys()}
        for rel in rels:
            ft = rel.get("from_table", "")
            tt = rel.get("to_table", "")
            if ft in degree:
                degree[ft] += 1
            if tt in degree:
                degree[tt] += 1
        # Prefer the most connected table as join anchor.
        return sorted(degree.items(), key=lambda x: x[1], reverse=True)[0][0]


class ValidationEngine:
    def __init__(self, metadata: Dict[str, Any]):
        self.metadata = metadata

    def validate_code(self, generated_type: str, code: str) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        if not code.strip():
            issues.append("Generated code is empty.")

        if generated_type.upper() in {"DAX", "SQL"}:
            if not _balanced(code):
                issues.append("Unbalanced brackets or parentheses.")

        if generated_type.upper() == "DAX":
            refs = re.findall(r"(\w+)\[(\w+)\]", code)
            for t, c in refs:
                table = self.metadata.get("tables", {}).get(t)
                if not table:
                    issues.append(f"Table not found: {t}")
                    continue
                if c not in table.get("columns", {}):
                    issues.append(f"Column not found: {t}[{c}]")
            
            # Check for semantic errors
            code_upper = code.upper()
            
            # Check if summing ID/Key columns (common mistake)
            # More precise regex: match only SUM(Table[IDColumn]) pattern specifically
            id_key_pattern = r"SUM\s*\(\s*(\w+)\s*\[\s*(\w*(?:Key|ID|EmployeeKey|ProductKey|OrderID|CustomerID)\w*)\s*\]\s*\)"
            id_matches = re.findall(id_key_pattern, code, re.IGNORECASE)
            if id_matches:
                # Format matches as "Table[Column]"
                formatted_matches = [f"{table}[{col}]" for table, col in id_matches]
                issues.append(f"⚠️ WARNING: You're using SUM() on ID/Key columns: {', '.join(formatted_matches)}. Use DISTINCTCOUNT() instead to count unique IDs, or SUM() on actual numeric values (SalesAmount, Price, Cost, etc).")
            
            # Check if average order value pattern is missing DISTINCTCOUNT
            if any(x in code.lower() for x in ["average order", "avgorder"]):
                if "DISTINCTCOUNT" not in code_upper and "AVERAGE" not in code_upper:
                    issues.append("⚠️ Average Order Value should use: DIVIDE(SUM(amount), DISTINCTCOUNT(OrderID))")

        if generated_type.upper() == "SQL":
            if "select" not in code.lower():
                issues.append("SQL must include SELECT.")

        if generated_type.lower() == "pyspark":
            if "df" not in code and "spark" not in code:
                issues.append("PySpark code should reference df or spark context.")

        return (len(issues) == 0), issues


class DuplicateDetectionEngine:
    def __init__(self, store: MetadataStore):
        self.store = store

    def detect_duplicate(self, object_name: str, object_type: str) -> bool:
        key = f"{object_type}:{object_name}".lower()
        return key in self.store.registry.get("objects", {})

    def register(self, object_name: str, object_type: str, code: str, lang: str, request: str) -> None:
        key = f"{object_type}:{object_name}".lower()
        self.store.registry.setdefault("objects", {})[key] = {
            "name": object_name,
            "object_type": object_type,
            "language": lang,
            "code": code,
            "request": request,
            "created_at": _now(),
        }
        self.store.save_registry()


class ExplanationEngine:
    @staticmethod
    def explain_output(generated_type: str, code: str, base: str = "") -> str:
        parts: List[str] = []
        if base:
            parts.append(base)
        up = code.upper()
        if generated_type.upper() == "DAX":
            if "SUM(" in up:
                parts.append("It aggregates numeric values in the semantic model.")
            if "CALCULATE(" in up:
                parts.append("It modifies filter context for the calculation.")
        elif generated_type.upper() == "SQL":
            parts.append("This query runs on Warehouse or SQL endpoint tables.")
        elif generated_type.lower() == "pyspark":
            parts.append("This transformation is designed for Fabric notebooks.")
        else:
            parts.append("This Python logic can be used for generic transformations.")
        return " ".join(parts).strip()


class ExecutionEngine:
    def execute(self, generated_type: str, code: str) -> Dict[str, Any]:
        t = generated_type.lower()
        if t == "pyspark":
            # In local/CLI mode we return executable snippet text, notebook can execute it directly.
            return {"mode": "notebook", "status": "ready", "message": "Run this PySpark code in Fabric notebook.", "code": code}
        if t == "sql":
            return {"mode": "sql", "status": "simulated", "query": code}
        if t == "dax":
            return {"mode": "semantic_model", "status": "ready", "expression": code}
        return {"mode": "python", "status": "ready", "code": code}


@dataclass
class UniversalFabricAssistant:
    store: MetadataStore
    ingestion: DataIngestionLayer
    discovery: ModelDiscoveryEngine
    detector: IntentDetectionEngine
    generator: MultiLanguageGenerationEngine
    executor: ExecutionEngine
    duplicate: DuplicateDetectionEngine

    def build_context(self) -> str:
        return ContextBuilder(self.store.metadata).build_context()

    def train_model(self) -> Dict[str, Any]:
        expressions: List[str] = []

        # Learn from generated objects in registry
        for obj in self.store.registry.get("objects", {}).values():
            if isinstance(obj, dict):
                code = str(obj.get("code", ""))
                if code:
                    expressions.append(code)

        # Learn from existing measures in metadata
        for measure in self.store.metadata.get("measures", {}).values():
            if isinstance(measure, dict):
                expr = str(measure.get("expression", ""))
                if expr:
                    expressions.append(expr)

        profile = FabricModelTrainer.train(self.store.metadata, expressions)
        self.store.metadata["training_profile"] = profile
        self.store.metadata.setdefault("training_history", []).append(
            {
                "trained_at": profile.get("trained_at"),
                "observed_expression_count": profile.get("observed_expression_count", 0),
                "preferred_table": profile.get("preferred_table"),
            }
        )
        self.store.save_metadata()
        return profile

    def run_once(self, user_input: str, target: Optional[str] = None, user_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        intent = self.detector.detect_intent(user_input, preferred_target=target)

        if intent.get("action") == "identify_relationships":
            discovery = self.discovery.discover_model()
            relationships = discovery.get("relationships", [])
            paste_ready = self._relationship_paste_ready_sql(relationships)
            return {
                "type": "RELATIONSHIPS",
                "code": json.dumps(relationships, indent=2),
                "paste_ready_query": paste_ready,
                "explanation": f"Identified {len(relationships)} relationship(s) from model metadata.",
                "validation": "passed",
                "errors": [],
                "intent": intent,
                "execution": {"mode": "metadata", "status": "ready"},
                "object_name": "model_relationships",
                "relationships": relationships,
            }

        # ENHANCED: Pass user_params to generator for comprehensive packet building
        generated = self.generator.generate_code(intent, user_params=user_params)
        generated = self._enforce_target_output_type(generated=generated, intent=intent, target=target)

        requested_name = ""
        if isinstance(user_params, dict):
            requested_name = str(user_params.get("item_name", "")).strip()

        object_name = requested_name or self._derive_object_name(user_input, intent["output_type"])
        object_type = intent["output_type"]

        paste_ready_query = self._build_paste_ready_query(
            object_name=object_name,
            object_type=object_type,
            generated_type=generated["type"],
            code=generated["code"],
        )

        if self.duplicate.detect_duplicate(object_name, object_type):
            return {
                "type": generated["type"],
                "code": generated["code"],
                "paste_ready_query": paste_ready_query,
                "explanation": f"Duplicate detected for {object_name}. Existing object preserved.",
                "validation": "failed",
                "errors": ["Duplicate object detected."],
                "intent": intent,
            }

        validator = ValidationEngine(self.store.metadata)
        ok, errors = validator.validate_code(generated["type"], generated["code"])
        validation = "passed" if ok else "failed"

        explanation = ExplanationEngine.explain_output(
            generated["type"],
            generated["code"],
            base=generated.get("explanation", ""),
        )

        if ok:
            self.duplicate.register(
                object_name=object_name,
                object_type=object_type,
                code=generated["code"],
                lang=generated["type"],
                request=user_input,
            )

            if generated["type"].upper() == "DAX" and object_type == "dax_measure":
                self.store.metadata.setdefault("measures", {})[object_name] = {
                    "expression": generated["code"],
                    "description": user_input,
                    "created_at": _now(),
                }
                self.store.save_metadata()

        execution = self.executor.execute(generated["type"], generated["code"])

        return {
            "type": generated["type"],
            "code": generated["code"],
            "paste_ready_query": paste_ready_query,
            "explanation": explanation,
            "validation": validation,
            "errors": errors,
            "intent": intent,
            "execution": execution,
            "object_name": object_name,
        }

    @staticmethod
    def _build_paste_ready_query(object_name: str, object_type: str, generated_type: str, code: str) -> str:
        g = generated_type.upper()
        if g == "DAX":
            if object_type in {"dax_measure", "dax_column", "dax_table"}:
                return f"{object_name} =\n{code}"
            return code
        return code

    def _enforce_target_output_type(
        self,
        generated: Dict[str, str],
        intent: Dict[str, Any],
        target: Optional[str],
    ) -> Dict[str, str]:
        """Force output type to match user-selected target when needed."""
        target_to_type = {
            "semantic": "DAX",
            "dax": "DAX",
            "semantic_model": "DAX",
            "warehouse": "SQL",
            "sql": "SQL",
            "sql_endpoint": "SQL",
            "notebook": "PySpark",
            "pyspark": "PySpark",
            "spark": "PySpark",
            "python": "Python",
            "general": "Python",
        }

        expected = None
        if target:
            expected = target_to_type.get(str(target).lower())

        # In auto mode, rely on detected output type expectation.
        if expected is None:
            expected = _map_intent_to_type(intent.get("output_type", "python_logic"))

        actual = str(generated.get("type", "")).strip()

        # Preserve explicit generation errors from LLM; do not replace with fallback code.
        if actual.upper() == "ERROR":
            return generated

        if actual.lower() == str(expected).lower():
            return generated

        # If mismatched (e.g., LLM returned DAX for notebook), regenerate via deterministic fallback.
        corrected_intent = dict(intent)
        reverse_map = {
            "DAX": "dax_measure",
            "SQL": "sql_query",
            "PySpark": "pyspark_transformation",
            "Python": "python_logic",
        }
        corrected_intent["output_type"] = reverse_map.get(expected, corrected_intent.get("output_type", "python_logic"))
        forced = self.generator._fallback(corrected_intent)
        forced["explanation"] = (
            f"Output was auto-corrected to {expected} to match selected target. "
            + forced.get("explanation", "")
        ).strip()
        return forced

    @staticmethod
    def _relationship_paste_ready_sql(relationships: List[Dict[str, str]]) -> str:
        if not relationships:
            return "-- No relationships found to build JOIN template."

        first = relationships[0]
        f_table = first.get("from_table", "table_a")
        f_col = first.get("from_column", "id")
        t_table = first.get("to_table", "table_b")
        t_col = first.get("to_column", "id")
        return (
            f"SELECT a.*, b.*\n"
            f"FROM {f_table} a\n"
            f"JOIN {t_table} b ON a.{f_col} = b.{t_col};"
        )

    @staticmethod
    def _derive_object_name(text: str, object_type: str) -> str:
        base = _safe_name(text)[:70]
        return f"{object_type}_{base}"[:90]


def _balanced(text: str) -> bool:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: List[str] = []
    for ch in text:
        if ch in pairs:
            stack.append(ch)
        elif ch in pairs.values():
            if not stack:
                return False
            top = stack.pop()
            if pairs[top] != ch:
                return False
    return not stack


def _extract_field(text: str, label: str) -> str:
    m = re.search(rf"{label}:\s*(.*)", text)
    return m.group(1).strip() if m else ""


def _extract_block(text: str, label: str, next_label: str) -> str:
    m = re.search(rf"{label}:\s*(.*?)(?:\n{next_label}:|\Z)", text, flags=re.S)
    return m.group(1).strip() if m else ""


def _map_intent_to_type(output_type: str) -> str:
    if output_type.startswith("dax"):
        return "DAX"
    if output_type.startswith("sql"):
        return "SQL"
    if output_type.startswith("pyspark"):
        return "PySpark"
    return "Python"


# Required function-style API surface requested by the user.
def load_data(csv_path: Optional[str] = None, table_name: Optional[str] = None) -> Dict[str, Any]:
    store = MetadataStore()
    ingestion = DataIngestionLayer(store)
    return ingestion.load_data(csv_path=csv_path, table_name=table_name)


def discover_model() -> Dict[str, Any]:
    store = MetadataStore()
    discovery = ModelDiscoveryEngine(store)
    return discovery.discover_model()


def detect_relationships() -> List[Dict[str, str]]:
    store = MetadataStore()
    discovery = ModelDiscoveryEngine(store)
    tables = store.metadata.get("tables", {})
    rels = discovery.detect_relationships(tables)
    store.metadata["relationships"] = rels
    store.save_metadata()
    return rels


def build_context() -> str:
    store = MetadataStore()
    return ContextBuilder(store.metadata).build_context()


def detect_intent(user_input: str, preferred_target: Optional[str] = None) -> Dict[str, Any]:
    detector = IntentDetectionEngine()
    return detector.detect_intent(user_input, preferred_target=preferred_target)


def generate_code(user_input: str, preferred_target: Optional[str] = None, api_key: Optional[str] = None) -> Dict[str, Any]:
    store = MetadataStore()
    client = configure_groq_client(api_key=api_key)
    context_builder = ContextBuilder(store.metadata)
    detector = IntentDetectionEngine()
    intent = detector.detect_intent(user_input, preferred_target=preferred_target)
    generator = MultiLanguageGenerationEngine(client, context_builder)
    return generator.generate_code(intent)


def validate_code(generated_type: str, code: str) -> Tuple[bool, List[str]]:
    store = MetadataStore()
    validator = ValidationEngine(store.metadata)
    return validator.validate_code(generated_type, code)


def detect_duplicate(object_name: str, object_type: str) -> bool:
    store = MetadataStore()
    dup = DuplicateDetectionEngine(store)
    return dup.detect_duplicate(object_name, object_type)


def explain_output(generated_type: str, code: str) -> str:
    return ExplanationEngine.explain_output(generated_type, code)


def run_agent(api_key: Optional[str] = None) -> None:
    store = MetadataStore()
    client = configure_groq_client(api_key=api_key)
    assistant = UniversalFabricAssistant(
        store=store,
        ingestion=DataIngestionLayer(store),
        discovery=ModelDiscoveryEngine(store),
        detector=IntentDetectionEngine(),
        generator=MultiLanguageGenerationEngine(client, ContextBuilder(store.metadata)),
        executor=ExecutionEngine(),
        duplicate=DuplicateDetectionEngine(store),
    )

    print("\nUniversal Fabric AI Assistant")
    print("Type 'help' for commands or 'exit' to quit.\n")

    while True:
        cmd = input("fabric> ").strip()
        if not cmd:
            continue
        if cmd.lower() in {"exit", "quit"}:
            print("Goodbye.")
            return
        if cmd.lower() == "help":
            print(
                "Commands:\n"
                "- load csv <path>\n"
                "- load table <name>\n"
                "- discover\n"
                "- context\n"
                "- run <request>\n"
                "- run target=<semantic|warehouse|notebook|python> <request>\n"
                "- exit"
            )
            continue

        if cmd.lower().startswith("load csv "):
            path = cmd[9:].strip()
            print(json.dumps(assistant.ingestion.load_data(csv_path=path), indent=2))
            continue

        if cmd.lower().startswith("load table "):
            table = cmd[11:].strip()
            print(json.dumps(assistant.ingestion.load_data(table_name=table), indent=2))
            continue

        if cmd.lower() == "discover":
            print(json.dumps(assistant.discovery.discover_model(), indent=2))
            continue

        if cmd.lower() == "context":
            print(assistant.build_context())
            continue

        if cmd.lower().startswith("run "):
            payload = cmd[4:].strip()
            target = None
            if payload.startswith("target="):
                pieces = payload.split(maxsplit=1)
                t = pieces[0].split("=", maxsplit=1)[1]
                target = t
                payload = pieces[1] if len(pieces) > 1 else ""
            result = assistant.run_once(payload, target=target)
            print(json.dumps(result, indent=2))
            continue

        print("Unknown command. Type 'help'.")
