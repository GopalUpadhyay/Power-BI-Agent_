import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

try:
    from groq import Groq
except Exception:  # pragma: no cover
    Groq = None

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()


def configure_openai_client(api_key: Optional[str] = None):
    """Create Groq client from argument or GROQ_API_KEY env var.

    Kept function name for backward compatibility with existing imports.
    """
    resolved_key = api_key or os.getenv("GROQ_API_KEY")
    if not resolved_key:
        logger.warning("GROQ_API_KEY not found. Running in fallback mode.")
        return None

    if Groq is None:
        logger.warning("Groq package is unavailable. Running in fallback mode.")
        return None

    try:
        # Keep retries low so quota/auth failures fail fast and fallback is immediate.
        client = Groq(api_key=resolved_key, timeout=20.0)
        logger.info("Groq client configured")
        return client
    except Exception as exc:  # pragma: no cover
        logger.warning("Groq client configuration failed: %s", exc)
        return None


def _groq_model_candidates() -> List[str]:
    primary = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    fallback_env = os.getenv("GROQ_FALLBACK_MODELS", "llama-3.1-8b-instant").strip()
    fallbacks = [m.strip() for m in fallback_env.split(",") if m.strip()]

    models: List[str] = []
    for model in [primary, *fallbacks]:
        if model and model not in models:
            models.append(model)
    return models


class SparkDataLoader:
    """Load semantic-model table metadata from Spark when available."""

    def __init__(self):
        self.spark = None
        self.tables_cache: Dict[str, Dict[str, str]] = {}
        self._init_spark()

    def _init_spark(self) -> None:
        try:
            self.spark = spark  # type: ignore[name-defined]
            logger.info("Spark session attached from notebook runtime")
            return
        except NameError:
            pass

        # Local Spark init is optional; most CLI use-cases work with sample metadata.
        if os.getenv("ENABLE_LOCAL_SPARK", "0") != "1":
            logger.info(
                "Local Spark init skipped (set ENABLE_LOCAL_SPARK=1 to enable). "
                "Using sample schema metadata."
            )
            return

        try:
            from pyspark.sql import SparkSession

            self.spark = SparkSession.builder.appName("PowerBI_AI_Assistant").getOrCreate()
            logger.info("Local Spark session initialized")
        except Exception:
            logger.warning("Spark unavailable; using sample schema metadata")

    def get_available_tables(self) -> List[str]:
        if not self.spark:
            return [
                "Sales",
                "Product",
                "Region",
                "Salesperson",
                "SalespersonRegion",
                "Targets",
            ]

        try:
            return [table.name for table in self.spark.catalog.listTables()]
        except Exception as exc:
            logger.warning("Unable to list Spark tables (%s). Using sample tables.", exc)
            return [
                "Sales",
                "Product",
                "Region",
                "Salesperson",
                "SalespersonRegion",
                "Targets",
            ]

    def get_table_schema(self, table_name: str) -> Dict[str, str]:
        if not self.spark:
            return self._sample_schema().get(table_name, {})

        try:
            df = self.spark.table(table_name)
            schema = {field.name: str(field.dataType) for field in df.schema.fields}
            self.tables_cache[table_name] = schema
            return schema
        except Exception as exc:
            logger.warning("Unable to read schema for %s (%s). Using fallback.", table_name, exc)
            return self._sample_schema().get(table_name, {})

    @staticmethod
    def _sample_schema() -> Dict[str, Dict[str, str]]:
        return {
            "Sales": {
                "SalesKey": "bigint",
                "ProductKey": "bigint",
                "EmployeeKey": "bigint",
                "RegionKey": "bigint",
                "OrderDate": "date",
                "Sales": "decimal(18,2)",
                "Quantity": "int",
                "OrderID": "string",
            },
            "Product": {
                "ProductKey": "bigint",
                "ProductName": "string",
                "Category": "string",
                "SubCategory": "string",
                "Price": "decimal(18,2)",
            },
            "Region": {
                "RegionKey": "bigint",
                "RegionName": "string",
                "Country": "string",
            },
            "Salesperson": {
                "EmployeeKey": "bigint",
                "EmployeeID": "string",
                "EmployeeName": "string",
                "Title": "string",
            },
            "SalespersonRegion": {
                "EmployeeKey": "bigint",
                "RegionKey": "bigint",
            },
            "Targets": {
                "EmployeeID": "string",
                "TargetAmount": "decimal(18,2)",
                "Year": "int",
            },
        }


