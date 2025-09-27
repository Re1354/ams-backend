from rest_framework import generics
from drf_spectacular.utils import extend_schema

from ..models import Students
from ..serializers import StudentsSerializer


@extend_schema(
    summary="Get all students",
    description="Retrieve all registered students",
    tags=['Students'],
    responses={200: StudentsSerializer(many=True)}
)
class AllStudentsView(generics.ListCreateAPIView):
    """List all students and create new students"""
    queryset = Students.objects.all().order_by('-created_at')
    serializer_class = StudentsSerializer


@extend_schema(
    summary="Student detail",
    description="Retrieve, update or delete a specific student",
    tags=['Students'],
    responses={200: StudentsSerializer}
)
class StudentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get specific student details"""
    queryset = Students.objects.all()
    serializer_class = StudentsSerializer
    lookup_url_kwarg = 'student_id'