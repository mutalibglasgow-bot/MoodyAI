from tools.followupboss import get_people

print("Getting leads...")

people = get_people()

from tools.followupboss import get_people

people = get_people()

for person in people.get("people", []):

    print("---------------------------------")

    print("Name:", person.get("displayName"))

    print("Email:", person.get("primaryEmail"))

    print("Phone:", person.get("primaryPhone"))

    print("Stage:", person.get("stage"))