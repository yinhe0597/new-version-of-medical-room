from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from backend.app import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    real_name = db.Column(db.String(64))
    role = db.Column(db.String(20))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    visits = db.relationship('Visit', backref='doctor', foreign_keys='Visit.doctor_id', lazy='dynamic')
    payments = db.relationship('Payment', backref='nurse', foreign_keys='Payment.nurse_id', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.username}>'

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True)
    name_pinyin = db.Column(db.String(128), index=True, nullable=True)
    name_initials = db.Column(db.String(64), index=True, nullable=True)
    gender = db.Column(db.String(10))
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    visits = db.relationship('Visit', backref='patient', lazy='dynamic')

    def __repr__(self):
        return f'<Patient {self.name}>'

class Drug(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), index=True)
    type = db.Column(db.Integer, default=1)
    specification = db.Column(db.String(50))
    unit = db.Column(db.String(10))
    price = db.Column(db.Float)
    stock = db.Column(db.Integer, default=0)
    status = db.Column(db.Integer, default=1)
    batch_no = db.Column(db.String(50), nullable=True)
    inbound_at = db.Column(db.DateTime, nullable=True)
    
    # 新增字段以支持整散装和进货价
    purchase_price = db.Column(db.Float, default=0.0)
    has_scattered = db.Column(db.Boolean, default=False)
    scattered_price = db.Column(db.Float, nullable=True)
    conversion_rate = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f'<Drug/Item {self.name}>'

class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)

    chief_complaint = db.Column(db.Text)
    present_illness = db.Column(db.Text)
    past_history = db.Column(db.Text)
    physical_exam = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    doctor_advice = db.Column(db.Text)

    consultation_fee = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')

    items = db.relationship('PrescriptionItem', backref='visit', lazy='dynamic')
    payment = db.relationship('Payment', backref='visit', uselist=False)

    def __repr__(self):
        return f'<Visit {self.id}>'

class PrescriptionItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey('visit.id'))
    drug_id = db.Column(db.Integer, db.ForeignKey('drug.id'))

    usage = db.Column(db.String(100))
    dosage = db.Column(db.String(50))
    frequency = db.Column(db.String(50))
    timing = db.Column(db.String(50))
    days = db.Column(db.Integer, default=1)

    quantity = db.Column(db.Integer)
    price_at_visit = db.Column(db.Float)
    amount = db.Column(db.Float)
    
    # 新增字段以支持整散装和成本计算
    is_scattered = db.Column(db.Boolean, default=False)
    purchase_cost = db.Column(db.Float, default=0.0)

    drug = db.relationship('Drug')

class DiagnosisDict(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), index=True)
    name = db.Column(db.String(200), index=True)
    pinyin = db.Column(db.String(200), index=True)

    def __repr__(self):
        return f'<DiagnosisDict {self.code} - {self.name}>'

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey('visit.id'), unique=True)
    nurse_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    amount = db.Column(db.Float)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50))
    receipt_printed = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Payment {self.id}>'

class InventoryRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drug_id = db.Column(db.Integer, db.ForeignKey('drug.id'))
    nurse_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    old_stock = db.Column(db.Integer)
    new_stock = db.Column(db.Integer)
    remark = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    drug = db.relationship('Drug')
    nurse = db.relationship('User')

    def __repr__(self):
        return f'<InventoryRecord {self.id}>'
