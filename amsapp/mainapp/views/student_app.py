from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiExample

from ..models import Students, ExamSchedule, Exam, ExamQuestion, Submission
from ..serializers import (
    StudentsSerializer, StudentLoginSerializer, ExamSubmissionSerializer,
    StudentLoginResponseSerializer, ExamSubmissionResponseSerializer
)


@extend_schema(
    operation_id='student_login',
    summary="Student login",
    description="Authenticate student with username and password",
    tags=['Student App'],
    request=StudentLoginSerializer,
    responses={
        200: StudentLoginResponseSerializer,
        401: {
            'type': 'object',
            'properties': {
                'error': {'type': 'string'}
            }
        }
    }
)
@csrf_exempt
@api_view(['POST'])
def student_login(request):
    """Student login endpoint"""
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response(
            {'error': 'Username and password are required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        student = Students.objects.get(username=username, password=password)
        return Response({
            'message': 'Login successful',
            'student': StudentsSerializer(student).data
        }, status=status.HTTP_200_OK)
    except Students.DoesNotExist:
        return Response(
            {'error': 'Invalid credentials'}, 
            status=status.HTTP_401_UNAUTHORIZED
        )


@extend_schema(
    summary="Student available exams",
    description="Get all active exam schedules available to students",
    tags=['Student App'],
    responses={200: {
        'type': 'array',
        'items': {
            'type': 'object',
            'properties': {
                'schedule_id': {'type': 'integer'},
                'exam_id': {'type': 'integer'},
                'exam_name': {'type': 'string'},
                'department': {'type': 'string'},
                'semester': {'type': 'string'},
                'total_questions': {'type': 'integer'},
                'duration_minutes': {'type': 'integer'},
                'start_time': {'type': 'string'},
                'end_time': {'type': 'string'},
                'is_active': {'type': 'boolean'}
            }
        }
    }}
)
class StudentAvailableExamsView(generics.ListAPIView):
    """List all available active exam schedules for students"""
    
    def get_queryset(self):
        return ExamSchedule.objects.filter(is_active=True).order_by('start_time')
    
    def list(self, request, *args, **kwargs):
        schedules = self.get_queryset()
        exam_list = []
        
        for schedule in schedules:
            exam_data = {
                'schedule_id': schedule.id,
                'exam_id': schedule.exam.id,
                'exam_name': f"{schedule.exam.department} - {schedule.exam.semester}",
                'department': schedule.exam.department,
                'semester': schedule.exam.semester,
                'total_questions': schedule.exam.total_questions,
                'duration_minutes': schedule.exam.duration_minutes,
                'start_time': schedule.start_time,
                'end_time': schedule.end_time,
                'is_active': schedule.is_active
            }
            exam_list.append(exam_data)
        
        return Response(exam_list, status=status.HTTP_200_OK)


@extend_schema(
    summary="Student exam questions",
    description="Get all questions for a specific exam",
    tags=['Student App'],
    responses={200: {
        'type': 'object',
        'properties': {
            'exam_id': {'type': 'integer'},
            'exam_details': {
                'type': 'object',
                'properties': {
                    'department': {'type': 'string'},
                    'semester': {'type': 'string'},
                    'total_questions': {'type': 'integer'},
                    'duration_minutes': {'type': 'integer'}
                }
            },
            'questions': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'question_id': {'type': 'integer'},
                        'question_text': {'type': 'string'},
                        'options': {'type': 'array', 'items': {'type': 'string'}},
                        'question_type': {'type': 'string'}
                    }
                }
            }
        }
    }}
)
class StudentExamQuestionsView(generics.RetrieveAPIView):
    """Get all questions for a specific exam (for students taking the exam)"""
    lookup_url_kwarg = 'exam_id'
    
    def retrieve(self, request, *args, **kwargs):
        exam_id = kwargs.get('exam_id')
        
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response(
                {'error': 'Exam not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get all questions for this exam (ExamQuestion contains the question data directly)
        exam_questions = ExamQuestion.objects.filter(exam=exam).order_by('id')
        
        questions_data = []
        for eq in exam_questions:
            question_data = {
                'question_id': eq.id,
                'question_text': eq.question_text,
                'options': eq.options,
                'question_type': eq.type,
                'marks': eq.marks,
                'subject': eq.subject
            }
            questions_data.append(question_data)
        
        response_data = {
            'exam_id': exam.id,
            'exam_details': {
                'department': exam.department,
                'semester': exam.semester,
                'total_questions': exam.total_questions,
                'duration_minutes': exam.duration_minutes
            },
            'questions': questions_data
        }
        
        return Response(response_data, status=status.HTTP_200_OK)


@extend_schema(
    operation_id='submit_exam',
    summary="Submit exam answers",
    description="Submit student answers for an exam",
    tags=['Student App'],
    request=ExamSubmissionSerializer,
    responses={
        201: ExamSubmissionResponseSerializer,
        400: {
            'type': 'object',
            'properties': {
                'error': {'type': 'string'}
            }
        }
    }
)
@csrf_exempt
@api_view(['POST'])
def submit_exam(request, exam_id):
    """Submit exam answers"""
    student_id = request.data.get('student_id')
    submissions = request.data.get('submissions', [])
    
    if not student_id:
        return Response(
            {'error': 'Student ID is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not submissions:
        return Response(
            {'error': 'At least one answer submission is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        student = Students.objects.get(id=student_id)
        exam = Exam.objects.get(id=exam_id)
    except (Students.DoesNotExist, Exam.DoesNotExist):
        return Response(
            {'error': 'Student or Exam not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    submissions_created = 0
    
    for submission_data in submissions:
        question_id = submission_data.get('question_id')
        answer = submission_data.get('answer', '').strip()
        
        if not question_id:
            continue
        
        try:
            # Get the ExamQuestion (not ScrappedQuestion)
            exam_question = ExamQuestion.objects.get(id=question_id, exam=exam)
            
            # Check if answer is correct
            is_correct = False
            if exam_question.type == 'option':
                # For option type, compare with correct answer
                correct_answers = exam_question.answer if isinstance(exam_question.answer, list) else [exam_question.answer]
                is_correct = answer in correct_answers
            elif exam_question.type == 'text':
                # For text type, simple string comparison
                is_correct = answer.lower() == str(exam_question.answer).lower()
            
            # Create or update submission
            submission, created = Submission.objects.update_or_create(
                student=student,
                exam=exam,
                question=exam_question,
                defaults={
                    'answer': answer,
                    'is_correct': is_correct
                }
            )
            
            if created:
                submissions_created += 1
                
        except ExamQuestion.DoesNotExist:
            continue
    
    return Response({
        'message': f'Exam submitted successfully',
        'total_submitted': submissions_created
    }, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Get exam result",
    description="Get student's exam result and performance details",
    tags=['Student App'],
    responses={200: {
        'type': 'object',
        'properties': {
            'student_id': {'type': 'integer'},
            'exam_id': {'type': 'integer'},
            'student_name': {'type': 'string'},
            'exam_details': {
                'type': 'object',
                'properties': {
                    'department': {'type': 'string'},
                    'semester': {'type': 'string'},
                    'total_questions': {'type': 'integer'}
                }
            },
            'results': {
                'type': 'object',
                'properties': {
                    'total_questions_attempted': {'type': 'integer'},
                    'correct_answers': {'type': 'integer'},
                    'wrong_answers': {'type': 'integer'},
                    'score_percentage': {'type': 'number'},
                    'grade': {'type': 'string'}
                }
            }
        }
    }}
)
@api_view(['GET'])
def get_exam_result(request, student_id, exam_id):
    """Get exam result for a specific student and exam"""
    try:
        student = Students.objects.get(id=student_id)
        exam = Exam.objects.get(id=exam_id)
    except (Students.DoesNotExist, Exam.DoesNotExist):
        return Response(
            {'error': 'Invalid student or exam ID'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Get all submissions for this student and exam
    submissions = Submission.objects.filter(student=student, exam=exam)
    
    if not submissions.exists():
        return Response(
            {'error': 'No submissions found for this student and exam'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Calculate results
    total_attempted = submissions.count()
    correct_answers = submissions.filter(is_correct=True).count()
    wrong_answers = total_attempted - correct_answers
    
    # Calculate percentage
    if total_attempted > 0:
        score_percentage = round((correct_answers / total_attempted) * 100, 2)
    else:
        score_percentage = 0
    
    # Determine grade
    if score_percentage >= 90:
        grade = 'A+'
    elif score_percentage >= 80:
        grade = 'A'
    elif score_percentage >= 70:
        grade = 'B'
    elif score_percentage >= 60:
        grade = 'C'
    elif score_percentage >= 50:
        grade = 'D'
    else:
        grade = 'F'
    
    response_data = {
        'student_id': student.id,
        'exam_id': exam.id,
        'student_name': student.username,
        'exam_details': {
            'department': exam.department,
            'semester': exam.semester,
            'total_questions': exam.total_questions
        },
        'results': {
            'total_questions_attempted': total_attempted,
            'correct_answers': correct_answers,
            'wrong_answers': wrong_answers,
            'score_percentage': score_percentage,
            'grade': grade
        }
    }
    
    return Response(response_data, status=status.HTTP_200_OK)


@extend_schema(
    summary="Calculate exam results",
    description="Calculate and display results for all students who took a specific exam",
    tags=['Student App'],
    responses={200: {
        'type': 'object',
        'properties': {
            'exam_id': {'type': 'integer'},
            'exam_details': {
                'type': 'object',
                'properties': {
                    'department': {'type': 'string'},
                    'semester': {'type': 'string'},
                    'total_questions': {'type': 'integer'}
                }
            },
            'results': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'student_id': {'type': 'integer'},
                        'student_name': {'type': 'string'},
                        'f_id': {'type': 'string'},
                        'total_questions_attempted': {'type': 'integer'},
                        'correct_answers': {'type': 'integer'},
                        'wrong_answers': {'type': 'integer'},
                        'score_percentage': {'type': 'number'},
                        'grade': {'type': 'string'}
                    }
                }
            },
            'class_statistics': {
                'type': 'object',
                'properties': {
                    'total_students': {'type': 'integer'},
                    'average_score': {'type': 'number'},
                    'highest_score': {'type': 'number'},
                    'lowest_score': {'type': 'number'}
                }
            }
        }
    }}
)
@api_view(['GET'])
def calculate_exam_result(request, exam_id):
    """Calculate results for all students who took a specific exam"""
    try:
        exam = Exam.objects.get(id=exam_id)
    except Exam.DoesNotExist:
        return Response(
            {'error': 'Exam not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Get all students who submitted answers for this exam
    students_with_submissions = Students.objects.filter(
        submission__exam=exam
    ).distinct()
    
    if not students_with_submissions.exists():
        return Response(
            {'error': 'No submissions found for this exam'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    results = []
    all_scores = []
    
    for student in students_with_submissions:
        # Get submissions for this student and exam
        submissions = Submission.objects.filter(student=student, exam=exam)
        
        total_attempted = submissions.count()
        correct_answers = submissions.filter(is_correct=True).count()
        wrong_answers = total_attempted - correct_answers
        
        # Calculate percentage
        if total_attempted > 0:
            score_percentage = round((correct_answers / total_attempted) * 100, 2)
        else:
            score_percentage = 0
        
        all_scores.append(score_percentage)
        
        # Determine grade
        if score_percentage >= 90:
            grade = 'A+'
        elif score_percentage >= 80:
            grade = 'A'
        elif score_percentage >= 70:
            grade = 'B'
        elif score_percentage >= 60:
            grade = 'C'
        elif score_percentage >= 50:
            grade = 'D'
        else:
            grade = 'F'
        
        student_result = {
            'student_id': student.id,
            'student_name': student.username,
            'f_id': student.f_id,
            'total_questions_attempted': total_attempted,
            'correct_answers': correct_answers,
            'wrong_answers': wrong_answers,
            'score_percentage': score_percentage,
            'grade': grade
        }
        results.append(student_result)
    
    # Calculate class statistics
    class_stats = {
        'total_students': len(all_scores),
        'average_score': round(sum(all_scores) / len(all_scores), 2) if all_scores else 0,
        'highest_score': max(all_scores) if all_scores else 0,
        'lowest_score': min(all_scores) if all_scores else 0
    }
    
    # Sort results by score percentage (highest first)
    results.sort(key=lambda x: x['score_percentage'], reverse=True)
    
    response_data = {
        'exam_id': exam.id,
        'exam_details': {
            'department': exam.department,
            'semester': exam.semester,
            'total_questions': exam.total_questions
        },
        'results': results,
        'class_statistics': class_stats
    }
    
    return Response(response_data, status=status.HTTP_200_OK)


def calculate_exam_result_helper(student_id, exam_id):
    """Helper function to calculate exam result for a specific student and exam"""
    try:
        student = Students.objects.get(id=student_id)
        exam = Exam.objects.get(id=exam_id)
        
        # Get all submissions for this student and exam
        submissions = Submission.objects.filter(student=student, exam=exam)
        
        if not submissions.exists():
            return None
        
        # Calculate overall stats
        total_questions = ExamQuestion.objects.filter(exam=exam).count()
        answered_questions = submissions.count()
        correct_answers = submissions.filter(is_correct=True).count()
        
        # Calculate marks
        total_marks = sum(ExamQuestion.objects.filter(exam=exam).values_list('marks', flat=True))
        obtained_marks = sum(s.question.marks for s in submissions if s.is_correct)
        percentage = (obtained_marks / total_marks * 100) if total_marks > 0 else 0
        
        return {
            'exam_id': exam_id,
            'student_id': student_id,
            'student_username': student.username,
            'total_questions': total_questions,
            'answered_questions': answered_questions,
            'correct_answers': correct_answers,
            'total_marks': total_marks,
            'obtained_marks': obtained_marks,
            'percentage': round(percentage, 2)
        }
        
    except (Students.DoesNotExist, Exam.DoesNotExist):
        return None