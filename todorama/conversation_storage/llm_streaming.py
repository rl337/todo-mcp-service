"""LLM streaming operations."""

import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from todorama.adapters import HTTPClientAdapterFactory, HTTPError, HTTPResponse

logger = logging.getLogger(__name__)


class LLMStreamingManager:
    """Manages LLM streaming operations."""
    
    def __init__(
        self,
        llm_api_url: str,
        llm_api_key: str,
        llm_model: str,
        llm_enabled: bool,
        get_or_create_conversation_func: callable = None,
        assign_ab_variant_func: callable = None,
        get_ab_test_func: callable = None,
        get_prompt_template_for_conversation_func: callable = None,
        record_ab_metric_func: callable = None
    ):
        """
        Initialize LLM streaming manager.
        
        Args:
            llm_api_url: LLM API URL
            llm_api_key: LLM API key
            llm_model: Default LLM model
            llm_enabled: Whether LLM is enabled
            get_or_create_conversation_func: Function to get or create conversation
            assign_ab_variant_func: Function to assign AB variant
            get_ab_test_func: Function to get AB test
            get_prompt_template_for_conversation_func: Function to get prompt template
            record_ab_metric_func: Function to record AB metrics
        """
        self.llm_api_url = llm_api_url
        self.llm_api_key = llm_api_key
        self.llm_model = llm_model
        self.llm_enabled = llm_enabled
        self.get_or_create_conversation = get_or_create_conversation_func
        self.assign_ab_variant = assign_ab_variant_func
        self.get_ab_test = get_ab_test_func
        self.get_prompt_template_for_conversation = get_prompt_template_for_conversation_func
        self.record_ab_metric = record_ab_metric_func
    
    def _setup_ab_testing(
        self,
        ab_test_id: Optional[int],
        user_id: Optional[str],
        chat_id: Optional[str]
    ) -> tuple:
        """
        Setup A/B testing configuration.
        
        Returns:
            Tuple of (ab_variant, conversation_id, test_config, ab_test_start_time, model_to_use, temperature, system_prompt)
        """
        ab_variant = None
        conversation_id = None
        test_config = None
        ab_test_start_time = None
        model_to_use = self.llm_model
        temperature = 0.7
        system_prompt = None
        
        if ab_test_id and user_id and chat_id:
            if self.get_or_create_conversation:
                conversation_id = self.get_or_create_conversation(user_id, chat_id)
            if self.assign_ab_variant and conversation_id:
                ab_variant = self.assign_ab_variant(conversation_id, ab_test_id)
            if self.get_ab_test:
                test_config = self.get_ab_test(ab_test_id)
            ab_test_start_time = datetime.now()
            
            if test_config and ab_variant:
                variant_config_str = test_config['variant_config'] if ab_variant == 'variant' else test_config['control_config']
                variant_config = json.loads(variant_config_str)
                
                if 'model' in variant_config:
                    model_to_use = variant_config['model']
                if 'temperature' in variant_config:
                    temperature = variant_config['temperature']
                if 'system_prompt' in variant_config:
                    system_prompt = variant_config['system_prompt']
        
        return ab_variant, conversation_id, test_config, ab_test_start_time, model_to_use, temperature, system_prompt
    
    def _format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format messages for LLM API."""
        return [
            {"role": msg.get('role', 'user'), "content": msg.get('content', '')}
            for msg in messages
        ]
    
    def _prepare_system_content(
        self,
        user_id: Optional[str],
        chat_id: Optional[str],
        system_prompt: Optional[str]
    ) -> str:
        """Prepare system content from template or prompt."""
        template_content = None
        if user_id and chat_id and self.get_prompt_template_for_conversation:
            template = self.get_prompt_template_for_conversation(user_id, chat_id, "chat")
            if template:
                template_content = template['template_content']
        
        if template_content:
            return template_content
        elif system_prompt:
            return system_prompt
        else:
            return "You are a helpful assistant."
    
    def _prepare_request(
        self,
        api_messages: List[Dict[str, Any]],
        model_to_use: str,
        temperature: float,
        max_tokens: Optional[int]
    ) -> tuple:
        """Prepare HTTP request headers and payload."""
        headers = {
            "Authorization": f"Bearer {self.llm_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model_to_use,
            "messages": api_messages,
            "stream": True,
            "temperature": temperature
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        return headers, payload
    
    async def _parse_sse_chunk(self, data_str: str) -> tuple:
        """
        Parse Server-Sent Events chunk.
        
        Returns:
            Tuple of (content, tokens_used, input_tokens, output_tokens)
        """
        if data_str.strip() == "[DONE]":
            return None, None, None, None
        
        try:
            data = json.loads(data_str)
            
            content = None
            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]
                delta = choice.get("delta", {})
                content = delta.get("content", "")
            
            tokens_used = None
            input_tokens = None
            output_tokens = None
            if "usage" in data:
                tokens_used = data["usage"].get("total_tokens")
                input_tokens = data["usage"].get("prompt_tokens", 0)
                output_tokens = data["usage"].get("completion_tokens", 0)
            
            return content, tokens_used, input_tokens, output_tokens
            
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse SSE data: {data_str}")
            return None, None, None, None
        except Exception as e:
            logger.warning(f"Error processing SSE chunk: {e}")
            return None, None, None, None
    
    def _track_costs(
        self,
        user_id: Optional[str],
        conversation_id: Optional[int],
        model_to_use: str,
        tokens_used: Optional[int],
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        temperature: float,
        max_tokens: Optional[int],
        ab_test_id: Optional[int],
        ab_variant: Optional[str]
    ):
        """Track LLM usage costs."""
        if not (user_id and conversation_id and tokens_used):
            return
        
        try:
            from cost_tracking import CostTracker, ServiceType
            cost_tracker = CostTracker()
            
            if input_tokens is None or output_tokens is None:
                input_tokens = int(tokens_used * 0.6)
                output_tokens = tokens_used - input_tokens
            
            cost = cost_tracker.calculate_llm_cost(
                model=model_to_use,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
            cost_tracker.record_cost(
                service_type=ServiceType.LLM,
                user_id=user_id,
                conversation_id=conversation_id,
                cost=cost,
                tokens=tokens_used,
                metadata={
                    "model": model_to_use,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "ab_test_id": ab_test_id,
                    "ab_variant": ab_variant
                }
            )
        except Exception as e:
            logger.warning(f"Failed to track LLM cost: {e}", exc_info=True)
    
    def _record_ab_metrics(
        self,
        ab_test_id: Optional[int],
        conversation_id: Optional[int],
        ab_variant: Optional[str],
        ab_test_start_time: Optional[datetime],
        tokens_used: Optional[int],
        response_content: str,
        error_occurred: bool
    ):
        """Record A/B test metrics."""
        if not (ab_test_id and conversation_id and ab_variant):
            return
        
        try:
            response_time_ms = None
            if ab_test_start_time:
                response_time_ms = int((datetime.now() - ab_test_start_time).total_seconds() * 1000)
            
            if tokens_used is None and response_content:
                tokens_used = len(response_content) // 4
            
            if self.record_ab_metric:
                self.record_ab_metric(
                    test_id=ab_test_id,
                    conversation_id=conversation_id,
                    variant=ab_variant,
                    response_time_ms=response_time_ms,
                    tokens_used=tokens_used,
                    error_occurred=error_occurred
                )
        except Exception as e:
            logger.warning(f"Failed to record A/B test metrics: {e}", exc_info=True)
    
    async def stream_response(
        self,
        messages: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        ab_test_id: Optional[int] = None
    ):
        """
        Stream LLM response character-by-character.
        
        Uses Server-Sent Events (SSE) to stream responses from OpenAI-compatible APIs.
        Yields text chunks as they arrive from the LLM.
        """
        if not self.llm_enabled:
            raise ValueError("LLM not configured. Set LLM_API_URL and LLM_API_KEY environment variables.")
        
        # Setup A/B testing
        ab_variant, conversation_id, test_config, ab_test_start_time, model_to_use, temperature, system_prompt = self._setup_ab_testing(
            ab_test_id, user_id, chat_id
        )
        
        # Format messages
        formatted_messages = self._format_messages(messages)
        
        # Prepare system content
        system_content = self._prepare_system_content(user_id, chat_id, system_prompt)
        
        # Add system message if provided
        if system_content:
            system_message = {"role": "system", "content": system_content}
            api_messages = [system_message] + formatted_messages
        else:
            api_messages = formatted_messages
        
        # Prepare request
        headers, payload = self._prepare_request(api_messages, model_to_use, temperature, max_tokens)
        
        # Make streaming request
        response_content = ""
        tokens_used = None
        input_tokens = None
        output_tokens = None
        error_occurred = False
        
        try:
            async with HTTPClientAdapterFactory.create_async_client(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.llm_api_url.rstrip('/')}/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    wrapped_response = HTTPResponse(response)
                    wrapped_response.raise_for_status()
                    
                    # Parse Server-Sent Events
                    async for line in wrapped_response.aiter_lines():
                        if not line.strip():
                            continue
                        
                        if line.startswith("data: "):
                            data_str = line[6:]
                            
                            if data_str.strip() == "[DONE]":
                                break
                            
                            content, chunk_tokens, chunk_input, chunk_output = await self._parse_sse_chunk(data_str)
                            
                            if content:
                                response_content += content
                                yield content
                            
                            if chunk_tokens is not None:
                                tokens_used = chunk_tokens
                            if chunk_input is not None:
                                input_tokens = chunk_input
                            if chunk_output is not None:
                                output_tokens = chunk_output
                    
                    logger.debug("Finished streaming LLM response")
        
        except HTTPError as e:
            error_occurred = True
            logger.error(f"HTTP error calling LLM API for streaming: {e}", exc_info=True)
            raise
        except Exception as e:
            error_occurred = True
            logger.error(f"Error streaming LLM response: {e}", exc_info=True)
            raise
        finally:
            # Track costs
            if tokens_used is None and response_content:
                tokens_used = len(response_content) // 4
            
            self._track_costs(
                user_id=user_id,
                conversation_id=conversation_id,
                model_to_use=model_to_use,
                tokens_used=tokens_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                temperature=temperature,
                max_tokens=max_tokens,
                ab_test_id=ab_test_id,
                ab_variant=ab_variant
            )
            
            # Record A/B test metrics
            self._record_ab_metrics(
                ab_test_id=ab_test_id,
                conversation_id=conversation_id,
                ab_variant=ab_variant,
                ab_test_start_time=ab_test_start_time,
                tokens_used=tokens_used,
                response_content=response_content,
                error_occurred=error_occurred
            )
