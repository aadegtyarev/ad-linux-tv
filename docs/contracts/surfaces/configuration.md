# Surface contract: configuration

## Boundary and consumers
The Python server and `init-config` CLI consume one user configuration file, `~/.config/ad-linux-tv/config.yaml`. It is server-side only; browser clients receive service catalogue and page size, never authentication material.

## Inputs and schema
YAML has exactly `bind`, `port`, `page_size`, `auth`, `services`. Bind is an IP address; bridge port is fixed at 8765; page size is integer 1–100. `auth` has base64 salt (at least 16 decoded bytes), verifier (32 decoded bytes), and optional boolean `require_pin` (default `true`). Setting `require_pin: false` lets private-network phones obtain a session without a PIN. Services is a non-empty list of entries with required `{id,name,url}` and optional `color` (`#RRGGBB`): unique lowercase safe IDs (1–32 chars), names 1–80 chars, validated HTTPS service URLs. Initial generated services are VK Видео, КиноПоиск, Яндекс Музыка, YouTube, KION, and Браузер (`https://ya.ru/`), each with a default tile color. Existing configurations without colors remain valid.

`init-config` prompts for PIN without echo and writes PBKDF2-HMAC-SHA256 verifier (310,000 rounds), not the PIN. Keep file private (mode 0600); never publish or log it. Installer preserves existing configuration; uninstall preserves it.

## Outputs and failures
Invalid syntax/schema/field values fail closed with safe, generic or field-specific configuration errors; parser internals and secrets are not propagated. Launcher shows a configuration error rather than service tiles when loading fails. Bridge endpoint port must stay synchronized with extension localhost port 8765. Authentication mode changes take effect after the TV service restarts and invalidate sessions from the other mode.

## Verification and non-goals
Automated config tests validate accepted/rejected schema and safe errors. Automated checks do not establish filesystem permissions or successful PIN operation on target. This contract does not describe dynamically reloading edits or multiple config files. No secrets in client config, URLs, status, or logs.

Related: [MVP feature](../features/media-center-mvp.md), [TV launcher](tv-launcher.md), [phone remote](phone-remote.md), [Kubuntu operation](kubuntu-operation.md).
