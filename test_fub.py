from dotenv import load_dotenv
load_dotenv()

from services.followupboss import get_people

people = get_people()

print(people)
