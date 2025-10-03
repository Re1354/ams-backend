# Student Schedule API

## New API Endpoint: Get Student Schedule

### URL
`GET /api/student/{student_id}/schedule/`

### Description
This API endpoint retrieves all scheduled exams for a specific student by their student ID. It returns comprehensive schedule information including exam details, timing, and teacher information.

### Authentication
- **Required**: Yes
- **Type**: JWT Authentication
- **Header**: `Authorization: Bearer <jwt_token>`

### URL Parameters
- `student_id` (integer, required): The ID of the student to get schedule for

### Response Format

#### Success Response (200 OK)
```json
{
    "success": true,
    "data": [
        {
            "assignment_id": 1,
            "schedule_id": 5,
            "exam_id": 3,
            "exam_name": "Exam 3",
            "exam_duration": 120,
            "total_questions": 50,
            "schedule_start_time": "2025-10-15T10:00:00Z",
            "schedule_end_time": "2025-10-15T12:00:00Z",
            "teacher_name": "john_doe",
            "teacher_department": "Computer Science",
            "subject_name": "Data Structures",
            "department_shortnames": ["CSE", "IT"],
            "assigned_at": "2025-10-10T08:30:00Z",
            "is_active": true
        }
    ],
    "message": "Found 1 scheduled exams for student john_student"
}
```

#### Error Responses

**Student Not Found (404)**
```json
{
    "success": false,
    "message": "Student not found"
}
```

**No Scheduled Exams (200)**
```json
{
    "success": true,
    "data": [],
    "message": "No scheduled exams found for student john_student"
}
```

**Authentication Required (403)**
```json
{
    "detail": "Authentication credentials were not provided."
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `assignment_id` | integer | ID of the student assignment record |
| `schedule_id` | integer | ID of the exam schedule |
| `exam_id` | integer | ID of the exam |
| `exam_name` | string | Name/title of the exam |
| `exam_duration` | integer | Duration of exam in minutes |
| `total_questions` | integer | Total number of questions in the exam |
| `schedule_start_time` | string (ISO 8601) | When the exam is scheduled to start |
| `schedule_end_time` | string (ISO 8601) | When the exam is scheduled to end |
| `teacher_name` | string | Username of the teacher who assigned the exam |
| `teacher_department` | string | Department of the teacher |
| `subject_name` | string | Subject name (if available) |
| `department_shortnames` | array | List of department short names for the exam |
| `assigned_at` | string (ISO 8601) | When the student was assigned to this exam |
| `is_active` | boolean | Whether the schedule is currently active |

### Usage Examples

#### cURL Example
```bash
curl -X GET "http://localhost:8000/api/student/1/schedule/" \
     -H "Authorization: Bearer your_jwt_token_here" \
     -H "Content-Type: application/json"
```

#### JavaScript (fetch) Example
```javascript
const studentId = 1;
const token = 'your_jwt_token_here';

fetch(`/api/student/${studentId}/schedule/`, {
    method: 'GET',
    headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    }
})
.then(response => response.json())
.then(data => {
    if (data.success) {
        console.log('Student schedule:', data.data);
    } else {
        console.error('Error:', data.message);
    }
});
```

#### Python Requests Example
```python
import requests

url = "http://localhost:8000/api/student/1/schedule/"
headers = {
    "Authorization": "Bearer your_jwt_token_here",
    "Content-Type": "application/json"
}

response = requests.get(url, headers=headers)
data = response.json()

if data.get('success'):
    print("Student schedule:", data['data'])
else:
    print("Error:", data.get('message'))
```

### Integration Notes

1. **Authentication**: Always include a valid JWT token in the Authorization header
2. **Student Validation**: The API verifies that the student exists before returning schedule data
3. **Data Relationships**: The response includes comprehensive exam and schedule information from multiple related models
4. **Performance**: The API uses `select_related` for optimized database queries
5. **Ordering**: Results are ordered by creation date (most recent first)

### Difference from Similar Endpoints

- **`/api/student/{student_id}/scheduled-exams/`**: Returns more detailed exam information with comprehensive structure
- **`/api/student/{student_id}/schedule/`**: Returns simplified schedule-focused information with essential details

Both endpoints serve similar purposes but with different levels of detail and response structure.