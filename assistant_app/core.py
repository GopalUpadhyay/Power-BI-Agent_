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
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()


def configure_openai_client(api_key: Optional[str] = None):
    """Create OpenAI client from argument or OPENAI_API_KEY env var."""
    resolved_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_key:
        logger.warning("OPENAI_API_KEY not found. Running in fallback mode.")
        return None

    if OpenAI is None:
        logger.warning("OpenAI package is unavailable. Running in fallback mode.")
        return None

    try:
        # Keep retries low so quota/auth failures fail fast and fallback is immediate.
        client = OpenAI(api_key=resolved_key, max_retries=0, timeout=20.0)
        logger.info("OpenAI client configured")
        return client
    except Exception as exc:  # pragma: no cover
        logger.warning("OpenAI client configuration failed: %s", exc)
        return None


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

    def __init__(self, loader: SparkDataLoader):
        self.loader = loader
        self.metadata: Dict[str, Any] = {
            "tables": {},
            "relationships": [],
            "measures": {},
            "calculated_columns": {},
            "calculated_tables": {},
        }
        self._build_metadata()

    def _build_metadata(self) -> None:
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
    """Generates model-safe DAX using OpenAI with fallback logic."""

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
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
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
                        "OpenAI disabled for this run due to quota/auth error. Falling back to rule-based generation."
                    )
            else:
                logger.warning("OpenAI generation failed (%s). Using fallback.", exc)
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

        expression = ""
        explanation = "Generated using fallback rules (no API)."

        if item_type == "measure":
            if "total" in description_l and "sale" in description_l:
                expression = "SUM(Sales[Sales])"
            elif "growth" in description_l and "month" in description_l:
                expression = (
                    "VAR CurrentMonthSales = SUM(Sales[Sales])\n"
                    "VAR PrevMonthSales = CALCULATE(SUM(Sales[Sales]), DATEADD(Sales[OrderDate], -1, MONTH))\n"
                    "RETURN DIVIDE(CurrentMonthSales - PrevMonthSales, PrevMonthSales)"
                )
            elif "top" in description_l and "product" in description_l:
                expression = (
                    "CALCULATE(SUM(Sales[Sales]), "
                    "TOPN(5, VALUES(Product[ProductName]), [Total_Sales], DESC))"
                )
            else:
                expression = "SUM(Sales[Sales])"

        elif item_type == "flag":
            if "1000" in description_l or "1000" in conditions:
                expression = 'IF(SUM(Sales[Sales]) > 1000, "Yes", "No")'
            else:
                expression = 'IF(SUM(Sales[Sales]) > 0, "Yes", "No")'

        elif item_type == "column":
            expression = 'IF(Sales[Sales] > 1000, "High", "Standard")'

        elif item_type == "table":
            expression = "TOPN(5, SUMMARIZE(Sales, Product[ProductName], \"Total_Sales\", SUM(Sales[Sales])), [Total_Sales], DESC)"

        else:
            expression = "SUM(Sales[Sales])"

        return {
            "name": clean_name[:80],
            "expression": expression,
            "explanation": explanation,
            "validation": "fallback_ok",
            "raw_response": "fallback",
        }


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

    def __init__(self, metadata: SemanticModelMetadata):
        self.metadata = metadata
        self.items: Dict[str, Dict[str, Any]] = {}
        self.storage_path = Path(__file__).resolve().parents[1] / ".assistant_registry.json"
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

        return {
            "name": name,
            "item_type": item_type,
            "description": description,
            "conditions": conditions,
            "expression": expression,
            "explanation": explanation,
            "validation_ok": valid,
            "validation_errors": validation_errors,
            "is_duplicate": duplicate,
            "similar_candidates": similar,
            "tips": tips,
            "generated_at": datetime.now().isoformat(),
        }

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
        print("-" * 30)
        print(f"Name: {result['name']}")
        print(f"Type: {result['item_type']}")
        print("Expression:")
        print(result["expression"])
        print("Explanation:")
        print(result["explanation"])

        if result["similar_candidates"]:
            print("Similar existing items:")
            for name, score in result["similar_candidates"][:3]:
                print(f"- {name} ({score:.0%} match)")

        if result["validation_errors"]:
            print("Validation issues:")
            for err in result["validation_errors"]:
                print(f"- {err}")

        print("Suggestions:")
        for tip in result["tips"]:
            print(f"- {tip}")

        if result["is_duplicate"]:
            print("Item name already exists in registry. Not saved.")
            return

        save = input("Save to registry? (y/n): ").strip().lower()
        if save == "y":
            saved = self.registry.register(
                name=result["name"],
                item_type=result["item_type"],
                expression=result["expression"],
                description=result["description"],
            )
            print("Saved." if saved else "Could not save (duplicate).")
        else:
            print("Not saved.")

    @staticmethod
    def _help_text() -> str:
        return (
            "Commands:\n"
            "- create [measure|flag|column|table] [description]\n"
            "- schema\n"
            "- registry\n"
            "- help\n"
            "- exit"
        )
