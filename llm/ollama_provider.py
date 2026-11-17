import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from core.config import settings


class LLMError(RuntimeError):
    """A user-safe LLM connectivity or response error."""


class LLMResponseError(LLMError):
    """The model answered, but the answer could not be used (no JSON / no SQL).

    This is a model failure on that question, not an outage, so callers should
    score it as invalid output rather than fall back to the heuristic generator.
    """


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_duration_ns: int | None = None

    @property
    def total_tokens(self):
        if self.prompt_tokens is None and self.completion_tokens is None:
            return None
        return (self.prompt_tokens or 0) + (self.completion_tokens or 0)


class OllamaProvider:
    def __init__(self, base_url=None, model=None, timeout=None):
        self.base_url=(base_url or settings.ollama_base_url).rstrip('/')
        self.model=model or settings.ollama_model or 'qwen2.5-coder:7b'
        self.timeout=timeout or settings.llm_timeout_seconds

    def _request(self, prompt, system=None, retries=1):
        """POST to Ollama; a dropped connection or timeout is retried once before giving up."""
        for attempt in range(retries+1):
            try:
                return self._request_once(prompt, system)
            except LLMError as exc:
                if attempt>=retries or 'not found' in str(exc): raise
                time.sleep(3)

    def _request_once(self, prompt, system=None):
        payload={'model':self.model,'prompt':prompt,'stream':False,'keep_alive':settings.ollama_keep_alive,'options':{'temperature':0,'num_ctx':settings.ollama_num_ctx,'num_predict':settings.ollama_num_predict}}
        if system: payload['system']=system
        request=urllib.request.Request(self.base_url+'/api/generate', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body=json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            detail=exc.read().decode('utf-8','replace')
            if exc.code == 404: raise LLMError(f"Ollama model '{self.model}' was not found. Run: ollama pull {self.model}") from exc
            raise LLMError(f'Ollama returned HTTP {exc.code}: {detail[:300]}') from exc
        except urllib.error.URLError as exc: raise LLMError(f'Ollama is unavailable at {self.base_url}: {exc.reason}') from exc
        except TimeoutError as exc: raise LLMError(f'Ollama timed out after {self.timeout}s') from exc
        except json.JSONDecodeError as exc: raise LLMError('Ollama returned invalid JSON') from exc
        return LLMResponse(body.get('response',''), body.get('prompt_eval_count'), body.get('eval_count'), body.get('total_duration'))

    def status(self):
        request=urllib.request.Request(self.base_url+'/api/tags', method='GET')
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout,5)) as response: tags=json.loads(response.read().decode())
            models={m.get('name') for m in tags.get('models',[])}
            return {'available':True,'model':self.model,'model_available':self.model in models,'models':sorted(x for x in models if x)}
        except Exception as exc: return {'available':False,'model':self.model,'model_available':False,'error':str(exc),'models':[]}

    def generate_json(self, prompt, system=None):
        response=self._request(prompt,system)
        text=response.text.strip().replace('```json','').replace('```','').strip()
        data=None
        try: data=json.loads(text)
        except json.JSONDecodeError:
            match=re.search(r'\{.*\}',text,re.S)
            if match:
                try: data=json.loads(match.group(0))
                except json.JSONDecodeError: data=None
        if isinstance(data,dict) and isinstance(data.get('sql'),list):
            data['sql']=' '.join(str(x) for x in data['sql'])
        if not isinstance(data,dict) or not isinstance(data.get('sql'),str):
            salvaged=_salvage_sql(text)
            if salvaged is None:
                raise LLMResponseError(f'Model reply had no usable JSON or SQL: {text[:200]!r}')
            data={'sql':salvaged,'plan':['(SQL recovered from a non-JSON reply)']}
        data.setdefault('plan',[])
        data['_usage']={'prompt_tokens':response.prompt_tokens,'completion_tokens':response.completion_tokens,'total_tokens':response.total_tokens,'duration_ns':response.total_duration_ns}
        return data

    def generate_explanation(self, prompt, system=None): return self._request(prompt,system)



def _salvage_sql(text):
    """Recover a SQL statement when the model ignored the JSON format."""
    match=re.search(r'"sql"\s*:\s*"((?:[^"\\]|\\.)*)"',text,re.S)  # truncated or invalid JSON with an sql field
    if match:
        try: return json.loads(f'"{match.group(1)}"').strip()
        except json.JSONDecodeError: pass
    match=re.search(r'\b(SELECT|WITH)\b[\s\S]*?(?=;|```|$)',text,re.I)
    return match.group(0).strip() if match else None
