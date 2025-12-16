"""
Admission Results Calculation Service

This module provides the core business logic for calculating admission results
based on MCQ scores, viva marks, and department-specific thresholds.
"""

from django.db import transaction
from django.db.models import Sum, Count, Q
from ..models import (
    AdmissionResult, DepartmentThreshold, Exam, Students, 
    Submission, Department, ExamQuestion
)
from ..models.viva_marks import VivaMarks


def calculate_mcq_marks_for_student(student, exam):
    """
    Calculate MCQ marks for a student in a specific exam.
    
    Args:
        student: Students instance
        exam: Exam instance
    
    Returns:
        tuple: (mcq_marks, subject_wise_marks_dict)
    """
    # Get all submissions for this student and exam
    submissions = Submission.objects.filter(
        student=student,
        exam=exam
    ).select_related('question')
    
    if not submissions.exists():
        return 0.0, {}
    
    # Calculate total MCQ marks (sum of marks for correct answers)
    mcq_marks = 0.0
    for submission in submissions:
        if submission.is_correct:
            mcq_marks += submission.question.marks
    
    # Calculate subject-wise breakdown
    exam_subjects = ExamQuestion.objects.filter(exam=exam).values_list('subject', flat=True).distinct()
    
    subject_wise_marks = {}
    for subject_name in exam_subjects:
        subject_submissions = submissions.filter(question__subject=subject_name)
        total_subject_questions = ExamQuestion.objects.filter(exam=exam, subject=subject_name).count()
        correct_subject_answers = subject_submissions.filter(is_correct=True).count()
        
        # Calculate marks for this subject
        subject_marks = 0.0
        for sub in subject_submissions.filter(is_correct=True):
            subject_marks += sub.question.marks
        
        subject_wise_marks[subject_name] = {
            'total_questions': total_subject_questions,
            'correct_answers': correct_subject_answers,
            'marks_obtained': subject_marks,
            'percentage': (correct_subject_answers / total_subject_questions * 100) if total_subject_questions > 0 else 0
        }
    
    return mcq_marks, subject_wise_marks


def get_viva_marks_for_student(student):
    """
    Get viva marks for a student.
    
    Args:
        student: Students instance
    
    Returns:
        float: viva marks (0.0 if no viva marks exist)
    """
    try:
        viva_marks = VivaMarks.objects.get(student=student)
        return float(viva_marks.marks)
    except VivaMarks.DoesNotExist:
        return 0.0


def get_student_department(student):
    """
    Get the department for a student based on their department_shortname.
    
    Args:
        student: Students instance
    
    Returns:
        Department instance or None
    """
    try:
        # Try to match by department shortname
        department = Department.objects.get(
            department_shortname__iexact=student.department_shortname
        )
        return department
    except Department.DoesNotExist:
        return None
    except Department.MultipleObjectsReturned:
        # If multiple departments with same shortname, get the first one
        return Department.objects.filter(
            department_shortname__iexact=student.department_shortname
        ).first()


