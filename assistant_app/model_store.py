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
