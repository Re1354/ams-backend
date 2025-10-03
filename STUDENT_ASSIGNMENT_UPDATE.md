# Student Assignment API Update

## Overview
This update modifies the student assignment system so that the `exam_id` is automatically retrieved from the `ExamSchedule` table instead of being provided by the frontend.

## Changes Made

### 1. Model Changes (`StudentAssignTeacherExam`)
- **Updated `unique_together`**: Changed from `('student', 'teacher', 'exam')` to `('student', 'teacher', 'schedule')` to prevent duplicate assignments for the same schedule
- **Added automatic exam setting**: The model now automatically sets the `exam` field from the `schedule.exam` when saving
- **Added new index**: Added index on `('student', 'schedule')` for better query performance

### 2. Serializer Changes
- **Removed `exam_id` field**: Both `StudentAssignBulkSerializer` and `StudentAssignSingleSerializer` no longer require `exam_id` from the frontend
- **Enhanced validation**: The `validate_schedule_id` method now checks that the schedule exists and has an associated exam
- **Updated help text**: Updated field descriptions to indicate that `exam_id` is automatically retrieved

### 3. View Changes
- **Modified assignment logic**: Both bulk and single assignment views now get the exam from the schedule automatically
- **Updated API documentation**: Added descriptions explaining the automatic exam retrieval
- **Removed exam validation**: No longer need to validate `exam_id` separately since it comes from the schedule
- **Added new endpoint**: `get_available_schedules` to help frontend know which schedules are available for assignment

### 4. New API Endpoint
**URL**: `GET /api/student-assignments/available-schedules/`
- Returns all active exam schedules that can be used for student assignment
- Includes role-based filtering (superadmin sees all, others see department-filtered schedules)
- Each schedule includes the exam information automatically

## API Usage Changes

### Before (Old Way)
```json
{
    "student_ids": [1, 2, 3],
    "teacher_id": 1,
    "exam_id": 5,
    "schedule_id": 10
}
```

### After (New Way)
```json
{
    "student_ids": [1, 2, 3],
    "teacher_id": 1,
    "schedule_id": 10
}
```

The `exam_id` is now automatically retrieved from `ExamSchedule.exam` where `ExamSchedule.id = schedule_id`.

## Frontend Integration Steps

1. **Remove exam_id field**: Remove `exam_id` from your assignment forms
2. **Use schedule selection**: Only provide `schedule_id` in assignment requests
3. **Fetch available schedules**: Use the new `/api/student-assignments/available-schedules/` endpoint to get available schedules
4. **Display schedule with exam info**: The schedule response includes exam details, so you can show exam information alongside schedule information

## Benefits

1. **Simplified frontend logic**: No need to manage both exam_id and schedule_id
2. **Data consistency**: Eliminates possibility of mismatched exam_id and schedule_id
3. **Better user experience**: Frontend can show schedule time along with exam details in one selection
4. **Automatic validation**: System automatically ensures schedule has a valid exam

## Database Migration

A migration file `0020_update_student_assignment_constraints.py` has been created to update the database schema. Run the migration:

```bash
python manage.py migrate
```

## Backward Compatibility

This is a **breaking change** for the frontend. The old API that requires `exam_id` will no longer work. Frontend applications must be updated to use the new API structure.