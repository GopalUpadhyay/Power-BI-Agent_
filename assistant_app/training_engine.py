import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple


class FabricModelTrainer:
    """Learns model usage patterns from metadata and expression history."""

    DAX_REF = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\[([A-Za-z_][A-Za-z0-9_]*)\]")
    FN_REF = re.compile(r"\b([A-Z][A-Z0-9_]*)\s*\(")

    @classmethod
    def train(
        cls,
        metadata: Dict[str, Any],
        expressions: List[str],
    ) -> Dict[str, Any]:
        tables = metadata.get("tables", {}) if isinstance(metadata.get("tables", {}), dict) else {}
        relationships = metadata.get("relationships", []) if isinstance(metadata.get("relationships", []), list) else []

        col_usage: Counter[str] = Counter()
        table_usage: Counter[str] = Counter()
        fn_usage: Counter[str] = Counter()

        for expr in expressions:
            if not expr:
                continue

            refs = cls.DAX_REF.findall(expr)
            for table_name, col_name in refs:
                key = f"{table_name}.{col_name}"
                col_usage[key] += 1
                table_usage[table_name] += 1

            for fn in re.findall(r"\b([A-Z][A-Z0-9_]*)\s*\(", expr.upper()):
                fn_usage[fn] += 1

        dtype_map: Dict[str, str] = {}
        numeric_cols: List[Tuple[str, str]] = []
        date_cols: List[Tuple[str, str]] = []
        text_cols: List[Tuple[str, str]] = []

        for table_name, table_info in tables.items():
            cols = table_info.get("columns", {}) if isinstance(table_info, dict) else {}
            if not isinstance(cols, dict):
                continue
            for col_name, col_type in cols.items():
                col_type_s = str(col_type).lower()
                dtype_map[f"{table_name}.{col_name}"] = col_type_s
                if cls._is_numeric(col_type_s):
                    numeric_cols.append((table_name, col_name))
                elif cls._is_date(col_type_s, col_name):
                    date_cols.append((table_name, col_name))
                else:
                    text_cols.append((table_name, col_name))

        relationship_degree: Counter[str] = Counter()
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            ft = rel.get("from_table")
            tt = rel.get("to_table")
            if ft:
                relationship_degree[str(ft)] += 1
            if tt:
                relationship_degree[str(tt)] += 1

        table_scores: Dict[str, float] = defaultdict(float)
        for table_name in tables.keys():
            table_scores[table_name] += table_usage.get(table_name, 0) * 3.0
            table_scores[table_name] += relationship_degree.get(table_name, 0) * 1.5

            cols = tables.get(table_name, {}).get("columns", {})
            if isinstance(cols, dict):
                for col_name, col_type in cols.items():
                    if cls._is_numeric(str(col_type).lower()):
                        table_scores[table_name] += 0.3
                    if cls._is_date(str(col_type).lower(), col_name):
                        table_scores[table_name] += 0.5

        preferred_table = None
        if table_scores:
            preferred_table = max(table_scores.items(), key=lambda x: x[1])[0]

        preferred_value_column = cls._pick_preferred_value_column(
            preferred_table=preferred_table,
            numeric_cols=numeric_cols,
            col_usage=col_usage,
        )
        preferred_date_column = cls._pick_preferred_date_column(
            preferred_table=preferred_table,
            date_cols=date_cols,
            col_usage=col_usage,
        )

        top_columns = [
            {"column": key, "count": count}
            for key, count in col_usage.most_common(20)
        ]
        top_functions = [
            {"function": fn, "count": count}
            for fn, count in fn_usage.most_common(20)
        ]

        profile = {
            "trained_at": datetime.now().isoformat(),
            "table_scores": dict(sorted(table_scores.items(), key=lambda x: x[1], reverse=True)),
            "top_columns": top_columns,
            "top_functions": top_functions,
            "preferred_table": preferred_table,
            "preferred_value_column": preferred_value_column,
            "preferred_date_column": preferred_date_column,
            "numeric_column_count": len(numeric_cols),
            "date_column_count": len(date_cols),
            "text_column_count": len(text_cols),
            "observed_expression_count": len([e for e in expressions if e and e.strip()]),
            "feature_flags": {
                "uses_time_intelligence": any(fn in {"DATEADD", "SAMEPERIODLASTYEAR", "DATESYTD"} for fn in fn_usage),
                "uses_calculate": "CALCULATE" in fn_usage,
                "uses_divide": "DIVIDE" in fn_usage,
            },
        }
        return profile

    @staticmethod
    def _is_numeric(dtype: str) -> bool:
        return any(k in dtype for k in ["int", "bigint", "float", "double", "decimal", "numeric", "real"])

    @staticmethod
    def _is_date(dtype: str, col_name: str) -> bool:
        low_col = col_name.lower()
        return any(k in dtype for k in ["date", "timestamp", "datetime"]) or any(
            k in low_col for k in ["date", "month", "year", "quarter", "day"]
        )

    @classmethod
    def _pick_preferred_value_column(
        cls,
        preferred_table: str | None,
        numeric_cols: List[Tuple[str, str]],
        col_usage: Counter[str],
    ) -> str | None:
        if not numeric_cols:
            return None

        ranked: List[Tuple[str, float]] = []
        for table_name, col_name in numeric_cols:
            score = float(col_usage.get(f"{table_name}.{col_name}", 0))
            low = col_name.lower()
            if any(k in low for k in ["sales", "amount", "revenue", "total", "price", "cost", "value"]):
                score += 2.0
            if preferred_table and table_name == preferred_table:
                score += 1.5
            ranked.append((f"{table_name}.{col_name}", score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[0][0]

    @classmethod
    def _pick_preferred_date_column(
        cls,
        preferred_table: str | None,
        date_cols: List[Tuple[str, str]],
        col_usage: Counter[str],
    ) -> str | None:
        if not date_cols:
            return None

        ranked: List[Tuple[str, float]] = []
        for table_name, col_name in date_cols:
            score = float(col_usage.get(f"{table_name}.{col_name}", 0))
            low = col_name.lower()
            if "order" in low or "date" in low:
                score += 1.0
            if preferred_table and table_name == preferred_table:
                score += 0.8
            ranked.append((f"{table_name}.{col_name}", score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[0][0]
