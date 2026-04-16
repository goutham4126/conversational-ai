from fastapi import FastAPI
import requests

app = FastAPI()

BASE_URL = "https://jsonplaceholder.typicode.com"

# Get all posts
@app.get("/tools/get_posts")
async def get_posts():
    res = requests.get(f"{BASE_URL}/posts")
    return res.json()

# Get post by ID
@app.get("/tools/get_post_by_id")
async def get_post_by_id(post_id: int):
    res = requests.get(f"{BASE_URL}/posts/{post_id}")
    return res.json()

# Get posts by user ID
@app.get("/tools/get_posts_by_user")
async def get_posts_by_user(user_id: int):
    res = requests.get(f"{BASE_URL}/posts", params={"userId": user_id})
    return res.json()

# Tool registry
@app.get("/tools")
async def list_tools():
    return {
        "tools": [
            {
                "name": "get_posts",
                "description": "Get all posts",
                "input_schema": {"type": "object", "properties": {}}
            },
            {
                "name": "get_post_by_id",
                "description": "Get a post by ID",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "post_id": {"type": "integer"}
                    },
                    "required": ["post_id"]
                }
            },
            {
                "name": "get_posts_by_user",
                "description": "Get posts by user ID",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer"}
                    },
                    "required": ["user_id"]
                }
            }
        ]
    }