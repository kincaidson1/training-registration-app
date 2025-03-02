from werkzeug.security import generate_password_hash

password = 'admin123'
hashed = generate_password_hash(password)
print(f"Password hash for '{password}':")
print(hashed)
