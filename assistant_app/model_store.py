import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class ModelStore:
    """Stores uploaded model metadata and files locally for testing."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or (Path(__file__).resolve().parents[1] / ".assistant_models")
        self.uploads_root = self.root / "uploads"
        self.index_path = self.root / "models_index.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.uploads_root.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._save_index([])

    def _load_index(self) -> List[Dict[str, Any]]:
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return []

    def _save_index(self, models: List[Dict[str, Any]]) -> None:
        self.index_path.write_text(json.dumps(models, indent=2), encoding="utf-8")

    @staticmethod
    def _slug(value: str) -> str:
        text = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return text or "model"

    def list_models(self) -> List[Dict[str, Any]]:
        models = self._load_index()
        return sorted(models, key=lambda m: m.get("created_at", ""), reverse=True)

    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        for model in self._load_index():
            if model.get("id") == model_id:
                return model
        return None

    def create_model(self, name: str, description: str = "") -> Dict[str, Any]:
        now = datetime.now().isoformat()
        model_id = f"{self._slug(name)}-{now.replace(':', '').replace('-', '').replace('.', '')}"
        metadata_path = self.root / f"{model_id}.metadata.json"

        default_metadata = {
            "tables": {
                "Sales": {
                    "columns": {
                        "Sales": "decimal(18,2)",
                        "OrderDate": "date",
                        "ProductKey": "bigint",
                    },
                    "column_count": 3,
                }
            },
            "relationships": [],
            "measures": {},
            "calculated_columns": {},
            "calculated_tables": {},
            "ingestion_notes": ["Default starter metadata"],
        }
        metadata_path.write_text(json.dumps(default_metadata, indent=2), encoding="utf-8")

        model = {
            "id": model_id,
            "name": name.strip() or "Untitled Model",
            "description": description.strip(),
            "created_at": now,
            "metadata_path": str(metadata_path),
            "uploads": [],
        }

        models = self._load_index()
        models.append(model)
        self._save_index(models)
        return model

    def load_metadata(self, model_id: str) -> Dict[str, Any]:
        model = self.get_model(model_id)
        if not model:
            return {}
        metadata_path = Path(model["metadata_path"])
        if not metadata_path.exists():
            return {}
        try:
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_metadata(self, model_id: str, metadata: Dict[str, Any]) -> None:
        model = self.get_model(model_id)
        if not model:
            return
        metadata_path = Path(model["metadata_path"])
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    def _upsert_model(self, model_id: str, update: Dict[str, Any]) -> None:
        models = self._load_index()
        for idx, model in enumerate(models):
            if model.get("id") == model_id:
                merged = dict(model)
                merged.update(update)
                models[idx] = merged
                self._save_index(models)
                return

    def add_upload(self, model_id: str, filename: str, data: bytes) -> Optional[str]:
        model = self.get_model(model_id)
        if not model:
            return None

        model_upload_dir = self.uploads_root / model_id
        model_upload_dir.mkdir(parents=True, exist_ok=True)

        safe_name = Path(filename).name
        target = model_upload_dir / safe_name
        target.write_bytes(data)

        uploads = list(model.get("uploads", []))
        uploads.append(
            {
                "filename": safe_name,
                "stored_path": str(target),
                "uploaded_at": datetime.now().isoformat(),
            }
        )
        self._upsert_model(model_id, {"uploads": uploads})

        self._ingest_file_into_metadata(model_id, target)
        return str(target)

    def _ingest_file_into_metadata(self, model_id: str, file_path: Path) -> None:
        metadata = self.load_metadata(model_id)
        if not metadata:
            metadata = {
                "tables": {},
                "relationships": [],
                "measures": {},
                "calculated_columns": {},
                "calculated_tables": {},
                "ingestion_notes": [],
            }

        suffix = file_path.suffix.lower()
        notes = metadata.setdefault("ingestion_notes", [])

        if suffix == ".json":
            try:
                parsed = json.loads(file_path.read_text(encoding="utf-8"))
                merged = self._merge_metadata(metadata, parsed)
                notes.append(f"Learned metadata from JSON: {file_path.name}")
                self.save_metadata(model_id, merged)
                return
            except Exception:
                notes.append(f"Could not parse JSON metadata file: {file_path.name}")
        elif suffix in {".csv", ".tsv"}:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            first_line = text.splitlines()[0] if text.splitlines() else ""
            delimiter = "\t" if suffix == ".tsv" else ","
            columns = [c.strip() for c in first_line.split(delimiter) if c.strip()]
            if columns:
                table_name = file_path.stem
                metadata.setdefault("tables", {})[table_name] = {
                    "columns": {col: "string" for col in columns},
                    "column_count": len(columns),
                }
                notes.append(f"Learned table schema from CSV/TSV: {file_path.name}")
        elif suffix in {".txt", ".md"}:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            matches = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\[([A-Za-z_][A-Za-z0-9_]*)\]", text)
            for table_name, col_name in matches:
                metadata.setdefault("tables", {}).setdefault(table_name, {"columns": {}, "column_count": 0})
                metadata["tables"][table_name]["columns"][col_name] = "string"
                metadata["tables"][table_name]["column_count"] = len(metadata["tables"][table_name]["columns"])
            notes.append(f"Learned references from text file: {file_path.name}")
        elif suffix in {".pbix"}:
            notes.append(f"PBIX uploaded: {file_path.name} (stored locally; direct parsing not implemented yet)")
        elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            notes.append(f"Screenshot uploaded: {file_path.name} (stored locally; OCR parsing not implemented yet)")
        else:
            notes.append(f"Uploaded file stored: {file_path.name}")

        self.save_metadata(model_id, metadata)
        
        # Auto-detect relationships based on column names
        self._detect_relationships(model_id)

    def _merge_metadata(self, base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(base)
        result.setdefault("tables", {})
        result.setdefault("relationships", [])
        result.setdefault("measures", {})
        result.setdefault("calculated_columns", {})
        result.setdefault("calculated_tables", {})
        result.setdefault("ingestion_notes", [])

        incoming_tables = incoming.get("tables", {}) if isinstance(incoming.get("tables", {}), dict) else {}
        for table_name, table_info in incoming_tables.items():
            if not isinstance(table_info, dict):
                continue
            cols = table_info.get("columns", {})
            if isinstance(cols, list):
                cols = {str(c): "string" for c in cols}
            if not isinstance(cols, dict):
                cols = {}
            result["tables"][table_name] = {
                "columns": {str(k): str(v) for k, v in cols.items()},
                "column_count": len(cols),
            }

        if isinstance(incoming.get("relationships", []), list):
            result["relationships"].extend(incoming.get("relationships", []))

        if isinstance(incoming.get("measures", {}), dict):
            result["measures"].update(incoming.get("measures", {}))

        return result

    def _detect_relationships(self, model_id: str) -> None:
        """Auto-detect relationships with confidence scoring to avoid false positives."""
        metadata = self.load_metadata(model_id)
        if not metadata or "tables" not in metadata:
            return
        
        tables = metadata.get("tables", {})
        existing_rels = set()
        
        # Track existing relationships to avoid duplicates
        for rel in metadata.get("relationships", []):
            key = (
                rel.get("from_table", ""),
                rel.get("from_column", ""),
                rel.get("to_table", ""),
                rel.get("to_column", ""),
            )
            existing_rels.add(key)
        
        # Get all table names and their columns
        table_names = list(tables.keys())
        
        # Look for matching columns between tables (potential foreign keys)
        detected_rels = []
        for i, table1 in enumerate(table_names):
            cols1 = set(tables[table1].get("columns", {}).keys())
            
            for j, table2 in enumerate(table_names):
                if i >= j:  # Avoid duplicates and self-relationships
                    continue
                
                cols2 = set(tables[table2].get("columns", {}).keys())
                
                # Find matching column names
                matching_cols = cols1 & cols2
                for col in matching_cols:
                    # Check if column looks like a key
                    is_key_like = self._is_likely_key_column(col)
                    
                    if is_key_like:
                        # Compute confidence score for this relationship
                        confidence = self._compute_relationship_confidence(col, table1, table2)
                        
                        # Only create relationship if confidence is high enough
                        if confidence >= 0.6:
                            rel_key1 = (table1, col, table2, col)
                            
                            if rel_key1 not in existing_rels:
                                detected_rels.append({
                                    "name": f"{table1}_{table2}_{col}",
                                    "from_table": table1,
                                    "from_column": col,
                                    "to_table": table2,
                                    "to_column": col,
                                    "confidence": round(confidence, 2),
                                    "validated": confidence >= 0.9,
                                })
                                existing_rels.add(rel_key1)
        
        # Update metadata with detected relationships
        if detected_rels:
            metadata.setdefault("relationships", []).extend(detected_rels)
            notes = metadata.get("ingestion_notes", [])
            high_conf = len([r for r in detected_rels if r.get("confidence", 0) >= 0.9])
            low_conf = len(detected_rels) - high_conf
            msg = f"Auto-detected {len(detected_rels)} relationship(s): {high_conf} high-confidence, {low_conf} need review"
            notes.append(msg)
            self.save_metadata(model_id, metadata)

    @staticmethod
    def _is_likely_key_column(col_name: str) -> bool:
        """Check if a column name looks like a primary or foreign key."""
        col_lower = col_name.lower()
        
        # Common key patterns
        key_patterns = [
            "id",            # *ID, ID*
            "key",           # *Key, Key*
            "code",          # *Code
            "identifier",    # *Identifier
        ]
        
        for pattern in key_patterns:
            if pattern in col_lower:
                return True
        
        return False

    def _compute_relationship_confidence(self, column_name: str, table1: str, table2: str) -> float:
        """Compute confidence score for a potential relationship. Range: 0.0 to 1.0."""
        score = 0.7  # Base score for matching columns
        
        col_lower = column_name.lower()
        t1_lower = table1.lower()
        t2_lower = table2.lower()
        
        # Bonus: Column name matches one of the table names (e.g., CustomerID + Customers)
        if col_lower.startswith(t1_lower.rstrip('s')) or col_lower.startswith(t2_lower.rstrip('s')):
            score += 0.2
        
        # Penalty: Generic column names (ID, Key, Code alone are too generic)
        generic_patterns = [r'\bid\b', r'\bkey\b', r'\bcode\b']
        if any(re.search(pattern, col_lower) for pattern in generic_patterns):
            if len(col_lower) <= 4:  # "ID", "Key" alone
                score -= 0.3  # Heavily penalize
            elif not (t1_lower in col_lower or t2_lower in col_lower):
                score -= 0.15  # Slightly penalize
        
        return min(max(score, 0.0), 1.0)  # Clamp to 0-1 range

    def identify_relationships(self, model_id: str) -> Dict[str, Any]:
        """Public method to identify and return relationships for a model.
        
        Args:
            model_id: The ID of the model to analyze
            
        Returns:
            Dictionary with relationship details and status
        """
        try:
            # Trigger relationship detection
            self._detect_relationships(model_id)
            
            # Load the updated metadata with detected relationships
            metadata = self.load_metadata(model_id)
            
            # Extract relationships
            relationships = metadata.get("relationships", [])
            notes = metadata.get("ingestion_notes", [])
            
            # Create summary
            high_conf = len([r for r in relationships if r.get("confidence", 0) >= 0.9])
            low_conf = len([r for r in relationships if r.get("confidence", 0) < 0.9])
            
            return {
                "success": True,
                "model_id": model_id,
                "relationships": relationships,
                "total_detected": len(relationships),
                "high_confidence": high_conf,
                "low_confidence": low_conf,
                "notes": notes,
                "message": f"Detected {len(relationships)} relationship(s): {high_conf} high-confidence, {low_conf} need review"
            }
        except Exception as e:
            return {
                "success": False,
                "model_id": model_id,
                "error": str(e),
                "message": f"Error identifying relationships: {str(e)}"
            }

    def delete_model(self, model_id: str) -> bool:
        """Delete a model and all its associated files.
        
        Args:
            model_id: The ID of the model to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            model = self.get_model(model_id)
            if not model:
                return False
            
            # Delete metadata file
            metadata_path = Path(model["metadata_path"])
            if metadata_path.exists():
                metadata_path.unlink()
            
            # Delete uploads directory
            model_upload_dir = self.uploads_root / model_id
            if model_upload_dir.exists():
                import shutil
                shutil.rmtree(model_upload_dir)
            
            # Remove from index
            models = self._load_index()
            models = [m for m in models if m.get("id") != model_id]
            self._save_index(models)
            
            return True
        except Exception:
            return False

    def delete_upload(self, model_id: str, filename: str) -> bool:
        """Delete an uploaded file from a model.
        
        Args:
            model_id: The ID of the model
            filename: The name of the file to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            model = self.get_model(model_id)
            if not model:
                return False
            
            # Find and delete the file
            uploads = list(model.get("uploads", []))
            for upload in uploads:
                if upload.get("filename") == filename:
                    stored_path = Path(upload["stored_path"])
                    if stored_path.exists():
                        stored_path.unlink()
                    uploads.remove(upload)
                    break
            
            # Update model
            self._upsert_model(model_id, {"uploads": uploads})
            
            # Reload metadata to recalculate tables
            metadata = self.load_metadata(model_id)
            self.save_metadata(model_id, metadata)
            
            return True
        except Exception:
            return False

    def delete_relationship(self, model_id: str, relationship_name: str) -> bool:
        """Delete a relationship from a model.
        
        Args:
            model_id: The ID of the model
            relationship_name: The name of the relationship to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            metadata = self.load_metadata(model_id)
            if not metadata:
                return False
            
            relationships = metadata.get("relationships", [])
            original_count = len(relationships)
            
            # Filter out the relationship
            relationships = [r for r in relationships if r.get("name") != relationship_name]
            
            if len(relationships) == original_count:
                return False  # Nothing was deleted
            
            metadata["relationships"] = relationships
            notes = metadata.setdefault("ingestion_notes", [])
            notes.append(f"User deleted relationship: {relationship_name}")
            
            self.save_metadata(model_id, metadata)
            return True
        except Exception:
            return False
