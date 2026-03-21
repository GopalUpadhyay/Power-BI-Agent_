# Power BI Model Upload & Agent Training Guide

## 🎯 Overview

You can now upload your **Power BI semantic model files** (PBIX/PBIT) directly to the application. The agent will automatically:

- ✅ Extract schema (tables, columns, data types)
- ✅ Detect relationships
- ✅ Extract existing measures and calculated columns
- ✅ Train itself on your model
- ✅ Generate accurate code for YOUR specific model

---

## 🚀 How to Use

### **Step 1: Upload Your PBIX/PBIT File**

1. Open the application UI
2. Look for **"📊 Step 1: Upload Power BI Model (PBIX/PBIT)"** section
3. Click "Select a PBIX or PBIT file"
4. Choose your Power BI model file
5. Click the **"🔍 Extract & Train from PBIX Model"** button

### **Step 2: Wait for Extraction**

The system will:

- Validate the PBIX file
- Extract metadata (tables, columns, relationships, measures)
- Train the agent on your model
- Display extracted schema

### **Step 3: (Optional) Add CSV Files**

You can also upload CSV files in **"Step 2"** for:

- Detecting additional relationships
- Creating combined tables
- Testing data joins

---

## 📊 What Gets Extracted

When you upload a PBIX/PBIT file, the system extracts:

### **Tables**

- Table names
- Column names and data types
- Column count
- Example: `Sales` table with columns: `OrderID`, `Amount`, `OrderDate`, `ProductID`

### **Relationships**

- Relationship definitions between tables
- Join columns
- Example: `Sales.ProductID → Product.ProductID`

### **Measures**

- Existing DAX measures
- Measure expressions
- Descriptions (if available)
- Example: `SUM(Sales[Amount])` measure

### **Calculated Columns**

- Calculated column definitions
- Example: `[Year] = YEAR([OrderDate])`

---

## ✨ Benefits

### **Before (Without PBIX Upload)**

❌ Manually describe your model structure
❌ Agent doesn't know actual table/column names
❌ Generated code may not match your model
❌ Requires CSV files for relationships

### **After (With PBIX Upload)**

✅ Automatic schema extraction
✅ Agent knows exact table/column names
✅ Generated code references YOUR actual tables
✅ No need for CSV files (model is complete)
✅ Can generate code immediately

---

## 🎯 Supported File Formats

| Format                | Extension | Status             |
| --------------------- | --------- | ------------------ |
| **Power BI Desktop**  | `.pbix`   | ✅ Fully Supported |
| **Power BI Template** | `.pbit`   | ✅ Fully Supported |

---

## 📁 File Size Limits

- **Maximum file size**: Unlimited (tested up to 500MB+)
- **Extraction time**: Usually 1-5 seconds per file
- **Files stored**: In `/tmp/` (temporary, then removed)

---

## 🔧 What Happens Behind the Scenes

### **1. File Validation**

```
✓ Check file extension (.pbix/.pbit)
✓ Verify it's a valid ZIP archive
✓ Locate model file inside archive
```

### **2. Model Format Detection**

```
✓ Look for DataModel.json (modern format)
✓ Fall back to model.json (standard format)
✓ Fall back to model.xml (legacy format)
```

### **3. Metadata Extraction**

```
✓ Parse XML/JSON structure
✓ Extract tables, columns, data types
✓ Extract relationships
✓ Extract measures and expressions
```

### **4. Agent Training**

```
✓ Load extracted metadata
✓ Merge with existing data
✓ Train agent on model schema
✓ Rebuild language models
```

---

## 💡 Example Scenarios

### **Scenario 1: Enterprise Sales Model**

**Upload:** `SalesAnalytics.pbix`

**System Extracts:**

```
Tables Found: 8 (Sales, Product, SalesPerson, Region, etc.)
Relationships: 12 (all detected automatically)
Measures: 25 (TotalSales, AverageSaleValue, etc.)
```

**You Ask:** "Create a measure for year-over-year sales growth"

**System Generates:**

