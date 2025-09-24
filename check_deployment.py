#!/usr/bin/env python3
"""
Simple script to verify deployment readiness
"""
import os
import sys

def check_deployment():
    print("🔍 Checking deployment readiness...")
    
    # Check if we're in the right directory
    if not os.path.exists('amsapp/manage.py'):
        print("❌ Error: manage.py not found. Make sure you're in the project root.")
        return False
    
    # Check WSGI module
    try:
        sys.path.insert(0, 'amsapp')
        from amsapp.wsgi import application
        print("✅ WSGI application can be imported")
    except ImportError as e:
        print(f"❌ Error importing WSGI application: {e}")
        return False
    
    # Check if gunicorn can find the module
    try:
        import gunicorn
        print("✅ Gunicorn is installed")
    except ImportError:
        print("❌ Gunicorn not found")
        return False
    
    print("✅ Deployment readiness check passed!")
    print("\n📋 Deployment Commands:")
    print("Build: ./build.sh")
    print("Start: ./start.sh")
    print("Manual: cd amsapp && gunicorn --bind 0.0.0.0:$PORT amsapp.wsgi:application")
    
    return True

if __name__ == "__main__":
    check_deployment()