def calculate_admission_results(exam_id):
    """
    Main calculation function for admission results.
    
    This function:
    1. Fetches all DepartmentThreshold entries for the given exam
    2. Fetches all students who took this exam
    3. For each student:
       - Calculates MCQ marks
       - Fetches viva marks
       - Calculates total marks
       - Determines if student is selected based on department threshold
       - Creates/updates AdmissionResult record
    
    Args:
        exam_id: ID of the exam to calculate results for
    
    Returns:
        dict: {
            'success': bool,
            'processed_count': int,
            'selected_count': int,
            'not_selected_count': int,
            'errors': list
        }
    """
    try:
        exam = Exam.objects.get(id=exam_id)
    except Exam.DoesNotExist:
        return {
            'success': False,
            'processed_count': 0,
            'selected_count': 0,
            'not_selected_count': 0,
            'errors': [f'Exam with ID {exam_id} does not exist']
        }
    
    # Get all department thresholds for this exam
    thresholds = DepartmentThreshold.objects.filter(exam=exam).select_related('department')
    
    if not thresholds.exists():
        return {
            'success': False,
            'processed_count': 0,
            'selected_count': 0,
            'not_selected_count': 0,
            'errors': ['No department thresholds set for this exam. Please set thresholds first.']
        }
    
    # Create a dictionary for quick threshold lookup
    threshold_map = {
        threshold.department.id: threshold.min_threshold_mark 
        for threshold in thresholds
    }
    
    # Get all students who submitted answers for this exam
    students_with_submissions = Students.objects.filter(
        submissions__exam=exam
    ).distinct()
    
    if not students_with_submissions.exists():
        return {
            'success': False,
            'processed_count': 0,
            'selected_count': 0,
            'not_selected_count': 0,
            'errors': ['No student submissions found for this exam']
        }
    
    processed_count = 0
    selected_count = 0
    not_selected_count = 0
    errors = []
    
    with transaction.atomic():
        for student in students_with_submissions:
            try:
                # Calculate MCQ marks
                mcq_marks, subject_wise_marks = calculate_mcq_marks_for_student(student, exam)
                
                # Get viva marks
                viva_marks = get_viva_marks_for_student(student)
                
                # Calculate total marks
                total_marks = mcq_marks + viva_marks
                
                # Get student's department
                student_department = get_student_department(student)
                
                if not student_department:
                    errors.append(
                        f"Student {student.username} (ID: {student.id}) - "
                        f"Department '{student.department_shortname}' not found in system"
                    )
                    continue
                
                # Get threshold for this department
                threshold = threshold_map.get(student_department.id)
                
                if threshold is None:
                    errors.append(
                        f"Student {student.username} (ID: {student.id}) - "
                        f"No threshold set for department '{student_department.department_name}'"
                    )
                    continue
                
                # Determine if student is selected
                is_selected = total_marks >= threshold
                
                # Create or update admission result
                admission_result, created = AdmissionResult.objects.update_or_create(
                    exam=exam,
                    student=student,
                    defaults={
                        'department': student_department,
                        'mcq_marks': mcq_marks,
                        'viva_marks': viva_marks,
                        'total_marks': total_marks,
                        'subject_wise_marks': subject_wise_marks,
                        'is_selected': is_selected,
                        'threshold_applied': threshold,
                        'status': 'PENDING'  # Results start as pending
                    }
                )
                
                processed_count += 1
                if is_selected:
                    selected_count += 1
                else:
                    not_selected_count += 1
                    
            except Exception as e:
                errors.append(
                    f"Error processing student {student.username} (ID: {student.id}): {str(e)}"
                )
                continue
    
    return {
        'success': True,
        'processed_count': processed_count,
        'selected_count': selected_count,
        'not_selected_count': not_selected_count,
        'errors': errors
    }


def recalculate_single_student_result(exam_id, student_id):
    """
    Recalculate admission result for a single student.
    Useful for updating individual results without recalculating the entire exam.
    
    Args:
        exam_id: ID of the exam
        student_id: ID of the student
    
    Returns:
        dict: Result of the calculation
    """
    try:
        exam = Exam.objects.get(id=exam_id)
        student = Students.objects.get(id=student_id)
    except (Exam.DoesNotExist, Students.DoesNotExist) as e:
        return {
            'success': False,
            'error': str(e)
        }
    
    # Check if student has submissions for this exam
    if not Submission.objects.filter(student=student, exam=exam).exists():
        return {
            'success': False,
            'error': f'Student {student.username} has no submissions for exam {exam_id}'
        }
    
    # Calculate marks
    mcq_marks, subject_wise_marks = calculate_mcq_marks_for_student(student, exam)
    viva_marks = get_viva_marks_for_student(student)
    total_marks = mcq_marks + viva_marks
    
    # Get student's department
    student_department = get_student_department(student)
    
    if not student_department:
        return {
            'success': False,
            'error': f"Department '{student.department_shortname}' not found"
        }
    
    # Get threshold
    try:
        threshold_obj = DepartmentThreshold.objects.get(
            exam=exam,
            department=student_department
        )
        threshold = threshold_obj.min_threshold_mark
    except DepartmentThreshold.DoesNotExist:
        return {
            'success': False,
            'error': f"No threshold set for department '{student_department.department_name}'"
        }
    
    # Determine selection status
    is_selected = total_marks >= threshold
    
    # Update or create result
    with transaction.atomic():
        admission_result, created = AdmissionResult.objects.update_or_create(
            exam=exam,
            student=student,
            defaults={
                'department': student_department,
                'mcq_marks': mcq_marks,
                'viva_marks': viva_marks,
                'total_marks': total_marks,
                'subject_wise_marks': subject_wise_marks,
                'is_selected': is_selected,
                'threshold_applied': threshold,
                'status': 'PENDING'
            }
        )
    
    return {
        'success': True,
        'student': student.username,
        'total_marks': total_marks,
        'is_selected': is_selected,
        'action': 'created' if created else 'updated'
    }
