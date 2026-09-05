with open("../frontend/src/api/client.ts", "r") as f:
    content = f.read()

if "getCompanyReports" not in content:
    new_content = content.replace("  },\n};", """  },
  getCompanyReports: async () => {
    const res = await fetch(`${BASE_URL}/reports/companies`, { headers: recruiterHeaders() });
    if (!res.ok) throw new Error("Error fetching company reports");
    return res.json();
  },
  getOfferReports: async () => {
    const res = await fetch(`${BASE_URL}/reports/offers`, { headers: recruiterHeaders() });
    if (!res.ok) throw new Error("Error fetching offer reports");
    return res.json();
  },
};""")
    with open("../frontend/src/api/client.ts", "w") as f:
        f.write(new_content)
