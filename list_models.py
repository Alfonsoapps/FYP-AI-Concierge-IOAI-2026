from google import genai

client = genai.Client(api_key="AIzaSyB4Mxt_ocpmfHNN5K13FcrQ3N2pqwLUNWM")

models = client.models.list()

for m in models:
    print(m.name)