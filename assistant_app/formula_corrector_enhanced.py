"""
Enhanced Formula Corrector Engine - Intelligently maps user intent to actual schema columns.
Uses fuzzy matching and semantic analysis to correctly identify tables and columns.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Any
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class SemanticColumnMatcher:
    """Intelligently matches user intent to actual schema columns."""
    
    # Column semantic categories
    AMOUNT_KEYWORDS = ["amount", "sales", "revenue", "price", "total", "value", "sum", "qty", "quantity"]
    COST_KEYWORDS = ["cost", "expense", "price", "production cost", "unit cost"]
    ID_KEYWORDS = ["key", "id", "identifier", "code", "number"]
    DATE_KEYWORDS = ["date", "month", "year", "time", "period", "day"]
    COUNT_KEYWORDS = ["count", "number", "distinct", "unique", "orders", "invoices"]
    
    def __init__(self, metadata: Dict[str, Any]):
        self.metadata = metadata
        self.tables = metadata.get("tables", {})
        self.relationships = metadata.get("relationships", [])
        self._build_column_index()
    
    def _build_column_index(self):
        """Build an index of all columns by their semantic purpose."""
        self.column_index = {
            "amount": [],
            "cost": [],
            "id": [],
            "date": [],
            "count": [],
            "other": []
        }
        
        for table_name, table_info in self.tables.items():
            columns = table_info.get("columns", {})
            for col_name in columns.keys():
                col_lower = col_name.lower()
                
                if any(kw in col_lower for kw in self.AMOUNT_KEYWORDS):
                    self.column_index["amount"].append((table_name, col_name))
                elif any(kw in col_lower for kw in self.COST_KEYWORDS):
                    self.column_index["cost"].append((table_name, col_name))
                elif any(kw in col_lower for kw in self.ID_KEYWORDS):
                    self.column_index["id"].append((table_name, col_name))
                elif any(kw in col_lower for kw in self.DATE_KEYWORDS):
                    self.column_index["date"].append((table_name, col_name))
                elif any(kw in col_lower for kw in self.COUNT_KEYWORDS):
                    self.column_index["count"].append((table_name, col_name))
                else:
                    self.column_index["other"].append((table_name, col_name))
    
    def find_fuzzy_match(self, search_term: str, semantic_type: str = "amount") -> Optional[Tuple[str, str]]:
        """
        Find column using fuzzy matching.
        Returns: (table_name, column_name) or None
        """
        search_lower = search_term.lower()
        candidates = self.column_index.get(semantic_type, [])
        
        if not candidates:
            return None
        
        # Calculate similarity ratios
        best_match = None
        best_ratio = 0.3  # Minimum 30% similarity
        
        for table_name, col_name in candidates:
            col_lower = col_name.lower()
            ratio = SequenceMatcher(None, search_lower, col_lower).ratio()
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = (table_name, col_name)
        
        return best_match
    
    def find_column_by_semantic_type(self, semantic_type: str, prefer_table: str = None) -> Optional[Tuple[str, str]]:
        """
        Find column by semantic type (amount, cost, id, date, count).
        Returns: (table_name, column_name) or None
        """
        candidates = self.column_index.get(semantic_type, [])
        
        if not candidates:
            return None
        
        # If preferred table exists, use that
        if prefer_table:
            for table_name, col_name in candidates:
                if table_name == prefer_table:
                    return (table_name, col_name)
        
        # Return first candidate (usually best match)
        return candidates[0] if candidates else None
    
    def find_fact_table(self) -> Optional[str]:
        """Find the main fact table (usually the one with most relationships)."""
        rel_count = {}
        
        for rel in self.relationships:
            from_table = rel.get("from_table")
            to_table = rel.get("to_table")
            
            rel_count[from_table] = rel_count.get(from_table, 0) + 1
            rel_count[to_table] = rel_count.get(to_table, 0) + 1
        
        if rel_count:
            return max(rel_count, key=rel_count.get)
        
        # Fallback: return largest table
        largest_table = max(self.tables.items(), key=lambda x: x[1].get("column_count", 0))[0]
        return largest_table if self.tables else None
    
    def suggested_columns_for_intent(self, intent: str) -> Dict[str, Tuple[str, str]]:
        """Get all suggested columns for a specific intent."""
        result = {}
        
        intent_lower = intent.lower()
        
        # For average order value
        if "average" in intent_lower:
            amount = self.find_column_by_semantic_type("amount")
            order_id = self.find_column_by_semantic_type("count")  # order/count column
            if amount and order_id:
                result["amount_column"] = amount
                result["order_column"] = order_id
        
        # For profit calculations
        if "profit" in intent_lower:
            amount = self.find_column_by_semantic_type("amount")
            cost = self.find_column_by_semantic_type("cost")
            if amount and cost:
                result["amount_column"] = amount
                result["cost_column"] = cost
        
        # For cost related
        if "cost" in intent_lower:
            cost = self.find_column_by_semantic_type("cost")
            if cost:
                result["cost_column"] = cost
        
        # For sales/revenue
        if "sales" in intent_lower or "revenue" in intent_lower:
            amount = self.find_column_by_semantic_type("amount")
            if amount:
                result["amount_column"] = amount
        
        # Default
        if not result:
            result["amount_column"] = self.find_column_by_semantic_type("amount")
            result["order_column"] = self.find_column_by_semantic_type("count")
        
        return result


class EnhancedFormulaCorrector:
    """Enhanced formula corrector with intelligent column identification."""
    
    def __init__(self, metadata: Dict[str, Any]):
        self.metadata = metadata
        self.tables = metadata.get("tables", {})
        self.relationships = metadata.get("relationships", [])
        self.matcher = SemanticColumnMatcher(metadata)
    
    def generate_formula_with_intent(
        self,
        description: str,
        item_type: str = "measure",
        output_language: str = "DAX"
    ) -> Tuple[str, List[str]]:
        """
        Generate formula by understanding user intent and mapping to actual schema.
        """
        warnings = []
        
        # Find fact table
        fact_table = self.matcher.find_fact_table()
        if not fact_table:
            return f"ERROR: No tables found in schema", ["No tables in metadata"]
        
        # Identify intent
        intent = self._identify_intent(description)
        
        # Get suggested columns for this intent
        suggested = self.matcher.suggested_columns_for_intent(description)
        
        # Generate formula based on intent
        if item_type == "flag":
            formula = self._generate_flag_with_mapping(description, suggested, fact_table)
        elif intent == "average_order_value":
            amount_col = suggested.get("amount_column")
            order_col = suggested.get("order_column")
            if amount_col and order_col:
                formula = f"DIVIDE(SUM({amount_col[0]}[{amount_col[1]}]), DISTINCTCOUNT({order_col[0]}[{order_col[1]}]))"
            else:
                warnings.append("Could not identify amount and order columns")
                formula = f"ERROR: Missing columns for {intent}"
        elif intent == "profit_margin":
            amount_col = suggested.get("amount_column")
            cost_col = suggested.get("cost_column")
            if amount_col and cost_col:
                table1 = amount_col[0]
                col1 = amount_col[1]
                col2 = cost_col[1]
                formula = f"DIVIDE(SUM({table1}[{col1}]) - SUM({table1}[{col2}]), SUM({table1}[{col1}]))"
            else:
                warnings.append("Could not identify amount and cost columns")
                formula = f"ERROR: Missing columns for profit margin"
        else:  # Default: total/sum
            amount_col = suggested.get("amount_column")
            if amount_col:
                formula = f"SUM({amount_col[0]}[{amount_col[1]}])"
            else:
                warnings.append("Could not identify amount column")
                formula = f"ERROR: Missing amount column"
        
        return formula, warnings
    
    def _identify_intent(self, description: str) -> str:
        """Identify user intent from description."""
        desc_lower = description.lower()
        
        if "average" in desc_lower or "avg" in desc_lower:
            return "average_order_value"
        elif "profit" in desc_lower and "margin" in desc_lower:
            return "profit_margin"
        elif "margin" in desc_lower:
            return "profit_margin"
        elif "total" in desc_lower or "sum" in desc_lower:
            return "total_sales"
        elif "ytd" in desc_lower or "year to date" in desc_lower:
            return "year_to_date"
        else:
            return "total_sales"
    
    def _generate_flag_with_mapping(
        self,
        description: str,
        suggested: Dict[str, Tuple[str, str]],
        fact_table: str
    ) -> str:
        """Generate flag formula with intelligent column mapping."""
        
        # Extract threshold
        threshold_match = re.search(r'[\$]?\s*([\d.]+)', description)
        threshold = threshold_match.group(1) if threshold_match else "0"
        
        # Determine column type from description
        desc_lower = description.lower()
        
        if "cost" in desc_lower:
            col_tuple = suggested.get("cost_column")
        elif "count" in desc_lower or "order" in desc_lower:
            col_tuple = suggested.get("order_column")
        else:
            col_tuple = suggested.get("amount_column")
        
        if not col_tuple:
            col_tuple = suggested.get("amount_column") or (fact_table, "Amount")
        
        table_name, col_name = col_tuple
        
        # Determine metric
        if "count" in desc_lower or "order" in desc_lower:
            metric = f"DISTINCTCOUNT({table_name}[{col_name}])"
        else:
            metric = f"SUM({table_name}[{col_name}])"
        
        return f'IF({metric} > {threshold}, "Yes", "No")'
    
    def validate_and_correct_formula(
        self,
        formula: str,
        description: str,
        item_type: str = "measure"
    ) -> Tuple[str, List[str]]:
        """Validate and correct user-provided formula."""
        warnings = []
        corrected = formula
        
        # Check for common mistakes
        if "SUM" in formula.upper():
            # Check for SUM on ID columns
            id_pattern = r"SUM\s*\(\s*\w+\s*\[\s*\w*(?:Key|ID|Id|key|id)\w*\s*\]\s*\)"
            if re.search(id_pattern, formula):
                warnings.append("⚠️ CRITICAL: SUM() on ID/Key column detected. Should use DISTINCTCOUNT instead.")
                # Try to auto-correct
                if "average" in description.lower() or "avg" in description.lower():
                    suggested = self.matcher.suggested_columns_for_intent(description)
                    amount_col = suggested.get("amount_column")
                    order_col = suggested.get("order_column")
                    if amount_col and order_col:
                        corrected = f"DIVIDE(SUM({amount_col[0]}[{amount_col[1]}]), DISTINCTCOUNT({order_col[0]}[{order_col[1]}]))"
                        warnings.append(f"Auto-corrected to: {corrected}")
        
        # Check for unbalanced parentheses
        if formula.count("(") != formula.count(")"):
            warnings.append("❌ Unbalanced parentheses in formula")
        
        # Check for unqualified column names
        unqualified = re.findall(r"\[\s*\w+\s*\](?!\()", formula)  # [Column] not followed by (
        if unqualified and not any("[" in formula for _ in ["[table["]):
            warnings.append("⚠️ Column names should be qualified as Table[Column]")
        
        return corrected, warnings


def get_schema_mapping_report(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a detailed report of available columns and their semantic purposes.
    Useful for understanding what the system can work with.
    """
    matcher = SemanticColumnMatcher(metadata)
    
    return {
        "fact_table": matcher.find_fact_table(),
        "amount_columns": matcher.column_index.get("amount", []),
        "cost_columns": matcher.column_index.get("cost", []),
        "id_columns": matcher.column_index.get("id", []),
        "date_columns": matcher.column_index.get("date", []),
        "count_columns": matcher.column_index.get("count", []),
        "other_columns": matcher.column_index.get("other", []),
        "all_tables": list(metadata.get("tables", {}).keys()),
        "relationships": metadata.get("relationships", [])
    }
