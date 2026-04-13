import requests
import json
import os

os.environ['NO_PROXY'] = '127.0.0.1,localhost'

BASE_URL = 'http://127.0.0.1:5000/api'

def run_tests():
    session = requests.Session()
    
    # 1. Login as Nurse
    print("Logging in as Nurse...")
    login_data = {
        "username": "nurse",
        "password": "123456"
    }
    resp = session.post(f"{BASE_URL}/auth/login", json=login_data)
    if resp.status_code != 200:
        print(f"Login failed: {resp.text}")
        return
    
    token = resp.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    print("Login Successful!")

    # 2. Get Pending Visits
    print("\nGetting Pending Visits...")
    resp = session.get(f"{BASE_URL}/nurse/pending-visits", headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    
    visits = resp.json().get('data', [])
    if not visits:
        print("No pending visits found. Please run doctor test first to create one.")
        return
        
    visit_id = visits[0]['visit_id']
    print(f"Processing Visit ID: {visit_id}")

    # 3. Get Visit Details
    print(f"\nGetting Details for Visit {visit_id}...")
    resp = session.get(f"{BASE_URL}/nurse/visits/{visit_id}", headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")

    # 4. Verify Visit
    print(f"\nVerifying Visit {visit_id}...")
    resp = session.post(f"{BASE_URL}/nurse/visits/{visit_id}/verify", headers=headers)
    print(f"Status: {resp.status_code}")
    try:
        print(f"Response: {resp.json()}")
    except Exception:
        print(f"Response: {resp.text}")

    # 5. Execute Visit
    print(f"\nExecuting Visit {visit_id}...")
    execute_data = {
        "payment_method": "cash"
    }
    resp = session.post(f"{BASE_URL}/nurse/visits/{visit_id}/execute", json=execute_data, headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    
    if resp.status_code == 200:
        payment_id = resp.json()['data']['payment_id']
        
        # 6. Mark Printed
        print(f"\nMarking Receipt Printed for Payment {payment_id}...")
        resp = session.put(f"{BASE_URL}/nurse/payments/{payment_id}/print", headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.json()}")

    # 7. List Drugs
    print("\nListing Drugs...")
    resp = session.get(f"{BASE_URL}/nurse/drugs", headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Found {len(resp.json()['data'])} drugs.")

if __name__ == '__main__':
    run_tests()
