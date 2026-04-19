from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..models.viva_marks import VivaMarks
from ..models.students import Students
from ..models.exam import Exam
from ..models.viva_assign import VivaAssignment
from ..serializers.viva_marks import (
    VivaMarksSerializer, VivaMarksCreateUpdateSerializer
)
from ..authentication import CustomJWTAuthentication
from ..services.viva_assessment import ensure_viva_assignment_snapshot


@extend_schema(
    operation_id='add_viva_marks',
    tags=['Viva Marks Management'],
    summary="Add or update viva marks for a student",
    description="Add new viva marks or update existing viva marks for a specific student",
    request=VivaMarksCreateUpdateSerializer,
    responses={
        200: OpenApiResponse(
            response=VivaMarksSerializer,
            description="Viva marks updated successfully"
        ),
        201: OpenApiResponse(
            response=VivaMarksSerializer,
            description="Viva marks created successfully"
        ),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Student not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def add_viva_marks(request, student_id):
    """Add or update viva marks for a student"""
    
    try:
        student = Students.objects.get(id=student_id)
    except Students.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Student not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    serializer = VivaMarksCreateUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = dict(serializer.validated_data)
    exam_id = validated_data.pop("exam_id", None)

    try:
        with transaction.atomic():
            viva_assignment = None
            if exam_id:
                try:
                    exam = Exam.objects.get(id=exam_id)
                except Exam.DoesNotExist:
                    return Response({
                        'success': False,
                        'message': 'Exam not found'
                    }, status=status.HTTP_404_NOT_FOUND)

                viva_assignment = VivaAssignment.objects.filter(
                    student=student,
                    exam=exam,
                ).select_related("teacher", "exam").first()
                if not viva_assignment:
                    return Response({
                        'success': False,
                        'message': 'Viva assignment not found for this student and exam'
                    }, status=status.HTTP_404_NOT_FOUND)
            else:
                assignments = list(
                    VivaAssignment.objects.filter(student=student)
                    .select_related("teacher", "exam")
                    .order_by("-created_at")
                )
                if len(assignments) == 1:
                    viva_assignment = assignments[0]
                elif len(assignments) > 1:
                    return Response({
                        'success': False,
                        'message': 'Multiple viva assignments found for this student. Please provide exam_id.'
                    }, status=status.HTTP_400_BAD_REQUEST)

            if viva_assignment:
                ensure_viva_assignment_snapshot(viva_assignment, save=False)
                viva_assignment.total_marks = validated_data.get("marks", 0)
                viva_assignment.rubric_scores = validated_data.get("rubrics_marks", {})
                viva_assignment.remarks = validated_data.get("remarks")
                viva_assignment.save(
                    update_fields=[
                        "total_marks",
                        "rubric_snapshot",
                        "rubric_scores",
                        "remarks",
                        "updated_at",
                    ]
                )

            viva_marks, created = VivaMarks.objects.get_or_create(
                student=student,
                defaults=validated_data
            )

            if not created:
                for key, value in validated_data.items():
                    setattr(viva_marks, key, value)
                viva_marks.save()

            response_payload = {
                'success': True,
                'message': 'Viva marks created successfully' if created else 'Viva marks updated successfully',
                'data': VivaMarksSerializer(viva_marks).data
            }
            if viva_assignment:
                response_payload['exam_id'] = viva_assignment.exam_id
                response_payload['viva_assignment_id'] = viva_assignment.id

            return Response(
                response_payload,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error adding viva marks: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='delete_viva_marks',
    tags=['Viva Marks Management'],
    summary="Delete viva marks for a student",
    description="Delete viva marks record for a specific student",
    responses={
        200: OpenApiResponse(description="Viva marks deleted successfully"),
        404: OpenApiResponse(description="Student or viva marks not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def delete_viva_marks(request, student_id):
    """Delete viva marks for a student"""
    
    try:
        student = Students.objects.get(id=student_id)
    except Students.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Student not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    exam_id = request.query_params.get("exam_id")

    try:
        deleted_assignment = None
        if exam_id:
            viva_assignment = VivaAssignment.objects.filter(
                student=student,
                exam_id=exam_id,
            ).first()
            if not viva_assignment:
                return Response({
                    'success': False,
                    'message': 'Viva assignment not found for this student and exam'
                }, status=status.HTTP_404_NOT_FOUND)

            viva_assignment.total_marks = 0
            viva_assignment.rubric_scores = {}
            viva_assignment.remarks = None
            viva_assignment.save(update_fields=['total_marks', 'rubric_scores', 'remarks', 'updated_at'])
            deleted_assignment = {
                'viva_assignment_id': viva_assignment.id,
                'exam_id': viva_assignment.exam_id,
            }

        try:
            viva_marks = VivaMarks.objects.get(student=student)
            marks_info = {
                'student_id': student.id,
                'student_username': student.username,
                'marks': viva_marks.marks,
                'rubrics_marks': viva_marks.rubrics_marks
            }
            viva_marks.delete()
        except VivaMarks.DoesNotExist:
            marks_info = None

        if not marks_info and not deleted_assignment:
            return Response({
                'success': False,
                'message': 'Viva marks not found for this student'
            }, status=status.HTTP_404_NOT_FOUND)

        response_data = {
            'success': True,
            'message': 'Viva marks deleted successfully',
        }
        if marks_info:
            response_data['deleted_marks'] = marks_info
        if deleted_assignment:
            response_data['deleted_assignment'] = deleted_assignment

        return Response(response_data)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error deleting viva marks: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
