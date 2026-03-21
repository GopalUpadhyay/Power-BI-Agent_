# 🐛 CORPORATE CLIENT ACCEPTANCE REPORT

## Issues & Bugs Found During Real-World Testing

**Date:** March 20, 2026  
**Testing Level:** Corporate/Enterprise Production Use  
**Tester Role:** BI Analyst, Data Engineer, Business User

---

## CRITICAL ISSUES (Block Production Use)

### 🔴 ISSUE #1: Empty Model Generates Hallucinated Code

**Severity:** CRITICAL  
**Category:** Code Generation  
**Stakeholder Impact:** Users get non-functional code, wastes analyst time

**Description:**

- When a model is created but has NO tables uploaded yet, the assistant generates DAX using SAMPLE hardcoded tables (Sales, Product, Region, Salesperson)
- Users paste this code into their Power BI semantic model and it fails because those tables don't exist
- No warning or error message indicates the model is empty

**Reproduction:**

```
1. Create new model in Model Hub
2. Skip uploading any files
3. Go to Generate tab
4. Request: "Create total sales measure"
5. Output uses tables: Sales[SalesAmount], Product[ProductName], etc.
6. User's actual model has ZERO tables → pasted code breaks immediately
```

**Root Cause:** `core.py` - `_pick_trained_schema_targets()` uses fallback sample tables when metadata is empty, no validation that tables exist in actual model

**User Comment:**

> "I created a model and tried to generate a sales measure. Copied the code into Power BI and got 'Table 'Sales' not found.' Wasted 30 minutes debugging only to realize the assistant was using sample data. This is unacceptable for a production tool."

**Fix Needed:**

- Validate that model has at least 1 table before generation
- Show explicit warning: "❌ Model is empty. Please upload CSV files first."
- Block generation if tables = 0

---

### 🔴 ISSUE #2: No Validation of Cross-Model Table References

**Severity:** CRITICAL  
**Category:** Data Integrity  
**Stakeholder Impact:** Users generate code for wrong models, causes data errors

**Description:**

- User can have multiple models (Model A: Sales data) and (Model B: HR data)
- Switch to Model B (empty or HR-focused) but Generate tab still might reference tables from Model A
- No warning or validation that referenced table exists in CURRENT selected model
- Session state doesn't properly sync model context between tabs

**Reproduction:**

```
1. Create Model A with [SalesAmount] column from sales.csv
2. Create Model B with [EmployeeCount] column from hr.csv
3. Switch active model to Model B
4. Request: "Create total sales measure"
5. Generated code might include Sales[SalesAmount] - which doesn't exist in Model B
```

**Root Cause:** Session state `active_model_id` not consistently passed to generation context; universal_assistant rebuilt but metadata not always synchronized immediately

**User Comment:**

> "I was switching between sales and HR models. Generated a measure in the HR model tab, but it referenced Sales tables. Code doesn't work. Why doesn't the system know which model I'm using?"

---

### 🔴 ISSUE #3: No File Format Validation or Error Handling

**Severity:** CRITICAL  
**Category:** Data Ingestion  
**Stakeholder Impact:** App crashes or silently fails, data corruption

**Description:**

- Upload file format validation is minimal
- If CSV is malformed (missing headers, wrong delimiters), app ingests invalid schema
- No error message to user; metadata silently contains garbage
- Generated code then uses invalid column names

**Reproduction:**

```
1. Create CSV with broken formatting:
   ProductID,ProductName|Price    ← wrong delimiter
   1,Widget|9.99
2. Upload to model
3. App accepts it silently
4. Metadata shows columns: "ProductName|Price" (one column, not two)
5. Generated code can't find [Price] column
```

**Root Cause:** `model_store.py` - `_ingest_file_into_metadata()` does minimal CSV validation on first line

---

### 🔴 ISSUE #4: Relationship Detection False Positives

**Severity:** CRITICAL  
**Category:** Schema Modeling  
**Stakeholder Impact:** Users rely on auto-detected relationships, get wrong joins

**Description:**

- Relationship auto-detection uses simple naming heuristics (CustomerID → CustomerID)
- False positives: two tables both have "ID" column assumed to be a relationship
- No validation of cardinality or direction
- Users export relationships and use them in Power BI incorrectly

**Example False Positive:**

