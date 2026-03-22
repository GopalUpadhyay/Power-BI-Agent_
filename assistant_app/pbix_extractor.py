"""Power BI PBIX/PBIT file extractor - Extracts metadata from Power BI model files."""

import json
import zipfile
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


class PBIXExtractor:
    """Extracts schema metadata from PBIX/PBIT files."""

    # XML namespaces used in Power BI model files
    NAMESPACES = {
        "tm": "http://schemas.microsoft.com/analysisservices/360/engine/tabular/model",
        "tmd": "http://schemas.microsoft.com/analysisservices/360/engine/tabular/model/design",
    }

    @staticmethod
    def _clean_name(name: str) -> str:
        """Clean Unicode artifacts from names (zero-width spaces, BOM markers, etc.)."""
        if not name:
            return name
        return name.replace('\ufeff', '').replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').strip()

    @staticmethod
    def extract_metadata(pbix_file_path: str) -> Optional[Dict[str, Any]]:
        """
        Extract schema metadata from a PBIX or PBIT file.
        
        Returns:
            Dict with tables, relationships, measures, calculated columns
            None if extraction fails
        """
        try:
            with zipfile.ZipFile(pbix_file_path, "r") as zip_ref:
                # Power BI model is stored in DataModel.json or model.json
                model_data = None
                
                # Try DataModel.json (newer format)
                if "DataModel.json" in zip_ref.namelist():
                    with zip_ref.open("DataModel.json") as f:
                        model_data = json.load(f)
                
                # Fallback to model.json (older format)
                elif "model.json" in zip_ref.namelist():
                    with zip_ref.open("model.json") as f:
                        model_data = json.load(f)
                
                # Otherwise try to extract from model.xml (legacy)
                else:
                    return PBIXExtractor._extract_from_xml(zip_ref)
                
                if model_data:
                    return PBIXExtractor._parse_model_json(model_data)
                
                return None

        except Exception as e:
            logger.error(f"Failed to extract PBIX metadata: {str(e)}")
            return None

    @staticmethod
    def _extract_from_xml(zip_ref: zipfile.ZipFile) -> Optional[Dict[str, Any]]:
        """Extract metadata from legacy XML-based PBIX files."""
        try:
            # Look for model.xml in the archive
            model_files = [f for f in zip_ref.namelist() if "model.xml" in f.lower()]
            
            if not model_files:
                return None
            
            with zip_ref.open(model_files[0]) as f:
                root = ET.parse(f).getroot()
            
            metadata = {
                "tables": {},
                "relationships": [],
                "measures": {},
                "calculated_columns": {},
            }
            
            # Find all tables in the model
            for table_elem in root.findall(".//tm:Table", PBIXExtractor.NAMESPACES):
                table_name = PBIXExtractor._clean_name(table_elem.get("Name", "UnnamedTable"))
                columns = {}
                measures = {}
                
                # Extract columns
                for col_elem in table_elem.findall(".//tm:Column", PBIXExtractor.NAMESPACES):
                    col_name = PBIXExtractor._clean_name(col_elem.get("Name", "UnnamedColumn"))
                    col_type = col_elem.get("DataType", "string")
                    columns[col_name] = col_type
                
                # Extract measures
                for measure_elem in table_elem.findall(".//tm:Measure", PBIXExtractor.NAMESPACES):
                    measure_name = PBIXExtractor._clean_name(measure_elem.get("Name", "UnnamedMeasure"))
                    expression = measure_elem.findtext(".//tm:Expression", "")
                    if expression:
                        measures[measure_name] = {
                            "expression": expression.strip(),
                            "table": table_name,
                        }
                
                if columns:
                    metadata["tables"][table_name] = {
                        "columns": columns,
                        "column_count": len(columns),
                    }
                    
                    if measures:
                        metadata["measures"].update(measures)
            
            # Extract relationships
            for rel_elem in root.findall(".//tm:Relationship", PBIXExtractor.NAMESPACES):
                from_table = PBIXExtractor._clean_name(rel_elem.findtext(".//tm:FromTable", ""))
                from_col = PBIXExtractor._clean_name(rel_elem.findtext(".//tm:FromColumn", ""))
                to_table = PBIXExtractor._clean_name(rel_elem.findtext(".//tm:ToTable", ""))
                to_col = PBIXExtractor._clean_name(rel_elem.findtext(".//tm:ToColumn", ""))
                
                if from_table and from_col and to_table and to_col:
                    metadata["relationships"].append({
                        "from_table": from_table,
                        "from_column": from_col,
                        "to_table": to_table,
                        "to_column": to_col,
                        "name": f"{from_table}-{to_table}",
                    })
            
            return metadata if metadata["tables"] else None
            
        except Exception as e:
            logger.error(f"Failed to extract from XML: {str(e)}")
            return None

    @staticmethod
    def _parse_model_json(model_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Power BI model from JSON format."""
        metadata = {
            "tables": {},
            "relationships": [],
            "measures": {},
            "calculated_columns": {},
        }
        
        # Extract tables from JSON structure
        tables = model_data.get("tables", [])
        if not isinstance(tables, list):
            return None
        
        for table in tables:
            table_name = PBIXExtractor._clean_name(table.get("name", "UnnamedTable"))
            columns = {}
            
            # Extract columns
            for column in table.get("columns", []):
                col_name = PBIXExtractor._clean_name(column.get("name", "UnnamedColumn"))
                col_type = column.get("dataType", "string")
                columns[col_name] = col_type
            
            # Extract measures
            for measure in table.get("measures", []):
                measure_name = PBIXExtractor._clean_name(measure.get("name", "UnnamedMeasure"))
                expression = measure.get("expression", "")
                if expression:
                    metadata["measures"][measure_name] = {
                        "expression": expression.strip(),
                        "table": table_name,
                        "description": measure.get("description", ""),
                    }
            
            if columns:
                metadata["tables"][table_name] = {
                    "columns": columns,
                    "column_count": len(columns),
                }
        
        # Extract relationships
        relationships = model_data.get("relationships", [])
        if isinstance(relationships, list):
            for rel in relationships:
                from_table = PBIXExtractor._clean_name(rel.get("fromTable", ""))
                from_col = PBIXExtractor._clean_name(rel.get("fromColumn", ""))
                to_table = PBIXExtractor._clean_name(rel.get("toTable", ""))
                to_col = PBIXExtractor._clean_name(rel.get("toColumn", ""))
                
                if from_table and from_col and to_table and to_col:
                    metadata["relationships"].append({
                        "from_table": from_table,
                        "from_column": from_col,
                        "to_table": to_table,
                        "to_column": to_col,
                        "name": rel.get("name", f"{from_table}-{to_table}"),
                    })
        
        return metadata if metadata["tables"] else None

    @staticmethod
    def validate_pbix_file(file_path: str) -> tuple[bool, str]:
        """
        Validate that a file is a valid PBIX/PBIT file.
        
        Returns:
            (is_valid, message)
        """
        try:
            if not file_path.lower().endswith((".pbix", ".pbit")):
                return False, "File must be .pbix or .pbit"
            
            if not Path(file_path).exists():
                return False, "File does not exist"
            
            # Check if it's a valid ZIP file (PBIX is ZIP-based)
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                # Check for required files
                files = zip_ref.namelist()
                has_model = any(
                    f in files 
                    for f in ["DataModel.json", "model.json", "model.xml"]
                )
                
                if not has_model:
                    return False, "No valid Power BI model found in file"
                
                return True, "Valid PBIX/PBIT file"
        
        except zipfile.BadZipFile:
            return False, "Not a valid ZIP file (corrupted PBIX?)"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    @staticmethod
    def get_file_info(file_path: str) -> Dict[str, Any]:
        """Get basic info about the PBIX file."""
        try:
            file_size_mb = Path(file_path).stat().st_size / (1024 * 1024)
            
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                files = zip_ref.namelist()
                model_type = "unknown"
                
                if "DataModel.json" in files:
                    model_type = "Modern (JSON)"
                elif "model.json" in files:
                    model_type = "Standard (JSON)"
                elif any("model.xml" in f for f in files):
                    model_type = "Legacy (XML)"
            
            return {
                "size_mb": round(file_size_mb, 2),
                "model_type": model_type,
                "valid": True,
            }
        except Exception:
            return {"size_mb": 0, "model_type": "unknown", "valid": False}
