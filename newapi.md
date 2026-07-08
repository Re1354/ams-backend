# Admission Management APIs

This document contains all APIs related to the **Admission Management** module - Dynamic Admission Threshold & Result Management based on Department and Exam.

## Base URL
- **Production:** `https://ams-diu-backend.onrender.com`
- **Development:** `http://localhost:8000`

## Authentication
All endpoints require JWT authentication. Include the token in the Authorization header:
```
Authorization: Bearer <your_jwt_token>
```

---

## Table of Contents
1. [Admission Threshold Management](#admission-threshold-management)
2. [Admission Results Management](#admission-results-management)
3. [Teacher Schedule Management](#teacher-schedule-management)

---

## Admission Threshold Management

### 1. Set Department Threshold Mappings

**Endpoint:** `POST /api/admission/threshold-mapping/`

**Description:** Bulk create or update department threshold mappings for a specific exam. This sets the minimum marks required for admission to each department.

**Request Body:**
```json
{
  "exam_id": 1,
  "mappings": [
    {
      "department_id": 2,
      "threshold": 60.0
    },
    {
      "department_id": 3,
      "threshold": 75.0
    }
  ]
}
```

**Request Fields:**
- `exam_id` (integer, required): ID of the exam
- `mappings` (array, required): Array of threshold mappings
  - `department_id` (integer, required): ID of the department
  - `threshold` (float, required): Minimum marks required for admission

**Success Response (201 Created):**
```json
{
  "success": true,
  "message": "Threshold mappings processed successfully. Created: 2, Updated: 0",
  "created_count": 2,
  "updated_count": 0,
  "data": [
    {
      "id": 1,
      "exam_id": 1,
      "exam_name": "CSE Admission Test 2024",
      "department_id": 2,
      "department_name": "Computer Science",
      "department_shortname": "CSE",
      "min_threshold_mark": 60.0,
      "created_at": "2024-12-08T10:30:00Z",
      "updated_at": "2024-12-08T10:30:00Z"
    },
    {
      "id": 2,
      "exam_id": 1,
      "exam_name": "CSE Admission Test 2024",
      "department_id": 3,
      "department_name": "Software Engineering",
      "department_shortname": "SWE",
      "min_threshold_mark": 75.0,
      "created_at": "2024-12-08T10:30:00Z",
      "updated_at": "2024-12-08T10:30:00Z"
    }
  ]
}
```

**Error Responses:**
- `400 Bad Request`: Invalid request data or threshold exceeds exam total marks
- `404 Not Found`: Exam or department not found

---

### 2. Get Department Threshold Mappings

**Endpoint:** `GET /api/admission/get-threshold-mapping/`

**Description:** Retrieve department threshold mappings with optional filtering.

**Query Parameters:**
- `exam_id` (integer, optional): Filter by exam ID
- `department_id` (integer, optional): Filter by department ID

**Example Request:**
```
GET /api/admission/get-threshold-mapping/?exam_id=1
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "count": 2,
  "thresholds": [
    {
      "id": 1,
      "exam_id": 1,
      "exam_name": "CSE Admission Test 2024",
      "department_id": 2,
      "department_name": "Computer Science",
      "department_shortname": "CSE",
      "min_threshold_mark": 60.0,
      "created_at": "2024-12-08T10:30:00Z",
      "updated_at": "2024-12-08T10:30:00Z"
    },
    {
      "id": 2,
      "exam_id": 1,
      "exam_name": "CSE Admission Test 2024",
      "department_id": 3,
      "department_name": "Software Engineering",
      "department_shortname": "SWE",
      "min_threshold_mark": 75.0,
      "created_at": "2024-12-08T10:30:00Z",
      "updated_at": "2024-12-08T10:30:00Z"
    }
  ],
  "message": "Found 2 threshold mappings"
}
```

---

### 3. Get Specific Threshold Mapping by ID

**Endpoint:** `GET /api/admission/threshold/{threshold_id}/`

**Description:** Retrieve a specific department threshold mapping by its ID.

**Path Parameters:**
- `threshold_id` (integer, required): ID of the threshold mapping

**Example Request:**
```
GET /api/admission/threshold/1/
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "exam_id": 1,
    "exam_name": "CSE Admission Test 2024",
    "department_id": 2,
    "department_name": "Computer Science",
    "department_shortname": "CSE",
    "min_threshold_mark": 60.0,
    "created_at": "2024-12-08T10:30:00Z",
    "updated_at": "2024-12-08T10:30:00Z"
  },
  "message": "Threshold mapping retrieved successfully"
}
```

**Error Response:**
- `404 Not Found`: Threshold mapping not found

---

### 4. Delete Threshold Mapping

**Endpoint:** `DELETE /api/admission/threshold/{threshold_id}/delete/`

**Description:** Delete a specific department threshold mapping by ID.

**Path Parameters:**
- `threshold_id` (integer, required): ID of the threshold mapping to delete

**Example Request:**
```
DELETE /api/admission/threshold/1/delete/
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "message": "Threshold mapping deleted successfully",
  "deleted_threshold": {
    "id": 1,
    "exam_id": 1,
    "department": "Computer Science",
    "threshold": 60.0
  }
}
```

**Error Response:**
- `404 Not Found`: Threshold mapping not found

---

## Admission Results Management

### 5. Calculate Admission Results

**Endpoint:** `POST /api/admission/calculate-results/`

**Description:** Triggers calculation of admission results for all students who took the specified exam. This will compute MCQ + Viva marks and determine selection status based on department thresholds.

**Request Body:**
```json
{
  "exam_id": 1
}
```

**Request Fields:**
- `exam_id` (integer, required): ID of the exam

**Success Response (200 OK):**
```json
{
  "success": true,
  "message": "Results calculated successfully. Processed 50 students.",
  "processed_count": 50,
  "selected_count": 35,
  "not_selected_count": 15,
  "exam_id": 1
}
```

**Note:** If there are any warnings during calculation, they will be included in the `warnings` array.

**Error Responses:**
- `400 Bad Request`: Invalid request data or missing thresholds
- `404 Not Found`: Exam not found

---

### 6. Get Admission Results

**Endpoint:** `GET /api/admission/results/`

**Description:** Retrieve paginated list of admission results with optional filtering.

**Query Parameters:**
- `exam_id` (integer, optional): Filter by exam ID
- `department_id` (integer, optional): Filter by department ID
- `student_id` (integer, optional): Filter by student ID
- `is_selected` (boolean, optional): Filter by selection status (true/false)
- `status` (string, optional): Filter by publication status (PENDING/PUBLISHED/CANCELLED)
- `page` (integer, optional): Page number (default: 1)
- `page_size` (integer, optional): Number of results per page (default: 20, max: 100)

**Example Request:**
```
GET /api/admission/results/?exam_id=1&is_selected=true&page=1&page_size=20
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "count": 35,
  "next": "http://localhost:8000/api/admission/results/?exam_id=1&is_selected=true&page=2",
  "previous": null,
  "filters_applied": {
    "exam_id": "1",
    "department_id": null,
    "student_id": null,
    "is_selected": "true",
    "status": null
  },
  "results": [
    {
      "id": 1,
      "exam_id": 1,
      "exam_name": "CSE Admission Test 2024",
      "student_id": 10,
      "student_username": "student001",
      "student_name": "John Doe",
      "student_email": "john@example.com",
      "department_id": 2,
      "department_name": "Computer Science",
      "department_shortname": "CSE",
      "mcq_marks": 45.5,
      "viva_marks": 18.0,
      "total_marks": 63.5,
      "subject_wise_marks": {
        "Mathematics": 20,
        "Physics": 15.5,
        "English": 10
      },
      "is_selected": true,
      "status": "PENDING",
      "threshold_applied": 60.0,
      "remarks": null,
      "created_at": "2024-12-08T10:30:00Z",
      "updated_at": "2024-12-08T10:30:00Z"
    }
  ]
}
```

---

### 7. Get Specific Admission Result by ID

**Endpoint:** `GET /api/admission/results/{result_id}/`

**Description:** Retrieve a specific admission result by its ID.

**Path Parameters:**
- `result_id` (integer, required): ID of the admission result

**Example Request:**
```
GET /api/admission/results/1/
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "exam_id": 1,
    "exam_name": "CSE Admission Test 2024",
    "student_id": 10,
    "student_username": "student001",
    "student_name": "John Doe",
    "student_email": "john@example.com",
    "department_id": 2,
    "department_name": "Computer Science",
    "department_shortname": "CSE",
    "mcq_marks": 45.5,
    "viva_marks": 18.0,
    "total_marks": 63.5,
    "subject_wise_marks": {
      "Mathematics": 20,
      "Physics": 15.5,
      "English": 10
    },
    "is_selected": true,
    "status": "PENDING",
    "threshold_applied": 60.0,
    "remarks": null,
    "created_at": "2024-12-08T10:30:00Z",
    "updated_at": "2024-12-08T10:30:00Z"
  },
  "message": "Admission result retrieved successfully"
}
```

**Error Response:**
- `404 Not Found`: Admission result not found

---

### 8. Get Student Admission Result

**Endpoint:** `GET /api/admission/results/student/{exam_id}/{student_id}/`

**Description:** Retrieve the admission result for a specific student in a specific exam.

**Path Parameters:**
- `exam_id` (integer, required): ID of the exam
- `student_id` (integer, required): ID of the student

**Example Request:**
```
GET /api/admission/results/student/1/10/
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "exam_id": 1,
    "exam_name": "CSE Admission Test 2024",
    "student_id": 10,
    "student_username": "student001",
    "student_name": "John Doe",
    "student_email": "john@example.com",
    "department_id": 2,
    "department_name": "Computer Science",
    "department_shortname": "CSE",
    "mcq_marks": 45.5,
    "viva_marks": 18.0,
    "total_marks": 63.5,
    "subject_wise_marks": {
      "Mathematics": 20,
      "Physics": 15.5,
      "English": 10
    },
    "is_selected": true,
    "status": "PENDING",
    "threshold_applied": 60.0,
    "remarks": null,
    "created_at": "2024-12-08T10:30:00Z",
    "updated_at": "2024-12-08T10:30:00Z"
  },
  "message": "Student admission result retrieved successfully"
}
```

**Error Response:**
- `404 Not Found`: No admission result found for the student in the specified exam

---

### 9. Publish Admission Results

**Endpoint:** `POST /api/admission/publish-results/`

**Description:** Change status of admission results to PUBLISHED for a specific exam. This makes the results visible to students.

**Request Body:**
```json
{
  "exam_id": 1
}
```

**Request Fields:**
- `exam_id` (integer, required): ID of the exam

**Success Response (200 OK):**
```json
{
  "success": true,
  "message": "Published 50 admission results for exam 1",
  "published_count": 50,
  "exam_id": 1
}
```

**Error Responses:**
- `400 Bad Request`: Invalid request data
- `404 Not Found`: Exam not found or no pending results to publish

---

### 10. Recalculate Student Result

**Endpoint:** `POST /api/admission/recalculate/{exam_id}/{student_id}/`

**Description:** Recalculate admission result for a specific student in a specific exam. Useful when marks are updated manually.

**Path Parameters:**
- `exam_id` (integer, required): ID of the exam
- `student_id` (integer, required): ID of the student

**Example Request:**
```
POST /api/admission/recalculate/1/10/
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "message": "Result updated successfully for student student001",
  "data": {
    "id": 1,
    "exam_id": 1,
    "exam_name": "CSE Admission Test 2024",
    "student_id": 10,
    "student_username": "student001",
    "student_name": "John Doe",
    "student_email": "john@example.com",
    "department_id": 2,
    "department_name": "Computer Science",
    "department_shortname": "CSE",
    "mcq_marks": 45.5,
    "viva_marks": 18.0,
    "total_marks": 63.5,
    "subject_wise_marks": {
      "Mathematics": 20,
      "Physics": 15.5,
      "English": 10
    },
    "is_selected": true,
    "status": "PENDING",
    "threshold_applied": 60.0,
    "remarks": null,
    "created_at": "2024-12-08T10:30:00Z",
    "updated_at": "2024-12-08T10:35:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Calculation failed
- `404 Not Found`: Student or exam not found

---

## Data Models

### DepartmentThreshold Model
```typescript
interface DepartmentThreshold {
  id: number;
  exam_id: number;
  exam_name: string;
  department_id: number;
  department_name: string;
  department_shortname: string;
  min_threshold_mark: number;
  created_at: string;
  updated_at: string;
}
```

### AdmissionResult Model
```typescript
interface AdmissionResult {
  id: number;
  exam_id: number;
  exam_name: string;
  student_id: number;
  student_username: string;
  student_name: string;
  student_email: string;
  department_id: number;
  department_name: string;
  department_shortname: string;
  mcq_marks: number;
  viva_marks: number;
  total_marks: number;
  subject_wise_marks: Record<string, number>;
  is_selected: boolean;
  status: 'PENDING' | 'PUBLISHED' | 'CANCELLED';
  threshold_applied: number | null;
  remarks: string | null;
  created_at: string;
  updated_at: string;
}
```

---

## Common Response Patterns

### Success Response
```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": { /* response data */ }
}
```

### Error Response
```json
{
  "success": false,
  "message": "Error description",
  "errors": { /* validation errors if applicable */ }
}
```

---

## Usage Workflow

### Setting Up Admission for an Exam

1. **Create the exam** using exam management APIs
2. **Set department thresholds** using `POST /api/admission/threshold-mapping/`
   - Define minimum marks required for each department
3. **Students take the exam** (MCQ portion)
4. **Conduct viva** and record viva marks
5. **Calculate results** using `POST /api/admission/calculate-results/`
   - System automatically calculates total marks
   - Determines selection status based on thresholds
6. **Review results** using `GET /api/admission/results/`
7. **Publish results** using `POST /api/admission/publish-results/`
   - Makes results visible to students

### Updating Results

- To recalculate a single student's result (after mark correction):
  - Use `POST /api/admission/recalculate/{exam_id}/{student_id}/`

- To update thresholds:
  - Use `POST /api/admission/threshold-mapping/` with new values

---

## Notes

- All timestamps are in ISO 8601 format (UTC)
- Results are ordered by total marks (highest first) by default
- Pagination is available on list endpoints with `page` and `page_size` parameters
- All endpoints require authentication via JWT token
- Threshold values cannot exceed exam total marks
- One threshold per department per exam
- One result per student per exam

---

---

## Teacher Schedule Management

### 11. Get Teacher Schedule

**Endpoint:** `GET /api/get-schedule/{teacher_id}/`

**Description:** Retrieve all exam schedules assigned to a specific teacher based on StudentAssignTeacherExam assignments. Returns unique schedules with complete exam details.

**Path Parameters:**
- `teacher_id` (integer, required): ID of the teacher

**Example Request:**
```
GET /api/get-schedule/5/
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "teacher": {
    "id": 5,
    "username": "john_teacher",
    "email": "john.teacher@example.com"
  },
  "count": 3,
  "schedules": [
    {
      "id": 1,
      "exam": {
        "id": 10,
        "department": "Computer Science",
        "semester": "Fall 2024",
        "total_questions": 50,
        "present_question": 50,
        "total_marks": 100,
        "duration_minutes": 120,
        "except_semesters": [],
        "language": "English",
        "faculty": "Engineering",
        "created_at": "2024-12-01T10:00:00Z",
        "updated_at": "2024-12-01T10:00:00Z"
      },
      "start_time": "2024-12-20T09:00:00Z",
      "end_time": "2024-12-20T11:00:00Z",
      "is_active": true,
      "created_at": "2024-12-01T10:30:00Z"
    },
    {
      "id": 2,
      "exam": {
        "id": 11,
        "department": "Software Engineering",
        "semester": "Fall 2024",
        "total_questions": 40,
        "present_question": 40,
        "total_marks": 80,
        "duration_minutes": 90,
        "except_semesters": [],
        "language": "English",
        "faculty": "Engineering",
        "created_at": "2024-12-02T10:00:00Z",
        "updated_at": "2024-12-02T10:00:00Z"
      },
      "start_time": "2024-12-21T14:00:00Z",
      "end_time": "2024-12-21T15:30:00Z",
      "is_active": true,
      "created_at": "2024-12-02T10:30:00Z"
    }
  ],
  "message": "Found 3 schedules for teacher john_teacher"
}
```

**Error Responses:**

**401 Unauthorized:**
```json
{
  "success": false,
  "message": "Authentication required"
}
```

**404 Not Found:**
```json
{
  "success": false,
  "message": "Teacher not found"
}
```

**Use Cases:**
- Display teacher's upcoming exam schedule on their dashboard
- Show all exams a teacher is assigned to supervise
- Help teachers plan their exam invigilation duties
- View exam details including timing, duration, and department

**Notes:**
- Returns only unique schedules (no duplicates even if teacher has multiple student assignments for the same schedule)
- Schedules are ordered by start time (most recent first)
- Each schedule includes complete exam information
- Only returns schedules where the teacher has been assigned students through StudentAssignTeacherExam

---

## API Testing

You can test these APIs using:
- **Swagger UI:** `http://localhost:8000/api/schema/swagger-ui/`
- **Postman** or any REST client
- **cURL** commands

Example cURL requests:

**Calculate Admission Results:**
```bash
curl -X POST http://localhost:8000/api/admission/calculate-results/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"exam_id": 1}'
```

**Get Teacher Schedule:**
```bash
curl -X GET http://localhost:8000/api/get-schedule/5/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

**Last Updated:** December 17, 2025
