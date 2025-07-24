"""
vertex_ai_client.py
Client for interacting with Google Cloud Vertex AI Generative Models.
"""
import logging
from typing import Optional, List

try:
    import google.auth
    import vertexai
    from vertexai.generative_models import GenerativeModel, Candidate, Part
    from google.auth import exceptions as google_auth_exceptions
    from google.api_core import exceptions as google_api_exceptions
    from google.cloud import aiplatform
except ImportError:
    logging.error(
        "google-cloud-aiplatform library not found. Please install it with 'pip install google-cloud-aiplatform'"
    )
    # Define dummy classes or raise an error to prevent use if library is missing
    GenerativeModel = None
    Candidate = None
    Part = None

from config.config import Config  # Assuming your Config class is here


class VertexAIClient:
    """
    A client for interacting with Google Cloud Vertex AI, specifically for text generation.
    """

    _initialized = False

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initializes the VertexAIClient.

        Args:
            project_id: Google Cloud Project ID. Defaults to Config.GCP_PROJECT_ID.
            location: Google Cloud Location (e.g., "us-central1"). Defaults to Config.GCP_LOCATION.
            model_name: The name of the Vertex AI model to use (e.g., "gemini-1.5-flash-001").
                        Defaults to Config.VERTEX_AI_MODEL_NAME.
        """
        if not GenerativeModel:
            logging.error(
                "Vertex AI client cannot be initialized because google-cloud-aiplatform is not installed."
            )
            raise RuntimeError(
                "google-cloud-aiplatform library is required for VertexAIClient."
            )

        # Use provided args or fall back to Config
        self.project_id = project_id or Config.GCP_PROJECT_ID
        self.location = location or Config.GCP_LOCATION
        self.model_name = model_name or Config.VERTEX_AI_MODEL_NAME

        # --- Centralized Initialization Logic ---
        # Ensure global initialization happens only once.
        if not VertexAIClient._initialized:
            if not self.project_id:
                raise ValueError("Vertex AI Project ID must be provided or set in Config.")
            if not self.location:
                raise ValueError("Vertex AI Location must be provided or set in Config.")

            try:
                # Let the SDK handle all credential loading and configuration.
                # It will automatically find Application Default Credentials (ADC)
                # and configure both sync and async clients correctly.
                vertexai.init(
                    project=self.project_id,
                    location=self.location,
                )

                VertexAIClient._initialized = True
                logging.info(
                    f"VertexAIClient initialized for project='{self.project_id}', "
                    f"location='{self.location}'"
                )

            except google_auth_exceptions.DefaultCredentialsError as e:
                logging.error(
                    "Google Cloud Default Credentials not found. "
                    "Ensure you are authenticated (e.g., via `gcloud auth application-default login`) "
                    "or GOOGLE_APPLICATION_CREDENTIALS environment variable is set. Error: %s",
                    e,
                )
                raise
            except Exception as e:
                logging.error(f"Failed to initialize Vertex AI client: {e}", exc_info=True)
                raise

        if not self.model_name:
            raise ValueError("Vertex AI Model Name must be provided or set in Config.")
        
        self.model = GenerativeModel(self.model_name)

    async def generate_text(
        self, prompt: str, max_tokens: Optional[int] = None, temperature: Optional[float] = None
    ) -> Optional[str]:
        """
        Generates text using the configured Vertex AI model.

        Args:
            prompt: The text prompt to send to the model.
            max_tokens: Maximum number of tokens to generate. Instructs the model to stop after generating this many tokens.
                        Helps control the length of the generated output.
            temperature: Sampling temperature. Higher values (e.g., 0.8) make the output more random,
                        while lower values (e.g., 0.2) make it more focused and deterministic.

        Returns:
            The generated text as a string, or None if an error occurred.
        """
        logging.debug("Generating text with Vertex AI for prompt: %s", prompt[:100])
        try:
            from vertexai.generative_models import GenerationConfig

            # The client library will handle async credentials automatically after aiplatform.init()
            generation_config = GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
            response = await self.model.generate_content_async(
                [Part.from_text(prompt)],
                generation_config=generation_config,
            )
            # Assuming the response has a 'text' attribute or can be converted to string
            generated_text = response.text
            logging.debug("Successfully received response from Vertex AI.")
            return generated_text
        except Exception as e:
            logging.error(
                "An unexpected error occurred during Vertex AI text generation: %s",
                e,
                exc_info=True,
            )
            return None

# Example Usage (can be run with `python -m genai.vertex_ai_client` from rebot directory)
if __name__ == "__main__":
    import asyncio

    async def main():
        # --- Configuration ---
        # Ensure these are set in your rebot/config/config.py or environment variables
        # Example:
        # Config.GCP_PROJECT_ID = "your-gcp-project-id"
        # Config.GCP_LOCATION = "us-central1"
        # Config.VERTEX_AI_MODEL_NAME = "gemini-1.0-pro-001" # Or other compatible model

        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        
        if not all([Config.GCP_PROJECT_ID, Config.GCP_LOCATION, Config.VERTEX_AI_MODEL_NAME]):
            print("Please set GCP_PROJECT_ID, GCP_LOCATION, and VERTEX_AI_MODEL_NAME in your Config.")
            print("Example for config.py:")
            print("  GCP_PROJECT_ID = \"your-gcp-project-id\"")
            print("  GCP_LOCATION = \"us-central1\"")
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