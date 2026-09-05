import csv
import json
import urllib.request
import os
import ast

url = "http://localhost:8000/openapi.json"
base_url = "http://localhost:8000"

print("Fetching OpenAPI schema from running server...")
try:
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode())
        
        endpoints = []
        for path, methods in data.get("paths", {}).items():
            for method, details in methods.items():
                full_url = f"{base_url}{path}"
                endpoints.append({
                    "URL Completa (Postman)": full_url,
                    "Metodo": method.upper(),
                    "Nombre Endpoint": details.get("summary", ""),
                    "Ruta Interna": path,
                    "Tags": ", ".join(details.get("tags", []))
                })
        
        if endpoints:
            keys = endpoints[0].keys()
            with open("/Users/dfurniel/pri-mvp/Mapa_Endpoints_API_PRI.csv", "w", newline="", encoding="utf-8-sig") as f:
                dict_writer = csv.DictWriter(f, keys)
                dict_writer.writeheader()
                dict_writer.writerows(endpoints)
            
            print("Successfully updated API endpoints CSV with full URLs.")
            
            # Also save openapi.json for direct import
            with open("/Users/dfurniel/pri-mvp/coleccion_postman_pri.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print("Saved coleccion_postman_pri.json for direct Postman import.")
            
except Exception as e:
    print(f"Error fetching openapi.json: {e}")
    print("Is the backend server running on port 8000?")

