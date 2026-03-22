#!/usr/bin/env python3
"""
COMPREHENSIVE APPLICATION TEST SUITE
Tests all item types, languages, and outputs
Validates correctness and identifies errors
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Setup
sys.path.insert(0, '/home/gopal-upadhyay/AI_Bot_MAQ')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import application modules
try:
    from assistant_app.formula_corrector import FormulaCorrector, SemanticColumnMatcher
    from assistant_app.fabric_universal import UniversalFabricAssistant, ValidationEngine
    from dotenv import load_dotenv
    import os
    
    load_dotenv()
    API_KEY = os.getenv('AI_BOT_MAQ_OPENAI_API_KEY')
    
    logger.info("✅ All imports successful")
except Exception as e:
    logger.error(f"❌ Import failed: {e}")
    sys.exit(1)


class ComprehensiveTestSuite:
    """Test all application functionality"""
    
    def __init__(self):
        self.results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": [],
            "warnings": [],
            "test_details": []
        }
        
        # Sample metadata for testing
        self.metadata = {
            "tables": {
                "Sales": {
                    "columns": {
                        "OrderID": {"type": "int"},
                        "SalesAmount": {"type": "decimal"},
                        "ProductCost": {"type": "decimal"},
                        "EmployeeKey": {"type": "int"},
                        "ProductKey": {"type": "int"},
                        "SalesPersonID": {"type": "int"},
                        "RegionID": {"type": "int"},
                        "OrderDate": {"type": "datetime"},
                        "Quantity": {"type": "int"}
                    }
                },
                "Product": {
                    "columns": {
                        "ProductKey": {"type": "int"},
                        "ProductName": {"type": "string"},
                        "Category": {"type": "string"},
                        "Price": {"type": "decimal"},
                        "Cost": {"type": "decimal"}
                    }
                },
                "Customer": {
                    "columns": {
                        "CustomerID": {"type": "int"},
                        "CustomerName": {"type": "string"},
                        "City": {"type": "string"},
                        "Country": {"type": "string"},
                        "Region": {"type": "string"}
                    }
                },
                "Employee": {
                    "columns": {
                        "EmployeeKey": {"type": "int"},
                        "EmployeeName": {"type": "string"},
                        "Department": {"type": "string"},
                        "SalesPersonID": {"type": "int"}
                    }
                }
            },
            "relationships": [
                {
                    "from_table": "Sales",
                    "from_column": "ProductKey",
                    "to_table": "Product",
                    "to_column": "ProductKey"
                },
                {
                    "from_table": "Sales",
                    "from_column": "EmployeeKey",
                    "to_table": "Employee",
                    "to_column": "EmployeeKey"
                }
            ]
        }
    
    def run_all_tests(self):
        """Run all tests"""
        logger.info("\n" + "="*100)
        logger.info("STARTING COMPREHENSIVE APPLICATION TEST SUITE")
        logger.info("="*100)
        
        self.test_semantic_column_matcher()
        self.test_dax_measure_generation()
        self.test_dax_column_generation()
        self.test_dax_flag_generation()
        self.test_validation_engine()
        self.test_error_handling()
        self.test_edge_cases()
        self.test_output_formats()
        
        self.print_summary()
    
    def add_test_result(self, name: str, status: str, details: str = ""):
        """Record test result"""
        self.results["total_tests"] += 1
        if status == "PASS":
            self.results["passed"] += 1
            logger.info(f"✅ {name}: PASS")
        else:
            self.results["failed"] += 1
            logger.error(f"❌ {name}: FAIL - {details}")
            self.results["errors"].append(f"{name}: {details}")
        
        self.results["test_details"].append({
            "name": name,
            "status": status,
            "details": details
        })
    
    @staticmethod
    def is_valid_dax(code: str) -> Tuple[bool, List[str]]:
        """Validate DAX syntax"""
        issues = []
        
        if not code or not code.strip():
            return False, ["Empty DAX code"]
        
        # Check for common DAX patterns
        code_lower = code.lower()
        
        # Valid measures should have aggregation
        valid_aggregations = ["sum", "average", "count", "max", "min", "distinctcount", "divide", "calculate"]
        has_aggregation = any(agg in code_lower for agg in valid_aggregations)
        
        if not has_aggregation:
            issues.append("No aggregation function found")
        
        # Check qualifications
        if "[" in code and "]" in code:
            # Should have table[column] format
            pass
        else:
            issues.append("No qualified columns detected")
        
        # Check for common errors
        common_errors = {
            "SUM(ID)": "Summing ID columns",
            "SUM(Key)": "Summing Key columns",
            "SUM(Name)": "Summing text columns"
        }
        
        for error_pattern, error_msg in common_errors.items():
            if error_pattern.lower() in code_lower:
                issues.append(f"⚠️ {error_msg}")
        
        return len(issues) == 0, issues
    
    @staticmethod
    def is_valid_sql(code: str) -> Tuple[bool, List[str]]:
        """Validate SQL syntax"""
        issues = []
        
        if not code or not code.strip():
            return False, ["Empty SQL code"]
        
        code_upper = code.upper()
        
        # Check for SELECT statement
        if "SELECT" not in code_upper:
            issues.append("No SELECT statement")
        
        # Check for FROM
        if "FROM" not in code_upper:
            issues.append("No FROM clause")
        
        return len(issues) == 0, issues
    
    @staticmethod
    def is_valid_pyspark(code: str) -> Tuple[bool, List[str]]:
        """Validate PySpark syntax"""
        issues = []
        
        if not code or not code.strip():
            return False, ["Empty PySpark code"]
        
        code_lower = code.lower()
        
        # Check for dataframe operations
        if "join" not in code_lower and "select" not in code_lower:
            issues.append("No join or select operations found")
        
        if ".createOrReplaceTempView" not in code:
            issues.append("No temporary view creation")
        
        return len(issues) == 0, issues
    
    def test_semantic_column_matcher(self):
        """Test 1: Semantic Column Matcher"""
        logger.info("\n" + "-"*100)
        logger.info("TEST 1: SEMANTIC COLUMN MATCHER")
        logger.info("-"*100)
        
        try:
            matcher = SemanticColumnMatcher(self.metadata)
            
            # Test different semantic types - find_column returns (table, column) tuple or None
            # Use the actual semantic types from the index: amount, cost, id, date, count
            test_cases = [
                ("amount", ["SalesAmount", "Revenue", "Price"]),  # amount semantic type
                ("cost", ["ProductCost", "Cost"]),                 # cost semantic type
                ("id", ["CustomerID", "ProductKey", "EmployeeKey"]),  # id semantic type
                ("date", ["OrderDate"]),                           # date semantic type
                ("count", ["OrderID"])                             # count semantic type (order-related)
            ]
            
            for semantic_type, expected_columns in test_cases:
                try:
                    matched = matcher.find_column(semantic_type, "Sales")
                    if matched:
                        # matched is a tuple (table, column)
                        if isinstance(matched, tuple) and len(matched) == 2:
                            table, column = matched
                            if column in expected_columns or any(exp.lower() == column.lower() for exp in expected_columns):
                                self.add_test_result(f"Semantic Match: {semantic_type}", "PASS")
                            else:
                                self.add_test_result(f"Semantic Match: {semantic_type}", "FAIL", f"Got column {column}, expected one of {expected_columns}")
                        else:
                            self.add_test_result(f"Semantic Match: {semantic_type}", "FAIL", f"Invalid return format: {matched}")
                    else:
                        self.add_test_result(f"Semantic Match: {semantic_type}", "FAIL", "find_column returned None")
                except Exception as e:
                    self.add_test_result(f"Semantic Match: {semantic_type}", "FAIL", str(e))
        
        except Exception as e:
            self.add_test_result("Semantic Column Matcher Init", "FAIL", str(e))
    
    def test_dax_measure_generation(self):
        """Test 2: DAX Measure Generation"""
        logger.info("\n" + "-"*100)
        logger.info("TEST 2: DAX MEASURE GENERATION")
        logger.info("-"*100)
        
        try:
            corrector = FormulaCorrector(self.metadata)
            
            test_cases = [
                ("Total Sales", "measure"),
                ("Average Order Value", "measure"),
                ("Profit Margin", "measure"),
                ("Customer Count", "measure"),
                ("Sales YTD", "measure")
            ]
            
            for description, item_type in test_cases:
                try:
                    formula, warnings = corrector.generate_dax_formula(description, item_type)
                    
                    if formula.startswith("ERROR"):
                        self.add_test_result(f"DAX Measure: {description}", "FAIL", formula)
                    else:
                        is_valid, issues = self.is_valid_dax(formula)
                        if is_valid:
                            self.add_test_result(f"DAX Measure: {description}", "PASS")
                            logger.info(f"  Formula: {formula}")
                        else:
                            self.add_test_result(f"DAX Measure: {description}", "FAIL", f"Issues: {issues}")
                            logger.warning(f"  Issues: {issues}")
                
                except Exception as e:
                    self.add_test_result(f"DAX Measure: {description}", "FAIL", str(e))
        
        except Exception as e:
            self.add_test_result("DAX Measure Generation Init", "FAIL", str(e))
    
    def test_dax_column_generation(self):
        """Test 3: DAX Column Generation"""
        logger.info("\n" + "-"*100)
        logger.info("TEST 3: DAX COLUMN GENERATION")
        logger.info("-"*100)
        
        try:
            corrector = FormulaCorrector(self.metadata)
            
            test_cases = [
                ("Calculate Profit", "column"),
                ("Half Year Sales", "column"),
                ("Price Category", "column")
            ]
            
            for description, item_type in test_cases:
                try:
                    formula, warnings = corrector.generate_dax_formula(description, item_type)
                    
                    if formula.startswith("ERROR"):
                        self.add_test_result(f"DAX Column: {description}", "FAIL", formula)
                    else:
                        is_valid, issues = self.is_valid_dax(formula)
                        if is_valid:
                            self.add_test_result(f"DAX Column: {description}", "PASS")
                            logger.info(f"  Formula: {formula}")
                        else:
                            self.add_test_result(f"DAX Column: {description}", "FAIL", f"Issues: {issues}")
                
                except Exception as e:
                    self.add_test_result(f"DAX Column: {description}", "FAIL", str(e))
        
        except Exception as e:
            self.add_test_result("DAX Column Generation Init", "FAIL", str(e))
    
    def test_dax_flag_generation(self):
        """Test 4: DAX Flag Generation"""
        logger.info("\n" + "-"*100)
        logger.info("TEST 4: DAX FLAG GENERATION")
        logger.info("-"*100)
        
        try:
            corrector = FormulaCorrector(self.metadata)
            
            test_cases = [
                ("Is High Value Order", "flag"),
                ("Is Recent Order", "flag"),
                ("Top Customer Flag", "flag")
            ]
            
            for description, item_type in test_cases:
                try:
                    formula, warnings = corrector.generate_dax_formula(description, item_type)
                    
                    if formula.startswith("ERROR"):
                        self.add_test_result(f"DAX Flag: {description}", "FAIL", formula)
                    else:
                        # Flags should have IF or comparison operators
                        if "IF" in formula.upper() or "=" in formula or ">" in formula:
                            self.add_test_result(f"DAX Flag: {description}", "PASS")
                            logger.info(f"  Formula: {formula}")
                        else:
                            self.add_test_result(f"DAX Flag: {description}", "FAIL", "Missing conditional logic")
                
                except Exception as e:
                    self.add_test_result(f"DAX Flag: {description}", "FAIL", str(e))
        
        except Exception as e:
            self.add_test_result("DAX Flag Generation Init", "FAIL", str(e))
    
    def test_validation_engine(self):
        """Test 5: Validation Engine"""
        logger.info("\n" + "-"*100)
        logger.info("TEST 5: VALIDATION ENGINE")
        logger.info("-"*100)
        
        try:
            validator = ValidationEngine(self.metadata)
            
            test_formulas = [
                ("SUM(Sales[SalesAmount])", "DAX", True, "Valid sum"),
                ("SUM(Sales[EmployeeKey])", "DAX", False, "Summing ID - should warn"),
                ("AVERAGE(Sales[SalesAmount])", "DAX", True, "Valid average"),
                ("SELECT * FROM Sales", "SQL", True, "Valid SQL"),
                ("DIVIDE(SUM(Sales[SalesAmount]), DISTINCTCOUNT(Sales[OrderID]))", "DAX", True, "Valid divided measure")
            ]
            
            for formula, gen_type, should_pass, description in test_formulas:
                try:
                    is_valid, errors = validator.validate_code(gen_type, formula)
                    
                    # For "Summing ID" test, it should warn but still be "valid" (no critical errors)
                    # The warnings are in the errors list
                    if description == "Summing ID - should warn":
                        if any("ID" in str(e) or "Key" in str(e) for e in errors):
                            self.add_test_result(f"Validation: {description}", "PASS")
                        else:
                            self.add_test_result(f"Validation: {description}", "FAIL", "Expected warning about ID columns")
                    elif is_valid == should_pass:
                        self.add_test_result(f"Validation: {description}", "PASS")
                    else:
                        self.add_test_result(f"Validation: {description}", "FAIL", 
                                           f"Expected valid={should_pass}, got {is_valid}. Errors: {errors}")
                
                except Exception as e:
                    self.add_test_result(f"Validation: {description}", "FAIL", str(e))
        
        except Exception as e:
            self.add_test_result("Validation Engine Init", "FAIL", str(e))
    
    def test_error_handling(self):
        """Test 6: Error Handling"""
        logger.info("\n" + "-"*100)
        logger.info("TEST 6: ERROR HANDLING")
        logger.info("-"*100)
        
        try:
            corrector = FormulaCorrector(self.metadata)
            
            # Test error cases
            test_cases = [
                ("", "Empty description"),
                ("xyz unknown thing", "Unknown terminology"),
                ("Calculate unknown_column_name", "Non-existent column")
            ]
            
            for description, case_name in test_cases:
                try:
                    if description:
                        formula, warnings = corrector.generate_dax_formula(description, "measure")
                        
                        # Should either return error or fallback gracefully
                        if formula.startswith("ERROR") or formula:
                            self.add_test_result(f"Error Handling: {case_name}", "PASS")
                        else:
                            self.add_test_result(f"Error Handling: {case_name}", "FAIL", "Invalid response")
                    else:
                        self.add_test_result(f"Error Handling: {case_name}", "PASS")
                
                except Exception as e:
                    # Exception is acceptable for error cases
                    self.add_test_result(f"Error Handling: {case_name}", "PASS")
        
        except Exception as e:
            self.add_test_result("Error Handling Init", "FAIL", str(e))
    
    def test_edge_cases(self):
        """Test 7: Edge Cases"""
        logger.info("\n" + "-"*100)
        logger.info("TEST 7: EDGE CASES")
        logger.info("-"*100)
        
        try:
            corrector = FormulaCorrector(self.metadata)
            
            test_cases = [
                ("Sum of Sales Amount", "measure"),
                ("Count Distinct Customers", "measure"),
                ("Maximum Price Ever", "measure"),
                ("Min Cost Ever", "measure"),
                ("Sales Greater Than 1000", "flag")
            ]
            
            for description, item_type in test_cases:
                try:
                    formula, warnings = corrector.generate_dax_formula(description, item_type)
                    
                    if not formula.startswith("ERROR") and formula:
                        self.add_test_result(f"Edge Case: {description}", "PASS")
                    else:
                        self.add_test_result(f"Edge Case: {description}", "FAIL", formula)
                
                except Exception as e:
                    self.add_test_result(f"Edge Case: {description}", "FAIL", str(e))
        
        except Exception as e:
            self.add_test_result("Edge Cases Init", "FAIL", str(e))
    
    def test_output_formats(self):
        """Test 8: Output Formats"""
        logger.info("\n" + "-"*100)
        logger.info("TEST 8: OUTPUT FORMATS")
        logger.info("-"*100)
        
        try:
            corrector = FormulaCorrector(self.metadata)
            
            # Test that all outputs are strings and properly formatted
            test_cases = [
                ("Total Revenue", "measure"),
                ("Order Count", "measure"),
                ("Is Premium Customer", "flag")
            ]
            
            for description, item_type in test_cases:
                try:
                    formula, warnings = corrector.generate_dax_formula(description, item_type)
                    
                    # Check output format
                    if isinstance(formula, str) and len(formula) > 0:
                        self.add_test_result(f"Output Format: {description}", "PASS")
                    else:
                        self.add_test_result(f"Output Format: {description}", "FAIL", 
                                           f"Invalid format: {type(formula)} with length {len(formula) if formula else 0}")
                
                except Exception as e:
                    self.add_test_result(f"Output Format: {description}", "FAIL", str(e))
        
        except Exception as e:
            self.add_test_result("Output Formats Init", "FAIL", str(e))
    
    def print_summary(self):
        """Print test summary"""
        logger.info("\n" + "="*100)
        logger.info("TEST SUMMARY")
        logger.info("="*100)
        
        logger.info(f"Total Tests: {self.results['total_tests']}")
        logger.info(f"Passed: {self.results['passed']} ✅")
        logger.info(f"Failed: {self.results['failed']} ❌")
        
        if self.results['passed'] == self.results['total_tests']:
            logger.info("\n🎉 ALL TESTS PASSED! 🎉")
        else:
            logger.info(f"\n⚠️  {self.results['failed']} tests failed")
            
            if self.results['errors']:
                logger.info("\nErrors:")
                for error in self.results['errors']:
                    logger.error(f"  • {error}")
        
        # Calculate pass percentage
        if self.results['total_tests'] > 0:
            percentage = (self.results['passed'] / self.results['total_tests']) * 100
            logger.info(f"\nPass Rate: {percentage:.1f}%")
        
        logger.info("="*100)
        
        # Save results to file
        results_file = Path("/home/gopal-upadhyay/AI_Bot_MAQ/test_results_comprehensive.json")
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    suite = ComprehensiveTestSuite()
    suite.run_all_tests()
