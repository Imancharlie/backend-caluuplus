# import_users_custom.py

import json
from uuid import uuid4
from django.utils.dateparse import parse_datetime
from api.models import User  # 👈 replace 'yourapp' with your actual app name

with open("users.json", "r") as file:
    users = json.load(file)

for entry in users:
    fields = entry["fields"]
    email = fields["email"]
    username = fields["username"]
    password = fields["password"]

    if User.objects.filter(email=email).exists():
        print(f"User already exists: {email}")
        continue

    # Combine first_name and last_name as display_name
    display_name = f"{fields['first_name']} {fields['last_name']}".strip()
    if not display_name:
        display_name = email.split('@')[0]  # fallback

    user = User(
        id=uuid4(),  # generate new UUID
        email=email,
        display_name=display_name,
        username=username or email,
        password=password,  # Already hashed — don't call set_password()
        is_active=fields["is_active"],
        is_staff=fields["is_staff"],
        is_superuser=fields["is_superuser"],
        date_joined=parse_datetime(fields["date_joined"]),
        last_login=parse_datetime(fields["last_login"]) if fields["last_login"] else None,
    )

    user.save()
    print(f"Imported: {email}")