class SemanticModelMetadata:
    """Semantic model metadata holder and schema helper."""

    def __init__(self, loader: Optional[SparkDataLoader] = None, metadata_override: Optional[Dict[str, Any]] = None):
        self.loader = loader
        self.metadata: Dict[str, Any] = {
            "tables": {},
            "relationships": [],
            "measures": {},
            "calculated_columns": {},
            "calculated_tables": {},
        }
        if metadata_override:
            self.metadata = self._normalize_metadata(metadata_override)
        else:
            self._build_metadata()

    def _normalize_metadata(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {
            "tables": {},
            "relationships": raw.get("relationships", []) if isinstance(raw.get("relationships", []), list) else [],
            "measures": raw.get("measures", {}) if isinstance(raw.get("measures", {}), dict) else {},
            "calculated_columns": raw.get("calculated_columns", {}) if isinstance(raw.get("calculated_columns", {}), dict) else {},
            "calculated_tables": raw.get("calculated_tables", {}) if isinstance(raw.get("calculated_tables", {}), dict) else {},
        }

        raw_tables = raw.get("tables", {}) if isinstance(raw.get("tables", {}), dict) else {}
        for table_name, table_info in raw_tables.items():
            if not isinstance(table_info, dict):
                continue
            columns = table_info.get("columns", {})
            if isinstance(columns, list):
                columns = {str(col): "string" for col in columns}
            if not isinstance(columns, dict):
                columns = {}

            normalized["tables"][str(table_name)] = {
                "columns": {str(col): str(col_type) for col, col_type in columns.items()},
                "column_count": len(columns),
            }

        # FIXED: Do NOT add sample tables - if model is empty, stay empty
        # This prevents hallucinated code generation for empty models
        # Users will see error message: "Model is empty, please upload CSV files"
        
        return normalized
    
    def is_empty(self) -> bool:
        """Check if model has no tables. Used for validation."""
        return len(self.metadata.get("tables", {})) == 0
    
    def validate_ready_for_generation(self) -> tuple[bool, str]:
        """Validate model is ready for code generation. Returns (is_valid, message)."""
        if self.is_empty():
            return False, (
                "❌ Your model is empty! Please upload CSV files first.\n\n"
                "Steps:\n"
                "1. Go to Model Hub tab\n"
                "2. Upload CSV files (orders.csv, customers.csv, etc)\n"
                "3. Click 'Store Uploaded Files'\n"
                "4. Return to Generate tab\n"
                "5. Generate code from your actual model data"
            )
        if len(self.metadata.get("tables", {})) < 1:
            return False, "Model has no tables. Cannot generate code."
        return True, "Model ready"

    def _build_metadata(self) -> None:
        if not self.loader:
            return
        for table_name in self.loader.get_available_tables():
            schema = self.loader.get_table_schema(table_name)
            self.metadata["tables"][table_name] = {
                "columns": schema,
                "column_count": len(schema),
            }

        self.metadata["relationships"] = [
            {
                "name": "Sales_Product",
                "from_table": "Sales",
                "from_column": "ProductKey",
                "to_table": "Product",
                "to_column": "ProductKey",
            },
            {
                "name": "Sales_Salesperson",
                "from_table": "Sales",
                "from_column": "EmployeeKey",
                "to_table": "Salesperson",
                "to_column": "EmployeeKey",
            },
            {
                "name": "Sales_Region",
                "from_table": "Sales",
                "from_column": "RegionKey",
                "to_table": "Region",
                "to_column": "RegionKey",
            },
            {
                "name": "Targets_Salesperson",
                "from_table": "Targets",
                "from_column": "EmployeeID",
                "to_table": "Salesperson",
                "to_column": "EmployeeID",
            },
        ]

        self.metadata["measures"] = {
            "Total_Sales": {
                "expression": "SUM(Sales[Sales])",
                "description": "Total sum of all sales",
            },
            "Total_Quantity": {
                "expression": "SUM(Sales[Quantity])",
                "description": "Total quantity sold",
            },
            "Average_Price": {
                "expression": "AVERAGE(Product[Price])",
                "description": "Average product price",
            },
        }

    def check_table_exists(self, table_name: str) -> bool:
        return table_name in self.metadata["tables"]

    def check_column_exists(self, table_name: str, column_name: str) -> bool:
        if not self.check_table_exists(table_name):
            return False
        return column_name in self.metadata["tables"][table_name]["columns"]

    def measure_exists(self, name: str) -> bool:
        return name in self.metadata["measures"]

    def add_measure(self, name: str, expression: str, description: str = "") -> None:
        self.metadata["measures"][name] = {
            "expression": expression,
            "description": description,
            "created_at": datetime.now().isoformat(),
        }

    def summary(self) -> str:
        lines: List[str] = []
        lines.append("SEMANTIC MODEL SUMMARY")
        lines.append("=" * 40)
        lines.append(f"Tables: {len(self.metadata['tables'])}")
        for table_name, info in self.metadata["tables"].items():
            lines.append(f"- {table_name}: {info['column_count']} columns")
        lines.append("")
        lines.append(f"Relationships: {len(self.metadata['relationships'])}")
        for rel in self.metadata["relationships"]:
            lines.append(
                f"- {rel['from_table']}.{rel['from_column']} -> {rel['to_table']}.{rel['to_column']}"
            )
        lines.append("")
        lines.append(f"Measures: {len(self.metadata['measures'])}")
        for name, m in self.metadata["measures"].items():
            lines.append(f"- {name} = {m['expression']}")
        return "\n".join(lines)

    def as_json(self) -> str:
        return json.dumps(self.metadata, indent=2, default=str)


class AIContextBuilder:
    """Builds strict prompt context for generation."""

    def __init__(self, metadata: SemanticModelMetadata):
        self.metadata = metadata
        self.base_prompt = self._build_base_prompt()

    def _build_base_prompt(self) -> str:
        prompt = []
        prompt.append("You are an expert Power BI Semantic Model engineer.")
        prompt.append("Rules:")
        prompt.append("1. Use only available tables and columns.")
        prompt.append("2. Do not invent schema entities.")
        prompt.append("3. Use valid DAX syntax and best practices.")
        prompt.append("4. Use OrderDate for time intelligence when needed.")
        prompt.append("5. Use EmployeeKey or EmployeeID as defined by relationships.")
        prompt.append("6. Prefer aggregation functions where appropriate.")
        prompt.append("")
        prompt.append("SCHEMA")
        for table_name, info in self.metadata.metadata["tables"].items():
            prompt.append(f"Table {table_name}:")
            for col, col_type in info["columns"].items():
                prompt.append(f"- {col} ({col_type})")

        prompt.append("")
        prompt.append("RELATIONSHIPS")
        for rel in self.metadata.metadata["relationships"]:
            prompt.append(
                f"- {rel['from_table']}.{rel['from_column']} -> {rel['to_table']}.{rel['to_column']}"
            )

        prompt.append("")
        prompt.append("EXISTING MEASURES")
        for name, m in self.metadata.metadata["measures"].items():
            prompt.append(f"- {name} = {m['expression']}")

        return "\n".join(prompt)

    def generation_prompt(self, item_type: str, description: str, conditions: str = "") -> str:
        text = []
        text.append(self.base_prompt)
        text.append("")
        text.append("REQUEST")
        text.append(f"ItemType: {item_type}")
        text.append(f"Description: {description}")
        if conditions:
            text.append(f"Conditions: {conditions}")
        text.append("")
        text.append("Return exactly this format:")
        text.append("NAME: <name>")
        text.append("EXPRESSION: <dax_or_logic_expression>")
        text.append("EXPLANATION: <plain business explanation>")
        text.append("VALIDATION: <ok or issue>")
        return "\n".join(text)


class DAXGenerationEngine:
    """Generates model-safe DAX using Groq with fallback logic."""

    def __init__(self, client, context_builder: AIContextBuilder):
        self.client = client
        self.context_builder = context_builder
        self._disabled_client_reason: Optional[str] = None

    def generate(self, item_type: str, description: str, conditions: str = "") -> Dict[str, str]:
        if not self.client:
            return self._fallback(item_type=item_type, description=description, conditions=conditions)

        prompt = self.context_builder.generation_prompt(
            item_type=item_type,
            description=description,
            conditions=conditions,
        )

        try:
            response = None
            last_error: Optional[Exception] = None
            for model_name in _groq_model_candidates():
                try:
                    response = self.client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a Power BI developer. Produce strict formatted output.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                        max_tokens=700,
                    )
                    break
                except Exception as model_exc:
                    last_error = model_exc
                    lowered_model = str(model_exc).lower()
                    if any(k in lowered_model for k in ["model_decommissioned", "does not exist", "not supported"]):
                        continue
                    raise

            if response is None:
                if last_error is not None:
                    raise last_error
                raise RuntimeError("No Groq response produced.")

            text = response.choices[0].message.content or ""
            parsed = self._parse_response(text)
            if not parsed["expression"]:
                return self._fallback(item_type=item_type, description=description, conditions=conditions)
            return parsed
        except Exception as exc:
            message = str(exc)
            lowered = message.lower()
            # Disable client for the rest of the run on persistent API failures.
            if any(code in lowered for code in ["insufficient_quota", "invalid_api_key", "401", "429"]):
                self.client = None
                if not self._disabled_client_reason:
                    self._disabled_client_reason = "quota/auth error"
                    logger.warning(
                        "Groq disabled for this run due to quota/auth error. Falling back to rule-based generation."
                    )
            else:
                logger.warning("Groq generation failed (%s). Using fallback.", exc)
            return self._fallback(item_type=item_type, description=description, conditions=conditions)

    @staticmethod
    def _parse_response(text: str) -> Dict[str, str]:
        result = {
            "name": "",
            "expression": "",
            "explanation": "",
            "validation": "",
            "raw_response": text,
        }

        def extract(label: str) -> str:
            pattern = rf"{label}:\s*(.*)"
            match = re.search(pattern, text)
            return match.group(1).strip() if match else ""

        result["name"] = extract("NAME")

        expression_match = re.search(r"EXPRESSION:\s*(.*?)(?:\nEXPLANATION:|\Z)", text, flags=re.S)
        result["expression"] = expression_match.group(1).strip() if expression_match else ""

        explanation_match = re.search(r"EXPLANATION:\s*(.*?)(?:\nVALIDATION:|\Z)", text, flags=re.S)
        result["explanation"] = explanation_match.group(1).strip() if explanation_match else ""

        result["validation"] = extract("VALIDATION")
        return result

    def _fallback(self, item_type: str, description: str, conditions: str = "") -> Dict[str, str]:
        description_l = description.lower()
        clean_name = re.sub(r"[^A-Za-z0-9_ ]", "", description).strip().replace(" ", "_")
        if not clean_name:
            clean_name = f"Generated_{item_type.title()}"

        table_name, value_col, date_col, label_col = self._pick_trained_schema_targets(description_l)

        expression = ""
        explanation = "Generated using trained model profile and fallback rules (no API)."

        if item_type == "measure":
            if "growth" in description_l and "month" in description_l and date_col:
                expression = (
                    f"VAR CurrentValue = SUM({table_name}[{value_col}])\n"
                    f"VAR PrevValue = CALCULATE(SUM({table_name}[{value_col}]), DATEADD({table_name}[{date_col}], -1, MONTH))\n"
                    "RETURN DIVIDE(CurrentValue - PrevValue, PrevValue)"
                )
            elif "top" in description_l:
                expression = (
                    f"CALCULATE(SUM({table_name}[{value_col}]), "
                    f"TOPN(5, VALUES({table_name}[{label_col}]), SUM({table_name}[{value_col}]), DESC))"
                )
            else:
                expression = f"SUM({table_name}[{value_col}])"

        elif item_type == "flag":
            if "1000" in description_l or "1000" in conditions:
                expression = f'IF(SUM({table_name}[{value_col}]) > 1000, "Yes", "No")'
            else:
                expression = f'IF(SUM({table_name}[{value_col}]) > 0, "Yes", "No")'

        elif item_type == "column":
            expression = f'IF({table_name}[{value_col}] > 1000, "High", "Standard")'

        elif item_type == "table":
            expression = (
                f"TOPN(5, SUMMARIZE({table_name}, {table_name}[{label_col}], "
                f"\"Total_Value\", SUM({table_name}[{value_col}])), [Total_Value], DESC)"
            )

        else:
            expression = f"SUM({table_name}[{value_col}])"

        return {
            "name": clean_name[:80],
            "expression": expression,
            "explanation": explanation,
            "validation": "fallback_ok",
            "raw_response": "fallback",
        }

    def _pick_trained_schema_targets(self, description_l: str = "") -> Tuple[str, str, Optional[str], str]:
        metadata_obj = self.context_builder.metadata.metadata
        tables = metadata_obj.get("tables", {}) if isinstance(metadata_obj.get("tables", {}), dict) else {}
        profile = metadata_obj.get("training_profile", {}) if isinstance(metadata_obj.get("training_profile", {}), dict) else {}

        preferred_table = profile.get("preferred_table")
        preferred_value = profile.get("preferred_value_column")
        preferred_date = profile.get("preferred_date_column")

        table_name = None

        # If request hints a business entity (product/region/customer), prefer matching table.
        for tname in tables.keys():
            if tname.lower() in description_l:
                table_name = tname
                break

        if table_name is None and preferred_table and preferred_table in tables:
            table_name = preferred_table
        elif table_name is None and tables:
            table_name = next(iter(tables.keys()))
        else:
            return ("Sales", "Sales", "OrderDate", "Sales")

        cols = tables.get(table_name, {}).get("columns", {})
        if not isinstance(cols, dict) or not cols:
            return (table_name, "value", None, "value")

        value_col = self._pick_value_col(table_name, cols, preferred_value)
        date_col = self._pick_date_col(table_name, cols, preferred_date)
        label_col = self._pick_label_col(cols, fallback=value_col)
        return (table_name, value_col, date_col, label_col)

    @staticmethod
    def _pick_value_col(table_name: str, cols: Dict[str, Any], preferred_value: Optional[str]) -> str:
        if preferred_value and "." in preferred_value:
            p_table, p_col = preferred_value.split(".", 1)
            if p_table == table_name and p_col in cols:
                return p_col

        preferred_keywords = ["sales", "amount", "revenue", "total", "price", "value", "cost"]
        numeric_candidates: List[str] = []
        id_like = ["id", "key", "code", "identifier"]
        for col, dtype in cols.items():
            dtype_l = str(dtype).lower()
            if any(k in dtype_l for k in ["int", "float", "double", "decimal", "numeric", "bigint"]):
                low_col = col.lower()
                # Avoid using identifier columns as business value measures.
                if not any(k in low_col for k in id_like):
                    numeric_candidates.append(col)

        for col in numeric_candidates:
            low = col.lower()
            if any(k in low for k in preferred_keywords):
                return col

        if numeric_candidates:
            return numeric_candidates[0]

        # Last-resort numeric fallback, even if identifier-like.
        for col, dtype in cols.items():
            dtype_l = str(dtype).lower()
            if any(k in dtype_l for k in ["int", "float", "double", "decimal", "numeric", "bigint"]):
                return col
        return next(iter(cols.keys()))

    @staticmethod
    def _pick_date_col(table_name: str, cols: Dict[str, Any], preferred_date: Optional[str]) -> Optional[str]:
        if preferred_date and "." in preferred_date:
            p_table, p_col = preferred_date.split(".", 1)
            if p_table == table_name and p_col in cols:
                return p_col

        for col, dtype in cols.items():
            low_col = col.lower()
            dtype_l = str(dtype).lower()
            if any(k in dtype_l for k in ["date", "timestamp", "datetime"]) or any(
                k in low_col for k in ["date", "month", "year"]
            ):
                return col
        return None

    @staticmethod
    def _pick_label_col(cols: Dict[str, Any], fallback: str) -> str:
        id_like = ["id", "key", "code", "identifier"]
        for col, dtype in cols.items():
            low = col.lower()
            if any(k in low for k in ["name", "title", "category", "segment", "type", "product"]):
                return col
            if "string" in str(dtype).lower() and not any(k in low for k in id_like):
                return col

        for col in cols.keys():
            low = col.lower()
            if col != fallback and not any(k in low for k in id_like):
                return col
        return fallback


