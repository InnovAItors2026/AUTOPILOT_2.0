# This file lets Python treat the src folder as a package.
# Other modules can import Member 1, 2, 3, 4, and 5 functions from src.

from src.data_loader import load_all_data
from src.dependency_detector import (
    detect_dependencies,
    find_direct_dependencies,
    find_multi_tier_dependencies,
    list_direct_dependencies,
)
from src.supply_chain_graph import (
    SupplyChainGraph,
    find_suppliers_sharing_upstream,
    find_upstream_dependencies,
    get_supply_chain_graph,
)

# Member 3 – Recovery Optimisation Engine
from src.recovery_optimisation import (
    optimise_recovery,
    optimise_from_disruption_report,
    classify_supplier,
    check_material_compatibility,
    assess_feasibility,
    assess_cost_and_delivery,
    assess_transport,
    assess_upstream_dependency,
    rank_candidates,
    allocate_quantity,
    DEFAULT_WEIGHTS,
    CLASS_PRIMARY,
    CLASS_BACKUP,
    CLASS_SECONDARY,
    CLASS_EMERGENCY,
    FEASIBLE,
    PARTIALLY_FEASIBLE,
    INFEASIBLE,
    FEASIBILITY_UNKNOWN,
    TRANSPORT_AVAILABLE,
    TRANSPORT_UNKNOWN,
    TRANSPORT_UNAVAILABLE,
    DEP_INDEPENDENT,
    DEP_SHARED_UPSTREAM,
    DEP_DIRECTLY_AFFECTED,
    DEP_UNKNOWN,
    STATUS_FEASIBLE,
    STATUS_PARTIAL,
    STATUS_NO_PLAN,
    STATUS_EMERGENCY,
    OBJ_BALANCED,
    OBJ_LOWEST_COST,
    OBJ_FASTEST,
    UNKNOWN,
)

# Member 4 – Cascading Failure & Challenger
from src.cascading_failure import (
    challenge_recovery_plan,
    detect_shared_upstream_dependencies,
    simulate_cascading_supplier_failures,
    simulate_route_failure,
    suppliers_using_route,
    transport_excluded_suppliers,
)

# Member 5 – SAP Integration & Unified Resilience Pipeline
from src.sap_client import SAPClient, get_sap_client
from src.pipeline import (
    run_full_resilience_pipeline,
    approve_recovery_plan,
    get_approval_history,
    generate_dossier_markdown,
    generate_ai_explanations,
)

__all__ = [
    # Member 1
    "load_all_data",
    "get_supply_chain_graph",
    "find_upstream_dependencies",
    "find_suppliers_sharing_upstream",
    "SupplyChainGraph",
    "detect_dependencies",
    "find_direct_dependencies",
    "list_direct_dependencies",
    "find_multi_tier_dependencies",
    # Member 3 – Recovery Optimisation
    "optimise_recovery",
    "optimise_from_disruption_report",
    "classify_supplier",
    "check_material_compatibility",
    "assess_feasibility",
    "assess_cost_and_delivery",
    "assess_transport",
    "assess_upstream_dependency",
    "rank_candidates",
    "allocate_quantity",
    "DEFAULT_WEIGHTS",
    "CLASS_PRIMARY",
    "CLASS_BACKUP",
    "CLASS_SECONDARY",
    "CLASS_EMERGENCY",
    "FEASIBLE",
    "PARTIALLY_FEASIBLE",
    "INFEASIBLE",
    "FEASIBILITY_UNKNOWN",
    "TRANSPORT_AVAILABLE",
    "TRANSPORT_UNKNOWN",
    "TRANSPORT_UNAVAILABLE",
    "DEP_INDEPENDENT",
    "DEP_SHARED_UPSTREAM",
    "DEP_DIRECTLY_AFFECTED",
    "DEP_UNKNOWN",
    "STATUS_FEASIBLE",
    "STATUS_PARTIAL",
    "STATUS_NO_PLAN",
    "STATUS_EMERGENCY",
    "OBJ_BALANCED",
    "OBJ_LOWEST_COST",
    "OBJ_FASTEST",
    "UNKNOWN",
    # Member 4 – Cascading Failure & Challenger
    "challenge_recovery_plan",
    "detect_shared_upstream_dependencies",
    "simulate_cascading_supplier_failures",
    "simulate_route_failure",
    "suppliers_using_route",
    "transport_excluded_suppliers",
    # Member 5 – SAP Integration & Unified Pipeline
    "SAPClient",
    "get_sap_client",
    "run_full_resilience_pipeline",
    "approve_recovery_plan",
    "get_approval_history",
    "generate_dossier_markdown",
    "generate_ai_explanations",
]
