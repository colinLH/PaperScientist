from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

load_dotenv()

# model = init_chat_model("google_genai:gemini-3.1-pro-preview")
# response = model.invoke("Why do parrots talk?")
# print(response)


model = init_chat_model("deepseek:deepseek-chat")
response = model.invoke("Why do parrots talk?")
print(response)