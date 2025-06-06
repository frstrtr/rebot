"""
vertex_ai_client.py
Client for interacting with Google Cloud Vertex AI Generative Models.
"""
import logging
from typing import Optional, List

try:
    import vertexai
    from vertexai.generative_models import GenerativeModel, Candidate, Part
    from google.auth import exceptions as google_auth_exceptions
    from google.api_core import exceptions as google_api_exceptions
except ImportError:
    logging.error(
        "google-cloud-aiplatform library not found. Please install it with 'pip install google-cloud-aiplatform'"
    )
    # Define dummy classes or raise an error to prevent use if library is missing
    GenerativeModel = None 
    Candidate = None
    Part = None

from config.config import Config # Assuming your Config class is here

class VertexAIClient:
    """
    A client for interacting with Google Cloud Vertex AI, specifically for text generation.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initializes the VertexAIClient.

        Args:
            project_id: Google Cloud Project ID. Defaults to Config.VERTEX_AI_PROJECT_ID.
            location: Google Cloud Location (e.g., "us-central1"). Defaults to Config.VERTEX_AI_LOCATION.
            model_name: The name of the Vertex AI model to use (e.g., "gemini-1.0-pro-001").
                        Defaults to Config.VERTEX_AI_MODEL_NAME.
        """
        if not GenerativeModel:
            logging.error("Vertex AI client cannot be initialized because google-cloud-aiplatform is not installed.")
            raise RuntimeError("google-cloud-aiplatform library is required for VertexAIClient.")

        self.project_id = project_id or Config.VERTEX_AI_PROJECT_ID
        self.location = location or Config.VERTEX_AI_LOCATION
        self.model_name = model_name or Config.VERTEX_AI_MODEL_NAME

        if not self.project_id:
            logging.error("Vertex AI Project ID is not configured.")
            raise ValueError("Vertex AI Project ID must be provided or set in Config.")
        if not self.location:
            logging.error("Vertex AI Location is not configured.")
            raise ValueError("Vertex AI Location must be provided or set in Config.")
        if not self.model_name:
            logging.error("Vertex AI Model Name is not configured.")
            raise ValueError("Vertex AI Model Name must be provided or set in Config.")

        try:
            vertexai.init(project=self.project_id, location=self.location)
            self.model = GenerativeModel(self.model_name)
            logging.info(
                f"VertexAIClient initialized for project='{self.project_id}', "
                f"location='{self.location}', model='{self.model_name}'"
            )
        except google_auth_exceptions.DefaultCredentialsError as e:
            logging.error(
                "Google Cloud Default Credentials not found. "
                "Ensure you are authenticated (e.g., via `gcloud auth application-default login`) "
                "or GOOGLE_APPLICATION_CREDENTIALS environment variable is set. Error: %s", e
            )
            raise
        except Exception as e:
            logging.error(f"Failed to initialize Vertex AI client: {e}", exc_info=True)
            raise

    async def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_output_tokens: int = 1024,
        top_p: float = 0.95,
        top_k: int = 40,
    ) -> Optional[str]:
        """
        Generates text using the configured Vertex AI model.

        Args:
            prompt: The text prompt to send to the model.
            temperature: Controls randomness. Lower values are more deterministic.
            max_output_tokens: Maximum number of tokens to generate.
            top_p: Nucleus sampling parameter.
            top_k: Top-k sampling parameter.

        Returns:
            The generated text as a string, or None if an error occurred or no content was generated.
        """
        if not self.model:
            logging.error("Vertex AI model is not initialized.")
            return None

        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "top_p": top_p,
            "top_k": top_k,
        }

        try:
            logging.debug(f"Sending prompt to Vertex AI: '{prompt[:100]}...' with config: {generation_config}")
            response = await self.model.generate_content_async(
                prompt,
                generation_config=generation_config
            )
            
            logging.debug(f"Vertex AI response received. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")

            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                # Assuming the first part of the first candidate contains the text
                generated_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
                if not generated_text.strip() and response.candidates[0].finish_reason.name != "SAFETY": # Check if empty due to safety
                     logging.warning(f"Vertex AI generated empty text for prompt: {prompt[:100]}... Finish Reason: {response.candidates[0].finish_reason}")

                return generated_text
            else:
                # Log safety ratings if available and content is missing/empty
                if response.candidates and response.candidates[0].finish_reason.name == "SAFETY":
                    safety_ratings_log = [str(rating) for rating in response.candidates[0].safety_ratings]
                    logging.warning(
                        f"Vertex AI content generation blocked due to safety reasons. Prompt: '{prompt[:100]}...'. "
                        f"Finish Reason: {response.candidates[0].finish_reason}. Safety Ratings: {safety_ratings_log}"
                    )
                elif not response.candidates:
                     logging.warning(f"Vertex AI response had no candidates. Prompt: '{prompt[:100]}...'")
                else: # Candidates exist, but no content.parts or empty parts
                    logging.warning(
                        f"Vertex AI response did not contain expected content parts. Prompt: '{prompt[:100]}...'. "
                        f"Candidate: {response.candidates[0]}"
                    )
                return None

        except google_api_exceptions.GoogleAPIError as e:
            logging.error(f"Vertex AI API error: {e}", exc_info=True)
            # Specific error codes can be checked here, e.g., e.code == 429 for rate limits
            if isinstance(e, (google_api_exceptions.Unauthorized, google_api_exceptions.Forbidden)):
                 logging.error("Permission denied error with Vertex AI. Check IAM roles for the service account/user.")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred during Vertex AI text generation: {e}", exc_info=True)
            return None

# Example Usage (can be run with `python -m genai.vertex_ai_client` from rebot directory)
if __name__ == "__main__":
    import asyncio

    async def main():
        # --- Configuration ---
        # Ensure these are set in your rebot/config/config.py or environment variables
        # Example:
        # Config.VERTEX_AI_PROJECT_ID = "your-gcp-project-id"
        # Config.VERTEX_AI_LOCATION = "us-central1"
        # Config.VERTEX_AI_MODEL_NAME = "gemini-1.0-pro-001" # Or other compatible model

        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        
        if not all([Config.VERTEX_AI_PROJECT_ID, Config.VERTEX_AI_LOCATION, Config.VERTEX_AI_MODEL_NAME]):
            print("Please set VERTEX_AI_PROJECT_ID, VERTEX_AI_LOCATION, and VERTEX_AI_MODEL_NAME in your Config.")
            print("Example for config.py:")
            print("  VERTEX_AI_PROJECT_ID = \"your-gcp-project-id\"")
            print("  VERTEX_AI_LOCATION = \"us-central1\"")
            print("  VERTEX_AI_MODEL_NAME = \"gemini-1.0-pro-001\"") # Or your preferred model
            return

        try:
            client = VertexAIClient()
        except Exception as e:
            print(f"Failed to initialize VertexAIClient: {e}")
            return

        test_prompt = "Explain the concept of a Large Language Model in simple terms."
        print(f"\n--- Testing Vertex AI: Sending prompt ---\n'{test_prompt}'")
        
        generated_text = await client.generate_text(test_prompt)

        if generated_text is not None:
            print("\n--- Generated Text ---")
            print(generated_text)
        else:
            print("\n--- Failed to generate text or no content returned ---")
            print("Check logs for more details. Ensure your GCP project, location, model, and authentication are correct.")

    asyncio.run(main())