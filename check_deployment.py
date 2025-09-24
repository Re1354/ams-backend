#!/usr/bin/env python3
"""
Deployment readiness check for AMS DIU Backend
"""
import os
import sys

def check_deployment():
    print("🔍 Checking deployment readiness...")
    
    checks_passed = 0
    total_checks = 8
    
    # Check if we're in the right directory
    if not os.path.exists('amsapp/manage.py'):
        print("❌ Error: manage.py not found. Make sure you're in the project root.")
        return False
    else:
        print("✅ Django project structure found")
        checks_passed += 1
    
    # Check WSGI module
    try:
        sys.path.insert(0, 'amsapp')
        from amsapp.wsgi import application
        print("✅ WSGI application can be imported")
        checks_passed += 1
    except ImportError as e:
        print(f"❌ Error importing WSGI application: {e}")
    
    # Check required packages
    required_packages = [
        'django',
        'djangorestframework', 
        'drf_spectacular',
        'psycopg2',
        'gunicorn',
        'whitenoise'
    ]
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package} is installed")
            checks_passed += 1
        except ImportError:
            print(f"❌ {package} not found")
    
    # Check deployment files
    deployment_files = ['build.sh', 'start.sh', 'Procfile', 'render.yaml', 'runtime.txt']
    for file in deployment_files:
        if os.path.exists(file):
            print(f"✅ {file} exists")
        else:
            print(f"❌ {file} missing")
    
    print(f"\n📊 Deployment readiness: {checks_passed}/{total_checks} checks passed")
    
    if checks_passed >= 7:
        print("🎉 Ready for deployment!")
        print("\n📋 Deployment Commands:")
        print("Build: ./build.sh")
        print("Start: ./start.sh")
        print("Manual: cd amsapp && gunicorn --bind 0.0.0.0:$PORT amsapp.wsgi:application")
        print("\n🌐 After deployment, access:")
        print("- API Docs: https://your-app.onrender.com/api/docs/")
        print("- Questions: https://your-app.onrender.com/api/all-scrapped-questions/")
        print("- Stats: https://your-app.onrender.com/api/questions-stats/")
        return True
    else:
        print("⚠️  Some issues need to be resolved before deployment")
        return False

if __name__ == "__main__":
    check_deployment()