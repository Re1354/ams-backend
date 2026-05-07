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
from ..services.admission_calculator import recalculate_single_student_result


def verify_viva_assignment_state(viva_assignment, marks, rubrics_marks, remarks):
    viva_assignment.refresh_from_db()
    if float(viva_assignment.total_marks or 0) != float(marks or 0):
        raise RuntimeError("Saved viva assignment marks did not persist correctly")
    if (viva_assignment.rubric_scores or {}) != (rubrics_marks or {}):
        raise RuntimeError("Saved viva assignment rubric scores did not persist correctly")
    if (viva_assignment.remarks or None) != (remarks or None):
        raise RuntimeError("Saved viva assignment remarks did not persist correctly")


def verify_legacy_viva_marks_state(viva_marks, marks, rubrics_marks, remarks):
    viva_marks.refresh_from_db()
    if float(viva_marks.marks or 0) != float(marks or 0):
        raise RuntimeError("Saved legacy viva marks did not persist correctly")
    if (viva_marks.rubrics_marks or {}) != (rubrics_marks or {}):
        raise RuntimeError("Saved legacy viva rubric scores did not persist correctly")
    if (viva_marks.remarks or None) != (remarks or None):
        raise RuntimeError("Saved legacy viva remarks did not persist correctly")


def build_recalculation_partial_response(
    *,
    message,
    viva_marks,
    student,
    exam_id=None,
    viva_assignment=None,
    recalculation=None,
):
    response_payload = {
        'success': False,
        'viva_saved': True,
        'message': message,
        'data': VivaMarksSerializer(viva_marks).data,
        'student_id': student.id,
        'exam_id': exam_id,
        'recalculated_result': recalculation,
    }
    if viva_assignment:
        response_payload['viva_assignment_id'] = viva_assignment.id
    return Response(response_payload, status=status.HTTP_200_OK)


def get_authenticated_teacher(request):
    return getattr(request.user, "custom_user", None)


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
    authenticated_teacher = get_authenticated_teacher(request)

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

                viva_assignment_queryset = VivaAssignment.objects.filter(
                    student=student,
                    exam=exam,
                ).select_related("teacher", "exam")
                if authenticated_teacher is not None:
                    viva_assignment_queryset = viva_assignment_queryset.filter(
                        teacher=authenticated_teacher,
                    )
                viva_assignment = viva_assignment_queryset.order_by("-created_at").first()
                if not viva_assignment:
                    return Response({
                        'success': False,
                        'message': (
                            'Viva assignment not found for this student, exam, '
                            'and authenticated teacher'
                        )
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
                verify_viva_assignment_state(
                    viva_assignment,
                    validated_data.get("marks", 0),
                    validated_data.get("rubrics_marks", {}),
                    validated_data.get("remarks"),
                )

            viva_marks, created = VivaMarks.objects.get_or_create(
                student=student,
                defaults=validated_data
            )

            if not created:
                for key, value in validated_data.items():
                    setattr(viva_marks, key, value)
                viva_marks.save()
            verify_legacy_viva_marks_state(
                viva_marks,
                validated_data.get("marks", 0),
                validated_data.get("rubrics_marks", {}),
                validated_data.get("remarks"),
            )

            response_payload = {
                'success': True,
                'message': 'Viva marks created successfully' if created else 'Viva marks updated successfully',
                'data': VivaMarksSerializer(viva_marks).data,
                'student_id': student.id,
            }
            if viva_assignment:
                response_payload['exam_id'] = viva_assignment.exam_id
                response_payload['viva_assignment_id'] = viva_assignment.id
                recalculation = recalculate_single_student_result(viva_assignment.exam_id, student.id)
                if not recalculation.get('success'):
                    return build_recalculation_partial_response(
                        message=(
                            'Viva marks saved, but admission totals could not be refreshed: '
                            f"{recalculation.get('error', 'Unknown recalculation error')}"
                        ),
                        viva_marks=viva_marks,
                        student=student,
                        exam_id=viva_assignment.exam_id,
                        viva_assignment=viva_assignment,
                        recalculation=recalculation,
                    )
                response_payload['recalculated_result'] = recalculation
                response_payload['message'] = (
                    'Viva marks created and admission totals updated successfully'
                    if created
                    else 'Viva marks updated and admission totals refreshed successfully'
                )

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
    authenticated_teacher = get_authenticated_teacher(request)

    try:
        deleted_assignment = None
        if exam_id:
            viva_assignment_queryset = VivaAssignment.objects.filter(
                student=student,
                exam_id=exam_id,
            )
            if authenticated_teacher is not None:
                viva_assignment_queryset = viva_assignment_queryset.filter(
                    teacher=authenticated_teacher,
                )
            viva_assignment = viva_assignment_queryset.order_by("-created_at").first()
            if not viva_assignment:
                return Response({
                    'success': False,
                    'message': (
                        'Viva assignment not found for this student, exam, '
                        'and authenticated teacher'
                    )
                }, status=status.HTTP_404_NOT_FOUND)

            viva_assignment.total_marks = 0
            viva_assignment.rubric_scores = {}
            viva_assignment.remarks = None
            viva_assignment.save(update_fields=['total_marks', 'rubric_scores', 'remarks', 'updated_at'])
            verify_viva_assignment_state(viva_assignment, 0, {}, None)
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
            'student_id': student.id,
        }
        if marks_info:
            response_data['deleted_marks'] = marks_info
        if deleted_assignment:
            response_data['deleted_assignment'] = deleted_assignment
            recalculation = recalculate_single_student_result(
                deleted_assignment['exam_id'],
                student.id,
            )
            if not recalculation.get('success'):
                return build_recalculation_partial_response(
                    message=(
                        'Viva marks deleted, but admission totals could not be refreshed: '
                        f"{recalculation.get('error', 'Unknown recalculation error')}"
                    ),
                    viva_marks=VivaMarks(student=student, marks=0, rubrics_marks={}, remarks=None),
                    student=student,
                    exam_id=deleted_assignment['exam_id'],
                    recalculation=recalculation,
                )
            response_data['recalculated_result'] = recalculation
            response_data['message'] = 'Viva marks deleted and admission totals refreshed successfully'

        return Response(response_data)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error deleting viva marks: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
