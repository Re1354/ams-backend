#!/usr/bin/env python3
"""
Build script for Render deployment
Alternative to build.sh for cross-platform compatibility
"""
import subprocess
import sys
import os

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed")
        print(f"Error: {e.stderr}")
        return False

def main():
    print("🚀 Starting Render deployment build...")
    
    # Install dependencies
    if not run_command("pip install -r requirements.txt", "Installing dependencies"):
        sys.exit(1)
    
    # Change to Django project directory
    os.chdir("amsapp")
    
    # Collect static files
    if not run_command("python manage.py collectstatic --no-input", "Collecting static files"):
        sys.exit(1)
    
    # Run migrations
    if not run_command("python manage.py migrate", "Running database migrations"):
        sys.exit(1)
    
    print("🎉 Build completed successfully!")

if __name__ == "__main__":
    main()