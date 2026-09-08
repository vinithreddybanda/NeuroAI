import os

from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

checks = []

groq1 = os.getenv("GROQ_API_KEY_1") or os.getenv("GROQ_API_KEY")
groq2 = os.getenv("GROQ_API_KEY_2")
openai_key = os.getenv("OPENAI_API_KEY")
gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

if groq1:
    ChatGroq(api_key=groq1, model="openai/gpt-oss-120b")
    checks.append("Groq #1")
if groq2:
    ChatGroq(api_key=groq2, model="openai/gpt-oss-120b")
    checks.append("Groq #2")
if openai_key:
    ChatOpenAI(api_key=openai_key, model="gpt-5.4-mini")
    checks.append("OpenAI")
if gemini_key:
    ChatGoogleGenerativeAI(google_api_key=gemini_key, model="gemini-3.8-flash")
    checks.append("Gemini")

assert checks, "No configured LLM credentials found"
print("OK - LLM clients construct successfully: " + ", ".join(checks))