from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from backend.app import db

VISIT_STATUS_PENDING = "pending"
VISIT_STATUS_NURSE_VERIFIED = "nurse_verified"
VISIT_STATUS_COMPLETED = "completed"
VISIT_STATUS_REJECTED = "rejected"

VISIT_ALLOWED_STATUS_TRANSITIONS = {
    VISIT_STATUS_PENDING: {VISIT_STATUS_NURSE_VERIFIED, VISIT_STATUS_REJECTED},
    VISIT_STATUS_NURSE_VERIFIED: {VISIT_STATUS_COMPLETED, VISIT_STATUS_REJECTED},
    VISIT_STATUS_COMPLETED: set(),
    VISIT_STATUS_REJECTED: set(),
}

def get_allowed_visit_status_transitions(from_status):
    return tuple(sorted(VISIT_ALLOWED_STATUS_TRANSITIONS.get(from_status, set())))

def is_visit_status_transition_allowed(from_status, to_status):
    if from_status == to_status:
        return True
    return to_status in VISIT_ALLOWED_STATUS_TRANSITIONS.get(from_status, set())

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
    text_templates = db.relationship('TextTemplate', backref='doctor', foreign_keys='TextTemplate.doctor_id', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.username}>'

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), index=True, unique=True, nullable=True)
    name = db.Column(db.String(64), index=True)
    gender = db.Column(db.String(10))
    class_name = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    grade = db.Column(db.String(50), nullable=True)
    college = db.Column(db.String(100), nullable=True)
    major = db.Column(db.String(100), nullable=True)
    name_pinyin = db.Column(db.Text, index=True, nullable=True)
    name_initials = db.Column(db.Text, index=True, nullable=True)
    is_temporary = db.Column(db.Boolean, default=False, index=True)
    age = db.Column(db.Integer, nullable=True)
    id_card = db.Column(db.String(20), nullable=True)
    counselor_name = db.Column(db.String(64), nullable=True)

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
    variant_type = db.Column(db.String(20), nullable=True)
    stock_group_code = db.Column(db.String(36), index=True, nullable=True)
    unit_amount = db.Column(db.Integer, nullable=True)
    base_name = db.Column(db.String(128), nullable=True)

    def __repr__(self):
        return f'<Drug/Item {self.name}>'

class DrugStockGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_code = db.Column(db.String(36), unique=True, index=True, nullable=False)
    batch_no = db.Column(db.String(50), index=True, nullable=False)
    base_name = db.Column(db.String(128), index=True, nullable=False)
    unit_name = db.Column(db.String(20), nullable=False)
    total_units = db.Column(db.Integer, nullable=False)
    pack_amount = db.Column(db.Integer, nullable=False)
    retail_amount = db.Column(db.Integer, nullable=True)
    pack_drug_id = db.Column(db.Integer, db.ForeignKey('drug.id'), nullable=False)
    retail_drug_id = db.Column(db.Integer, db.ForeignKey('drug.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    pack_drug = db.relationship('Drug', foreign_keys=[pack_drug_id])
    retail_drug = db.relationship('Drug', foreign_keys=[retail_drug_id])
    creator = db.relationship('User', foreign_keys=[created_by])

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
    special_note = db.Column(db.Text)

    consultation_fee = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')
    verified_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    rejected_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    reject_reason = db.Column(db.Text, nullable=True)

    items = db.relationship('PrescriptionItem', backref='visit', lazy='dynamic')
    payment = db.relationship('Payment', backref='visit', uselist=False)
    verifier = db.relationship('User', foreign_keys=[verified_by])
    rejector = db.relationship('User', foreign_keys=[rejected_by])

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
    original_price = db.Column(db.Float, nullable=True)
    original_amount = db.Column(db.Float, nullable=True)
    new_price = db.Column(db.Float, nullable=True)
    new_amount = db.Column(db.Float, nullable=True)
    modified_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    modified_at = db.Column(db.DateTime, nullable=True)
    modify_reason = db.Column(db.Text, nullable=True)
    
    # 新增字段以支持整散装和成本计算
    is_scattered = db.Column(db.Boolean, default=False)
    purchase_cost = db.Column(db.Float, default=0.0)

    drug = db.relationship('Drug')
    modifier = db.relationship('User', foreign_keys=[modified_by])

class DiagnosisDict(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), index=True)
    name = db.Column(db.String(200), index=True)
    pinyin = db.Column(db.String(200), index=True)

    def __repr__(self):
        return f'<DiagnosisDict {self.code} - {self.name}>'

class TextTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True, nullable=False)
    category = db.Column(db.String(50), index=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<TextTemplate {self.id}>'

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey('visit.id'), unique=True)
    nurse_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    amount = db.Column(db.Float)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50))
    receipt_printed = db.Column(db.Boolean, default=False)
    is_employee_discount = db.Column(db.Boolean, default=False)  # 是否职工优惠
    original_amount = db.Column(db.Float, nullable=True)  # 原始应收金额（优惠前）

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

class DailyStockSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drug_id = db.Column(db.Integer, db.ForeignKey('drug.id'), index=True)
    date = db.Column(db.Date, index=True)
    stock = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    drug = db.relationship('Drug')
    __table_args__ = (db.UniqueConstraint('drug_id', 'date'),)

class OperationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    action_type = db.Column(db.String(50), index=True)
    target_type = db.Column(db.String(50))
    target_id = db.Column(db.Integer)
    summary = db.Column(db.String(200))
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')

    def __repr__(self):
        return f'<OperationLog {self.id} {self.action_type}>'
