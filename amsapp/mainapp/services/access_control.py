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

    is_global = getattr(user, 'is_global_access', False)
    access_type = getattr(user, 'access_type', None)
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
