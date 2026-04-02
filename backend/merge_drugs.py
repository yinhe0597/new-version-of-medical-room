import os
import sys

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Drug, PrescriptionItem
from sqlalchemy import func

def merge_duplicate_drugs():
    app = create_app()
    with app.app_context():
        print("Starting to scan for duplicate drugs/items...")
        
        # Find duplicates based on name and specification (and optionally type)
        # Using name and specification as the unique identifier
        duplicates_query = db.session.query(
            Drug.name, 
            Drug.specification,
            func.count(Drug.id).label('count')
        ).group_by(
            Drug.name, 
            Drug.specification
        ).having(
            func.count(Drug.id) > 1
        ).all()
        
        if not duplicates_query:
            print("No duplicate drugs found.")
            return
            
        print(f"Found {len(duplicates_query)} groups of duplicates. Processing...")
        
        total_merged = 0
        total_deleted = 0
        
        for dup in duplicates_query:
            name = dup.name
            spec = dup.specification
            
            # Get all drugs with this name and spec, ordered by id (keep the first one)
            drugs = Drug.query.filter_by(name=name, specification=spec).order_by(Drug.id.asc()).all()
            
            if len(drugs) <= 1:
                continue
                
            # The one we keep
            primary_drug = drugs[0]
            # The ones we merge and delete
            duplicate_drugs = drugs[1:]
            
            print(f"\nProcessing '{name}' [{spec}]: Keep ID {primary_drug.id}, Merge {len(duplicate_drugs)} duplicates")
            
            for dup_drug in duplicate_drugs:
                # 1. Add stock to the primary drug (if it's a physical drug, type=1)
                if primary_drug.type == 1 and dup_drug.stock > 0:
                    primary_drug.stock += dup_drug.stock
                
                # 2. Update any PrescriptionItem that references the duplicate drug
                # so history records don't break
                items_to_update = PrescriptionItem.query.filter_by(drug_id=dup_drug.id).all()
                for item in items_to_update:
                    item.drug_id = primary_drug.id
                
                if items_to_update:
                    print(f"  - Updated {len(items_to_update)} prescription items from ID {dup_drug.id} to {primary_drug.id}")
                
                # 3. Delete the duplicate drug
                db.session.delete(dup_drug)
                total_deleted += 1
                
            total_merged += 1
            
            # Commit after each group to avoid locking too many rows
            db.session.commit()
            
        print(f"\nCompleted! Merged {total_merged} groups, deleted {total_deleted} duplicate records.")

if __name__ == '__main__':
    merge_duplicate_drugs()
