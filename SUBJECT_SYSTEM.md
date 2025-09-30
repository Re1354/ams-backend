# Subject & Subject-Department Mapping System

## Overview
This system provides comprehensive subject management and department-subject mapping functionality using PostgreSQL array fields for efficient storage and retrieval.

## 📚 Models

### Subject Model (`models/subjects.py`)
```python
class Subject(models.Model):
    subject_name = models.CharField(max_length=255, unique=True)
    
    class Meta:
        db_table = "subjects"
```

### SubjectDepartment Model (`models/subjects_demartments.py`)
```python
class SubjectDepartment(models.Model):
    department_name = models.CharField(max_length=255, unique=True)
    subject_ids = ArrayField(
        models.IntegerField(), blank=True, default=list
    )  # store subject IDs
    
    class Meta:
        db_table = "subjects_departments"
```

## 🔗 API Endpoints

### Subject Management
- `GET /api/subjects/` - Get all subjects
- `POST /api/subjects/create/` - Create subject (**Superadmin Only**)
- `GET /api/subjects/{id}/` - Get subject by ID
- `PUT/PATCH /api/subjects/{id}/update/` - Update subject (**Superadmin Only**)
- `DELETE /api/subjects/{id}/delete/` - Delete subject (**Superadmin Only**)

### Subject-Department Mapping
- `GET /api/subject-departments/` - Get all department-subject mappings
- `POST /api/subject-departments/create/` - Create mapping (**Superadmin Only**)
- `GET /api/subject-departments/{id}/` - Get mapping by ID
- `GET /api/subject-departments/department/{name}/` - Get subjects by department name
- `PUT/PATCH /api/subject-departments/{id}/update/` - Update mapping (**Superadmin Only**)
- `POST /api/subject-departments/{id}/add-subjects/` - Add subjects to department (**Superadmin Only**)
- `POST /api/subject-departments/{id}/remove-subjects/` - Remove subjects from department (**Superadmin Only**)
- `DELETE /api/subject-departments/{id}/delete/` - Delete mapping (**Superadmin Only**)

## 📝 Usage Examples

### 1. Create Subjects
```bash
POST /api/subjects/create/
Authorization: Bearer <superadmin_jwt_token>
Content-Type: application/json

{
  "subject_name": "Data Structures and Algorithms"
}

# Response:
{
  "success": true,
  "data": {
    "id": 1,
    "subject_name": "Data Structures and Algorithms"
  },
  "message": "Subject \"Data Structures and Algorithms\" created successfully"
}
```

### 2. Get All Subjects
```bash
GET /api/subjects/
Authorization: Bearer <jwt_token>

# Response:
{
  "success": true,
  "data": [
    {
      "id": 1,
      "subject_name": "Data Structures and Algorithms"
    },
    {
      "id": 2,
      "subject_name": "Database Management Systems"
    },
    {
      "id": 3,
      "subject_name": "Computer Networks"
    }
  ],
  "message": "Subjects retrieved successfully"
}
```

### 3. Create Department-Subject Mapping
```bash
POST /api/subject-departments/create/
Authorization: Bearer <superadmin_jwt_token>
Content-Type: application/json

{
  "department_name": "Computer Science",
  "subject_ids": [1, 2, 3, 5, 7]
}

# Response:
{
  "success": true,
  "data": {
    "id": 1,
    "department_name": "Computer Science",
    "subject_ids": [1, 2, 3, 5, 7],
    "subjects": [
      {
        "id": 1,
        "subject_name": "Data Structures and Algorithms"
      },
      {
        "id": 2,
        "subject_name": "Database Management Systems"
      },
      {
        "id": 3,
        "subject_name": "Computer Networks"
      }
    ]
  }
}
```

### 4. Get Subjects by Department
```bash
GET /api/subject-departments/department/Computer%20Science/
Authorization: Bearer <jwt_token>

# Response:
{
  "success": true,
  "data": {
    "id": 1,
    "department_name": "Computer Science",
    "subject_ids": [1, 2, 3, 5, 7],
    "subjects": [
      {
        "id": 1,
        "subject_name": "Data Structures and Algorithms"
      },
      {
        "id": 2,
        "subject_name": "Database Management Systems"
      }
    ]
  }
}
```

