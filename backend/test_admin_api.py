import requests
import json
import os
import datetime

os.environ['NO_PROXY'] = '127.0.0.1,localhost'

BASE_URL = 'http://127.0.0.1:5000/api'

def run_tests():
    session = requests.Session()
    
    # 1. Login as Admin
    print("Logging in as Admin...")
    login_data = {
        "username": "admin",
        "password": "123456"
    }
    resp = session.post(f"{BASE_URL}/auth/login", json=login_data)
    if resp.status_code != 200:
        print(f"Login failed: {resp.text}")
        return
    
    token = resp.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    print("Login Successful!")

    # 2. Create Drug
    print("\nCreating Drug...")
    drug_data = {
        "name": "Test Drug",
        "specification": "100mg",
        "unit": "Box",
        "price": 10.0,
        "stock": 100
    }
    resp = session.post(f"{BASE_URL}/admin/drugs", json=drug_data, headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    
    drug_id = resp.json()['data']['id']

    # 3. Get Drugs
    print("\nGetting Drugs...")
    resp = session.get(f"{BASE_URL}/admin/drugs", params={'keyword': 'Test'}, headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Found {len(resp.json()['data'])} drugs.")

    # 4. Update Drug
    print(f"\nUpdating Drug {drug_id}...")
    update_data = {
        "stock": 200
    }
    resp = session.put(f"{BASE_URL}/admin/drugs/{drug_id}", json=update_data, headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")

    # 5. Delete Drug (Logic)
    print(f"\nDisabling Drug {drug_id}...")
    resp = session.delete(f"{BASE_URL}/admin/drugs/{drug_id}", headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")

    # 6. Revenue Stats
    print("\nGetting Revenue Stats (Daily)...")
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    resp = session.get(f"{BASE_URL}/admin/statistics/revenue", params={'type': 'daily', 'date': today}, headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")

    # 7. Backup
    print("\nBacking up Database...")
    resp = session.post(f"{BASE_URL}/admin/backup", headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")

if __name__ == '__main__':
    run_tests()
