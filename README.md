# AMS DIU Backend - Academic Management System

## Project Overview

AMS DIU Backend is a comprehensive Academic Management System built with Django REST Framework for managing university admission processes and exam operations. The system provides robust APIs for admission threshold management, exam creation and scheduling, student-teacher assignments, viva examination handling, and dynamic result calculation based on department-specific criteria.

The platform supports role-based access control with features including question bank management, automated exam generation, real-time result processing, and multi-departmental admission result publication. It integrates JWT authentication, PostgreSQL database, and is deployed on Render with full API documentation via Swagger/OpenAPI.

## Key Features

- **Admission Management:** Dynamic threshold setting and automated result calculation with department-based selection criteria
- **Exam System:** Comprehensive exam creation, scheduling, and question management with MCQ and viva support
- **Role-Based Access:** Granular permission system for superadmin, teachers, and students with menu-based navigation
- **Student Management:** Student registration, assignment tracking, and performance monitoring
- **Viva Management:** Complete viva examination workflow with rubrics, marks distribution, and teacher-student assignments
- **Results Processing:** Automated calculation of admission results combining MCQ and viva marks with publication controls

## Technology Stack

- **Backend:** Django 5.2.6, Django REST Framework
- **Database:** PostgreSQL (Production), SQLite (Development)
- **Authentication:** JWT (djangorestframework-simplejwt)
- **API Documentation:** drf-spectacular (Swagger/OpenAPI)
- **Deployment:** Render, WhiteNoise for static files
- **CORS:** django-cors-headers for frontend integration

## Live API Documentation

- **Swagger UI:** `https://ams-diu-backend.onrender.com/api/schema/swagger-ui/`
- **API Endpoints:** See [newapi.md](newapi.md) for detailed documentation

## Quick Start

```bash
# Clone the repository
git clone https://github.com/morsalin101/ams-diu-backend.git
cd ams-diu-backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Navigate to project directory
cd amsapp

# Run migrations
python manage.py migrate

# Seed initial data (menus and roles)
python manage.py seed_menus

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

## API Modules

1. **Authentication & Authorization** - Login, token refresh, role management
2. **Question Management** - Question bank, scraping, blocklist
3. **Exam Management** - Exam creation, scheduling, question assignment
4. **Student Management** - Registration, assignment, results
5. **Teacher Management** - User management, student assignments, schedules
6. **Department & Subject** - Department setup, subject mapping
7. **Admission System** - Threshold management, result calculation, publication
8. **Viva Management** - Rubrics, assignments, marks entry
9. **Results & Reports** - Result processing, publication, analytics

## Environment Variables

```env
SECRET_KEY=your-secret-key
DEBUG=False
DB_NAME=your-database-name
DB_USER=your-database-user
DB_PASSWORD=your-database-password
DB_HOST=your-database-host
DB_PORT=5432
DATABASE_URL=your-full-database-url
```

## Project Structure

```
ams-diu-backend/
├── amsapp/
│   ├── mainapp/
│   │   ├── models/          # Database models
│   │   ├── views/           # API endpoints
│   │   ├── serializers/     # Data serializers
│   │   ├── services/        # Business logic
│   │   ├── management/      # Custom commands
│   │   └── migrations/      # Database migrations
│   ├── amsapp/             # Project settings
│   └── manage.py           # Django management
├── requirements.txt
├── runtime.txt
├── newapi.md              # API documentation
└── README.md
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is developed for academic purposes at Daffodil International University.

## Contact

For any queries or support, please contact the development team.

---

**Last Updated:** December 17, 2025