### 5. Add Subjects to Department
```bash
POST /api/subject-departments/1/add-subjects/
Authorization: Bearer <superadmin_jwt_token>
Content-Type: application/json

{
  "subject_ids": [8, 9, 10]
}

# Response:
{
  "success": true,
  "data": {
    "id": 1,
    "department_name": "Computer Science",
    "subject_ids": [1, 2, 3, 5, 7, 8, 9, 10],
    "subjects": [...]
  },
  "message": "Subjects added to department \"Computer Science\" successfully"
}
```

### 6. Remove Subjects from Department
```bash
POST /api/subject-departments/1/remove-subjects/
Authorization: Bearer <superadmin_jwt_token>
Content-Type: application/json

{
  "subject_ids": [2, 3]
}

# Response:
{
  "success": true,
  "data": {
    "id": 1,
    "department_name": "Computer Science",
    "subject_ids": [1, 5, 7, 8, 9, 10],
    "subjects": [...]
  },
  "message": "Subjects removed from department \"Computer Science\" successfully"
}
```

## 🛡️ Security Features

### Subject Management Permissions
- **Get Subjects**: Any authenticated user
- **Create/Update/Delete**: Superadmin only

### Department-Subject Mapping Permissions  
- **Get Mappings**: Any authenticated user
- **Create/Update/Delete**: Superadmin only
- **Add/Remove Subjects**: Superadmin only

### Validation Features
- **Unique Subject Names**: Prevents duplicate subjects
- **Unique Department Names**: Prevents duplicate department mappings
- **Foreign Key Validation**: Ensures all subject IDs exist before assignment
- **Array Deduplication**: Automatically prevents duplicate subject assignments

## 🔧 Advanced Features

### Efficient Array Operations
- **Add Subjects**: Uses set union to prevent duplicates
- **Remove Subjects**: Uses set difference for clean removal
- **Bulk Operations**: Handle multiple subject IDs efficiently

### Smart Deletion
- **Subject Deletion**: Automatically removes from all department mappings
- **Department Deletion**: Shows count of affected subject assignments
- **Cascade Warnings**: Informs about related data impact

### Response Format
- **Nested Subject Details**: Shows full subject information in mappings
- **Optimized Queries**: Uses `select_related` and efficient database queries
- **Consistent Error Handling**: Standardized error responses

## 💾 Database Migration

### Run Migrations
```bash
cd amsapp
python manage.py makemigrations
python manage.py migrate
```

### Sample Data Setup
```python
# Create sample subjects
subjects = [
    "Data Structures and Algorithms",
    "Database Management Systems", 
    "Computer Networks",
    "Operating Systems",
    "Software Engineering",
    "Web Development",
    "Mobile App Development",
    "Machine Learning",
    "Artificial Intelligence",
    "Cybersecurity"
]

for subject_name in subjects:
    Subject.objects.get_or_create(subject_name=subject_name)

# Create department mappings
SubjectDepartment.objects.create(
    department_name="Computer Science",
    subject_ids=[1, 2, 3, 4, 5]
)
```

## 📊 Data Structure Benefits

### PostgreSQL Array Field Advantages
- **Performance**: Single query to get all subjects for a department
- **Flexibility**: Easy to add/remove subjects without complex joins
- **Scalability**: Efficient storage for large subject lists
- **Atomic Operations**: All changes in single database transaction

### API Response Efficiency
- **Nested Data**: Complete subject details in single response
- **Reduced Requests**: No need for separate subject detail calls
- **Optimized Serialization**: Smart caching of subject lookups

## 🎯 Integration with Existing System

### Question System Integration
- Filter questions by department subjects
- Subject-based exam generation
- Department-specific question pools

### User System Integration
- Department users see relevant subjects
- Role-based subject access control
- Subject-aware menu filtering

The system provides comprehensive subject management with efficient department mapping using PostgreSQL array fields for optimal performance! 🎉