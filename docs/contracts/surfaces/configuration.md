# Surface contract: configuration

## Boundary and consumers
The Python server and `init-config` CLI consume one user configuration file, `~/.config/ad-linux-tv/config.yaml`. It is server-side only; browser clients receive service catalogue and page size, never authentication material.

## Inputs and schema
YAML has required `bind`, `port`, `page_size`, `auth`, `services` and optional `proxy`. Bind is an IP address; bridge port is fixed at 8765; page size is integer 1–100. `auth` has base64 salt (at least 16 decoded bytes), verifier (32 decoded bytes), and optional boolean `require_pin` (legacy default `true`). New generated configurations explicitly set `require_pin: false`; existing files retain their saved mode. Services is a non-empty list of entries with required `{id,name,url}` and optional `color` (`#RRGGBB`): unique lowercase safe IDs (1–32 chars), names 1–80 chars, validated HTTPS service URLs. Initial generated services are VK Видео, КиноПоиск, Яндекс Музыка, YouTube, KION, and Браузер (`https://ya.ru/`), each with a default tile color. Existing configurations without colors remain valid.

`proxy` has `mode: system` or `mode: none`, or `mode: custom` with `protocol: http|socks5`, a hostname/IP and integer port 1–65535. It applies only to the dedicated TV Firefox profile. New configurations select system proxy; an existing Beelink configuration without the field retains its pre-existing local Xray profile until the user changes the setting. Manual proxy keeps localhost/private LAN bypass. Proxy credentials are not accepted.

Optional `audio` contains `browser` and `player` integer levels from 0–100; absent values default to 100. These are the saved Firefox stream and accessible page-player targets. Selected output and its volume retain their existing TV-user audio preference. Optional `pointer.acceleration` is an integer 0–100, default 50; zero preserves the former constant cursor mapping. Settings save these fields atomically in the same private config file.

`init-config` generates a random disabled PIN verifier without prompting. Enabling or replacing a four-digit PIN in TV/phone settings writes a PBKDF2-HMAC-SHA256 verifier (310,000 rounds) to config and the code to the existing local-TV-only mode-0600 display file. Keep both files private; never publish or log them. Installer preserves existing configuration; uninstall preserves it.

## Outputs and failures
Invalid syntax/schema/field values fail closed with safe, generic or field-specific configuration errors; parser internals and secrets are not propagated. Launcher shows a configuration error rather than service tiles when loading fails. Bridge endpoint port must stay synchronized with extension localhost port 8765. PIN mode/code changes take effect immediately and invalidate all phone sessions. Proxy changes are saved immediately, but Firefox reads them after the user activates the offered TV-session restart. Invalid updates preserve the previous setting.

## Verification and non-goals
Automated config tests validate accepted/rejected schema, persistence, session invalidation and safe errors. Live target checks cover the Settings page and proxy inference without altering the current PIN or proxy. No secrets in client config, URLs, status, or logs.

Related: [MVP feature](../features/media-center-mvp.md), [TV launcher](tv-launcher.md), [phone remote](phone-remote.md), [Kubuntu operation](kubuntu-operation.md).
