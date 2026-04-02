from app import create_app, db
from app.models import User, Patient, Drug, Visit, PrescriptionItem, Payment

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Patient': Patient, 'Drug': Drug, 'Visit': Visit, 'PrescriptionItem': PrescriptionItem, 'Payment': Payment}

if __name__ == '__main__':
    app.run(debug=True)
