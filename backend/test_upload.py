import requests

with open("test.pdf", "wb") as f:
    f.write(b"%PDF-1.4 test")

url = "http://localhost:8000/api/recruiter/upload"
files = [
    ("files", ("test.pdf", open("test.pdf", "rb"), "application/pdf"))
]
response = requests.post(url, files=files)
print(response.json())
