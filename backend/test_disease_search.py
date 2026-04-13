import sqlite3
import time
import timeit
import json
import urllib.request
import urllib.parse
import sys
sys.path.append(r'e:\yws')
from backend.app import create_app

app = create_app()
app.testing = True

def test_search():
    client = app.test_client()
    
    # 模拟登录获取 token
    with app.app_context():
        from flask_jwt_extended import create_access_token
        from backend.app.models import User
        # 找一个医生用户
        user = User.query.filter_by(role='doctor').first()
        if user:
            token = create_access_token(identity=str(user.id))
        else:
            # 如果没有，创建一个
            from backend.app import db
            user = User(username='test_doctor', role='doctor')
            user.set_password('123456')
            db.session.add(user)
            db.session.commit()
            token = create_access_token(identity=str(user.id))
    
    headers = {'Authorization': f'Bearer {token}'}

    test_cases = [
        {"keyword": "gm", "expected_in_results": "感冒"},
        {"keyword": "ganmao", "expected_in_results": "感冒"},
        {"keyword": "J00", "expected_in_results": "急性鼻咽炎［感冒］"},
        {"keyword": "感冒", "expected_in_results": "感冒"},
        {"keyword": "gmx", "expected_in_results": "肝毛细线虫病"},
        {"keyword": "bdxgm", "expected_in_results": "病毒性感冒"}
    ]

    total_time = 0
    passed = 0
    
    for case in test_cases:
        kw = urllib.parse.quote(case['keyword'])
        start_time = time.time()
        res = client.get(f'/api/doctor/diagnoses/search?keyword={kw}', headers=headers)
        elapsed = (time.time() - start_time) * 1000
        total_time += elapsed
        
        if res.status_code != 200:
            print(f"Error {res.status_code}: {res.data}")
            continue
        res_data = json.loads(res.data)
        
        # 检查是否包含 expected_in_results
        found = False
        for item in res_data.get('data', []):
            if case['expected_in_results'] in item['name']:
                found = True
                break
                
        if found:
            passed += 1
            print(f"PASS: Keyword '{case['keyword']}' found '{case['expected_in_results']}' in {elapsed:.2f} ms")
        else:
            print(f"FAIL: Keyword '{case['keyword']}' did not find '{case['expected_in_results']}'")
            print(f"  Results: {res_data.get('data', [])}")
            
    avg_time = total_time / len(test_cases)
    print(f"\nTotal test cases: {len(test_cases)}, Passed: {passed}")
    print(f"Average response time: {avg_time:.2f} ms")
    
    assert passed / len(test_cases) >= 0.95, "Recall rate must be >= 95%"
    assert avg_time <= 300, "Response time must be <= 300 ms"

if __name__ == '__main__':
    test_search()