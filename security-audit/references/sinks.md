# Sink checklist: grep before you read

Grep the scope for these first, then trace each hit back to its source (step 3 of the skill). A hit is a lead, not a finding: it becomes one only when an untrusted value reaches it with no adequate control in between. Use `rg -n` (ripgrep) or `grep -rnE`; the patterns are extended regexes, trimmed for recall over precision.

## Cross-language sources (what "untrusted" looks like)
- Request data: `request\.(args|form|json|files|headers|cookies|GET|POST)`, `req\.(body|query|params|headers)`, `params\[`, `c\.Query|c\.Param|r\.URL\.Query|r\.FormValue`.
- Environment or config read at runtime from user-writable places; CLI arguments; file contents; database rows that users wrote.
- Third-party responses: anything after `requests\.(get|post)|httpx|fetch\(|axios|http\.Get` to an external host.
- LLM output and retrieved documents: RAG chunks, scraped pages, tool results, e-mails, calendar text, user messages.

## Python
- Command execution: `subprocess\.(run|Popen|call|check_output|check_call)\(.*shell=True`, `os\.(system|popen|exec[lv]p?e?|spawn)`, `pty\.spawn`.
- Code execution and deserialization: `\beval\(|\bexec\(|compile\(`, `pickle\.loads?|cPickle|dill\.|shelve\.`, `yaml\.(load|load_all|unsafe_load)\((?!.*SafeLoader)`, `marshal\.loads`, `jsonpickle`, `importlib\.import_module\(` with a dynamic name, `__import__\(`.
- Queries: `execute\(.*(f"|f'|%|\.format\(|\+)`, `text\(f"`, `\.raw\(`, `\.extra\(`, `\$where`, `find\(\{.*\$`, `aggregate\(.*\$`, string-built `ORDER BY` or table names.
- Templates and HTML: `render_template_string\(`, `Markup\(`, `\| ?safe`, `autoescape=False`, `Template\(.*\)\.render`, `mark_safe\(`, `format_html\(.*\+`.
- Files and paths: `open\(.*(request|user|param|arg|name|filename)`, `os\.path\.join\(.*(request|name|filename)`, `send_file\(|send_from_directory\(`, `\.extractall\(`, `shutil\.(copy|move|rmtree)\(` on user paths, `tempfile\.mktemp`.
- URLs and SSRF: `requests\.(get|post|put|delete)\(.*(url|host|endpoint|uri)\b`, `urllib\.request\.urlopen\(`, `httpx\.`, `aiohttp\.ClientSession`, `redirect\(.*(next|url|return|target)`.
- Crypto: `hashlib\.(md5|sha1)\(` for passwords or signatures, `random\.(random|randint|choice|getrandbits)` for tokens, `MODE_ECB`, `verify=False`, `ssl\._create_unverified_context|CERT_NONE`, `jwt\.decode\(.*(verify=False|verify_signature.*False)`, `algorithms=\[.*none`.
- Secrets: `(api[_-]?key|secret|token|password|passwd|private_key)\s*[=:]\s*['"][^'"]{8,}`, `AKIA[0-9A-Z]{16}`, `-----BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY`, `mongodb(\+srv)?://[^/\s]+:[^@\s]+@`, `postgres(ql)?://[^/\s]+:[^@\s]+@`.
- Framework: `debug=True`, `CORS\(.*origins=.*\*|allow_origins=\["\*"\]`, route handlers with no auth dependency next to ones that have it, `csrf_exempt`, `SECRET_KEY\s*=\s*['"]`, `ALLOWED_HOSTS\s*=\s*\[\s*['"]\*`.

