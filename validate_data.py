"""One-off dataset checks for AUTOPILOT 2.0 Member 1."""

import collections
import csv
import os
import re

BASE = os.path.join(os.path.dirname(__file__), "data")


def load(name):
    path = os.path.join(BASE, name)
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    print("FILE", name, "rows", len(rows), "cols", list(rows[0].keys()) if rows else [])
    return rows


def duplicates(rows, key, label, errors):
    ids = [row[key] for row in rows]
    extra = [item for item, count in collections.Counter(ids).items() if count > 1]
    if extra:
        errors.append("duplicate %s: %s" % (label, extra))


def main():
    suppliers = load("suppliers.csv")
    materials = load("materials.csv")
    factories = load("factories.csv")
    warehouses = load("warehouses.csv")
    routes = load("transport_routes.csv")
    orders = load("customer_orders.csv")
    inventory = load("inventory.csv")
    deps = load("supplier_dependencies.csv")
    maps = load("supplier_materials.csv")

    sup = {row["supplier_id"] for row in suppliers}
    mat = {row["material_id"] for row in materials}
    fac = {row["factory_id"] for row in factories}
    wh = {row["warehouse_id"] for row in warehouses}
    rte = {row["route_id"] for row in routes}

    errors = []
    warnings = []

    print("\n=== COUNTS ===")
    print("suppliers", len(suppliers), "unique", len(sup))
    print("materials", len(materials), "unique", len(mat))
    print("factories", len(factories), "unique", len(fac))
    print("warehouses", len(warehouses), "unique", len(wh))
    print("routes", len(routes), "unique", len(rte))
    print("orders", len(orders), "unique", len({row["order_id"] for row in orders}))
    print("inventory", len(inventory))
    print("deps", len(deps))
    print("maps", len(maps))
    print("tiers", dict(collections.Counter(row["tier"] for row in suppliers)))

    duplicates(suppliers, "supplier_id", "supplier", errors)
    duplicates(materials, "material_id", "material", errors)
    duplicates(factories, "factory_id", "factory", errors)
    duplicates(warehouses, "warehouse_id", "warehouse", errors)
    duplicates(routes, "route_id", "route", errors)
    duplicates(orders, "order_id", "order", errors)
    duplicates(inventory, "inventory_id", "inventory", errors)
    duplicates(deps, "dependency_id", "dependency", errors)

    map_keys = [(row["supplier_id"], row["material_id"]) for row in maps]
    extra_maps = [item for item, count in collections.Counter(map_keys).items() if count > 1]
    if extra_maps:
        errors.append("duplicate supplier-material pairs: %s" % extra_maps)

    required_fields = {
        "suppliers.csv": (suppliers, ["supplier_id", "supplier_name", "tier", "primary_route_id"]),
        "materials.csv": (materials, ["material_id", "material_name", "used_in_product"]),
        "factories.csv": (factories, ["factory_id", "linked_warehouse_id"]),
        "warehouses.csv": (warehouses, ["warehouse_id", "linked_factory_id"]),
        "transport_routes.csv": (routes, ["route_id", "origin_id", "destination_id"]),
        "customer_orders.csv": (orders, ["order_id", "warehouse_id", "product_name"]),
        "inventory.csv": (inventory, ["inventory_id", "location_id", "material_id"]),
        "supplier_dependencies.csv": (
            deps,
            ["dependency_id", "downstream_supplier_id", "upstream_supplier_id", "material_id"],
        ),
        "supplier_materials.csv": (maps, ["supplier_id", "material_id"]),
    }
    for fname, (rows, cols) in required_fields.items():
        for line_no, row in enumerate(rows, start=2):
            for col in cols:
                value = row.get(col)
                if value is None or str(value).strip() == "":
                    errors.append("%s:%s missing %s" % (fname, line_no, col))

    if len(suppliers) != 35:
        errors.append("need 35 suppliers, got %s" % len(suppliers))
    if len(factories) != 3:
        errors.append("need 3 factories, got %s" % len(factories))
    if len(warehouses) != 4:
        errors.append("need 4 warehouses, got %s" % len(warehouses))
    if len(routes) != 6:
        errors.append("need 6 routes, got %s" % len(routes))
    if len(orders) != 25:
        errors.append("need 25 orders, got %s" % len(orders))

    token_re = re.compile(r"[A-Z]+-[A-Z0-9]+(?:-\d+)?")
    tables = [
        ("suppliers.csv", suppliers),
        ("materials.csv", materials),
        ("factories.csv", factories),
        ("warehouses.csv", warehouses),
        ("transport_routes.csv", routes),
        ("customer_orders.csv", orders),
        ("inventory.csv", inventory),
        ("supplier_dependencies.csv", deps),
        ("supplier_materials.csv", maps),
    ]
    for fname, rows in tables:
        for line_no, row in enumerate(rows, start=2):
            for col, val in row.items():
                if not val:
                    continue
                for tok in token_re.findall(val):
                    if tok.startswith("SUP-") and tok not in sup:
                        errors.append("%s:%s %s unknown supplier %s" % (fname, line_no, col, tok))
                    elif tok.startswith("MAT-") and tok not in mat:
                        errors.append("%s:%s %s unknown material %s" % (fname, line_no, col, tok))
                    elif tok.startswith("FAC-") and tok not in fac:
                        errors.append("%s:%s %s unknown factory %s" % (fname, line_no, col, tok))
                    elif tok.startswith("WH-") and tok not in wh:
                        errors.append("%s:%s %s unknown warehouse %s" % (fname, line_no, col, tok))
                    elif tok.startswith("RTE-") and tok not in rte:
                        errors.append("%s:%s %s unknown route %s" % (fname, line_no, col, tok))
                    elif tok.startswith("HUB-"):
                        warnings.append("%s:%s %s hub id %s has no master row" % (fname, line_no, col, tok))

    for row in factories:
        if row["linked_warehouse_id"] not in wh:
            errors.append("factory %s bad warehouse %s" % (row["factory_id"], row["linked_warehouse_id"]))
    for row in warehouses:
        if row["linked_factory_id"] not in fac:
            errors.append("warehouse %s bad factory %s" % (row["warehouse_id"], row["linked_factory_id"]))
    for row in suppliers:
        if row["primary_route_id"] and row["primary_route_id"] not in rte:
            errors.append("supplier %s bad route %s" % (row["supplier_id"], row["primary_route_id"]))

    for row in routes:
        origin_id = row["origin_id"]
        dest_id = row["destination_id"]
        origin_type = row["origin_type"]
        dest_type = row["destination_type"]
        if dest_type == "factory" and dest_id not in fac:
            errors.append("route dest factory missing " + row["route_id"])
        if dest_type == "warehouse" and dest_id not in wh:
            errors.append("route dest warehouse missing " + row["route_id"])
        if origin_type == "factory" and origin_id not in fac:
            errors.append("route origin factory missing " + row["route_id"])
        if origin_type == "warehouse" and origin_id not in wh:
            errors.append("route origin warehouse missing " + row["route_id"])
        if origin_type == "supplier" and origin_id not in sup:
            errors.append("route origin supplier missing " + row["route_id"])
        if row["shared_supplier_ids"]:
            for supplier_id in row["shared_supplier_ids"].split(";"):
                if supplier_id not in sup:
                    errors.append("route shared unknown " + supplier_id)

    for row in orders:
        if row["warehouse_id"] not in wh:
            errors.append("order warehouse " + row["order_id"])
        expected = int(row["quantity"]) * int(row["unit_price_inr"])
        if expected != int(row["order_value_inr"]):
            errors.append("order value " + row["order_id"])

    for row in inventory:
        if row["material_id"] not in mat:
            errors.append("inv mat " + row["inventory_id"])
        if row["location_type"] == "factory" and row["location_id"] not in fac:
            errors.append("inv factory " + row["inventory_id"])
        if row["location_type"] == "warehouse" and row["location_id"] not in wh:
            errors.append("inv warehouse " + row["inventory_id"])

    print("\n=== DEPENDENCIES ===")
    invalid = []
    self_refs = []
    for row in deps:
        down_id = row["downstream_supplier_id"]
        up_id = row["upstream_supplier_id"]
        material_id = row["material_id"]
        if down_id not in sup:
            invalid.append((row["dependency_id"], "down", down_id))
        if up_id not in sup:
            invalid.append((row["dependency_id"], "up", up_id))
        if material_id not in mat:
            invalid.append((row["dependency_id"], "mat", material_id))
        if down_id == up_id:
            self_refs.append(row["dependency_id"])
    print("invalid deps", invalid)
    print("self refs", self_refs)
    if invalid:
        errors.append("invalid dependency ids")
    if self_refs:
        errors.append("self-referencing deps")

    print("\n=== BACKUP / SHARED UPSTREAM ===")
    backups = [
        (row["supplier_id"], row["material_id"])
        for row in maps
        if row["is_backup"] in ("1", "true", "True")
    ]
    print("backup mappings", backups)

    down_to_ups = collections.defaultdict(set)
    for row in deps:
        down_to_ups[row["downstream_supplier_id"]].add(row["upstream_supplier_id"])
    shared_pairs = []
    downs = list(down_to_ups)
    for i, left in enumerate(downs):
        for right in downs[i + 1 :]:
            common = down_to_ups[left] & down_to_ups[right]
            if common:
                shared_pairs.append((left, right, sorted(common)))
    print("pairs sharing an upstream:", len(shared_pairs))
    for pair in shared_pairs:
        print(" ", pair)
    if len(shared_pairs) < 1:
        errors.append("no two suppliers share an upstream dependency")

    backup_ids = {supplier_id for supplier_id, _material in backups}
    backup_shared = [
        pair for pair in shared_pairs
        if pair[0] in backup_ids or pair[1] in backup_ids
    ]
    print("backup suppliers in a shared-upstream pair:", backup_shared)
    if len(backup_ids) < 2:
        errors.append("need at least two backup suppliers")
    if not backup_shared:
        errors.append("backup suppliers do not share an upstream dependency")

    print("\n=== SHARED ROUTES ===")
    route_users = collections.defaultdict(list)
    for row in suppliers:
        if row["primary_route_id"]:
            route_users[row["primary_route_id"]].append(row["supplier_id"])
    shared_routes = {rid: users for rid, users in route_users.items() if len(users) >= 2}
    for rid, users in sorted(route_users.items()):
        print(rid, len(users), users)
    print("routes with 2+ suppliers", shared_routes)
    if not shared_routes:
        errors.append("no two suppliers share a transport route")

    print("\n=== MATERIAL MAPPINGS ===")
    mapped = {row["material_id"] for row in maps}
    unmapped = sorted(mat - mapped)
    print("unmapped materials", unmapped)
    if unmapped:
        errors.append("materials with no supplier mapping: %s" % unmapped)
    for row in maps:
        if row["supplier_id"] not in sup:
            errors.append("map unknown supplier " + row["supplier_id"])
        if row["material_id"] not in mat:
            errors.append("map unknown material " + row["material_id"])

    print("\n=== WARNINGS ===")
    if not warnings:
        print("NONE")
    for warning in warnings:
        print(" W", warning)

    print("\n=== ERRORS ===")
    if not errors:
        print("NONE")
    for error in errors:
        print(" E", error)

    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
