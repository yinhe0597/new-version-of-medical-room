import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app import create_app, db
from backend.app.models import User, Patient, Drug, Visit, PrescriptionItem, Payment

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Patient': Patient, 'Drug': Drug, 'Visit': Visit, 'PrescriptionItem': PrescriptionItem, 'Payment': Payment}

if __name__ == '__main__':
    app.run(debug=True)