class ValidationEngine:
    """Validates generated expressions against schema and syntax checks."""

    def __init__(self, metadata: SemanticModelMetadata):
        self.metadata = metadata

    def validate_expression(self, expression: str) -> Tuple[bool, List[str]]:
        issues: List[str] = []

        if not expression.strip():
            issues.append("Expression is empty")

        if not self._balanced_pairs(expression):
            issues.append("Expression contains unbalanced brackets or parentheses")

        for bad in ["DELETE", "DROP", "INSERT", "UPDATE", "ALTER"]:
            if bad in expression.upper():
                issues.append(f"Forbidden keyword detected: {bad}")

        refs = re.findall(r"(\w+)\[(\w+)\]", expression)
        for table_name, col_name in refs:
            if not self.metadata.check_table_exists(table_name):
                issues.append(f"Table not found: {table_name}")
            elif not self.metadata.check_column_exists(table_name, col_name):
                issues.append(f"Column not found: {table_name}[{col_name}]")

        # Guardrail: avoid SUM/AVERAGE over identifier-like columns (EmployeeID, ProductKey, etc.)
        agg_refs = re.findall(r"(SUM|AVERAGE)\s*\(\s*(\w+)\[(\w+)\]\s*\)", expression, flags=re.I)
        for fn, table_name, col_name in agg_refs:
            low = col_name.lower()
            if any(k in low for k in ["id", "key", "code", "identifier"]):
                issues.append(f"{fn.upper()} on identifier-like column is likely wrong: {table_name}[{col_name}]")

        return len(issues) == 0, issues

    @staticmethod
    def _balanced_pairs(text: str) -> bool:
        pairs = {"(": ")", "[": "]", "{": "}"}
        stack: List[str] = []
        for ch in text:
            if ch in pairs:
                stack.append(ch)
            elif ch in pairs.values():
                if not stack:
                    return False
                open_br = stack.pop()
                if pairs[open_br] != ch:
                    return False
        return not stack


