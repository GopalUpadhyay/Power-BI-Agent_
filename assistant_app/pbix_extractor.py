"""Power BI PBIX/PBIT file extractor - Extracts metadata from Power BI model files."""

import json
import re
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
    def _find_member(files: List[str], candidates: List[str]) -> Optional[str]:
        """Find a zip member by exact or suffix match (case-insensitive)."""
        lowered = {f.lower(): f for f in files}

        # Exact case-insensitive matches first.
        for cand in candidates:
            hit = lowered.get(cand.lower())
            if hit:
                return hit

        # Then suffix/path-insensitive matches.
        for f in files:
            f_lower = f.lower()
            for cand in candidates:
                cand_lower = cand.lower()
                if f_lower.endswith(cand_lower) or cand_lower in f_lower:
                    return f
        return None

    @staticmethod
    def _read_json_member(zip_ref: zipfile.ZipFile, member_name: str) -> Optional[Dict[str, Any]]:
        """Read a JSON model member with tolerant decoding."""
        try:
            raw = zip_ref.read(member_name)
        except Exception:
            return None

        for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "latin-1"):
            try:
                text = raw.decode(encoding)
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
        return None

    @staticmethod
    def _extract_from_report_layout(zip_ref: zipfile.ZipFile) -> Optional[Dict[str, Any]]:
        """Best-effort fallback for binary PBIX: infer schema from Report/Layout query refs.

        This does not recover full tabular metadata but can recover many table/column names
        used by report visuals, which is enough to train generation context.
        """
        try:
            files = zip_ref.namelist()
            layout_member = PBIXExtractor._find_member(
                files,
                ["Report/Layout", "report/layout", "Layout"],
            )
            if not layout_member:
                return None

            raw = zip_ref.read(layout_member)
            text = None
            for encoding in ("utf-16-le", "utf-8-sig", "utf-8", "latin-1"):
                try:
                    text = raw.decode(encoding, errors="ignore")
                    if text and len(text) > 50:
                        break
                except Exception:
                    continue

            if not text:
                return None

            # Query refs are often like "Sales[Amount]" or "'Date'[Year]".
            pattern = re.compile(r"'?(?P<table>[A-Za-z0-9_\- ]+)'?\[(?P<column>[^\]]+)\]")
            tables: Dict[str, Dict[str, Any]] = {}

            for match in pattern.finditer(text):
                table = PBIXExtractor._clean_name(match.group("table"))
                column = PBIXExtractor._clean_name(match.group("column"))
                if not table or not column:
                    continue
                if table.lower() in {"measures", "__measures"}:
                    continue

                entry = tables.setdefault(table, {"columns": {}, "column_count": 0})
                entry["columns"][column] = "string"

            for info in tables.values():
                info["column_count"] = len(info["columns"])

            if not tables:
                return None

            return {
                "tables": tables,
                "relationships": [],
                "measures": {},
                "calculated_columns": {},
            }
        except Exception as e:
            logger.warning(f"Fallback layout extraction failed: {str(e)}")
            return None

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
                files = zip_ref.namelist()

                # Prefer directly parseable JSON model artifacts first.
                json_candidates = [
                    "DataModel.json",
                    "model.json",
                    "DataModelSchema",
                    "DataModelSchema.json",
                    "model.bim",
                ]
                json_member = PBIXExtractor._find_member(files, json_candidates)
                if json_member:
                    model_data = PBIXExtractor._read_json_member(zip_ref, json_member)
                    if model_data:
                        parsed = PBIXExtractor._parse_model_json(model_data)
                        if parsed and parsed.get("tables"):
                            return parsed

                # Fallback to XML-based extraction when available.
                xml_result = PBIXExtractor._extract_from_xml(zip_ref)
                if xml_result and xml_result.get("tables"):
                    return xml_result

                # Fallback for binary DataModel PBIX: infer schema from report layout.
                layout_result = PBIXExtractor._extract_from_report_layout(zip_ref)
                if layout_result and layout_result.get("tables"):
                    notes = layout_result.setdefault("ingestion_notes", [])
                    notes.append(
                        "Recovered schema from Report/Layout (binary DataModel fallback). "
                        "Relationships and hidden fields may be incomplete."
                    )
                    return layout_result

                # Many PBIX files contain a binary DataModel that cannot be parsed without
                # external engines. At this point extraction is unsupported, but file is valid.
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

        # Handle both flat and nested model structures.
        model_root = model_data.get("model") if isinstance(model_data.get("model"), dict) else model_data

        # Extract tables from JSON structure
        tables = model_root.get("tables", [])
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
        relationships = model_root.get("relationships", [])
        if isinstance(relationships, list):
            for rel in relationships:
                from_table = PBIXExtractor._clean_name(rel.get("fromTable", ""))
                from_col = PBIXExtractor._clean_name(rel.get("fromColumn", ""))
                to_table = PBIXExtractor._clean_name(rel.get("toTable", ""))
                to_col = PBIXExtractor._clean_name(rel.get("toColumn", ""))

                # Some tabular models use nested endpoint objects.
                if not (from_table and from_col and to_table and to_col):
                    from_obj = rel.get("fromColumn") if isinstance(rel.get("fromColumn"), dict) else {}
                    to_obj = rel.get("toColumn") if isinstance(rel.get("toColumn"), dict) else {}
                    from_table = from_table or PBIXExtractor._clean_name(from_obj.get("table", ""))
                    from_col = from_col or PBIXExtractor._clean_name(from_obj.get("column", ""))
                    to_table = to_table or PBIXExtractor._clean_name(to_obj.get("table", ""))
                    to_col = to_col or PBIXExtractor._clean_name(to_obj.get("column", ""))
                
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
                files = zip_ref.namelist()
                lower_files = [f.lower() for f in files]

                # Common Power BI project signatures.
                has_powerbi_signature = any(
                    token in name
                    for name in lower_files
                    for token in [
                        "datamodel",
                        "datamodelschema",
                        "model.json",
                        "model.xml",
                        "model.bim",
                        "report/layout",
                        "datamashup",
                    ]
                )

                if not has_powerbi_signature:
                    return False, "File is a ZIP but does not contain recognizable Power BI artifacts"

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

                file_lowers = [f.lower() for f in files]

                if any(f.endswith("datamodel.json") for f in file_lowers):
                    model_type = "Modern (JSON)"
                elif any(f.endswith("model.json") for f in file_lowers):
                    model_type = "Standard (JSON)"
                elif any("datamodelschema" in f for f in file_lowers) or any(f.endswith("model.bim") for f in file_lowers):
                    model_type = "Tabular (Schema JSON/BIM)"
                elif any("model.xml" in f for f in file_lowers):
                    model_type = "Legacy (XML)"
                elif any(f.endswith("datamodel") for f in file_lowers):
                    model_type = "Binary DataModel (limited extraction)"
            
            return {
                "size_mb": round(file_size_mb, 2),
                "model_type": model_type,
                "valid": True,
            }
        except Exception:
            return {"size_mb": 0, "model_type": "unknown", "valid": False}
