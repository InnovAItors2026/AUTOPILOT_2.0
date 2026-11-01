from src.data_loader import load_all_data

d = load_all_data(verbose=False)

print("\nORDER STATUSES:")
print(d["customer_orders"]["status"].value_counts(dropna=False))

print("\nINVENTORY LOCATION TYPES:")
print(d["inventory"]["location_type"].value_counts(dropna=False))

print("\nDEPENDENCY TYPES:")
print(d["supplier_dependencies"]["dependency_type"].value_counts(dropna=False))

print("\nMATERIAL PRODUCT MAPPING:")
print(d["materials"]["used_in_product"].head(5).tolist())

print("\nTRANSPORT ROUTES:")
print(d["transport_routes"][
    ["route_id", "origin_type", "destination_type", "shared_supplier_ids"]
].to_string(index=False))