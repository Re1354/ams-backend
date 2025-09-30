# Department Integration Guide

## Overview
This guide covers the integration of department functionality with user management and authentication system.

## 🏢 Department Model

### Model Structure (`models/departments.py`)
```python
class Department(models.Model):
    department_name = models.CharField(max_length=255, unique=True)
    
    class Meta:
        db_table = "departments"
    
    def __str__(self):
        return self.department_name
```

### User-Department Relationship (`models/user.py`)
```python
class User(models.Model):
    # ... other fields
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='users', null=True, blank=True)
```

## 🔗 API Endpoints

### Department Management
- `GET /api/departments/` - Get all departments
- `POST /api/departments/create/` - Create department (**Superadmin Only**)
- `GET /api/departments/{id}/` - Get department by ID
- `PUT/PATCH /api/departments/{id}/update/` - Update department (**Superadmin Only**)
- `DELETE /api/departments/{id}/delete/` - Delete department (**Superadmin Only**)

## 📝 Authentication Updates

### Login Response (Enhanced)
```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "user": {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "created_at": "2024-01-01T10:00:00Z",
      "role_details": {
        "id": 1,
        "role_name": "superadmin"
      },
      "department_details": {
        "id": 1,
        "department_name": "Computer Science"
      }
    }
  }
}
```

## 👥 User Management Updates

### Create User with Department
```json
POST /api/users/create/
{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "securePassword123",
  "role_id": 2,
  "department_id": 3
}
```

### User Response Format
```json
{
  "success": true,
  "data": {
    "id": 5,
    "username": "john_doe",
    "email": "john@example.com",
    "role_name": "cse_admin",
    "department_name": "Computer Science",
    "created_at": "2024-01-01T10:00:00Z"
  }
}
```

## 🔧 Serializer Updates

### UserSerializer Fields
```python
class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.role_name', read_only=True)
    role_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'password', 
            'role_id', 'role_name', 
            'department_id', 'department_name', 
            'created_at'
        ]
```

## 🛡️ Security Features

### Department CRUD Permissions
- **Get All Departments**: Any authenticated user
- **Create Department**: Superadmin only
- **Update Department**: Superadmin only  
- **Delete Department**: Superadmin only

### Validation
- **Unique Department Names**: Prevents duplicate department names
- **Foreign Key Validation**: Ensures department exists before assignment
- **Cascade Delete Protection**: Shows affected users count on department deletion

## 💾 Database Migration

### Run Migrations
```bash
cd amsapp
python manage.py makemigrations
python manage.py migrate
```

### Sample Department Data
```python
# Create sample departments
departments = [
    "Computer Science",
    "Software Engineering", 
    "Electronics & Communication",
    "Electrical Engineering",
    "Mechanical Engineering",
    "Civil Engineering"
]

for dept_name in departments:
    Department.objects.get_or_create(department_name=dept_name)
```

## 🎯 Usage Examples

### 1. Get All Departments
```bash
GET /api/departments/
Authorization: Bearer <jwt_token>

Response:
{
  "success": true,
  "data": [
    {
      "id": 1,
      "department_name": "Computer Science"
    },
    {
      "id": 2, 
      "department_name": "Software Engineering"
    }
  ]
}
```

### 2. Create Department (Superadmin)
```bash
POST /api/departments/create/
Authorization: Bearer <superadmin_jwt_token>
Content-Type: application/json

{
  "department_name": "Data Science"
}
```

### 3. Create User with Department
```bash
POST /api/users/create/
Authorization: Bearer <superadmin_jwt_token>
Content-Type: application/json

{
  "username": "alice_cs",
  "email": "alice@university.edu",
  "password": "securePass123",
  "role_id": 2,
  "department_id": 1
}
```

### 4. Login and Get Department Info
```bash
POST /api/auth/login/
Content-Type: application/json

{
  "username": "alice_cs",
  "password": "securePass123"
}

# Response includes department_details in user object
```

## 📋 Integration Workflow

1. **Setup Departments**: Superadmin creates department list
2. **Assign Users**: Create/update users with department assignments
3. **Login Enhanced**: Users receive department info on login
4. **Frontend Integration**: Use department data for UI customization
5. **Role-Based Access**: Combine with existing role system for permissions

## 🔄 Backward Compatibility

- **Existing Users**: Can have null department (optional field)
- **API Compatibility**: All existing endpoints continue to work
- **Gradual Migration**: Departments can be assigned over time

The system now provides complete department-aware user management while maintaining all existing functionality! 🎉