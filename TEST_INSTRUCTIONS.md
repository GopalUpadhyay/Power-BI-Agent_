# Testing the Metadata Training Fix

## What Was Fixed

The universal assistant in the **Generate** tab was not using the model metadata from uploaded CSV files. It was using an empty metadata store, so generated code was generic and didn't reference your actual tables.

### Root Cause

- `_build_universal_assistant()` was creating an empty `MetadataStore()`
- The metadata from uploaded CSVs (in Model Hub tab) was stored separately
- The universal assistant had no access to it

### Solution

- Modified `MetadataStore` to accept optional metadata parameter
- Updated `_build_universal_assistant()` to accept and pass metadata
- Updated all calls in the UI to pass the active model's metadata

## How to Test

### 1. Start the Streamlit App

```bash
python run_ui.py
```

### 2. Create a Model

- Go to **Model Hub** tab
- Click "New Model"
- Enter name: `Customer Orders`
- Description: `Sample orders and customer data`
- Click "Create"

### 3. Upload Sample Data

- Use the file uploader to upload these CSVs:

**orders.csv**

```
OrderID,CustomerID,OrderDate,TotalAmount
1,101,2024-01-15,250.50
2,102,2024-01-16,180.25
3,101,2024-01-17,520.00
```

**customers.csv**

```
CustomerID,CustomerName,City,Country
101,Alice Johnson,New York,USA
102,Bob Smith,Los Angeles,USA
```

- Click "Store Uploaded Files"
- You should see:
  - ✅ Detected 1 relationship (orders.CustomerID → customers.CustomerID)
  - ✅ Learned from CSV files
  - ✅ Auto-training applied

### 4. Test the Generate Tab

- Go to **Generate** tab
- Under "Item Type": select `table`
- Under "Output Language": select `PySpark`
- Under "Where will this be used?": select `Notebook`
- Description: `Create total order amount by customer`
- Click "Generate"

### Expected Results

✅ Should generate **PySpark code** that:

- References the `orders` table
- References the `customers` table
- Uses the `TotalAmount` column
- Uses the relationship between tables

**Before the fix**: Code would be generic, not referencing your tables at all
**After the fix**: Code should reference your actual 'orders' and 'customers' tables

### 5. Verify Relationships Were Detected

- In Model Hub tab, the relationship grid should show:
  | From | To |
  | --- | --- |
  | orders.CustomerID | customers.CustomerID |

## Technical Details

### Files Modified

1. **assistant_app/fabric_universal.py** (line 55-70)
   - `MetadataStore.__init__()` now accepts optional metadata

2. **assistant_app/ui.py** (6 locations)
   - `_build_universal_assistant()` now accepts metadata parameter
   - All 6 calls now pass metadata from the active model or preserved metadata

### Verification Commands

```bash
# Check syntax
python -m py_compile assistant_app/fabric_universal.py assistant_app/ui.py

# Test metadata passing
python << 'EOF'
from assistant_app.fabric_universal import MetadataStore
test_metadata = {
    "tables": {"Orders": {...}, "Customers": {...}},
    "relationships": [...]
}
store = MetadataStore(metadata=test_metadata)
print("Tables:", list(store.metadata['tables'].keys()))
# Output: Tables: ['Orders', 'Customers']
EOF
```

## If Something Still Doesn't Work

1. **Check the Model Hub** - Verify CSVs were uploaded and relationships were detected
2. **Check the metadata file** - Look at `.assistant_models/<model-id>.metadata.json`
3. **Restart the UI** - `python run_ui.py` (clears any stale session state)
4. **Check logs** - Both Model Hub and Generate tab console for error messages
