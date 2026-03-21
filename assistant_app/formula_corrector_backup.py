"""
Formula Corrector Engine - Automatically fixes common LLM generation mistakes.
Handles DAX, SQL, and PySpark formula corrections based on semantic intent.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger(__name__)

# Knowledge base of correct formulas and patterns
FORMULA_PATTERNS = {
    "average_order_value": [
        "DIVIDE(SUM({amount_col}), DISTINCTCOUNT({order_col}))",
        "SUM({amount_col}) / DISTINCTCOUNT({order_col})",
    ],
    "total_sales": [
        "SUM({sales_col})",
    ],
    "unique_customers": [
        "DISTINCTCOUNT({customer_col})",
    ],
    "profit_margin": [
        "DIVIDE(SUM({sales_col}) - SUM({cost_col}), SUM({sales_col}))",
    ],
    "month_over_month_growth": [
        "DIVIDE([Current Month Sales] - [Previous Month Sales], [Previous Month Sales])",
    ],
}

# Common mistakes and corrections
COMMON_MISTAKES = {
    # Pattern: SUM on ID/Key columns
    r"SUM\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*(.*?(?:Key|ID|EmployeeKey|ProductKey|OrderID|CustomerID)[^\]]*)\s*\]\s*\)": {
        "issue": "Summing ID/Key columns (should use DISTINCTCOUNT or sum numeric values)",
        "replace_with": "DISTINCTCOUNT({table}[{column}])",
        "severity": "high"
    },
    
    # Pattern: Missing DISTINCTCOUNT in average calculations
    r"AVERAGE\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*([^\]]*Amount|SalesAmount|Price|Revenue)[^\]]*\]\s*\)": {
        "issue": "Using AVERAGE on fact table amounts (should use DIVIDE with DISTINCTCOUNT)",
        "severity": "medium",
        "hint": "Use: DIVIDE(SUM(Table[Amount]), DISTINCTCOUNT(Table[OrderID]))"
    },
    
    # Pattern: Creating measure with wrong name
    r"^([A-Za-z0-9_]+)\s*=\s*SUM\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*(?:Key|ID|EmployeeKey|ProductKey)[^\]]*\]\s*\)": {
        "issue": "Measure created but with SUM on ID column",
        "severity": "high"
    },
}


class FormulaCorrector:
    """Automatically corrects and validates formulas to match semantic intent."""
    
    def __init__(self, metadata: Dict[str, Any]):
        self.metadata = metadata
        self.tables = metadata.get("tables", {})
        self.relationships = metadata.get("relationships", [])
    
    def correct_dax_formula(self, code: str, description: str, user_intent: str = "", item_type: str = "measure") -> Tuple[str, List[str]]:
        """
        Correct DAX formulas based on semantic intent and common patterns.
        Returns: (corrected_code, warnings)
        """
        warnings = []
        corrected = code
        
        # Identify intent from description/user input
        intent = self._identify_intent(description, user_intent)
        
        # Apply corrections based on item type and intent
        if item_type == "flag":
            corrected, msg = self._fix_flag_formula(code, description)
            if msg:
                warnings.append(msg)
        
        elif intent == "average_order_value":
            corrected, msg = self._fix_average_order_value(code)
            if msg:
                warnings.append(msg)
        
        elif intent == "total_sales":
            corrected, msg = self._fix_total_sales(code)
            if msg:
                warnings.append(msg)
        
        elif intent == "profit_margin":
            corrected, msg = self._fix_profit_margin(code)
            if msg:
                warnings.append(msg)
        
        # Check for common mistakes
        mistake_warnings = self._check_common_mistakes(corrected, "DAX")
        warnings.extend(mistake_warnings)
        
        return corrected, warnings
    
    def _identify_intent(self, description: str, user_intent: str = "") -> str:
        """Identify what user is trying to do from description."""
        combined = (description + " " + user_intent).lower()
        
        patterns = {
            "average_order_value": ["average order", "avg order", "order value", "per order"],
            "total_sales": ["total sales", "sum sales", "sales amount"],
            "profit_margin": ["profit margin", "margin", "profit %"],
            "unique_customers": ["unique customers", "customer count", "distinct customer"],
            "month_over_month_growth": ["month over month", "mom growth", "previous month"],
        }
        
        for intent, keywords in patterns.items():
            if any(kw in combined for kw in keywords):
                return intent
        
        return ""
    
    def _fix_average_order_value(self, code: str) -> Tuple[str, Optional[str]]:
        """Fix Average Order Value calculations."""
        code_upper = code.upper()
        
        # Wrong: SUM(Sales[EmployeeKey])
        if "SUM" in code_upper and ("EMPLOYEEKEY" in code_upper or "ID" in code_upper):
            # Find the amount column
            amount_col = self._find_amount_column("Sales")
            order_col = self._find_order_column("Sales")
            
            if amount_col and order_col:
                corrected = f"DIVIDE(SUM(Sales[{amount_col}]), DISTINCTCOUNT(Sales[{order_col}]))"
                return corrected, f"Fixed: Changed from SUM(ID) to proper AOV: DIVIDE(SUM({amount_col}), DISTINCTCOUNT({order_col}))"
        
        # Wrong: AVERAGE(Sales[SalesAmount]) - should be DIVIDE
        if "AVERAGE" in code_upper and ("SALESAMOUNT" in code_upper or "AMOUNT" in code_upper):
            amount_col = self._find_amount_column("Sales")
            order_col = self._find_order_column("Sales")
            
            if amount_col and order_col:
                corrected = f"DIVIDE(SUM(Sales[{amount_col}]), DISTINCTCOUNT(Sales[{order_col}]))"
                return corrected, "Fixed: Changed from AVERAGE to proper AOV using DIVIDE"
        
        return code, None
    
    def _fix_total_sales(self, code: str) -> Tuple[str, Optional[str]]:
        """Fix Total Sales calculations."""
        # Find the correct sales column
        amount_col = self._find_amount_column("Sales")
        
        if amount_col and "SUM" in code.upper():
            # Check if summing wrong column
            if not amount_col.lower() in code.lower():
                corrected = f"SUM(Sales[{amount_col}])"
                return corrected, f"Fixed: Changed to sum correct column: {amount_col}"
        
        return code, None
    
    def _fix_profit_margin(self, code: str) -> Tuple[str, Optional[str]]:
        """Fix Profit Margin calculations."""
        amount_col = self._find_amount_column("Sales")
        cost_col = self._find_cost_column("Sales")
        
        if amount_col and cost_col:
            if "SUM" in code.upper() and "DIVIDE" in code.upper():
                # Structure looks right, just ensure columns are correct
                if amount_col.lower() not in code.lower() or cost_col.lower() not in code.lower():
                    corrected = f"DIVIDE(SUM(Sales[{amount_col}]) - SUM(Sales[{cost_col}]), SUM(Sales[{amount_col}]))"
                    return corrected, f"Fixed: Ensured correct columns in profit margin calculation"
        
        return code, None
    
    def _fix_flag_formula(self, code: str, description: str) -> Tuple[str, Optional[str]]:
        """Fix flag/conditional formulas (IF statements)."""
        # Extract threshold value from description (e.g., "500$" or "> 500")
        threshold_match = re.search(r'([\d.]+)\s*\$?', description)
        threshold = threshold_match.group(1) if threshold_match else "0"
        
        # Identify what is being compared
        is_cost_related = any(x in description.lower() for x in ["cost", "expense", "expense"])
        is_sales_related = any(x in description.lower() for x in ["sales", "revenue", "amount"])
        is_count_related = any(x in description.lower() for x in ["count", "number", "quantity"])
        
        # Find the right column
        if is_cost_related:
            column = self._find_cost_column("Sales")
            metric = f"SUM(Sales[{column}])" if column else "SUM(Sales[Cost])"
        elif is_sales_related:
            column = self._find_amount_column("Sales")
            metric = f"SUM(Sales[{column}])" if column else "SUM(Sales[SalesAmount])"
        elif is_count_related:
            column = self._find_order_column("Sales")
            metric = f"DISTINCTCOUNT(Sales[{column}])" if column else "DISTINCTCOUNT(Sales[OrderID])"
        else:
            # Default to trying to fix the code
            metric = None
        
        # Check if current code is wrong (summing ID columns)
        code_upper = code.upper()
        if "SUM" in code_upper and ("EMPLOYEEKEY" in code_upper or "PRODUCTKEY" in code_upper or "ID" in code_upper):
            if metric:
                corrected = f'IF({metric} > {threshold}, "Yes", "No")'
                return corrected, f"Fixed: Changed from SUM(ID) to SUM({column}) with threshold {threshold}"
        
        # Check if threshold is wrong (> 0 instead of > 500)
        if "> 0" in code or ">0" in code:
            if metric:
                corrected = f'IF({metric} > {threshold}, "Yes", "No")'
                return corrected, f"Fixed: Updated threshold from >0 to >{threshold}"
        
        return code, None
    
    def _find_amount_column(self, table_name: str) -> Optional[str]:
        """Find the amount/sales column in a table."""
        if table_name not in self.tables:
            return None
        
        columns = self.tables[table_name].get("columns", {})
        
        # Look for common amount columns
        for col in columns.keys():
            col_lower = col.lower()
            if any(x in col_lower for x in ["salesamount", "amount", "revenue", "price", "sales"]):
                return col
        
        return None
    
    def _find_cost_column(self, table_name: str) -> Optional[str]:
        """Find the cost column in a table."""
        if table_name not in self.tables:
            return None
        
        columns = self.tables[table_name].get("columns", {})
        
        for col in columns.keys():
            col_lower = col.lower()
            if any(x in col_lower for x in ["cost", "productcost", "unitcost"]):
                return col
        
        return None
    
    def _find_order_column(self, table_name: str) -> Optional[str]:
        """Find the order ID column."""
        if table_name not in self.tables:
            return None
        
        columns = self.tables[table_name].get("columns", {})
        
        for col in columns.keys():
            col_lower = col.lower()
            if any(x in col_lower for x in ["orderid", "order_id", "invoice"]):
                return col
        
        return None
    
    def _check_common_mistakes(self, code: str, language: str) -> List[str]:
        """Check for common mistakes in generated code."""
        warnings = []
        
        if language.upper() == "DAX":
            # Check: Summing ID columns
            id_pattern = r"SUM\s*\(\s*\w+\s*\[\s*\w*(?:Key|ID|EmployeeKey|ProductKey|OrderID)\w*\s*\]\s*\)"
            if re.search(id_pattern, code, re.IGNORECASE):
                warnings.append("⚠️ CRITICAL: Found SUM on ID/Key column. This will give wrong results. Use DISTINCTCOUNT instead.")
            
            # Check: Missing qualified column names
            if "[" in code and "]" in code:
                # Should have Table[Column] format
                unqualified = re.findall(r"(?:SUM|AVERAGE|COUNT)\s*\(\s*\[", code)
                if unqualified:
                    warnings.append("⚠️ Column names should be qualified: Table[Column], not just [Column]")
            
            # Check: Unbalanced parentheses
            if code.count("(") != code.count(")"):
                warnings.append("❌ Unbalanced parentheses - formula is invalid")
        
        return warnings
    
    def generate_dax_formula(self, description: str, item_type: str = "measure", table_name: str = "Sales") -> Tuple[str, List[str]]:
        """
        GENERATE a DAX formula from scratch based on description.
        Returns: (generated_formula, warnings)
        """
        warnings = []
        description_lower = description.lower()
        
        # Identify intent
        intent = self._identify_intent(description)
        
        # Generate formula based on intent
        if item_type == "flag":
            # Flag: IF statement with threshold
            formula = self._generate_flag_formula(description)
        elif "average order" in description_lower:
            formula = self._generate_average_order_value_formula(table_name)
        elif "total sales" in description_lower or "sum of sales" in description_lower:
            formula = self._generate_total_sales_formula(table_name)
        elif "profit margin" in description_lower:
            formula = self._generate_profit_margin_formula(table_name)
        elif "year to date" in description_lower or "ytd" in description_lower:
            formula = self._generate_ytd_formula(table_name)
        elif "unique" in description_lower or "distinct" in description_lower or "count" in description_lower:
            formula = self._generate_distinct_count_formula(table_name)
        else:
            # Fallback: use suggest_formula
            formula = self.suggest_formula(description, table_name)
            if not formula:
                formula = f"PLACEHOLDER -- Could not generate formula for: {description}"
                warnings.append(f"⚠️ No matching pattern for: {description}")
        
        return formula, warnings
    
    def _generate_flag_formula(self, description: str) -> str:
        """Generate IF flag formula from description."""
        # Extract threshold
        threshold_match = re.search(r'([\d.]+)\s*\$?', description)
        threshold = threshold_match.group(1) if threshold_match else "0"
        
        # Identify column type
        is_cost = any(x in description.lower() for x in ["cost", "expense"])
        is_sales = any(x in description.lower() for x in ["sales", "revenue", "amount"])
        is_count = any(x in description.lower() for x in ["count", "number", "quantity", "orders"])
        
        # Generate metric
        if is_cost:
            cost_col = self._find_cost_column("Sales") or "ProductCost"
            metric = f"SUM(Sales[{cost_col}])"
        elif is_sales or not is_count:  # Default to sales
            amount_col = self._find_amount_column("Sales") or "SalesAmount"
            metric = f"SUM(Sales[{amount_col}])"
        else:
            order_col = self._find_order_column("Sales") or "OrderID"
            metric = f"DISTINCTCOUNT(Sales[{order_col}])"
        
        # Return as IF formula
        return f'IF({metric} > {threshold}, "Yes", "No")'
    
    def _generate_average_order_value_formula(self, table_name: str) -> str:
        """Generate Average Order Value formula."""
        amount_col = self._find_amount_column(table_name) or "SalesAmount"
        order_col = self._find_order_column(table_name) or "OrderID"
        return f"DIVIDE(SUM({table_name}[{amount_col}]), DISTINCTCOUNT({table_name}[{order_col}]))"
    
    def _generate_total_sales_formula(self, table_name: str) -> str:
        """Generate Total Sales formula."""
        amount_col = self._find_amount_column(table_name) or "SalesAmount"
        return f"SUM({table_name}[{amount_col}])"
    
    def _generate_profit_margin_formula(self, table_name: str) -> str:
        """Generate Profit Margin formula."""
        amount_col = self._find_amount_column(table_name) or "SalesAmount"
        cost_col = self._find_cost_column(table_name) or "ProductCost"
        return f"DIVIDE(SUM({table_name}[{amount_col}]) - SUM({table_name}[{cost_col}]), SUM({table_name}[{amount_col}]))"
    
    def _generate_ytd_formula(self, table_name: str) -> str:
        """Generate Year-to-Date formula."""
        amount_col = self._find_amount_column(table_name) or "SalesAmount"
        return f"CALCULATE(SUM({table_name}[{amount_col}]), DATESYTD(Dates[Date]))"
    
    def _generate_distinct_count_formula(self, table_name: str) -> str:
        """Generate Distinct Count formula."""
        order_col = self._find_order_column(table_name) or "OrderID"
        return f"DISTINCTCOUNT({table_name}[{order_col}])"
    
    def suggest_formula(self, intent: str, table_name: str = "Sales") -> Optional[str]:
        """Suggest a correct formula based on intent."""
        intent_lower = intent.lower()
        
        if "average order" in intent_lower:
            amount_col = self._find_amount_column(table_name)
            order_col = self._find_order_column(table_name)
            if amount_col and order_col:
                return f"DIVIDE(SUM({table_name}[{amount_col}]), DISTINCTCOUNT({table_name}[{order_col}]))"
        
        elif "total sales" in intent_lower or "total" in intent_lower:
            amount_col = self._find_amount_column(table_name)
            if amount_col:
                return f"SUM({table_name}[{amount_col}])"
        
        elif "profit" in intent_lower and "margin" in intent_lower:
            amount_col = self._find_amount_column(table_name)
            cost_col = self._find_cost_column(table_name)
            if amount_col and cost_col:
                return f"DIVIDE(SUM({table_name}[{amount_col}]) - SUM({table_name}[{cost_col}]), SUM({table_name}[{amount_col}]))"
        
        elif "unique" in intent_lower or "distinct" in intent_lower or "count" in intent_lower:
            order_col = self._find_order_column(table_name)
            if order_col:
                return f"DISTINCTCOUNT({table_name}[{order_col}])"
        
        return None
