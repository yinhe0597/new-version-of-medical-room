import os
import sys
import unittest


def main() -> int:
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    suite = unittest.defaultTestLoader.discover(
        start_dir=os.path.join(root, "backend", "tests"),
        pattern="test_admin_patient_import_required_fields.py",
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
