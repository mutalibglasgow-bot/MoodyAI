from services.followupboss import get_people, create_note

people = get_people(limit=1)
person = people["people"][0]

note = create_note(
    person_id=person["id"],
    subject="AI Lead Review",
    body="RealEstateAI test note: this lead was reviewed by Moody AI."
)

print(note)
