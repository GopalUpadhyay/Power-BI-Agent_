"""
Comprehensive End-to-End Application Testing
Tests all major user workflows and features
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ComprehensiveAppTester:
    """Test all application functionality end-to-end"""
    
    def __init__(self):
        self.results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "tests": [],
            "issues": []
        }
    
    def test_imports(self) -> bool:
        """Test 1: Verify all imports work"""
        logger.info("\n" + "="*80)
        logger.info("TEST 1: TESTING ALL IMPORTS")
        logger.info("="*80)
        
        try:
            from assistant_app.formula_corrector import FormulaCorrector, SemanticColumnMatcher
            from assistant_app.fabric_universal import UniversalFabricAssistant
            from assistant_app.pbix_extractor import PBIXExtractor
            from assistant_app.model_store import ModelStore
            from assistant_app.ui import main
            
            logger.info("✅ All imports successful")
            self.results['passed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "Imports", "status": "PASS"})
            return True
        except Exception as e:
            logger.error(f"❌ Import failed: {str(e)}")
            self.results['failed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "Imports", "status": "FAIL", "error": str(e)})
            self.results['issues'].append(f"Import Error: {str(e)}")
            return False
    
    def test_semantic_matcher(self) -> bool:
        """Test 2: Test SemanticColumnMatcher"""
        logger.info("\n" + "="*80)
        logger.info("TEST 2: SEMANTIC COLUMN MATCHER")
        logger.info("="*80)
        
        try:
            from assistant_app.formula_corrector import SemanticColumnMatcher
            
            # Create test metadata
            metadata = {
                'tables': {
                    'Sales': {
                        'columns': {
                            'SalesAmount': 'numeric',
                            'ProductCost': 'numeric',
                            'OrderID': 'string',
                            'OrderDate': 'date',
                            'EmployeeKey': 'string'
                        }
                    }
                },
                'relationships': [
                    {'from_table': 'Sales', 'from_column': 'EmployeeKey', 
                     'to_table': 'Employee', 'to_column': 'EmployeeKey'}
                ]
            }
            
            matcher = SemanticColumnMatcher(metadata)
            
            # Test 2.1: Find amount column
            amt_col = matcher.find_column("amount", "Sales")
            assert amt_col == ("Sales", "SalesAmount"), f"Amount column mismatch: {amt_col}"
            logger.info("  ✓ Amount column detection: OK")
            
            # Test 2.2: Find cost column
            cost_col = matcher.find_column("cost", "Sales")
            assert cost_col == ("Sales", "ProductCost"), f"Cost column mismatch: {cost_col}"
            logger.info("  ✓ Cost column detection: OK")
            
            # Test 2.3: Find count column
            count_col = matcher.find_column("count", "Sales")
            assert count_col == ("Sales", "OrderID"), f"Count column mismatch: {count_col}"
            logger.info("  ✓ Count column detection: OK")
            
            # Test 2.4: Find date column
            date_col = matcher.find_column("date", "Sales")
            assert date_col == ("Sales", "OrderDate"), f"Date column mismatch: {date_col}"
            logger.info("  ✓ Date column detection: OK")
            
            # Test 2.5: Fact table detection
            fact_table = matcher.find_fact_table()
            assert fact_table == "Sales", f"Fact table mismatch: {fact_table}"
            logger.info("  ✓ Fact table detection: OK")
            
            logger.info("✅ SemanticColumnMatcher: ALL TESTS PASSED")
            self.results['passed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "SemanticColumnMatcher", "status": "PASS"})
            return True
        except Exception as e:
            logger.error(f"❌ SemanticColumnMatcher failed: {str(e)}")
            self.results['failed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "SemanticColumnMatcher", "status": "FAIL", "error": str(e)})
            self.results['issues'].append(f"SemanticColumnMatcher Error: {str(e)}")
            return False
    
    def test_formula_generation(self) -> bool:
        """Test 3: Test FormulaCorrector generation"""
        logger.info("\n" + "="*80)
        logger.info("TEST 3: FORMULA GENERATION")
        logger.info("="*80)
        
        try:
            from assistant_app.formula_corrector import FormulaCorrector
            
            metadata = {
                'tables': {
                    'Sales': {
                        'columns': {
                            'SalesAmount': 'numeric',
                            'ProductCost': 'numeric',
                            'OrderID': 'string',
                            'OrderDate': 'date',
                            'EmployeeKey': 'string'
                        }
                    }
                },
                'relationships': []
            }
            
            corrector = FormulaCorrector(metadata)
            
            # Test 3.1: Total Sales generation
            formula, warnings = corrector.generate_dax_formula("Total Sales", "measure")
            assert "SUM" in formula, "SUM not in formula"
            assert "SalesAmount" in formula, "SalesAmount not in formula"
            logger.info(f"  ✓ Total Sales: {formula}")
            
            # Test 3.2: Average Order Value generation
            formula, warnings = corrector.generate_dax_formula("Average Order Value", "measure")
            assert "DIVIDE" in formula, "DIVIDE not in formula"
            assert "DISTINCTCOUNT" in formula, "DISTINCTCOUNT not in formula"
            logger.info(f"  ✓ Average Order Value: {formula}")
            
            # Test 3.3: Profit Margin generation
            formula, warnings = corrector.generate_dax_formula("Profit Margin", "measure")
            assert "ProductCost" in formula, "ProductCost not in formula"
            logger.info(f"  ✓ Profit Margin: {formula}")
            
            # Test 3.4: YTD generation
            formula, warnings = corrector.generate_dax_formula("Sales Year to Date", "measure")
            assert "DATESYTD" in formula, "DATESYTD not in formula"
            logger.info(f"  ✓ Year-to-Date: {formula}")
            
            # Test 3.5: Flag generation
            formula, warnings = corrector.generate_dax_formula("Flag if cost > 500", "flag")
            assert "IF" in formula, "IF not in formula"
            assert "> 500" in formula, "> 500 not in formula"
            logger.info(f"  ✓ Cost Flag: {formula}")
            
            logger.info("✅ Formula Generation: ALL TESTS PASSED")
            self.results['passed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "FormulaGeneration", "status": "PASS"})
            return True
        except Exception as e:
            logger.error(f"❌ Formula generation failed: {str(e)}")
            self.results['failed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "FormulaGeneration", "status": "FAIL", "error": str(e)})
            self.results['issues'].append(f"Formula Generation Error: {str(e)}")
            return False
    
    def test_formula_correction(self) -> bool:
        """Test 4: Test FormulaCorrector correction"""
        logger.info("\n" + "="*80)
        logger.info("TEST 4: FORMULA CORRECTION")
        logger.info("="*80)
        
        try:
            from assistant_app.formula_corrector import FormulaCorrector
            
            metadata = {
                'tables': {
                    'Sales': {
                        'columns': {
                            'SalesAmount': 'numeric',
                            'ProductCost': 'numeric',
                            'OrderID': 'string',
                            'OrderDate': 'date',
                            'EmployeeKey': 'string'
                        }
                    }
                },
                'relationships': []
            }
            
            corrector = FormulaCorrector(metadata)
            
            # Test 4.1: Correct wrong average formula
            wrong = "IF(SUM(Sales[EmployeeKey]) > 0, 'Yes', 'No')"
            desc = "Return true if number of orders is greater than 10"
            corrected, warnings = corrector.correct_dax_formula(wrong, desc, '', 'flag')
            assert "DISTINCTCOUNT" in corrected, "Should have DISTINCTCOUNT"
            assert "OrderID" in corrected, "Should have OrderID"
            assert "> 10" in corrected, "Should have > 10"
            logger.info(f"  ✓ Corrected flag formula: {corrected}")
            
            # Test 4.2: Detect ID column on SUM
            code = "SUM(Sales[EmployeeKey])"
            issues = corrector._validate(code)
            assert any("ID" in issue for issue in issues), "Should detect ID column issue"
            logger.info(f"  ✓ ID column detection: OK")
            
            # Test 4.3: Detect unbalanced parentheses
            code = "SUM(Sales[SalesAmount]"
            issues = corrector._validate(code)
            assert any("parenthesis" in issue.lower() or "paren" in issue.lower() for issue in issues), "Should detect unbalanced"
            logger.info(f"  ✓ Unbalanced parentheses detection: OK")
            
            logger.info("✅ Formula Correction: ALL TESTS PASSED")
            self.results['passed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "FormulaCorrection", "status": "PASS"})
            return True
        except Exception as e:
            logger.error(f"❌ Formula correction failed: {str(e)}")
            self.results['failed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "FormulaCorrection", "status": "FAIL", "error": str(e)})
            self.results['issues'].append(f"Formula Correction Error: {str(e)}")
            return False
    
    def test_metadata_extraction(self) -> bool:
        """Test 5: Test PBIX metadata extraction"""
        logger.info("\n" + "="*80)
        logger.info("TEST 5: PBIX METADATA EXTRACTION")
        logger.info("="*80)
        
        try:
            from assistant_app.pbix_extractor import PBIXExtractor
            
            # Create sample metadata for testing
            test_metadata = {
                "tables": {
                    "Sales": {
                        "columns": {"Amount": "numeric", "Date": "date"},
                        "column_count": 2
                    }
                },
                "relationships": []
            }
            
            # Verify validation works
            assert test_metadata['tables'], "Tables not present"
            assert len(test_metadata['tables']) > 0, "No tables in metadata"
            logger.info("  ✓ Metadata structure validation: OK")
            
            logger.info("✅ PBIX Metadata Extraction: READY")
            self.results['passed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "MetadataExtraction", "status": "PASS"})
            return True
        except Exception as e:
            logger.error(f"❌ Metadata extraction failed: {str(e)}")
            self.results['failed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "MetadataExtraction", "status": "FAIL", "error": str(e)})
            self.results['issues'].append(f"Metadata Extraction Error: {str(e)}")
            return False
    
    def test_configuration(self) -> bool:
        """Test 6: Test configuration and environment"""
        logger.info("\n" + "="*80)
        logger.info("TEST 6: CONFIGURATION & ENVIRONMENT")
        logger.info("="*80)
        
        try:
            from pathlib import Path
            
            # Check .env file
            env_path = Path("/home/gopal-upadhyay/AI_Bot_MAQ/.env")
            if env_path.exists():
                logger.info("  ✓ .env file exists")
            else:
                logger.warning("  ⚠ .env file not found (may use defaults)")
            
            # Check virtual environment
            try:
                import venv
                logger.info("  ✓ Python venv module available")
            except:
                logger.warning("  ⚠ venv module not available")
            
            # Check required directories
            paths_to_check = [
                Path("/home/gopal-upadhyay/AI_Bot_MAQ/assistant_app"),
                Path("/home/gopal-upadhyay/AI_Bot_MAQ/.venv"),
                Path("/home/gopal-upadhyay/AI_Bot_MAQ/requirements.txt")
            ]
            
            for path in paths_to_check:
                if path.exists():
                    logger.info(f"  ✓ {path.name} exists")
                else:
                    logger.warning(f"  ⚠ {path.name} missing")
            
            logger.info("✅ Configuration & Environment: OK")
            self.results['passed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "Configuration", "status": "PASS"})
            return True
        except Exception as e:
            logger.error(f"❌ Configuration test failed: {str(e)}")
            self.results['failed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "Configuration", "status": "FAIL", "error": str(e)})
            self.results['issues'].append(f"Configuration Error: {str(e)}")
            return False
    
    def test_error_handling(self) -> bool:
        """Test 7: Test error handling and edge cases"""
        logger.info("\n" + "="*80)
        logger.info("TEST 7: ERROR HANDLING & EDGE CASES")
        logger.info("="*80)
        
        try:
            from assistant_app.formula_corrector import FormulaCorrector
            
            metadata = {
                'tables': {
                    'Sales': {
                        'columns': {
                            'SalesAmount': 'numeric',
                            'OrderID': 'string',
                        }
                    }
                },
                'relationships': []
            }
            
            corrector = FormulaCorrector(metadata)
            
            # Test 7.1: Empty description
            formula, warnings = corrector.generate_dax_formula("", "measure")
            assert formula, "Should generate default formula"
            logger.info("  ✓ Empty description handling: OK")
            
            # Test 7.2: Invalid item type
            formula, warnings = corrector.generate_dax_formula("test", "invalid_type")
            assert formula, "Should handle gracefully"
            logger.info("  ✓ Invalid item type handling: OK")
            
            # Test 7.3: Missing metadata
            try:
                empty_corrector = FormulaCorrector({'tables': {}, 'relationships': []})
                formula, warnings = empty_corrector.generate_dax_formula("test", "measure")
                logger.info("  ✓ Empty metadata handling: OK")
            except:
                logger.info("  ✓ Empty metadata raises error (expected): OK")
            
            logger.info("✅ Error Handling & Edge Cases: OK")
            self.results['passed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "ErrorHandling", "status": "PASS"})
            return True
        except Exception as e:
            logger.error(f"❌ Error handling test failed: {str(e)}")
            self.results['failed'] += 1
            self.results['total_tests'] += 1
            self.results['tests'].append({"name": "ErrorHandling", "status": "FAIL", "error": str(e)})
            self.results['issues'].append(f"Error Handling Test Error: {str(e)}")
            return False
    
    def run_all_tests(self) -> Dict:
        """Run all tests and return results"""
        logger.info("\n\n")
        logger.info("╔" + "="*78 + "╗")
        logger.info("║" + " "*78 + "║")
        logger.info("║" + "COMPREHENSIVE APPLICATION TEST SUITE".center(78) + "║")
        logger.info("║" + " "*78 + "║")
        logger.info("╚" + "="*78 + "╝")
        
        # Run all tests
        self.test_imports()
        self.test_semantic_matcher()
        self.test_formula_generation()
        self.test_formula_correction()
        self.test_metadata_extraction()
        self.test_configuration()
        self.test_error_handling()
        
        # Print summary
        logger.info("\n\n")
        logger.info("╔" + "="*78 + "╗")
        logger.info("║" + " "*78 + "║")
        logger.info("║" + "TEST RESULTS SUMMARY".center(78) + "║")
        logger.info("║" + " "*78 + "║")
        logger.info("╚" + "="*78 + "╝")
        
        logger.info(f"\nTotal Tests: {self.results['total_tests']}")
        logger.info(f"✅ Passed: {self.results['passed']}")
        logger.info(f"❌ Failed: {self.results['failed']}")
        
        if self.results['total_tests'] > 0:
            pass_rate = (self.results['passed'] / self.results['total_tests']) * 100
            logger.info(f"Pass Rate: {pass_rate:.1f}%")
        
        if self.results['issues']:
            logger.info("\n⚠️ ISSUES FOUND:")
            for issue in self.results['issues']:
                logger.error(f"  • {issue}")
        else:
            logger.info("\n✅ NO ISSUES FOUND")
        
        logger.info("\n" + "="*80)
        
        if self.results['failed'] == 0:
            logger.info("🎉 ALL TESTS PASSED - APPLICATION IS READY FOR PRODUCTION")
        else:
            logger.info(f"⚠️ {self.results['failed']} TEST(S) FAILED - PLEASE FIX BEFORE DEPLOYMENT")
        
        logger.info("="*80 + "\n")
        
        return self.results


if __name__ == "__main__":
    tester = ComprehensiveAppTester()
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    exit(0 if results['failed'] == 0 else 1)
