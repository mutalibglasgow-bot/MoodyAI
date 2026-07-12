from datetime import date
from services.followupboss import get_people, create_task

people = get_people(limit=1)
person = people["people"][0]

task = create_task(
    person_id=person["id"],
    description="Follow up with this lead based on AI Morning Brief.",
    due_date=date.today().isoformat()
)

print(task)
