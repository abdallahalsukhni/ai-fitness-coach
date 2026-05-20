from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from anthropic import Anthropic
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

class WorkoutLog(BaseModel):
    user_id: str
    text: str

class Query(BaseModel):
    user_id: str
    question: str

def get_embedding(text: str):
    response = anthropic.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"Extract the key fitness data points from this workout log as a comma separated list: {text}"
        }]
    )
    summary = response.content[0].text

    embed_response = anthropic.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{
            "role": "user", 
            "content": f"Return ONLY a JSON array of 1536 numbers between -1 and 1 representing an embedding vector for: {summary}. No explanation, just the array."
        }]
    )
    import json
    embedding = json.loads(embed_response.content[0].text)
    return summary, embedding

@app.get("/")
def root():
    return {"status": "AI Fitness Coach API is running"}

@app.post("/log")
def log_workout(workout: WorkoutLog):
    summary, embedding = get_embedding(workout.text)
    supabase.table("workouts").insert({
        "user_id": workout.user_id,
        "raw_text": workout.text,
        "summary": summary,
        "embedding": embedding
    }).execute()
    return {"message": "Workout logged!", "summary": summary}

@app.post("/ask")
def ask(query: Query):
    _, embedding = get_embedding(query.question)
    results = supabase.rpc("match_workouts", {
        "query_embedding": embedding,
        "match_user_id": query.user_id,
        "match_count": 5
    }).execute()
    
    context = "\n".join([r["raw_text"] for r in results.data])
    
    response = anthropic.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"You are a fitness coach. Based on these past workouts:\n{context}\n\nAnswer this question: {query.question}"
        }]
    )
    return {"answer": response.content[0].text}