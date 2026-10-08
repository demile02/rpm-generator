#!/usr/bin/env python3
"""
9Router API Client - Real AI Gateway Integration
Actual 9Router API calls (combo=rpm) for the RPM pipeline
"""

import os
import json
import re
import time
import requests
import logging
from typing import Dict, Optional
from dataclasses import dataclass

# Configure logging
logger = logging.getLogger(__name__)


def _default_dotenv_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, '.env')


# Dioverride tes untuk isolasi hermetik (monkeypatch ke file tmp).
_DOTENV_PATH: Optional[str] = None


def _load_dotenv(path: Optional[str] = None) -> None:
    """Muat file `.env` di root proyek bila ada (opsional).

    Environment proses selalu menang (`override=False`): user yang
    mengekspor variabel secara eksplisit tidak akan ditimpa isi file.
    Tanpa paket python-dotenv, fungsi ini diam (no-op).
    Di bawah pytest, `.env` repo TIDAK dibaca kecuali path eksplisit
    diberikan (atau `_DOTENV_PATH` di-override) agar tes hermetik.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    target = path if path is not None else _DOTENV_PATH
    if target is None:
        if 'PYTEST_CURRENT_TEST' in os.environ:
            return  # hermetik: .env user tidak boleh bocor ke tes
        target = _default_dotenv_path()
    else:
        target = str(target)
    if os.path.exists(target):
        load_dotenv(target, override=False)


class NineRouterError(Exception):
    """Base exception for 9Router client errors."""
    pass


class AuthenticationError(NineRouterError):
    """Authentication/authorization failed."""
    pass


class ValidationError(NineRouterError):
    """Response validation failed."""
    pass


class TimeoutError(NineRouterError):
    """Request timeout."""
    pass


class RateLimitError(NineRouterError):
    """Rate limit exceeded."""
    pass


class ServerError(NineRouterError):
    """Server error (5xx)."""
    pass


class NetworkError(NineRouterError):
    """Network/connection failure (connection reset, dropped socket)."""
    pass


# ---------------------------------------------------------------------------
# Reliability policy (task: HARDEN 9ROUTER `rpm` RELIABILITY).
#
# Retryable  : malformed model JSON, empty model content, 429, timeout,
#              connection reset, 500/502/503/504.
# Non-retry. : auth (401/403), invalid request (4xx), unsupported model,
#              malformed local request. Pipeline-level validation failures
#              (KKTP/TP/protected fields) never reach the client at all —
#              the pipeline stops before another router call.
#
# Bounded: max_retries (default 2) EXTRA attempts => at most 3 attempts.
# Backoff: retry 1 -> short delay, retry 2 -> longer delay, capped;
# a 429 Retry-After header is honored up to MAX_BACKOFF_SECONDS.
# ---------------------------------------------------------------------------
RETRY_BACKOFF_SCHEDULE = {0: 1.0, 1: 3.0}  # keyed by 0-based retry index
MAX_BACKOFF_SECONDS = 10.0

# One-line recovery note appended ON THE FIRST JSON RETRY ONLY. It changes
# output FORMAT, never the semantic task: same prompt body, same curriculum
# context, same requested schema (no drift to CP/TP/KKTP/topic/subject).
JSON_RETRY_NOTE = (
    "\n\nPERHATIAN (percobaan ulang): respons sebelumnya bukan JSON valid. "
    "Kembalikan struktur JSON yang PERSIS diminta di atas. Output HANYA JSON "
    "valid: tanpa markdown fence, tanpa komentar, tanpa teks tambahan."
)


@dataclass
class NineRouterConfig:
    """Configuration for 9Router client."""
    base_url: str = "http://localhost:20128"
    api_key: Optional[str] = None
    combo: str = "rpm"
    # Real `rpm` calls with large structured-JSON payloads (rubric
    # descriptors, materials synthesis) routinely exceed 30s; a timeout
    # below the model's legitimate working time burns all retry attempts
    # on a healthy request. 120s per attempt is the observed-safe default.
    timeout: int = 120
    max_retries: int = 2
    # Base multiplier for the inter-attempt backoff schedule (seconds).
    # 0 disables sleeping (used by unit tests).
    backoff_base: float = 1.0
    
    @classmethod
    def from_environment(cls) -> "NineRouterConfig":
        """Load configuration from environment variables (.env dulu)."""
        _load_dotenv()
        api_key = os.getenv("NINE_ROUTER_API_KEY")
        base_url = os.getenv("NINE_ROUTER_BASE_URL", "http://localhost:20128")
        combo = os.getenv("NINE_ROUTER_COMBO", "rpm")
        timeout = int(os.getenv("NINE_ROUTER_TIMEOUT", "120"))
        max_retries = int(os.getenv("NINE_ROUTER_MAX_RETRIES", "2"))
        backoff_base = float(os.getenv("NINE_ROUTER_BACKOFF_BASE", "1.0"))
        
        return cls(
            base_url=base_url,
            api_key=api_key,
            combo=combo,
            timeout=timeout,
            max_retries=max_retries,
            backoff_base=backoff_base
        )


def detect_truncated_response(text: str) -> bool:
    """Deterministic truncation heuristic for model output (metadata only).

    Returns True when ``text`` looks cut off mid-structure: unbalanced
    braces/brackets, an odd number of unescaped quotes (ends inside a
    string literal), or a trailing comma/colon. Complete valid JSON
    NEVER matches (verified by unit test). Empty text is NOT truncation
    (it has its own ``empty`` flag). This only classifies — validation
    and retry policy are unchanged.
    """
    if not text or not text.strip():
        return False
    try:
        json.loads(text.strip())
        return False
    except (json.JSONDecodeError, ValueError):
        pass
    s = text.strip()
    if s[-1] in (',', ':'):
        return True
    if s.count('{') != s.count('}'):
        return True
    if s.count('[') != s.count(']'):
        return True
    # A quote is escaped iff preceded by an odd number of backslashes.
    unescaped = sum(
        1 for m in re.finditer(r'(\\*)"', s) if len(m.group(1)) % 2 == 0
    )
    if unescaped % 2 == 1:
        return True
    return False


def _extract_json(text: str) -> object:
    """Harden JSON extraction from model output (NOT a repair pass).

    Handles the legitimate formatting cases the model produces:
    1. Plain JSON (fast path).
    2. Markdown-fenced JSON (```json ... ```).
    3. JSON embedded in surrounding commentary (first {..last} or [..]).

    A genuinely malformed JSON body (e.g. "Expecting ',' delimiter") is
    NEVER silently repaired — it raises ValidationError so the bounded
    retry asks the model for a clean re-response.
    """
    if not text or not text.strip():
        raise ValidationError("Empty content in response message")
    s = text.strip()
    fence = re.match(
        r"^```(?:json)?\s*(.*?)\s*```$", s, re.DOTALL
    )
    if fence:
        s = fence.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Commentary-wrapped: slice from first brace/bracket to the last one.
    last_err: Optional[Exception] = None
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = s.find(open_ch)
        end = s.rfind(close_ch)
        if start != -1 and end > start:
            candidate = s[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as e:
                last_err = e
    if last_err is not None:
        raise ValidationError(f"AI response is not valid JSON: {last_err}")
    raise ValidationError(
        "AI response is not valid JSON: no JSON object or array found"
    )


class NineRouterClient:
    """Client for 9Router API with error handling, retry, and timeout."""
    
    def __init__(self, config: Optional[NineRouterConfig] = None):
        """Initialize client with configuration."""
        self.config = config or NineRouterConfig.from_environment()
        self._validate_config()
        # Metadata of the most recent generate_text call (METADATA ONLY:
        # char count + empty/truncated flags, never raw content, never
        # secrets). Consumed by the pipeline's generation-log audit trail.
        self.last_response_meta: Optional[Dict] = None
    
    def _validate_config(self) -> None:
        """Validate configuration."""
        if not self.config.base_url:
            raise ValueError("NINE_ROUTER_BASE_URL not configured")
        if not self.config.combo:
            raise ValueError("NINE_ROUTER_COMBO not configured")
        if self.config.combo not in ["rpm", "modul", "automation", "bu"]:
            logger.warning(
                f"Unusual combo value: {self.config.combo}. "
                f"Expected: rpm, modul, automation, or bu"
            )
    
    def _get_headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = {
            "Content-Type": "application/json",
        }
        
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        return headers
    
    def _handle_response(self, response: requests.Response) -> Dict:
        """Handle API response with error checking."""
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            logger.error("Authentication failed - invalid or missing API key")
            raise AuthenticationError(
                "Authentication failed. Check NINE_ROUTER_API_KEY."
            )
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            logger.error("Rate limit exceeded (Retry-After: %s)", retry_after)
            exc = RateLimitError("Rate limit exceeded. Please retry later.")
            exc.retry_after = retry_after  # honored (capped) by the retry loop
            raise exc
        elif 500 <= response.status_code < 600:
            logger.error(f"Server error: {response.status_code}")
            raise ServerError(f"Server error: {response.status_code}")
        else:
            logger.error(f"Unexpected status {response.status_code}")
            try:
                error_data = response.json()
                raise NineRouterError(
                    f"API error {response.status_code}: {error_data}"
                )
            except json.JSONDecodeError:
                raise NineRouterError(
                    f"API error {response.status_code}: {response.text}"
                )

    def _sleep_before_retry(self, attempt: int, error: Exception) -> None:
        """Bounded non-busy backoff before the next attempt.

        ``attempt`` is the 0-based index of the attempt that just failed.
        Schedule: 1st retry -> 1s, 2nd retry -> 3s (x backoff_base), capped
        at MAX_BACKOFF_SECONDS. A 429 Retry-After is honored up to the cap.
        No sleep after the final attempt.
        """
        if attempt >= self.config.max_retries:
            return
        delay = self.config.backoff_base * RETRY_BACKOFF_SCHEDULE.get(
            attempt, 3.0
        )
        retry_after = getattr(error, "retry_after", None)
        if retry_after is not None:
            try:
                delay = max(delay, min(float(retry_after), MAX_BACKOFF_SECONDS))
            except (TypeError, ValueError):
                pass
        delay = min(delay, MAX_BACKOFF_SECONDS)
        if delay > 0:
            logger.info("Backing off %.1fs before retry", delay)
            time.sleep(delay)

    def _make_request(self, endpoint: str, data: Dict) -> Dict:
        """Make HTTP request with classified, bounded retry logic.

        Retryable: TimeoutError, RateLimitError (429), ServerError (5xx),
        NetworkError (connection reset/dropped). Non-retryable: everything
        else (auth, 4xx, unexpected statuses) and any error after the last
        attempt — honest failure, no fake success.
        """
        url = f"{self.config.base_url}{endpoint}"
        headers = self._get_headers()
        
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(
                    f"9Router request (attempt {attempt + 1}): "
                    f"{endpoint}, combo={self.config.combo}"
                )
                
                try:
                    response = requests.post(
                        url,
                        json=data,
                        headers=headers,
                        timeout=self.config.timeout
                    )
                except requests.exceptions.Timeout:
                    logger.error("Request timeout")
                    raise TimeoutError(
                        f"Request timeout after {self.config.timeout}s"
                    )
                except requests.exceptions.ConnectionError as e:
                    logger.error("Connection failure: %s", e)
                    raise NetworkError(
                        f"Connection failure: {type(e).__name__}"
                    )
                
                return self._handle_response(response)
                
            except (TimeoutError, RateLimitError, ServerError,
                    NetworkError) as e:
                last_error = e
                if attempt < self.config.max_retries:
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}), retrying: {e}"
                    )
                    self._sleep_before_retry(attempt, e)
                    continue
                raise
            except (AuthenticationError, ValidationError) as e:
                # Don't retry these
                raise
        
        if last_error:
            raise last_error
        raise NineRouterError("Request failed after retries")
    
    def health_check(self) -> bool:
        """Check if 9Router is healthy."""
        try:
            response = requests.get(
                f"{self.config.base_url}/api/health",
                timeout=self.config.timeout
            )
            data = response.json()
            is_ok = data.get("ok", False)
            logger.info(f"9Router health check: {'OK' if is_ok else 'NOT OK'}")
            return is_ok
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        json_format: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        Generate text using 9Router with OpenAI-compatible interface.
        
        Args:
            prompt: User prompt/request
            system_instruction: Optional system message
            json_format: If True, instruct model to respond with valid JSON
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens in response
        
        Returns:
            Generated text
        
        Raises:
            NineRouterError: Various error conditions (auth, timeout, etc.)
        """
        messages = []
        
        if system_instruction:
            messages.append({
                "role": "system",
                "content": system_instruction
            })
        
        # Add JSON format instruction if requested
        if json_format:
            prompt = (
                f"{prompt}\n\n"
                "IMPORTANT: Respond with ONLY valid JSON, no markdown or extra text. "
                "Your entire response must be parseable as JSON."
            )
        
        messages.append({
            "role": "user",
            "content": prompt
        })
        
        request_data = {
            "model": self.config.combo,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        try:
            response_data = self._make_request(
                "/v1/chat/completions",
                request_data
            )
            
            # Parse OpenAI-compatible response
            if "choices" not in response_data:
                raise ValidationError(
                    f"Invalid response format: missing 'choices'"
                )
            
            if not response_data["choices"]:
                raise ValidationError("Empty choices in response")
            
            choice = response_data["choices"][0]
            if "message" not in choice:
                raise ValidationError(
                    f"Invalid choice format: missing 'message'"
                )
            
            content = choice["message"].get("content", "")
            # Token usage aktual bila provider menyediakannya (metadata
            # saja; tidak ada estimasi/angka buatan bila absen).
            usage = response_data.get("usage") or {}
            output_tokens = usage.get("completion_tokens")
            if not isinstance(output_tokens, int):
                output_tokens = None
            self.last_response_meta = {
                'response_chars': len(content) if content else 0,
                'empty': not content or not content.strip(),
                'truncated': detect_truncated_response(content),
                'output_tokens': output_tokens,
            }
            if not content:
                raise ValidationError("Empty content in response message")

            logger.debug(f"Generated text ({len(content)} chars)")
            return content

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse API response as JSON: {e}")
            raise ValidationError(f"Invalid JSON in API response: {e}")
        except (ValidationError, NineRouterError):
            # Envelope/HTTP failure: no model content reached us.
            if self.last_response_meta is None:
                self.last_response_meta = {
                    'response_chars': 0, 'empty': True, 'truncated': False,
                    'output_tokens': None,
                }
            raise
        except Exception:
            # Transport-level failure before any model content existed.
            self.last_response_meta = {
                'response_chars': 0, 'empty': True, 'truncated': False,
                'output_tokens': None,
            }
            raise
    
    def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        expected_schema: Optional[Dict] = None,
        # Rendah (0.1) agar output terstruktur deterministik dan patuh
        # instruksi skema/level: model lalai (level C2, top-level array)
        # pada temperatur lebih tinggi. Bukan pelonggaran validasi —
        # seluruh gate stage tetap menolak output invalid.
        temperature: float = 0.1,
        max_tokens: int = 2000
    ) -> Dict:
        """
        Generate structured JSON output using 9Router.
        
        Args:
            prompt: Request for JSON generation
            system_instruction: Optional system message
            expected_schema: Optional schema for validation
            temperature: Lower temp for more consistent JSON
            max_tokens: Maximum tokens in response
        
        Returns:
            Parsed JSON object
        
        Raises:
            ValidationError: If response is not valid JSON
        """
        text = None
        attempts = self.config.max_retries + 1
        recovery_added = False
        last_error: Optional[Exception] = None
        for attempt in range(attempts):
            try:
                text = self.generate_text(
                    prompt,
                    system_instruction=system_instruction,
                    json_format=True,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                data = _extract_json(text)
                logger.debug(f"Generated valid JSON ({len(json.dumps(data))} chars)")
                return data
            except ValidationError as e:
                # Content-level transient failure (malformed/empty model JSON,
                # broken envelope). Bounded retry with the SAME task: the
                # one-line recovery note changes output format only — never
                # the curriculum context or requested schema. Non-retryable
                # client errors (auth, 4xx after HTTP retries) propagate
                # uncaught from generate_text.
                last_error = e
                if attempt < attempts - 1:
                    logger.warning(
                        "JSON attempt %d/%d failed (%s); retrying with "
                        "format-recovery note",
                        attempt + 1, attempts, e,
                    )
                    if not recovery_added:
                        prompt = prompt + JSON_RETRY_NOTE
                        recovery_added = True
                    self._sleep_before_retry(attempt, e)
                    continue
                logger.error(
                    "JSON generation failed after %d attempts: %s",
                    attempts, e,
                )
                raise
        # Unreachable (loop always returns or raises); kept as a guard.
        raise last_error or ValidationError(
            "JSON generation failed without a specific error"
        )
