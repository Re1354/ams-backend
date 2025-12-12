# 🚀 Quick Start Guide - Admission System Setup

## Prerequisites Checklist
- ✅ Django project running
- ✅ PostgreSQL database configured
- ✅ Existing models (Exam, Students, Department) in place
- ✅ Virtual environment activated

---

## Step-by-Step Setup

### 1. Create Database Migrations
```powershell
cd "C:\Users\Shahadat Imti\Desktop\ams diu --force\ams-diu-backend\amsapp"
python manage.py makemigrations mainapp
```

**Expected Output:**
```
Migrations for 'mainapp':
  mainapp/migrations/00XX_department_threshold_admission_result.py
    - Create model DepartmentThreshold
    - Create model AdmissionResult
```

### 2. Apply Migrations
```powershell
python manage.py migrate mainapp
```

**Expected Output:**
```
Running migrations:
  Applying mainapp.00XX_department_threshold_admission_result... OK
```

### 3. Verify Tables Created
```powershell
python manage.py dbshell
```

Then in PostgreSQL:
```sql
-- Check if tables exist
\dt department_threshold
\dt admission_result

-- Verify structure
\d department_threshold
\d admission_result

-- Exit
\q
```

---

## 4. Test the Implementation

### Run Tests
```powershell
# Run only admission system tests
python manage.py test mainapp.tests.test_admission_system -v 2

# Run all tests
python manage.py test mainapp
```

**Expected:** All 17 tests should pass ✅

---

## 5. Quick API Test (Manual)

### Start Server
```powershell
python manage.py runserver
```

### Test Endpoints (Using Postman/Thunder Client/curl)

**1. Login to get JWT token:**
```http
POST http://localhost:8000/api/auth/login/
Content-Type: application/json

{
  "username": "your_admin_username",
  "password": "your_password"
}
```

Save the `access` token from response.

**2. Set Threshold Mapping:**
```http
POST http://localhost:8000/api/admission/threshold-mapping/
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json

{
  "exam_id": 1,
  "mappings": [
    {"department_id": 1, "threshold": 60.0}
  ]
}
```

**3. Get Threshold Mappings:**
```http
GET http://localhost:8000/api/admission/get-threshold-mapping/?exam_id=1
Authorization: Bearer YOUR_ACCESS_TOKEN
```

---

## 6. Verify Admin Panel

### Access Admin
```
http://localhost:8000/admin/
```

### Check Models
1. Navigate to **Department Thresholds**
2. Navigate to **Admission Results**
3. Verify you can create/edit/delete records

---

## 7. Integration Verification

### Check Existing Endpoints Still Work
```http
# Test existing exam endpoint
GET http://localhost:8000/api/all-exams/
Authorization: Bearer YOUR_ACCESS_TOKEN

# Test existing students endpoint
GET http://localhost:8000/api/students/
Authorization: Bearer YOUR_ACCESS_TOKEN

# Test existing results endpoint
GET http://localhost:8000/api/get-all-results-by-teacher/1/
Authorization: Bearer YOUR_ACCESS_TOKEN
```

All should work without errors! ✅

---

## 8. API Documentation

### View Swagger Documentation
```
http://localhost:8000/api/schema/swagger-ui/
```

**Search for:** "Admission Management" tag

You should see:
- ✅ Set threshold mapping
- ✅ Get threshold mapping
- ✅ Calculate admission results
- ✅ Get admission results
- ✅ Publish admission results
- ✅ And 5 more endpoints...

---

## Common Issues & Solutions

### Issue 1: Migration Error
**Error:** `No changes detected`

**Solution:**
```powershell
# Force create migrations
python manage.py makemigrations mainapp --empty
# Then manually add CreateModel operations or re-run:
python manage.py makemigrations mainapp
```

### Issue 2: Import Errors
**Error:** `ImportError: cannot import name 'DepartmentThreshold'`

**Solution:** Verify `models/__init__.py` includes:
```python
from .department_threshold import DepartmentThreshold
from .admission_result import AdmissionResult
```

### Issue 3: JWT Authentication Failed
**Error:** `Authentication credentials were not provided`

**Solution:** Ensure token is sent as:
```
Authorization: Bearer YOUR_ACCESS_TOKEN
```

---

## Production Deployment Checklist

Before deploying to production:

- [ ] All tests passing
- [ ] Migrations applied on production database
- [ ] Admin superuser has access to new models
- [ ] API documentation updated
- [ ] Swagger UI accessible
- [ ] Backup database before migration
- [ ] Test rollback procedure
- [ ] Update frontend API calls (if needed)
- [ ] Monitor logs for errors
- [ ] Test with real data (sample exam)

---

## File Structure Summary

```
amsapp/mainapp/
├── models/
│   ├── department_threshold.py      ✨ NEW
│   ├── admission_result.py          ✨ NEW
│   └── __init__.py                  📝 MODIFIED
├── serializers/
│   ├── department_threshold.py      ✨ NEW
│   └── admission_result.py          ✨ NEW
├── services/
│   └── admission_calculator.py      ✨ NEW
├── views/
│   ├── admission_threshold.py       ✨ NEW
│   └── admission_results.py         ✨ NEW
├── tests/
│   └── test_admission_system.py     ✨ NEW
├── urls.py                          📝 MODIFIED
└── admin.py                         📝 MODIFIED
```

---

## Next Steps

### For Development:
1. Test with real exam data
2. Add more edge case tests
3. Optimize queries (select_related, prefetch_related)
4. Add caching for threshold lookups

### For Production:
1. Set up monitoring/logging
2. Create database indexes
3. Add rate limiting
4. Set up backup procedures

---

## Support

If you encounter issues:
1. Check Django logs: `tail -f logs/django.log`
2. Check PostgreSQL logs
3. Run tests to identify issues
4. Review `ADMISSION_SYSTEM_IMPLEMENTATION.md` for detailed documentation

---

**Setup Complete! Ready to use! 🎉**
