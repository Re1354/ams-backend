from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..models.faculty import Faculty
from ..permissions import require_menu_permission
from ..serializers.faculty import FacultySerializer, FacultyCreateSerializer


@extend_schema(
    operation_id='get_all_faculties',
    tags=['Faculties'],
    summary="Get all faculties",
    description="Retrieve all faculties in the system with their names and shortnames.",
    responses={
        200: {
            'description': 'Faculties retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': [
                            {
                                'id': 1,
                                'faculty_name': 'Faculty of Science and Information Technology',
                                'faculty_shortname': 'FSIT'
                            }
                        ],
                        'message': 'Faculties retrieved successfully'
                    }
                }
            }
        }
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_faculties(request):
    """Get all faculties"""
    faculties = Faculty.objects.all().order_by('faculty_name')
    serializer = FacultySerializer(faculties, many=True)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Faculties retrieved successfully'
    })


@extend_schema(
    operation_id='create_faculty',
    tags=['Faculties'],
    summary="Create a new faculty",
    description="Create a new faculty with name and shortname. Requires faculty management write permission.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'faculty_name': {
                    'type': 'string',
                    'description': 'Full name of the faculty',
                    'example': 'Faculty of Science and Information Technology'
                },
                'faculty_shortname': {
                    'type': 'string',
                    'description': 'Short name/abbreviation of the faculty',
                    'example': 'FSIT'
                }
            },
            'required': ['faculty_name', 'faculty_shortname']
        }
    },
    responses={
        201: {
            'description': 'Faculty created successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': {
                            'id': 1,
                            'faculty_name': 'Faculty of Science and Information Technology',
                            'faculty_shortname': 'FSIT'
                        },
                        'message': 'Faculty "Faculty of Science and Information Technology" created successfully'
                    }
                }
            }
        },
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Missing faculty create permission")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_faculty(request):
    """Create a new faculty."""
    denied = require_menu_permission(
        request,
        "/faculty-management",
        "write",
        "You do not have permission to create faculties.",
    )
    if denied:
        return denied

    serializer = FacultyCreateSerializer(data=request.data)
    if serializer.is_valid():
        faculty = serializer.save()
        response_serializer = FacultySerializer(faculty)
        return Response({
            'success': True,
            'data': response_serializer.data,
            'message': f'Faculty "{faculty.faculty_name}" created successfully'
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    operation_id='get_faculty_by_id',
    tags=['Faculties'],
    summary="Get faculty by ID",
    description="Retrieve a specific faculty by its ID with name and shortname.",
    responses={
        200: {
            'description': 'Faculty retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': {
                            'id': 1,
                            'faculty_name': 'Faculty of Science and Information Technology',
                            'faculty_shortname': 'FSIT'
                        },
                        'message': 'Faculty retrieved successfully'
                    }
                }
            }
        },
        404: OpenApiResponse(description="Faculty not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_faculty_by_id(request, faculty_id):
    """Get faculty by ID"""
    faculty = get_object_or_404(Faculty, id=faculty_id)
    serializer = FacultySerializer(faculty)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Faculty retrieved successfully'
    })


@extend_schema(
    operation_id='update_faculty_full',
    tags=['Faculties'],
    summary="Update faculty (PUT)",
    description="Update faculty name and shortname. Requires faculty management edit permission.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'faculty_name': {
                    'type': 'string',
                    'description': 'Full name of the faculty',
                    'example': 'Faculty of Science and Information Technology'
                },
                'faculty_shortname': {
                    'type': 'string',
                    'description': 'Short name/abbreviation of the faculty',
                    'example': 'FSIT'
                }
            },
            'required': ['faculty_name', 'faculty_shortname']
        }
    },
    responses={
        200: {
            'description': 'Faculty updated successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': {
                            'id': 1,
                            'faculty_name': 'Faculty of Science and Information Technology',
                            'faculty_shortname': 'FSIT'
                        },
                        'message': 'Faculty "Faculty of Science and Information Technology" updated successfully'
                    }
                }
            }
        },
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Missing faculty edit permission"),
        404: OpenApiResponse(description="Faculty not found")
    }
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_faculty_full(request, faculty_id):
    """Update faculty completely."""
    denied = require_menu_permission(
        request,
        "/faculty-management",
        "edit",
        "You do not have permission to edit faculties.",
    )
    if denied:
        return denied

    faculty = get_object_or_404(Faculty, id=faculty_id)
    serializer = FacultyCreateSerializer(faculty, data=request.data, partial=False)

    if serializer.is_valid():
        faculty = serializer.save()
        response_serializer = FacultySerializer(faculty)
        return Response({
            'success': True,
            'data': response_serializer.data,
            'message': f'Faculty "{faculty.faculty_name}" updated successfully'
        })
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    operation_id='update_faculty_partial',
    tags=['Faculties'],
    summary="Update faculty (PATCH)",
    description="Partially update faculty name and/or shortname. Requires faculty management edit permission.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'faculty_name': {
                    'type': 'string',
                    'description': 'Full name of the faculty',
                    'example': 'Faculty of Science and Information Technology'
                },
                'faculty_shortname': {
                    'type': 'string',
                    'description': 'Short name/abbreviation of the faculty',
                    'example': 'FSIT'
                }
            }
        }
    },
    responses={
        200: {
            'description': 'Faculty updated successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': {
                            'id': 1,
                            'faculty_name': 'Faculty of Science and Information Technology',
                            'faculty_shortname': 'FSIT'
                        },
                        'message': 'Faculty "Faculty of Science and Information Technology" updated successfully'
                    }
                }
            }
        },
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Missing faculty edit permission"),
        404: OpenApiResponse(description="Faculty not found")
    }
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_faculty_partial(request, faculty_id):
    """Update faculty partially."""
    denied = require_menu_permission(
        request,
        "/faculty-management",
        "edit",
        "You do not have permission to edit faculties.",
    )
    if denied:
        return denied

    faculty = get_object_or_404(Faculty, id=faculty_id)
    serializer = FacultyCreateSerializer(faculty, data=request.data, partial=True)

    if serializer.is_valid():
        faculty = serializer.save()
        response_serializer = FacultySerializer(faculty)
        return Response({
            'success': True,
            'data': response_serializer.data,
            'message': f'Faculty "{faculty.faculty_name}" updated successfully'
        })
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    operation_id='delete_faculty',
    tags=['Faculties'],
    summary="Delete faculty",
    description="Delete a faculty. Requires faculty management delete permission.",
    responses={
        200: OpenApiResponse(description="Faculty deleted successfully"),
        403: OpenApiResponse(description="Missing faculty delete permission"),
        404: OpenApiResponse(description="Faculty not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_faculty(request, faculty_id):
    """Delete faculty."""
    denied = require_menu_permission(
        request,
        "/faculty-management",
        "delete",
        "You do not have permission to delete faculties.",
    )
    if denied:
        return denied

    faculty = get_object_or_404(Faculty, id=faculty_id)
    faculty_name = faculty.faculty_name
    faculty.delete()

    return Response({
        'success': True,
        'message': f'Faculty "{faculty_name}" deleted successfully'
    })