## JavaScript / TypeScript
- Command and code: `child_process|execSync\(|exec\(|spawn\(.*shell:\s*true`, `\beval\(|new Function\(|vm\.(run|compile)`, `setTimeout\(\s*['"]`.
- HTML and XSS: `innerHTML\s*=|outerHTML\s*=|insertAdjacentHTML\(|document\.write\(`, `dangerouslySetInnerHTML`, `v-html`, `\[innerHTML\]`, `bypassSecurityTrust`, markdown renderers (`marked\(|markdown-it|showdown|remark`) with no sanitizer, `res\.send\(.*\+`.
- Queries: `query\(\s*[` + "`" + `'"].*(\$\{|\+\s*(req|params|input))`, `\$where`, `sequelize\.query\(`, `knex\.raw\(`, `\.find\(\s*req\.(body|query)` (NoSQL operator injection).
- Files and paths: `fs\.(readFile|writeFile|createReadStream|unlink|rm|readdir)(Sync)?\(.*(req|params|query|input)`, `path\.(join|resolve)\(.*(req|params|query)`, `res\.sendFile\(`, `express\.static\(` with a user-controlled root.
- URLs, SSRF, redirects: `fetch\(\s*(req|url|params|input)`, `axios\.(get|post|request)\(.*(req|url|input)`, `res\.redirect\(.*(req|url|next|return)`, `new URL\(.*req`.
- Deserialization and prototype pollution: untrusted `JSON\.parse\(` flowing into `Object\.assign\(|_\.merge\(|deepmerge\(|lodash\.set|\.defaultsDeep`, `node-serialize|unserialize\(`, `yaml\.load\(`, `__proto__`.
- Crypto and auth: `jwt\.verify\(.*algorithms|jwt\.decode\(` without verify, `algorithms:\s*\[\s*['"]none`, `Math\.random\(\)` for tokens or IDs, `createHash\(['"](md5|sha1)`, `rejectUnauthorized:\s*false`, `NODE_TLS_REJECT_UNAUTHORIZED`.
- Config: `cors\(\s*\)|origin:\s*['"]\*`, missing `helmet`, cookies without `httpOnly|secure|sameSite`, no body-size limit on upload routes, `app\.use\(express\.json\(\)\)` with no limit on public routes.

## Go
- `exec\.Command\(.*(r\.|req|input|param|arg)`, `"sh", "-c"`, `template\.HTML\(|template\.JS\(`, `text/template` used for HTML, `fmt\.Sprintf\(.*(SELECT|INSERT|UPDATE|DELETE)`, `db\.(Query|Exec|QueryRow)\(.*\+`, `http\.Get\(.*(r\.|param|url)`, `os\.(Open|ReadFile|Create)\(.*(r\.|param)`, `filepath\.Join\(.*r\.`, `InsecureSkipVerify:\s*true`, `math/rand` for secrets, `unsafe\.`.