```
Table A: [CustomerID] (sales dimension)
Table B: [CustomerID] (customers fact)
- Both named CustomerID
- Auto-detector creates 2-way relationship
- But one is actually a fact table, should be many-to-one only
```

**User Comment:**

> "System auto-detected 15 relationships from our 8-table model. 3 of them were wrong duplicates. Had to manually edit all of them. Auto-detection is more work than it saves."

---

## HIGH SEVERITY ISSUES (Impact Core Functionality)

### 🟠 ISSUE #5: Output Type Mismatches Not Always Corrected

**Severity:** HIGH  
**Category:** Multi-Language Generation  
**Stakeholder Impact:** Users request PySpark but get DAX, code can't be pasted

**Description:**

- When user selects "Notebook" (PySpark target), requests sometimes return DAX instead
- The auto-correction from enforcement only works some workflows
- Complex requests bypass the `_enforce_target_output_type()` check
- No user-visible indication that output was auto-corrected or failed to match

**Reproduction:**

```
1. Go to Generate tab
2. Set: Output Language = PySpark, Target = Notebook
3. Request: "Create customer analysis by segment grouping"
4. Result type = DAX (should be PySpark)
5. User can't paste into notebook
```

**User Comment:**

> "I asked for PySpark and got DAX. The paste-ready code doesn't even work in Fabric notebooks. Why is this happening?"

---

### 🟠 ISSUE #6: Model Hub Upload Workflow Is Unintuitive

**Severity:** HIGH  
**Category:** UX/Usability  
**Stakeholder Impact:** Users don't know how to provide model data

**Description:**

- File upload button says "Upload PBIX / screenshot / metadata files"
- But PBIX extraction is incomplete, screenshots aren't processed, metadata parsing is fragile
- Best way (CSV files) is not highlighted
- Users upload PBIX expecting magic extraction, get only partial table detection
- No step-by-step guidance on what to upload and why

**User Comment:**

> "I uploaded a PBIX file but only 3 of my 12 tables showed up. The system doesn't work. I don't understand what files I should upload."

**Issues:**

- PBIX parsing incomplete (extracts basic tables but misses measures, hierarchies, RLS)
- Screenshots not actually processed
- JSON metadata format not documented
- CSV is best approach but not obvious to new users

---

### 🟠 ISSUE #7: Paste-Ready Output Quality Varies Widely

**Severity:** HIGH  
**Category:** Usability  
**Stakeholder Impact:** Users can't reliably copy-paste code

**Description:**

- `paste_ready_query` field sometimes has correct format, sometimes is identical to raw code
- No consistent pattern: sometimes includes `[MeasureName] = Expression`, sometimes doesn't
- DAX output should be formatted as: `Name = Expression` but isn't always
- SQL and PySpark have different formatting expectations not met

**Examples of inconsistency:**

```
DAX: "TOPN(10, Sales)" ← Missing measure assignment
SQL: "SELECT * FROM table JOIN..." → Should be wrapped in "CREATE VIEW"
PySpark: "df.groupBy(...)" ← Missing display() or .show() for notebook
```

**User Comment:**

> "Copy-paste functionality is broken. Sometimes I get the expression, sometimes the full assignment, sometimes Python code I can't use. Inconsistent."

---

### 🟠 ISSUE #8: No Session Persistence Between Page Refreshes

**Severity:** HIGH  
**Category:** Stability  
**Stakeholder Impact:** Users lose work when browser updates, frustrating experience

**Description:**

- Streamlit refreshes entire page on any interaction
- Session state can be lost if network hiccup or browser back button
- Created items disappear from Created Items tab until registry is manually reloaded
- Relationship editing results are lost on refresh
- No save confirmation or "unsaved changes" warning

**Reproduction:**

```
1. Upload CSV and auto-detect relationships
2. Edit relationships in grid (add/remove/modify)
3. Click another button (triggers st.rerun())
4. All edits gone if not explicitly saved
5. Users don't realize they need to click "Save Relationship Edits"
```

**User Comment:**

> "I spent 10 minutes editing relationships, clicked another button, and all my edits disappeared. Streamlit keeps refreshing the page. Why is there no save??"

---

### 🟠 ISSUE #9: Error Messages Are Not Actionable

**Severity:** HIGH  
**Category:** User Experience  
**Stakeholder Impact:** Users can't fix problems on their own

**Description:**

