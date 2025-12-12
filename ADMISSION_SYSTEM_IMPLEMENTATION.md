# 🎓 Dynamic Admission Threshold & Result System

## Overview
Complete implementation of a dynamic admission threshold and result calculation system for the AMS DIU Backend. This system allows setting department-specific admission thresholds and automatically calculating whether students are selected based on their combined MCQ and Viva marks.

---

## 📦 What's Been Implemented

### 1. **Database Models** (2 new models)

#### A. `DepartmentThreshold`
**Location:** `amsapp/mainapp/models/department_threshold.py`

Stores minimum marks required for admission to specific departments.

**Fields:**
- `exam` - ForeignKey to Exam (ensures historical data integrity)
- `department` - ForeignKey to Department
- `min_threshold_mark` - FloatField (cutoff score, validated >= 0)
- `created_at`, `updated_at` - Timestamps

**Constraints:**
- Unique together: `['exam', 'department']` (one threshold per dept per exam)
- Validation: Threshold cannot exceed exam total marks

#### B. `AdmissionResult`
**Location:** `amsapp/mainapp/models/admission_result.py`

Stores calculated admission status for students.

**Fields:**
- `exam`, `student`, `department` - Foreign keys
- `mcq_marks`, `viva_marks`, `total_marks` - FloatField (marks breakdown)
- `subject_wise_marks` - JSONField (detailed subject breakdown)
- `is_selected` - BooleanField (True if marks >= threshold)
- `status` - CharField (PENDING/PUBLISHED/CANCELLED)
- `threshold_applied` - FloatField (threshold used in calculation)
- `remarks` - TextField (optional notes)

**Constraints:**
- Unique together: `['exam', 'student']`
- Auto-calculated: `total_marks = mcq_marks + viva_marks`

---

### 2. **Business Logic Service**
**Location:** `amsapp/mainapp/services/admission_calculator.py`

Core calculation engine with the following functions:

#### Main Functions:

**`calculate_admission_results(exam_id)`**
- Fetches all department thresholds for the exam
- Gets all students who took the exam
- For each student:
  - Calculates MCQ marks from `Submission` records
  - Fetches Viva marks from `VivaMarks`
  - Computes total marks
  - Determines department based on student's `department_shortname`
  - Checks if total >= department threshold
  - Creates/updates `AdmissionResult` record
- Returns: `{success, processed_count, selected_count, not_selected_count, errors}`

**`calculate_mcq_marks_for_student(student, exam)`**
- Aggregates correct submissions and their marks
- Generates subject-wise breakdown (total questions, correct answers, marks obtained, percentage)
- Returns: `(mcq_marks, subject_wise_marks_dict)`

**`get_viva_marks_for_student(student)`**
- Retrieves viva marks from `VivaMarks` model
- Returns: `float` (0.0 if no viva marks exist)

**`recalculate_single_student_result(exam_id, student_id)`**
- Recalculates result for a single student
- Useful for updating without reprocessing entire exam

---

### 3. **Serializers**
**Locations:**
- `amsapp/mainapp/serializers/department_threshold.py`
- `amsapp/mainapp/serializers/admission_result.py`

#### Key Serializers:

**DepartmentThreshold:**
- `DepartmentThresholdSerializer` - Full model serialization with exam details
- `BulkThresholdMappingSerializer` - For bulk create/update operations
- `ThresholdMappingItemSerializer` - Individual mapping validation

**AdmissionResult:**
- `AdmissionResultSerializer` - Full result with student/department/exam info
- `CalculateAdmissionResultsSerializer` - Request validation
- `CalculateResultsResponseSerializer` - Response structure
- `AdmissionResultFilterSerializer` - Query parameter validation

All serializers include:
- ✅ Input validation (positive numbers, existing IDs)
- ✅ Swagger documentation annotations
- ✅ Nested data serialization (department names, exam details)

---

### 4. **API Endpoints**

#### **Threshold Management:**

**POST** `/api/admission/threshold-mapping/`
- **Purpose:** Bulk create/update department thresholds
- **Request:**
```json
{
  "exam_id": 1,
  "mappings": [
    {"department_id": 2, "threshold": 60.0},
    {"department_id": 3, "threshold": 75.0}
  ]
}
```
- **Response:** Created/updated thresholds with counts
- **Authentication:** Required (JWT)

**GET** `/api/admission/get-threshold-mapping/`
- **Purpose:** Retrieve threshold mappings
- **Query Params:** `exam_id`, `department_id`
- **Response:** List of thresholds with details

