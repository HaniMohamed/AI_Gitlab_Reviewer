"""
Model abstraction layer supporting both Ollama and API-based models.
"""
from langchain_community.llms import Ollama
from typing import Optional, Union
import requests
from config import OLLAMA_BASE_URL, OLLAMA_MODEL


class ModelProvider:
    """Enum-like class for model providers."""
    OLLAMA = "ollama"
    API = "api"


class UnifiedLLM:
    """
    Unified LLM wrapper that supports both Ollama and API-based models.
    """
    
    def __init__(
        self,
        provider: str = ModelProvider.OLLAMA,
        model_name: str = OLLAMA_MODEL,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_endpoint: Optional[str] = None
    ):
        """
        Initialize the unified LLM.
        
        Args:
            provider: Either "ollama" or "api"
            model_name: Model name (for Ollama) or model identifier (for API)
            base_url: Base URL for Ollama (defaults to config)
            api_key: API key for API-based models
            api_endpoint: API endpoint URL for API-based models
        """
        self.provider = provider
        self.model_name = model_name
        self.api_key = api_key
        self.api_endpoint = api_endpoint or "https://llm-platform.gosi.ins/api/chat/completions"
        
        if provider == ModelProvider.OLLAMA:
            self.llm = Ollama(
                model=model_name,
                base_url=base_url or OLLAMA_BASE_URL
            )
        elif provider == ModelProvider.API:
            # For API-based models, we'll use direct API calls
            self.llm = None  # We'll use direct API calls instead
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def __call__(self, prompt: str) -> str:
        """
        Call the LLM with a prompt.
        
        Args:
            prompt: The input prompt
            
        Returns:
            The model's response as a string
        """
        if self.provider == ModelProvider.OLLAMA:
            # Ollama uses direct call
            return self.llm(prompt)
        elif self.provider == ModelProvider.API:
            # API-based models use direct API calls
            return self._direct_api_call(prompt)
    
    def _direct_api_call(self, prompt: str) -> str:
        """
        Fallback method to make direct API calls if LangChain fails.
        
        Args:
            prompt: The input prompt
            
        Returns:
            The model's response as a string
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "accept": "application/json",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        try:
            response = requests.post(
                self.api_endpoint,
                headers=headers,
                json=data,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            
            # Extract content from response
            if "choices" in result and len(result["choices"]) > 0:
                message = result["choices"][0].get("message", {})
                return message.get("content", "")
            else:
                raise ValueError(f"Unexpected API response format: {result}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API call failed: {str(e)}")
    
    def get_model_info(self) -> dict:
        """Get information about the current model configuration."""
        if self.provider == ModelProvider.OLLAMA:
            return {
                "provider": "Ollama",
                "model": self.model_name,
                "base_url": getattr(self.llm, 'base_url', OLLAMA_BASE_URL)
            }
        else:
            return {
                "provider": "API",
                "model": self.model_name,
                "endpoint": self.api_endpoint
            }


# Global LLM instance (will be updated when model changes)
_global_llm = UnifiedLLM(provider=ModelProvider.OLLAMA, model_name=OLLAMA_MODEL)


def get_llm() -> UnifiedLLM:
    """Get the current global LLM instance."""
    return _global_llm


def set_llm(
    provider: str = ModelProvider.OLLAMA,
    model_name: str = OLLAMA_MODEL,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    api_endpoint: Optional[str] = None
) -> UnifiedLLM:
    """
    Set the global LLM instance.
    
    Args:
        provider: Either "ollama" or "api"
        model_name: Model name/identifier
        base_url: Base URL for Ollama
        api_key: API key for API-based models
        api_endpoint: API endpoint URL for API-based models
        
    Returns:
        The new global LLM instance
    """
    global _global_llm
    _global_llm = UnifiedLLM(
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        api_endpoint=api_endpoint
    )
    return _global_llm
