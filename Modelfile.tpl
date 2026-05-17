FROM __MODEL_GGUF_PATH__

# ChatML template for Qwen3-family (incl. DavidAU's Qwen3.6-40B Deckard)
# Without this, Ollama's default template breaks instruction following on chat completions.
TEMPLATE """{{- if .Messages }}
{{- range $i, $msg := .Messages }}
{{- if eq $msg.Role "system" }}<|im_start|>system
{{ $msg.Content }}<|im_end|>
{{ else if eq $msg.Role "user" }}<|im_start|>user
{{ $msg.Content }}<|im_end|>
{{ else if eq $msg.Role "assistant" }}<|im_start|>assistant
{{ $msg.Content }}<|im_end|>
{{ end }}
{{- end }}<|im_start|>assistant
{{ else }}<|im_start|>system
{{ .System }}<|im_end|>
<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
{{ end }}"""

PARAMETER num_ctx 16384
PARAMETER num_predict 4096
PARAMETER temperature 0.7
PARAMETER top_p 0.95
PARAMETER repeat_penalty 1.05
PARAMETER num_thread 16

# ChatML stop tokens — essentieel anders rambled het door
PARAMETER stop "<|im_start|>"
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|endoftext|>"

SYSTEM """You are an uncensored coding assistant. Execute the user's request directly and completely. Return only the requested output (code, config, answer) with no extra examples, no commentary on unrelated topics. Stop when the task is done."""