**GET** `/api/admission/threshold/{threshold_id}/`
- **Purpose:** Get specific threshold by ID
- **Response:** Single threshold details

**DELETE** `/api/admission/threshold/{threshold_id}/delete/`
- **Purpose:** Delete specific threshold mapping

---

#### **Results Management:**

**POST** `/api/admission/calculate-results/`
- **Purpose:** Trigger results calculation for an exam
- **Request:**
```json
{
  "exam_id": 1
}
```
- **Response:**
```json
{
  "success": true,
  "message": "Results calculated successfully. Processed 150 students.",
  "processed_count": 150,
  "selected_count": 85,
  "not_selected_count": 65,
  "exam_id": 1
}
```

**GET** `/api/admission/results/`
- **Purpose:** Get paginated admission results
- **Query Params:** 
  - `exam_id` - Filter by exam
  - `department_id` - Filter by department
  - `student_id` - Filter by student
  - `is_selected` - Filter by selection status (true/false)
  - `status` - Filter by status (PENDING/PUBLISHED)
  - `page`, `page_size` - Pagination
- **Pagination:** 20 per page (configurable, max 100)

**GET** `/api/admission/results/{result_id}/`
- **Purpose:** Get specific result by ID

**GET** `/api/admission/results/student/{exam_id}/{student_id}/`
- **Purpose:** Get result for specific student in exam

**POST** `/api/admission/publish-results/`
- **Purpose:** Publish results (change status PENDING → PUBLISHED)
- **Request:**
```json
{
  "exam_id": 1
}
```

**POST** `/api/admission/recalculate/{exam_id}/{student_id}/`
- **Purpose:** Recalculate result for single student

---

### 5. **Comprehensive Tests**
**Location:** `amsapp/mainapp/tests/test_admission_system.py`

#### Test Coverage (17 test cases):

**Threshold Management:**
- ✅ Setting threshold mappings successfully
- ✅ Updating existing thresholds
- ✅ Validation: threshold exceeds exam marks
- ✅ Validation: negative threshold
- ✅ Getting threshold mappings
- ✅ Filtering by exam

**Calculation Logic:**
- ✅ Student passes with 50 marks, threshold 40
- ✅ Student fails with 50 marks, threshold 60
- ✅ Calculation includes viva marks
- ✅ Multiple students with different departments
- ✅ Error when no thresholds set

**Results Retrieval:**
- ✅ Get all admission results
- ✅ Filter by selection status
- ✅ Get student-specific result

**Publishing:**
- ✅ Publish admission results

**Recalculation:**
- ✅ Recalculate single student result

#### Running Tests:
```bash
# Run admission system tests
python manage.py test mainapp.tests.test_admission_system

# Run all tests
python manage.py test

# Run with verbosity
python manage.py test mainapp.tests.test_admission_system -v 2
```

---

## 🚀 Setup & Migration

### Step 1: Create Migrations
```bash
cd amsapp
python manage.py makemigrations
```

### Step 2: Apply Migrations
```bash
python manage.py migrate
```

### Step 3: Verify Tables Created
```bash
python manage.py dbshell
```
```sql
\dt department_threshold
\dt admission_result
```

---

## 📝 Usage Examples

### Example 1: Setting Up Thresholds

```bash
# Step 1: Set thresholds for an exam
POST /api/admission/threshold-mapping/
{
  "exam_id": 5,
  "mappings": [
    {"department_id": 1, "threshold": 60.0},
    {"department_id": 2, "threshold": 70.0},
    {"department_id": 3, "threshold": 65.0}
  ]
}
```

### Example 2: Calculating Results

```bash
# Step 2: Students take exam (submissions created via existing flow)
# Step 3: Viva marks added (via existing viva marks API)

# Step 4: Calculate admission results
POST /api/admission/calculate-results/
{
  "exam_id": 5
}

# Response shows how many students were processed and selected
```

### Example 3: Viewing Results

```bash
# Get all selected students
GET /api/admission/results/?exam_id=5&is_selected=true

# Get results for a specific department
GET /api/admission/results/?exam_id=5&department_id=2

# Get result for specific student
GET /api/admission/results/student/5/123/
```

### Example 4: Publishing Results

```bash
# Publish results to make them visible to students
POST /api/admission/publish-results/
{
  "exam_id": 5
}
```

---

## 🔄 Integration with Existing System

### Seamless Integration:
1. **Uses existing models:** `Exam`, `Students`, `Department`, `Submission`, `ExamQuestion`, `VivaMarks`
2. **Follows existing patterns:** Same authentication (CustomJWTAuthentication), same serializer structure, same URL naming
3. **No breaking changes:** All existing APIs continue to work
4. **Extends functionality:** Adds new capabilities without modifying existing code

