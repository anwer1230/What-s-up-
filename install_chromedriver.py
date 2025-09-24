#!/usr/bin/env python3
import os
import requests
import zipfile
import platform

def install_chromedriver():
    """تثبيت ChromeDriver تلقائياً على Render"""
    print("🔧 Installing ChromeDriver for Render...")
    
    system = platform.system().lower()
    
    if 'linux' in system:
        chrome_version = "114.0.5735.90"
        url = f"https://chromedriver.storage.googleapis.com/{chrome_version}/chromedriver_linux64.zip"
        
        print(f"📥 Downloading ChromeDriver {chrome_version} for Linux...")
        
        try:
            response = requests.get(url)
            with open("chromedriver.zip", "wb") as f:
                f.write(response.content)
            
            with zipfile.ZipFile("chromedriver.zip", "r") as zip_ref:
                zip_ref.extractall(".")
            
            os.chmod("chromedriver", 0o755)
            os.remove("chromedriver.zip")
            
            print("✅ ChromeDriver installed successfully")
            
        except Exception as e:
            print(f"❌ Failed to install ChromeDriver: {e}")
            print("📝 Please upload chromedriver manually")
    
    else:
        print("ℹ️ Manual ChromeDriver installation required for this system")

if __name__ == "__main__":
    install_chromedriver()