## Rust / Java / Ruby / PHP (quick set)
- Rust: `Command::new\(.*(input|arg)`, `unsafe\s*\{`, `format!\(.*(SELECT|INSERT|UPDATE)`, `danger_accept_invalid_certs\(true\)`, `std::fs::(read|write|remove)` on user paths.
- Java: `Runtime\.getRuntime\(\)\.exec\(`, `ProcessBuilder\(`, `Statement\.(execute|executeQuery|executeUpdate)\(.*\+`, `createQuery\(.*\+`, `ObjectInputStream|readObject\(|XMLDecoder|XStream`, `new File\(.*(request|param)`, `setAllowedOrigins\("\*"\)`, `TrustAllCerts|X509TrustManager`, `MessageDigest\.getInstance\("(MD5|SHA-1)"`, `@CrossOrigin\(\s*\)`.
- Ruby: `\b(system|exec|spawn)\(|%x\(`, backtick commands with `#{`, `\beval\(|instance_eval|send\(params|constantize`, `Marshal\.load|YAML\.load\((?!.*safe)`, `\.where\("#\{|find_by_sql\(.*#\{|\.order\(params`, `html_safe|raw\(`, `send_file\(params|File\.(read|open)\(params`, `redirect_to params`, `open\(params` (Kernel#open).
- PHP: `\b(system|exec|shell_exec|passthru|popen|proc_open)\(`, `\beval\(|assert\(|preg_replace\(.*/e`, `unserialize\(`, `(include|require)(_once)?\s*\(?\s*\$`, `mysqli_query\(.*\$|->query\(.*\$_(GET|POST)`, `echo \$_(GET|POST|REQUEST|COOKIE)`, `move_uploaded_file\(`, `header\("Location: *".*\$`, `file_get_contents\(\$|fopen\(\$`.

## Shell, CI, containers, config
- Shell: `eval "|\$\(.*\$\{?[A-Z_]+`, unquoted `$VAR` in `rm -rf`, `curl .* \| (ba)?sh`, `chmod (777|-R 777)`, `sudo` in scripts, secrets in `set -x` output.
- CI: secrets echoed (`echo .*\$\{\{ ?secrets`), `pull_request_target` with a checkout of the PR head, unpinned actions (`uses: .*@(main|master|v?\d+)$` instead of a SHA), `run:` steps interpolating `github\.event\.(issue|pull_request|comment)\.(title|body)`.
- Docker / compose: `privileged:\s*true`, `network_mode:\s*host`, `/var/run/docker\.sock`, `USER root` or no `USER`, ports published on `0\.0\.0\.0` for admin UIs, secrets as `environment:` literals, `:latest` tags, `ADD http`.
- Kubernetes: `hostNetwork|hostPID|privileged:\s*true|allowPrivilegeEscalation:\s*true`, `automountServiceAccountToken` left on, wildcard RBAC (`verbs:\s*\["\*"\]|resources:\s*\["\*"\]`).
- Reverse proxy: `proxy_pass \$`, missing `proxy_set_header Host`, absent security headers, no `client_max_body_size` on upload paths, `auth_basic off` on admin locations.

## Non-web code: bots, CLIs, pipelines, schedulers, agents

Most of the language sections above assume request handlers. When the code has none, the hunting surface is every place it talks to the outside world, in either direction:
- Sources: every outbound call and what comes back (`requests|httpx|aiohttp|urllib|fetch|axios|http\.Get`, RSS/scrape parsers, message queues, mail, webhooks it receives), every file or environment value it reads, every database row another process wrote.
- Sinks: subprocess and shell (see the language section), file writes and path building from fetched data, deserialization of fetched payloads (`pickle|yaml\.load|json\.loads` into merges), LLM prompt assembly from fetched text (next section), outbound calls whose URL, host or auth header is built from data, and anything that sends (mail, chat, push, money).
- Configuration: plaintext transports to other hosts (`http://|mongodb://|redis://|amqp://` without TLS on a shared network), credentials in URLs, retries without back-off against third parties, schedules that can overlap themselves (TOCTOU on shared state), logs that echo fetched content or config.
- Trust model: name it in section 0.5 (LAN-only, single operator, internet-facing) and rate severity against it; a plaintext LAN call is Low for a single-operator bot and High for anything reachable from the internet.

## LLM / agent code
- Prompt assembly: `f".*\{(user|query|doc|content|retrieved|snippet|message|tool_result)` or `\.format\(.*(user|doc|content)`, templates that inline retrieved text with no delimiter or role separation, system prompts that carry secrets or internal URLs.
- Tools: tool schemas whose handlers run `subprocess`, `eval`, file writes, HTTP requests, or DB writes from model-provided arguments without allow-lists or confirmation; tool results fed straight back as instructions; tools that can send messages or money.
- Output handling: model output into `innerHTML|dangerouslySetInnerHTML|render_template_string|Markup`, into `eval|exec|subprocess|cursor\.execute|open\(`, or into `redirect\(`.
- Cost and abuse: no `max_tokens`, no per-user rate limit, unbounded loops on `tool_use`, retries without back-off, caches keyed on user-controlled text.

## Not a sink on its own (common false positives)
- `subprocess.run([...])` with a list argument, no `shell=True`, and every element constant or validated.
- Parameterised queries (`execute("... %s", (v,))`, `?` placeholders, ORM filters with keyword arguments).
- `innerHTML` assigned a constant or a `DOMPurify.sanitize(...)` result.
- `yaml.safe_load`, `json.loads` (unless the result is merged into a prototype or config object).
- `hashlib.md5` used for a cache key, not for passwords or signatures.