class MeasureRegistry:
    """Tracks created items and prevents duplicate logic."""

    def __init__(self, metadata: SemanticModelMetadata, storage_path: Optional[Path] = None):
        self.metadata = metadata
        self.items: Dict[str, Dict[str, Any]] = {}
        self.storage_path = storage_path or (Path(__file__).resolve().parents[1] / ".assistant_registry.json")
        self._load_existing()
        self._load_persisted()

    def _load_existing(self) -> None:
        for name, measure in self.metadata.metadata["measures"].items():
            self.items[name] = {
                "name": name,
                "item_type": "measure",
                "expression": measure["expression"],
                "description": measure.get("description", ""),
                "source": "existing",
                "created_at": None,
            }

    def _load_persisted(self) -> None:
        if not self.storage_path.exists():
            return

        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read registry storage %s (%s).", self.storage_path, exc)
            return

        generated_items = payload.get("generated_items", []) if isinstance(payload, dict) else []
        if not isinstance(generated_items, list):
            logger.warning("Registry storage format invalid; expected list in generated_items.")
            return

        for item in generated_items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name or name in self.items:
                continue

            item_type = str(item.get("item_type", "measure")).strip().lower()
            expression = str(item.get("expression", "")).strip()
            description = str(item.get("description", "")).strip()
            source = str(item.get("source", "generated")).strip() or "generated"
            created_at = item.get("created_at")

            self.items[name] = {
                "name": name,
                "item_type": item_type,
                "expression": expression,
                "description": description,
                "source": source,
                "created_at": created_at,
            }

            # Keep measure metadata consistent after restart.
            if item_type == "measure" and expression and not self.metadata.measure_exists(name):
                self.metadata.add_measure(name=name, expression=expression, description=description)

    def _save_persisted(self) -> None:
        generated_items: List[Dict[str, Any]] = []
        for item in self.items.values():
            if item.get("source") != "generated":
                continue
            generated_items.append(
                {
                    "name": item.get("name", ""),
                    "item_type": str(item.get("item_type", "measure")).lower(),
                    "expression": item.get("expression", ""),
                    "description": item.get("description", ""),
                    "source": "generated",
                    "created_at": item.get("created_at"),
                }
            )

        payload = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "generated_items": generated_items,
        }

        try:
            self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to persist registry storage %s (%s).", self.storage_path, exc)

    def exists(self, name: str) -> bool:
        return name in self.items

    def find_similar(self, description: str, threshold: float = 0.5) -> List[Tuple[str, float]]:
        target_words = set(description.lower().split())
        matches: List[Tuple[str, float]] = []
        if not target_words:
            return matches

        for name, item in self.items.items():
            corpus = f"{name} {item.get('description', '')}".lower()
            words = set(corpus.split())
            if not words:
                continue
            similarity = len(target_words & words) / len(target_words | words)
            if similarity >= threshold:
                matches.append((name, similarity))

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def register(self, name: str, item_type: str, expression: str, description: str = "") -> bool:
        item_type = item_type.lower().strip()
        if self.exists(name):
            return False

        self.items[name] = {
            "name": name,
            "item_type": item_type,
            "expression": expression,
            "description": description,
            "source": "generated",
            "created_at": datetime.now().isoformat(),
        }

        if item_type == "measure":
            self.metadata.add_measure(name=name, expression=expression, description=description)

        self._save_persisted()

        return True

    def get_items_by_type(self, item_type: str) -> List[Dict[str, Any]]:
        """Get all items of a specific type (e.g., 'flag', 'measure', 'table')."""
        normalized_type = item_type.lower().strip()
        return [item for item in self.items.values() if str(item.get("item_type", "")).lower() == normalized_type]

    def flags_summary(self) -> str:
        """Get detailed report of all flags."""
        flags = self.get_items_by_type('flag')
        if not flags:
            return "No flags created yet."
        
        lines = ["FLAGS REPORT", "=" * 50]
        lines.append(f"Total flags: {len(flags)}\n")
        
        for i, flag in enumerate(flags, 1):
            lines.append(f"[{i}] {flag['name']}")
            lines.append(f"    Type: {flag['item_type']}")
            lines.append(f"    Source: {flag['source']}")
            if flag['description']:
                lines.append(f"    Description: {flag['description']}")
            lines.append(f"    Expression: {flag['expression']}")
            if flag['created_at']:
                lines.append(f"    Created: {flag['created_at']}")
            lines.append("")
        
        return "\n".join(lines)

    def summary(self) -> str:
        lines = ["REGISTRY SUMMARY", "=" * 50, f"Total items: {len(self.items)}\n"]
        
        # Group by type
        types = {}
        for name, item in self.items.items():
            item_type = item['item_type']
            if item_type not in types:
                types[item_type] = []
            types[item_type].append(f"- {name} ({item['source']})")
        
        # Display grouped
        for item_type in sorted(types.keys()):
            lines.append(f"{item_type.upper()}S ({len(types[item_type])})")
            for entry in types[item_type]:
                lines.append(f"  {entry}")
            lines.append("")
        
        return "\n".join(lines)