### Data Flow:
```
Exam Created → Students Take Exam → Submissions Created
                                    ↓
                              Viva Conducted → VivaMarks Added
                                    ↓
                         Thresholds Set → Calculate Admission Results
                                    ↓
                              AdmissionResult Created (is_selected = True/False)
                                    ↓
                              Results Published → Students View Results
```

---

## 🎯 Key Features

### ✅ Historical Data Integrity
- Thresholds linked to specific exams
- Results are immutable snapshots
- Can recalculate without losing old data

### ✅ Flexible Thresholds
- Different thresholds per department
- Can update thresholds before calculation
- Easy to adjust for different exam difficulties

### ✅ Comprehensive Calculation
- MCQ marks from submissions
- Viva marks integration
- Subject-wise breakdown preserved
- Automatic threshold comparison

### ✅ Role-Based Access
- Uses existing JWT authentication
- Permission checks built-in
- Admin-only operations for threshold management

### ✅ Robust Validation
- Thresholds cannot exceed exam marks
- Department/exam existence checks
- Prevents duplicate mappings
- Handles missing data gracefully

---

## 📊 Database Schema

```sql
-- DepartmentThreshold
CREATE TABLE department_threshold (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER REFERENCES exam(id) ON DELETE CASCADE,
    department_id INTEGER REFERENCES departments(id) ON DELETE CASCADE,
    min_threshold_mark REAL NOT NULL CHECK (min_threshold_mark >= 0),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE (exam_id, department_id)
);

-- AdmissionResult
CREATE TABLE admission_result (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER REFERENCES exam(id) ON DELETE CASCADE,
    student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
    department_id INTEGER REFERENCES departments(id) ON DELETE CASCADE,
    mcq_marks REAL NOT NULL DEFAULT 0,
    viva_marks REAL NOT NULL DEFAULT 0,
    total_marks REAL NOT NULL DEFAULT 0,
    subject_wise_marks JSONB DEFAULT '{}',
    is_selected BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    threshold_applied REAL,
    remarks TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE (exam_id, student_id)
);
```

---

## 🔍 Admin Panel Integration

Both models are registered in Django Admin with:
- List displays with key fields
- Filters for quick searching
- Search functionality
- Raw ID fields for performance
- Custom fieldsets for `AdmissionResult`

**Access:** `http://localhost:8000/admin/`

---

## 🐛 Troubleshooting

### Issue: "No thresholds set for this exam"
**Solution:** Use `/api/admission/threshold-mapping/` to set thresholds before calculating results

### Issue: "Department not found"
**Solution:** Ensure student's `department_shortname` matches a `Department.department_shortname` in the database

### Issue: "No submissions found"
**Solution:** Students must submit exam answers before calculating admission results

### Issue: Incorrect total marks
**Solution:** Check if viva marks are properly added via `/api/add-viva-marks/{student_id}/`

---

## 📚 API Documentation

After running the server, visit:
- **Swagger UI:** `http://localhost:8000/api/schema/swagger-ui/`
- **ReDoc:** `http://localhost:8000/api/schema/redoc/`

All endpoints are fully documented with:
- Request/response schemas
- Example payloads
- Parameter descriptions
- Authentication requirements

---

## ✨ Future Enhancements (Optional)

1. **Rank Calculation:** Add ranking based on total marks
2. **Waitlist Management:** Track students close to threshold
3. **Multiple Threshold Criteria:** Add conditional thresholds (e.g., min MCQ + min Viva)
4. **Batch Processing:** Process large exams in background tasks
5. **Analytics Dashboard:** Visual reports on selection statistics
6. **Email Notifications:** Auto-notify students on result publication

---

## 🎉 Implementation Summary

**Total Files Created/Modified:**
- ✅ 2 Model files
- ✅ 2 Serializer files
- ✅ 1 Service file (business logic)
- ✅ 2 View files (APIs)
- ✅ 1 Test file (17 test cases)
- ✅ Modified: `urls.py`, `admin.py`, `models/__init__.py`

**API Endpoints Added:** 10 new endpoints
**Test Coverage:** 17 comprehensive test cases
**Documentation:** Complete inline documentation + this guide

---

## 📞 Support & Questions

For issues or questions:
1. Check test cases for usage examples
2. Review Swagger documentation
3. Check Django admin for data verification
4. Run tests to verify setup: `python manage.py test mainapp.tests.test_admission_system`

---

**Implementation Complete! 🎊**

The system is production-ready and follows all existing code patterns and conventions.
