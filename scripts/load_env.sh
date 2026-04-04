#!/usr/bin/env bash

load_dotenv_preserve_existing() {
  local env_file="${1:-.env}"
  local line key value

  if [[ ! -f "$env_file" ]]; then
    return 0
  fi

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue

    line="${line#"${line%%[![:space:]]*}"}"
    if [[ "$line" =~ ^export[[:space:]]+ ]]; then
      line="${line#export }"
    fi

    key="${line%%=*}"
    value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"

    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      continue
    fi

    if [[ -n "${!key+x}" ]]; then
      export "$key"
      continue
    fi

    eval "export ${key}=${value}"
  done < "$env_file"
}

sync_llm_env_aliases() {
  if [[ -z "${SCW_LLM_BASE_URL:-}" && -n "${OPENAI_API_BASE:-}" ]]; then
    export SCW_LLM_BASE_URL="${OPENAI_API_BASE}"
  fi
  if [[ -z "${SCW_SECRET_KEY_LLM:-}" && -n "${OPENAI_API_KEY:-}" ]]; then
    export SCW_SECRET_KEY_LLM="${OPENAI_API_KEY}"
  fi
  if [[ -z "${SCW_LLM_MODEL:-}" && -n "${OPENAI_MODEL:-}" ]]; then
    export SCW_LLM_MODEL="${OPENAI_MODEL}"
  fi

  if [[ -n "${SCW_LLM_BASE_URL:-}" ]]; then
    export OPENAI_API_BASE="${SCW_LLM_BASE_URL}"
  fi
  if [[ -n "${SCW_SECRET_KEY_LLM:-}" ]]; then
    export OPENAI_API_KEY="${SCW_SECRET_KEY_LLM}"
  fi
  if [[ -n "${SCW_LLM_MODEL:-}" ]]; then
    export OPENAI_MODEL="${SCW_LLM_MODEL}"
  fi

  if [[ -z "${SCW_API_KEY:-}" && -n "${SCW_SECRET_KEY_LLM:-}" ]]; then
    export SCW_API_KEY="${SCW_SECRET_KEY_LLM}"
  fi
  if [[ -z "${SCW_SECRET_KEY_LLM:-}" && -n "${SCW_API_KEY:-}" ]]; then
    export SCW_SECRET_KEY_LLM="${SCW_API_KEY}"
  fi

  if [[ -z "${SCW_CHAT_BASE_URL:-}" && -n "${SCW_LLM_BASE_URL:-}" ]]; then
    export SCW_CHAT_BASE_URL="${SCW_LLM_BASE_URL}"
  fi
  if [[ -z "${SCW_EMBEDDING_BASE_URL:-}" && -n "${SCW_LLM_BASE_URL:-}" ]]; then
    export SCW_EMBEDDING_BASE_URL="${SCW_LLM_BASE_URL}"
  fi
  if [[ -z "${SCW_LLM_BASE_URL:-}" && -n "${SCW_CHAT_BASE_URL:-}" ]]; then
    export SCW_LLM_BASE_URL="${SCW_CHAT_BASE_URL}"
  fi

  if [[ -z "${SCW_CHAT_MODEL:-}" && -n "${SCW_LLM_MODEL:-}" ]]; then
    export SCW_CHAT_MODEL="${SCW_LLM_MODEL}"
  fi
  if [[ -z "${SCW_LLM_MODEL:-}" && -n "${SCW_CHAT_MODEL:-}" ]]; then
    export SCW_LLM_MODEL="${SCW_CHAT_MODEL}"
  fi

  if [[ -z "${SCW_EMBEDDING_MODEL:-}" && -n "${OPENAI_EMBEDDING_MODEL:-}" ]]; then
    export SCW_EMBEDDING_MODEL="${OPENAI_EMBEDDING_MODEL}"
  fi
  if [[ -z "${OPENAI_EMBEDDING_MODEL:-}" && -n "${SCW_EMBEDDING_MODEL:-}" ]]; then
    export OPENAI_EMBEDDING_MODEL="${SCW_EMBEDDING_MODEL}"
  fi

  if [[ -z "${OPENAI_EMBEDDING_VECTOR_SIZE:-}" ]]; then
    case "${OPENAI_EMBEDDING_MODEL:-bge-multilingual-gemma2}" in
      qwen3-embedding-8b)
        export OPENAI_EMBEDDING_VECTOR_SIZE=4096
        ;;
      *)
        export OPENAI_EMBEDDING_VECTOR_SIZE=3584
        ;;
    esac
  fi
}