- Validation errors are cryptic: "Expression contains invalid syntax" (but which line?)
- No suggestion for how to fix: "Column [NonExistent] not found" (offer correct names?)
- Internal error messages shown to users: `TypeError: 'NoneType' object has no attribute 'get'`
- No FAQ or help button for common issues
- Generated code explanation sometimes contradicts the actual code

**Example Error:**

```
❌ Validation Error: "Cannot aggregate non-additive column"
User thinks: "But I want to aggregate! How do I fix this?"
Better: "❌ Column [ProductID] is non-additive (ID field).
         Try aggregating [SalesAmount] or [Quantity] instead.
         (Available numeric columns: SalesAmount, Quantity, Discount)"
```

---

### 🟠 ISSUE #10: Performance Issues on Large Models

**Severity:** HIGH  
**Category:** Performance  
**Stakeholder Impact:** 15+ table models become slow/unusable

**Description:**

- No pagination or lazy loading for large models
- Relationship grid renders ALL relationships at once (100+ rows = laggy)
- Schema view displays all columns for all tables without filtering or search
- Code generation prompt becomes huge on large models, slow LLM response
- Model switching is slow (rebuilds everything)

**Reproduction:**

```
1. Upload data model with 50+ tables
2. Go to Schema tab
3. Render all tables, all columns → visible lag
4. Go to Model Hub, try to edit relationships in grid → very slow
5. Generate measure → takes 30+ seconds (prompt is huge)
```

**User Comment:**

> "Our model has 40 tables and this tool is unusably slow. The UI lags, generating code takes forever. This should be optimized for enterprise models."

---

## MEDIUM SEVERITY ISSUES (Annoying but Workable)

### 🟡 ISSUE #11: Duplicate Measure Detection Doesn't Work Across Models

**Severity:** MEDIUM  
**Category:** Data Quality  
**Stakeholder Impact:** Users accidentally create duplicate measures

**Description:**

- Duplicate detection only checks within current model's registry
- If user switches models with Model A [TotalSales], creates it in Model B, then switches back to Model A, creates again → no duplicate warning
- Suggestion system doesn't show close semantic matches only exact name matches

---

### 🟡 ISSUE #12: Column Type Information Is Not Used by Generator

**Severity:** MEDIUM  
**Category:** Code Generation Quality  
**Stakeholder Impact:** Generated code uses wrong aggregation functions

**Description:**

- Metadata stores column types (int, string, decimal, datetime)
- But generator ignores this and makes assumptions
- Creates SUM() on string columns, or COUNT() on decimal columns
- Should use type information to validate and suggest correct functions

---

### 🟡 ISSUE #13: Training Profile Data Is Not Visible/Actionable

**Severity:** MEDIUM  
**Category:** Model Training  
**Stakeholder Impact:** Users don't know if model is trained; can't debug

**Description:**

- Training completes with message "Training completed at [time]"
- But doesn't show what was learned: preferred table, value column, date column
- User can't verify training worked correctly
- No way to see the training profile details in UI

---

### 🟡 ISSUE #14: Relationships Grid Doesn't Validate Table/Column Existence

**Severity:** MEDIUM  
**Category:** Data Integrity  
**Stakeholder Impact:** Users create relationships to non-existent tables

**Description:**

- Relationship edit grid allows manual entry without validation
- User can type in non-existent table names
- System accepts it, metadata corrupts
- No dropdown or validation on table/column names

**Reproduction:**

```
1. Edit relationships grid
2. Change table name from "Orders" to "Ordres" (typo)
3. Click save
4. Silently saves invalid relationship
5. Generated code later fails because table doesn't exist
```

---

### 🟡 ISSUE #15: DAX vs PySpark Naming Conventions Not Respected

**Severity:** MEDIUM  
**Category:** Code Quality  
**Stakeholder Impact:** Generated code doesn't follow enterprise standards

**Description:**