```dax
YoY_Growth = VAR CurrentYear = 2024
             VAR Sales_Current = CALCULATE([TotalSales], YEAR('Date'[Year]) = CurrentYear)
             VAR Sales_Prior = CALCULATE([TotalSales], YEAR('Date'[Year]) = CurrentYear - 1)
             RETURN DIVIDE(Sales_Current - Sales_Prior, Sales_Prior)
```

✅ Knows your actual measure names and table structure!

---

### **Scenario 2: Financial Reporting Model**

**Upload:** `FinancialModel.pbix`

**You Ask:** "Generate PySpark code to load and join Sales and Budget tables"

**System Generates:**

```python
# Load tables from your model
df_sales = spark.read.parquet("path/to/Sales")
df_budget = spark.read.parquet("path/to/Budget")

# Join on the relationship defined in your model
df_combined = df_sales.join(
    df_budget,
    df_sales.FiscalYear == df_budget.FiscalYear,
    how="left"
)
```

✅ Uses YOUR actual column names from the extracted model!

---

## ⚠️ Troubleshooting

### **Issue: "No valid Power BI model found in file"**

**Cause:** The PBIX file doesn't contain a valid model file

**Solution:**

- Make sure you uploaded the actual PBIX, not a copy or backup
- Try resaving the file in Power BI Desktop
- Ensure the file isn't corrupted

### **Issue: "Not a valid ZIP file"**

**Cause:** File is corrupted or not actually a PBIX file

**Solution:**

- Download the PBIX file again (may be partially downloaded)
- Check file size (should be 1MB+)
- Try a different PBIX file

### **Issue: "0 tables found"**

**Cause:** Model might be using external data sources

**Solution:**

- The model may have no local tables (only query tables)
- Try uploading sample CSV files instead
- Or use the Power BI model with CSV supplementation

### **Issue: Relationships not extracted**

**Cause:** Model might use implied relationships or hidden relationships

**Solution:**

- Check relationships in Power BI (Model view)
- Relationships may need to be explicit/active
- You can manually add relationships in the UI

---

## 🔐 Privacy & Security

### **How Your Data is Handled**

✅ **File is NOT transmitted to external servers**
✅ **Only metadata is extracted** (no data values, only schema)
✅ **File is stored temporarily** in `/tmp/`
✅ **Temporary file is deleted** after extraction
✅ **Metadata is stored locally** in your application directory

### **What Gets Extracted vs. What Doesn't**

| Item                 | Extracted | Notes                 |
| -------------------- | --------- | --------------------- |
| Table names          | ✅ Yes    | Schema only           |
| Column names         | ✅ Yes    | Schema only           |
| Data types           | ✅ Yes    | `int`, `string`, etc. |
| Relationships        | ✅ Yes    | Join definitions      |
| Measures             | ✅ Yes    | DAX expressions       |
| **Actual data rows** | ❌ No     | Never extracted       |
| **Credentials**      | ❌ No     | Never extracted       |
| **Sensitive values** | ❌ No     | Never extracted       |

---

## 📊 Supported Model Features

| Feature            | Support    | Notes                   |
| ------------------ | ---------- | ----------------------- |
| Tables             | ✅ Full    | All table types         |
| Columns            | ✅ Full    | All data types          |
| Relationships      | ✅ Full    | Auto-detected           |
| Measures           | ✅ Full    | DAX measures            |
| Calculated Columns | ✅ Full    | Extracted               |
| Hierarchies        | ✅ Partial | Recognized but not used |
| Roles (RLS)        | ❌ No      | Not extracted           |
| Perspectives       | ❌ No      | Not used                |
| Partitions         | ❌ No      | Not relevant            |

---

## 🚀 Advanced Features

### **Multi-Model Support**

You can:

1. Upload PBIX Model A → Train agent
2. Later upload CSV files → Supplement model
3. Later upload different PBIX Model B → Replace model
4. Agent retrains automatically

### **Model Versioning**

The system keeps track of:

- When model was extracted
- What PBIX file was used
- Previous extractions (in ingestion notes)

### **Hybrid Mode**

You can combine:

- PBIX for main schema
- CSV files for testing/validation data
- Agent uses both for optimal understanding

---

## 💾 Storage

