# 🚀 AMS DIU Backend - Render Deployment Guide

## 📋 Project Overview

**AMS DIU Backend** is a Django REST API with Swagger documentation that provides:
- 📚 **25 Academic Questions** across 5 subjects (Math, Physics, English, General Knowledge, IT/AI)
- 🔍 **Advanced Filtering** by subject, type, semester, and search
- 📊 **Statistics API** for analytics
- 📖 **Interactive Swagger Documentation**
- 🗄️ **PostgreSQL Database** integration

## 🛠️ Tech Stack

- **Backend**: Django 5.2.6 + Django REST Framework
- **Database**: PostgreSQL (Render hosted)
- **Documentation**: drf-spectacular (Swagger/OpenAPI)
- **Deployment**: Render
- **Static Files**: WhiteNoise

## 🔗 API Endpoints

### 📚 **Questions API**
- `GET /api/all-scrapped-questions/` - Get all questions with filtering
- `GET /api/questions-stats/` - Get statistics and analytics

### 📖 **Documentation**
- `GET /api/schema/` - OpenAPI Schema
- `GET /api/docs/` - Swagger UI Documentation
- `GET /api/redoc/` - ReDoc Documentation
- `GET /api/info/` - API Information

### 🏠 **Home**
- `GET /` - API Documentation Home Page

## 🎯 Query Parameters

### **Filter Questions** (`/api/all-scrapped-questions/`)
- `?subject=Mathematics` - Filter by subject
- `?type=option` - Filter by question type (option/text)
- `?semester=General` - Filter by semester
- `?search=algorithm` - Search in questions and subjects
- `?page=2` - Pagination (50 items per page)

**Example**: `/api/all-scrapped-questions/?subject=English&type=option&page=1`

---

## 🚀 Render Deployment

### **Option 1: Using Render Dashboard (Recommended)**

1. **📁 Push to GitHub**
   ```bash
   git add .
   git commit -m "Setup for Render deployment with Swagger docs"
   git push origin main
   ```

2. **🌐 Deploy on Render**
   - Go to [render.com](https://render.com)
   - Click **"New Web Service"**
   - Connect your GitHub repository

3. **⚙️ Configure Service**
   - **Name**: `ams-diu-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `./build.sh`
   - **Start Command**: `./start.sh`
   - **Python Version**: `3.12.6` (from runtime.txt)

4. **🔧 Environment Variables**
   ```
   DEBUG=False
   SECRET_KEY=[Generate a new secret key]
  DATABASE_URL=postgresql://admin:s1PrybnHZz2loPWHm2LAvAf3SFdQRkhZ@dpg-d7vqh2jbc2fs73d3guig-a.oregon-postgres.render.com:5432/ams_85ev
   ALLOWED_HOSTS=your-app-name.onrender.com,*.onrender.com
   CORS_ALLOW_ALL_ORIGINS=True
   ```

5. **🎯 Update Swagger Config**
   - After deployment, update the server URL in `settings.py`
   - Replace `ams-diu-backend.onrender.com` with your actual domain

### **Option 2: Using render.yaml**

The `render.yaml` file is already configured. Just push to GitHub and use "Deploy from Repository" in Render.

---

## 📊 Database Status

✅ **PostgreSQL Database Ready**
- **Host**: dpg-d7b6kvia214c73cmo8kg-a.oregon-postgres.render.com
- **Database**: ams_85ev
- **Questions Loaded**: 25 questions across 5 subjects
- **Migrations Applied**: All migrations up to date

---

## 🧪 Testing Your Deployment

### **1. Health Check**
```bash
curl https://your-app-name.onrender.com/api/info/
```

### **2. Get Questions**
```bash
curl https://your-app-name.onrender.com/api/all-scrapped-questions/
```

### **3. Get Statistics**
```bash
curl https://your-app-name.onrender.com/api/questions-stats/
```

### **4. Access Documentation**
- **Swagger UI**: `https://your-app-name.onrender.com/api/docs/`
- **ReDoc**: `https://your-app-name.onrender.com/api/redoc/`
- **Home Page**: `https://your-app-name.onrender.com/`

---

## 📁 Files Created for Deployment

✅ **Core Files**
- `build.sh` - Render build script
- `start.sh` - Application start script
- `Procfile` - Alternative deployment config
- `runtime.txt` - Python version specification
- `render.yaml` - Render service configuration

✅ **API Files**
- `serializers.py` - API serializers with documentation
- `views.py` - API views with Swagger decorators
- `urls.py` - URL routing
- `api_info.py` - API information endpoints

✅ **Configuration**
- `settings.py` - Updated with DRF Spectacular config
- `requirements.txt` - Updated with all dependencies

---

## 🔧 Local Development

```bash
# 1. Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run migrations
cd amsapp
python manage.py migrate

# 4. Start development server
python manage.py runserver

# 5. Access API
# - API: http://localhost:8000/api/
# - Swagger: http://localhost:8000/api/docs/
# - Admin: http://localhost:8000/admin/
```

---

## 🎯 API Response Examples

### **Questions List Response**
```json
{
  "count": 25,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "subject": "Mathematics",
      "questions": "If A = [2! 3! 2!; 3! 2! 4!; 0! 3! 2!], then det(A) = ?",
      "type": "option",
      "text": null,
      "options": {
        "A": "-16",
        "B": "-140", 
        "C": "-208",
        "D": "-280"
      },
      "answer": ["B"],
      "marks": 1,
      "semester": "General"
    }
  ]
}
```

### **Statistics Response**
```json
{
  "total_questions": 25,
  "by_subject": {
    "Mathematics": 3,
    "English": 11,
    "Physics": 5,
    "General Knowledge": 3,
    "IT - Using AI and ChatGPT": 3
  },
  "by_type": {
    "option": 25,
    "text": 0
  },
  "by_semester": {
    "General": 25
  },
  "subjects": ["Mathematics", "English", "Physics", "General Knowledge", "IT - Using AI and ChatGPT"],
  "semesters": ["General"]
}
```

---

## 🔒 Security Notes

1. **Generate New SECRET_KEY** for production
2. **Set DEBUG=False** in production
3. **Configure ALLOWED_HOSTS** with your domain
4. **Use HTTPS** in production
5. **Database credentials** are already configured

---

## 🎉 Ready for Deployment!

Your Django REST API with Swagger documentation is ready for Render deployment. The database is configured, questions are loaded, and all deployment files are in place.

**Next Steps:**
1. 📤 Push to GitHub
2. 🌐 Deploy on Render
3. 🔧 Set environment variables
4. 🎯 Update domain in Swagger config
5. 🎊 Enjoy your deployed API with documentation!