from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..models.viva_marks import VivaMarks
from ..models.students import Students
from ..serializers.viva_marks import (
    VivaMarksSerializer, VivaMarksCreateUpdateSerializer
)
from ..authentication import CustomJWTAuthentication


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
    
    try:
        with transaction.atomic():
            # Check if viva marks already exist for this student
            viva_marks, created = VivaMarks.objects.get_or_create(
                student=student,
                defaults=serializer.validated_data
            )
            
            if not created:
                # Update existing viva marks
                for key, value in serializer.validated_data.items():
                    setattr(viva_marks, key, value)
                viva_marks.save()
                
                return Response({
                    'success': True,
                    'message': 'Viva marks updated successfully',
                    'data': VivaMarksSerializer(viva_marks).data
                })
            else:
                # Return newly created viva marks
                return Response({
                    'success': True,
                    'message': 'Viva marks created successfully',
                    'data': VivaMarksSerializer(viva_marks).data
                }, status=status.HTTP_201_CREATED)
            
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
    
    try:
        viva_marks = VivaMarks.objects.get(student=student)
        
        marks_info = {
            'student_id': student.id,
            'student_username': student.username,
            'marks': viva_marks.marks,
            'rubrics_marks': viva_marks.rubrics_marks
        }
        
        viva_marks.delete()
        
        return Response({
            'success': True,
            'message': 'Viva marks deleted successfully',
            'deleted_marks': marks_info
        })
        
    except VivaMarks.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Viva marks not found for this student'
        }, status=status.HTTP_404_NOT_FOUND)