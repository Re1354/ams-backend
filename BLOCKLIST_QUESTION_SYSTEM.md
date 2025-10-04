# BlocklistQuestion Management System

## Overview
This system allows users to block problematic scrapped questions and restore them after fixing issues. Questions are moved between `scrapped_questions` and `blocklist_questions` tables.

## API Endpoints

### 1. Block a Question
**POST** `/api/question/block/`

Moves a scrapped question to the blocklist and deletes it from scrapped_questions.

**Request Body:**
```json
{
    "question_id": 5,
    "remarks": "Incorrect answer provided in options"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Question blocked successfully",
    "data": {
        "id": 1,
        "subject": "Mathematics",
        "questions": "What is the value of 12 + 28?",
        "type": "option",
        "text": null,
        "options": {
            "A": "30",
            "B": "35", 
            "C": "40",
            "D": "45"
        },
        "answer": ["C"],
        "marks": 1,
        "semester": "Batch 6",
        "department_shortname": "CSE",
        "original_question_id": 5,
        "remarks": "Incorrect answer provided in options",
        "creator": 5,
        "creator_username": "admin",
        "creator_name": "Admin",
        "issue_solved": false,
        "created_at": "2025-10-04T10:30:00Z",
        "updated_at": "2025-10-04T10:30:00Z"
    }
}
```

### 2. Get All Blocked Questions
**GET** `/api/get-all-blocked-questions/`

Retrieves all blocked questions with optional filters.

**Query Parameters:**
- `department_shortname` (optional): Filter by department
- `subject` (optional): Filter by subject
- `semester` (optional): Filter by semester
- `issue_solved` (optional): Filter by solved status (true/false)

**Response:**
```json
{
    "success": true,
    "count": 2,
    "questions": [
        {
            "id": 1,
            "subject": "Mathematics",
            "questions": "What is the value of 12 + 28?",
            "type": "option",
            "text": null,
            "options": {
                "A": "30",
                "B": "35",
                "C": "40", 
                "D": "45"
            },
            "answer": ["C"],
            "marks": 1,
            "semester": "Batch 6",
            "department_shortname": "CSE",
            "original_question_id": 5,
            "remarks": "Incorrect answer provided in options",
            "creator": 5,
            "creator_username": "admin",
            "creator_name": "Admin",
            "issue_solved": false,
            "created_at": "2025-10-04T10:30:00Z",
            "updated_at": "2025-10-04T10:30:00Z"
        }
    ],
    "message": "Found 2 blocked questions"
}
```

### 3. Update and Restore Question
**PUT** `/api/blocked-question/{question_id}/restore/`

Updates a blocked question with corrected data and restores it back to scrapped_questions.

**Request Body:**
```json
{
    "subject": "Mathematics",
    "questions": "What is the value of 12 + 28?",
    "type": "option",
    "text": null,
    "options": {
        "A": "30",
        "B": "35",
        "C": "40",
        "D": "45"
    },
    "answer": ["C"],
    "marks": 1,
    "semester": "Batch 6", 
    "department_shortname": "CSE",
    "remarks": "Fixed the incorrect answer",
    "issue_solved": true
}
```

**Response:**
```json
{
    "success": true,
    "message": "Question updated and restored successfully",
    "data": {
        "id": 156,
        "subject": "Mathematics",
        "questions": "What is the value of 12 + 28?",
        "original_blocked_id": 1
    }
}
```

### 4. Delete Blocked Question (Bonus)
**DELETE** `/api/blocked-question/{question_id}/delete/`

Permanently deletes a blocked question.

**Response:**
```json
{
    "success": true,
    "message": "Blocked question deleted permanently",
    "deleted_question": {
        "id": 1,
        "subject": "Mathematics",
        "questions": "What is the value of 12 + 28?"
    }
}
```

## Workflow

### 1. Block a Question
1. User identifies a problematic question in scrapped_questions
2. User calls `POST /api/question/block/` with question_id and remarks
3. System creates BlocklistQuestion record with full question data
4. System deletes the original ScrappedQuestion
5. Question is now in blocklist for review

### 2. Review and Fix
1. User calls `GET /api/get-all-blocked-questions/` to see blocked questions
2. User reviews the question and identifies the issue
3. User prepares corrected question data

### 3. Restore Question
1. User calls `PUT /api/blocked-question/{id}/restore/` with corrected data
2. System updates the BlocklistQuestion with new data
3. System creates new ScrappedQuestion with corrected data
4. System deletes the BlocklistQuestion record
5. Question is now back in scrapped_questions with fixes

## Role-Based Access Control

### Superadmin
- Can see all blocked questions from all departments
- Can block/restore questions from any department

### Department Users
- Can only see blocked questions from their department
- Can only block/restore questions from their department

### Security Features
- JWT authentication required for all endpoints
- Role-based filtering ensures data isolation
- Transaction-based operations ensure data consistency
- Audit trail with creator information and timestamps

## Database Changes

### BlocklistQuestion Model
- Enhanced with `create_from_scrapped_question()` class method
- Enhanced with `restore_to_scrapped_question()` instance method
- Full snapshot of ScrappedQuestion data preserved
- Additional metadata (creator, remarks, timestamps)

## Usage Examples

### Block a problematic question:
```bash
curl -X POST "http://localhost:8000/api/question/block/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question_id": 5, "remarks": "Wrong answer in options"}'
```

### Get all blocked questions:
```bash
curl -X GET "http://localhost:8000/api/get-all-blocked-questions/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Restore a fixed question:
```bash
curl -X PUT "http://localhost:8000/api/blocked-question/1/restore/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subject": "Mathematics", "questions": "Fixed question...", "issue_solved": true}'
```

The BlocklistQuestion management system is now fully operational! 🚀