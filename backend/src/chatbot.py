from pydantic import BaseModel, Field
from typing import List, Optional
from dotenv import load_dotenv
import os

try:
    from google import genai
except Exception:
    genai = None

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
class Response(BaseModel):
    stop: str
    train: str
    delay: Optional[int] = Field(0, description="Delay in seconds, if available")
    response: str


class Chatbot:
    def __init__(self):
        self.client = genai.Client(api_key=api_key) if genai and api_key else None
        self.model_id = "gemini-2.5-flash"
    getWeather = {
        "name": "getWeather",
        "description": "Get the current weather conditions at a specific location.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The location for which to get the weather (e.g., 'New York City')."
                }
            },
            "required": ["location"]
        }
    }
    def get_response(self, stop_name, train, current_delay, train_data, stop_data, message=None) -> Response:
        # best-effort weather lookup
        try:
            from utils import weather as weather_util
            weather = weather_util.get_weather_by_place(stop_name)
        except Exception:
            weather = None

        if weather:
            weather_summary = f"{weather.get('temp_c')}C, {weather.get('description') or ''} (src={weather.get('source')})"
        else:
            weather_summary = "unavailable"

        prompt = f"""
You are a helpful assistant for MTA subway riders. You have access to the following information:
- Current delay for the train: {current_delay} seconds
- Train data: {train_data}
- Stop data: {stop_data}
- External weather data: {weather_summary}
    - User message: {message or 'none'}

Based on this information, provide a response to the user about the expected arrival time of their train and any relevant details about the delay. If there is no delay, confirm that the train is on time. If you believe a delay is likely to occur, provide an estimate of the expected delay and any potential causes based on the train and stop data or external factors.

"""

        if self.client:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
            )
            response_text = response.text
        else:
            response_text = (
                f"Live chatbot fallback: {train} train at {stop_name} is currently "
                f"reporting about {current_delay} seconds of delay."
            )

        return Response(stop=stop_name, train=train, delay=current_delay, response=response_text)



    
