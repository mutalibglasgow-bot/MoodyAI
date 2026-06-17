# ======================================================
# Moody AI - Lesson 2
# Lead Scoring Tool
# ======================================================

print("\n==============================")
print("     Moody AI Lead Scorer")
print("==============================\n")

# Get information from the user
name = input("Client Name: ")
budget = int(input("Budget ($): "))
city = input("Current City: ")
employer = input("Employer: ")

score = 0

# Budget Score
if budget >= 700000:
    score += 50
elif budget >= 500000:
    score += 40
elif budget >= 350000:
    score += 30
else:
    score += 20

# Employer Score
if "bsw" in employer.lower():
    score += 30
elif "hospital" in employer.lower():
    score += 20

# City Score
high_value_cities = [
    "austin",
    "dallas",
    "houston",
    "round rock",
    "georgetown"
]

if city.lower() in high_value_cities:
    score += 20

# Determine Rating
if score >= 90:
    rating = "★★★★★ Hot Lead"
elif score >= 70:
    rating = "★★★★ Strong Lead"
elif score >= 50:
    rating = "★★★ Good Lead"
elif score >= 30:
    rating = "★★ Fair Lead"
else:
    rating = "★ Low Priority"

print("\n==============================")
print("Lead Summary")
print("==============================")

print(f"Name      : {name}")
print(f"Budget    : ${budget:,.0f}")
print(f"City      : {city}")
print(f"Employer  : {employer}")

print("------------------------------")
print(f"Lead Score: {score}")
print(f"Rating    : {rating}")
print("==============================")