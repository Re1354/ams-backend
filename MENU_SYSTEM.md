# Menu Management System

This system provides role-based menu access control for the frontend application.

## Models Created

### Menu Model (`models/menu.py`)
- `label`: Menu display name
- `icon`: Frontend icon identifier 
- `link`: Frontend route path

### RoleMenu Model (`models/role_menu.py`)
- `role`: Foreign key to Role
- `menu`: Foreign key to Menu
- `permissions`: JSON field with CRUD permissions
- Unique constraint on (role, menu) combination

## Setup Instructions

### 1. Run Migrations
```bash
cd amsapp
python manage.py makemigrations
python manage.py migrate
```

### 2. Seed Initial Data
```bash
python manage.py seed_menus
```

This will create:
- 7 default menus (Dashboard, Create Questions, All Questions, Students, Exam Schedule, Users Management, Role Management)
- Superadmin role (if not exists)
- Assign all menus to superadmin with full permissions

## API Endpoints

### Menu Management
- `GET /api/menus/` - Get all available menus
- `POST /api/menus/create/` - Create a new menu (**Superadmin Only**)
- `PUT/PATCH /api/menus/{menu_id}/update/` - Update existing menu (**Superadmin Only**)
- `DELETE /api/menus/{menu_id}/delete/` - Delete menu (**Superadmin Only**)
- `GET /api/menus/user/` - Get current user's accessible menus
- `GET /api/roles/{role_id}/menus/` - Get menus for specific role

### Role-Menu Assignment (Superadmin Only)
- `POST /api/roles/assign-menus/` - Assign menus to role with permissions
- `DELETE /api/roles/{role_id}/menus/{menu_id}/remove/` - Remove menu from role

## Usage Examples

### 1. Get User's Menus (for Frontend)
```javascript
// GET /api/menus/user/
// Response:
{
  "success": true,
  "data": [
    {
      "id": 1,
      "title": "Dashboard",
      "icon": "LayoutDashboard", 
      "link": "/dashboard",
      "permissions": {
        "read": true,
        "write": true,
        "edit": true,
        "delete": true
      }
    }
  ],
  "role": "superadmin"
}
```

### 2. Create New Menu (Superadmin)
```javascript
// POST /api/menus/create/
{
  "label": "Reports",
  "icon": "FileBarChart",
  "link": "/reports"
}

// Response:
{
  "success": true,
  "data": {
    "id": 8,
    "title": "Reports",
    "icon": "FileBarChart", 
    "link": "/reports",
    "label": "Reports"
  },
  "message": "Menu \"Reports\" created successfully"
}
```

### 3. Update Menu (Superadmin)
```javascript
// PUT /api/menus/8/update/
{
  "label": "Advanced Reports",
  "icon": "FileBarChart2",
  "link": "/advanced-reports"
}
```

### 4. Assign Menus to Role (Superadmin)
```javascript
// POST /api/roles/assign-menus/
{
  "role_id": 2,
  "menus": [
    {
      "menu_id": 1,
      "permissions": {
        "read": true,
        "write": false,
        "edit": false,
        "delete": false
      }
    },
    {
      "menu_id": 4,
      "permissions": {
        "read": true,
        "write": true,
        "edit": true,
        "delete": false
      }
    }
  ]
}
```

## Permission Structure

Each menu assignment includes four permissions:
- `read`: Can view the page/feature
- `write`: Can create new items
- `edit`: Can modify existing items  
- `delete`: Can remove items

## Frontend Integration

The API response format is designed to work directly with your frontend menu structure:

```javascript
const menuItems = [
  {
    title: 'Dashboard',
    icon: LayoutDashboard,
    id: 'dashboard',
  }
];
```

## Security Features

1. **Superadmin Only**: Only users with 'superadmin' role can assign/remove menus
2. **JWT Authentication**: All endpoints require valid JWT token
3. **Role Validation**: Menu access is validated against user's role
4. **Unique Constraints**: Prevents duplicate role-menu assignments

## Database Tables

- `menus` - Menu definitions
- `role_menus` - Role-menu assignments with permissions
- `roles` - User roles (existing)
- `users` - Users with role assignments (existing)

## Default Menus Created

1. Dashboard (`/dashboard`)
2. Create Questions (`/create-questions`) 
3. All Questions (`/all-questions`)
4. Students (`/students`)
5. Exam Schedule (`/exam-schedule`)
6. Users Management (`/users-management`)
7. Role Management (`/role-management`)

All menus are initially assigned to the superadmin role with full permissions.