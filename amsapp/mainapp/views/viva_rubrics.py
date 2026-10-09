from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ..models import VivaRubrics, Department
from ..serializers.viva_rubrics import (
    VivaRubricsSerializer, VivaRubricsCreateSerializer, VivaRubricsUpdateSerializer
)
from ..authentication import CustomJWTAuthentication


@extend_schema(
    operation_id='create_viva_rubrics',
    tags=['Viva Rubrics Management'],
    summary="Create new viva rubrics",
    description="Create new viva rubrics for a department with marking criteria",
    request=VivaRubricsCreateSerializer,
    responses={
        201: OpenApiResponse(
            response=VivaRubricsSerializer,
            description="Viva rubrics created successfully"
        ),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Department not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def create_viva_rubrics(request):
    """Create new viva rubrics"""
    
    serializer = VivaRubricsCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            viva_rubrics = serializer.save()
            
            return Response({
                'success': True,
                'message': 'Viva rubrics created successfully',
                'data': VivaRubricsSerializer(viva_rubrics).data
            }, status=status.HTTP_201_CREATED)
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error creating viva rubrics: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='get_all_viva_rubrics',
    tags=['Viva Rubrics Management'],
    summary="Get all viva rubrics",
    description="Retrieve all viva rubrics with optional filtering by department",
    parameters=[
        OpenApiParameter(name='department_id', description='Filter by department ID', required=False, type=int),
        OpenApiParameter(name='department_name', description='Filter by department name', required=False, type=str),
    ],
    responses={
        200: OpenApiResponse(
            response=VivaRubricsSerializer(many=True),
            description="Viva rubrics retrieved successfully"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_all_viva_rubrics(request):
    """Get all viva rubrics with optional filtering"""
    
    user = request.user
    custom_user = user.custom_user if hasattr(user, 'custom_user') else None
    from ..services.access_control import get_user_access_scope
    scope = get_user_access_scope(custom_user)
    
    if scope['is_global']:
        viva_rubrics = VivaRubrics.objects.select_related('department').all()
    else:
        if scope['department_ids']:
            viva_rubrics = VivaRubrics.objects.select_related('department').filter(department_id__in=scope['department_ids'])
        else:
            viva_rubrics = VivaRubrics.objects.none()
    
    # Apply filters
    department_id = request.query_params.get('department_id')
    department_name = request.query_params.get('department_name')
    
    if department_id:
        viva_rubrics = viva_rubrics.filter(department_id=department_id)
    
    if department_name:
        viva_rubrics = viva_rubrics.filter(department__department_name__icontains=department_name)
    
    # Order by department name
    viva_rubrics = viva_rubrics.order_by('department__department_name', '-id')
    
    serializer = VivaRubricsSerializer(viva_rubrics, many=True)
    return Response({
        'success': True,
        'count': viva_rubrics.count(),
        'rubrics': serializer.data,
        'message': f'Found {viva_rubrics.count()} viva rubrics'
    })


@extend_schema(
    operation_id='get_viva_rubrics_by_id',
    tags=['Viva Rubrics Management'],
    summary="Get viva rubrics by ID",
    description="Retrieve a specific viva rubrics by its ID",
    responses={
        200: OpenApiResponse(
            response=VivaRubricsSerializer,
            description="Viva rubrics retrieved successfully"
        ),
        404: OpenApiResponse(description="Viva rubrics not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_viva_rubrics_by_id(request, rubrics_id):
    """Get viva rubrics by ID"""
    
    try:
        viva_rubrics = VivaRubrics.objects.select_related('department').get(id=rubrics_id)
        
        user = request.user
        custom_user = user.custom_user if hasattr(user, 'custom_user') else None
        from ..services.access_control import get_user_access_scope
        scope = get_user_access_scope(custom_user)
        
        if not scope['is_global']:
            if not scope['department_ids'] or viva_rubrics.department_id not in scope['department_ids']:
                return Response(
                    {"success": False, "message": "You do not have access to this department's rubrics."},
                    status=403
                )

        serializer = VivaRubricsSerializer(viva_rubrics)
        return Response({
            'success': True,
            'data': serializer.data,
            'message': 'Viva rubrics retrieved successfully'
        })
    except VivaRubrics.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Viva rubrics not found'
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    operation_id='get_viva_rubrics_by_department',
    tags=['Viva Rubrics Management'],
    summary="Get viva rubrics by department",
    description="Retrieve all viva rubrics for a specific department",
    responses={
        200: OpenApiResponse(
            response=VivaRubricsSerializer(many=True),
            description="Department viva rubrics retrieved successfully"
        ),
        404: OpenApiResponse(description="Department not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_viva_rubrics_by_department(request, department_id):
    """Get all viva rubrics for a specific department"""
    
    try:
        # Verify department exists
        department = Department.objects.get(id=department_id)
        
        user = request.user
        custom_user = user.custom_user if hasattr(user, 'custom_user') else None
        from ..services.access_control import get_user_access_scope
        scope = get_user_access_scope(custom_user)
        
        if not scope['is_global']:
            if not scope['department_ids'] or department_id not in scope['department_ids']:
                return Response(
                    {"success": False, "message": "You do not have access to this department."},
                    status=403
                )
    except Department.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Department not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    viva_rubrics = VivaRubrics.objects.filter(
        department=department
    ).select_related('department').order_by('-id')
    
    serializer = VivaRubricsSerializer(viva_rubrics, many=True)
    return Response({
        'success': True,
        'department_info': {
            'id': department.id,
            'name': department.department_name,
            'shortname': department.department_shortname
        },
        'count': viva_rubrics.count(),
        'rubrics': serializer.data,
        'message': f'Found {viva_rubrics.count()} viva rubrics for {department.department_name}'
    })


@extend_schema(
    operation_id='update_viva_rubrics',
    tags=['Viva Rubrics Management'],
    summary="Update viva rubrics",
    description="Update an existing viva rubrics by ID",
    request=VivaRubricsUpdateSerializer,
    responses={
        200: OpenApiResponse(
            response=VivaRubricsSerializer,
            description="Viva rubrics updated successfully"
        ),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Viva rubrics not found")
    }
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def update_viva_rubrics(request, rubrics_id):
    """Update viva rubrics by ID"""
    
    try:
        viva_rubrics = VivaRubrics.objects.get(id=rubrics_id)
    except VivaRubrics.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Viva rubrics not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    serializer = VivaRubricsUpdateSerializer(viva_rubrics, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            updated_rubrics = serializer.save()
            
            return Response({
                'success': True,
                'message': 'Viva rubrics updated successfully',
                'data': VivaRubricsSerializer(updated_rubrics).data
            })
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error updating viva rubrics: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='delete_viva_rubrics',
    tags=['Viva Rubrics Management'],
    summary="Delete viva rubrics",
    description="Delete an existing viva rubrics by ID",
    responses={
        200: OpenApiResponse(description="Viva rubrics deleted successfully"),
        404: OpenApiResponse(description="Viva rubrics not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def delete_viva_rubrics(request, rubrics_id):
    """Delete viva rubrics by ID"""
    
    try:
        viva_rubrics = VivaRubrics.objects.get(id=rubrics_id)
        
        rubrics_info = {
            'id': viva_rubrics.id,
            'department_name': viva_rubrics.department.department_name,
            'marks': viva_rubrics.marks
        }
        
        viva_rubrics.delete()
        
        return Response({
            'success': True,
            'message': 'Viva rubrics deleted successfully',
            'deleted_rubrics': rubrics_info
        })
        
    except VivaRubrics.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Viva rubrics not found'
        }, status=status.HTTP_404_NOT_FOUND)