"""
Comprehensive test suite for the Admission Threshold & Result System

Tests cover:
1. Setting threshold mappings
2. Calculating admission results based on thresholds
3. Filtering and retrieving results
4. Publishing results
5. Edge cases and validations
"""

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import timedelta

from ..models import (
    Exam, Students, Department, Role, User,
    DepartmentThreshold, AdmissionResult, 
    ExamQuestion, Submission, ScrappedQuestion
)
from ..models.viva_marks import VivaMarks
from ..tokens import get_tokens_for_user


class AdmissionSystemTestCase(APITestCase):
    """Test suite for Admission Threshold & Result System"""
    
    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        # Create role
        self.admin_role = Role.objects.create(
            role_name='Admin',
            role_description='Administrator'
        )
        
        # Create departments
        self.dept_cse = Department.objects.create(
            department_name='Computer Science & Engineering',
            department_shortname='CSE'
        )
        self.dept_eee = Department.objects.create(
            department_name='Electrical & Electronic Engineering',
            department_shortname='EEE'
        )
        
        # Create admin user
        self.admin_user = User.objects.create(
            username='admin',
            email='admin@test.com',
            password=make_password('admin123'),
            role=self.admin_role,
            department=self.dept_cse
        )
        
        # Get JWT token for authentication
        tokens = get_tokens_for_user(self.admin_user)
        self.access_token = tokens['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        
        # Create exam
        self.exam = Exam.objects.create(
            department='CSE',
            semester='Fall-2025',
            total_questions=100,
            present_question=100,
            total_marks=100,
            duration_minutes=120
        )
        
        # Create students
        self.student1 = Students.objects.create(
            username='student1',
            password='pass123',
            f_id='F001',
            full_name='Student One',
            email='student1@test.com',
            department_shortname='CSE'
        )
        
        self.student2 = Students.objects.create(
            username='student2',
            password='pass123',
            f_id='F002',
            full_name='Student Two',
            email='student2@test.com',
            department_shortname='CSE'
        )
        
        self.student3 = Students.objects.create(
            username='student3',
            password='pass123',
            f_id='F003',
            full_name='Student Three',
            email='student3@test.com',
            department_shortname='EEE'
        )
        
        # Create exam questions
        self.create_exam_questions()
    
    def create_exam_questions(self):
        """Create exam questions for testing"""
        # Create 10 questions worth 10 marks each (total 100 marks)
        for i in range(10):
            ExamQuestion.objects.create(
                exam=self.exam,
                subject='Mathematics',
                question_text=f'Question {i+1}',
                type='option',
                options={'A': '1', 'B': '2', 'C': '3', 'D': '4'},
                answer=['A'],
                marks=10,
                semester='Fall-2025',
                department_shortname='CSE'
            )
    
    def create_submissions_for_student(self, student, correct_count):
        """Helper to create submissions for a student"""
        questions = ExamQuestion.objects.filter(exam=self.exam)[:correct_count + 5]
        
        for i, question in enumerate(questions):
            is_correct = i < correct_count
            Submission.objects.create(
                student=student,
                exam=self.exam,
                question=question,
                answer='A' if is_correct else 'B',  # 'A' is correct, 'B' is wrong
                is_correct=is_correct
            )
    
    # Test 1: Setting Threshold Mappings
    def test_set_threshold_mapping_success(self):
        """Test setting threshold mappings successfully"""
        data = {
            'exam_id': self.exam.id,
            'mappings': [
                {'department_id': self.dept_cse.id, 'threshold': 60.0},
                {'department_id': self.dept_eee.id, 'threshold': 75.0}
            ]
        }
        
        response = self.client.post('/api/admission/threshold-mapping/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['created_count'], 2)
        self.assertEqual(response.data['updated_count'], 0)
        
        # Verify in database
        self.assertEqual(
            DepartmentThreshold.objects.filter(exam=self.exam).count(), 
            2
        )
    
    def test_update_existing_threshold(self):
        """Test updating existing threshold mapping"""
        # Create initial threshold
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_cse,
            min_threshold_mark=50.0
        )
        
        # Update threshold
        data = {
            'exam_id': self.exam.id,
            'mappings': [
                {'department_id': self.dept_cse.id, 'threshold': 65.0}
            ]
        }
        
        response = self.client.post('/api/admission/threshold-mapping/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['created_count'], 0)
        self.assertEqual(response.data['updated_count'], 1)
        
        # Verify updated value
        threshold = DepartmentThreshold.objects.get(
            exam=self.exam,
            department=self.dept_cse
        )
        self.assertEqual(threshold.min_threshold_mark, 65.0)
    
    def test_invalid_threshold_exceeds_exam_marks(self):
        """Test validation: threshold cannot exceed exam total marks"""
        data = {
            'exam_id': self.exam.id,
            'mappings': [
                {'department_id': self.dept_cse.id, 'threshold': 150.0}  # > 100
            ]
        }
        
        response = self.client.post('/api/admission/threshold-mapping/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
    
    def test_invalid_negative_threshold(self):
        """Test validation: threshold must be positive"""
        data = {
            'exam_id': self.exam.id,
            'mappings': [
                {'department_id': self.dept_cse.id, 'threshold': -10.0}
            ]
        }
        
        response = self.client.post('/api/admission/threshold-mapping/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_get_threshold_mappings(self):
        """Test retrieving threshold mappings"""
        # Create thresholds
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_cse,
            min_threshold_mark=60.0
        )
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_eee,
            min_threshold_mark=70.0
        )
        
        response = self.client.get('/api/admission/get-threshold-mapping/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['count'], 2)
    
    def test_get_threshold_mappings_filtered_by_exam(self):
        """Test filtering threshold mappings by exam"""
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_cse,
            min_threshold_mark=60.0
        )
        
        response = self.client.get(
            f'/api/admission/get-threshold-mapping/?exam_id={self.exam.id}'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
    
    # Test 2: Calculating Admission Results
    def test_calculate_results_student_passes_threshold(self):
        """Test student with 50 marks passes if threshold is 40"""
        # Set threshold to 40
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_cse,
            min_threshold_mark=40.0
        )
        
        # Create submissions: 5 correct answers = 50 marks (5 x 10)
        self.create_submissions_for_student(self.student1, correct_count=5)
        
        # Calculate results
        data = {'exam_id': self.exam.id}
        response = self.client.post('/api/admission/calculate-results/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['processed_count'], 1)
        self.assertEqual(response.data['selected_count'], 1)
        self.assertEqual(response.data['not_selected_count'], 0)
        
        # Verify in database
        result = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        self.assertEqual(result.mcq_marks, 50.0)
        self.assertTrue(result.is_selected)
        self.assertEqual(result.threshold_applied, 40.0)
    
    def test_calculate_results_student_fails_threshold(self):
        """Test student with 50 marks fails if threshold is 60"""
        # Set threshold to 60
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_cse,
            min_threshold_mark=60.0
        )
        
        # Create submissions: 5 correct answers = 50 marks
        self.create_submissions_for_student(self.student1, correct_count=5)
        
        # Calculate results
        data = {'exam_id': self.exam.id}
        response = self.client.post('/api/admission/calculate-results/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['selected_count'], 0)
        self.assertEqual(response.data['not_selected_count'], 1)
        
        # Verify in database
        result = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        self.assertEqual(result.mcq_marks, 50.0)
        self.assertFalse(result.is_selected)
        self.assertEqual(result.threshold_applied, 60.0)
    
    def test_calculate_results_with_viva_marks(self):
        """Test calculation includes viva marks"""
        # Set threshold
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_cse,
            min_threshold_mark=60.0
        )
        
        # Create submissions: 4 correct = 40 marks
        self.create_submissions_for_student(self.student1, correct_count=4)
        
        # Add viva marks: 25 marks
        VivaMarks.objects.create(
            student=self.student1,
            marks=25,
            rubrics_marks={'Communication': 10, 'Technical': 15}
        )
        
        # Calculate results
        data = {'exam_id': self.exam.id}
        response = self.client.post('/api/admission/calculate-results/', data, format='json')
        
        # Total = 40 (MCQ) + 25 (Viva) = 65 >= 60 (threshold) → Selected
        result = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        self.assertEqual(result.mcq_marks, 40.0)
        self.assertEqual(result.viva_marks, 25.0)
        self.assertEqual(result.total_marks, 65.0)
        self.assertTrue(result.is_selected)
    
    def test_calculate_results_multiple_students(self):
        """Test calculating results for multiple students"""
        # Set thresholds
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_cse,
            min_threshold_mark=60.0
        )
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_eee,
            min_threshold_mark=70.0
        )
        
        # Student 1 (CSE): 7 correct = 70 marks (passes)
        self.create_submissions_for_student(self.student1, correct_count=7)
        
        # Student 2 (CSE): 5 correct = 50 marks (fails)
        self.create_submissions_for_student(self.student2, correct_count=5)
        
        # Student 3 (EEE): 8 correct = 80 marks (passes)
        self.create_submissions_for_student(self.student3, correct_count=8)
        
        # Calculate results
        data = {'exam_id': self.exam.id}
        response = self.client.post('/api/admission/calculate-results/', data, format='json')
        
        self.assertEqual(response.data['processed_count'], 3)
        self.assertEqual(response.data['selected_count'], 2)
        self.assertEqual(response.data['not_selected_count'], 1)
    
    def test_calculate_results_no_thresholds_set(self):
        """Test calculation fails when no thresholds are set"""
        self.create_submissions_for_student(self.student1, correct_count=5)
        
        data = {'exam_id': self.exam.id}
        response = self.client.post('/api/admission/calculate-results/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
    
    # Test 3: Retrieving Results
    def test_get_admission_results(self):
        """Test retrieving admission results"""
        # Create result
        AdmissionResult.objects.create(
            exam=self.exam,
            student=self.student1,
            department=self.dept_cse,
            mcq_marks=70.0,
            viva_marks=20.0,
            total_marks=90.0,
            is_selected=True,
            threshold_applied=60.0,
            status='PENDING'
        )
        
        response = self.client.get('/api/admission/results/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_filter_results_by_selection_status(self):
        """Test filtering results by is_selected"""
        AdmissionResult.objects.create(
            exam=self.exam,
            student=self.student1,
            department=self.dept_cse,
            mcq_marks=70.0,
            viva_marks=20.0,
            is_selected=True,
            threshold_applied=60.0
        )
        AdmissionResult.objects.create(
            exam=self.exam,
            student=self.student2,
            department=self.dept_cse,
            mcq_marks=40.0,
            viva_marks=10.0,
            is_selected=False,
            threshold_applied=60.0
        )
        
        response = self.client.get('/api/admission/results/?is_selected=true')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check that only selected students are returned
        self.assertEqual(len(response.data['results']), 1)
    
    def test_get_student_specific_result(self):
        """Test getting result for specific student"""
        AdmissionResult.objects.create(
            exam=self.exam,
            student=self.student1,
            department=self.dept_cse,
            mcq_marks=70.0,
            viva_marks=20.0,
            is_selected=True,
            threshold_applied=60.0
        )
        
        response = self.client.get(
            f'/api/admission/results/student/{self.exam.id}/{self.student1.id}/'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['student_username'], 'student1')
    
    # Test 4: Publishing Results
    def test_publish_admission_results(self):
        """Test publishing admission results"""
        # Create pending results
        AdmissionResult.objects.create(
            exam=self.exam,
            student=self.student1,
            department=self.dept_cse,
            mcq_marks=70.0,
            viva_marks=20.0,
            is_selected=True,
            status='PENDING'
        )
        
        data = {'exam_id': self.exam.id}
        response = self.client.post('/api/admission/publish-results/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['published_count'], 1)
        
        # Verify status changed
        result = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        self.assertEqual(result.status, 'PUBLISHED')
    
    # Test 5: Recalculate Single Student
    def test_recalculate_single_student_result(self):
        """Test recalculating result for a single student"""
        # Set threshold
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_cse,
            min_threshold_mark=60.0
        )
        
        # Create submissions
        self.create_submissions_for_student(self.student1, correct_count=7)
        
        response = self.client.post(
            f'/api/admission/recalculate/{self.exam.id}/{self.student1.id}/',
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        # Verify result was created/updated
        result = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        self.assertEqual(result.mcq_marks, 70.0)
        self.assertTrue(result.is_selected)