- Generated measure might be "total_sales" (snake_case, SQL style)
- But DAX convention is "TotalSales" (PascalCase, C# style)
- Generated Python is "TotalSales" (should be "total_sales")
- SQL is "TOTAL_SALES" (should match existing conventions)
- Users have to rename everything manually

---

### 🟡 ISSUE #16: No Option to Use Existing Measures in New Measures

**Severity:** MEDIUM  
**Category:** Code Generation  
**Stakeholder Impact:** Code duplication, maintenance nightmare

**Description:**

- User has existing measure [TotalSales]
- Requests: "Create average sales"
- Generated code does: `AVERAGE(FactSales[SalesAmount])`
- Better would be: `AVERAGE([TotalSales])`
- But system doesn't discover or suggest reusing existing measures

---

## LOW SEVERITY ISSUES (Polish/Nice-to-Have)

### 🟢 ISSUE #17: Export Format Options Missing

**Severity:** LOW  
**Category:** Feature Request  
**Stakeholder Impact:** Some users may need different export formats

**Description:**

- Export tab only supports CSV of created items
- No export as DAX script (.dax)
- No export as Power BI XML backup
- No export as SQL migration script
- Users have to manually format code for their target platform

---

### 🟢 ISSUE #18: No Search/Filter in Schema View

**Severity:** LOW  
**Category:** Usability  
**Stakeholder Impact:** Hard to find specific tables/columns in large models

**Description:**

- Schema tab shows all tables and relationships
- No search box to filter by table name
- No column search to find specific data types
- Scrolling through 50+ tables is tedious

---

### 🟢 ISSUE #19: Explanation Text Sometimes Contradicts Generated Code

**Severity:** LOW  
**Category:** Clarity  
**Stakeholder Impact:** Users confused by mismatch

**Description:**

```
Generated Code: "TOPN(10, FactSales, SUM(SalesAmount))"
Explanation: "This creates a top 10 rank by product category"
→ Code doesn't match explanation
```

---

### 🟢 ISSUE #20: No Rate Limiting on API Calls

**Severity:** LOW  
**Category:** Cost Control  
**Stakeholder Impact:** Accidental high OpenAI bill if user spams generation

**Description:**

- No limit on how many generations per minute/hour
- User could accidentally hammer API repeatedly
- No cost estimate or warning
- Enterprise clients need spend controls

---

## USABILITY & UX ISSUES

### 📋 ISSUE #21: Unclear What "Conditions" Field Does

**Severity:** MEDIUM  
**Category:** UX  
**Impact:** New users don't know how to use filter/condition field

**Example Users Try:**

- "where Sales > 1000" ← Works only in some contexts
- "quarterly" ← Interpreted as filter, but meant as grouping
- "Customer segment = Premium" ← Works sometimes, sometimes causes errors

**Fix Needed:** Placeholder text showing exact syntax with examples

---

### 📋 ISSUE #22: No Clear Indication of "Fallback Mode"

**Severity:** MEDIUM  
**Category:** Transparency  
**Impact:** User doesn't realize they're not getting LLM-powered generation

**Description:**

- When OpenAI API key missing or quota exceeded, falls back to rule-based generation
- No UI indicator: "⚠️ Running in fallback mode (no API key configured)"
- Generated code is noticeably worse but users think it's the system's best effort
- Users blame the tool instead of checking configuration

---

### 📋 ISSUE #23: Model Card Design Is Poor

**Severity:** LOW  
**Category:** UX  
**Impact:** Information overload, overwhelming for new users

**Description:**

- Too many options on one screen
- Auto-train checkbox is confusing (auto-train what exactly?)
- Status metrics (Total Items, Generated, Flags, Tables) not useful initially
- New user doesn't know where to start

**Suggested Layout:**

1. **Getting Started** (collapsible section)
   - "Upload CSV files or PBIX"
   - "Auto-detect schema"
2. **Models** (main content)
   - List of models with action buttons
3. **Advanced** (collapsible)
   - Auto-train, refresh, etc.

---

## API/INTEGRATION ISSUES

### 🔌 ISSUE #24: No API Endpoint for Programmatic Access

**Severity:** LOW  
**Category:** Enterprise Feature  
**Impact:** Can't integrate with CI/CD, Enterprise Apps, Power Automate

**Description:**

- All features locked behind Streamlit UI
- No REST API or Python SDK for DAX generation
- Can't call from Power Automate to auto-generate measures
- Can't integrate into Power BI Deployment Pipelines

---

### 🔌 ISSUE #25: Metadata Format Not Documented

**Severity:** MEDIUM  
**Category:** Integration  
**Impact:** Users can't create/edit metadata JSON files manually

**Description:**

- JSON schema for metadata.json not provided
- No example file with all required fields
- Users try to manually add tables/relationships and fail
- Documentation missing for relationship JSON structure

---

## SECURITY & COMPLIANCE ISSUES

### 🔒 ISSUE #26: No Access Control

**Severity:** HIGH  
**Category:** Enterprise  
**Impact:** Anyone with URL can access/modify all models

**Description:**

- No authentication required
- No role-based access control (who can edit vs. view)
- No audit trail of who generated what
- Unsafe in multi-team environment

---

### 🔒 ISSUE #27: API Key Stored in Plain Text Could Be Leaked

**Severity:** MEDIUM  
**Category:** Security  
**Impact:** OpenAI API key could be compromised via Streamlit session

**Description:**

- User enters API key in text_input() widget
- Session state might persist in browser cookies
- .env file stored in git repo (if not in .gitignore)
- No warning about API key exposure

---

## DATA QUALITY & VALIDATION

### ✔️ ISSUE #28: No Validation of Generated Code Syntax Before Return

**Severity:** MEDIUM  
**Category:** Quality  
**Impact:** Returns invalid code that doesn't execute

**Description:**

- Code validation runs but errors aren't always caught
- Generated PySpark might have missing imports (DataFrame methods)
- DAX might reference columns without table prefix in wrong context
- SQL might have syntax errors (missing commas, wrong JOIN syntax)
- System returns code with validation errors, user finds them in production

---

## SUMMARY TABLE

| #     | Issue                                   | Severity    | Impact                   | Category         |
| ----- | --------------------------------------- | ----------- | ------------------------ | ---------------- |
| 1     | Empty model generates hallucinated code | 🔴 CRITICAL | Code doesn't work        | Generation       |
| 2     | No validation of table references       | 🔴 CRITICAL | Wrong model context      | Data Integrity   |
| 3     | No CSV format validation                | 🔴 CRITICAL | Bad schema ingestion     | Input Validation |
| 4     | Relationship false positives            | 🔴 CRITICAL | Wrong joins generated    | Schema Modeling  |
| 5     | Output type mismatches                  | 🟠 HIGH     | Wrong language output    | Multi-Language   |
| 6     | Model Hub unintuitive                   | 🟠 HIGH     | Users lost, confused     | UX               |
| 7     | Paste-ready output inconsistent         | 🟠 HIGH     | Can't copy-paste         | Usability        |
| 8     | No session persistence                  | 🟠 HIGH     | Users lose work          | Stability        |
| 9     | Errors not actionable                   | 🟠 HIGH     | Users can't fix problems | UX               |
| 10    | Performance on large models             | 🟠 HIGH     | Slow/unusable            | Performance      |
| 11-20 | Medium/Low severity issues              | 🟡/🟢       | Workarounds exist        | Various          |
| 24-28 | API, Security, Quality issues           | 🟠 HIGH     | Enterprise gaps          | Integration      |

---

## TESTING RECOMMENDATIONS

### ✅ Tests That Should Pass Before Production:

1. **Empty Model Test**

   ```
   Create model with 0 tables → Generate measure → Should ERROR, not return sample code
   ```

2. **Cross-Model Isolation Test**

   ```
   Model A: [SalesAmount] only
   Model B: [EmployeeCount] only
   Switch to Model B → Generate "total sales" → Should WARN or ERROR, not reference Sales table
   ```

3. **CSV Validation Test**

   ```
   Upload malformed CSV → Should show clear error with remediation
   ```

4. **Output Type Consistency Test**

   ```
   For EACH target (semantic, warehouse, notebook, python):
   - Generate item
   - Verify output type matches target
   - Try to use output in target environment
   ```

5. **Large Model Performance Test**
   ```
   Load model with 50+ tables
   - Schema view should load in < 2 seconds
   - Relationship grid should be scrollable without lag
   - Generation should complete in < 10 seconds
   ```

---

## CORPORATE CLIENT CONCLUSION

**Overall Assessment:** Tool has good potential but **NOT PRODUCTION READY**

**Blocking Issues:** 4 Critical issues must be fixed before any enterprise use

- Can't generate code for empty models
- Wrong model isolation causes data errors
- No file validation creates bad schema
- Relationship detection has false positives

**Risk Level:** 🔴 HIGH

- Users will generate broken code
- Data integrity issues possible
- No access control (security risk)
- Performance inadequate for large models

**Recommendation:** Fix critical issues in backlog before rollout to business users. Consider beta testing with small pilot group first.
