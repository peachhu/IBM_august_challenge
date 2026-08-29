import requests
r = requests.get("https://ll.thespacedevs.com/2.2.0/launch/previous/",
                  params={"search": "Cape Canaveral", "limit": 40, "mode": "detailed"})
results = r.json()["results"]

for l in results:
    hr = l.get("holdreason")
    if hr:
        print(l["name"], "→ HOLD:", hr)

print("---")
print(f"Total: {len(results)}, With holdreason: {sum(1 for l in results if l.get('holdreason'))}")