class ExplanationModule:
    """Generates concise business explanations and suggestions."""

    def __init__(self, generator: DAXGenerationEngine):
        self.generator = generator

    def explain(self, expression: str) -> str:
        exp_u = expression.upper()
        points: List[str] = []
        if "SUM(" in exp_u:
            points.append("Sums numeric values for aggregated analysis.")
        if "CALCULATE(" in exp_u:
            points.append("Changes filter context to evaluate a specific scenario.")
        if "IF(" in exp_u:
            points.append("Applies conditional business logic.")
        if "DATEADD(" in exp_u:
            points.append("Uses time intelligence across date periods.")
        if "TOPN(" in exp_u:
            points.append("Ranks and returns top entities by a metric.")
        if not points:
            points.append("Implements custom semantic model logic.")
        return " ".join(points)

    def suggestions(self, expression: str) -> List[str]:
        notes: List[str] = []
        if "/" in expression and "DIVIDE(" not in expression.upper():
            notes.append("Use DIVIDE(x, y) instead of x / y to avoid division-by-zero errors.")
        if expression.count("FILTER(") > 2:
            notes.append("Consider reducing nested FILTER calls for better performance.")
        if len(expression) > 400:
            notes.append("Split complex logic into helper measures for maintainability.")
        if not notes:
            notes.append("Expression quality looks good for a presentation demo.")
        return notes


