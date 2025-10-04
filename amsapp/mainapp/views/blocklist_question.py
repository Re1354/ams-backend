from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ..models import BlocklistQuestion, ScrappedQuestion, User
from ..serializers.blocklist_question import (
    BlockQuestionSerializer, BlockedQuestionSerializer, RestoreQuestionSerializer
)
from ..authentication import CustomJWTAuthentication


@extend_schema(
    operation_id='block_question',
    tags=['Question Management'],
    summary="Block a scrapped question",
    description="Move a scrapped question to blocklist with remarks. The question will be deleted from scrapped_questions and added to blocklist_questions.",
    request=BlockQuestionSerializer,
    responses={
        201: OpenApiResponse(
            response=BlockedQuestionSerializer,
            description="Question blocked successfully"
        ),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Question not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def block_question(request):
    """Block a scrapped question and move it to blocklist"""
    
    serializer = BlockQuestionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    question_id = serializer.validated_data['question_id']
    remarks = serializer.validated_data['remarks']
    
    try:
        with transaction.atomic():
            # Get the scrapped question
            scrapped_question = ScrappedQuestion.objects.get(id=question_id)
            
            # Get the current user (extract the actual User model instance from CustomUser wrapper)
            creator = request.user.custom_user
            
            # Create blocked question from scrapped question
            blocked_question = BlocklistQuestion.create_from_scrapped_question(
                scrapped_question=scrapped_question,
                creator=creator,
                remarks=remarks
            )
            
            # Delete the original scrapped question
            scrapped_question.delete()
            
            return Response({
                'success': True,
                'message': 'Question blocked successfully',
                'data': BlockedQuestionSerializer(blocked_question).data
            }, status=status.HTTP_201_CREATED)
            
    except ScrappedQuestion.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Scrapped question not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error blocking question: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='get_all_blocked_questions',
    tags=['Question Management'],
    summary="Get all blocked questions",
    description="Retrieve all questions in the blocklist with role-based filtering. Superadmin sees all, others see questions filtered by department.",
    parameters=[
        OpenApiParameter(name='department_shortname', description='Filter by department shortname', required=False, type=str),
        OpenApiParameter(name='subject', description='Filter by subject', required=False, type=str),
        OpenApiParameter(name='semester', description='Filter by semester', required=False, type=str),
        OpenApiParameter(name='issue_solved', description='Filter by issue solved status', required=False, type=bool),
    ],
    responses={
        200: OpenApiResponse(
            response=BlockedQuestionSerializer(many=True),
            description="Blocked questions retrieved successfully"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_all_blocked_questions(request):
    """Get all blocked questions with role-based filtering"""
    
    user = request.user
    
    # Get the custom user and role information
    if hasattr(user, 'custom_user'):
        custom_user = user.custom_user
        
        # Check if user has a role
        if custom_user.role:
            role_name = custom_user.role.role_name.lower()
            
            # Check if superadmin - return all blocked questions
            if role_name == 'superadmin':
                blocked_questions = BlocklistQuestion.objects.all().select_related('creator')
            else:
                # For non-superadmin users, filter by department_shortname
                if custom_user.department:
                    user_dept_shortname = custom_user.department.department_shortname
                    blocked_questions = BlocklistQuestion.objects.filter(
                        department_shortname=user_dept_shortname
                    ).select_related('creator')
                else:
                    # If user has no department assigned, return empty queryset
                    blocked_questions = BlocklistQuestion.objects.none()
        else:
            # If user has no role, return empty queryset
            blocked_questions = BlocklistQuestion.objects.none()
    else:
        # If no custom_user, return empty queryset for security
        blocked_questions = BlocklistQuestion.objects.none()
    
    # Apply filters
    department_filter = request.query_params.get('department_shortname')
    subject_filter = request.query_params.get('subject')
    semester_filter = request.query_params.get('semester')
    issue_solved_filter = request.query_params.get('issue_solved')
    
    if department_filter:
        blocked_questions = blocked_questions.filter(department_shortname__icontains=department_filter)
    
    if subject_filter:
        blocked_questions = blocked_questions.filter(subject__icontains=subject_filter)
    
    if semester_filter:
        blocked_questions = blocked_questions.filter(semester__icontains=semester_filter)
    
    if issue_solved_filter is not None:
        is_solved = issue_solved_filter.lower() in ['true', '1', 'yes']
        blocked_questions = blocked_questions.filter(issue_solved=is_solved)
    
    # Order by creation date (newest first)
    blocked_questions = blocked_questions.order_by('-created_at')
    
    serializer = BlockedQuestionSerializer(blocked_questions, many=True)
    return Response({
        'success': True,
        'count': blocked_questions.count(),
        'questions': serializer.data,
        'message': f'Found {blocked_questions.count()} blocked questions'
    })


@extend_schema(
    operation_id='restore_blocked_question',
    tags=['Question Management'],
    summary="Update and restore a blocked question",
    description="Update a blocked question with new data and restore it back to scrapped_questions. The question will be deleted from blocklist_questions and added back to scrapped_questions.",
    request=RestoreQuestionSerializer,
    responses={
        200: OpenApiResponse(
            description="Question restored successfully"
        ),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Blocked question not found")
    }
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def restore_blocked_question(request, question_id):
    """Update and restore a blocked question back to scrapped questions"""
    
    try:
        blocked_question = BlocklistQuestion.objects.get(id=question_id)
    except BlocklistQuestion.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Blocked question not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    serializer = RestoreQuestionSerializer(blocked_question, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            # Update the blocked question with new data
            updated_blocked_question = serializer.save()
            
            # Restore to scrapped questions
            restored_question = updated_blocked_question.restore_to_scrapped_question()
            
            # Store info for response
            question_info = {
                'id': restored_question.id,
                'subject': restored_question.subject,
                'questions': restored_question.questions[:100] + '...' if len(restored_question.questions) > 100 else restored_question.questions,
                'original_blocked_id': blocked_question.id
            }
            
            # Delete the blocked question
            updated_blocked_question.delete()
            
            return Response({
                'success': True,
                'message': 'Question updated and restored successfully',
                'data': question_info
            })
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error restoring question: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='delete_blocked_question',
    tags=['Question Management'],
    summary="Permanently delete a blocked question",
    description="Permanently delete a blocked question from the blocklist. This action cannot be undone.",
    responses={
        200: OpenApiResponse(description="Blocked question deleted successfully"),
        404: OpenApiResponse(description="Blocked question not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def delete_blocked_question(request, question_id):
    """Permanently delete a blocked question"""
    
    try:
        blocked_question = BlocklistQuestion.objects.get(id=question_id)
        
        question_info = {
            'id': blocked_question.id,
            'subject': blocked_question.subject,
            'questions': blocked_question.questions[:100] + '...' if len(blocked_question.questions) > 100 else blocked_question.questions
        }
        
        blocked_question.delete()
        
        return Response({
            'success': True,
            'message': 'Blocked question deleted permanently',
            'deleted_question': question_info
        })
        
    except BlocklistQuestion.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Blocked question not found'
        }, status=status.HTTP_404_NOT_FOUND)