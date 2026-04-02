import requests
import json
import os

os.environ['NO_PROXY'] = '127.0.0.1,localhost'

BASE_URL = 'http://127.0.0.1:5000/api'

def run_tests():
    session = requests.Session()
    
    # 1. Login as Doctor
    print("Logging in as Doctor...")
    login_data = {
        "username": "doctor",
        "password": "123456"
    }
    resp = session.post(f"{BASE_URL}/auth/login", json=login_data)
    if resp.status_code != 200:
        print(f"Login failed: {resp.text}")
        return
    
    token = resp.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    print("Login Successful!")

    # 2. Search Patient (Non-existent)
    print("\nSearching for non-existent patient...")
    resp = session.get(f"{BASE_URL}/doctor/patient/search", params={'student_id': '999999'}, headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")

    # 3. Create Patient
    print("\nCreating new patient...")
    new_patient = {
        "student_id": "2024999",
        "name": "Test Student",
        "gender": "男",
        "class_name": "Test Class",
        "phone": "1234567890"
    }
    resp = session.post(f"{BASE_URL}/doctor/patient", json=new_patient, headers=headers)
    if resp.status_code == 400 and "already exists" in resp.text:
        print("Patient already exists, skipping creation.")
        # Need to get ID if exists
        resp = session.get(f"{BASE_URL}/doctor/patient/search", params={'student_id': '2024999'}, headers=headers)
        patient_id = resp.json()['data']['id']
    else:
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.json()}")
        patient_id = resp.json()['data']['id']

    # 4. Search Drugs
    print("\nSearching for drugs (keyword='感冒')...")
    resp = session.get(f"{BASE_URL}/doctor/drugs/search", params={'keyword': '感冒'}, headers=headers)
    print(f"Status: {resp.status_code}")
    drugs = resp.json()['data']
    print(f"Found {len(drugs)} drugs.")
    if drugs:
        drug_id = drugs[0]['id']
        print(f"Using Drug ID: {drug_id} ({drugs[0]['name']})")
    else:
        print("No drugs found, cannot proceed with prescription test.")
        return

    # 5. Create Visit (Prescription)
    print("\nCreating Visit...")
    visit_data = {
        "patient_id": patient_id,
        "chief_complaint": "Test Complaint",
        "diagnosis": "Test Diagnosis",
        "consultation_fee": 5.0,
        "items": [
            {
                "drug_id": drug_id,
                "quantity": 1,
                "usage": "Oral",
                "frequency": "Once a day",
                "days": 3
            }
        ]
    }
    resp = session.post(f"{BASE_URL}/doctor/visits", json=visit_data, headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")

    # 6. Get Visit History
    print("\nGetting Visit History...")
    resp = session.get(f"{BASE_URL}/doctor/visits/history", headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")

if __name__ == '__main__':
    run_tests()
