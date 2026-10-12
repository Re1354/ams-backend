from mainapp.models.faculties_departments import FacultyDepartment


def get_user_access_scope(user):
    """
    Returns the user's access scope based on their access_type:
    GLOBAL: Access to all departments.
    FACULTY: Access to all departments within their assigned faculty.
    DEPARTMENT: Access only to their assigned department.
    
    Returns a dict:
    {
        'is_global': bool,
        'department_ids': list of int (or None if global),
        'access_type': str
    }
    """
    if not user:
        return {'is_global': False, 'department_ids': [], 'access_type': 'NONE'}

    # Superadmin role always receives full global access
    role = getattr(user, 'role', None)
    role_name = getattr(role, 'role_name', None) or getattr(role, 'name', None)
    if role_name and str(role_name).lower() == 'superadmin':
        return {'is_global': True, 'department_ids': None, 'access_type': 'GLOBAL'}

    is_global = getattr(user, 'is_global_access', False)
    access_type = str(getattr(user, 'access_type', '') or '').strip().upper()
    faculty_id = getattr(user, 'faculty_id', None)
    department_id = getattr(user, 'department_id', None)

    if is_global or access_type == 'GLOBAL' or getattr(user, 'is_superuser', False):
        return {'is_global': True, 'department_ids': None, 'access_type': 'GLOBAL'}
        
    if access_type == 'FACULTY' and faculty_id:
        # Get all departments mapped to this faculty
        faculty_dept = FacultyDepartment.objects.filter(faculty_id=faculty_id).first()
        if faculty_dept and faculty_dept.department_ids:
            return {'is_global': False, 'department_ids': faculty_dept.department_ids, 'access_type': 'FACULTY'}
        # If no departments mapped to the faculty, return empty list
        return {'is_global': False, 'department_ids': [], 'access_type': 'FACULTY'}
        
    if access_type == 'DEPARTMENT' and department_id:
        return {'is_global': False, 'department_ids': [department_id], 'access_type': 'DEPARTMENT'}
        
    # Default fallback
    return {'is_global': False, 'department_ids': [], 'access_type': 'NONE'}


def get_faculty_for_department(department_id):
    """
    Returns the Faculty instance associated with the given department_id,
    or None if the department is not mapped to any faculty.
    """
    if not department_id:
        return None
    mapping = FacultyDepartment.objects.filter(
        department_ids__contains=[department_id]
    ).select_related('faculty').first()
    return mapping.faculty if mapping else None


def get_departments_for_faculty(faculty_id):
    """
    Returns the list of department IDs mapped to the given faculty_id.
    """
    if not faculty_id:
        return []
    mapping = FacultyDepartment.objects.filter(faculty_id=faculty_id).first()
    return mapping.department_ids if mapping and mapping.department_ids else []


def get_subjects_for_department(department_id):
    """
    Dual-resolution helper:
    1. Looks up parent Faculty for the department. If the faculty has SubjectFaculty mapping, returns its subject IDs.
    2. Fallback: Checks legacy department-level SubjectDepartment mapping.
    """
    if not department_id:
        return []

    from mainapp.models.subject_faculty import SubjectFaculty
    from mainapp.models.subjects_demartments import SubjectDepartment

    faculty = get_faculty_for_department(department_id)
    if faculty:
        faculty_mapping = SubjectFaculty.objects.filter(faculty=faculty).first()
        if faculty_mapping and faculty_mapping.subject_ids:
            return list(faculty_mapping.subject_ids)

    # Fallback to department-level mapping
    dept_mapping = SubjectDepartment.objects.filter(department_id=department_id).first()
    if dept_mapping and dept_mapping.subject_ids:
        return list(dept_mapping.subject_ids)

    return []


def get_subjects_for_faculty(faculty_id):
    """
    Returns the list of subject IDs mapped to the given faculty_id.
    Falls back to any department-level subject mapping within the faculty if unmapped.
    """
    if not faculty_id:
        return []

    from mainapp.models.subject_faculty import SubjectFaculty
    from mainapp.models.subjects_demartments import SubjectDepartment

    faculty_mapping = SubjectFaculty.objects.filter(faculty_id=faculty_id).first()
    if faculty_mapping and faculty_mapping.subject_ids:
        return list(faculty_mapping.subject_ids)

    # Fallback: inspect departments under this faculty
    dept_ids = get_departments_for_faculty(faculty_id)
    if dept_ids:
        for dept_id in dept_ids:
            dept_mapping = SubjectDepartment.objects.filter(department_id=dept_id).first()
            if dept_mapping and dept_mapping.subject_ids:
                return list(dept_mapping.subject_ids)

    return []