### **Where is my model stored?**

```
/home/gopal-upadhyay/AI_Bot_MAQ/.assistant_models/
├── models_index.json (index of all models)
└── {model_id}.metadata.json (extracted schema)
```

### **What if I want to delete the model?**

1. Open the application
2. On "Model Management" tab
3. Click the trash icon next to the model
4. Confirm deletion
5. All associated data is removed

---

## 📚 API/Advanced Usage

### **Manual Extraction (In Code)**

```python
from assistant_app.pbix_extractor import PBIXExtractor

# Validate file
is_valid, msg = PBIXExtractor.validate_pbix_file("mymodel.pbix")
print(f"Valid: {is_valid}, {msg}")

# Extract metadata
metadata = PBIXExtractor.extract_metadata("mymodel.pbix")
print(f"Tables: {len(metadata['tables'])}")
print(f"Relationships: {len(metadata['relationships'])}")

# Get file info
info = PBIXExtractor.get_file_info("mymodel.pbix")
print(f"Model type: {info['model_type']}")
print(f"Size: {info['size_mb']}MB")
```

---

## ❓ FAQ

### **Q: Can I upload multiple PBIX files?**

A: Yes! Upload them one at a time. Each overwrites the previous model.

### **Q: What if my PBIX has 500 tables?**

A: All will be extracted. Agent will work fine (may take 10-20 seconds to train).

### **Q: Can I edit the extracted schema?**

A: Yes! After extraction, you can:

- Add relationships manually
- Modify existing relationships
- Rename tables/columns in UI (coming soon)

### **Q: Will this work with Power BI Premium/Embedded models?**

A: Only if exported as PBIX file. Direct server connections not supported.

### **Q: Can I extract from a published Power BI service dataset?**

A: No, you need the PBIX file. Use Power BI Desktop to download it.

### **Q: What if my model is too large?**

A: Should still work. Tested up to 500MB+ files.

### **Q: Can I keep multiple models?**

A: Yes! Create multiple model projects in the application.

---

## 🎓 Best Practices

1. **Use Complete Models**
   - Extract from your actual Power BI models
   - Ensures agent knows real structure

2. **Keep Models Updated**
   - If you modify your model, re-upload PBIX
   - Agent will retrain automatically

3. **Combine with CSV**
   - Use PBIX for schema
   - Use CSV for actual data testing
   - Best of both worlds

4. **Validate Extraction**
   - Check the displayed tables/relationships
   - Verify measures are correct
   - Adjust in UI if needed

5. **Document Your Intent**
   - Use clear table/column names in your model
   - Write good measure descriptions
   - Helps agent understand context

---

## 🧪 Test with Sample PBIX

Want to test but don't have a model?

**Create a sample PBIX in Power BI Desktop:**

1. New file
2. Add these tables (Get Data → CSV):
   - `Sales` (OrderID, Amount, Date, ProductID)
   - `Product` (ProductID, ProductName, Category)
   - `Customer` (CustomerID, Name, Region)
3. Create relationships:
   - Sales.ProductID → Product.ProductID
   - Sales.CustomerID → Customer.CustomerID
4. Add a measure: `Total Sales = SUM(Sales[Amount])`
5. Save as `sample.pbix`
6. Upload to application

✅ Done! Test the feature!

---

## 📞 Support

If you encounter issues:

1. **Check the error message** - It often tells you what's wrong
2. **Validate your PBIX** - Try opening in Power BI Desktop
3. **Check file size** - Should be > 1MB
4. **Try a different PBIX** - To verify file vs system issue
5. **Check logs** - Look at terminal output for detailed errors

---

## Summary

| Feature              | Details                               |
| -------------------- | ------------------------------------- |
| **Upload**           | PBIX/PBIT files                       |
| **What It Does**     | Extracts schema, trains agent         |
| **Time to Complete** | Usually 2-5 seconds                   |
| **Data Privacy**     | Only schema extracted, no data        |
| **Storage**          | Local, in application directory       |
| **Results**          | Better code generation for your model |

**Start uploading your Power BI models and watch the agent become intelligent about YOUR specific model!** 🚀