@dataclass
class PowerBIAssistantAgent:
    metadata: SemanticModelMetadata
    generator: DAXGenerationEngine
    validator: ValidationEngine
    registry: MeasureRegistry
    explainer: ExplanationModule

    def generate_item(
        self,
        description: str,
        item_type: str,
        conditions: str = "",
        auto_register: bool = False,
    ) -> Dict[str, Any]:
        # FIXED: Validate model is not empty before generating code
        is_valid, validation_msg = self.metadata.validate_ready_for_generation()
        if not is_valid:
            return {
                "name": f"Error_{item_type.title()}",
                "item_type": item_type,
                "description": description,
                "expression": "",
                "paste_ready_query": "",
                "explanation": validation_msg,
                "validation_ok": False,
                "validation_errors": [validation_msg],
                "is_duplicate": False,
                "similar_candidates": [],
                "tips": ["Upload CSV files to your model first"],
                "generated_at": datetime.now().isoformat(),
            }
        
        similar = self.registry.find_similar(description)
        draft = self.generator.generate(item_type=item_type, description=description, conditions=conditions)

        name = draft.get("name") or f"Generated_{item_type.title()}"
        expression = draft.get("expression", "")

        valid, validation_errors = self.validator.validate_expression(expression)

        duplicate = self.registry.exists(name)
        if auto_register and (not duplicate):
            self.registry.register(
                name=name,
                item_type=item_type,
                expression=expression,
                description=description,
            )

        explanation = draft.get("explanation") or self.explainer.explain(expression)
        tips = self.explainer.suggestions(expression)
        paste_ready_query = self._build_paste_ready_query(name=name, item_type=item_type, expression=expression)

        return {
            "name": name,
            "item_type": item_type,
            "description": description,
            "conditions": conditions,
            "expression": expression,
            "paste_ready_query": paste_ready_query,
            "explanation": explanation,
            "validation_ok": valid,
            "validation_errors": validation_errors,
            "is_duplicate": duplicate,
            "similar_candidates": similar,
            "tips": tips,
            "generated_at": datetime.now().isoformat(),
        }

    @staticmethod
    def _build_paste_ready_query(name: str, item_type: str, expression: str) -> str:
        normalized = (item_type or "measure").strip().lower()
        if normalized in {"measure", "flag", "column", "table"}:
            return f"{name} =\n{expression}"
        return expression

    def registry_summary(self) -> str:
        return self.registry.summary()

    def run_interactive_loop(self) -> None:
        print("\nPower BI Semantic Model AI Assistant")
        print("Type 'help' for commands or 'exit' to quit.\n")

        while True:
            try:
                command = input("assistant> ").strip()
                if not command:
                    continue

                if command.lower() in {"exit", "quit"}:
                    print("Goodbye.")
                    return

                if command.lower() == "help":
                    print(self._help_text())
                    continue

                if command.lower() in {"schema", "model"}:
                    print(self.metadata.summary())
                    continue

                if command.lower() in {"registry", "list"}:
                    print(self.registry_summary())
                    continue

                if command.lower().startswith("create"):
                    self._interactive_create(command)
                    continue

                print("Unknown command. Type 'help' for guidance.")
            except KeyboardInterrupt:
                print("\nInterrupted. Exiting.")
                return

    def _interactive_create(self, command: str) -> None:
        parts = command.split(maxsplit=2)
        item_type = "measure"
        description = ""

        if len(parts) == 1:
            item_type = input("Item type (measure/flag/column/table): ").strip().lower() or "measure"
            description = input("Description: ").strip()
        elif len(parts) == 2:
            item_type = parts[1].strip().lower()
            description = input("Description: ").strip()
        else:
            item_type = parts[1].strip().lower()
            description = parts[2].strip()

        if item_type not in {"measure", "flag", "column", "table"}:
            print("Unsupported type. Use measure, flag, column, or table.")
            return

        conditions = ""
        if item_type in {"flag", "column", "table"}:
            conditions = input("Conditions (optional): ").strip()

        result = self.generate_item(
            description=description,
            item_type=item_type,
            conditions=conditions,
            auto_register=False,
        )

        print("\nGenerated Result")
        print("-" * 50)
        print(f"✓ Name: {result['name']}")
        print(f"  Type: {result['item_type']}")

        if result["validation_errors"]:
            print("\n⚠ Validation issues:")
            for err in result["validation_errors"]:
                print(f"  - {err}")
        else:
            print("\n✓ Validation passed")

        if result["similar_candidates"]:
            print("\nSimilar existing items:")
            for name, score in result["similar_candidates"][:3]:
                print(f"  - {name} ({score:.0%} match)")

        print("\nSuggestions:")
        for tip in result["tips"]:
            print(f"  - {tip}")

        # Show expression in hidden section
        show_expr = input("\nView expression? (y/n): ").strip().lower()
        if show_expr == "y":
            print("\nExpression (DAX/Spark Query):")
            print("-" * 50)
            print(result["expression"])
            print("\nPaste-ready:")
            print(result.get("paste_ready_query", result["expression"]))
            print("Explanation:")
            print(result["explanation"])
            print("-" * 50)

        if result["is_duplicate"]:
            print("\nItem name already exists in registry. Not saved.")
            return

        save = input("\nSave to registry? (y/n): ").strip().lower()
        if save == "y":
            saved = self.registry.register(
                name=result["name"],
                item_type=result["item_type"],
                expression=result["expression"],
                description=result["description"],
            )
            print("✓ Saved." if saved else "✗ Could not save (duplicate).")
        else:
            print("Not saved.")

    @staticmethod
    def _help_text() -> str:
        return (
            "Commands:\n"
            "- create [measure|flag|column|table] [description]\n"
            "- schema          Show semantic model\n"
            "- registry        View items in registry\n"
            "- help            Show this help\n"
            "- exit            Exit\n"
            "\n"
            "Tip: Use 'exit' then run:\n"
            "  python run_app.py --show-expression <name>   View expression"
        )
