"""
Enhanced Formula Corrector - Intelligently maps user intent to actual schema columns.
Uses semantic analysis and column discovery to correctly identify tables and columns.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger(__name__)


class SemanticColumnMatcher:
    """Intelligently matches user intent to actual schema columns."""
    
    AMOUNT_KEYWORDS = ["amount", "sales", "revenue", "price", "total", "value", "sum", "qty"]
    COST_KEYWORDS = ["cost", "expense", "unit cost"]
    ID_KEYWORDS = ["key", "id", "identifier"]
    DATE_KEYWORDS = ["date", "month", "year", "time", "period"]
    COUNT_KEYWORDS = ["count", "number", "distinct", "unique", "orders", "orderid", "invoiceid", "transactionid", "order_id"]
    
    def __init__(self, metadata: Dict[str, Any]):
        self.metadata = metadata
        self.tables = metadata.get("tables", {})
        self.relationships = metadata.get("relationships", [])
        self._build_index()
    
    def _build_index(self):
        """Index all columns by semantic type."""
        self.index = {"amount": [], "cost": [], "id": [], "date": [], "count": [], "other": []}
        
        for table_name, table_info in self.tables.items():
            columns = table_info.get("columns", {})
            for col_name in columns.keys():
                # Clean Unicode artifacts (zero-width spaces, BOM markers, etc.)
                col_clean = col_name.replace('\ufeff', '').replace('\u200b', '').strip()
                col_lower = col_clean.lower()
                
                # Check count/order columns FIRST (before ID) since they're more specific
                if any(kw in col_lower for kw in self.COUNT_KEYWORDS):
                    self.index["count"].append((table_name, col_clean))
                elif any(kw in col_lower for kw in self.AMOUNT_KEYWORDS):
                    self.index["amount"].append((table_name, col_clean))
                elif any(kw in col_lower for kw in self.COST_KEYWORDS):
                    self.index["cost"].append((table_name, col_clean))
                elif any(kw in col_lower for kw in self.ID_KEYWORDS):
                    self.index["id"].append((table_name, col_clean))
                elif any(kw in col_lower for kw in self.DATE_KEYWORDS):
                    self.index["date"].append((table_name, col_clean))
                else:
                    self.index["other"].append((table_name, col_clean))
    
    def find_column(self, semantic_type: str, prefer_table: str = None) -> Optional[Tuple[str, str]]:
        """Find column by semantic type. Returns (table, column)."""
        candidates = self.index.get(semantic_type, [])
        if not candidates:
            return None
        
        if prefer_table:
            for table_name, col_name in candidates:
                if table_name == prefer_table:
                    return (table_name, col_name)
        
        return candidates[0] if candidates else None
    
    def find_fact_table(self) -> Optional[str]:
        """Find main fact table (most relationships)."""
        rel_count = {}
        for rel in self.relationships:
            from_table = rel.get("from_table")
            to_table = rel.get("to_table")
            rel_count[from_table] = rel_count.get(from_table, 0) + 1
            rel_count[to_table] = rel_count.get(to_table, 0) + 1
        
        if rel_count:
            return max(rel_count, key=rel_count.get)
        
        # Fallback: table with most amount columns
        best = max([(t, len([c for tb, c in self.index["amount"] if tb == t])) for t in self.tables.keys()], 
                   key=lambda x: x[1], default=(None, 0))
        return best[0] if best[0] else next(iter(self.tables.keys())) if self.tables else None


class FormulaCorrector:
    """Intelligently corrects and generates formulas."""
    
    def __init__(self, metadata: Dict[str, Any]):
        self.metadata = metadata
        self.tables = metadata.get("tables", {})
        self.relationships = metadata.get("relationships", [])
        self.matcher = SemanticColumnMatcher(metadata)
    
    def generate_dax_formula(self, description: str, item_type: str = "measure", table_name: str = None) -> Tuple[str, List[str]]:
        """Generate DAX formula from intent description."""
        warnings = []
        
        fact_table = table_name or self.matcher.find_fact_table()
        if not fact_table:
            return "ERROR: No tables found", ["No metadata available"]
        
        intent = self._get_intent(description)
        
        if item_type == "flag":
            formula = self._make_flag(description, fact_table)
        elif "average" in intent:
            formula = self._make_average(fact_table)
        elif "profit" in intent:
            formula = self._make_profit(fact_table)
        elif "ytd" in intent:
            formula = self._make_ytd(fact_table)
        else:
            formula = self._make_sum(fact_table)
        
        return formula, warnings
    
    def correct_dax_formula(self, code: str, description: str, user_intent: str = "", item_type: str = "measure") -> Tuple[str, List[str]]:
        """Correct user-provided formula."""
        warnings = []
        corrected = code
        
        # Check for mistakes
        if "SUM" in code.upper() and any(x in code.upper() for x in ["KEY", "ID"]):
            warnings.append("⚠️ WARNING: SUM on ID column detected")
            if item_type == "flag":
                corrected, msg = self._fix_flag(code, description)
            else:
                corrected, msg = self._auto_fix(code, description, item_type)
        
        # Validate
        val_warnings = self._validate(corrected)
        warnings.extend(val_warnings)
        
        return corrected, warnings
    
    def _get_intent(self, description: str) -> str:
        """Identify intent from description."""
        d = description.lower()
        if "average" in d:
            return "average"
        elif "profit" in d:
            return "profit"
        elif "ytd" in d or "year" in d:
            return "ytd"
        return "sum"
    
    def _make_flag(self, description: str, fact_table: str) -> str:
        """Generate IF flag formula."""
        match = re.search(r'[\$]?\s*([\d.]+)', description)
        threshold = match.group(1) if match else "100"
        
        d = description.lower()
        if "cost" in d:
            col = self.matcher.find_column("cost", fact_table)
            metric = f"SUM({col[0]}[{col[1]}])" if col else f"SUM({fact_table}[Cost])"
        elif "count" in d or "order" in d:
            col = self.matcher.find_column("count", fact_table)
            metric = f"DISTINCTCOUNT({col[0]}[{col[1]}])" if col else f"DISTINCTCOUNT({fact_table}[OrderID])"
        else:
            col = self.matcher.find_column("amount", fact_table)
            metric = f"SUM({col[0]}[{col[1]}])" if col else f"SUM({fact_table}[Amount])"
        
        return f'IF({metric} > {threshold}, "Yes", "No")'
    
    def _make_average(self, fact_table: str) -> str:
        """Generate average formula."""
        amt = self.matcher.find_column("amount", fact_table)
        cnt = self.matcher.find_column("count", fact_table)
        
        if not (amt and cnt):
            return f"ERROR: Missing columns"
        
        return f"DIVIDE(SUM({amt[0]}[{amt[1]}]), DISTINCTCOUNT({cnt[0]}[{cnt[1]}]))"
    
    def _make_profit(self, fact_table: str) -> str:
        """Generate profit formula."""
        amt = self.matcher.find_column("amount", fact_table)
        cst = self.matcher.find_column("cost", fact_table)
        
        if not (amt and cst):
            return f"ERROR: Missing columns"
        
        return f"DIVIDE(SUM({amt[0]}[{amt[1]}]) - SUM({cst[0]}[{cst[1]}]), SUM({amt[0]}[{amt[1]}]))"
    
    def _make_ytd(self, fact_table: str) -> str:
        """Generate year-to-date formula."""
        amt = self.matcher.find_column("amount", fact_table)
        if not amt:
            return f"ERROR: Missing amount column"
        
        date_col = self.matcher.find_column("date")
        date_table = date_col[0] if date_col else "Dates"
        date_name = date_col[1] if date_col else "Date"
        
        return f"CALCULATE(SUM({amt[0]}[{amt[1]}]), DATESYTD({date_table}[{date_name}]))"
    
    def _make_sum(self, fact_table: str) -> str:
        """Generate sum formula."""
        amt = self.matcher.find_column("amount", fact_table)
        if not amt:
            return f"ERROR: Missing amount column"
        
        return f"SUM({amt[0]}[{amt[1]}])"
    
    def _fix_flag(self, code: str, description: str) -> Tuple[str, Optional[str]]:
        """Fix flag formula."""
        match = re.search(r'[\$]?\s*([\d.]+)', description)
        threshold = match.group(1) if match else "100"
        
        fact_table = self.matcher.find_fact_table()
        d = description.lower()
        
        # Determine metric type from description
        if "count" in d or "number of" in d or "orders" in d:
            # Count-based metric - use DISTINCTCOUNT
            col = self.matcher.find_column("count", fact_table)
            if col:
                metric = f"DISTINCTCOUNT({col[0]}[{col[1]}])"
            else:
                metric = f"DISTINCTCOUNT({fact_table}[OrderID])"
        elif "cost" in d:
            col = self.matcher.find_column("cost", fact_table)
            metric = f"SUM({col[0]}[{col[1]}])" if col else f"SUM({fact_table}[Cost])"
        else:
            col = self.matcher.find_column("amount", fact_table)
            metric = f"SUM({col[0]}[{col[1]}])" if col else f"SUM({fact_table}[Amount])"
        
        corrected = f'IF({metric} > {threshold}, "Yes", "No")'
        
        return corrected, f"Fixed: Using {metric.split('[')[1].split(']')[0] if '[' in metric else 'column'} with threshold >{threshold}"
    
    def _auto_fix(self, code: str, description: str, item_type: str) -> Tuple[str, Optional[str]]:
        """Auto-correct formula."""
        fact_table = self.matcher.find_fact_table()
        
        if item_type == "flag":
            corrected = self._make_flag(description, fact_table)
        elif "average" in description.lower():
            corrected = self._make_average(fact_table)
        elif "profit" in description.lower():
            corrected = self._make_profit(fact_table)
        else:
            corrected = self._make_sum(fact_table)
        
        if corrected.startswith("ERROR"):
            return code, None
        
        return corrected, "Auto-corrected based on schema"
    
    def _validate(self, code: str) -> List[str]:
        """Validate formula."""
        warnings = []
        
        if code.count("(") != code.count(")"):
            warnings.append("❌ Unbalanced parentheses")
        
        if code.count("[") != code.count("]"):
            warnings.append("❌ Unbalanced brackets")
        
        id_pat = r"SUM\s*\(\s*\w+\s*\[\s*\w*(?:Key|ID|key|id)\w*\s*\]\s*\)"
        if re.search(id_pat, code):
            warnings.append("⚠️ SUM on ID column - use DISTINCTCOUNT")
        
        return warnings
    
    def suggest_formula(self, intent: str, table_name: str = None) -> Optional[str]:
        """Suggest formula by intent."""
        fact_table = table_name or self.matcher.find_fact_table()
        if not fact_table:
            return None
        
        d = intent.lower()
        if "average" in d:
            return self._make_average(fact_table)
        elif "profit" in d:
            return self._make_profit(fact_table)
        elif "ytd" in d:
            return self._make_ytd(fact_table)
        else:
            return self._make_sum(fact_table)

    def _find_amount_column(self, table_name: str) -> Optional[str]:
        """Find amount column (for backward compatibility)."""
        col = self.matcher.find_column("amount", table_name)
        return col[1] if col else None
    
    def _find_cost_column(self, table_name: str) -> Optional[str]:
        """Find cost column (for backward compatibility)."""
        col = self.matcher.find_column("cost", table_name)
        return col[1] if col else None
    
    def _find_order_column(self, table_name: str) -> Optional[str]:
        """Find order column (for backward compatibility)."""
        col = self.matcher.find_column("count", table_name)
        return col[1] if col else None
    
    def _check_common_mistakes(self, code: str, language: str) -> List[str]:
        """Check for mistakes (backward compatibility)."""
        return self._validate(code)
    
    def _generate_flag_formula(self, description: str) -> str:
        """Generate flag (backward compatibility)."""
        fact_table = self.matcher.find_fact_table()
        return self._make_flag(description, fact_table)
    
    def _generate_average_order_value_formula(self, table_name: str) -> str:
        """Generate average (backward compatibility)."""
        return self._make_average(table_name)
    
    def _generate_total_sales_formula(self, table_name: str) -> str:
        """Generate sum (backward compatibility)."""
        return self._make_sum(table_name)
    
    def _generate_profit_margin_formula(self, table_name: str) -> str:
        """Generate profit (backward compatibility)."""
        return self._make_profit(table_name)
    
    def _generate_ytd_formula(self, table_name: str) -> str:
        """Generate YTD (backward compatibility)."""
        return self._make_ytd(table_name)
    
    def _generate_distinct_count_formula(self, table_name: str) -> str:
        """Generate distinct count (backward compatibility)."""
        col = self.matcher.find_column("count", table_name)
        if col:
            return f"DISTINCTCOUNT({col[0]}[{col[1]}])"
        return f"DISTINCTCOUNT({table_name}[OrderID])"
    
    def _identify_intent(self, description: str, user_intent: str = "") -> str:
        """Identify intent (backward compatibility)."""
        return self._get_intent(description + " " + user_intent)
    
    def _fix_average_order_value(self, code: str) -> Tuple[str, Optional[str]]:
        """Fix AOV (backward compatibility)."""
        fact_table = self.matcher.find_fact_table()
        return self._auto_fix(code, "average order value", "measure")
    
    def _fix_total_sales(self, code: str) -> Tuple[str, Optional[str]]:
        """Fix total sales (backward compatibility)."""
        fact_table = self.matcher.find_fact_table()
        return self._auto_fix(code, "total sales", "measure")
    
    def _fix_profit_margin(self, code: str) -> Tuple[str, Optional[str]]:
        """Fix profit (backward compatibility)."""
        fact_table = self.matcher.find_fact_table()
        return self._auto_fix(code, "profit margin", "measure")
