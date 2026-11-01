"""
run_recovery.py
---------------
CLI shim for src/recovery_optimisation.py.

Usage (from project root):
    python run_recovery.py <material_id> <quantity> [failed_supplier_id ...]

Examples:
    python run_recovery.py MAT-02 1000 SUP-T1-03
    python run_recovery.py MAT-03 5000 SUP-T1-01 SUP-T1-02
"""
import json
import sys

if __name__ == "__main__":
    from src.recovery_optimisation import optimise_recovery

    _mat = sys.argv[1] if len(sys.argv) > 1 else "MAT-02"
    _qty = float(sys.argv[2]) if len(sys.argv) > 2 else 1000.0
    _failed = sys.argv[3:] if len(sys.argv) > 3 else ["SUP-T1-03"]

    result = optimise_recovery(
        material_id=_mat,
        required_quantity=_qty,
        failed_supplier_ids=_failed,
    )
    print(json.dumps(result, indent=2, default=str))
