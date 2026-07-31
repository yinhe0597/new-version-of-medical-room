"""手工验收：JWT 登录与角色路由（需后端服务运行中）。

凭据来自环境变量 MEDICAL_ADMIN_PASSWORD / MEDICAL_NURSE_PASSWORD。
"""

import os

import requests

from _common import api_base_url, require_password

os.environ['NO_PROXY'] = '127.0.0.1,localhost'

BASE_URL = api_base_url()


def login(username, password):
    url = f"{BASE_URL}/auth/login"
    payload = {'username': username, 'password': password}
    response = requests.post(url, json=payload)
    return response


def access_protected(token, endpoint):
    url = f"{BASE_URL}/{endpoint}"
    headers = {'Authorization': f'Bearer {token}'}
    response = requests.get(url, headers=headers)
    return response


def run_tests():
    admin_password = require_password('admin')
    nurse_password = require_password('nurse')

    # 1. Test Login (Admin)
    print("Testing Login (Admin)...")
    resp = login('admin', admin_password)
    if resp.status_code == 200:
        print("Login Successful!")
        data = resp.json()
        token = data.get('access_token')
        print(f"Token obtained: {token[:20]}...")
    else:
        print(f"Login Failed: {resp.text}")
        return

    # 2. Test Protected Route
    print("\nTesting Protected Route...")
    resp = access_protected(token, 'protected')
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text}")

    # 3. Test Admin Only Route (as Admin)
    print("\nTesting Admin Only Route (as Admin)...")
    resp = access_protected(token, 'admin-only')
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text}")

    # 4. Test Login (Nurse)
    print("\nTesting Login (Nurse)...")
    resp = login('nurse', nurse_password)
    if resp.status_code == 200:
        nurse_token = resp.json().get('access_token')
        print("Nurse Login Successful!")
    else:
        print(f"Nurse Login Failed: {resp.text}")
        return

    # 5. Test Admin Only Route (as Nurse)
    print("\nTesting Admin Only Route (as Nurse) - Should Fail...")
    resp = access_protected(nurse_token, 'admin-only')
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text}")


if __name__ == '__main__':
    run_tests()
