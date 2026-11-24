import re
with open('core/database/models.py', 'r') as f:
    content = f.read()

# Find all __tablename__ definitions
matches = re.findall(r'__tablename__\s*=\s*["\']([^"\']+)["\']', content)
for m in matches:
    print(m)