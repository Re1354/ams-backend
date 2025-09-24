# 🎯 Render Deployment - Quick Setup Guide

## ✅ **Status: Ready for Deployment!**

Your AMS DIU Backend API with Swagger documentation is fully configured for Render deployment.

## 🚀 **Quick Deployment Steps**

### **1. Push to GitHub**
```bash
git add .
git commit -m "Setup complete: Django REST API with Swagger docs ready for Render"
git push origin main
```

### **2. Deploy on Render.com**

#### **Option A: Using Manual Configuration (Recommended)**
1. Go to [render.com](https://render.com) → **New Web Service**
2. Connect your GitHub repository: `morsalin101/ams-diu-backend`
3. Configure:
   - **Name**: `ams-diu-backend`
   - **Build Command**: `pip install -r requirements.txt && cd amsapp && python manage.py collectstatic --no-input && python manage.py migrate`
   - **Start Command**: `cd amsapp && gunicorn --bind 0.0.0.0:$PORT amsapp.wsgi:application`

#### **Option B: Using render.yaml**
- Just push to GitHub and use "Deploy from Repository" in Render

### **3. Set Environment Variables**
```
DEBUG=False
SECRET_KEY=your-generated-secret-key-here
DATABASE_URL=postgresql://ams_db_yim9_user:MWFsvDM81DcwxDf548eQMLYmsXe3vRmq@dpg-d39sm10dl3ps73agniu0-a.oregon-postgres.render.com:5432/ams_db_yim9
ALLOWED_HOSTS=ams-diu-backend.onrender.com,*.onrender.com,localhost,127.0.0.1
CORS_ALLOW_ALL_ORIGINS=True
```

### **4. After Deployment**
Update your actual domain in `amsapp/amsapp/settings.py` in the SPECTACULAR_SETTINGS.

## 📖 **Your API Endpoints**

Once deployed at `https://ams-diu-backend.onrender.com`:

### **Documentation**
- 📖 **Swagger UI**: `/api/docs/`
- 📚 **ReDoc**: `/api/redoc/`
- 🏠 **Home**: `/`

### **API Endpoints**
- 📝 **All Questions**: `/api/all-scrapped-questions/`
- 📊 **Statistics**: `/api/questions-stats/`
- ℹ️ **API Info**: `/api/info/`

### **Features**
- ✅ 25 Academic questions loaded
- ✅ Advanced filtering (subject, type, semester, search)
- ✅ Pagination (50 items per page)
- ✅ Interactive Swagger documentation
- ✅ PostgreSQL database ready
- ✅ CORS configured for frontend integration

## 🎯 **Example API Calls**

```bash
# Get all questions
curl https://ams-diu-backend.onrender.com/api/all-scrapped-questions/

# Filter by subject
curl https://ams-diu-backend.onrender.com/api/all-scrapped-questions/?subject=Mathematics

# Search questions
curl https://ams-diu-backend.onrender.com/api/all-scrapped-questions/?search=algorithm

# Get statistics
curl https://ams-diu-backend.onrender.com/api/questions-stats/
```

## 📋 **Files Ready**
- ✅ `requirements.txt` - All dependencies
- ✅ `build.sh` - Build script
- ✅ `start.sh` - Start script  
- ✅ `render.yaml` - Render configuration
- ✅ `Procfile` - Alternative deployment
- ✅ `runtime.txt` - Python 3.12.6
- ✅ Django settings configured for production
- ✅ Database migrations ready
- ✅ Static files configuration
- ✅ Swagger documentation setup

## 🔧 **Troubleshooting**

### **Build Script Issues**
If you encounter "No such file or directory" for `build.sh`:

**Solution 1: Use Manual Commands**
In Render dashboard, set:
```
Build Command: pip install -r requirements.txt && cd amsapp && python manage.py collectstatic --no-input && python manage.py migrate
Start Command: cd amsapp && gunicorn --bind 0.0.0.0:$PORT amsapp.wsgi:application
```

**Solution 2: Use Python Build Script**
```
Build Command: python build.py
Start Command: cd amsapp && gunicorn --bind 0.0.0.0:$PORT amsapp.wsgi:application
```

### **Common Issues**
- **Module not found**: Make sure all dependencies are in `requirements.txt`
- **Database connection**: Verify `DATABASE_URL` environment variable
- **Static files**: Ensure `STATIC_ROOT` is configured in settings
- **CORS errors**: Set `CORS_ALLOW_ALL_ORIGINS=True` for testing

### **Environment Variables Check**
Make sure these are set in Render:
```
DEBUG=False
SECRET_KEY=your-secret-key
DATABASE_URL=your-postgres-url
ALLOWED_HOSTS=your-domain.onrender.com,*.onrender.com
CORS_ALLOW_ALL_ORIGINS=True
```

Your API is production-ready! 🎉