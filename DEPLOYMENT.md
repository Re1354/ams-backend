# AMS DIU Backend - Deployment Guide

## Database Configuration ✅

Your PostgreSQL database is now configured with the following credentials:
- **Host**: dpg-d39sm10dl3ps73agniu0-a.oregon-postgres.render.com
- **Port**: 5432
- **Database**: ams_db_yim9
- **Username**: ams_db_yim9_user
- **Password**: MWFsvDM81DcwxDf548eQMLYmsXe3vRmq

## Local Development

1. **Use SQLite for local development** (default):
   - Keep the DATABASE_URL commented in `.env`
   - Run: `python manage.py runserver`

2. **Use PostgreSQL for local testing**:
   - Uncomment the DATABASE_URL in `.env`
   - Run: `python manage.py migrate`

## Deployment to Render

### Option 1: Using Render Dashboard (Recommended)

1. **Connect your GitHub repository** to Render:
   - Go to [render.com](https://render.com)
   - Click "New Web Service"
   - Connect your GitHub repository

2. **Configure the service**:
   - **Name**: `ams-diu-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `./build.sh`
   - **Start Command**: `6. **Set Start Command:** `./start.sh``
   - **Root Directory**: Leave empty (use repository root)

3. **Set Environment Variables**:
   ```
   DEBUG=False
   SECRET_KEY=your-secret-key-here (generate a new one)
   DATABASE_URL=postgresql://ams_db_yim9_user:MWFsvDM81DcwxDf548eQMLYmsXe3vRmq@dpg-d39sm10dl3ps73agniu0-a.oregon-postgres.render.com:5432/ams_db_yim9
   ALLOWED_HOSTS=your-app-name.onrender.com
   ```

4. **Deploy**: Click "Create Web Service"

### Option 2: Using render.yaml (Infrastructure as Code)

1. Modify the `render.yaml` file to use your existing database
2. Run: `render deploy`

### Option 3: Manual Database Connection

If you prefer to use the existing database directly:

1. In Render dashboard, set these environment variables:
   ```
   DATABASE_URL=postgresql://ams_db_yim9_user:MWFsvDM81DcwxDf548eQMLYmsXe3vRmq@dpg-d39sm10dl3ps73agniu0-a.oregon-postgres.render.com:5432/ams_db_yim9
   ```

## Important Security Notes

1. **Generate a new SECRET_KEY** for production
2. **Set DEBUG=False** in production
3. **Update ALLOWED_HOSTS** with your domain
4. **Never commit sensitive credentials** to version control

## Files Created/Updated

- ✅ `settings.py` - Updated for PostgreSQL and production
- ✅ `requirements.txt` - Added production dependencies
- ✅ `.env` - Environment variables template
- ✅ `.gitignore` - Updated ignore patterns
- ✅ `build.sh` - Render build script
- ✅ `render.yaml` - Render configuration
- ✅ `Procfile` - Alternative deployment config

## Testing

1. **Database connection tested** ✅
2. **Migrations applied** ✅
3. **Static files collected** ✅

Your application is ready for deployment to Render!

## Next Steps

1. Push your code to GitHub
2. Connect the repository to Render
3. Set the environment variables
4. Deploy!

Your database is already set up and ready to use.

## Troubleshooting

### Common Issues

1. **"No module named 'app'" Error**:
   - Make sure you're using the correct start command: `./start.sh`
   - Verify that Render is using your custom build and start commands
   - Check that the working directory is set correctly

2. **Database Connection Issues**:
   - Verify the DATABASE_URL environment variable is set correctly
   - Check that your database credentials are still valid

3. **Static Files Not Loading**:
   - Ensure `python manage.py collectstatic` runs in build.sh
   - Check that WhiteNoise is configured in settings.py

### Manual Deployment Steps (Alternative)

If render.yaml doesn't work, deploy manually:

1. **Create Web Service** on Render dashboard
2. **Connect Repository** 
3. **Set Configuration**:
   - Build Command: `./build.sh`
   - Start Command: `./start.sh`
   - Python Version: 3.12.6 (see runtime.txt)
4. **Add Environment Variables**:
   ```
   DEBUG=False
   SECRET_KEY=your-new-secret-key
   DATABASE_URL=postgresql://ams_db_yim9_user:MWFsvDM81DcwxDf548eQMLYmsXe3vRmq@dpg-d39sm10dl3ps73agniu0-a.oregon-postgres.render.com:5432/ams_db_yim9
   ALLOWED_HOSTS=your-app-name.onrender.com
   ```