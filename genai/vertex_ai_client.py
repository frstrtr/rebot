"""
vertex_ai_client.py
Client for interacting with Google Cloud Vertex AI Generative Models.
"""
import logging
import asyncio
from typing import Optional

import vertexai
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel, Part

from config.config import Config

logger = logging.getLogger(__name__)


class VertexAIClient:
    """A client for interacting with Google's Vertex AI Generative Models."""

    _initialized = False

    def __init__(self, model_name: Optional[str] = None):
        """
        Initializes the Vertex AI client.

        Args:
            model_name: The name of the generative model to use.
                        Defaults to the one specified in the global Config.
        """
        if not VertexAIClient._initialized:
            try:
                gcp_project_id = Config.GCP_PROJECT_ID
                gcp_location = Config.GCP_LOCATION

                if not gcp_project_id or not gcp_location:
                    raise ValueError(
                        "GCP_PROJECT_ID and GCP_LOCATION must be set in the config."
                    )

                aiplatform.init(project=gcp_project_id, location=gcp_location)
                VertexAIClient._initialized = True
                logger.info(
                    "Vertex AI SDK initialized successfully for project '%s' in location '%s'.",
                    gcp_project_id,
                    gcp_location,
                )

            except Exception as e:
                logger.critical(
                    f"Failed to initialize Vertex AI SDK: {e}", exc_info=True
                )
                raise

        # Use the provided model_name or fall back to the one in Config
        self.model = GenerativeModel(model_name or Config.VERTEX_AI_MODEL_NAME)

    async def generate_text(self, prompt: str) -> Optional[str]:
        """
        Generates text using the configured Vertex AI model.

        Args:
            prompt: The text prompt to send to the model.

        Returns:
            The generated text as a string, or None if an error occurred.
        """
        logger.debug("Generating text with Vertex AI for prompt: %s", prompt[:100])
        try:
            # The client library will handle async credentials automatically after aiplatform.init()
            response = await self.model.generate_content_async(
                [Part.from_text(prompt)]
            )
            # Assuming the response has a 'text' attribute or can be converted to string
            generated_text = response.text
            logger.debug("Successfully received response from Vertex AI.")
            return generated_text
        except Exception as e:
            logger.error(
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